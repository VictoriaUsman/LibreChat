# Okta OIDC Setup — ChatGPT for Employees

## Dev Environment

**LibreChat URL:** `https://ca-librechat-dev.orangerock-6ea70881.eastus2.azurecontainerapps.io`

---

### 1. What the Okta admin must configure

Create a new **OIDC Web Application** in Okta with the following settings:

| Field | Value |
|---|---|
| Application name | `ChatGPT for Employees - Dev` |
| Application type | Web Application |
| Grant type | Authorization Code |
| Sign-in redirect URI | `https://ca-librechat-dev.orangerock-6ea70881.eastus2.azurecontainerapps.io/oauth/openid/callback` |
| Sign-out redirect URI | `https://ca-librechat-dev.orangerock-6ea70881.eastus2.azurecontainerapps.io` |
| Initiate login URI | `https://ca-librechat-dev.orangerock-6ea70881.eastus2.azurecontainerapps.io` |
| Assignments | Users or groups that should have access |

---

### 2. What the Okta admin provides after creating the app

Store these values in Azure Key Vault (`kv-romtech-dev`):

| Value | Key Vault Secret Name |
|---|---|
| Client ID | `ChatGptForEmployeesDev-OpenIdClientId` |
| Client Secret | `ChatGptForEmployeesDev-OpenIdClientSecret` |

---

### 3. What we generate (not from Okta)

| Value | How to generate | Key Vault Secret Name |
|---|---|---|
| Session Secret | `openssl rand -hex 32` | `ChatGptForEmployeesDev-OpenIdSessionSecret` |

---

### 4. Already configured in Bicep (no action needed)

| Environment Variable | Value |
|---|---|
| `OPENID_ISSUER` | `https://romtech.okta.com/oauth2/default` |
| `OPENID_SCOPE` | `openid profile email` |
| `OPENID_CALLBACK_URL` | `/oauth/openid/callback` |
| `OPENID_BUTTON_TEXT` | `Login with ROMTech Okta` |

---

## Test & Production

The same steps apply for Test and Production. The redirect URIs and Key Vault secret names follow the same pattern — replace `Dev`/`dev` with `Test`/`test` or `Prod`/`prod` accordingly.

The LibreChat URLs for those environments will be available as pipeline outputs after deployment.
