# Python integration with AGNTCY Observe

Use this path for a Python 3.10+ server built on a compatible official `mcp` package. AGNTCY Observe supplies verified MCP auto-instrumentation and exports spans Flowlines recognizes directly.

## Inspect compatibility

Before adding anything, inspect `pyproject.toml`, lockfiles, requirements files, the Python support range, the MCP version, and existing OpenTelemetry setup.

The verified compatibility floor is:

```text
ioa-observe-sdk >= 1.0.44, < 2
mcp >= 1.6
```

Select and lock an exact compatible release when the target's dependency policy requires it. Do not downgrade a newer working version or replace the target's package manager. If the project already owns a global tracer provider, confirm how Observe composes with it before initialization; fall back to the vanilla path rather than registering two global providers.

## Configure without secrets in source

Declare these variables in deployment documentation or a secret-backed environment template:

```sh
OTEL_EXPORTER_OTLP_ENDPOINT=https://api.flowlines.ai
OTEL_EXPORTER_OTLP_HEADERS=x-flowlines-api-key=<deployment-secret>
OBSERVE_HEADERS=<same-secret-backed-header-value>
OBSERVE_METRICS_ENABLED=false
OTEL_SERVICE_NAME=<stable-mcp-service-name>
```

AGNTCY Observe reads exporter headers from `OBSERVE_HEADERS`; mirror the standard OTLP header value at deployment time. Do not commit either value. If the exporter requires a signal-specific URL, set `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://api.flowlines.ai/v1/traces`.

## Initialize before MCP objects

Run initialization during application startup before creating the MCP client or server:

```python
import os

from ioa_observe.sdk import Observe
from ioa_observe.sdk.instrumentations.mcp import McpInstrumentor


def configure_mcp_observability() -> None:
    Observe.init(
        app_name=os.environ.get("OTEL_SERVICE_NAME", "mcp-server"),
        api_endpoint=os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"],
        telemetry_enabled=False,
    )
    McpInstrumentor().instrument()
```

Call `configure_mcp_observability()` exactly once before constructing the server or registering transports. Preserve any target-specific application factory and import-order conventions.

The integration must also:

- add required `reason` and `user_intent` fields to every tool schema;
- preserve `_meta["session.id"]` as request metadata;
- resolve a stable user ID for every call, preferring the verified authenticated subject and otherwise requiring `_meta["user.id"]`;
- set exact `user.id`, plus `user.name` and `user.email` when verified or client-supplied values exist, on the emitted MCP span; verified profile values win;
- register `report_outcome` with the required final-call description and server instruction;
- set explicit `OK` status for a successful final MCP result and `ERROR` for a tool or protocol failure; do not accept a completed span left at `UNSET`;
- map failures to a safe client-visible MCP error without exporting backend exception content;
- uninstrument or flush during the application's bounded shutdown lifecycle when the SDK exposes that operation.

## Verify the emitted contract

Do not assume that a successful import proves the installed MCP version produces the needed attributes. In particular, do not assume AGNTCY promotes user name/email from MCP `_meta`. Use the target server's central execution/authentication boundary to set `user.id`, `user.name`, and `user.email` on the actual AGNTCY MCP span. If the instrumentor does not expose an active span or a required field at that boundary, fall back to the vanilla wrapper at MCP-level `tools/call` middleware or the shared dispatcher, prefer middleware when the framework has it, and disable overlapping Flowlines MCP coverage so the call is not duplicated.

Add or adapt tests to exercise one complete tool call and inspect exported spans. Confirm Flowlines-recognized AGNTCY attributes identify:

- operation `execute_tool` and the tool name;
- reason and user intent;
- server identity;
- unique invocation and request correlation;
- explicit session identity and a non-empty stable `user.id`;
- exact `user.name` and `user.email` when verified profile or client analytics values are available;
- explicit `OK` or `ERROR` span status, with no completed call left at `UNSET`;
- validated arguments and final client-visible result.

Also verify that request metadata, authorization values, and raw exceptions are absent, and that a verified profile overrides spoofed client user fields. Configure the Flowlines user mapping exactly as described in [contract.md](contract.md). If automatic instrumentation cannot expose a required field or set explicit completed-call status at the server's actual framework boundary, keep Observe for export only if it composes cleanly and add the smallest vanilla OpenTelemetry wrapper at MCP-level `tools/call` middleware or the shared dispatcher described in [vanilla-opentelemetry.md](vanilla-opentelemetry.md). Prefer middleware when the framework has it. Avoid duplicate spans: disable overlapping automatic coverage or make only one layer emit the Flowlines MCP span.

For a smoke check, importing, instrumenting, and uninstrumenting the installed `mcp` package must complete without error. Full acceptance still requires inspecting a real finished span and, when authorized, confirming receipt in Flowlines.
