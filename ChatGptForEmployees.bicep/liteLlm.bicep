param envName string = 'Dev'
param location string = 'eastus'
param environmentId string
param liteLlmImage string
param minReplicas int = 0
param maxReplicas int = 2
// Maintenance-state enforcement (LiteLLM v1.99.0 review, Follow-up 1 P1: "preserve
// maintenance isolation throughout deployment"; corrected per the `89c57d0`
// working-changes follow-up, Finding 2, and extended again per the second
// working-changes follow-up, Finding 1: "validate LibreChat before releasing
// users and jobs"). Four states, shared with libreChat.bicep and jobs.bicep so
// all three modules read the same value from main.bicep:
//   'paused'       -- this app forced to 0/0 replicas (same as the old
//                     maintenanceMode=true). Used while the database migration
//                     itself runs.
//   'litellm-only' -- this app runs at its normal minReplicas/maxReplicas so an
//                     operator can send direct, internal-only synthetic requests
//                     to it (see REVIEW-AND-CUTOVER.md §2a Step 8d) -- but
//                     libreChat.bicep stays at 0/0 in this same state (see that
//                     module), so no ordinary employee request can reach this
//                     app end-to-end yet.
//   'validation'   -- this app stays at normal scale (identical to
//                     'litellm-only' from this module's point of view);
//                     libreChat.bicep now ALSO runs, but restricted to
//                     authorized testers via its own ipSecurityRestrictions
//                     (see that module) -- this app has no ingress restriction
//                     of its own beyond `external: false` (already
//                     internal-only), so in both 'litellm-only' and
//                     'validation' this app relies on LibreChat being the only
//                     realistic path an ordinary employee has to it.
//   'off'          -- normal operation; this app runs at its normal scale, same
//                     as libreChat.bicep and jobs.bicep's normal schedules.
// See REVIEW-AND-CUTOVER.md, "Maintenance-mode enforcement" (§8.1, as
// corrected), for the full enter/verify/release sequence across all four
// states.
@allowed(['off', 'paused', 'litellm-only', 'validation'])
param maintenanceState string = 'off'
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
            // confirmed absent in litellm_routing_config.yaml as of this change.
            { name: 'DISABLE_SCHEMA_UPDATE', value: 'true' }
            // Closes the prompt-storage OR-gate risk (LiteLLM v1.99.0 review
            // addendum, Finding 1): _should_store_prompts_and_responses_in_spend_logs()
            // returns True if EITHER general_settings.store_prompts_in_spend_logs OR
            // this env var is true -- an explicit YAML `false` alone does NOT block a
            // `true` env var from re-enabling storage (verified by running the pinned
            // image with both set; see REVIEW-AND-CUTOVER.md §1). Both must be pinned
            // false together so no shared-environment or ad-hoc override can flip
            // storage on.
            { name: 'STORE_PROMPTS_IN_SPEND_LOGS', value: 'false' }
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
        // Only 'paused' forces 0/0 here -- 'litellm-only' and 'off' both run at
        // normal scale (this app is up in both; see the param comment above for
        // why 'litellm-only' still blocks ordinary traffic via libreChat.bicep,
        // not via this app's own scale).
        minReplicas: maintenanceState == 'paused' ? 0 : minReplicas
        maxReplicas: maintenanceState == 'paused' ? 0 : maxReplicas
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
