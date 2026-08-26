# Vanilla OpenTelemetry integration

Use this path for TypeScript and for any language where an official OpenTelemetry SDK can create spans and export OTLP HTTP/protobuf. There is no Flowlines runtime package.

## Integrate at the execution boundary

Find or create one small adapter around the shared MCP tool dispatcher. The wrapper needs:

- published tool name;
- validated arguments, including `reason` and `user_intent`;
- JSON-RPC request ID and request `_meta`;
- a mandatory stable user ID resolved from verified authentication or required client metadata, plus verified or client-supplied name/email when available;
- incoming trace context when the transport exposes it;
- the final `CallToolResult` or equivalent after public error mapping.

The wrapper starts one server span, calls the handler, records the final result, sets status, ends the span in `finally`, and returns the result unchanged. Export failure must never change handler behavior.

If public error mapping currently happens outside the common dispatcher, move the span boundary outward or make the execution callback return both the client-visible result and an internal `failed` flag. Never attach the caught backend exception to the span.

## Attribute algorithm

Use the target SDK's public APIs to implement this logic:

```text
call_id = fresh UUID for this invocation
attributes = {
  gen_ai.operation.name: "execute_tool",
  gen_ai.tool.name: tool_name,
  gen_ai.tool.call.reason: validated_arguments.reason,
  session.user_intent: validated_arguments.user_intent,
  gen_ai.tool.call.arguments: JSON(validated_arguments),
  mcp.method.name: "tools/call",
  mcp.server.name: stable_server_name,
  gen_ai.tool.call.id: call_id,
  mcp.request.id: string(request_id),
}

if _meta["session.id"] is a non-empty string:
  attributes["session.id"] = bounded value

user = verified authenticated profile, otherwise validated client metadata
attributes["user.id"] = bounded stable user.id
if user.name exists: attributes["user.name"] = bounded name
if user.email exists: attributes["user.email"] = bounded email

start SERVER span "execute_tool <tool_name>"
execute handler and public MCP error mapping
set gen_ai.tool.call.result to JSON(final client-visible result)
set OK or ERROR status; on error set only a sanitized error.type
end span
```

Exclude `_meta` from the serialized arguments. Generate the call ID independently from the request ID. Reject or omit non-serializable payloads rather than falling back to object inspection that could expose internal state.

Resolve identity before entering the telemetry wrapper. Verified authentication/profile fields always win over client metadata. If the end user cannot be resolved, extend the server/client contract before declaring the integration complete; do not silently substitute an application, session, email, or generated ID. Runtime diagnostics may count a missing identity, but must remain fail-open and must not block the MCP result.

## TypeScript shape

With the official OpenTelemetry JavaScript packages, prefer a wrapper shaped like this and adapt it to the target SDK rather than copying it blindly:

```ts
import { randomUUID } from "node:crypto";
import {
  context,
  type Attributes,
  type Context,
  SpanKind,
  SpanStatusCode,
  trace,
  type Tracer,
} from "@opentelemetry/api";

type ToolRequest = {
  requestId?: string | number;
  _meta?: Record<string, unknown>;
};

type ToolExecution<T> = {
  result: T;
  failed?: boolean;
  errorType?: string;
};

type UserIdentity = {
  id: string;
  name?: string;
  email?: string;
  source: "verified" | "client_metadata";
};

export async function observeTool<T>(input: {
  tracer: Tracer;
  serverName: string;
  toolName: string;
  validatedArguments: Record<string, unknown> & {
    reason: string;
    user_intent: string;
  };
  request: ToolRequest;
  user: UserIdentity;
  parentContext?: Context;
  execute: () => Promise<ToolExecution<T>>;
}): Promise<T> {
  const attributes: Attributes = {
    "gen_ai.operation.name": "execute_tool",
    "gen_ai.tool.name": input.toolName,
    "gen_ai.tool.call.reason": input.validatedArguments.reason,
    "session.user_intent": input.validatedArguments.user_intent,
    "gen_ai.tool.call.arguments": JSON.stringify(input.validatedArguments),
    "mcp.method.name": "tools/call",
    "mcp.server.name": input.serverName,
    "gen_ai.tool.call.id": randomUUID(),
    "user.id": input.user.id,
  };

  if (input.request.requestId !== undefined) {
    attributes["mcp.request.id"] = String(input.request.requestId);
  }
  const sessionId = metadataString(input.request._meta, "session.id");
  if (sessionId !== undefined) attributes["session.id"] = sessionId;
  if (input.user.name !== undefined) attributes["user.name"] = input.user.name;
  if (input.user.email !== undefined) attributes["user.email"] = input.user.email;

  const span = input.tracer.startSpan(
    `execute_tool ${input.toolName}`,
    { kind: SpanKind.SERVER, attributes },
    input.parentContext ?? context.active(),
  );

  try {
    const activeContext = trace.setSpan(input.parentContext ?? context.active(), span);
    const execution = await context.with(activeContext, input.execute);
    span.setAttribute("gen_ai.tool.call.result", JSON.stringify(execution.result));
    if (execution.failed) {
      span.setStatus({ code: SpanStatusCode.ERROR });
      if (execution.errorType) span.setAttribute("error.type", safeErrorType(execution.errorType));
    } else {
      span.setStatus({ code: SpanStatusCode.OK });
    }
    return execution.result;
  } catch (error) {
    span.setStatus({ code: SpanStatusCode.ERROR });
    const errorType = error instanceof Error ? error.name : "UnknownError";
    span.setAttribute("error.type", safeErrorType(errorType));
    throw error;
  } finally {
    span.end();
  }
}

function metadataString(
  metadata: Record<string, unknown> | undefined,
  key: string,
): string | undefined {
  const value = metadata?.[key];
  if (typeof value !== "string") return undefined;
  const normalized = value.trim();
  return normalized === "" ? undefined : normalized.slice(0, 500);
}

function safeErrorType(value: string): string {
  return /^[A-Za-z0-9_.:/-]{1,128}$/.test(value) ? value : "Error";
}
```

Production code must handle a serialization failure explicitly and should use the target's existing payload bounds. Ensure that `execute` includes public error mapping so `execution.result` is safe. Do not call `recordException` with a backend exception.

## Provider and exporter

If the application already has a tracer provider, use `trace.getTracer(...)` or the equivalent and add no second provider. Confirm its OTLP pipeline reaches Flowlines directly or through the configured Collector.

When the MCP service owns a dedicated provider:

- create it once before starting the server;
- set a stable `service.name` resource and explicit `mcp.server.name` span attribute;
- use a batch span processor and an OTLP HTTP exporter configured from standard environment variables;
- use always-on sampling for dedicated MCP product spans;
- register standard W3C propagation and extract incoming transport headers when present;
- force-flush and shut down with a short bound during `SIGTERM`, `SIGINT`, or the runtime's equivalent;
- never await export or force-flush on every tool call.

Standard deployment configuration is:

```text
OTEL_TRACES_EXPORTER=otlp
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=https://api.flowlines.ai
OTEL_EXPORTER_OTLP_HEADERS=x-flowlines-api-key=<deployment-secret>
OTEL_SERVICE_NAME=<stable-mcp-service-name>
```

Use the target package manager, public package entry points, exact-version rules, and lockfile. Do not add an auto-instrumentation bundle when the focused tracing packages already satisfy the requirement.

## Tests

Use the language SDK's in-memory exporter and simple processor in unit tests. Assert the semantic contract, not the exact span implementation. Include a call whose request ID is intentionally reused and verify that two executions receive different call IDs. Include spoofed `_meta` user ID/name/email alongside a verified profile and confirm only the verified identity is exported. Include the metadata-only path and confirm it promotes exact `user.id`, `user.name`, and `user.email` attributes without serializing `_meta` into captured arguments.

Test an exception that contains a recognizable secret sentinel, map it to a public MCP error, and confirm the sentinel is absent from all attributes and events. Test shutdown separately with a fake or in-memory exporter; do not contact Flowlines from ordinary CI. During authorized end-to-end verification, save and verify the exact Flowlines user mapping from [contract.md](contract.md).
