/** Reject duplicate object keys before JSON.parse can silently overwrite them. */
export function parseParameterJson(source: string): Record<string, unknown> {
  const value: unknown = JSON.parse(source);
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Object required');
  const tokens = source.match(/"(?:[^"\\]|\\.)*"|[{}\[\],:]|[^\s{}\[\],:]+/g) ?? [];
  let position = 0;
  function visit(): void {
    const token = tokens[position++];
    if (token === '{') {
      const keys = new Set<string>();
      if (tokens[position] === '}') { position++; return; }
      do {
        const key = JSON.parse(tokens[position++]) as string;
        if (keys.has(key)) throw new Error('Duplicate parameter');
        keys.add(key); position++; visit();
      } while (tokens[position++] === ',');
    } else if (token === '[') {
      if (tokens[position] === ']') { position++; return; }
      do { visit(); } while (tokens[position++] === ',');
    }
  }
  visit();
  return value as Record<string, unknown>;
}
