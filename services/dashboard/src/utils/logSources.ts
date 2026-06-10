export type LogSourceGroup = 'services' | 'tests' | 'other'

export interface ParsedSource {
  raw:   string
  group: LogSourceGroup
  label: string
}

const SERVICE_NAMES = new Set([
  'advancer', 'claimer', 'evm-reader', 'validator',
  'jsonrpc-api', 'database', 'state-server',
])

/**
 * Parse a log source string into a group and human-readable label.
 * resultMap maps the short 8-char test result ID (after "test:") to a test slug.
 */
export function parseSource(
  src: string,
  resultMap: Map<string, string> = new Map(),
): ParsedSource {
  if (src.startsWith('test:')) {
    const shortId = src.slice(5)
    const label   = resultMap.get(shortId) ?? shortId
    return { raw: src, group: 'tests', label }
  }
  if (SERVICE_NAMES.has(src)) {
    return { raw: src, group: 'services', label: src }
  }
  return { raw: src, group: 'other', label: src }
}

export interface SourceGroups {
  services: ParsedSource[]
  tests:    ParsedSource[]
  other:    ParsedSource[]
}

/** Group and sort a set of raw source strings. */
export function groupSources(
  sources: string[],
  resultMap: Map<string, string> = new Map(),
): SourceGroups {
  const groups: SourceGroups = { services: [], tests: [], other: [] }
  for (const src of sources) {
    const parsed = parseSource(src, resultMap)
    groups[parsed.group].push(parsed)
  }
  const byLabel = (a: ParsedSource, b: ParsedSource) => a.label.localeCompare(b.label)
  groups.services.sort(byLabel)
  groups.tests.sort(byLabel)
  groups.other.sort(byLabel)
  return groups
}
