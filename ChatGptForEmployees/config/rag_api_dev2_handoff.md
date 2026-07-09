# LibreChat RAG API -- Dev 2 Handoff
**PBI-XX-BE -> PBI-19-FE**

Share this document with Dev 2 via a secure channel.

---

## Status

- [x] pgvector extension enabled on `librechat_rag` database (`setup_pgvector.py` passed)
- [x] LibreChat RAG API installed and starts cleanly locally
- [x] RAG API configured with Azure OpenAI embedding model (PBI-18-BE credentials)
- [x] RAG API connects to pgvector database without errors
- [x] `RAG_API_URL` set in `scripts/.env`
- [x] Test document upload returned success and embeddings visible in pgvector
- [x] LibreChat starts cleanly with `RAG_API_URL` configured
- [x] No regression in LiteLLM routing or streaming
- [ ] Handoff shared with Dev 2

---

## RAG API Endpoint

| Field | Value |
|---|---|
| Base URL | `http://localhost:8000` |
| Health check | `GET /health` -> `{"status": "ok"}` |
| Upload endpoint | `POST /api/v1/add` (multipart form) |
| Query endpoint | `POST /api/v1/query` |
| Delete endpoint | `POST /api/v1/delete` |

LibreChat calls these endpoints automatically when a user uploads a file in the chat interface. Dev 2 does not need to call them directly.

---

## Starting the RAG API

The RAG API is a separate Python/FastAPI process. It must be running whenever LibreChat is running.

```
# From the rag_api directory (cloned from https://github.com/danny-avila/rag_api)
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Confirm it is alive:
```
curl http://localhost:8000/health
# Expected: {"status": "ok"}
```

---

## LibreChat Configuration Required (PBI-19-FE)

### 1. RAG_API_URL in environment

`RAG_API_URL=http://localhost:8000` is already set in `scripts/.env`.

When LibreChat starts, it reads this variable and routes all file upload/retrieval
requests to the RAG API automatically. No changes to LibreChat source code are required.

### 2. File upload is already enabled

`config/librechat.yaml` already has `fileConfig` configured for the `custom` endpoint:

```yaml
fileConfig:
  endpoints:
    custom:
      disabled: false
      fileLimit: 5
      fileSizeLimit: 10        # MB per file
      totalSizeLimit: 50       # MB per conversation
      supportedMimeTypes:
        - "text/plain"
        - "text/csv"
        - "text/markdown"
        - "application/pdf"
        - "image/jpeg"
        - "image/png"
        - "image/gif"
        - "image/webp"
        - "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        - "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        - "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        - "application/msword"
```

No changes to `librechat.yaml` are needed to enable file upload in the UI.

### 3. Acceptance test for PBI-19-FE

1. Start the RAG API: `uvicorn main:app --port 8000` (from rag_api directory)
2. Start LibreChat with `RAG_API_URL=http://localhost:8000` in the environment
3. Open LibreChat in the browser
4. Open a new conversation with the LiteLLM Gateway endpoint
5. Use the paperclip/attachment button to upload a `.txt` or `.pdf` file
6. Send a message asking about the content of the file
7. **PASS**: Model references content from the uploaded document in its reply
8. **PASS**: Attachment button is visible and functional
9. **PASS**: Unsupported MIME types (e.g. `.exe`) are rejected with an error in the UI

---

## RAG Pipeline Flow

```
User uploads file in LibreChat UI
  |
  v
LibreChat (Node.js, port 3080)
  POST /api/v1/add -> RAG API (FastAPI, port 8000)
    |
    +--> Chunks document (CHUNK_SIZE=1500, CHUNK_OVERLAP=100)
    +--> Calls Azure OpenAI embeddings deployment (from PBI-18-BE)
    +--> Stores vectors in langchain_pg_embedding (librechat_rag database)
  |
User sends a message in the conversation
  |
  v
LibreChat queries RAG API for relevant chunks
  POST /api/v1/query -> RAG API
    |
    +--> Embeds the query via Azure OpenAI
    +--> Vector similarity search in langchain_pg_embedding
    +--> Returns top-N relevant chunks to LibreChat
  |
LibreChat injects chunks into the system prompt context
  |
  v
LibreChat -> LiteLLM -> Azure OpenAI
  |
Streaming response to user
```

---

## Known Constraints

- The RAG API must be running before LibreChat starts. LibreChat does not retry
  on startup if the RAG API is unreachable -- it will log a warning and continue
  without RAG, but file uploads will fail at runtime.
- The embedding deployment name must exist in Azure AI Foundry. Confirm with the
  PBI-18-BE owner before setting RAG_AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT.
- Deleting a conversation in LibreChat does not delete its embeddings from pgvector.
  This is a v1 cleanup task.
- `RAG_API_JWT_SECRET` in the rag_api `.env` should match `JWT_SECRET` in
  LibreChat's environment if request signing is enabled.

---

## Quick Reference -- All Local Services

| Component  | Local address         | Start command                                        |
|------------|-----------------------|------------------------------------------------------|
| LibreChat  | http://localhost:3080 | `npm run backend` (LibreChat repo)                   |
| LiteLLM    | http://localhost:4000 | `litellm --config litellm_routing_config.yaml`       |
| RAG API    | http://localhost:8000 | `uvicorn main:app --port 8000` (rag_api dir)         |
| MongoDB    | localhost:27017       | Windows service                                      |
| PostgreSQL | localhost:5432        | Windows service                                      |

---

## Security Notes

- All RAG API secrets (`RAG_AZURE_OPENAI_API_KEY`, `DB_PASS`) live in the
  rag_api directory's `.env` file and are NOT committed to source control.
- `scripts/.env` holds `RAG_API_URL` and the DB connection params only --
  no embedding API keys are stored in this repo.
- If Dev 2 receives HTTP 502 from LibreChat when uploading a file, the RAG API
  is not running.
- If embeddings succeed but retrieval returns nothing, confirm `COLLECTION_NAME=librechat`
  in the rag_api `.env` matches what LibreChat sends in `collection_name` query fields.
