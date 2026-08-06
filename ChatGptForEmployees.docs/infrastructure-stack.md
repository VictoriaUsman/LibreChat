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

| Service | CPU | RAM | Min Replicas | Max Replicas | Dev | Test | Production |
|---|---|---|---|---|---|---|---|
| LibreChat (Chat UI) | 0.5 vCPU | 1 Gi | — | 2 | 0 | 0 | 1 |
| LiteLLM (LLM Gateway) | 0.5 vCPU | 1 Gi | — | 2 | 1 | 1 | 1 |
| RAG API | 0.5 vCPU | 1 Gi | — | 2 | 0 | 0 | 1 |

> Min Replicas in Production are set to 1 to eliminate cold starts. Dev and Test scale to zero when idle.

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
| Container Apps | $15–30 | $15–30 | $150–230 |
| PostgreSQL | $13 | $13 | $13 |
| Cosmos DB | $5–15 | $5–15 | $5–15 |
| Storage Account | $2 | $2 | $2 |
| Key Vault | <$1 | <$1 | <$1 |
| **Total** | **~$35–60 / month** | **~$35–60 / month** | **~$170–260 / month** |

> AI token costs (gpt-4o, gpt-4o-mini) are variable and billed per usage — not included above.
