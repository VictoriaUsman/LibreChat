import { z } from 'zod';
import { createHash } from 'crypto';
import { Constants, EToolResources, PrincipalType, AccessRoleIds } from 'librechat-data-provider';
import type { ToolContract, DiscoveredTool } from './contract';
import { computeContractHash, compareToolSchemas, parseContract } from './contract';

const SHA256 = /^[a-f0-9]{64}$/;
const PROVISIONING_KEY = /^[a-z0-9][a-z0-9-]{2,63}$/;
const INSTRUCTION_HEADING = '## Instruction text';
const AGENT_ID_PREFIX = 'agent_';
const AGENT_ID_HASH_LENGTH = 21;

const principalSchema = z.object({
  type: z.enum(['user', 'group', 'role']),
  id: z.string().min(1),
});

export const manifestSchema = z.object({
  environment: z.string().min(1),
  provisioningKey: z.string().regex(PROVISIONING_KEY),
  owner: z.object({ id: z.string().min(1) }),
  audience: z.array(principalSchema).min(1),
  provider: z.string().min(1),
  model: z.string().min(1),
  mcpServerName: z.string().min(1),
  contract: z.object({ version: z.string().min(1), sha256: z.string().regex(SHA256) }),
  instructions: z.object({
    version: z.number().int().positive(),
    sha256: z.string().regex(SHA256),
  }),
  maxContextTokens: z.number().int().positive(),
  name: z.string().min(1).default('ROMChat CXOne'),
  description: z
    .string()
    .default('Read-only CXOne contact-center reporting for approved ROMChat users.'),
});

export type CxoneAgentManifest = z.infer<typeof manifestSchema>;
export type ManifestPrincipal = z.infer<typeof principalSchema>;

export interface AgentAclEntry {
  principalType: string;
  principalId: string;
  accessRoleId: string;
}

export type ModelParameters = { maxContextTokens?: number } & Record<
  string,
  string | number | boolean | undefined
>;

export type AgentUpdate = Omit<DesiredAgent, 'id' | 'model_parameters'> & {
  model_parameters: ModelParameters;
};

export interface ProvisionedAgent {
  id: string;
  name?: string;
  description?: string;
  instructions?: string;
  provider: string;
  model: string;
  model_parameters?: ModelParameters;
  tools?: string[];
}

export interface DesiredAgent {
  id: string;
  name: string;
  description: string;
  instructions: string;
  provider: string;
  model: string;
  model_parameters: { model: string; maxContextTokens: number };
  tools: string[];
}

export interface ProvisionDeps {
  findAgentsByIdOrName: (id: string, name: string) => Promise<ProvisionedAgent[]>;
  createAgent: (data: DesiredAgent & { author: string }) => Promise<ProvisionedAgent>;
  updateAgent: (id: string, data: AgentUpdate) => Promise<ProvisionedAgent | null>;
  getAcl: (agentId: string) => Promise<AgentAclEntry[]>;
  grant: (entry: AgentAclEntry & { agentId: string; grantedBy: string }) => Promise<void>;
  revoke: (entry: AgentAclEntry & { agentId: string }) => Promise<void>;
  principalExists: (principalType: string, principalId: string) => Promise<boolean>;
}

export interface ProvisionInput {
  manifest: CxoneAgentManifest;
  /** Raw contract file text; the hash is recomputed from it, never trusted from the file or manifest. */
  contractText: string;
  discoveredTools: DiscoveredTool[];
  instructionsMarkdown: string;
  apply: boolean;
}

export type ProvisionAction = 'create' | 'update' | 'no-change';

export interface ProvisionResult {
  action: ProvisionAction;
  applied: boolean;
  agentId: string;
  changedFields: string[];
  aclGrants: number;
  fingerprint: string;
}

const sha256 = (text: string): string => createHash('sha256').update(text).digest('hex');

const principalTypes: Record<ManifestPrincipal['type'], PrincipalType> = {
  user: PrincipalType.USER,
  group: PrincipalType.GROUP,
  role: PrincipalType.ROLE,
};

export function validateManifest(raw: unknown): CxoneAgentManifest {
  const parsed = manifestSchema.safeParse(raw);
  if (parsed.success) {
    return parsed.data;
  }
  const issues = parsed.error.issues.map((i) => `${i.path.join('.') || '(root)'}: ${i.message}`);
  throw new Error(`Invalid provisioning manifest: ${issues.join('; ')}`);
}

/** Deterministic ID so repeated runs address the same agent and a display-name match is never trusted. */
export function agentIdForKey(provisioningKey: string): string {
  return `${AGENT_ID_PREFIX}${sha256(`romchat-provision:${provisioningKey}`).slice(0, AGENT_ID_HASH_LENGTH)}`;
}

export function mcpToolId(serverName: string, toolName: string): string {
  return `${toolName}${Constants.mcp_delimiter}${serverName}`;
}

export function extractInstructionText(markdown: string): string {
  const normalized = markdown.replace(/\r\n/g, '\n');
  const start = normalized.indexOf(INSTRUCTION_HEADING);
  if (start === -1) {
    throw new Error(`Instruction file has no "${INSTRUCTION_HEADING}" section`);
  }
  const body = normalized.slice(normalized.indexOf('\n', start) + 1);
  const end = body.search(/^## /m);
  const text = (end === -1 ? body : body.slice(0, end)).trim();
  if (!text) {
    throw new Error('Instruction text section is empty');
  }
  return text;
}

export function verifyContract(
  manifest: CxoneAgentManifest,
  contractText: string,
  discoveredTools: DiscoveredTool[],
): string[] {
  const contract = parseContract(contractText);
  const problems: string[] = [];
  const computedHash = computeContractHash(contractText);
  if (contract.contract_version !== manifest.contract.version) {
    problems.push(
      `contract version ${contract.contract_version} does not match manifest ${manifest.contract.version}`,
    );
  }
  if (computedHash !== contract.content_sha256) {
    problems.push(
      'contract file content does not match its own content_sha256 (edited or corrupt)',
    );
  }
  if (computedHash !== manifest.contract.sha256) {
    problems.push('recomputed contract hash does not match manifest');
  }
  const expected = contract.tools.map((t) => t.name).sort();
  const actual = discoveredTools.map((t) => t.name).sort();
  const missing = expected.filter((t) => !actual.includes(t));
  const extra = actual.filter((t) => !expected.includes(t));
  if (missing.length > 0) {
    problems.push(`server is missing contract tools: ${missing.join(', ')}`);
  }
  if (extra.length > 0) {
    problems.push(`server exposes tools outside the contract: ${extra.join(', ')}`);
  }
  return [...problems, ...compareToolSchemas(contract, discoveredTools)];
}

export function buildDesiredAgent(
  manifest: CxoneAgentManifest,
  contract: ToolContract,
  instructions: string,
): DesiredAgent {
  const mcpTools = contract.tools.map((t) => mcpToolId(manifest.mcpServerName, t.name)).sort();
  return {
    id: agentIdForKey(manifest.provisioningKey),
    name: manifest.name,
    description: manifest.description,
    instructions,
    provider: manifest.provider,
    model: manifest.model,
    model_parameters: { model: manifest.model, maxContextTokens: manifest.maxContextTokens },
    tools: [...mcpTools, EToolResources.file_search],
  };
}

const sameSet = (a: string[] = [], b: string[] = []): boolean =>
  a.length === b.length && [...a].sort().every((v, i) => v === [...b].sort()[i]);

export function diffAgent(existing: ProvisionedAgent, desired: DesiredAgent): string[] {
  const changed: string[] = [];
  if (existing.name !== desired.name) changed.push('name');
  if (existing.instructions !== desired.instructions) changed.push('instructions');
  if (existing.provider !== desired.provider) changed.push('provider');
  if (existing.model !== desired.model) changed.push('model');
  if (existing.model_parameters?.maxContextTokens !== desired.model_parameters.maxContextTokens) {
    changed.push('model_parameters.maxContextTokens');
  }
  if (existing.model_parameters?.model !== desired.model_parameters.model) {
    changed.push('model_parameters.model');
  }
  if (hasUnexpectedParameters(existing.model_parameters, desired.model_parameters)) {
    changed.push('model_parameters.extra');
  }
  if (!sameSet(existing.tools, desired.tools)) changed.push('tools');
  return changed;
}

/** Parameters beyond the manifest's (e.g. a stray temperature) change how the agent runs, so they are drift. */
function hasUnexpectedParameters(
  existing: ModelParameters | undefined,
  desired: DesiredAgent['model_parameters'],
): boolean {
  const wanted = new Set(Object.keys(desired));
  return Object.entries(existing ?? {}).some(
    ([key, value]) => value !== undefined && !wanted.has(key),
  );
}

export function desiredAcl(manifest: CxoneAgentManifest): AgentAclEntry[] {
  const owner: AgentAclEntry = {
    principalType: PrincipalType.USER,
    principalId: manifest.owner.id,
    accessRoleId: AccessRoleIds.AGENT_OWNER,
  };
  const viewers = manifest.audience.map((p) => ({
    principalType: principalTypes[p.type],
    principalId: p.id,
    accessRoleId: AccessRoleIds.AGENT_VIEWER,
  }));
  return [owner, ...viewers.filter((v) => v.principalId !== owner.principalId)];
}

const aclKey = (e: AgentAclEntry): string => `${e.principalType}:${e.principalId}`;

export function diffAcl(
  current: AgentAclEntry[],
  desired: AgentAclEntry[],
): { missing: AgentAclEntry[]; unexpected: AgentAclEntry[] } {
  const byKey = new Map(current.map((e) => [aclKey(e), e]));
  const wanted = new Map(desired.map((e) => [aclKey(e), e]));
  const missing = desired.filter((e) => byKey.get(aclKey(e))?.accessRoleId !== e.accessRoleId);
  const unexpected = current.filter((e) => !wanted.has(aclKey(e)));
  return { missing, unexpected };
}

export function fingerprintAgent(desired: DesiredAgent, acl: AgentAclEntry[]): string {
  const aclSummary = acl.map((e) => `${aclKey(e)}=${e.accessRoleId}`).sort();
  return sha256(
    JSON.stringify({ ...desired, instructions: sha256(desired.instructions), acl: aclSummary }),
  );
}

function chooseAction(
  existing: ProvisionedAgent | undefined,
  changedFields: string[],
): ProvisionAction {
  if (!existing) return 'create';
  return changedFields.length > 0 ? 'update' : 'no-change';
}

/**
 * Creates or updates the CXOne agent and its ACLs without the agent builder.
 * Fails closed on contract mismatch, ambiguous matches and ACL drift; safe to re-run.
 */
export async function provisionCxoneAgent(
  input: ProvisionInput,
  deps: ProvisionDeps,
): Promise<ProvisionResult> {
  const { manifest, contractText, discoveredTools, instructionsMarkdown, apply } = input;

  const problems = verifyContract(manifest, contractText, discoveredTools);
  if (problems.length > 0) {
    throw new Error(`Contract verification failed: ${problems.join('; ')}`);
  }
  const contract = parseContract(contractText);

  const instructions = extractInstructionText(instructionsMarkdown);
  if (sha256(instructions) !== manifest.instructions.sha256) {
    throw new Error('Instruction text hash does not match manifest');
  }

  const desired = buildDesiredAgent(manifest, contract, instructions);
  const matches = await deps.findAgentsByIdOrName(desired.id, desired.name);
  const strangers = matches.filter((a) => a.id !== desired.id);
  if (strangers.length > 0) {
    throw new Error(
      `Ambiguous match: ${strangers.length} other agent(s) already use the name "${desired.name}"`,
    );
  }

  const existing = matches[0];
  const wantedAcl = desiredAcl(manifest);
  const checks = await Promise.all(
    wantedAcl.map((e) => deps.principalExists(e.principalType, e.principalId)),
  );
  const unknownPrincipals = wantedAcl.filter((_, i) => !checks[i]);
  if (unknownPrincipals.length > 0) {
    const labels = unknownPrincipals.map((e) => aclKey(e));
    throw new Error(`Unknown owner/audience principal(s), nothing written: ${labels.join(', ')}`);
  }
  const currentAcl = existing ? await deps.getAcl(existing.id) : [];
  const aclDiff = diffAcl(currentAcl, wantedAcl);
  if (aclDiff.unexpected.length > 0) {
    throw new Error(
      `ACL drift: ${aclDiff.unexpected.length} principal(s) have access outside the manifest; revoke them first`,
    );
  }

  const changedFields = existing ? diffAgent(existing, desired) : ['(new agent)'];
  const action = chooseAction(existing, changedFields);
  const fingerprint = fingerprintAgent(desired, wantedAcl);
  const result: ProvisionResult = {
    action,
    applied: false,
    agentId: desired.id,
    changedFields: action === 'no-change' ? [] : changedFields,
    aclGrants: aclDiff.missing.length,
    fingerprint,
  };
  if (!apply) {
    return result;
  }

  /** Owner first, audience last: until the final grant lands, ordinary users have no access. */
  const grants = [...aclDiff.missing].sort(
    (a, b) =>
      Number(b.accessRoleId === AccessRoleIds.AGENT_OWNER) -
      Number(a.accessRoleId === AccessRoleIds.AGENT_OWNER),
  );
  const granted: AgentAclEntry[] = [];
  try {
    if (action === 'create') {
      await deps.createAgent({ ...desired, author: manifest.owner.id });
    }
    if (action === 'update') {
      const { id: _id, ...update } = desired;
      await deps.updateAgent(desired.id, update);
    }
    for (const entry of grants) {
      await deps.grant({ ...entry, agentId: desired.id, grantedBy: manifest.owner.id });
      granted.push(entry);
    }
    await verifyReadBack(deps, desired, wantedAcl);
  } catch (error) {
    const rollback = await rollbackRun(
      deps,
      desired,
      existing,
      granted,
      currentAcl,
      manifest.owner.id,
    );
    const reason = error instanceof Error ? error.message : String(error);
    throw new Error(`${reason}. Rollback: ${rollback}`);
  }
  return { ...result, applied: true };
}

async function verifyReadBack(
  deps: ProvisionDeps,
  desired: DesiredAgent,
  wantedAcl: AgentAclEntry[],
): Promise<void> {
  const readBack = (await deps.findAgentsByIdOrName(desired.id, desired.name)).find(
    (a) => a.id === desired.id,
  );
  const remaining = readBack ? diffAgent(readBack, desired) : ['(missing after write)'];
  const aclAfter = diffAcl(await deps.getAcl(desired.id), wantedAcl);
  if (remaining.length > 0 || aclAfter.missing.length > 0 || aclAfter.unexpected.length > 0) {
    throw new Error(
      `Read-back verification failed: fields=[${remaining.join(', ')}] missingAcl=${aclAfter.missing.length} unexpectedAcl=${aclAfter.unexpected.length}`,
    );
  }
}

/**
 * Undoes this run's grants (audience first) and restores a pre-existing agent's prior fields. A newly
 * created agent is left with at most owner access, so it stays unavailable to the audience.
 */
async function rollbackRun(
  deps: ProvisionDeps,
  desired: DesiredAgent,
  existing: ProvisionedAgent | undefined,
  granted: AgentAclEntry[],
  priorAcl: AgentAclEntry[],
  grantedBy: string,
): Promise<string> {
  const failures: string[] = [];
  const attempt = async (label: string, step: () => Promise<unknown>): Promise<void> => {
    try {
      await step();
    } catch {
      failures.push(label);
    }
  };

  const audienceFirst = [...granted].reverse();
  const priorByKey = new Map(priorAcl.map((e) => [aclKey(e), e]));
  for (const entry of audienceFirst) {
    const prior = priorByKey.get(aclKey(entry));
    if (prior != null) {
      await attempt(`restore ${aclKey(entry)}`, () =>
        deps.grant({ ...prior, agentId: desired.id, grantedBy }),
      );
      continue;
    }
    await attempt(`revoke ${aclKey(entry)}`, () => deps.revoke({ ...entry, agentId: desired.id }));
  }
  if (existing != null) {
    await attempt('restore previous agent fields', () =>
      deps.updateAgent(desired.id, {
        name: existing.name ?? desired.name,
        description: existing.description ?? desired.description,
        instructions: existing.instructions ?? '',
        provider: existing.provider,
        model: existing.model,
        model_parameters: { ...(existing.model_parameters ?? desired.model_parameters) },
        tools: existing.tools ?? [],
      }),
    );
  }
  const scope =
    existing == null
      ? 'new agent left with no access grants, unavailable'
      : 'previous version restored';
  if (failures.length > 0) {
    return `incomplete, manual review needed for: ${failures.join(', ')}`;
  }
  return `completed (${scope})`;
}
