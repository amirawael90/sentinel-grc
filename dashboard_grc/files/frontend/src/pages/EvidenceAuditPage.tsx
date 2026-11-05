import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { apiFetch } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { DataTable, type Column } from '../components/DataTable'
import { DetailDrawer } from '../components/DetailDrawer'
import { PageHeader } from '../components/PageHeader'
import { Pill } from '../components/Pill'
import { downloadFile } from '../grcApi'
import type {
  GrcAuditEntry,
  GrcAuditPage,
  GrcChainCheck,
  GrcEvidenceCheck,
  GrcEvidenceItem,
  GrcEvidencePage,
} from '../grcTypes'

const PAGE_SIZE = 12
const RESULT_COLOR: Record<string, string> = {
  success: 'var(--success)',
  rejected: 'var(--medium)',
  failed: 'var(--critical)',
}

const short = (hash: string) => `${hash.slice(0, 12)}...`
const when = (iso: string) => iso.replace('T', ' ').slice(0, 19)

type Tab = 'evidence' | 'audit'

export function EvidenceAuditPage() {
  const [tab, setTab] = useState<Tab>('evidence')

  return (
    <div>
      <PageHeader
        title="Evidence and Audit"
        subtitle="Proof that controls work (hashed evidence) and a tamper-evident log of every decision and action. Read-only for auditors."
      />
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {(['evidence', 'audit'] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            style={{ ...tabButton, ...(tab === t ? tabActive : null) }}
          >
            {t === 'evidence' ? 'Evidence browser' : 'Audit log'}
          </button>
        ))}
      </div>
      {tab === 'evidence' ? <EvidenceTab /> : <AuditTab />}
    </div>
  )
}

function Pager({ page, total, pageSize, onPage }: { page: number; total: number; pageSize: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12, fontSize: 13, color: 'var(--text-muted)' }}>
      <span>
        {total} rows, page {page} of {pages}
      </span>
      <span style={{ display: 'flex', gap: 8 }}>
        <button type="button" style={input} disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
        <button type="button" style={input} disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
      </span>
    </div>
  )
}

function EvidenceTab() {
  const [data, setData] = useState<GrcEvidencePage | null>(null)
  const [error, setError] = useState('')
  const [control, setControl] = useState('')
  const [controlQuery, setControlQuery] = useState('')
  const [source, setSource] = useState('')
  const [state, setState] = useState('')
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<GrcEvidenceItem | null>(null)
  const [check, setCheck] = useState<GrcEvidenceCheck | null>(null)

  const load = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) })
    if (controlQuery) params.set('control', controlQuery)
    if (source) params.set('source', source)
    if (state) params.set('state', state)
    if (since) params.set('since', since)
    if (until) params.set('until', until)
    apiFetch<GrcEvidencePage>(`/api/grc/evidence?${params.toString()}`)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load'))
  }, [page, controlQuery, source, state, since, until])

  useEffect(load, [load])

  useEffect(() => {
    const timer = setTimeout(() => {
      setControlQuery(control.trim())
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [control])

  async function verify() {
    setCheck(null)
    try {
      setCheck(await apiFetch<GrcEvidenceCheck>('/api/grc/evidence/verify'))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Verification failed')
    }
  }

  const columns: Column<GrcEvidenceItem>[] = [
    { key: 'source', header: 'Source', render: (e) => <strong>{e.source}</strong> },
    { key: 'path', header: 'File', render: (e) => e.path },
    { key: 'hash', header: 'SHA-256', render: (e) => <code title={e.sha256}>{short(e.sha256)}</code> },
    { key: 'first', header: 'Collected', render: (e) => when(e.first_collected_at) },
    { key: 'last', header: 'Last verified', render: (e) => when(e.last_verified_at) },
    { key: 'state', header: 'State', render: (e) => <Pill text={e.state} color={e.state === 'fresh' ? 'var(--success)' : 'var(--medium)'} /> },
    { key: 'controls', header: 'Controls', render: (e) => e.linked_controls.length },
  ]

  return (
    <section style={card}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 12, alignItems: 'center' }}>
        <input value={control} onChange={(e) => setControl(e.target.value)} placeholder="Control (e.g. ISO-8.15)" style={input} />
        <select value={source} onChange={(e) => { setSource(e.target.value); setPage(1) }} style={input}>
          <option value="">All sources</option>
          {data?.sources.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={state} onChange={(e) => { setState(e.target.value); setPage(1) }} style={input}>
          <option value="">Fresh and stale</option>
          <option value="fresh">Fresh</option>
          <option value="stale">Stale</option>
        </select>
        <label style={small}>From <input type="date" value={since} onChange={(e) => { setSince(e.target.value); setPage(1) }} style={input} /></label>
        <label style={small}>To <input type="date" value={until} onChange={(e) => { setUntil(e.target.value); setPage(1) }} style={input} /></label>
        <button type="button" style={{ ...input, marginLeft: 'auto' }} onClick={verify}>Verify integrity</button>
      </div>

      {check ? (
        <div style={{ ...banner, borderColor: check.ok ? 'var(--success)' : 'var(--critical)' }}>
          {check.ok
            ? `All ${check.checked} evidence files match their recorded hash.`
            : `Integrity problem: ${check.problems.join('; ')}`}
        </div>
      ) : null}
      {error ? <div style={{ color: 'var(--danger)', marginBottom: 12 }}>{error}</div> : null}

      <DataTable
        columns={columns}
        rows={data?.items ?? []}
        rowKey={(e) => e.id}
        onRowClick={setSelected}
        emptyMessage={data ? 'No evidence matches these filters. Collect evidence from the Compliance Center.' : 'Loading...'}
      />
      {data ? <Pager page={page} total={data.total} pageSize={PAGE_SIZE} onPage={setPage} /> : null}

      <DetailDrawer open={selected !== null} title={selected?.source ?? ''} onClose={() => setSelected(null)}>
        {selected ? (
          <div style={{ display: 'grid', gap: 14, fontSize: 14 }}>
            <div><span style={small}>File</span><br />{selected.path} ({selected.size} bytes)</div>
            <div>
              <span style={small}>SHA-256</span>
              <br />
              <code style={{ wordBreak: 'break-all' }}>{selected.sha256}</code>
            </div>
            <div><span style={small}>First collected</span><br />{when(selected.first_collected_at)}</div>
            <div><span style={small}>Last verified</span><br />{when(selected.last_verified_at)}</div>
            <div>
              <span style={small}>Fresh for</span><br />{selected.max_age_days} days{' '}
              <Pill text={selected.state} color={selected.state === 'fresh' ? 'var(--success)' : 'var(--medium)'} />
            </div>
            <div>
              <span style={small}>Supports {selected.linked_controls.length} controls</span>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                {selected.linked_controls.map((c) => <Pill key={c} text={c} color="var(--accent)" />)}
              </div>
            </div>
          </div>
        ) : null}
      </DetailDrawer>
    </section>
  )
}

function AuditTab() {
  const { hasRole } = useAuth()
  const [data, setData] = useState<GrcAuditPage | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [actor, setActor] = useState('')
  const [action, setAction] = useState('')
  const [target, setTarget] = useState('')
  const [q, setQ] = useState('')
  const [result, setResult] = useState('')
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [text, setText] = useState({ actor: '', action: '', target: '', q: '' })
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<GrcAuditEntry | null>(null)
  const [chain, setChain] = useState<GrcChainCheck | null>(null)

  const filters = useCallback(() => {
    const params = new URLSearchParams()
    if (actor) params.set('actor', actor)
    if (action) params.set('action', action)
    if (target) params.set('target', target)
    if (q) params.set('q', q)
    if (result) params.set('result', result)
    if (since) params.set('since', since)
    if (until) params.set('until', until)
    return params
  }, [actor, action, target, q, result, since, until])

  const load = useCallback(() => {
    const params = filters()
    params.set('page', String(page))
    params.set('page_size', String(PAGE_SIZE))
    apiFetch<GrcAuditPage>(`/api/grc/audit?${params.toString()}`)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load'))
  }, [filters, page])

  useEffect(load, [load])

  useEffect(() => {
    const timer = setTimeout(() => {
      setActor(text.actor.trim())
      setAction(text.action.trim())
      setTarget(text.target.trim())
      setQ(text.q.trim())
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [text])

  async function verifyChain() {
    setChain(null)
    try {
      setChain(await apiFetch<GrcChainCheck>('/api/grc/audit/verify'))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Verification failed')
    }
  }

  async function exportCsv() {
    try {
      await downloadFile(`/api/grc/audit/export?${filters().toString()}`, 'sentinel_audit_log.csv')
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed')
    }
  }

  async function importActions() {
    setNotice('')
    try {
      const r = await apiFetch<{ added: number }>('/api/grc/audit/import', { method: 'POST' })
      setNotice(`Imported ${r.added} executor action(s).`)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    }
  }

  const columns: Column<GrcAuditEntry>[] = [
    { key: 'seq', header: '#', render: (e) => e.seq, width: '60px' },
    { key: 'ts', header: 'Time (UTC)', render: (e) => when(e.ts) },
    { key: 'actor', header: 'Actor', render: (e) => e.actor },
    { key: 'action', header: 'Action', render: (e) => <strong>{e.action}</strong> },
    { key: 'target', header: 'Target', render: (e) => e.target },
    { key: 'result', header: 'Result', render: (e) => <Pill text={e.result} color={RESULT_COLOR[e.result] ?? 'var(--text-muted)'} /> },
    { key: 'corr', header: 'Correlation id', render: (e) => e.correlation_id || '-' },
    { key: 'hash', header: 'Hash', render: (e) => <code title={e.hash}>{short(e.hash)}</code> },
  ]

  return (
    <section style={card}>
      {data?.has_sample ? (
        <div style={{ ...banner, borderColor: 'var(--medium)' }}>
          This log contains SAMPLE entries (flagged in each entry) until the platform components write to it. Actions done in this dashboard are real entries.
        </div>
      ) : null}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 12, alignItems: 'center' }}>
        <input value={text.actor} onChange={(e) => setText({ ...text, actor: e.target.value })} placeholder="Actor" style={input} />
        <input value={text.action} onChange={(e) => setText({ ...text, action: e.target.value })} placeholder="Action" style={input} />
        <input value={text.target} onChange={(e) => setText({ ...text, target: e.target.value })} placeholder="Target" style={input} />
        <input value={text.q} onChange={(e) => setText({ ...text, q: e.target.value })} placeholder="Search everything" style={input} />
        <select value={result} onChange={(e) => { setResult(e.target.value); setPage(1) }} style={input}>
          <option value="">Any result</option>
          <option value="success">success</option>
          <option value="rejected">rejected</option>
          <option value="failed">failed</option>
        </select>
        <label style={small}>From <input type="date" value={since} onChange={(e) => { setSince(e.target.value); setPage(1) }} style={input} /></label>
        <label style={small}>To <input type="date" value={until} onChange={(e) => { setUntil(e.target.value); setPage(1) }} style={input} /></label>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 12, alignItems: 'center' }}>
        <button type="button" style={input} onClick={verifyChain}>Verify chain</button>
        <button type="button" style={input} onClick={exportCsv}>Export CSV</button>
        {hasRole('Admin', 'Analyst') ? <button type="button" style={input} onClick={importActions}>Import executor audit</button> : null}
        {data ? (
          <span style={{ ...small, marginLeft: 'auto' }}>
            {data.chain.entries} entries, chain head <code title={data.chain.head}>{short(data.chain.head)}</code>
          </span>
        ) : null}
      </div>

      {chain ? (
        <div style={{ ...banner, borderColor: chain.ok ? 'var(--success)' : 'var(--critical)' }}>
          {chain.ok
            ? `The chain of ${chain.entries} entries is intact.`
            : `Chain broken at entry #${chain.broken_at}: ${chain.reason}`}
        </div>
      ) : null}
      {notice ? <div style={{ ...banner, borderColor: 'var(--accent)' }}>{notice}</div> : null}
      {error ? <div style={{ color: 'var(--danger)', marginBottom: 12 }}>{error}</div> : null}

      <DataTable
        columns={columns}
        rows={data?.items ?? []}
        rowKey={(e) => String(e.seq)}
        onRowClick={setSelected}
        emptyMessage={data ? 'No audit entries match these filters' : 'Loading...'}
      />
      {data ? <Pager page={page} total={data.total} pageSize={PAGE_SIZE} onPage={setPage} /> : null}

      <DetailDrawer open={selected !== null} title={selected ? `Entry #${selected.seq}` : ''} onClose={() => setSelected(null)}>
        {selected ? (
          <div style={{ display: 'grid', gap: 14, fontSize: 14 }}>
            <div><span style={small}>When</span><br />{when(selected.ts)} UTC</div>
            <div><span style={small}>Actor</span><br />{selected.actor}</div>
            <div><span style={small}>Action</span><br />{selected.action} on {selected.target || '-'}</div>
            <div><Pill text={selected.result} color={RESULT_COLOR[selected.result] ?? 'var(--text-muted)'} /> {selected.sample ? <Pill text="sample" color="var(--medium)" /> : null}</div>
            <div><span style={small}>Correlation id</span><br />{selected.correlation_id || '-'}</div>
            <div>
              <span style={small}>Details</span>
              <pre style={{ background: 'var(--bg-panel)', padding: 10, borderRadius: 10, overflow: 'auto', fontSize: 12 }}>
                {JSON.stringify(selected.details, null, 2)}
              </pre>
            </div>
            <div><span style={small}>Previous hash</span><br /><code style={{ wordBreak: 'break-all' }}>{selected.prev_hash}</code></div>
            <div><span style={small}>This entry hash</span><br /><code style={{ wordBreak: 'break-all' }}>{selected.hash}</code></div>
          </div>
        ) : null}
      </DetailDrawer>
    </section>
  )
}

const card: CSSProperties = { background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 14, padding: 16 }
const small: CSSProperties = { color: 'var(--text-muted)', fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 6 }
const input: CSSProperties = {
  background: 'var(--bg-panel)',
  color: 'var(--text)',
  border: '1px solid var(--border)',
  borderRadius: 10,
  padding: '8px 12px',
}
const banner: CSSProperties = {
  border: '1px solid var(--border)',
  background: 'var(--bg-panel)',
  borderRadius: 10,
  padding: '10px 14px',
  marginBottom: 12,
  fontSize: 13,
}
const tabButton: CSSProperties = { ...input, cursor: 'pointer', fontWeight: 600 }
const tabActive: CSSProperties = { borderColor: 'var(--accent)', color: 'var(--accent)' }
