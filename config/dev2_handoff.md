# LiteLLM Gateway — Dev 2 Handoff
**PBI-03-BE → PBI-08-FE / PBI-09-FE**
**Updated: PBI-04-BE — model names finalised**

Share this document with Dev 2 through a secure channel — it contains a live API key.

---

## Status

- [x] `validate_litellm_routing.py` passed with 0 failures
- [x] `validate_litellm_allowlist.py` passed with 0 failures
- [ ] Restart validation passed (run after Azure Container Apps deployment)
- [ ] Handoff shared with Dev 2

---

## LiteLLM Endpoint

| Field | Value |
|---|---|
| Base URL | `https://litellm-nonprod.<fill-in-after-aca-deploy>.azurecontainerapps.io` |
| API format | OpenAI-compatible (`/chat/completions`, `/models`) |
| Auth header | `Authorization: Bearer sk-nq9PjZi_lKew_CAR2KrXHw` |

> **Note for gateway track:** Fill in the Base URL once LiteLLM is deployed to Azure Container Apps
> (`litellm-nonprod`). All other values are final.

---

## API Key for Dev 2

| Field | Value |
|---|---|
| Virtual key alias | `librechat-phase0` |
| Virtual key value | `sk-nq9PjZi_lKew_CAR2KrXHw` |
| Permitted models | `ROMTech AI Standard`, `ROMTech AI Fast` |
| Expires | Never |

This is a scoped key — it cannot reach any model outside the two listed above,
and it cannot call admin endpoints. Do not share the master key.

---

## Available Models (Final — PBI-04-BE)

These names are final. Use them exactly as written in the `"model"` field.

| Model name | Backed by | Purpose | Default? |
|---|---|---|---|
| `ROMTech AI Standard` | `website-chatbot-gpt-4o-mini` | General use | Yes — set as default in LibreChat |
| `ROMTech AI Fast` | `website-chatbot-gpt-4o-mini` | High-volume, low-complexity | No |

**Recommended default for LibreChat:** `ROMTech AI Standard`
Configure this in the LibreChat endpoint settings (PBI-09-FE) so it is pre-selected for users.

> **Allowlist is enforced.** Requests to any model name not listed above — including raw
> Azure deployment names like `website-chatbot-gpt-4o-mini` or `azure/website-chatbot-gpt-4o-mini`
> — will return a 4xx error. Do not attempt to call any model name other than the two listed.

---

## Quick Integration Test for Dev 2

Before wiring LibreChat, confirm the endpoint is reachable with:

```bash
curl -s https://litellm-nonprod.<fill-in>.azurecontainerapps.io/chat/completions \
  -H "Authorization: Bearer sk-nq9PjZi_lKew_CAR2KrXHw" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ROMTech AI Standard",
    "messages": [{"role": "user", "content": "Say OK"}]
  }'
```

Expected: HTTP 200 with a `choices[0].message.content` field.

---

## Notes

- Streaming is confirmed working (SSE, `stream: true`).
- Requests to models not in the permitted list return a 4xx error — no silent fallback.
- If Dev 2 receives a 401, the virtual key may have expired or been regenerated — contact the gateway track.
- Model names are final. No further naming changes expected before PBI-08-FE / PBI-09-FE.
