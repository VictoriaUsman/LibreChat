# AIUsageLog Table Schema
**PBI-XX-BE | Central DB data contract**

This document defines the schema for the `ai_usage_log` table that the
Azure Function (PBI-12-BE) will write to. The LiteLLM telemetry callback
(`callbacks/litellm_usage_callback.py`) produces payloads that map to the
columns marked **From callback**.

The schema is final for the deployment sprint. Any changes to the callback
payload fields require a corresponding migration.

---

## Payload Shape (from LiteLLM callback)

Each successful LiteLLM request emits one JSON line to stdout and,
when `TELEMETRY_ENDPOINT_URL` is set, POSTs this body to the Azure Function:

```json
{
  "department":          "engineering",
  "model":               "ROMTech AI Standard",
  "input_tokens":        42,
  "output_tokens":       15,
  "estimated_cost_usd":  0.00000855,
  "timestamp":           "2026-06-04T10:30:00.000Z"
}
```

No message content is included. The `timestamp` is the UTC datetime when
the LiteLLM request completed (from `end_time` in the callback).

---

## Table Definition

```sql
CREATE TABLE ai_usage_log (
    -- Auto-generated surrogate key
    id                  BIGSERIAL       PRIMARY KEY,

    -- Server-side timestamp: when the Azure Function received the payload.
    -- Used for deduplication queries and to detect delivery delays.
    received_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- ---------- From callback payload ----------

    -- Department or cost centre, derived from the virtual key's team_id tag.
    -- 'unknown' when the request used an unscoped key (e.g. librechat-phase0).
    department          VARCHAR(100)    NOT NULL,

    -- User-facing model alias (e.g. 'ROMTech AI Standard').
    -- Matches the model_name in litellm_routing_config.yaml -- NOT the raw
    -- Azure deployment name.
    model               VARCHAR(100)    NOT NULL,

    -- Prompt (input) token count as reported by the Azure OpenAI response.
    input_tokens        INTEGER         NOT NULL CHECK (input_tokens >= 0),

    -- Completion (output) token count as reported by the Azure OpenAI response.
    output_tokens       INTEGER         NOT NULL CHECK (output_tokens >= 0),

    -- Estimated USD cost calculated by LiteLLM using the per-token rates
    -- configured in litellm_routing_config.yaml.
    -- Precision: 8 decimal places (sufficient for sub-cent amounts at GPT-4o-mini rates).
    estimated_cost_usd  NUMERIC(14, 8)  NOT NULL CHECK (estimated_cost_usd >= 0),

    -- UTC timestamp from the callback (when the LiteLLM request completed).
    -- ISO 8601 format: YYYY-MM-DDTHH:MM:SS.mmmZ
    event_timestamp     TIMESTAMPTZ     NOT NULL,

    -- ---------- Added by the Azure Function ----------

    -- Identifies which LiteLLM instance sent this event.
    -- Values: 'litellm-local', 'litellm-nonprod', 'litellm-prod'
    -- Allows filtering local test traffic from production data.
    source_instance     VARCHAR(50)     NOT NULL DEFAULT 'litellm-local'
);
```

---

## Column Reference

| Column | Type | Source | Required | Notes |
|---|---|---|:---:|---|
| `id` | `BIGSERIAL` | DB auto | Yes | Surrogate key |
| `received_at` | `TIMESTAMPTZ` | DB auto | Yes | Azure Function arrival time |
| `department` | `VARCHAR(100)` | Callback | Yes | Virtual key `team_id`; `'unknown'` if unset |
| `model` | `VARCHAR(100)` | Callback | Yes | User-facing alias, not Azure deployment name |
| `input_tokens` | `INTEGER` | Callback | Yes | Prompt token count; >= 0 |
| `output_tokens` | `INTEGER` | Callback | Yes | Completion token count; >= 0 |
| `estimated_cost_usd` | `NUMERIC(14,8)` | Callback | Yes | LiteLLM-calculated cost estimate |
| `event_timestamp` | `TIMESTAMPTZ` | Callback | Yes | UTC datetime from callback `end_time` |
| `source_instance` | `VARCHAR(50)` | Azure Function | Yes | Identifies environment; default `'litellm-local'` |

---

## Recommended Indexes

```sql
-- Fast monthly rollups by department
CREATE INDEX idx_ai_usage_log_dept_ts
    ON ai_usage_log (department, event_timestamp);

-- Fast model-level cost queries
CREATE INDEX idx_ai_usage_log_model_ts
    ON ai_usage_log (model, event_timestamp);

-- Deduplication / audit queries by arrival time
CREATE INDEX idx_ai_usage_log_received_at
    ON ai_usage_log (received_at);
```

---

## Example Queries

**Monthly cost by department:**
```sql
SELECT
    department,
    DATE_TRUNC('month', event_timestamp) AS month,
    SUM(input_tokens)          AS total_input_tokens,
    SUM(output_tokens)         AS total_output_tokens,
    SUM(estimated_cost_usd)    AS total_cost_usd
FROM ai_usage_log
WHERE source_instance != 'litellm-local'   -- exclude dev traffic
GROUP BY department, month
ORDER BY month DESC, total_cost_usd DESC;
```

**Daily request count by model:**
```sql
SELECT
    model,
    DATE_TRUNC('day', event_timestamp) AS day,
    COUNT(*)                           AS requests,
    SUM(estimated_cost_usd)            AS cost_usd
FROM ai_usage_log
GROUP BY model, day
ORDER BY day DESC;
```

---

## Notes

- **No PII or message content** is stored. The callback explicitly omits the
  `messages` array and completion text from its payload, per Section 1.5 of
  `Phase_0_Findings_v1_Recommendation.md`.
- The `estimated_cost_usd` values are estimates based on the per-token rates
  in `litellm_routing_config.yaml`. Replace with ROMTech Azure agreement rates
  when confirmed with the billing admin.
- The `source_instance` value must be set by the Azure Function based on the
  request origin header or a config variable, not by the callback itself.
- Retry deduplication (if the Azure Function is invoked more than once for the
  same event) should be handled by the Azure Function using `received_at` and
  a short deduplication window.
- Migration from local SQLite / in-memory tracking to this table is a
  deployment sprint item (PBI-12-BE).
