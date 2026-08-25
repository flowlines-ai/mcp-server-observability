# Flowlines MCP telemetry contract

Use this contract for emitted telemetry. The Flowlines ingestion service accepts AGNTCY Observe MCP spans and vanilla OpenTelemetry GenAI/MCP spans, then canonicalizes and redacts them.

## OTLP destination

Use OTLP over HTTP/protobuf unless the target already sends through an OpenTelemetry Collector:

```text
OTEL_EXPORTER_OTLP_ENDPOINT=https://api.flowlines.ai
OTEL_EXPORTER_OTLP_HEADERS=x-flowlines-api-key=<deployment-secret>
OTEL_SERVICE_NAME=<stable-service-name>
```

The API accepts both `/traces` and `/v1/traces`. Exporters that require a signal-specific URL may use:

```text
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://api.flowlines.ai/v1/traces
```

Never commit the header value. Keep it in the deployment's secret manager. A Collector may own batching, retry, queueing, and the Flowlines exporter; the application still owns the span contract.

## Tool input contract

Every ordinary tool schema must require:

- `reason`: a short phrase explaining why the agent is making this specific call, without execution commentary;
- `user_intent`: one concise sentence stating what the end user is trying to accomplish. Callers keep it stable until the user's goal changes.

Both values must be non-empty strings. Flowlines' own server caps them at 128 and 256 characters respectively, which is a useful emitter guardrail but not an ingestion limit. The legacy `intent` name is accepted by ingestion but new integrations must publish `reason`.

Do not reconstruct either value with an LLM. Missing reasons remain visible for operational metrics but cannot participate fully in behavioral analysis; missing user intent produces a telemetry-quality issue.

Clients attach analytics identity to request metadata, outside tool arguments:

```json
{
  "name": "get_order",
  "arguments": {
    "reason": "Check whether the customer's order has shipped",
    "user_intent": "Get order 123 delivered",
    "order_id": "order-123"
  },
  "_meta": {
    "session.id": "support-session-42",
    "user.id": "customer-17"
  }
}
```

`session.id` and `user.id` are analytics dimensions, not authentication claims. Never authorize from them. If the server already authenticated the request, it may emit its verified subject as `user.id` and must ignore a caller-supplied spoofed value. Do not copy `_meta` into captured arguments.

## One span per tool execution

For an MCP server, emit one `SERVER` span around the complete tool call, after input validation and around the layer that returns the final client-visible MCP result. A useful span name is `execute_tool <tool-name>`.

Set these attributes:

| Attribute | Requirement | Value |
|---|---|---|
| `gen_ai.operation.name` | required | `execute_tool` |
| `gen_ai.tool.name` | required | published MCP tool name |
| `gen_ai.tool.call.reason` | required for behavioral analysis | validated `reason` |
| `session.user_intent` | required for session goal | validated `user_intent` |
| `gen_ai.tool.call.arguments` | required for evidence | serialized, valid JSON of the validated tool arguments |
| `gen_ai.tool.call.result` | required when a result exists | serialized, valid JSON of the final client-visible MCP result |
| `mcp.method.name` | required | `tools/call` |
| `mcp.server.name` | required | stable logical server name; do not rely on `service.name` |
| `gen_ai.tool.call.id` | required | fresh unique ID for this invocation |
| `mcp.request.id` | recommended | JSON-RPC request ID as a string |
| `session.id` | required for session association | non-empty client `_meta["session.id"]` |
| `user.id` | optional | verified identity when available, otherwise non-empty `_meta["user.id"]` |

The call ID identifies an invocation. It may remain stable only when retrying export of that same span. Never derive it solely from `mcp.request.id`; clients may reuse JSON-RPC IDs across stateless requests.

For compatibility during a staged reason rename, an emitter may also set `gen_ai.tool.call.intent` to the same value. New code must always set `gen_ai.tool.call.reason`.

Useful optional client attributes are:

- `mcp.client.name` and `mcp.client.version` from the MCP `initialize` handshake;
- `user_agent.original` and `mcp.protocol.version` from transport headers;
- `flowlines.auth.client_id` from a verified OAuth client identifier.

Keep OAuth client identity separate from the user-facing host name. Propagate incoming W3C trace context when available. Client and server spans carrying the same trace and call ID can be correlated by Flowlines.

## Session identity

Use an explicit client-supplied conversation identity whenever possible. Do not fall back to trace ID, authenticated user, OAuth client ID, a time window, or tool arguments.

An MCP transport session is not necessarily a conversation: reconnects may split one conversation and connection reuse may merge several. A server may expose its transport identity separately as `mcp.session.id`, but must not silently present it as a reliable conversation. If the product explicitly accepts a provisional transport fallback, label its source, reliability, and definition so downstream users can distinguish it.

## Payload and error boundary

Connecting supported instrumentation to Flowlines enables payload capture. There is no additional per-span opt-in marker.

Capture:

- the complete validated tool-argument object, excluding request `_meta`;
- the final bounded MCP `CallToolResult` or equivalent returned to the client;
- a safe public MCP error response when the call fails.

Do not capture:

- authorization headers, cookies, API keys, OAuth claims, or environment variables;
- request `_meta` as payload;
- backend exception messages, stack traces, exception events, or internal error objects;
- raw framework request/response objects.

Set span status to error and record only a bounded, sanitized `error.type`. Flowlines caps each canonical arguments/result value at 50,000 characters and replaces oversized values with a valid JSON truncation object. Preserve tighter target-server response bounds when they exist.

## `report_outcome`

Register a tool named `report_outcome` and tell agents to call it once as the last tool call before the final answer, including after read-only, partial, failed, or blocked work.

Its description must begin with an unconditional trigger such as `REQUIRED final call in every conversation` so deferred tool indexes expose the obligation. Its schema includes the same required `reason` and `user_intent` fields plus:

- `status`: required enum `accomplished`, `partial`, or `failed`;
- `outcome_summary`: required non-empty two-to-three-sentence description of what the agent is about to tell the user;
- `unmet_needs`: optional array of concrete missing questions, filters, or inaccessible data, one item per need.

The handler should return immediately with a small success result and should not mutate product data. The tool call itself is the report; Flowlines extracts its named arguments from telemetry. Treat it as the agent's self-report, not verified ground truth.

Include the final-call rule in the MCP server instructions as well as the tool description. If the server has bootstrap or context tools, their successful results may repeat a short reminder.

## End-to-end acceptance

After local in-memory span tests pass and live export is explicitly authorized:

1. Make ten ordinary test calls carrying `reason`, `user_intent`, one stable test `session.id`, and a test `user.id`.
2. Make one final `report_outcome` call in the same session.
3. Confirm Flowlines ingestion health shows eleven matched and accepted calls with no persistent pending calls.
4. Confirm tool name, server, success, latency, session intent, captured evidence, and reported outcome.
5. Treat clustering as eligible only after at least 20 valid-reason calls and three distinct normalized reasons.
6. Tool-loop detection requires three adjacent calls to the same server/tool/reason in one metadata session within ten minutes.
