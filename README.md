# Flowlines MCP server observability

Add Flowlines observability to an existing MCP server with a reusable coding-agent skill.

The skill inspects the target server, preserves its framework and telemetry setup, and implements the Flowlines MCP contract using AGNTCY Observe for compatible Python servers or vanilla OpenTelemetry for other stacks. On the vanilla path it prefers the framework's existing MCP-level `tools/call` middleware or interceptor rather than wrapping every handler. It does not ship a Flowlines runtime SDK or a one-size-fits-all codemod.

## Privacy notice

This integration exports validated MCP tool arguments, final client-visible tool results, and user identity metadata to Flowlines. Identity metadata includes a stable user ID and, when available, the user's name and email. Those fields and payloads may contain personal data, customer data, source code, file contents, queries, or other sensitive information.

Only integrate it after you understand the payload boundary, have permission to export that data, and have configured appropriate retention and access controls. The skill requires explicit consent before changing a target server.

## What it adds

- required per-call `reason` and session-level `user_intent` tool inputs;
- canonical GenAI/MCP OpenTelemetry spans for complete tool executions;
- explicit session identity and mandatory stable `user.id` on every span;
- exact `user.name` and `user.email` attributes when verified or client-supplied values are available, with Flowlines mapping verification;
- captured validated arguments and safe client-visible results;
- a final `report_outcome` tool for session self-reporting;
- local span-contract tests and an end-to-end Flowlines verification checklist.

The Flowlines API key stays in the target deployment's secret manager. It must never be committed, pasted into an assistant conversation, or printed by diagnostics.

## Use the skill

Install the skill from this repository with your assistant's skill installer, selecting:

```text
skills/flowlines-mcp-observability
```

Compatible assistants can also use [`SKILL.md`](skills/flowlines-mcp-observability/SKILL.md) directly. Invoke it from the root of the MCP server repository, for example:

```text
Use $flowlines-mcp-observability to integrate Flowlines observability into this MCP server. Preserve its package manager and existing OpenTelemetry setup, add in-memory span tests, and do not perform a live export until I authorize it.
```

The skill supports implementation, repair, review, and verification. It reads the server's own repository instructions before making changes.

## Runtime configuration

The target deployment supplies standard OTLP configuration through secrets:

```text
OTEL_EXPORTER_OTLP_ENDPOINT=https://api.flowlines.ai
OTEL_EXPORTER_OTLP_HEADERS=x-flowlines-api-key=<deployment-secret>
OTEL_SERVICE_NAME=<stable-mcp-service-name>
```

Export may go through an existing OpenTelemetry Collector. The application still emits the Flowlines MCP span attributes described by the skill.

## Development

Validate the repository skill structure:

```sh
python3 scripts/validate_skill.py
```

When the Codex skill-creator utilities are available, also run their `quick_validate.py` against `skills/flowlines-mcp-observability`.

## License

MIT
