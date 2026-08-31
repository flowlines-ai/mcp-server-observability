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
    "user.id": "customer-17",
    "user.name": "Ada Lovelace",
    "user.email": "ada@example.com"
  }
}
```

`session.id` and the client-supplied user fields are analytics metadata, not authentication claims. Never authorize from them. If the server already authenticated the request, emit its verified subject as `user.id`, use the corresponding trusted profile for name/email, and ignore caller-supplied spoofed values. Do not copy `_meta` into captured arguments.

This skill requires a non-empty `user.id` for every emitted MCP span. Use a stable, immutable application user ID that identifies the same person across sessions. Do not use an email address, display name, session ID, trace ID, or OAuth client application ID as the user ID. If the server cannot authenticate the end user, require the MCP client to provide `_meta["user.id"]`; if neither source exists, report the integration as incomplete instead of manufacturing an ID.

When available from a verified authenticated profile, promote name and email to top-level span attributes `user.name` and `user.email`. Otherwise promote non-empty client metadata as untrusted analytics values, never as authorization claims. Verified values always win. Do not rely on their presence inside `_meta`: Flowlines' MCP canonicalizer reads `user.id` from MCP metadata as a compatibility path, but user name/email must exist as span attributes to participate in identity mapping.

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
| `user.id` | required by this integration | stable verified user ID, otherwise required non-empty `_meta["user.id"]` promoted to the span |
| `user.name` | required when available | verified display name, otherwise client-supplied analytics value, promoted to the span |
| `user.email` | required when available | verified email, otherwise client-supplied analytics value, promoted to the span |

The call ID identifies an invocation. It may remain stable only when retrying export of that same span. Never derive it solely from `mcp.request.id`; clients may reuse JSON-RPC IDs across stateless requests.

For compatibility during a staged reason rename, an emitter may also set `gen_ai.tool.call.intent` to the same value. New code must always set `gen_ai.tool.call.reason`.

Useful optional client attributes are:

- `mcp.client.name` and `mcp.client.version` from the MCP `initialize` handshake;
- `user_agent.original` and `mcp.protocol.version` from transport headers;
- `flowlines.auth.client_id` from a verified OAuth client identifier.

Keep OAuth client identity separate from the user-facing host name. Propagate incoming W3C trace context when available. Client and server spans carrying the same trace and call ID can be correlated by Flowlines.

## Flowlines user mapping

Flowlines canonicalizes the exact `user.id` span attribute into `flowlines.mcp.user_id`, which associates the MCP call and normalized session with that user. No other user-ID alias is accepted by the MCP adapter, so always emit `user.id` even if the target also uses a vendor-specific field.

Name and email remain standard observed span attributes. Flowlines user identity fields are empty until they are explicitly mapped. When the canonical MCP span carries a real caller agent identity and that agent is configured in Flowlines, configure its users mapping as follows:

```json
{
  "userIdAttribute": "user.id",
  "identityFields": {
    "name": {
      "fieldId": "name",
      "name": "Name",
      "attributeKey": "user.name"
    },
    "email": {
      "fieldId": "email",
      "name": "Email",
      "attributeKey": "user.email"
    },
    "location": null,
    "customFields": []
  }
}
```

Use the equivalent fields in the Flowlines UI when mappings are configured interactively. A standalone server-side MCP span may be agentless; do not set the server name as a caller agent merely to unlock this mapping. When Flowlines exposes namespace-level identifier mapping for that telemetry, use the equivalent mapping:

```json
{
  "ingestion": {
    "identifiers": {
      "sessionId": "session.id",
      "userId": "user.id",
      "custom": {
        "user.name": "user.name",
        "user.email": "user.email"
      }
    }
  }
}
```

The namespace source configuration requires the `ingestion.identifiers` nesting shown above, and `sessionId` must be present for that identifier mapping to be accepted. Do not map `user.name` or `user.email` as the user ID. After saving the applicable mapping, verify that a new test session stores the expected ID and that the user profile displays the mapped name/email. Do not assume existing sessions will be retroactively enriched. If neither a caller-agent users mapping nor a namespace identifier mapping is available, continue emitting the exact attributes but report name/email profile enrichment as unverified or unsupported; do not claim the identity is fully mapped.

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

Set span status to `OK` when the final client-visible MCP result is successful. Set it to `ERROR` for a tool error or protocol failure and record only a bounded, sanitized `error.type`. Do not leave a completed tool span at the OpenTelemetry default `UNSET`: absence of an error status does not mean success, and Flowlines reports an unset call's success as unknown. Determine success from the final MCP result's error marker and any protocol error, not merely from the absence of a caught exception.

Flowlines caps each canonical arguments/result value at 50,000 characters and replaces oversized values with a valid JSON truncation object. Preserve tighter target-server response bounds when they exist.

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

1. Make ten ordinary test calls carrying `reason`, `user_intent`, one stable test `session.id`, and one stable test `user.id`; include `user.name` and `user.email` when available.
2. Make one final `report_outcome` call in the same session.
3. Confirm Flowlines ingestion health shows eleven matched and accepted calls with no persistent pending calls.
4. Confirm tool name, server, explicit successful status rather than unknown status, latency, session intent, captured evidence, and reported outcome.
5. Confirm every call and the session map to the exact test user ID, and confirm the user profile displays the mapped name/email rather than falling back to the raw ID.
6. Treat clustering as eligible only after at least 20 valid-reason calls and three distinct normalized reasons.
7. Tool-loop detection requires three adjacent calls to the same server/tool/reason in one metadata session within ten minutes.
