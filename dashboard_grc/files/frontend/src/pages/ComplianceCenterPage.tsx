import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { apiFetch } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { DataTable, type Column } from '../components/DataTable'
import { DetailDrawer } from '../components/DetailDrawer'
import { Gauge } from '../components/Gauge'
import { KpiTile } from '../components/KpiTile'
import { PageHeader } from '../components/PageHeader'
import type { GrcControl, GrcControlPage, GrcOverview } from '../grcTypes'
import { gaugeColor } from '../grcUtils'

const STATUSES = ['Implemented', 'Partial', 'Not implemented', 'Not applicable']
const PAGE_SIZE = 15

const STATUS_COLOR: Record<string, string> = {
  Implemented: 'var(--success)',
  Partial: 'var(--medium)',
  'Not implemented': 'var(--critical)',
  'Not applicable': 'var(--text-muted)',
}

function Pill({ text, color }: { text: string; color: string }) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 10px',
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 600,
        whiteSpace: 'nowrap',
        color,
        background: `color-mix(in srgb, ${color} 14%, transparent)`,
        border: `1px solid color-mix(in srgb, ${color} 40%, transparent)`,
      }}
    >
      {text}
    </span>
  )
}

function EvidencePill({ control }: { control: GrcControl }) {
  const { state, fresh, stale } = control.evidence
  if (state === 'fresh') return <Pill text={`${fresh} fresh`} color="var(--success)" />
  if (state === 'stale') return <Pill text={`${stale} stale`} color="var(--medium)" />
  return <Pill text="none" color="var(--text-muted)" />
}

export function ComplianceCenterPage() {
  const { hasRole } = useAuth()
  const [overview, setOverview] = useState<GrcOverview | null>(null)
  const [controls, setControls] = useState<GrcControlPage | null>(null)
  const [error, setError] = useState('')
  const [framework, setFramework] = useState('')
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<GrcControl | null>(null)
  const [collecting, setCollecting] = useState(false)

  const loadOverview = useCallback(() => {
    apiFetch<GrcOverview>('/api/grc/compliance')
      .then(setOverview)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load'))
  }, [])

  const loadControls = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) })
    if (framework) params.set('framework', framework)
    if (status) params.set('status', status)
    if (query) params.set('q', query)
    apiFetch<GrcControlPage>(`/api/grc/controls?${params.toString()}`)
      .then(setControls)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load'))
  }, [page, framework, status, query])

  useEffect(loadOverview, [loadOverview])
  useEffect(loadControls, [loadControls])

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search.trim())
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [search])

  async function collectEvidence() {
    setCollecting(true)
    try {
      await apiFetch('/api/grc/evidence/collect', { method: 'POST' })
      loadOverview()
      loadControls()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Evidence collection failed')
    } finally {
      setCollecting(false)
    }
  }

  function pickFramework(id: string) {
    setFramework((current) => (current === id ? '' : id))
    setPage(1)
  }

  const focus = overview?.frameworks.find((f) => f.id === (framework || overview.frameworks[0]?.id))
  const labelOf = (id: string) => overview?.frameworks.find((f) => f.id === id)?.label ?? id
  const totalPages = controls ? Math.max(1, Math.ceil(controls.total / controls.page_size)) : 1

  const columns: Column<GrcControl>[] = [
    { key: 'id', header: 'Control', render: (c) => <strong>{c.id}</strong>, width: '120px' },
    {
      key: 'title',
      header: 'Description',
      render: (c) => {
        const text = c.title || c.description
        return <span title={c.description}>{text.length > 90 ? `${text.slice(0, 90)}...` : text}</span>
      },
    },
    { key: 'category', header: 'Category', render: (c) => c.function ?? c.category },
    { key: 'status', header: 'Status', render: (c) => <Pill text={c.status} color={STATUS_COLOR[c.status] ?? 'var(--text-muted)'} /> },
    { key: 'maturity', header: 'Maturity', render: (c) => `${c.maturity}/5` },
    { key: 'evidence', header: 'Evidence', render: (c) => <EvidencePill control={c} /> },
    { key: 'review', header: 'Review date', render: (c) => c.review_date ?? '-' },
  ]

  return (
    <div>
      <PageHeader
        title="Compliance Center"
        subtitle="Coverage of NIST CSF 2.0, ISO 27001, CIS v8.1 and OWASP Top 10 by the platform. Not a certification."
        actions={
          hasRole('Admin', 'Analyst') ? (
            <button type="button" onClick={collectEvidence} disabled={collecting} style={primaryButton}>
              {collecting ? 'Collecting...' : 'Collect evidence now'}
            </button>
          ) : undefined
        }
      />

      {error ? <div style={{ color: 'var(--danger)', marginBottom: 12 }}>{error}</div> : null}
      {!overview && !error ? <div style={{ color: 'var(--text-muted)' }}>Loading...</div> : null}

      {overview ? (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12, marginBottom: 16 }}>
            <KpiTile label="Average coverage" value={`${overview.overall}%`} hint="across the four frameworks" />
            <KpiTile label="Controls" value={overview.total_controls} hint="in the control library" />
            <KpiTile label="With fresh evidence" value={overview.evidence.controls_fresh} hint={`${overview.evidence.items} evidence items`} />
            <KpiTile label="Stale evidence" value={overview.evidence.controls_stale} hint={`${overview.evidence.controls_none} controls have none`} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12, marginBottom: 16 }}>
            {overview.frameworks.map((f) => (
              <Gauge
                key={f.id}
                value={f.percent}
                label={f.label}
                hint={`${f.counts['Implemented'] ?? 0} implemented, ${f.counts['Partial'] ?? 0} partial`}
                active={framework === f.id}
                onClick={() => pickFramework(f.id)}
              />
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16, marginBottom: 16 }}>
            <section style={card}>
              <h3 style={heading}>By function: {focus?.label}</h3>
              <div style={{ display: 'grid', gap: 10 }}>
                {focus?.functions.map((fn) => (
                  <div key={fn.name}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                      <span>{fn.name}</span>
                      <span style={{ color: 'var(--text-muted)' }}>{fn.percent}%</span>
                    </div>
                    <div style={{ height: 8, borderRadius: 999, background: 'var(--bg-panel)', overflow: 'hidden' }}>
                      <div style={{ width: `${fn.percent}%`, height: '100%', background: gaugeColor(fn.percent) }} />
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section style={card}>
              <h3 style={heading}>Biggest gaps</h3>
              <div style={{ display: 'grid', gap: 8 }}>
                {overview.gaps.length === 0 ? <span style={{ color: 'var(--text-muted)' }}>No gaps</span> : null}
                {overview.gaps.map((g) => (
                  <div key={`${g.framework}|${g.category}`} style={row}>
                    <span>
                      {g.category}
                      <span style={{ color: 'var(--text-muted)' }}> ({labelOf(g.framework)})</span>
                    </span>
                    <strong>-{g.points_lost}</strong>
                  </div>
                ))}
              </div>
            </section>

            <section style={card}>
              <h3 style={heading}>Quickest wins</h3>
              <div style={{ display: 'grid', gap: 8 }}>
                {overview.quick_wins.length === 0 ? <span style={{ color: 'var(--text-muted)' }}>Nothing pending</span> : null}
                {overview.quick_wins.map((w) => (
                  <div key={w.id} style={row}>
                    <strong>{w.id}</strong>
                    <span style={{ color: 'var(--text-muted)', fontSize: 12, textAlign: 'right' }}>
                      {w.missing_features.length ? `needs: ${w.missing_features.join(', ')}` : 'ready to confirm'}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </>
      ) : null}

      <section style={card}>
        <h3 style={heading}>Controls</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 12 }}>
          <select value={framework} onChange={(e) => { setFramework(e.target.value); setPage(1) }} style={input}>
            <option value="">All frameworks</option>
            {overview?.frameworks.map((f) => (
              <option key={f.id} value={f.id}>{f.label}</option>
            ))}
          </select>
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} style={input}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search id, text, category" style={{ ...input, minWidth: 240 }} />
        </div>

        <DataTable
          columns={columns}
          rows={controls?.items ?? []}
          rowKey={(c) => c.id}
          onRowClick={setSelected}
          emptyMessage={controls ? 'No controls match these filters' : 'Loading...'}
        />

        {controls ? (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12, fontSize: 13, color: 'var(--text-muted)' }}>
            <span>
              {controls.total} controls, page {controls.page} of {totalPages}
            </span>
            <span style={{ display: 'flex', gap: 8 }}>
              <button type="button" style={input} disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
              <button type="button" style={input} disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</button>
            </span>
          </div>
        ) : null}
      </section>

      <DetailDrawer open={selected !== null} title={selected?.id ?? ''} onClose={() => setSelected(null)}>
        {selected ? (
          <div style={{ display: 'grid', gap: 14, fontSize: 14 }}>
            <div>
              <div style={label}>{labelOf(selected.framework)}</div>
              {selected.title ? <strong>{selected.title}</strong> : null}
              <p style={{ margin: '6px 0 0' }}>{selected.description}</p>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Pill text={selected.status} color={STATUS_COLOR[selected.status] ?? 'var(--text-muted)'} />
              <EvidencePill control={selected} />
            </div>
            <div><span style={label}>Category</span><br />{selected.function ? `${selected.function} / ` : ''}{selected.category}</div>
            <div><span style={label}>Owner</span><br />{selected.owner}</div>
            <div><span style={label}>Maturity</span><br />{selected.maturity} of 5</div>
            <div>
              <span style={label}>Platform features that cover it</span>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                {selected.platform_features.length === 0 ? (
                  <span style={{ color: 'var(--text-muted)' }}>None: an organisational control (gap)</span>
                ) : (
                  selected.platform_features.map((f) => <Pill key={f} text={f} color="var(--accent)" />)
                )}
              </div>
            </div>
          </div>
        ) : null}
      </DetailDrawer>
    </div>
  )
}

const card: CSSProperties = {
  background: 'var(--bg-elevated)',
  border: '1px solid var(--border)',
  borderRadius: 14,
  padding: 16,
}
const heading: CSSProperties = { marginTop: 0, marginBottom: 12, fontSize: 15 }
const row: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  gap: 10,
  padding: '8px 10px',
  borderRadius: 10,
  background: 'var(--bg-panel)',
  fontSize: 13,
}
const label: CSSProperties = { color: 'var(--text-muted)', fontSize: 12 }
const input: CSSProperties = {
  background: 'var(--bg-panel)',
  color: 'var(--text)',
  border: '1px solid var(--border)',
  borderRadius: 10,
  padding: '8px 12px',
}
const primaryButton: CSSProperties = {
  background: 'var(--accent)',
  color: '#fff',
  border: 'none',
  borderRadius: 10,
  padding: '9px 16px',
  fontWeight: 600,
  cursor: 'pointer',
}
