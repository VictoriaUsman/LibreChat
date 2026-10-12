import { logger } from '@librechat/data-schemas';
import { isolateInvalidMCPServers, sanitizeErrorMessage } from './isolate';

jest.mock('@librechat/data-schemas', () => ({
  logger: { error: jest.fn(), warn: jest.fn(), info: jest.fn(), debug: jest.fn() },
}));

const good = { type: 'streamable-http', url: 'https://mcp.internal.example/mcp' };

describe('isolateInvalidMCPServers', () => {
  beforeEach(() => jest.clearAllMocks());

  it('keeps a valid config untouched (same reference)', () => {
    const config = { version: '1.2.0', mcpServers: { 'romtech-cxone': good } };
    const result = isolateInvalidMCPServers(config);
    expect(result.config).toBe(config);
    expect(result.dropped).toEqual([]);
  });

  it.each([
    ['malformed URL', 'not a url'],
    ['unresolved placeholder', '${CXONE_MCP_URL_UNSET_IN_TEST}'],
    ['empty URL', ''],
  ])('drops only the bad server for %s and logs no value', (_label, url) => {
    const config = {
      version: '1.2.0',
      mcpServers: { 'romtech-cxone': { type: 'streamable-http', url }, other: good },
    };
    const result = isolateInvalidMCPServers(config);
    expect(Object.keys(result.config.mcpServers)).toEqual(['other']);
    expect(result.dropped).toEqual([{ serverName: 'romtech-cxone', category: 'invalid_url' }]);
    const logged = JSON.stringify((logger.error as jest.Mock).mock.calls);
    expect(logged).toContain('romtech-cxone');
    expect(logged).not.toContain('CXONE_MCP_URL_UNSET_IN_TEST');
    expect(logged).not.toContain('not a url');
  });

  it('classifies non-URL problems separately', () => {
    const result = isolateInvalidMCPServers({ mcpServers: { s: { type: 'carrier-pigeon' } } });
    expect(result.dropped).toEqual([{ serverName: 's', category: 'invalid_config' }]);
  });

  it('does not alter configs without mcpServers', () => {
    const config = { version: '1.2.0' };
    expect(isolateInvalidMCPServers(config).config).toBe(config);
  });
});

describe('sanitizeErrorMessage', () => {
  it('strips credential-bearing URLs and bounds length', () => {
    const msg = `connect failed https://user:secret@host.internal/mcp?token=abc ${'x'.repeat(500)}`;
    const out = sanitizeErrorMessage(msg);
    expect(out).not.toContain('secret');
    expect(out).not.toContain('token=abc');
    expect(out.length).toBeLessThanOrEqual(200);
  });
});
