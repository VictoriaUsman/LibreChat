import type { AppConfig } from '@librechat/data-schemas';
import type { AgentModelParameters } from 'librechat-data-provider';
import type { LoadAgentDeps } from './load';
import { selectableEphemeralServers } from '~/mcp/utils';
import { loadEphemeralAgent } from './load';

const mcpConfig = {
  'romtech-cxone': {
    type: 'streamable-http',
    url: 'https://mcp.internal.example/mcp',
    chatMenu: false,
  },
  open: { type: 'streamable-http', url: 'https://open.internal.example/mcp' },
} as AppConfig['mcpConfig'];

describe('selectableEphemeralServers', () => {
  it('drops servers configured with chatMenu: false and keeps the rest', () => {
    const result = selectableEphemeralServers(['romtech-cxone', 'open', 'unknown'], mcpConfig);
    expect([...result].sort()).toEqual(['open', 'unknown']);
  });

  it('handles missing input and config', () => {
    expect(selectableEphemeralServers(undefined, mcpConfig).size).toBe(0);
    expect([...selectableEphemeralServers(['a'], undefined)]).toEqual(['a']);
  });
});

describe('loadEphemeralAgent MCP selection', () => {
  const getMCPServerTools = jest.fn(async (_user: string, server: string) => ({
    [`tool_mcp_${server}`]: {},
  }));
  const deps: LoadAgentDeps = { getAgent: jest.fn(), getMCPServerTools };
  const load = (ephemeralMcp: string[], spec?: string, modelSpecs?: unknown) =>
    loadEphemeralAgent(
      {
        req: {
          user: { id: 'u1' },
          config: { mcpConfig, modelSpecs, endpoints: {} } as unknown as AppConfig,
          body: { ephemeralAgent: { mcp: ephemeralMcp } },
        },
        spec,
        endpoint: 'agents',
        model_parameters: { model: 'm' } as AgentModelParameters & { model?: string },
      },
      deps,
    );

  beforeEach(() => getMCPServerTools.mockClear());

  it('does not bind a chatMenu:false server requested by the client', async () => {
    const agent = await load(['romtech-cxone', 'open']);
    expect(agent?.tools).toEqual(['tool_mcp_open']);
    expect(getMCPServerTools).not.toHaveBeenCalledWith('u1', 'romtech-cxone');
  });

  it('still binds a chatMenu:false server that an admin put on the modelSpec', async () => {
    const specs = { list: [{ name: 's', mcpServers: ['romtech-cxone'] }] };
    const agent = await load([], 's', specs);
    expect(agent?.tools).toEqual(['tool_mcp_romtech-cxone']);
  });
});
