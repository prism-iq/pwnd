// API Configuration
export const API_URL = '/api';

// Query Parser - Natural Language DSL
const INTENT_PATTERNS: [RegExp, string][] = [
  [/^(find|show|search|list|get)\s+/i, 'SEARCH'],
  [/^(who|whom)\s+/i, 'WHO'],
  [/^(connections?|links?|relations?)\s+(between|from|to)/i, 'CONNECT'],
  [/^(when|timeline|dates?)\s+/i, 'TIMELINE'],
  [/^(count|how many|total)\s+/i, 'COUNT'],
];

const ENTITY_PATTERNS = {
  quoted: /"([^"]+)"/g,
  names: /\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b/g,
  emails: /\b[\w.-]+@[\w.-]+\.\w+\b/g,
  dates: /\b(\d{4}|\d{1,2}\/\d{1,2}\/\d{2,4}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})\b/gi,
  amounts: /\$[\d,]+(?:\.\d{2})?(?:[kmb])?/gi,
};

const FILTER_PATTERNS = {
  from: /\b(?:from|by|sent by)\s+([^\s,]+(?:\s+[A-Z][a-z]+)?)/i,
  to: /\b(?:to|sent to|recipient)\s+([^\s,]+(?:\s+[A-Z][a-z]+)?)/i,
  about: /\b(?:about|regarding|concerning|mentioning)\s+(.+?)(?:\s+(?:from|to|in|before|after|between)|$)/i,
  before: /\b(?:before|until|prior to)\s+(\d{4}|\d{1,2}\/\d{1,2}\/\d{2,4})/i,
  after: /\b(?:after|since|from)\s+(\d{4}|\d{1,2}\/\d{1,2}\/\d{2,4})/i,
  year: /\b(?:in|during)\s+(\d{4})\b/i,
};

export interface ParsedQuery {
  intent: string;
  raw: string;
  entities: string[];
  filters: Record<string, string>;
  searchTerms: string[];
}

export function parseQuery(query: string): ParsedQuery {
  const result: ParsedQuery = {
    intent: 'SEARCH',
    raw: query,
    entities: [],
    filters: {},
    searchTerms: [],
  };

  // Detect intent
  for (const [pattern, intent] of INTENT_PATTERNS) {
    if (pattern.test(query)) {
      result.intent = intent;
      break;
    }
  }

  // Extract entities
  const quoted = [...query.matchAll(ENTITY_PATTERNS.quoted)].map(m => m[1]);
  const names = [...query.matchAll(ENTITY_PATTERNS.names)].map(m => m[0]);
  const emails = [...query.matchAll(ENTITY_PATTERNS.emails)].map(m => m[0]);
  result.entities = [...new Set([...quoted, ...names, ...emails])];

  // Extract filters
  for (const [key, pattern] of Object.entries(FILTER_PATTERNS)) {
    const match = query.match(pattern);
    if (match) result.filters[key] = match[1];
  }

  // Build search terms
  let terms = query
    .replace(/"[^"]+"/g, '')  // Remove quoted
    .replace(/\b(find|show|search|list|get|who|whom|from|to|by|about|in|before|after|between|and|or|the|a|an)\b/gi, '')
    .split(/\s+/)
    .filter(t => t.length > 2);

  result.searchTerms = [...new Set([...result.entities, ...terms])].slice(0, 5);

  return result;
}

// SSE Stream Handler with error handling
export async function* streamQuery(query: string): AsyncGenerator<any> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/ask?q=${encodeURIComponent(query)}`);
  } catch (e) {
    yield { type: 'error', message: 'Network error - server unreachable' };
    return;
  }

  if (!response.ok) {
    yield { type: 'error', message: `Server error: ${response.status}` };
    return;
  }

  if (!response.body) {
    yield { type: 'error', message: 'No response body' };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            yield JSON.parse(line.slice(6));
          } catch {}
        }
      }
    }
  } catch (e) {
    yield { type: 'error', message: 'Stream interrupted' };
  }
}

// Fetch stats with error handling
export async function fetchStats() {
  try {
    const res = await fetch(`${API_URL}/stats`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

// Search with error handling
export async function search(q: string, limit = 20) {
  try {
    const res = await fetch(`${API_URL}/search?q=${encodeURIComponent(q)}&limit=${limit}`);
    if (!res.ok) return { results: [], error: `Server error: ${res.status}` };
    return res.json();
  } catch {
    return { results: [], error: 'Network error' };
  }
}
