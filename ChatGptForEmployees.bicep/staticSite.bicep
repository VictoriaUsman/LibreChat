// Azure Static Web App (Free) hosting the ROMTech AI user Help / FAQ page.
//
// bicep only CREATES the site — there is no `az` command to push content to a SWA.
// The page content (ChatGptForEmployees.docs/romtech_ai_help.html, deployed as
// index.html) is pushed by the pipeline's `DeployHelpPage` stage using the SWA
// deployment token + the Static Web Apps CLI (`swa deploy`). See dev/test/prod.yml.
//
// PUBLIC by design — the help page contains only generic, non-sensitive usage guidance.
// The URL (defaultHostname) is wired into LibreChat's HELP_AND_FAQ_URL + CUSTOM_FOOTER
// via main.bicep -> libreChat.bicep (helpUrl param), so no manual URL wiring is needed.

param envName string = 'Dev'
// SWA resources only deploy to specific control-plane regions (eastus2 is one).
// Kept independent of the general `location` so a region change elsewhere can't
// push the SWA into an unsupported region.
param location string = 'eastus2'

var swaName = 'swa-cgfe-${toLower(envName)}'

resource staticSite 'Microsoft.Web/staticSites@2023-12-01' = {
  name: swaName
  location: location
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  // No linked repo — content is pushed manually by the pipeline via the deploy token.
  properties: {}
}

output name string = staticSite.name
output defaultHostname string = staticSite.properties.defaultHostname
