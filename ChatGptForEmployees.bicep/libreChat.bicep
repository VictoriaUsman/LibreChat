param envName string = 'Dev'
param location string = 'eastus'
param environmentId string
param libreChatImage string
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
param ragApiJwtSecret string

var appName = 'ca-librechat-${toLower(envName)}'
var allowRegistration = envName != 'Prod'

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
        { name: 'rag-api-jwt-secret', value: ragApiJwtSecret }
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
            { name: 'ALLOW_SOCIAL_LOGIN', value: 'true' }
            { name: 'CONFIG_PATH', value: '/app/api/data/librechat.yaml' }
            { name: 'LITELLM_URL', value: 'http://${liteLlmInternalUrl}' }
            { name: 'RAG_API_URL', value: 'http://${ragApiInternalUrl}' }
            { name: 'OPENID_ISSUER', value: 'https://romtech.okta.com/oauth2/default' }
            { name: 'OPENID_SCOPE', value: 'openid profile email' }
            { name: 'OPENID_BUTTON_TEXT', value: 'Login with ROMTech Okta' }
            { name: 'OPENID_CALLBACK_URL', value: '/oauth/openid/callback' }
            { name: 'MONGO_URI', secretRef: 'mongo-uri' }
            { name: 'JWT_SECRET', secretRef: 'jwt-secret' }
            { name: 'JWT_REFRESH_SECRET', secretRef: 'jwt-refresh-secret' }
            { name: 'CREDS_KEY', secretRef: 'creds-key' }
            { name: 'CREDS_IV', secretRef: 'creds-iv' }
            { name: 'LITELLM_VIRTUAL_KEY', secretRef: 'litellm-virtual-key' }
            { name: 'OPENID_CLIENT_ID', secretRef: 'openid-client-id' }
            { name: 'OPENID_CLIENT_SECRET', secretRef: 'openid-client-secret' }
            { name: 'OPENID_SESSION_SECRET', secretRef: 'openid-session-secret' }
            { name: 'RAG_API_JWT_SECRET', secretRef: 'rag-api-jwt-secret' }
          ]
          volumeMounts: [
            {
              volumeName: 'librechat-data'
              mountPath: '/app/api/data'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/api/health', port: 3080 }
              initialDelaySeconds: 20
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/api/health', port: 3080 }
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
