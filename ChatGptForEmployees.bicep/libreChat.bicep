param envName string = 'Dev'
param location string = 'eastus'
param environmentId string
param defaultDomain string
param libreChatImage string
// Per-env ACR (acrcgfe<env>) that now hosts the LibreChat image. Wired from main.bicep.
param acrName string
param minReplicas int = 0
param appInsightsConnectionString string
param liteLlmInternalUrl string
param ragApiInternalUrl string
@secure()
param mongoConnectionString string
@secure()
param jwtSecret string
@secure()
param jwtRefreshSecret string
@secure()
param credsKey string
@secure()
param credsIv string
@secure()
param liteLlmVirtualKey string
@secure()
param openIdClientId string
@secure()
param openIdClientSecret string
@secure()
param openIdSessionSecret string
@secure()
param storageConnectionString string
param blobContainerName string
// Static Web App defaultHostname (from staticSite.bicep via main.bicep) — the user
// Help/FAQ page. Used for the footer link + the account-menu Help & FAQ link below.
param helpUrl string
// Read-aloud (text-to-speech) via Azure OpenAI. All three are consumed by the
// speech.tts.azureOpenAI block in config/librechat.yaml, which references them as
// ${TTS_*} placeholders — that keeps the single shared librechat.yaml env-agnostic
// while each Container App points at its own Azure OpenAI account and deployment.
@secure()
param ttsApiKey string
param ttsInstanceName string
param ttsDeploymentName string

var appName = 'ca-librechat-${toLower(envName)}'
var allowRegistration = false
var libreChatUrl = 'https://${appName}.${defaultDomain}'

// The LibreChat image lives in our per-env ACR (acrcgfe<env>); reference it to read the
// registry's admin credentials at deploy time for the image pull below (mirrors jobs.bicep).
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource libreChatApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 3080
        transport: 'Auto'
        allowInsecure: false
        stickySessions: {
          affinity: 'sticky'
        }
      }
      secrets: [
        { name: 'mongo-uri', value: mongoConnectionString }
        { name: 'jwt-secret', value: jwtSecret }
        { name: 'jwt-refresh-secret', value: jwtRefreshSecret }
        { name: 'creds-key', value: credsKey }
        { name: 'creds-iv', value: credsIv }
        { name: 'litellm-virtual-key', value: liteLlmVirtualKey }
        { name: 'openid-client-id', value: openIdClientId }
        { name: 'openid-client-secret', value: openIdClientSecret }
        { name: 'openid-session-secret', value: openIdSessionSecret }
        { name: 'azure-storage-connection-string', value: storageConnectionString }
        { name: 'tts-api-key', value: ttsApiKey }
        // ACR admin password (read at deploy time) so the app can pull its image from
        // acrcgfe<env>. Mirrors jobs.bicep: the deploy SP can read a registry's own creds
        // but can't assign an AcrPull role, so we pull with admin creds (WI 12306 hardens).
        { name: 'acr-password', value: acr.listCredentials().passwords[0].value }
      ]
      // Pull the LibreChat image from our ACR using the admin credentials above. (No
      // registries block was needed while the image came from public ghcr.io.)
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'librechat'
          image: libreChatImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'HOST', value: '0.0.0.0' }
            { name: 'PORT', value: '3080' }
            { name: 'NODE_ENV', value: 'production' }
            { name: 'ALLOW_REGISTRATION', value: allowRegistration ? 'true' : 'false' }
            { name: 'ALLOW_EMAIL_LOGIN', value: 'false' }
            { name: 'ALLOW_SOCIAL_LOGIN', value: 'true' }
            { name: 'CONFIG_PATH', value: '/app/api/data/librechat.yaml' }
            { name: 'LITELLM_URL', value: 'http://${liteLlmInternalUrl}' }
            { name: 'RAG_API_URL', value: 'http://${ragApiInternalUrl}' }
            { name: 'DOMAIN_CLIENT', value: libreChatUrl }
            { name: 'DOMAIN_SERVER', value: libreChatUrl }
            { name: 'OPENID_ENABLED', value: 'true' }
            { name: 'OPENID_ISSUER', value: 'https://romtech.okta.com' }
            { name: 'OPENID_SCOPE', value: 'openid profile email' }
            { name: 'OPENID_BUTTON_TEXT', value: 'Login with ROMTech Okta' }
            { name: 'OPENID_CALLBACK_URL', value: '/oauth/openid/callback' }
            // Browser-tab + in-app product name. Unset, LibreChat shows "LibreChat";
            // brand it ROMChat (user-facing rebrand — model aliases stay unchanged).
            { name: 'APP_TITLE', value: 'ROMChat' }
            // Footer renders markdown (Footer.tsx) — a single clickable "Help & FAQ"
            // link to the Static Web App help page (helpUrl, from staticSite.bicep).
            // Replaced the earlier "ROMTech AI — Internal Use Only" branding text.
            { name: 'CUSTOM_FOOTER', value: '[Help & FAQ](https://${helpUrl})' }
            // Account-menu "Help & FAQ" link — defaults to librechat.ai when unset,
            // so repoint it to our help page (opens in a new tab). Set to '/' to hide.
            { name: 'HELP_AND_FAQ_URL', value: 'https://${helpUrl}' }
            { name: 'MONGO_URI', secretRef: 'mongo-uri' }
            { name: 'JWT_SECRET', secretRef: 'jwt-secret' }
            { name: 'JWT_REFRESH_SECRET', secretRef: 'jwt-refresh-secret' }
            { name: 'CREDS_KEY', secretRef: 'creds-key' }
            { name: 'CREDS_IV', secretRef: 'creds-iv' }
            { name: 'LITELLM_VIRTUAL_KEY', secretRef: 'litellm-virtual-key' }
            { name: 'OPENID_CLIENT_ID', secretRef: 'openid-client-id' }
            { name: 'OPENID_CLIENT_SECRET', secretRef: 'openid-client-secret' }
            { name: 'OPENID_SESSION_SECRET', secretRef: 'openid-session-secret' }
            // Azure Blob file storage (fileStrategy: azure_blob in librechat.yaml).
            // PUBLIC_ACCESS forced false so PHI files are never publicly readable
            // (LibreChat defaults it to true). Container + soft-delete: storage.bicep.
            { name: 'AZURE_STORAGE_CONNECTION_STRING', secretRef: 'azure-storage-connection-string' }
            { name: 'AZURE_CONTAINER_NAME', value: blobContainerName }
            { name: 'AZURE_STORAGE_PUBLIC_ACCESS', value: 'false' }
            // Read-aloud TTS (speech.tts.azureOpenAI in librechat.yaml). The instance
            // name is the bare Azure OpenAI account name — LibreChat's genAzureEndpoint
            // appends `.openai.azure.com` and the /openai/deployments/... path itself.
            // Azure OpenAI TTS is covered by the Microsoft BAA, so it is PHI-safe; no
            // non-BAA provider (OpenAI, ElevenLabs) is configured in any environment.
            { name: 'TTS_INSTANCE_NAME', value: ttsInstanceName }
            { name: 'TTS_DEPLOYMENT_NAME', value: ttsDeploymentName }
            { name: 'TTS_API_KEY', secretRef: 'tts-api-key' }
          ]
          volumeMounts: [
            {
              volumeName: 'librechat-data'
              mountPath: '/app/api/data'
            }
          ]
          // Health probe path is '/health' on LibreChat v0.8.x (api/server/index.js).
          // It was '/api/health' on v0.7.5 — using the old path 404s, so probes fail,
          // the replica never goes ready, and the revision crash-loops ("Progress
          // Deadline Exceeded"). Re-verify this path on any future major version bump.
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 3080 }
              initialDelaySeconds: 20
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 3080 }
              initialDelaySeconds: 20
              periodSeconds: 10
              failureThreshold: 3
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'librechat-data'
          storageType: 'AzureFile'
          storageName: 'librechat-data-store'
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: 2
      }
    }
  }
}

output fqdn string = libreChatApp.properties.configuration.ingress.fqdn
output principalId string = libreChatApp.identity.principalId
output appName string = libreChatApp.name
