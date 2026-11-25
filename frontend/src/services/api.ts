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

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const resp = await fetch(`${BASE_URL}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) throw new Error(`API error: ${resp.status}`)
  return resp.json()
}

export interface YouTubeMetric {
  id: number
  account_id: string
  metric_name: string
  metric_value: number | null
  date_start: string
  date_end: string
  source_dashboard: string | null
  extraction_method: string | null
  extracted_at: string | null
}

export interface YouTubeAccount {
  id: number
  account_id: string
  account_name: string
  account_url: string | null
  auth_status: string
  last_auth_at: string | null
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

  // Instagram-specific
  instagram: {
    accounts: () => fetchJson<YouTubeAccount[]>('/instagram/accounts'),
    verifyAuth: () => postJson<{ authenticated: boolean; username: string | null }>('/instagram/verify-auth', {}),
    login: (accountId: string = 'default') => postJson<{ status: string; username?: string; message: string }>('/instagram/login', { account_id: accountId }),
    extract: (params: { account_id: string; date_start: string; date_end: string; job_type?: string }) => postJson<{ run_id: string; status: string; metrics_extracted: number; errors: string[]; warnings: string[] }>('/instagram/extract', params),
    metrics: (params?: { account_id?: string; metric_name?: string }) => {
      const qs = new URLSearchParams()
      if (params?.account_id) qs.set('account_id', params.account_id)
      if (params?.metric_name) qs.set('metric_name', params.metric_name)
      const q = qs.toString()
      return fetchJson<YouTubeMetric[]>(`/instagram/metrics${q ? '?' + q : ''}`)
    },
  },

  // TikTok-specific
  tiktok: {
    accounts: () => fetchJson<YouTubeAccount[]>('/tiktok/accounts'),
    verifyAuth: () => postJson<{ authenticated: boolean; username: string | null }>('/tiktok/verify-auth', {}),
    login: (accountId: string = 'default') => postJson<{ status: string; username?: string; message: string }>('/tiktok/login', { account_id: accountId }),
    extract: (params: { account_id: string; date_start: string; date_end: string; job_type?: string }) => postJson<{ run_id: string; status: string; metrics_extracted: number; errors: string[]; warnings: string[] }>('/tiktok/extract', params),
    metrics: (params?: { account_id?: string; metric_name?: string }) => {
      const qs = new URLSearchParams()
      if (params?.account_id) qs.set('account_id', params.account_id)
      if (params?.metric_name) qs.set('metric_name', params.metric_name)
      const q = qs.toString()
      return fetchJson<YouTubeMetric[]>(`/tiktok/metrics${q ? '?' + q : ''}`)
    },
  },

  // YouTube-specific
  youtube: {
    accounts: () => fetchJson<YouTubeAccount[]>('/youtube/accounts'),
    verifyAuth: () => postJson<{ authenticated: boolean; channel_id: string | null }>('/youtube/verify-auth', {}),
    login: (accountId: string = 'default') => postJson<{ status: string; channel_id?: string; message: string }>('/youtube/login', { account_id: accountId }),
    extract: (params: { account_id: string; date_start: string; date_end: string; job_type?: string }) => postJson<{ run_id: string; status: string; metrics_extracted: number; errors: string[]; warnings: string[] }>('/youtube/extract', params),
    metrics: (params?: { account_id?: string; metric_name?: string }) => {
      const qs = new URLSearchParams()
      if (params?.account_id) qs.set('account_id', params.account_id)
      if (params?.metric_name) qs.set('metric_name', params.metric_name)
      const q = qs.toString()
      return fetchJson<YouTubeMetric[]>(`/youtube/metrics${q ? '?' + q : ''}`)
    },
  },
}
