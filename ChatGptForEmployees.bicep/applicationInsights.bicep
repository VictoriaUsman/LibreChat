param appName string = 'ChatGptForEmployees'
param envName string = 'Dev'
param rgName string = 'rg-dev-shared'
param subId string = 'e64069c2-4b14-4c32-a1f0-3493457f0eff'
param location string = 'eastus'
param workspaceName string = 'cdb-workspace-Dev'

output appiConnString string = appi.properties.ConnectionString
output appiInstKey string = appi.properties.InstrumentationKey
output appiResourceId string = appi.id

var appEnvName = '${appName}${envName}'
var workspaceId = '/subscriptions/${subId}/resourceGroups/${rgName}/providers/Microsoft.OperationalInsights/workspaces/${workspaceName}'

resource appi 'microsoft.insights/components@2020-02-02' = {
  name: 'appi${appEnvName}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    Flow_Type: 'Redfield'
    Request_Source: 'WebTools16.0'
    RetentionInDays: 90
    WorkspaceResourceId: workspaceId
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}
