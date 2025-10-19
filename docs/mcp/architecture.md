MCP Fabric Architecture (Local, Read-Only v1)

- Control vs. Fabric: In this phase, we implement the Fabric locally only.
- No HTTP/gRPC, no workers. Pure importable modules and CLIs.
- Deterministic adapter stubs that only describe/plan, never execute.
- Strict policy/security modules with fail-safe defaults and no side effects.

Usage from REPL (no server):

```
>>> from backend.mcp.server import registry, policy, security, app
>>> registry.list_tools()
[{"id": "ops.health_check", "version": "1.0.0"}, ...]
>>> security.parse_bearer("Bearer tenant:ACME|role:ops")
ParsedToken(tenant='ACME', role='ops')
>>> policy.load_policy()
Policy(dry_run_default=True, allowed_tools=['ops.health_check'], quotas={})
>>> adapter_cls = app.get_adapter_factory('ops.health_check'); adapter_cls.plan(version='1.0.0')
{'status': 'ok', 'version': '1.0.0', 'ts': '2025-01-01T00:00:00Z'}
```
