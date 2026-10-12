import { logger } from '@librechat/data-schemas';
import { MCPOptionsSchema } from 'librechat-data-provider';

export type MCPConfigFailureCategory = 'invalid_url' | 'invalid_config';

export interface DroppedMCPServer {
  serverName: string;
  category: MCPConfigFailureCategory;
}

export interface IsolatedMCPConfig<T extends { mcpServers?: Record<string, unknown> }> {
  config: T;
  dropped: DroppedMCPServer[];
}

const MAX_LOGGED_MESSAGE_LENGTH = 200;
const URL_PATTERN = /[a-z][a-z0-9+.-]*:\/\/\S+/gi;

/** Bounded single-line message with every URL removed, safe for logs. */
export function sanitizeErrorMessage(message: string): string {
  return message
    .replace(URL_PATTERN, '[url]')
    .replace(/\s+/g, ' ')
    .slice(0, MAX_LOGGED_MESSAGE_LENGTH);
}

function hasUrlIssue(serverConfig: unknown): boolean {
  const parsed = MCPOptionsSchema.safeParse(serverConfig);
  return !parsed.success && parsed.error.issues.some((issue) => issue.path.includes('url'));
}

/** The schema's URL refinements can throw on a malformed URL instead of returning an issue. */
function categorize(serverConfig: unknown): MCPConfigFailureCategory | null {
  try {
    const parsed = MCPOptionsSchema.safeParse(serverConfig);
    if (parsed.success) {
      return null;
    }
    return hasUrlIssue(serverConfig) ? 'invalid_url' : 'invalid_config';
  } catch {
    return 'invalid_url';
  }
}

/**
 * Removes individually invalid `mcpServers` entries so one bad endpoint cannot fail
 * validation of the whole config. Reports name and category only, never values.
 * Everything outside `mcpServers` is left untouched and still fully validated.
 */
export function isolateInvalidMCPServers<T extends { mcpServers?: Record<string, unknown> }>(
  config: T,
): IsolatedMCPConfig<T> {
  const servers = config.mcpServers;
  if (servers == null || typeof servers !== 'object' || Array.isArray(servers)) {
    return { config, dropped: [] };
  }

  const kept: Record<string, unknown> = {};
  const dropped: DroppedMCPServer[] = [];
  for (const [serverName, serverConfig] of Object.entries(servers)) {
    const category = categorize(serverConfig);
    if (category == null) {
      kept[serverName] = serverConfig;
      continue;
    }
    dropped.push({ serverName, category });
    logger.error(`[MCP][${serverName}] Excluded from configuration: ${category}`);
  }

  if (dropped.length === 0) {
    return { config, dropped };
  }
  return { config: { ...config, mcpServers: kept }, dropped };
}
