param envName string = 'Dev'
param location string = 'eastus'
param adminUser string = 'cgfeadmin'
@secure()
param adminPassword string

var serverName = 'psql-db-cgfe-${toLower(envName)}'

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: serverName
  location: location
  sku: {
    name: envName == 'Prod' ? 'Standard_B2ms' : 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: adminUser
    administratorLoginPassword: adminPassword
    version: '16'
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
  }
}

resource pgvectorExtension 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgresServer
  name: 'azure.extensions'
  properties: {
    value: 'vector'
    source: 'user-override'
  }
}

resource allowAzureServices 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgresServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

output hostname string = postgresServer.properties.fullyQualifiedDomainName
output adminUser string = adminUser
@secure()
output liteLlmConnectionString string = 'postgresql://${adminUser}:${adminPassword}@${postgresServer.properties.fullyQualifiedDomainName}:5432/litellm?sslmode=require'
@secure()
output ragApiConnectionString string = 'postgresql://${adminUser}:${adminPassword}@${postgresServer.properties.fullyQualifiedDomainName}:5432/librechat_rag?sslmode=require'
