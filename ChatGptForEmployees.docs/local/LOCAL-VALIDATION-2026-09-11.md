# Local validation — 2026-09-11

Scope: current uncommitted cutover implementation after `89c57d0`. No dev database connection or Azure deployment was performed.

## Results

| Check | Result | Limits |
|---|---|---|
| Compile `main.bicep` | Passed with Bicep CLI 0.47.16 (`3f73e1a234`), no diagnostics | Does not validate acceptance by the Azure resource provider |
| Compile `main.dev.bicepparam` | Passed with the same compiler, no diagnostics | Does not resolve live secrets or deploy resources |
| Inspect compiled maintenance wiring | Passed: `maintenanceState` is passed to LiteLLM, jobs, and LibreChat; allowed states are `off`, `paused`, `litellm-only`, `validation` | Not a runtime access-control or scheduling test |
| Run actual `05-synthetic-litellm-check.py` | Six cases passed; see below | Mock HTTP service plus real isolated PostgreSQL 16, not a LiteLLM/Azure end-to-end rehearsal |
| `git diff --check` | Passed | Git reports expected LF/CRLF conversion notices |

Compiler commands, run from the workspace root using a downloaded official standalone compiler:

```powershell
& './migration-review/validation-tools/bicep.exe' build 'ChatGptForEmployees/ChatGptForEmployees.bicep/main.bicep' --outfile 'migration-review/validation-tools/main.json'
& './migration-review/validation-tools/bicep.exe' build-params 'ChatGptForEmployees/ChatGptForEmployees.bicep/main.dev.bicepparam' --outfile 'migration-review/validation-tools/main.dev.parameters.json'
```

The local harness executes the repository's synthetic script unchanged as a subprocess. A local HTTP fixture returns controlled responses and inserts uniquely identified synthetic rows into disposable PostgreSQL. It does not test LiteLLM's actual request logging implementation.

| Fixture case | Expected exit | Actual exit |
|---|---|---|
| Healthy, successful completion, empty content fields | 0 | 0 |
| Completion rejected with HTTP 401 | 2 | 2 |
| Completion rejected with HTTP 400 | 2 | 2 |
| Successful completion but no matching log row | 3 | 3 |
| Synthetic log row contains response content | 4 | 4 |
| Database connection fails | 5 | 5 |

Local harness and result evidence are at workspace-relative `migration-review/validation-tools/check_synthetic.py` and `synthetic-results.json`. These are local scratch artifacts, not committed runtime dependencies. The disposable container `romchat-validation-pg-0911` was removed after testing.

## Pending Azure rehearsal

Azure CLI was not installed and no local Azure profile was found. An isolated rehearsal subscription/resource group and permission to create temporary resources have been requested from the user; no target has been confirmed yet.

Before cutover, verify in that confirmed environment:

- Resource-provider acceptance and actual enforcement of zero-replica maintenance and the job pause mechanism.
- Tester-only access from an allowed source, denied access from another source, and continued job suspension during validation.
- Updated jobs-image build and immutable digest on both the deployed job and its exact started execution.
- Actual job-start response, exact execution polling, terminal success, and execution-scoped PASS logs.
- Full enter, controlled-startup, restricted-validation, and release transitions, including failure paths and restoration of settings.

Do not equate successful Bicep compilation or the six local script cases with a completed Azure rehearsal. Step 1 is locally validated but remains incomplete until the Azure checks above pass.
