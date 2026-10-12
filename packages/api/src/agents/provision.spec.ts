import { createHash } from 'crypto';
import { Constants } from 'librechat-data-provider';
import type {
  ToolContract,
  AgentAclEntry,
  ProvisionDeps,
  DesiredAgent,
  ProvisionedAgent,
} from './provision';
import {
  agentIdForKey,
  mcpToolId,
  validateManifest,
  extractInstructionText,
  verifyContract,
  provisionCxoneAgent,
} from './provision';

const sha = (t: string) => createHash('sha256').update(t).digest('hex');
const INSTRUCTIONS = 'CXOne reporting rules.\n1. State the interval.';
const MARKDOWN = `---\nversion: 1\n---\n\n# Title\n\n## Instruction text (paste as written)\n\n${INSTRUCTIONS}\n\n## Not part of the instruction text\n\nnotes`;
const contract: ToolContract = {
  contract_version: '1.1.0',
  content_sha256: 'b'.repeat(64),
  tools: [{ name: 'compare_periods' }, { name: 'drill_down' }, { name: 'current_state' }],
};
const tools = ['compare_periods', 'drill_down', 'current_state'];
const manifestRaw = {
  environment: 'dev',
  provisioningKey: 'romchat-cxone',
  owner: { id: 'owner1' },
  audience: [{ type: 'group', id: 'grp1' }],
  provider: 'LiteLLM Gateway',
  model: 'ROMTech AI Standard',
  mcpServerName: 'romtech-cxone',
  contract: { version: '1.1.0', sha256: 'b'.repeat(64) },
  instructions: { version: 1, sha256: sha(INSTRUCTIONS) },
  maxContextTokens: 128000,
};

function fakeDeps() {
  const agents = new Map<string, ProvisionedAgent>();
  const acl = new Map<string, AgentAclEntry[]>();
  const deps: ProvisionDeps = {
    findAgentsByIdOrName: async (id, name) =>
      [...agents.values()].filter((a) => a.id === id || a.name === name),
    createAgent: async (data) => {
      const { author: _author, ...agent } = data;
      agents.set(agent.id, agent);
      return agent;
    },
    updateAgent: async (id, data) => {
      const next = { ...agents.get(id), id, ...data } as ProvisionedAgent;
      agents.set(id, next);
      return next;
    },
    getAcl: async (id) => acl.get(id) ?? [],
    grant: async ({ agentId, ...entry }) => {
      const { grantedBy: _g, ...e } = entry;
      acl.set(agentId, [
        ...(acl.get(agentId) ?? []).filter((x) => x.principalId !== e.principalId),
        e,
      ]);
    },
  };
  return { deps, agents, acl };
}

const run = (apply: boolean, deps: ProvisionDeps, raw: unknown = manifestRaw) =>
  provisionCxoneAgent(
    {
      manifest: validateManifest(raw),
      contract,
      discoveredTools: tools,
      instructionsMarkdown: MARKDOWN,
      apply,
    },
    deps,
  );

describe('provisionCxoneAgent', () => {
  it('uses LibreChat MCP tool namespacing and a deterministic id', () => {
    expect(mcpToolId('romtech-cxone', 'drill_down')).toBe(
      `drill_down${Constants.mcp_delimiter}romtech-cxone`,
    );
    expect(agentIdForKey('romchat-cxone')).toBe(agentIdForKey('romchat-cxone'));
    expect(agentIdForKey('a-key')).not.toBe(agentIdForKey('b-key'));
  });

  it('extracts only the instruction section', () => {
    expect(extractInstructionText(MARKDOWN)).toBe(INSTRUCTIONS);
    expect(() => extractInstructionText('no section')).toThrow('Instruction text');
  });

  it('rejects an invalid manifest without leaking values', () => {
    expect(() => validateManifest({ ...manifestRaw, maxContextTokens: -1 })).toThrow(
      /maxContextTokens/,
    );
    expect(() => validateManifest({ ...manifestRaw, audience: [] })).toThrow(/audience/);
  });

  it('flags contract mismatch and extra/missing tools', () => {
    const m = validateManifest(manifestRaw);
    expect(verifyContract(m, contract, tools)).toEqual([]);
    expect(verifyContract(m, contract, ['drill_down', 'rogue']).join()).toMatch(
      /missing.*rogue|rogue/,
    );
    expect(verifyContract(m, { ...contract, content_sha256: 'c'.repeat(64) }, tools)[0]).toMatch(
      /hash/,
    );
  });

  it('dry run changes nothing', async () => {
    const { deps, agents } = fakeDeps();
    const r = await run(false, deps);
    expect(r).toMatchObject({ action: 'create', applied: false });
    expect(agents.size).toBe(0);
  });

  it('creates once with MCP tools, file_search, 128000 cap and ACLs; rerun is a no-op', async () => {
    const { deps, agents, acl } = fakeDeps();
    const first = await run(true, deps);
    expect(first).toMatchObject({ action: 'create', applied: true });
    const agent = agents.get(first.agentId) as DesiredAgent;
    expect(agent.tools).toEqual([
      'compare_periods_mcp_romtech-cxone',
      'current_state_mcp_romtech-cxone',
      'drill_down_mcp_romtech-cxone',
      'file_search',
    ]);
    expect(agent.model_parameters.maxContextTokens).toBe(128000);
    expect(acl.get(first.agentId)).toHaveLength(2);

    const second = await run(true, deps);
    expect(second).toMatchObject({
      action: 'no-change',
      aclGrants: 0,
      fingerprint: first.fingerprint,
    });
    expect(agents.size).toBe(1);
  });

  it('updates drifted fields in place', async () => {
    const { deps, agents } = fakeDeps();
    const first = await run(true, deps);
    agents.set(first.agentId, { ...agents.get(first.agentId)!, tools: ['file_search'] });
    const r = await run(true, deps);
    expect(r).toMatchObject({ action: 'update', changedFields: ['tools'] });
  });

  it('fails on an agent with the same name but a different id', async () => {
    const { deps, agents } = fakeDeps();
    agents.set('agent_other', {
      id: 'agent_other',
      name: 'ROMChat CXOne',
      provider: 'x',
      model: 'y',
    });
    await expect(run(true, deps)).rejects.toThrow('Ambiguous match');
  });

  it('refuses to apply when someone outside the manifest has access', async () => {
    const { deps, acl } = fakeDeps();
    const first = await run(true, deps);
    acl.set(first.agentId, [
      ...(acl.get(first.agentId) ?? []),
      { principalType: 'user', principalId: 'stranger', accessRoleId: 'agent_viewer' },
    ]);
    await expect(run(true, deps)).rejects.toThrow('ACL drift');
  });

  it('fails when the instruction hash differs', async () => {
    const { deps } = fakeDeps();
    const raw = { ...manifestRaw, instructions: { version: 1, sha256: 'd'.repeat(64) } };
    await expect(run(true, deps, raw)).rejects.toThrow('Instruction text hash');
  });

  it('fails read-back verification when a write is silently lost', async () => {
    const { deps } = fakeDeps();
    deps.grant = async () => undefined;
    await expect(run(true, deps)).rejects.toThrow('Read-back verification failed');
  });
});
