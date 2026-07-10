# Cosmos DB Index Fix — LibreChat User Registration

Cosmos DB for MongoDB does not support sparse unique indexes. LibreChat creates sparse unique indexes for social login providers (Google, Facebook, etc.) that are never used. This causes an E11000 duplicate key error when a second user attempts to register or log in.

This fix must be applied once per environment, before any users are created.

> **Update (PBI: Pin LibreChat to Stable v0.8.6 Across All Environments).** The previous version of this doc claimed "the pipeline automatically drops these indexes after every deployment going forward." No such step exists in `ChatGptForEmployees.pipelines/*.yml` — that claim did not match reality and has been removed. What actually changed in v0.8.0+ is described below.

---

## v0.8.0+ supersedes this manual fix — but requires its own manual step

LibreChat's v0.8.0 multi-tenancy change ships a real migration for this,
`dropSupersededTenantIndexes` (and a sibling, `dropSupersededPromptGroupIndexes`),
exported from `@librechat/data-schemas`
(`packages/data-schemas/src/migrations/tenantIndexes.ts` /
`promptGroupIndexes.ts` in the LibreChat source). It covers far more than the
old manual list below — old *unique* indexes across 12 collections that
conflict with the new tenant-scoped compound indexes:

```
users:            email_1, googleId_1, facebookId_1, openidId_1,
                  openidId_1_tenantId_1, samlId_1, ldapId_1, githubId_1,
                  discordId_1, appleId_1
roles:            name_1
agents:           id_1
conversations:    conversationId_1, conversationId_1_user_1
messages:         messageId_1, messageId_1_user_1
presets:          presetId_1
agentcategories:  value_1
accessroles:      accessRoleId_1
conversationtags: tag_1_user_1
mcpservers:       serverName_1
files:            filename_1_conversationId_1_context_1
groups:           idOnTheSource_1_source_1
promptgroups:     createdAt_1_updatedAt_1  (dropSupersededPromptGroupIndexes)
```

**This is NOT wired into automatic startup** — there is no call site for
either function anywhere under `api/` in the v0.8.6 source, and no shipped
`config/migrate-*.js` CLI wrapper for it either (unlike its sibling
migrations `migrate-prompt-permissions.js`,
`migrate-shared-link-permissions.js`, which do exist). It must be invoked
manually, once per environment, as part of the v0.8.6 cutover — otherwise
the same class of duplicate-key error this doc originally covered can
resurface under the new tenant-scoped indexes (`email_1`, `openidId_1`,
`openidId_1_tenantId_1` are new in this set).

### Known risk — verify before trusting this on Test/Prod

The original manual fix below required **deleting every user document
first**, because "indexes cannot be dropped while documents exist in Cosmos
DB for MongoDB (RU-based)." `dropSupersededTenantIndexes` calls the same
underlying `collection.dropIndex()` — if that RU-based restriction is what
caused the original problem (not just the sparse+unique combination), the
same restriction likely blocks this migration too on collections that
already have real data (`users`, `conversations`, `messages`, etc. in Dev/
Test/Prod all have live data by now). The function does not throw on a
per-index failure — it logs to `result.errors` and continues to the next
index — so a partial or total failure will NOT crash the app or fail a
deploy; it will silently leave old indexes in place.

**Before relying on this for the v0.8.6 cutover:** run it against Dev first
(which has real conversations/messages by now, same shape as Test/Prod) and
inspect the returned `result.errors`. If it comes back empty, the migration
is safe to run against Test then Prod. If `errors` is non-empty, the
original document-deletion workaround (or an equivalent one scoped to the
newly-superseded collections) will be needed before this can complete —
escalate rather than assuming the app "started cleanly" means the indexes
were actually dropped.

### How to run it

The image does not ship a runnable script for this, so invoke it inline
against the running container (values from the Environment reference table
below):

```bash
az containerapp exec --name ca-librechat-<env> --resource-group <rg> --command "/bin/sh"
# inside the container:
node -e "
const mongoose = require('mongoose');
const { dropSupersededTenantIndexes, dropSupersededPromptGroupIndexes } = require('@librechat/data-schemas');
(async () => {
  await mongoose.connect(process.env.MONGO_URI);
  console.log('tenant indexes:', await dropSupersededTenantIndexes(mongoose.connection));
  console.log('promptGroup indexes:', await dropSupersededPromptGroupIndexes(mongoose.connection));
  await mongoose.disconnect();
})();
"
```

---

## Original manual fix (pre-v0.8.0 / if the migration above fails)

### Prerequisites

Install mongosh if you don't have it:

```bash
npm install -g mongosh
```

### 1. Delete existing users

In the Azure Portal, open your Cosmos DB account → **Data Explorer** → **LibreChat** → **users**.

Delete every document in the collection. If you had an admin user, note down the email before deleting.

> The indexes cannot be dropped while documents exist in Cosmos DB for MongoDB (RU-based).

### 2. Get the connection string

In the Azure Portal, open your Cosmos DB account → **Settings** → **Connection Strings**.

Copy the **Primary Connection String**. It looks like:

```
mongodb://cosmos-cgfe-dev:<key>@cosmos-cgfe-dev.mongo.cosmos.azure.com:10255/?ssl=true&retrywrites=false
```

### 3. Connect with mongosh

```bash
mongosh "mongodb://cosmos-cgfe-dev:<key>@cosmos-cgfe-dev.mongo.cosmos.azure.com:10255/?ssl=true&retrywrites=false&maxIdleTimeMS=120000"
```

### 4. Drop the incompatible indexes

```javascript
use LibreChat

db.users.reIndex()

db.users.dropIndex("googleId_1")
db.users.dropIndex("facebookId_1")
db.users.dropIndex("samlId_1")
db.users.dropIndex("ldapId_1")
db.users.dropIndex("githubId_1")
db.users.dropIndex("discordId_1")
db.users.dropIndex("appleId_1")
```

Each command returns `{ "nIndexesWas": N, "ok": 1 }` on success. If an index does not exist it will throw an error — that is fine, continue with the rest.

### 5. Register users again

Go to LibreChat and register your account as usual. Other users can now also register without errors.

### 6. Restore admin role

After registering, go back to **Cosmos DB Data Explorer** → **LibreChat** → **users**, open your user document, and change:

```json
"role": "USER"
```

to:

```json
"role": "ADMIN"
```

Save the document.

---

## Environment reference

| Environment | Cosmos DB account | Resource group |
|---|---|---|
| Dev | `cosmos-cgfe-dev` | `rg-dev-shared` |
| Test | `cosmos-cgfe-test` | `rg-test-shared` |
| Prod | `cosmos-cgfe-prod` | `rg-prod-shared` |
