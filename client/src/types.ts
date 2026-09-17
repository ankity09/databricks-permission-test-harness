// Mirrors the backend Pydantic models.

export type Tab = 'uc-data' | 'workspace' | 'scenarios' | 'activity'

export interface ActionProbe {
  kind: 'sql' | 'permission-check'
  statement?: string
  api?: string
  level?: string
}

export interface ActionDescriptor {
  id: string
  tab: Tab
  label: string
  grant_sql: string
  revoke_sql: string
  probe: ActionProbe
  side_effect: 'none' | 'write-guarded'
}

export type ProbeStatus =
  | 'pass'
  | 'fail_denied'
  | 'grant_failed'
  | 'bad_input'
  | 'error'

export interface ProbeResult {
  status: ProbeStatus
  detail: string
  raw_error: string
  rows?: Array<Record<string, unknown>> | null
}

export interface PromoteInfo {
  grant_sql: string
  uc_deep_link: string
}

export interface Identity {
  user_name?: string | null
  display_name?: string | null
  active?: boolean | null
  id?: string | null
}

export interface MeResponse {
  admin: Identity
  app_sp: Identity | { error: string }
  configured_sp_application_id: string
  obo: string
}

export interface ActivityEntry {
  ts: string
  kind: 'apply' | 'probe' | 'revoke' | 'promote' | 'reset'
  action_id: string
  securable: string
  detail: string
}

// ---- v2 ----

export interface ScenarioItem {
  action_id: string
  securable: string
}

export interface Scenario {
  id: string
  name: string
  description?: string
  created_by?: string
  items: ScenarioItem[]
  is_seed?: boolean
}

export interface MatrixRow {
  action_id: string
  securable: string
  status: ProbeStatus
  detail: string
}

export interface MatrixResult {
  overall: 'pass' | 'fail'
  results: MatrixRow[]
}

export interface ActivityRow {
  id: string
  session_id?: string
  ts?: string
  admin_email?: string
  sp_id?: string
  event_type: string
  action_id?: string
  securable?: string
  verdict?: string | null
  raw_message?: string
  scenario_id?: string | null
}

export interface DbHealth {
  ok: boolean
  error?: string
}

export interface ActivityResponse {
  events: ActivityRow[]
  db: DbHealth
}

export interface ToolChip {
  tool: string
  summary: string
  verdict?: ProbeStatus | string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

// ---- v3: query runner + reach sweep ----

export interface Governance {
  masked_columns: string[]
  row_filter: boolean
  detail: string
}

export interface QueryResult {
  columns: string[]
  rows: unknown[][]
  truncated: boolean
  error: string | null
  governance: Governance
}

export type SweepCell = 'hold' | 'hole' | 'error'

export interface SweepRow {
  object: string
  action: 'use_catalog' | 'use_schema' | 'select'
  result: SweepCell
  detail: string
  raw: string
}

export interface SweepVerdict {
  status: 'boundaries_hold' | 'holes_found'
  holes: number
  checked: number
}

export interface SweepResult {
  matrix: SweepRow[]
  verdict: SweepVerdict
  scope_note: string
}
