// Failure alerting for the scheduled ACA Jobs (WI 12341).
//
// Azure Monitor sends the alert email NATIVELY via an action group — no app
// SMTP and no Ops dependency. Point `alertEmailAddress` at any inbox/DL we own.
//
// The alert is a Log Analytics scheduled query rule over the jobs' console logs.
// ⚠️ VALIDATE IN DEV BEFORE RELYING ON IT: the table name (ContainerAppConsoleLogs_CL
// vs the resource-specific ContainerAppConsoleLogs) and the exact failure strings
// depend on this workspace's ingestion. Run the query in the Log Analytics blade
// against a real FAILED run first and adjust `failureQuery` to match. Structure is
// correct; the KQL is the part to confirm.

param envName string = 'Dev'
param location string = 'eastus'
// Log Analytics workspace the ACA environment logs to (main.bicep: cdb-workspace-<env>).
param workspaceName string
// Recipient for the failure email (an inbox or DL we own). Empty => caller should
// not deploy this module (main.bicep gates on non-empty).
param alertEmailAddress string

var oktaJobName = 'job-cgfe-okta-sync-${toLower(envName)}'
var cleanupJobName = 'job-cgfe-cleanup-${toLower(envName)}'

resource workspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = {
  name: workspaceName
}

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-cgfe-jobs-${toLower(envName)}'
  location: 'global'
  properties: {
    groupShortName: 'cgfejobs'
    enabled: true
    emailReceivers: [
      {
        name: 'jobalerts'
        emailAddress: alertEmailAddress
        useCommonAlertSchema: true
      }
    ]
  }
}

// Failure signal, scoped to just our two jobs so app traffic can't trip it.
// Keys on FAILURE-ONLY markers: the shared logging format emits `[ERROR]` only on
// real failures (both scripts), and the sync job emits an explicit
// `SYNC_SUMMARY status=failed`. Deliberately NOT matching bare 'canary' /
// 'circuit breaker' — those words also appear in HEALTHY logs and would false-alarm.
// NB: single-quoted (interpolated) string — Bicep's triple-quote strings do NOT
// interpolate, which would bake the literal '${...}' into the query.
var failureQuery = 'ContainerAppConsoleLogs_CL\n| where ContainerAppName_s in (\'${oktaJobName}\', \'${cleanupJobName}\')\n| where Log_s contains \'[ERROR]\' or Log_s contains \'SYNC_SUMMARY status=failed\''

resource jobFailureAlert 'Microsoft.Insights/scheduledQueryRules@2022-06-15' = {
  name: 'alert-cgfe-job-failure-${toLower(envName)}'
  location: location
  properties: {
    displayName: 'CGFE scheduled job failure (${envName})'
    description: 'Fires when the Okta sync or nightly cleanup ACA job logs a failure.'
    severity: 2
    enabled: true
    // Hourly evaluation over a 1h window = continuous coverage; a failure at the
    // 02:00/05:00 UTC run is caught within the hour.
    evaluationFrequency: 'PT1H'
    windowSize: 'PT1H'
    scopes: [
      workspace.id
    ]
    criteria: {
      allOf: [
        {
          query: failureQuery
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    autoMitigate: true
    actions: {
      actionGroups: [
        actionGroup.id
      ]
    }
  }
}

output actionGroupId string = actionGroup.id
output alertRuleId string = jobFailureAlert.id
