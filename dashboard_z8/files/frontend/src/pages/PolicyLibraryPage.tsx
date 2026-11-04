import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { apiFetch } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { DataTable, type Column } from '../components/DataTable'
import { DetailDrawer } from '../components/DetailDrawer'
import { KpiTile } from '../components/KpiTile'
import { PageHeader } from '../components/PageHeader'
import type { GrcException, GrcPolicies, GrcPolicy } from '../grcTypes'

const APPROVAL_COLOR: Record<string, string> = {
  Approved: 'var(--success)',
  Draft: 'var(--medium)',
  Retired: 'var(--text-muted)',
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

export function PolicyLibraryPage() {
  const { hasRole, user } = useAuth()
  const [data, setData] = useState<GrcPolicies | null>(null)
  const [error, setError] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    apiFetch<GrcPolicies>('/api/grc/policies')
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load'))
  }, [])

  useEffect(load, [load])

  const selected = data?.policies.find((p) => p.id === selectedId) ?? null
  const approved = data?.policies.filter((p) => p.approval_status === 'Approved').length ?? 0

  async function acknowledge(policy: GrcPolicy) {
    setBusy(true)
    try {
      await apiFetch(`/api/grc/policies/${policy.id}/acknowledge`, { method: 'POST' })
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not acknowledge')
    } finally {
      setBusy(false)
    }
  }

  const columns: Column<GrcPolicy>[] = [
    { key: 'id', header: 'ID', render: (p) => <strong style={{ whiteSpace: 'nowrap' }}>{p.id}</strong>, width: '100px' },
    { key: 'title', header: 'Policy', render: (p) => p.title },
    { key: 'version', header: 'Version', render: (p) => `v${p.version}` },
    { key: 'owner', header: 'Owner', render: (p) => p.owner },
    { key: 'status', header: 'Approval', render: (p) => <Pill text={p.approval_status} color={APPROVAL_COLOR[p.approval_status]} /> },
    {
      key: 'review',
      header: 'Review date',
      render: (p) => (
        <span>
          {p.review_date} {p.review_overdue ? <Pill text="overdue" color="var(--critical)" /> : null}
        </span>
      ),
    },
    { key: 'acks', header: 'Acknowledged', render: (p) => p.acknowledgements.length },
    {
      key: 'enforces',
      header: 'Enforces',
      render: (p) =>
        p.drives.length === 0 ? (
          <span style={{ color: 'var(--text-muted)' }}>guard / manual</span>
        ) : (
          <span style={{ display: 'grid', gap: 2 }}>
            {p.drives.map((d) => (
              <span key={`${d.playbook}.${d.parameter}`} style={{ fontSize: 12 }}>
                {d.playbook}: {d.parameter} = {String(d.value)}
              </span>
            ))}
          </span>
        ),
    },
  ]

  const exceptionColumns: Column<GrcException>[] = [
    { key: 'id', header: 'Exception', render: (e) => <strong>{e.id}</strong> },
    { key: 'policy', header: 'Policy', render: (e) => e.policy_id },
    { key: 'param', header: 'Parameter = value', render: (e) => `${e.parameter} = ${String(e.value)}` },
    { key: 'reason', header: 'Reason', render: (e) => e.reason },
    { key: 'approver', header: 'Approver', render: (e) => e.approver },
    {
      key: 'expires',
      header: 'Expires',
      render: (e) => (
        <span>
          {e.expires_on} <Pill text={e.expired ? 'expired' : 'active'} color={e.expired ? 'var(--critical)' : 'var(--success)'} />
        </span>
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        title="Policy Library"
        subtitle="Policies that execute: an approved policy sets the parameters its playbook runs with."
      />

      {error ? <div style={{ color: 'var(--danger)', marginBottom: 12 }}>{error}</div> : null}
      {!data && !error ? <div style={{ color: 'var(--text-muted)' }}>Loading...</div> : null}

      {data ? (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12, marginBottom: 16 }}>
            <KpiTile label="Policies" value={data.policies.length} />
            <KpiTile label="Approved" value={approved} hint="only these change playbooks" />
            <KpiTile label="Reviews overdue" value={data.overdue_reviews} />
            <KpiTile label="Expired exceptions" value={data.expired_exceptions} />
          </div>

          <section style={{ ...card, marginBottom: 16 }}>
            <h3 style={heading}>Policies</h3>
            <DataTable columns={columns} rows={data.policies} rowKey={(p) => p.id} onRowClick={(p) => setSelectedId(p.id)} />
          </section>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
            <section style={card}>
              <h3 style={heading}>Exceptions</h3>
              <DataTable columns={exceptionColumns} rows={data.exceptions} rowKey={(e) => e.id} emptyMessage="No exceptions" />
            </section>

            <section style={card}>
              <h3 style={heading}>What the playbooks run with now</h3>
              <div style={{ display: 'grid', gap: 10 }}>
                {Object.keys(data.effective_parameters).length === 0 ? (
                  <span style={{ color: 'var(--text-muted)' }}>No policy drives a playbook</span>
                ) : null}
                {Object.entries(data.effective_parameters).map(([playbook, params]) => (
                  <div key={playbook} style={{ background: 'var(--bg-panel)', borderRadius: 10, padding: '10px 12px', fontSize: 13 }}>
                    <strong>{playbook}</strong>
                    {Object.entries(params).map(([k, v]) => (
                      <div key={k} style={{ color: 'var(--text-muted)' }}>
                        {k} = {String(v)}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </section>
          </div>
        </>
      ) : null}

      <DetailDrawer open={selected !== null} title={selected ? `${selected.id} v${selected.version}` : ''} onClose={() => setSelectedId(null)}>
        {selected ? (
          <div style={{ display: 'grid', gap: 14, fontSize: 14 }}>
            <strong>{selected.title}</strong>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Pill text={selected.approval_status} color={APPROVAL_COLOR[selected.approval_status]} />
              {selected.review_overdue ? <Pill text="review overdue" color="var(--critical)" /> : null}
            </div>
            <div><span style={label}>Owner</span><br />{selected.owner}</div>
            <div>
              <span style={label}>Approval</span>
              <br />
              {selected.approved_by ? `${selected.approved_by} on ${selected.approved_on ?? '-'}` : 'Not approved'}
            </div>
            <div><span style={label}>Next review</span><br />{selected.review_date}</div>

            <div>
              <span style={label}>Playbook parameters it sets</span>
              {selected.drives.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', marginTop: 4 }}>None (enforced by the Policy Guard or manual process)</div>
              ) : (
                selected.drives.map((d) => (
                  <div key={`${d.playbook}.${d.parameter}`} style={{ background: 'var(--bg-panel)', borderRadius: 10, padding: '8px 12px', marginTop: 6 }}>
                    <strong>{d.playbook}</strong>
                    <div>{d.parameter} = {String(d.value)}</div>
                  </div>
                ))
              )}
            </div>

            <div>
              <span style={label}>Linked controls</span>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                {selected.linked_controls.map((c) => <Pill key={c} text={c} color="var(--accent)" />)}
              </div>
            </div>

            <div style={{ display: 'grid', gap: 6, justifyItems: 'start' }}>
              <span style={label}>Acknowledged by ({selected.acknowledgements.length})</span>
              {selected.acknowledgements.map((a) => (
                <div key={a.user} style={{ marginTop: 4 }}>{a.user} <span style={{ color: 'var(--text-muted)' }}>on {a.date}</span></div>
              ))}
              {hasRole('Admin', 'Analyst') && !selected.acknowledgements.some((a) => a.user === user?.username) ? (
                <button type="button" disabled={busy} onClick={() => acknowledge(selected)} style={primaryButton}>
                  {busy ? 'Saving...' : 'I acknowledge this policy'}
                </button>
              ) : null}
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
const label: CSSProperties = { color: 'var(--text-muted)', fontSize: 12 }
const primaryButton: CSSProperties = {
  background: 'var(--accent)',
  color: '#fff',
  border: 'none',
  borderRadius: 10,
  padding: '9px 16px',
  fontWeight: 600,
  cursor: 'pointer',
}
