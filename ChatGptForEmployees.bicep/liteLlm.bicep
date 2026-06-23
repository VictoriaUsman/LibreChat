param envName string = 'Dev'
param location string = 'eastus'
param environmentId string
param liteLlmImage string
param minReplicas int = 0
param appInsightsConnectionString string
param azureOpenAiEndpoint string
@secure()
param azureOpenAiApiKey string
@secure()
param liteLlmMasterKey string
@secure()
param databaseUrl string

var appName = 'ca-litellm-${toLower(envName)}'

resource liteLlmApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: 4000
        transport: 'Auto'
        allowInsecure: false
      }
      secrets: [
        { name: 'litellm-master-key', value: liteLlmMasterKey }
        { name: 'database-url', value: databaseUrl }
        { name: 'azure-openai-api-key', value: azureOpenAiApiKey }
      ]
    }
    template: {
      containers: [
        {
          name: 'litellm'
          image: liteLlmImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          args: [
            '--config'
            '/app/config/litellm_routing_config.yaml'
            '--port'
            '4000'
          ]
          env: [
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'PORT', value: '4000' }
            { name: 'LITELLM_ENV', value: toLower(envName) }
            { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
            { name: 'LITELLM_MASTER_KEY', secretRef: 'litellm-master-key' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-api-key' }
          ]
          volumeMounts: [
            {
              volumeName: 'litellm-config'
              mountPath: '/app/config'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health/liveliness', port: 4000 }
              initialDelaySeconds: 15
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health/readiness', port: 4000 }
              initialDelaySeconds: 15
              periodSeconds: 10
              failureThreshold: 3
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'litellm-config'
          storageType: 'AzureFile'
          storageName: 'litellm-config-store'
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: 2
      }
    }
  }
}

output fqdn string = liteLlmApp.properties.configuration.ingress.fqdn
output principalId string = liteLlmApp.identity.principalId
output appName string = liteLlmApp.name
