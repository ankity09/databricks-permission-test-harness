import axios from 'axios'
import type {
  ActionDescriptor,
  ActivityResponse,
  ChatMessage,
  MatrixResult,
  MeResponse,
  ProbeResult,
  PromoteInfo,
  QueryResult,
  Scenario,
  ScenarioItem,
  SweepResult,
} from './types'

const api = axios.create({
  baseURL: import.meta.env.DEV ? 'http://localhost:8000/api' : '/api',
})

export async function getActions(): Promise<ActionDescriptor[]> {
  const { data } = await api.get<ActionDescriptor[]>('/actions')
  return data
}

export async function getMe(): Promise<MeResponse> {
  const { data } = await api.get<MeResponse>('/me')
  return data
}

export async function applyGrant(action_id: string, securable: string) {
  const { data } = await api.post('/grant/apply', { action_id, securable })
  return data
}

export async function revokeGrant(action_id: string, securable: string) {
  const { data } = await api.post('/grant/revoke', { action_id, securable })
  return data
}

export async function probe(
  action_id: string,
  securable: string,
  opts: { really_do?: boolean; negative_test?: boolean } = {},
): Promise<ProbeResult> {
  const { data } = await api.post<ProbeResult>('/probe', {
    action_id,
    securable,
    really_do: opts.really_do ?? false,
    negative_test: opts.negative_test ?? false,
  })
  return data
}

export async function promote(
  action_id: string,
  securable: string,
  principal: string,
): Promise<PromoteInfo> {
  const { data } = await api.post<PromoteInfo>(
    `/promote?principal=${encodeURIComponent(principal)}`,
    { action_id, securable },
  )
  return data
}

export async function resetSp() {
  const { data } = await api.post('/reset-sp')
  return data
}

// ---- v2 ----

export async function getActivity(
  filters: {
    admin_email?: string
    verdict?: string
    securable?: string
    scenario_id?: string
    limit?: number
  } = {},
): Promise<ActivityResponse> {
  const { data } = await api.get<ActivityResponse>('/activity', { params: filters })
  return data
}

export async function getScenarios(): Promise<{ scenarios: Scenario[] }> {
  const { data } = await api.get<{ scenarios: Scenario[] }>('/scenarios')
  return data
}

export async function saveScenario(s: {
  name: string
  description?: string
  items: ScenarioItem[]
}): Promise<{ id: string }> {
  const { data } = await api.post<{ id: string }>('/scenarios', s)
  return data
}

export async function runScenario(items: ScenarioItem[]): Promise<MatrixResult> {
  const { data } = await api.post<MatrixResult>('/scenarios/run', { items })
  return data
}

export async function agentChat(
  messages: ChatMessage[],
): Promise<{ content: string }> {
  const { data } = await api.post<{ content: string }>('/agent/chat', { messages })
  return data
}

// ---- v3 ----

export async function runQuery(
  body: { sql?: string; table?: string; limit?: number },
): Promise<QueryResult> {
  const { data } = await api.post<QueryResult>('/query', body)
  return data
}

export async function runSweep(securable: string): Promise<SweepResult> {
  const { data } = await api.post<SweepResult>('/sweep', { securable })
  return data
}

export default api
