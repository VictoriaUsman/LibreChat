# LiteLLM Usage Tracking and Cost Visibility — Phase 0 Assessment
**PBI-05-BE | Section 4G of Phase 0 Plan**
**Status: Pending — awaiting live LiteLLM instance (depends on PBI-03-BE)**

Run `scripts/validate_litellm_usage.py` against the deployed LiteLLM container, then
fill in every **TBD** field below and tick the relevant checkboxes.

---

## Validation Script Result

- [ ] All tests passed (`scripts/validate_litellm_usage.py` — 0 failures)
- [ ] Tests failed — see findings below
- [ ] Not yet run — LiteLLM instance not yet available

**Script output summary:**
> TBD — paste the script's pass/fail/finding summary here after running it.

---

## 1. Token Usage Visibility

**What LiteLLM provides out of the box:**
Every completed request is logged with `prompt_tokens`, `completion_tokens`, and
`total_tokens`. These always appear in container stdout regardless of database config.
When a PostgreSQL database is configured, they are also queryable via `/spend/logs`.

**Phase 0 finding:**
> TBD — Did token counts appear in `/spend/logs`? If not, were they visible in container stdout logs?

**Assessment:**
- [ ] Available out of the box — no additional config needed
- [ ] Available but requires PostgreSQL database configuration
- [ ] Not available — requires additional work

---

## 2. Usage Breakdown by Model

**What LiteLLM provides out of the box:**
`/spend/models` returns cumulative spend and token counts grouped by model name.
Requires PostgreSQL to persist across restarts.

**Phase 0 finding:**
> TBD — Did `/spend/models` return per-model data? What fields were present?

**Assessment:**
- [ ] Available out of the box — no additional config needed
- [ ] Available but requires PostgreSQL database configuration
- [ ] Not available — requires additional work

---

## 3. Usage Attribution by User

**What LiteLLM provides out of the box:**
Callers can pass a `"user"` field in the request body (standard OpenAI parameter).
LiteLLM records this in the spend log. Queryable via `/spend/logs?user=<value>`.
LibreChat passes the authenticated user's ID automatically if configured correctly.

**Configuration needed for v1:**
Set `general_settings.allow_user_requests: true` in `litellm_routing_config.yaml`.
LibreChat must be configured to forward the Okta user identity as the `user` field —
confirm during PBI-08-FE / PBI-09-FE.

**Phase 0 finding:**
> TBD — Were user-attributed requests visible in `/spend/logs`? Did the `user` field index correctly?

**Assessment:**
- [ ] Available out of the box
- [ ] Available — requires LibreChat to forward user identity (PBI-08-FE / PBI-09-FE)
- [ ] Not available — requires additional work

---

## 4. Usage Attribution by Virtual Key / Team / Department

**What LiteLLM provides out of the box:**
Virtual keys are issued per integration (e.g. one key per team or department).
`/spend/keys` returns cumulative spend per key. Keys can be tagged with metadata
(team name, department) at creation time for grouping.

**For v1:** Issue one virtual key per department or cost centre. Tag each key with
`team_id` and `metadata` at generation time. This gives monthly cost breakdowns
without any custom instrumentation.

**Phase 0 finding:**
> TBD — Did `/spend/keys` return per-key data? Were metadata tags queryable?

**Assessment:**
- [ ] Available out of the box
- [ ] Available — requires structured key-naming convention and tag discipline at issuance
- [ ] Not available — requires additional work

---

## 5. Cost Estimation and Tracking

**What LiteLLM provides out of the box:**
LiteLLM calculates estimated cost per request using a built-in pricing table
(sourced from the `litellm` Python package's model cost data). The `spend` field
in log entries contains the estimated USD cost. Cumulative spend is aggregated by
model, key, user, and team via the `/spend/*` endpoints.

**Caveats:**
- Pricing data is bundled with the LiteLLM version — it may lag new Azure OpenAI pricing changes.
- Azure OpenAI pricing may differ from OpenAI.com pricing. LiteLLM uses OpenAI public pricing
  as a proxy unless overridden.
- To set custom prices: add `input_cost_per_token` and `output_cost_per_token` to each model
  entry in `litellm_routing_config.yaml`.

**Phase 0 finding:**
> TBD — Was the `spend` field populated in log entries? Did estimated costs look reasonable
> for the model and token counts used?

**Assessment:**
- [ ] Cost estimation available out of the box — acceptable accuracy
- [ ] Cost estimation available but prices need overriding to match Azure agreement
- [ ] Cost estimation not available or unreliable — requires additional work

---

## 6. Operational Dashboard

**What LiteLLM provides out of the box:**
LiteLLM ships with a built-in admin UI accessible at `<LITELLM_URL>/ui`.
The dashboard shows: active keys, request logs, spend by model / key / user,
budget status, and rate limit settings.

**Requires:** PostgreSQL (`DATABASE_URL`). Without it, the UI may be accessible
but shows no historical data.

**Phase 0 finding:**
> TBD — Was `/ui` accessible? What data was visible? Was historical spend queryable?

**V1 recommendation:**
- [ ] Built-in dashboard is sufficient for v1 operations
- [ ] Built-in dashboard needs supplementing with Azure Monitor / custom queries
- [ ] Built-in dashboard is not sufficient — custom observability required

---

## 7. Capability Summary

Fill in after completing sections 1–6.

| Capability | Available Now | Needs Config | Needs Build | Notes |
|---|:---:|:---:|:---:|---|
| Token usage per request | | | | |
| Usage by model | | | | |
| Usage by virtual key | | | | |
| Usage by user (Okta identity) | | | | |
| Usage by team / department | | | | |
| Cost estimation per request | | | | |
| Cumulative cost by model | | | | |
| Cumulative cost by department | | | | |
| Persistent spend history (survives restart) | | | | |
| Operational dashboard | | | | |
| Alerting on cost anomalies | | | | |
| Export to Azure Monitor / Log Analytics | | | | |

---

## 8. Recommendation

Choose one after completing the table above.

- [ ] **LiteLLM's built-in tracking is sufficient for v1** — configure PostgreSQL and
  structured virtual key naming; no additional instrumentation needed.

- [ ] **LiteLLM covers the basics but v1 needs supplemental observability** — describe
  what is missing and the proposed approach (e.g. forwarding LiteLLM audit logs to
  Azure Monitor, building a cost dashboard query).

- [ ] **LiteLLM's usage tracking is not sufficient for v1 requirements** — describe
  what is missing and what alternative or additional tooling is recommended.

**Notes:**
> TBD

---

## 9. Key v1 Configuration Steps (if recommendation is to proceed)

1. Provision Azure Database for PostgreSQL (Flexible Server, BAA-eligible region).
2. Add `DATABASE_URL` to the LiteLLM container environment.
3. Generate one virtual key per department/team, tagged with metadata.
4. Override Azure OpenAI token prices in `litellm_routing_config.yaml` if the bundled
   prices do not match the ROMTech Azure agreement.
5. Confirm LibreChat forwards Okta user identity as the `user` field (PBI-08-FE).
6. Set up a monthly cost report query or Azure Monitor alert on the spend data.
