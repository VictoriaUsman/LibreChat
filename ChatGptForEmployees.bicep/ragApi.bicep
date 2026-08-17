param envName string = 'Dev'
param location string = 'eastus'
param environmentId string
param ragApiImage string
param minReplicas int = 0
param maxReplicas int = 2
// In-flight requests per replica that trigger a scale-out (ACA's default is 10 when no rule
// is declared). Set from main.bicep, which tunes it per service.
param concurrentRequests int = 10
// cpu is a string so it can be passed through json() below (the ARM property is numeric).
// cpu:memory must hold ACA's 1:2 vCPU:GiB ratio — main.bicep pairs them in one object.
param containerCpu string = '0.5'
param containerMemory string = '1Gi'
param azureOpenAiEndpoint string
@secure()
param azureOpenAiApiKey string
param embeddingsDeploymentName string
@secure()
param databaseUrl string
param postgresHost string
param postgresUser string
@secure()
param postgresPassword string
@secure()
param jwtSecret string

var appName = 'ca-ragapi-${toLower(envName)}'

resource ragApiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: 8000
        transport: 'Auto'
        allowInsecure: true
      }
      secrets: [
        { name: 'azure-openai-api-key', value: azureOpenAiApiKey }
        { name: 'postgres-url', value: databaseUrl }
        { name: 'postgres-password', value: postgresPassword }
        { name: 'jwt-secret', value: jwtSecret }
      ]
    }
    template: {
      containers: [
        {
          name: 'rag-api'
          image: ragApiImage
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
          env: [
            { name: 'HOST', value: '0.0.0.0' }
            { name: 'PORT', value: '8000' }
            { name: 'LOG_LEVEL', value: 'INFO' }
            { name: 'EMBEDDINGS_PROVIDER', value: 'azure' }
            { name: 'EMBEDDINGS_MODEL', value: embeddingsDeploymentName }
            { name: 'RAG_AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
            { name: 'RAG_AZURE_OPENAI_API_VERSION', value: '2024-10-21' }
            { name: 'COLLECTION_NAME', value: 'librechat' }
            { name: 'CHUNK_SIZE', value: '1500' }
            { name: 'CHUNK_OVERLAP', value: '100' }
            { name: 'RAG_AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-api-key' }
            { name: 'DATABASE_URL', secretRef: 'postgres-url' }
            { name: 'DB_HOST', value: postgresHost }
            { name: 'DB_PORT', value: '5432' }
            { name: 'POSTGRES_DB', value: 'librechat_rag' }
            { name: 'POSTGRES_USER', value: postgresUser }
            { name: 'POSTGRES_PASSWORD', secretRef: 'postgres-password' }
            { name: 'JWT_SECRET', secretRef: 'jwt-secret' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 20
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 20
              periodSeconds: 10
              failureThreshold: 3
            }
          ]
        }
      ]
      // Declaring an explicit rule replaces ACA's implicit default (HTTP, 10 concurrent
      // requests per replica). This is the most conservative threshold of the three and tops
      // out lowest: traffic arrives only on document upload and File Search retrieval, not on
      // every turn. The embedding calls themselves are remote (EMBEDDINGS_PROVIDER: azure), so
      // those are I/O waits — the genuinely heavy work is parsing and chunking a large upload,
      // where memory is the binding constraint rather than CPU.
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: string(concurrentRequests)
              }
            }
          }
        ]
      }
    }
  }
}

output fqdn string = ragApiApp.properties.configuration.ingress.fqdn
output principalId string = ragApiApp.identity.principalId
output appName string = ragApiApp.name
