// Failure alerting for the scheduled ACA Jobs (WI 12341).
//
// Azure Monitor sends the alert email NATIVELY via an action group — no app
// SMTP and no Ops dependency. Point `alertEmailAddresses` at the inboxes/DLs we own.
//
// The alert is a Log Analytics scheduled query rule over the jobs' console logs.
// ⚠️ VALIDATE IN DEV BEFORE RELYING ON IT (see main.dev.bicepparam): set a dev
// recipient, deploy, FORCE a failed run, and confirm the email arrives.
//
// COVERAGE / KNOWN GAP: this query keys on the jobs' own stdout, so it catches
// every *handled* failure (both scripts log `[ERROR]` before a non-zero exit; the
// sync job also emits `SYNC_SUMMARY status=failed`) plus escaped exceptions
// (`Traceback`). It does NOT catch failures that produce no stdout — OOM kills,
// image-pull failures, or a replica killed at `replicaTimeout` before it logs.
// Closing that requires a control-plane signal. Build it during the dev
// validation above: inspect ContainerAppSystemLogs_CL during a forced infra
// failure, then `union` an execution-failure clause into `failureQuery`. Left out
// here deliberately rather than shipped as unverified KQL. (Tracked as a follow-up.)

param envName string = 'Dev'
param location string = 'eastus'
// Log Analytics workspace the ACA environment logs to (main.bicep: cdb-workspace-<env>).
param workspaceName string
// Recipients for the failure email (inboxes/DLs we own). Empty => caller should
// not deploy this module (main.bicep gates on non-empty).
param alertEmailAddresses array

resource workspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = {
  name: workspaceName
}

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-cgfe-jobs-${toLower(envName)}'
  location: 'global'
  properties: {
    groupShortName: 'cgfejobs'
    enabled: true
    emailReceivers: [for (email, i) in alertEmailAddresses: {
      name: 'jobalerts-${i}'
      emailAddress: email
      useCommonAlertSchema: true
    }]
  }
}

// Scoped to our jobs by the `job-cgfe-` name prefix. `startswith` (not an exact
// name list) survives either log schema — bare job name or execution-suffixed
// replica name — so the rule can't silently match nothing. No app is named
// `job-cgfe-*`, so app traffic can't trip it.
// FAILURE-ONLY markers: `[ERROR]` (both scripts log it only on real failures),
// the sync job's explicit `SYNC_SUMMARY status=failed`, and `Traceback` (an
// exception that escaped main()). Deliberately NOT bare 'canary' / 'circuit
// breaker' — those appear in HEALTHY logs and would false-alarm.
// NB: single-quoted (interpolated) string — Bicep triple-quote strings do NOT
// interpolate.
var failureQuery = 'ContainerAppConsoleLogs_CL\n| where ContainerAppName_s startswith \'job-cgfe-\'\n| where Log_s contains \'[ERROR]\' or Log_s contains \'SYNC_SUMMARY status=failed\' or Log_s contains \'Traceback (most recent call last)\''

resource jobFailureAlert 'Microsoft.Insights/scheduledQueryRules@2022-06-15' = {
  name: 'alert-cgfe-job-failure-${toLower(envName)}'
  location: location
  properties: {
    displayName: 'CGFE scheduled job failure (${envName})'
    description: 'Fires when the Okta sync or nightly cleanup ACA job logs a failure.'
    severity: 2
    enabled: true
    // Hourly evaluation over a 2h window (overlapping) so a failure whose log is
    // ingested a few minutes late can't slip between a 1h window and the next
    // evaluation. autoMitigate + the once-nightly cadence prevent double-alerting.
    evaluationFrequency: 'PT1H'
    windowSize: 'PT2H'
    // The workspace-wide _CL table always pre-exists (the always-on apps log to it
    // continuously), but skip PUT-time query validation so a first-ever deploy into
    // a brand-new workspace can't fail on a not-yet-created table.
    skipQueryValidation: true
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
