# Cosmos DB Index Fix — LibreChat User Registration

Cosmos DB for MongoDB does not support sparse unique indexes. LibreChat creates sparse unique indexes for social login providers (Google, Facebook, etc.) that are never used. This causes an E11000 duplicate key error when a second user attempts to register or log in.

This fix must be applied once per environment, before any users are created.

---

## Prerequisites

Install mongosh if you don't have it:

```bash
npm install -g mongosh
```

---

## Steps

### 1. Delete existing users

In the Azure Portal, open your Cosmos DB account → **Data Explorer** → **LibreChat** → **users**.

Delete every document in the collection. If you had an admin user, note down the email before deleting.

> The indexes cannot be dropped while documents exist in Cosmos DB for MongoDB (RU-based).

---

### 2. Get the connection string

In the Azure Portal, open your Cosmos DB account → **Settings** → **Connection Strings**.

Copy the **Primary Connection String**. It looks like:

```
mongodb://cosmos-cgfe-dev:<key>@cosmos-cgfe-dev.mongo.cosmos.azure.com:10255/?ssl=true&retrywrites=false
```

---

### 3. Connect with mongosh

```bash
mongosh "mongodb://cosmos-cgfe-dev:<key>@cosmos-cgfe-dev.mongo.cosmos.azure.com:10255/?ssl=true&retrywrites=false&maxIdleTimeMS=120000"
```

---

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

---

### 5. Register users again

Go to LibreChat and register your account as usual. Other users can now also register without errors.

---

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

> The pipeline automatically drops these indexes after every deployment going forward, so this manual fix is only needed the first time per environment.
