import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { apiFetch } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { DataTable, type Column } from '../components/DataTable'
import { PageHeader } from '../components/PageHeader'
import { downloadFile, fetchBlobUrl } from '../grcApi'
import type { GrcReportRun } from '../grcTypes'

const when = (iso: string) => iso.replace('T', ' ').slice(0, 16)

export function ReportsPage() {
  const { hasRole } = useAuth()
  const [runs, setRuns] = useState<GrcReportRun[]>([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [days, setDays] = useState(7)
  const [audience, setAudience] = useState('both')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<{ name: string; url: string } | null>(null)

  const load = useCallback(() => {
    apiFetch<{ runs: GrcReportRun[] }>('/api/grc/reports')
      .then((r) => {
        setRuns(r.runs)
        setLoaded(true)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load'))
  }, [])

  useEffect(load, [load])

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview.url)
    }
  }, [preview])

  async function generate() {
    setBusy(true)
    setError('')
    try {
      await apiFetch('/api/grc/reports/generate', { method: 'POST', body: JSON.stringify({ days, audience }) })
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Report generation failed')
    } finally {
      setBusy(false)
    }
  }

  async function show(name: string) {
    try {
      const url = await fetchBlobUrl(`/api/grc/reports/files/${name}`)
      setPreview({ name, url })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open the report')
    }
  }

  function fileCell(name?: string) {
    if (!name) return <span style={{ color: 'var(--text-muted)' }}>-</span>
    return (
      <span style={{ display: 'flex', gap: 8 }}>
        <button type="button" style={linkButton} onClick={() => show(name)}>Preview</button>
        <button type="button" style={linkButton} onClick={() => downloadFile(`/api/grc/reports/files/${name}`, name)}>Download</button>
      </span>
    )
  }

  const columns: Column<GrcReportRun>[] = [
    { key: 'when', header: 'Generated', render: (r) => when(r.generated_at) },
    { key: 'period', header: 'Period', render: (r) => `${r.period_start} to ${r.period_end}` },
    { key: 'aud', header: 'Audience', render: (r) => r.audience ?? 'both' },
    { key: 'exec', header: 'Executive report', render: (r) => fileCell(r.files.executive) },
    { key: 'tech', header: 'Technical report', render: (r) => fileCell(r.files.technical) },
  ]

  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle="Executive (1-2 pages) and technical reports as PDF, built from the platform's current data."
      />
      {error ? <div style={{ color: 'var(--danger)', marginBottom: 12 }}>{error}</div> : null}

      {hasRole('Admin', 'Analyst') ? (
        <section style={{ ...card, marginBottom: 16 }}>
          <h3 style={heading}>Generate a report</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
            <select value={days} onChange={(e) => setDays(Number(e.target.value))} style={input}>
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </select>
            <select value={audience} onChange={(e) => setAudience(e.target.value)} style={input}>
              <option value="both">Executive and technical</option>
              <option value="executive">Executive only</option>
              <option value="technical">Technical only</option>
            </select>
            <button type="button" style={primaryButton} disabled={busy} onClick={generate}>
              {busy ? 'Generating...' : 'Generate'}
            </button>
          </div>
          <p style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 0 }}>
            Weekly reports: schedule the command <code>python reports.py</code> (in the grc folder) with Windows Task Scheduler or cron.
          </p>
        </section>
      ) : null}

      <section style={card}>
        <h3 style={heading}>History</h3>
        <DataTable
          columns={columns}
          rows={runs}
          rowKey={(r) => r.generated_at}
          emptyMessage={loaded ? 'No reports yet' : 'Loading...'}
        />
      </section>

      {preview ? (
        <section style={{ ...card, marginTop: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
            <h3 style={{ ...heading, marginBottom: 0 }}>{preview.name}</h3>
            <button type="button" style={linkButton} onClick={() => setPreview(null)}>Close preview</button>
          </div>
          <iframe title="Report preview" src={preview.url} style={{ width: '100%', height: 760, border: '1px solid var(--border)', borderRadius: 10, background: '#fff' }} />
        </section>
      ) : null}
    </div>
  )
}

const card: CSSProperties = { background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 14, padding: 16 }
const heading: CSSProperties = { marginTop: 0, marginBottom: 12, fontSize: 15 }
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
const linkButton: CSSProperties = { background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', padding: 0, fontSize: 13 }
