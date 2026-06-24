# ChatGPT for Employees — Infrastructure Stack

## Current Dev Stack

### Azure AI Foundry (Azure OpenAI)

| Deployment | Model | SKU | Capacity |
|---|---|---|---|
| romtech-standard | gpt-4o | GlobalStandard | 30K TPM |
| romtech-fast | gpt-4o-mini | GlobalStandard | 100K TPM |
| romtech-embeddings | text-embedding-3-small | GlobalStandard | 120K TPM |

> **TPM = Tokens Per Minute.** Determines how many concurrent requests the service can handle.

---

### Container Apps (cae-cgfe-dev) — Consumption Plan

| Service | CPU | RAM | Min Replicas | Max Replicas |
|---|---|---|---|---|
| LibreChat (Chat UI) | 0.5 vCPU | 1 Gi | 0 | 2 |
| LiteLLM (LLM Gateway) | 0.5 vCPU | 1 Gi | 1 | 2 |
| RAG API | 0.5 vCPU | 1 Gi | 0 | 2 |

---

### Databases & Storage

| Service | Tier / SKU | Capacity |
|---|---|---|
| Cosmos DB for MongoDB | Serverless | No provisioned throughput — pay per request |
| PostgreSQL Flexible Server | Burstable B1ms | 1 vCore, 2 GB RAM, 32 GB storage |
| Storage Account | Standard LRS | No geo-redundancy |
| Key Vault | Standard | Software-protected keys |

---
---

## Recommended Production Stack

### Azure AI Foundry (Azure OpenAI)

| Deployment | Model | SKU | Recommended Capacity | Reason |
|---|---|---|---|---|
| romtech-standard | gpt-4o | GlobalStandard | 150K TPM | 5× dev — real concurrent users |
| romtech-fast | gpt-4o-mini | GlobalStandard | 400K TPM | Expected high request volume |
| romtech-embeddings | text-embedding-3-small | GlobalStandard | 350K TPM | Document processing at scale |

---

### Container Apps — Consumption Plan

| Service | CPU | RAM | Min Replicas | Max Replicas | Change Rationale |
|---|---|---|---|---|---|
| LibreChat (Chat UI) | 1 vCPU | 2 Gi | 1 | 5 | No cold start; handles more concurrent users |
| LiteLLM (LLM Gateway) | 1 vCPU | 2 Gi | 1 | 3 | Stable routing under load |
| RAG API | 1 vCPU | 2 Gi | 1 | 3 | Document embedding is CPU-intensive |

---

### Databases & Storage

| Service | Dev | Production | Reason |
|---|---|---|---|
| Cosmos DB for MongoDB | Serverless | Provisioned — 1,000 RU/s | Predictable latency in production |
| PostgreSQL Flexible Server | Burstable B1ms | General Purpose D2s_v3 (2 vCores, 8 GB RAM) | pgvector requires real memory; Burstable is not suited for sustained load |
| Storage Account | Standard LRS | Standard ZRS | Zone redundancy for critical config file share |
| Key Vault | Standard | Standard | No change needed |

---

### Estimated Monthly Infrastructure Cost (AI token usage not included)

| Component | Dev | Production (estimated) |
|---|---|---|
| Container Apps | $15–30 | $150–230 |
| PostgreSQL | $13 | $95 |
| Cosmos DB | $5–15 | $25 |
| Storage Account | $2 | $5 |
| Key Vault | <$1 | <$1 |
| **Total** | **~$35–60 / month** | **~$275–360 / month** |

> AI token costs (gpt-4o, gpt-4o-mini) are variable and billed per usage — not included above. These will be the dominant cost in production with active users.
