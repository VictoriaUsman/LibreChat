param envName string = 'Dev'
param location string = 'eastus'
param environmentId string
param liteLlmImage string
param minReplicas int = 0
param maxReplicas int = 2
// In-flight requests per replica that trigger a scale-out (ACA's default is 10 when no rule
// is declared). Set from main.bicep, which tunes it per service.
param concurrentRequests int = 10
// cpu is a string so it can be passed through json() below (the ARM property is numeric).
// cpu:memory must hold ACA's 1:2 vCPU:GiB ratio — main.bicep pairs them in one object.
param containerCpu string = '0.5'
param containerMemory string = '1Gi'
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
        allowInsecure: true
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
            cpu: json(containerCpu)
            memory: containerMemory
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
            // Manual-migration mode (LiteLLM v1.99.0 review note 3): startup no
            // longer runs `prisma db push`/auto-repair against the database.
            // Every future LiteLLM upgrade now requires an explicit, reviewed
            // migration step (see ChatGptForEmployees.docs/local/REVIEW-AND-CUTOVER.md)
            // BEFORE the new image is allowed to start against the database.
            // A conflicting general_settings.disable_prisma_schema_update value
            // in litellm_routing_config.yaml would take precedence over this --
            // confirmed absent as of this change (Step 1 above).
            { name: 'DISABLE_SCHEMA_UPDATE', value: 'true' }
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
      // Declaring an explicit rule replaces ACA's implicit default (HTTP, 10 concurrent
      // requests per replica). The threshold is deliberately AT OR BELOW LibreChat's, not
      // above it: every chat turn becomes a request here, and the container runs a single
      // uvicorn worker (no --num_workers in the args above), so one GIL-bound process does
      // the SSE parsing, token counting, per-chunk pricing, and spend-log write. It contends
      // on CPU long before a generous threshold would trip. See main.bicep for the numbers.
      //
      // ⚠️ Running more than one replica means the router's in-memory state is PER REPLICA,
      // not shared:
      //   • rate-limit / TPM tracking — each replica admits up to its own limit, so N replicas
      //     admit N× what a single instance would.
      //   • deployment cooldown — after a primary 429s, each replica learns that independently,
      //     so a sustained Azure throttle has every replica burn its own num_retries before
      //     failing over. Extra retry pressure on an already-throttling endpoint, not a
      //     correctness break.
      // Harmless while nothing enforcement-shaped is in the request path — spend logging goes
      // to Postgres and is transactional, so it is unaffected — but a shared Redis cache is a
      // prerequisite before turning budget or rate-limit enforcement on for real traffic.
      //
      // ⚠️ That "nothing enforced" claim is about the CONFIG, which sets no max_budget and no
      // per-model rpm/tpm. Budgets and limits can also be attached at runtime to the virtual
      // key LibreChat authenticates with (liteLlmVirtualKey). If that key carries a budget or
      // rate limit, enforcement IS in the request path and the per-replica caveat above
      // applies for real. Verify the key's settings in LiteLLM before scaling prod out.
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

output fqdn string = liteLlmApp.properties.configuration.ingress.fqdn
output principalId string = liteLlmApp.identity.principalId
output appName string = liteLlmApp.name
