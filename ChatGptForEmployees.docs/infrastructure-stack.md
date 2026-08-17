# ChatGPT for Employees — Infrastructure Stack

## Azure AI Foundry (Azure OpenAI)

| Deployment | Model | SKU | Dev | Test | Production |
|---|---|---|---|---|---|
| romtech-standard | gpt-4o | GlobalStandard | 10K TPM | 20K TPM | 50K TPM |
| romtech-fast | gpt-4o-mini | GlobalStandard | 20K TPM | 40K TPM | 100K TPM |
| romtech-embeddings | text-embedding-3-small | GlobalStandard | 20K TPM | 20K TPM | 50K TPM |
| romtech-tts | gpt-4o-mini-tts (2025-12-15) | GlobalStandard | 25K TPM | 25K TPM | 100K TPM |

> **TPM = Tokens Per Minute.** Determines how many concurrent requests the service can handle.
>
> Current capacities are set by the ternaries in `ChatGptForEmployees.bicep/main.bicep`, which is
> authoritative — treat the numbers above as indicative.
>
> `romtech-tts` backs LibreChat's read-aloud button (`speech.tts.azureOpenAI` in
> `config/librechat.yaml`). LibreChat calls it directly, not through the LiteLLM Gateway, so its
> spend does not appear in per-department reporting.

---

## Container Apps — Consumption Plan

| Service | CPU / RAM (Prod) | CPU / RAM (Dev, Test) | Replicas (Prod) | Replicas (Dev, Test) | Scale-out at |
|---|---|---|---|---|---|
| LibreChat (Chat UI) | 1 vCPU / 2 Gi | 0.5 vCPU / 1 Gi | min 2, max 10 | min 1, max 2 | 15 concurrent req/replica |
| LiteLLM (LLM Gateway) | 1 vCPU / 2 Gi | 0.5 vCPU / 1 Gi | min 2, max 10 | min 1, max 2 | 12 concurrent req/replica |
| RAG API | 1 vCPU / 2 Gi | 0.5 vCPU / 1 Gi | min 1, max 5 | min 1, max 2 | 10 concurrent req/replica |

> Set by the `containerSize` / `*Scale` vars in `ChatGptForEmployees.bicep/main.bicep`, which is
> authoritative. cpu:memory must hold ACA's 1:2 vCPU:GiB ratio or the deploy fails, and this is a
> Consumption-**only** environment (no `workloadProfiles`), so the per-app ceiling is 2 vCPU /
> 4 GiB — not the 4/8Gi quoted for the Consumption workload profile.
>
> Min replicas are the always-on floor and are billed continuously; max replicas cost only while
> in use. LibreChat and LiteLLM floor at 2 in prod so a rolling revision swap never leaves a
> single replica serving; RAG API stays at 1 because it is not on every turn. **No environment
> scales to zero** — every service has a min of at least 1, so there are no cold starts anywhere.
> (This doc previously said Dev and Test scale to zero. That was true when written — the compiled
> `main.json` still shows `if(Prod, 1, 0)` — and went stale when `minReplicas` became a flat 1.)
>
> LiteLLM's threshold is held at or below LibreChat's on purpose: every chat turn becomes a
> LiteLLM request, and LiteLLM runs a single uvicorn worker, so it must not scale out later than
> the service feeding it.
>
> Each service declares an explicit HTTP scale rule. Without one, ACA applies an implicit default
> of 10 concurrent requests per replica. Note that this is a scale-out **trigger**, not a cap:
> the old max of 2 replicas did not refuse an 11th request, it just had nowhere to put the load,
> so the prod tier accepted everything and contended for 1 vCPU per service. The old failure mode
> was latency collapse, not refused connections.

---

## Databases & Storage

| Service | Tier / SKU | Dev | Test | Production |
|---|---|---|---|---|
| Cosmos DB for MongoDB | Serverless | ✓ | ✓ | ✓ |
| PostgreSQL Flexible Server | Burstable B1ms (1 vCore, 2 GB) | ✓ | ✓ | ✓ |
| Storage Account | Standard LRS | ✓ | ✓ | ✓ |
| Key Vault | Standard | ✓ | ✓ | ✓ |

---

## Estimated Monthly Infrastructure Cost (AI token usage not included)

| Component | Dev | Test | Production |
|---|---|---|---|
| Container Apps | $15–30 | $15–30 | $150–230 ⚠️ stale |
| PostgreSQL | $13 | $13 | $13 |
| Cosmos DB | $5–15 | $5–15 | $5–15 |
| Storage Account | $2 | $2 | $2 |
| Key Vault | <$1 | <$1 | <$1 |
| **Total** | **~$35–60 / month** | **~$35–60 / month** | **~$170–260 / month** |

> AI token costs (gpt-4o, gpt-4o-mini) are variable and billed per usage — not included above.
>
> ⚠️ The Prod Container Apps figure predates the launch sizing above and has **not** been
> re-estimated. The always-on floor went from 3 replicas × 0.5 vCPU (1.5 vCPU / 3 GiB) to
> 5 replicas × 1 vCPU (5 vCPU / 10 GiB), and burst capacity rose from 6 replicas to 25.
> Idle replicas bill at a lower rate than active ones, so this is not a straight 3.3×, but the
> line needs a real number from the Azure pricing calculator before it is quoted to anyone.
