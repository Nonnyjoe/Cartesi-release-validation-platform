import { useEffect, useState } from 'react'
import { releasesApi, cliReleasesApi, sdkReleasesApi, contractsReleasesApi } from '../api'
import type { ReleaseEntry, CliRelease, SdkRelease, ContractsRelease } from '../types'
import { format } from 'date-fns'

type Tab = 'node' | 'cli' | 'sdk' | 'contracts'

const CHANNEL_BADGE: Record<string, string> = {
  stable: 'bg-rvp-success/20 text-rvp-success',
  alpha:  'bg-rvp-warning/20 text-rvp-warning',
  beta:   'bg-rvp-info/20 text-rvp-info',
}

// ─── Shared sub-components ────────────────────────────────────────────────────

function SafetyBar({ rate }: { rate?: number }) {
  if (rate == null) return <span className="text-gray-600 text-xs">no runs</span>
  const color = rate >= 90 ? 'bg-rvp-success' : rate >= 70 ? 'bg-rvp-warning' : 'bg-rvp-error'
  const textColor = rate >= 90 ? 'text-rvp-success' : rate >= 70 ? 'text-rvp-warning' : 'text-rvp-error'
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 rounded-full bg-gray-700 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${rate}%` }} />
      </div>
      <span className={`text-xs font-medium ${textColor}`}>{rate.toFixed(1)}%</span>
    </div>
  )
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(value).then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        })
      }}
      title="Copy install command"
      className="ml-1 text-gray-600 hover:text-gray-300 transition-colors text-[10px] leading-none"
    >
      {copied ? '✓' : '⎘'}
    </button>
  )
}

function ToolchainRow({
  label, pkg, version,
}: { label: string; pkg: string; version?: string | null }) {
  const installCmd = version ? `npm install -g ${pkg}@${version}` : ''
  return (
    <div className="flex items-center justify-between gap-2 py-1.5 border-b border-rvp-border/30 last:border-0">
      <span className="text-xs text-gray-500 w-16 shrink-0">{label}</span>
      <span className="font-mono text-xs text-rvp-info flex-1 truncate">{pkg}</span>
      <div className="flex items-center gap-1 shrink-0">
        {version ? (
          <>
            <span className="font-mono text-xs text-gray-300">{version}</span>
            {pkg.startsWith('@') && <CopyButton value={installCmd} />}
          </>
        ) : (
          <span className="text-xs text-gray-600 italic">unknown</span>
        )}
      </div>
    </div>
  )
}

function RefRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="flex items-center gap-3 py-1 border-b border-rvp-border/30 last:border-0">
      <span className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider w-16 shrink-0">
        {label}
      </span>
      {value ? (
        <span className="font-mono text-xs text-gray-300">{value}</span>
      ) : (
        <span className="text-xs text-gray-600 italic">unknown</span>
      )}
    </div>
  )
}

function ReleaseNotes({ body }: { body?: string | null }) {
  const [expanded, setExpanded] = useState(false)
  if (!body) return null
  return (
    <div>
      <button
        className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        {expanded ? '▲ Hide notes' : '▼ Release notes'}
      </button>
      {expanded && (
        <pre className="mt-2 text-xs text-gray-400 bg-rvp-bg rounded-md p-3 overflow-auto max-h-48 whitespace-pre-wrap">
          {body}
        </pre>
      )}
    </div>
  )
}

// ─── Node release card ────────────────────────────────────────────────────────

function NodeReleaseCard({
  entry, onEditToolchain,
}: { entry: ReleaseEntry; onEditToolchain: () => void }) {
  return (
    <div className="card p-5 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-base font-mono font-semibold text-gray-100">{entry.tag}</span>
            <span className={`badge text-xs ${CHANNEL_BADGE[entry.channel] ?? 'bg-gray-700 text-gray-400'}`}>
              {entry.channel}
            </span>
          </div>
          <div className="text-xs text-gray-500 font-mono truncate" title={entry.image_tag}>
            {entry.image_tag}
          </div>
        </div>
        {entry.html_url && (
          <a href={entry.html_url} target="_blank" rel="noopener noreferrer"
             className="shrink-0 text-xs text-rvp-primary hover:underline">
            GitHub ↗
          </a>
        )}
      </div>

      {/* Toolchain — always visible, placeholders when unknown */}
      <div className="rounded-md bg-rvp-bg px-3 py-2">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider">
            Toolchain
          </span>
          <button
            onClick={onEditToolchain}
            className="text-[10px] text-rvp-primary hover:underline"
          >
            edit
          </button>
        </div>
        <ToolchainRow label="SDK" pkg="@cartesi/sdk" version={entry.sdk_version} />
        <ToolchainRow label="CLI" pkg="@cartesi/cli" version={entry.cli_version} />
        <ToolchainRow label="Devnet" pkg="@cartesi/devnet" version={entry.devnet_version} />
        <ToolchainRow label="Contracts" pkg="rollups-contracts" version={entry.contracts_version} />
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3 py-3 border-y border-rvp-border/50">
        <div>
          <div className="text-xs text-gray-500 mb-1">Published</div>
          <div className="text-sm text-gray-300">
            {entry.published_at ? format(new Date(entry.published_at), 'MMM d, yyyy') : '—'}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500 mb-1">Downloads</div>
          <div className="text-sm text-gray-300">
            {entry.downloads != null ? entry.downloads.toLocaleString() : '—'}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500 mb-1">Runs</div>
          <div className="text-sm text-gray-300">{entry.total_runs}</div>
        </div>
      </div>

      <div>
        <div className="text-xs text-gray-500 mb-1.5">Safety ratio</div>
        <SafetyBar rate={entry.avg_pass_rate} />
      </div>

      <ReleaseNotes body={entry.body} />
    </div>
  )
}

// ─── CLI release card ─────────────────────────────────────────────────────────

function CliReleaseCard({ entry }: { entry: CliRelease }) {
  return (
    <div className="card p-5 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-base font-mono font-semibold text-gray-100">{entry.tag}</span>
            <span className={`badge text-xs ${CHANNEL_BADGE[entry.channel] ?? 'bg-gray-700 text-gray-400'}`}>
              {entry.channel}
            </span>
          </div>
        </div>
        {entry.html_url && (
          <a href={entry.html_url} target="_blank" rel="noopener noreferrer"
             className="shrink-0 text-xs text-rvp-primary hover:underline">
            GitHub ↗
          </a>
        )}
      </div>

      {/* Cross-references */}
      <div className="rounded-md bg-rvp-bg px-3 py-2">
        <div className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider mb-1.5">
          Targets
        </div>
        <RefRow label="Node" value={entry.node_release_tag} />
        <RefRow label="SDK" value={entry.sdk_tag} />
        <RefRow label="Devnet" value={entry.devnet_tag} />
        <RefRow label="Contracts" value={entry.contracts_tag} />
      </div>

      <div className="grid grid-cols-2 gap-3 py-3 border-y border-rvp-border/50">
        <div>
          <div className="text-xs text-gray-500 mb-1">Published</div>
          <div className="text-sm text-gray-300">
            {entry.published_at ? format(new Date(entry.published_at), 'MMM d, yyyy') : '—'}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500 mb-1">Downloads</div>
          <div className="text-sm text-gray-300">
            {entry.downloads != null ? entry.downloads.toLocaleString() : '—'}
          </div>
        </div>
      </div>

      <ReleaseNotes body={entry.body} />
    </div>
  )
}

// ─── SDK release card ─────────────────────────────────────────────────────────

function SdkReleaseCard({ entry }: { entry: SdkRelease }) {
  return (
    <div className="card p-5 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-base font-mono font-semibold text-gray-100">{entry.tag}</span>
            <span className={`badge text-xs ${CHANNEL_BADGE[entry.channel] ?? 'bg-gray-700 text-gray-400'}`}>
              {entry.channel}
            </span>
          </div>
        </div>
        {entry.html_url && (
          <a href={entry.html_url} target="_blank" rel="noopener noreferrer"
             className="shrink-0 text-xs text-rvp-primary hover:underline">
            GitHub ↗
          </a>
        )}
      </div>

      {/* Cross-references */}
      <div className="rounded-md bg-rvp-bg px-3 py-2">
        <div className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider mb-1.5">
          Targets
        </div>
        <RefRow label="Node" value={entry.node_release_tag} />
        <RefRow label="CLI" value={entry.cli_tag} />
        <RefRow label="Contracts" value={entry.contracts_tag} />
      </div>

      <div className="grid grid-cols-2 gap-3 py-3 border-y border-rvp-border/50">
        <div>
          <div className="text-xs text-gray-500 mb-1">Published</div>
          <div className="text-sm text-gray-300">
            {entry.published_at ? format(new Date(entry.published_at), 'MMM d, yyyy') : '—'}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500 mb-1">Downloads</div>
          <div className="text-sm text-gray-300">
            {entry.downloads != null ? entry.downloads.toLocaleString() : '—'}
          </div>
        </div>
      </div>

      <ReleaseNotes body={entry.body} />
    </div>
  )
}

// ─── Contracts release card ───────────────────────────────────────────────────

function ContractsReleaseCard({ entry }: { entry: ContractsRelease }) {
  return (
    <div className="card p-5 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-base font-mono font-semibold text-gray-100">{entry.tag}</span>
            <span className={`badge text-xs ${CHANNEL_BADGE[entry.channel] ?? 'bg-gray-700 text-gray-400'}`}>
              {entry.channel}
            </span>
          </div>
        </div>
        {entry.html_url && (
          <a href={entry.html_url} target="_blank" rel="noopener noreferrer"
             className="shrink-0 text-xs text-rvp-primary hover:underline">
            GitHub ↗
          </a>
        )}
      </div>

      {/* Cross-references — contracts → devnet → cli → node */}
      <div className="rounded-md bg-rvp-bg px-3 py-2">
        <div className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider mb-1.5">
          Used By
        </div>
        <RefRow label="Devnet" value={entry.devnet_tag} />
        <RefRow label="CLI" value={entry.cli_tag} />
        <RefRow label="Node" value={entry.node_release_tag} />
        <RefRow label="SDK" value={entry.sdk_tag} />
      </div>

      <div className="grid grid-cols-2 gap-3 py-3 border-y border-rvp-border/50">
        <div>
          <div className="text-xs text-gray-500 mb-1">Published</div>
          <div className="text-sm text-gray-300">
            {entry.published_at ? format(new Date(entry.published_at), 'MMM d, yyyy') : '—'}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500 mb-1">Downloads</div>
          <div className="text-sm text-gray-300">
            {entry.downloads != null ? entry.downloads.toLocaleString() : '—'}
          </div>
        </div>
      </div>

      <ReleaseNotes body={entry.body} />
    </div>
  )
}

// ─── Toolchain edit modal ─────────────────────────────────────────────────────

function ToolchainEditModal({
  release, cliReleases, sdkReleases, contractsReleases, onClose, onSave,
}: {
  release:           ReleaseEntry
  cliReleases:       CliRelease[]
  sdkReleases:       SdkRelease[]
  contractsReleases: ContractsRelease[]
  onClose:           () => void
  onSave:            (tag: string, sdk?: string, cli?: string, devnet?: string, contracts?: string) => Promise<void>
}) {
  const [sdkVersion,       setSdkVersion]       = useState(release.sdk_version       ?? '')
  const [cliVersion,       setCliVersion]       = useState(release.cli_version       ?? '')
  const [devnetVersion,    setDevnetVersion]    = useState(release.devnet_version    ?? '')
  const [contractsVersion, setContractsVersion] = useState(release.contracts_version ?? '')
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave(
        release.tag,
        sdkVersion       || undefined,
        cliVersion       || undefined,
        devnetVersion    || undefined,
        contractsVersion || undefined,
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="card w-full max-w-md p-6 space-y-4 max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-100">Edit Toolchain</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-xl leading-none">
            ✕
          </button>
        </div>
        <p className="text-xs text-gray-500 -mt-2">
          Manually override toolchain versions for{' '}
          <span className="font-mono text-gray-300">{release.tag}</span>
        </p>

        {/* SDK version */}
        <div className="space-y-2">
          <label className="text-xs font-medium text-gray-400">@cartesi/sdk version</label>
          {sdkReleases.length > 0 && (
            <select onChange={e => { if (e.target.value) setSdkVersion(e.target.value) }}
              defaultValue="" className="input w-full">
              <option value="" disabled>— pick a known version —</option>
              {sdkReleases.map(s => (
                <option key={s.tag} value={s.tag.replace(/^v/, '')}>{s.tag}</option>
              ))}
            </select>
          )}
          <input type="text" value={sdkVersion} onChange={e => setSdkVersion(e.target.value)}
            placeholder="e.g. 0.12.0-alpha.39" className="input w-full font-mono" />
        </div>

        {/* CLI version */}
        <div className="space-y-2">
          <label className="text-xs font-medium text-gray-400">@cartesi/cli version</label>
          {cliReleases.length > 0 && (
            <select onChange={e => { if (e.target.value) setCliVersion(e.target.value) }}
              defaultValue="" className="input w-full">
              <option value="" disabled>— pick a known version —</option>
              {cliReleases.map(c => (
                <option key={c.tag} value={c.tag.replace(/^v/, '')}>{c.tag}</option>
              ))}
            </select>
          )}
          <input type="text" value={cliVersion} onChange={e => setCliVersion(e.target.value)}
            placeholder="e.g. 2.0.0-alpha.34" className="input w-full font-mono" />
        </div>

        {/* Devnet version */}
        <div className="space-y-2">
          <label className="text-xs font-medium text-gray-400">@cartesi/devnet version</label>
          <input type="text" value={devnetVersion} onChange={e => setDevnetVersion(e.target.value)}
            placeholder="e.g. 1.5.0" className="input w-full font-mono" />
        </div>

        {/* Contracts version */}
        <div className="space-y-2">
          <label className="text-xs font-medium text-gray-400">rollups-contracts version</label>
          {contractsReleases.length > 0 && (
            <select onChange={e => { if (e.target.value) setContractsVersion(e.target.value) }}
              defaultValue="" className="input w-full">
              <option value="" disabled>— pick a known version —</option>
              {contractsReleases.map(c => (
                <option key={c.tag} value={c.tag.replace(/^v/, '')}>{c.tag}</option>
              ))}
            </select>
          )}
          <input type="text" value={contractsVersion} onChange={e => setContractsVersion(e.target.value)}
            placeholder="e.g. 2.0.0-alpha.5" className="input w-full font-mono" />
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3 pt-1">
          <button onClick={onClose} className="btn-ghost text-sm">Cancel</button>
          <button onClick={handleSave} disabled={saving} className="btn-primary text-sm">
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Section grouping helper ──────────────────────────────────────────────────

function ChannelSection<T extends { channel: string }>({
  label, items, renderCard,
}: { label: string; items: T[]; renderCard: (item: T) => React.ReactNode }) {
  if (items.length === 0) return null
  return (
    <section>
      <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
        {label}
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item, i) => <div key={i}>{renderCard(item)}</div>)}
      </div>
    </section>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

const TAB_LABELS: Record<Tab, string> = { node: 'Node', cli: 'CLI', sdk: 'SDK', contracts: 'Contracts' }
const TAB_DESC: Record<Tab, string> = {
  node:      'Catalog of rollups-node releases tracked by RVP',
  cli:       '@cartesi/cli releases — one per CLI toolchain version',
  sdk:       '@cartesi/sdk releases — one per runtime image tag',
  contracts: 'rollups-contracts releases — L1 contract deployments',
}

export default function Releases() {
  const [tab, setTab]                       = useState<Tab>('sdk')
  const [releases, setReleases]             = useState<ReleaseEntry[]>([])
  const [cliReleases, setCli]               = useState<CliRelease[]>([])
  const [sdkReleases, setSdk]               = useState<SdkRelease[]>([])
  const [contractsReleases, setContracts]   = useState<ContractsRelease[]>([])
  const [loading, setLoading]               = useState(true)
  const [syncing, setSyncing]               = useState(false)
  const [syncMsg, setSyncMsg]               = useState('')
  const [editRelease, setEditRelease]       = useState<ReleaseEntry | null>(null)

  const loadAll = async () => {
    setLoading(true)
    try {
      const [n, c, s, co] = await Promise.all([
        releasesApi.list(),
        cliReleasesApi.list(),
        sdkReleasesApi.list(),
        contractsReleasesApi.list(),
      ])
      setReleases(n)
      setCli(c)
      setSdk(s)
      setContracts(co)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { loadAll() }, [])

  const handleSync = async () => {
    setSyncing(true)
    setSyncMsg('')
    try {
      const res = tab === 'node'      ? await releasesApi.sync()
                : tab === 'cli'       ? await cliReleasesApi.sync()
                : tab === 'sdk'       ? await sdkReleasesApi.sync()
                :                       await contractsReleasesApi.sync()
      setSyncMsg(`Synced ${res.synced} releases`)
      await loadAll()
    } catch (e) {
      setSyncMsg(`Sync failed: ${String(e)}`)
    } finally { setSyncing(false) }
  }

  const handleToolchainSave = async (
    tag: string, sdk?: string, cli?: string, devnet?: string, contracts?: string
  ) => {
    await releasesApi.updateToolchain(tag, {
      sdk_version:       sdk,
      cli_version:       cli,
      devnet_version:    devnet,
      contracts_version: contracts,
    })
    await loadAll()
    setEditRelease(null)
  }

  const nodeGroups = {
    stable: releases.filter(r => r.channel === 'stable'),
    beta:   releases.filter(r => r.channel === 'beta'),
    alpha:  releases.filter(r => r.channel === 'alpha'),
  }
  const cliGroups = {
    stable: cliReleases.filter(r => r.channel === 'stable'),
    beta:   cliReleases.filter(r => r.channel === 'beta'),
    alpha:  cliReleases.filter(r => r.channel === 'alpha'),
  }
  const sdkGroups = {
    stable: sdkReleases.filter(r => r.channel === 'stable'),
    beta:   sdkReleases.filter(r => r.channel === 'beta'),
    alpha:  sdkReleases.filter(r => r.channel === 'alpha'),
  }
  const contractsGroups = {
    stable: contractsReleases.filter(r => r.channel === 'stable'),
    beta:   contractsReleases.filter(r => r.channel === 'beta'),
    alpha:  contractsReleases.filter(r => r.channel === 'alpha'),
  }

  const isEmpty = tab === 'node'      ? releases.length === 0
                : tab === 'cli'       ? cliReleases.length === 0
                : tab === 'sdk'       ? sdkReleases.length === 0
                :                       contractsReleases.length === 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">Releases</h1>
          <p className="text-xs text-gray-500 mt-0.5">{TAB_DESC[tab]}</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {syncMsg && (
            <span className={`text-xs ${syncMsg.startsWith('Sync failed') ? 'text-rvp-error' : 'text-rvp-success'}`}>
              {syncMsg}
            </span>
          )}
          <button className="btn-primary" onClick={handleSync} disabled={syncing}>
            {syncing ? 'Syncing…' : '↻ Sync from GitHub'}
          </button>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 p-1 bg-rvp-surface rounded-lg border border-rvp-border w-fit">
        {(['sdk', 'node', 'cli', 'contracts'] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => { setTab(t); setSyncMsg('') }}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === t
                ? 'bg-rvp-primary text-white'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="text-sm text-gray-500">Loading…</div>
      ) : isEmpty ? (
        <div className="card p-8 text-center text-gray-500 text-sm">
          No {TAB_LABELS[tab]} releases in catalog. Click "Sync from GitHub" to populate.
        </div>
      ) : (
        <div className="space-y-6">
          {tab === 'node' && (
            <>
              <ChannelSection
                label="Stable" items={nodeGroups.stable}
                renderCard={r => <NodeReleaseCard entry={r} onEditToolchain={() => setEditRelease(r)} />}
              />
              <ChannelSection
                label="Beta" items={nodeGroups.beta}
                renderCard={r => <NodeReleaseCard entry={r} onEditToolchain={() => setEditRelease(r)} />}
              />
              <ChannelSection
                label="Alpha" items={nodeGroups.alpha}
                renderCard={r => <NodeReleaseCard entry={r} onEditToolchain={() => setEditRelease(r)} />}
              />
            </>
          )}

          {tab === 'cli' && (
            <>
              <ChannelSection label="Stable" items={cliGroups.stable} renderCard={r => <CliReleaseCard entry={r} />} />
              <ChannelSection label="Beta"   items={cliGroups.beta}   renderCard={r => <CliReleaseCard entry={r} />} />
              <ChannelSection label="Alpha"  items={cliGroups.alpha}  renderCard={r => <CliReleaseCard entry={r} />} />
            </>
          )}

          {tab === 'sdk' && (
            <>
              <ChannelSection label="Stable" items={sdkGroups.stable} renderCard={r => <SdkReleaseCard entry={r} />} />
              <ChannelSection label="Beta"   items={sdkGroups.beta}   renderCard={r => <SdkReleaseCard entry={r} />} />
              <ChannelSection label="Alpha"  items={sdkGroups.alpha}  renderCard={r => <SdkReleaseCard entry={r} />} />
            </>
          )}

          {tab === 'contracts' && (
            <>
              <ChannelSection label="Stable" items={contractsGroups.stable} renderCard={r => <ContractsReleaseCard entry={r} />} />
              <ChannelSection label="Beta"   items={contractsGroups.beta}   renderCard={r => <ContractsReleaseCard entry={r} />} />
              <ChannelSection label="Alpha"  items={contractsGroups.alpha}  renderCard={r => <ContractsReleaseCard entry={r} />} />
            </>
          )}
        </div>
      )}

      {/* Toolchain edit modal */}
      {editRelease && (
        <ToolchainEditModal
          release={editRelease}
          cliReleases={cliReleases}
          sdkReleases={sdkReleases}
          contractsReleases={contractsReleases}
          onClose={() => setEditRelease(null)}
          onSave={handleToolchainSave}
        />
      )}
    </div>
  )
}
