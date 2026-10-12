import { createHash } from 'crypto';

export type JsonLike = string | number | boolean | null | JsonLike[] | { [key: string]: JsonLike };

export interface ContractTool {
  name: string;
  description: string;
  input_schema: JsonLike;
}

export interface ToolContract {
  contract_version: string;
  content_sha256: string;
  tools: ContractTool[];
}

export interface DiscoveredTool {
  name: string;
  description?: string;
  inputSchema: JsonLike;
}

/** A number kept as its source lexeme, so `300.0` is not re-serialized as `300`. */
class JsonNumber {
  constructor(readonly raw: string) {}
}

type LexemeValue =
  | string
  | boolean
  | null
  | JsonNumber
  | LexemeValue[]
  | { [key: string]: LexemeValue };

const NUMBER_PATTERN = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y;
// eslint-disable-next-line no-control-regex
const STRING_PATTERN = /"(?:[^"\\\u0000-\u001f]|\\.)*"/y;
const HASH_EXCLUDED_KEYS = new Set(['contract_version', 'content_sha256']);

function parseLexemes(text: string): LexemeValue {
  let pos = 0;

  const skip = (): void => {
    while (pos < text.length && ' \t\r\n'.includes(text[pos])) pos++;
  };
  const fail = (): never => {
    throw new Error(`Invalid contract JSON at offset ${pos}`);
  };
  const match = (pattern: RegExp): string | null => {
    pattern.lastIndex = pos;
    const found = pattern.exec(text);
    if (found == null) return null;
    pos += found[0].length;
    return found[0];
  };

  const parseValue = (): LexemeValue => {
    skip();
    const ch = text[pos];
    if (ch === '{') return parseObject();
    if (ch === '[') return parseArray();
    if (ch === '"') {
      const token = match(STRING_PATTERN);
      return token == null ? fail() : (JSON.parse(token) as string);
    }
    for (const [word, value] of [
      ['true', true],
      ['false', false],
      ['null', null],
    ] as const) {
      if (text.startsWith(word, pos)) {
        pos += word.length;
        return value;
      }
    }
    const raw = match(NUMBER_PATTERN);
    return raw == null ? fail() : new JsonNumber(raw);
  };

  const parseArray = (): LexemeValue[] => {
    const items: LexemeValue[] = [];
    pos++;
    skip();
    if (text[pos] === ']') {
      pos++;
      return items;
    }
    for (;;) {
      items.push(parseValue());
      skip();
      const next = text[pos++];
      if (next === ']') return items;
      if (next !== ',') fail();
    }
  };

  const parseObject = (): { [key: string]: LexemeValue } => {
    const entries: { [key: string]: LexemeValue } = {};
    pos++;
    skip();
    if (text[pos] === '}') {
      pos++;
      return entries;
    }
    for (;;) {
      skip();
      const token = match(STRING_PATTERN);
      if (token == null) fail();
      const key = JSON.parse(token as string) as string;
      skip();
      if (text[pos++] !== ':') fail();
      entries[key] = parseValue();
      skip();
      const next = text[pos++];
      if (next === '}') return entries;
      if (next !== ',') fail();
    }
  };

  const value = parseValue();
  skip();
  return pos === text.length ? value : fail();
}

const SHORT_ESCAPES: Record<string, string> = {
  '"': '\\"',
  '\\': '\\\\',
  '\n': '\\n',
  '\r': '\\r',
  '\t': '\\t',
  '\b': '\\b',
  '\f': '\\f',
};

/** Python `json.dumps(ensure_ascii=True)` string escaping. */
function escapeString(value: string): string {
  // eslint-disable-next-line no-control-regex
  const body = value.replace(/[\u0000-\u001f"\\\u007f-￿]/g, (ch) => {
    const code = ch.charCodeAt(0);
    if (SHORT_ESCAPES[ch] != null) return SHORT_ESCAPES[ch];
    if (code === 0x7f) return ch;
    return `\\u${code.toString(16).padStart(4, '0')}`;
  });
  return `"${body}"`;
}

/** Python `json.dumps(sort_keys=True, separators=(',', ':'))` over lexeme-preserving values. */
function canonicalize(value: LexemeValue): string {
  if (value === null) return 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'string') return escapeString(value);
  if (value instanceof JsonNumber) return value.raw;
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(',')}]`;
  const members = Object.keys(value)
    .sort()
    .map((key) => `${escapeString(key)}:${canonicalize(value[key])}`);
  return `{${members.join(',')}}`;
}

/**
 * Recomputes the generator's `content_sha256` from the contract file text: the SHA-256 of the canonical
 * JSON of everything except `contract_version` and `content_sha256` (see the MCP repo's tool_contract.py).
 */
export function computeContractHash(contractText: string): string {
  const parsed = parseLexemes(contractText);
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Contract must be a JSON object');
  }
  if (parsed instanceof JsonNumber) {
    throw new Error('Contract must be a JSON object');
  }
  const body = Object.fromEntries(
    Object.entries(parsed).filter(([key]) => !HASH_EXCLUDED_KEYS.has(key)),
  );
  return createHash('sha256').update(canonicalize(body)).digest('hex');
}

export function parseContract(contractText: string): ToolContract {
  const contract = JSON.parse(contractText) as ToolContract;
  const valid =
    typeof contract?.contract_version === 'string' &&
    typeof contract?.content_sha256 === 'string' &&
    Array.isArray(contract?.tools) &&
    contract.tools.every((t) => typeof t?.name === 'string' && t.input_schema != null);
  if (!valid) {
    throw new Error('Contract is missing contract_version, content_sha256 or tool schemas');
  }
  return contract;
}

/** Key-order-independent comparison form of a plain JSON value. */
export function stableStringify(value: JsonLike): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  const members = Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`);
  return `{${members.join(',')}}`;
}

/** Compares each discovered tool's description and argument schema with the contract. */
export function compareToolSchemas(contract: ToolContract, discovered: DiscoveredTool[]): string[] {
  const byName = new Map(discovered.map((t) => [t.name, t]));
  return contract.tools.flatMap((expected) => {
    const actual = byName.get(expected.name);
    if (actual == null) return [];
    const problems: string[] = [];
    if (stableStringify(actual.inputSchema) !== stableStringify(expected.input_schema)) {
      problems.push(`tool ${expected.name}: argument schema differs from the contract`);
    }
    if (actual.description !== expected.description) {
      problems.push(`tool ${expected.name}: description differs from the contract`);
    }
    return problems;
  });
}
