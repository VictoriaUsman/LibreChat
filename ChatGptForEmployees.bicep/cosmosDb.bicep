param envName string = 'Dev'
param location string = 'eastus'

var accountName = 'cosmos-cgfe-${toLower(envName)}'

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: accountName
  location: location
  kind: 'MongoDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [
      { name: 'EnableMongo' }
      { name: 'EnableServerless' }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    apiProperties: {
      serverVersion: '4.2'
    }
    // Serverless doesn't support Continuous backup (true PITR) — only Periodic.
    // 30-day retention (720 h) is the maximum available on Serverless.
    backupPolicy: {
      type: 'Periodic'
      periodicModeProperties: {
        backupIntervalInMinutes: 240
        backupRetentionIntervalInHours: 720
        backupStorageRedundancy: 'Local'
      }
    }
  }
}

var primaryKey = cosmosAccount.listKeys().primaryMasterKey

@secure()
output connectionString string = 'mongodb://${accountName}:${primaryKey}@${accountName}.mongo.cosmos.azure.com:10255/LibreChat?ssl=true&retrywrites=false&maxIdleTimeMS=120000&appName=@${accountName}@'
