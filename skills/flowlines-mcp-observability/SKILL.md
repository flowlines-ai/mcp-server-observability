---
name: flowlines-mcp-observability
description: Integrate, repair, review, or verify Flowlines observability in an MCP server repository. Use when a server must emit canonical Flowlines MCP tool-call telemetry through AGNTCY Observe or vanilla OpenTelemetry; do not use for Claude Code or Codex CLI telemetry.
---

# Flowlines MCP Observability

Instrument an MCP server so complete tool executions arrive in Flowlines as canonical MCP calls. Modify the target server; do not add a Flowlines runtime SDK or assume ownership of unrelated telemetry.

## Consent and secrets

Before changing code or deployment configuration:

1. Explain that supported MCP spans export validated tool arguments, final client-visible results, and user identity metadata to Flowlines. Identity metadata includes a stable user ID and, when available, name and email; these fields and payloads may contain personal data, customer data, source code, file content, or other sensitive values.
2. Obtain explicit consent for payload export. Do not infer it from a generic request to "add telemetry."
3. Ask the user to place the Flowlines API key in the target deployment's secret manager. Never request the key in chat, write it into source or examples, interpolate it into a command, or print an existing value.
4. Treat the integration request as permission to edit and test the target repository, not to deploy it, call production tools, or mutate any production database.

Read [references/contract.md](references/contract.md) before implementing or reviewing an integration.

## Inspect the target first

Read the repository instructions, architecture documentation, and testing strategy. Then identify:

- language, runtime, MCP SDK and transport;
- package manager, lockfile, dependency policies, and supported runtime versions;
- the central tool-registration or dispatch boundary;
- existing MCP-level middleware or interceptors;
- existing OpenTelemetry provider, exporter, collector, propagation, and shutdown handling;
- where validated arguments, request ID, request `_meta`, authenticated user ID/profile, final MCP result, and error mapping are available;
- how deployment secrets and environment variables are declared without values.

Preserve the target's package manager and telemetry ownership. Reuse an existing tracer provider and collector when present; never register a competing global provider or replace unrelated exporters.

## Choose the integration path

- For a compatible Python server using the official `mcp` package, prefer AGNTCY Observe. Read [references/python-agntcy.md](references/python-agntcy.md).
- For TypeScript or any other language with an OpenTelemetry SDK, use vanilla OpenTelemetry. Read [references/vanilla-opentelemetry.md](references/vanilla-opentelemetry.md).
- On the vanilla path, prefer the framework's existing MCP-level middleware or interceptor at `tools/call` as the default span boundary. Typical hooks: Go `AddReceivingMiddleware`, FastMCP `on_call_tool`, official Python `server.middleware` filtered to `tools/call`, or the equivalent TypeScript hook. Do not use HTTP, transport, or sending middleware as the Flowlines MCP span boundary; resolve identity from those layers when needed, then emit the span at MCP `tools/call`.
- If automatic instrumentation or that middleware hook cannot observe the final client-visible result, validated arguments, or request metadata, keep a single wrapper around the central tool execution boundary and capture the missing fields there. Do not scatter nearly identical span code across every handler unless the framework provides no shared boundary. Do not emit Flowlines MCP spans for `initialize`, `tools/list`, or other non-`tools/call` methods. Disable overlapping automatic coverage so each call produces one Flowlines MCP span.

If the stack has neither supported AGNTCY instrumentation nor a usable OpenTelemetry SDK, explain the gap instead of inventing an unverified exporter or protocol adapter.

## Implement the contract

Make the smallest coherent change that satisfies all of these invariants:

1. Require non-empty `reason` and `user_intent` strings in every ordinary tool input schema. Do not synthesize either value from prompts or tool arguments. Update server instructions, examples, affected callers, and tests because this is an intentional schema change.
2. Register `report_outcome` exactly as described in the contract and include its unconditional final-call instruction in the server instructions.
3. Start one server span around each complete, validated `tools/call` execution. Give every invocation a fresh tool-call ID that is independent of the JSON-RPC request ID.
4. Record the canonical attributes from `contract.md`, the validated tool-argument object, and only the final MCP result returned to the client.
5. Put a non-empty, stable user identifier on every emitted MCP span as the exact `user.id` attribute. Prefer a verified authenticated subject; otherwise require client `_meta["user.id"]`. Never substitute email, display name, session ID, trace ID, or OAuth client ID. If neither identity source exists, the integration is incomplete: extend the authentication or client metadata contract rather than inventing an identity.
6. When verified profile name/email exists, emit it on the same span as exact `user.name` and `user.email` attributes. Otherwise promote non-empty client metadata as untrusted analytics values and document that provenance. Verified fields always win. Flowlines does not map name or email merely because they remain nested in MCP `_meta`; treat them as PII and never put them in captured tool arguments.
7. Configure and verify the applicable Flowlines identity mapping with user ID attribute `user.id`, name field ID `name` mapped to `user.name`, and email field ID `email` mapped to `user.email`. Use the caller-agent users mapping when a real caller agent is present, or the equivalent namespace identifier mapping for an agentless MCP session. Never label the MCP server as a caller agent. Sending the attributes alone is not sufficient for name/email profile enrichment when identity fields have not been mapped; if neither mapping surface is available, report that limitation explicitly.
8. Prefer client-supplied `_meta["session.id"]`. Never derive a conversation from user identity, trace ID, timing, or a reused protocol request ID.
9. Propagate valid incoming W3C trace context when the transport exposes it. Do not make trace context a prerequisite for a call to be recorded.
10. Mark every completed call explicitly: set span status to `OK` after a successful final MCP result and `ERROR` for a tool or protocol failure. Do not leave a completed call at the OpenTelemetry default `UNSET`, because Flowlines reports that call's success as unknown. On failure, record only a bounded error type; do not record raw exceptions, stack traces, authorization headers, OAuth claims, request `_meta`, environment variables, or secret-bearing diagnostics.
11. Keep telemetry fail-open. Export failure must not change the MCP response, and shutdown flushing must be bounded.
12. Configure OTLP through environment variables or the existing collector. Commit only secret placeholders and variable names.

Do not change sampling for an application-wide provider without explicit approval. A dedicated MCP provider may use always-on sampling because these spans are product facts; with a shared provider, preserve its policy and call out any risk from unsampled remote parents.

## Verify

Add tests at the middleware or wrapper boundary, using the stack's in-memory exporter when available. At minimum cover:

- a successful call with explicit `OK` span status, required attributes, distinct call/request IDs, session identity, stable `user.id`, arguments, and result;
- exact `user.name` and `user.email` span attributes for both the verified-profile path and the client-metadata fallback when those values are available;
- a failed call with explicit `ERROR` span status that exports only the safe client-visible error and a bounded error type;
- absence of `_meta`, authorization material, raw exception messages, and spoofed identity; verified identity must win over all client-supplied user fields;
- `report_outcome` schema and server instructions;
- exporter shutdown or force-flush behavior when the integration owns the provider.

Run the target repository's narrow tests, formatter/linter, type checker, and package-manager checks. Never put a real API key in a test.

Only perform live verification when the user has authorized network export and configured the key outside chat. Make ten harmless calls sharing a test `session.id` and stable test `user.id`, include a test name/email when those fields are supported, then make one final `report_outcome` call. Confirm Flowlines shows eleven accepted calls, reports successful calls as successful rather than unknown, maps all calls to the expected user ID, displays the mapped name/email, and shows the session intent, outcome, captured evidence, client attribution when supplied, and no persistent ingestion-quality issues. Behavioral clustering and tool-loop signals have separate volume and timing thresholds, so do not treat their immediate absence as exporter failure.

## Hand off

Report:

- files and dependencies changed;
- where deployment must set the endpoint, API-key header, and service name;
- the source of `user.id`, availability of name/email, and the exact Flowlines user mappings verified;
- schema or client compatibility changes caused by `reason`, `user_intent`, or `report_outcome`;
- checks run and whether live Flowlines receipt was verified;
- any identity, propagation, sampling, payload, or shutdown limitation that remains.
