const fs = require('fs');
const path = require('path');
const mongoose = require('mongoose');
const { logger } = require('@librechat/data-schemas');
const { provisionCxoneAgent, validateManifest } = require('@librechat/api');
const { Constants, ResourceType } = require('librechat-data-provider');

require('module-alias')({ base: path.resolve(__dirname, '..', 'api') });
const connect = require('./connect');

const { grantPermission } = require('~/server/services/PermissionService');
const initializeMCPs = require('~/server/services/initializeMCPs');
const { getMCPManager } = require('~/config');
const { Agent, AclEntry, AccessRole } = require('~/db/models');
const { createAgent, updateAgent } = require('~/models');

/**
 * Operator-only: creates/updates the CXOne agent without the agent builder.
 *   node config/provision-cxone-agent.js --manifest <file> [--dry-run | --apply] \
 *     --contract <contract.json> --instructions <claim-instructions.md>
 * Credentials come from the deployment environment, never from arguments.
 */
function parseArgs(argv) {
  const args = { apply: false };
  for (let i = 2; i < argv.length; i++) {
    const flag = argv[i];
    if (flag === '--apply') args.apply = true;
    else if (flag === '--dry-run') args.apply = false;
    else if (['--manifest', '--contract', '--instructions'].includes(flag)) args[flag.slice(2)] = argv[++i];
    else throw new Error(`Unknown argument: ${flag}`);
  }
  const missing = ['manifest', 'contract', 'instructions'].filter((k) => !args[k]);
  if (missing.length > 0) throw new Error(`Missing required argument(s): ${missing.map((m) => `--${m}`).join(', ')}`);
  return args;
}

const readJson = (file) => JSON.parse(fs.readFileSync(file, 'utf8'));

async function discoverTools(serverName) {
  await initializeMCPs();
  const suffix = `${Constants.mcp_delimiter}${serverName}`;
  const functions = (await getMCPManager().getAppToolFunctions()) || {};
  return Object.keys(functions)
    .filter((key) => key.endsWith(suffix))
    .map((key) => key.slice(0, -suffix.length));
}

async function getAgentObjectId(id) {
  const agent = await Agent.findOne({ id }).select('_id').lean();
  if (!agent) throw new Error('Agent not found for ACL operation');
  return agent._id;
}

function createDeps() {
  return {
    findAgentsByIdOrName: (id, name) => Agent.find({ $or: [{ id }, { name }] }).lean(),
    createAgent: (data) => createAgent(data),
    updateAgent: (id, data) => updateAgent({ id }, data, { forceVersion: true }),
    getAcl: async (id) => {
      const resourceId = await getAgentObjectId(id);
      const entries = await AclEntry.find({ resourceType: ResourceType.AGENT, resourceId }).lean();
      const roles = await AccessRole.find({ _id: { $in: entries.map((e) => e.roleId) } }).lean();
      const roleById = new Map(roles.map((r) => [String(r._id), r.accessRoleId]));
      return entries.map((e) => ({
        principalType: e.principalType,
        principalId: String(e.principalId),
        accessRoleId: roleById.get(String(e.roleId)) ?? 'unknown',
      }));
    },
    grant: async ({ agentId, principalType, principalId, accessRoleId, grantedBy }) =>
      grantPermission({
        principalType,
        principalId,
        resourceType: ResourceType.AGENT,
        resourceId: await getAgentObjectId(agentId),
        accessRoleId,
        grantedBy,
      }),
  };
}

async function main() {
  const args = parseArgs(process.argv);
  const manifest = validateManifest(readJson(args.manifest));
  const contract = readJson(args.contract);
  const instructionsMarkdown = fs.readFileSync(args.instructions, 'utf8');

  await connect();
  const discoveredTools = await discoverTools(manifest.mcpServerName);
  const result = await provisionCxoneAgent(
    { manifest, contract, discoveredTools, instructionsMarkdown, apply: args.apply },
    createDeps(),
  );
  console.log(JSON.stringify({ mode: args.apply ? 'apply' : 'dry-run', ...result }, null, 2));
  await mongoose.disconnect();
}

main().catch((error) => {
  logger.error(`[provision-cxone-agent] ${error.message}`);
  process.exit(1);
});
