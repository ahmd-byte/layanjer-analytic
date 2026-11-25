const BASE_URL = '/api'

async function fetchJson<T>(url: string): Promise<T> {
  const resp = await fetch(`${BASE_URL}${url}`)
  if (!resp.ok) throw new Error(`API error: ${resp.status}`)
  return resp.json()
}

export interface HealthStatus {
  status: string
  version: string
  ai_provider: string
  ai_configured: boolean
}

export interface SystemStatus {
  accounts: { total: number; authenticated: number }
  metrics: { account_metrics: number; content_metrics: number }
  sync: { pending: number }
  last_extraction: { platform: string | null; status: string | null; completed_at: string | null }
  ai: { provider: string; configured: boolean }
  google_sheets: { configured: boolean }
}

export interface AccountInfo {
  id: number
  platform: string
  account_id: string
  account_name: string
  auth_status: string
  last_auth_at: string | null
}

export interface ExtractionRunInfo {
  id: number
  run_id: string
  platform: string
  account_id: string
  job_type: string
  status: string
  metrics_extracted: number
  metrics_failed: number
  error_category: string | null
  started_at: string | null
  completed_at: string | null
  duration_seconds: number | null
}

export const api = {
  health: () => fetchJson<HealthStatus>('/health'),
  systemStatus: () => fetchJson<SystemStatus>('/system/status'),
  accounts: () => fetchJson<AccountInfo[]>('/accounts/'),
  extractionRuns: (params?: { platform?: string; status?: string }) => {
    const qs = new URLSearchParams()
    if (params?.platform) qs.set('platform', params.platform)
    if (params?.status) qs.set('status', params.status)
    const q = qs.toString()
    return fetchJson<ExtractionRunInfo[]>(`/extraction/runs${q ? '?' + q : ''}`)
  },
  aiUsage: () => fetchJson<any[]>('/system/ai-usage'),
}
