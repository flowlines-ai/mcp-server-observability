---
name: flowlines-mcp-observability
description: Integrate, repair, review, or verify Flowlines observability in an MCP server repository. Use when a server must emit canonical Flowlines MCP tool-call telemetry through AGNTCY Observe or vanilla OpenTelemetry; do not use for Claude Code or Codex CLI telemetry.
---

# Flowlines MCP Observability

Instrument an MCP server so complete tool executions arrive in Flowlines as canonical MCP calls. Modify the target server; do not add a Flowlines runtime SDK or assume ownership of unrelated telemetry.

## Consent and secrets

Before changing code or deployment configuration:

1. Explain that supported MCP spans export validated tool arguments and final client-visible results to Flowlines. These payloads may contain customer data, source code, file content, or other sensitive values.
2. Obtain explicit consent for payload export. Do not infer it from a generic request to "add telemetry."
3. Ask the user to place the Flowlines API key in the target deployment's secret manager. Never request the key in chat, write it into source or examples, interpolate it into a command, or print an existing value.
4. Treat the integration request as permission to edit and test the target repository, not to deploy it, call production tools, or mutate any production database.

Read [references/contract.md](references/contract.md) before implementing or reviewing an integration.

## Inspect the target first

Read the repository instructions, architecture documentation, and testing strategy. Then identify:

- language, runtime, MCP SDK and transport;
- package manager, lockfile, dependency policies, and supported runtime versions;
- the central tool-registration or dispatch boundary;
- existing OpenTelemetry provider, exporter, collector, propagation, and shutdown handling;
- where validated arguments, request ID, request `_meta`, authenticated identity, final MCP result, and error mapping are available;
- how deployment secrets and environment variables are declared without values.

Preserve the target's package manager and telemetry ownership. Reuse an existing tracer provider and collector when present; never register a competing global provider or replace unrelated exporters.

## Choose the integration path

- For a compatible Python server using the official `mcp` package, prefer AGNTCY Observe. Read [references/python-agntcy.md](references/python-agntcy.md).
- For TypeScript or any other language with an OpenTelemetry SDK, use vanilla OpenTelemetry. Read [references/vanilla-opentelemetry.md](references/vanilla-opentelemetry.md).
- If automatic instrumentation cannot observe the final client-visible result, validated arguments, or request metadata, add the smallest wrapper around the central tool execution boundary. Do not scatter nearly identical span code across every handler unless the framework provides no shared boundary.

If the stack has neither supported AGNTCY instrumentation nor a usable OpenTelemetry SDK, explain the gap instead of inventing an unverified exporter or protocol adapter.

## Implement the contract

Make the smallest coherent change that satisfies all of these invariants:

1. Require non-empty `reason` and `user_intent` strings in every ordinary tool input schema. Do not synthesize either value from prompts or tool arguments. Update server instructions, examples, affected callers, and tests because this is an intentional schema change.
2. Register `report_outcome` exactly as described in the contract and include its unconditional final-call instruction in the server instructions.
3. Start one server span around each complete, validated `tools/call` execution. Give every invocation a fresh tool-call ID that is independent of the JSON-RPC request ID.
4. Record the canonical attributes from `contract.md`, the validated tool-argument object, and only the final MCP result returned to the client.
5. Prefer client-supplied `_meta["session.id"]`. Never derive a conversation from user identity, trace ID, timing, or a reused protocol request ID. Treat `_meta["user.id"]` as an untrusted analytics dimension unless the server has a verified authenticated identity to use instead.
6. Propagate valid incoming W3C trace context when the transport exposes it. Do not make trace context a prerequisite for a call to be recorded.
7. Mark failure with span status and a bounded error type. Do not record raw exceptions, stack traces, authorization headers, OAuth claims, request `_meta`, environment variables, or secret-bearing diagnostics.
8. Keep telemetry fail-open. Export failure must not change the MCP response, and shutdown flushing must be bounded.
9. Configure OTLP through environment variables or the existing collector. Commit only secret placeholders and variable names.

Do not change sampling for an application-wide provider without explicit approval. A dedicated MCP provider may use always-on sampling because these spans are product facts; with a shared provider, preserve its policy and call out any risk from unsampled remote parents.

## Verify

Add tests at the same boundary as the wrapper, using the stack's in-memory exporter when available. At minimum cover:

- a successful call with required attributes, distinct call/request IDs, session identity, arguments, and result;
- a failed call that exports only the safe client-visible error and a bounded error type;
- absence of `_meta`, authorization material, raw exception messages, and spoofed user identity;
- `report_outcome` schema and server instructions;
- exporter shutdown or force-flush behavior when the integration owns the provider.

Run the target repository's narrow tests, formatter/linter, type checker, and package-manager checks. Never put a real API key in a test.

Only perform live verification when the user has authorized network export and configured the key outside chat. Make ten harmless calls sharing a test `session.id`, then one final `report_outcome` call. Confirm Flowlines shows eleven accepted calls, the session intent and outcome, captured evidence, client attribution when supplied, and no persistent ingestion-quality issues. Behavioral clustering and tool-loop signals have separate volume and timing thresholds, so do not treat their immediate absence as exporter failure.

## Hand off

Report:

- files and dependencies changed;
- where deployment must set the endpoint, API-key header, and service name;
- schema or client compatibility changes caused by `reason`, `user_intent`, or `report_outcome`;
- checks run and whether live Flowlines receipt was verified;
- any identity, propagation, sampling, payload, or shutdown limitation that remains.
