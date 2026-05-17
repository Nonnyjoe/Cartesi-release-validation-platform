import { useEffect, useState, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { format } from 'date-fns'
import { testsApi } from '../api'
import type { TestDefinition } from '../types'

marked.use({ gfm: true })

const PRIORITY_BADGE: Record<string, string> = {
  critical: 'bg-rvp-error/20 text-rvp-error',
  high:     'bg-rvp-warning/20 text-rvp-warning',
  medium:   'bg-rvp-info/20 text-rvp-info',
  low:      'bg-gray-700 text-gray-400',
}

/** Split "---\nfrontmatter\n---\nbody" into its two parts. */
function splitDefinition(raw: string): { yaml: string; body: string } {
  const match = raw.match(/^---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|$)([\s\S]*)$/s)
  if (!match) return { yaml: '', body: raw }
  return { yaml: match[1].trim(), body: match[2].trim() }
}

export default function TestDetail() {
  const { testId } = useParams<{ testId: string }>()
  const [def, setDef]         = useState<TestDefinition | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')
  const [copied, setCopied]   = useState(false)

  useEffect(() => {
    if (!testId) return
    testsApi.get(testId)
      .then(setDef)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [testId])

  const { yaml, body } = useMemo(
    () => def ? splitDefinition(def.definition_raw) : { yaml: '', body: '' },
    [def]
  )

  const renderedMd = useMemo(() => {
    if (!body) return ''
    const html = marked.parse(body) as string
    return DOMPurify.sanitize(html, { ADD_ATTR: ['target', 'rel'] })
  }, [body])

  const handleCopy = () => {
    if (!def?.definition_raw) return
    navigator.clipboard.writeText(def.definition_raw).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  if (loading) return <div className="text-gray-500 text-sm">Loading…</div>
  if (error)   return <div className="text-rvp-error text-sm">{error}</div>
  if (!def)    return null

  return (
    <div className="space-y-5">

      {/* ── Header ── */}
      <div className="flex items-start gap-3">
        <Link
          to="/tests"
          className="text-gray-500 hover:text-gray-300 transition-colors mt-1 shrink-0 text-sm"
        >
          ← Back
        </Link>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-xl font-semibold text-gray-100">{def.name}</h1>
            <span className={`badge text-xs ${PRIORITY_BADGE[def.priority] ?? 'bg-gray-700 text-gray-400'}`}>
              {def.priority}
            </span>
            <span className={`badge text-xs ${def.is_active ? 'bg-rvp-success/20 text-rvp-success' : 'bg-gray-700 text-gray-500'}`}>
              {def.is_active ? 'active' : 'inactive'}
            </span>
          </div>
          <p className="text-xs text-gray-500 mt-1 font-mono break-all">{def.slug}</p>
        </div>
      </div>

      {/* ── Metadata grid ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-2">
        <MetaCard label="Version"   value={`v${def.version}`} />
        <MetaCard label="Component" value={def.component ?? '—'} />
        <MetaCard label="Timeout"   value={`${def.timeout_seconds}s`} />
        <MetaCard label="Created"   value={format(new Date(def.created_at), 'dd MMM yy')} />
        <MetaCard label="Updated"   value={format(new Date(def.updated_at), 'dd MMM yy')} />
        <MetaCard
          label="Tags"
          value={
            def.tags.length > 0
              ? <div className="flex flex-wrap gap-1">
                  {def.tags.map(t => (
                    <span key={t} className="badge text-xs bg-gray-700 text-gray-400">{t}</span>
                  ))}
                </div>
              : <span className="text-gray-500">—</span>
          }
        />
      </div>

      {/* ── Main content: Config (left) + Instructions (right) ── */}
      <div className="flex flex-col lg:flex-row gap-4 items-start">

        {/* Configuration */}
        {yaml && (
          <div className="card overflow-hidden w-full lg:w-2/5 lg:sticky lg:top-4">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-rvp-border">
              <span className="text-sm font-medium text-gray-300">Configuration</span>
              <button
                onClick={handleCopy}
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors px-2 py-1 rounded hover:bg-white/5"
              >
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
            <pre className="p-4 overflow-auto text-xs leading-relaxed text-gray-300 font-mono whitespace-pre max-h-[70vh]">
              {yaml}
            </pre>
          </div>
        )}

        {/* Instructions */}
        {body && (
          <div className="card overflow-hidden w-full lg:flex-1">
            <div className="px-4 py-2.5 border-b border-rvp-border">
              <span className="text-sm font-medium text-gray-300">Instructions</span>
            </div>
            <div
              className="md-prose px-5 py-4"
              dangerouslySetInnerHTML={{ __html: renderedMd }}
            />
          </div>
        )}
      </div>

    </div>
  )
}

function MetaCard({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="card px-3 py-2.5">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-sm text-gray-200 font-medium">{value}</div>
    </div>
  )
}
