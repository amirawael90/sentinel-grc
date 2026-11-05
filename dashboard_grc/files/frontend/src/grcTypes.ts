export interface GrcFunction {
  name: string
  percent: number
}

export interface GrcFramework {
  id: string
  label: string
  percent: number
  counts: Record<string, number>
  functions: GrcFunction[]
}

export interface GrcGap {
  framework: string
  category: string
  points_lost: number
}

export interface GrcQuickWin {
  id: string
  status: string
  missing_features: string[]
}

export interface GrcOverview {
  generated_at: string
  overall: number
  total_controls: number
  frameworks: GrcFramework[]
  gaps: GrcGap[]
  quick_wins: GrcQuickWin[]
  evidence: {
    items: number
    controls_fresh: number
    controls_stale: number
    controls_none: number
  }
}

export interface GrcControl {
  id: string
  framework: string
  function: string | null
  category: string
  title: string | null
  description: string
  status: string
  maturity: number
  owner: string
  review_date: string | null
  platform_features: string[]
  evidence: { fresh: number; stale: number; state: 'fresh' | 'stale' | 'no_evidence' }
}

export interface GrcControlPage {
  total: number
  page: number
  page_size: number
  items: GrcControl[]
}

export interface GrcDrive {
  playbook: string
  parameter: string
  value: string | number | boolean
}

export interface GrcPolicy {
  id: string
  title: string
  version: string
  owner: string
  approval_status: 'Draft' | 'Approved' | 'Retired'
  approved_by: string | null
  approved_on: string | null
  review_date: string
  review_overdue: boolean
  acknowledgements: { user: string; date: string }[]
  drives: GrcDrive[]
  linked_controls: string[]
}

export interface GrcException {
  id: string
  policy_id: string
  parameter: string
  value: string | number | boolean
  reason: string
  approver: string
  expires_on: string
  expired: boolean
}

export interface GrcPolicies {
  policies: GrcPolicy[]
  exceptions: GrcException[]
  effective_parameters: Record<string, Record<string, string | number | boolean>>
  overdue_reviews: number
  expired_exceptions: number
}

export interface GrcEvidenceItem {
  id: string
  source: string
  path: string
  sha256: string
  size: number
  first_collected_at: string
  last_verified_at: string
  max_age_days: number
  linked_controls: string[]
  state: 'fresh' | 'stale'
}

export interface GrcEvidencePage {
  total: number
  page: number
  page_size: number
  items: GrcEvidenceItem[]
  sources: string[]
}

export interface GrcEvidenceCheck {
  ok: boolean
  checked: number
  problems: string[]
}

export interface GrcAuditEntry {
  seq: number
  ts: string
  actor: string
  action: string
  target: string
  result: string
  correlation_id: string
  details: Record<string, unknown>
  sample: boolean
  prev_hash: string
  hash: string
}

export interface GrcAuditPage {
  total: number
  page: number
  page_size: number
  items: GrcAuditEntry[]
  chain: { entries: number; head: string }
  has_sample: boolean
}

export interface GrcChainCheck {
  ok: boolean
  entries: number
  head: string
  broken_at: number | null
  reason: string | null
}

export interface GrcReportRun {
  generated_at: string
  period_start: string
  period_end: string
  days?: number
  audience?: string
  files: { executive?: string; technical?: string }
}
