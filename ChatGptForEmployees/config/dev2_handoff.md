# LiteLLM Gateway — Dev 2 Handoff
**PBI-03-BE → PBI-08-FE / PBI-09-FE**
**Updated: 2026-06-05 — local validation complete, all services running**

Share this document with Dev 2 through a secure channel — it contains a live API key.

---

## Status

- [x] `validate_litellm_routing.py` passed with 0 failures
- [x] `validate_litellm_allowlist.py` passed with 0 failures
- [x] `validate_librechat_litellm.py` passed with 0 failures — LibreChat ↔ LiteLLM confirmed
- [x] `validate_rag_api.py` passed 8/8 — RAG API + pgvector confirmed
- [x] `validate_telemetry_callback.py` passed 7/7 — telemetry callback confirmed
- [x] Chat confirmed working end-to-end in browser (localhost:3080)
- [ ] Restart validation passed (run after Azure Container Apps deployment)
- [x] Handoff shared with Dev 2

---

## Services Running on Dev 1's Machine

| Service | Local URL | Notes |
|---|---|---|
| LiteLLM gateway | `http://localhost:4000` | Start: `python scripts/start_litellm.py` |
| RAG API | `http://localhost:8000` | Start: `python main.py` from rag_api dir |
| LibreChat | `http://localhost:3080` | Start: `npm run backend` from LibreChat dir |
| PostgreSQL | `localhost:5432` | Windows service |
| MongoDB | `localhost:27017` | Windows service |

---

## LiteLLM Endpoint

| Field | Value |
|---|---|
| Base URL | `http://localhost:4000/v1` |
| API format | OpenAI-compatible (`/chat/completions`, `/models`) |
| Auth header | `Authorization: Bearer sk-yOFaZks_IO2ozCXdf085yQ` |

---

## API Key for Dev 2

| Field | Value |
|---|---|
| Virtual key alias | `librechat-phase0` |
| Virtual key value | `sk-yOFaZks_IO2ozCXdf085yQ` |
| Permitted models | `ROMTech AI Standard`, `ROMTech AI Fast` |
| Expires | Never |

This is a scoped key — it cannot reach any model outside the two listed above,
and it cannot call admin endpoints. Do not share the master key.

> **Note:** This key is stored in the LiteLLM PostgreSQL database. If LiteLLM is restarted
> with a fresh database, the key must be regenerated via `python scripts/generate_litellm_key.py`
> or the LiteLLM API. Contact the gateway track if you receive a 401.

---

## Available Models

| Model name | Backed by | Purpose | Default? |
|---|---|---|---|
| `ROMTech AI Standard` | `gpt-5.4-mini` (dev-lms-foundry) | General use | Yes |
| `ROMTech AI Fast` | `gpt-5.4-mini` (dev-lms-foundry) | High-volume, low-complexity | No |

**Allowlist is enforced.** Requests to any model name not listed above — including raw
deployment names like `gpt-5.4-mini` or `azure/gpt-5.4-mini` — will return a 4xx error.

---

## LibreChat Configuration (already applied)

`config/librechat.yaml` is configured and loaded. Key settings:

- Endpoint: LiteLLM Gateway at `http://localhost:4000/v1`
- Models: fetched from LiteLLM, default is `ROMTech AI Standard`
- RAG API: `http://localhost:8000` (file upload wired up)
- Feature governance: endpoints menu hidden, agents/skills/memories disabled

---

## Quick Integration Test for Dev 2

```bash
curl -s http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-yOFaZks_IO2ozCXdf085yQ" \
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
- RAG API is running and reachable at `http://localhost:8000` — see `config/rag_api_dev2_handoff.md` for RAG acceptance tests.
- LibreChat startup shows 401 errors for OpenAI model polling — this is expected noise (LibreChat polls built-in endpoints in background). Chat works correctly.
- Requests to models not in the permitted list return a 4xx error — no silent fallback.
- Model names are final. No further naming changes expected.
