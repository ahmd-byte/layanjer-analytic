import { useEffect, useState } from 'react'
import { RefreshCw, AlertCircle, CheckCircle2 } from 'lucide-react'
import { api, type HealthStatus } from '../services/api'

type SheetsStatus = {
  configured: boolean
  spreadsheet_id: string | null
  credentials_set: boolean
  sync_queue: { pending: number; synced: number }
  last_sync_at: string | null
}

type AIStatus = {
  provider: string
  model: string
  configured: boolean
  available: boolean
  budget: { daily_limit: number; spent_today: number; remaining: number; within_budget: boolean }
}

export default function Settings() {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [sheets, setSheets] = useState<SheetsStatus | null>(null)
  const [aiStatus, setAIStatus] = useState<AIStatus | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    api.health().then(setHealth).catch(() => {})
    api.sheets.status().then(setSheets).catch(() => {})
    api.ai.status().then(setAIStatus).catch(() => {})
  }, [])

  async function handleSync() {
    setSyncing(true)
    setSyncMsg(null)
    try {
      const res = await api.sheets.sync()
      setSyncMsg({
        ok: res.success,
        text: res.success
          ? `Synced ${res.account_metrics_synced} account metrics, ${res.content_metrics_synced} content metrics, ${res.summary_rows} summary rows`
          : res.errors.join('; '),
      })
      api.sheets.status().then(setSheets).catch(() => {})
    } catch (e) {
      setSyncMsg({ ok: false, text: String(e) })
    } finally {
      setSyncing(false)
    }
  }

  async function handleTestConnection() {
    setSyncMsg(null)
    try {
      const res = await api.sheets.testConnection()
      setSyncMsg({
        ok: res.connected,
        text: res.connected
          ? `Connected to "${res.spreadsheet_title}"`
          : res.error || 'Connection failed',
      })
    } catch (e) {
      setSyncMsg({ ok: false, text: String(e) })
    }
  }

  return (
    <div className="p-8">
      <h2 className="text-xl font-bold text-slate-900 mb-2">Settings</h2>
      <p className="text-sm text-slate-500 mb-6">Account, AI, extraction, and sync configuration</p>

      <div className="space-y-6">
        <Section title="AI Provider">
          <SettingRow label="Provider" value={aiStatus?.provider ?? health?.ai_provider ?? '—'} />
          <SettingRow label="Model" value={aiStatus?.model ?? '—'} />
          <SettingRow label="API Key" value={aiStatus?.configured ? 'Configured' : 'Not set'} />
          <SettingRow label="Available" value={aiStatus?.available ? 'Yes' : 'No'} />
          {aiStatus?.budget && (
            <>
              <SettingRow label="Daily Budget" value={`$${aiStatus.budget.daily_limit.toFixed(2)}`} />
              <SettingRow label="Spent Today" value={`$${aiStatus.budget.spent_today.toFixed(4)}`} />
              <SettingRow label="Remaining" value={`$${aiStatus.budget.remaining.toFixed(4)}`} />
            </>
          )}
          <p className="text-xs text-slate-400 mt-2">
            Configure in <code className="bg-slate-100 px-1 rounded">.env</code> file: AI_PROVIDER, AI_API_KEY
          </p>
        </Section>

        <Section title="Application">
          <SettingRow label="Version" value={health?.version ?? '—'} />
          <SettingRow label="Backend" value="http://127.0.0.1:8000" />
          <SettingRow label="Timezone" value="Asia/Kuala_Lumpur" />
        </Section>

        <Section title="Google Sheets">
          <SettingRow label="Credentials" value={sheets?.credentials_set ? 'Set' : 'Not set'} />
          <SettingRow label="Spreadsheet ID" value={sheets?.spreadsheet_id ?? 'Not set'} />
          <SettingRow label="Pending Sync" value={String(sheets?.sync_queue?.pending ?? 0)} />
          <SettingRow label="Total Synced" value={String(sheets?.sync_queue?.synced ?? 0)} />
          <SettingRow
            label="Last Sync"
            value={sheets?.last_sync_at ? new Date(sheets.last_sync_at).toLocaleString() : 'Never'}
          />

          {syncMsg && (
            <div
              className={`mt-3 px-3 py-2 rounded-lg text-sm flex items-center gap-2 ${
                syncMsg.ok
                  ? 'bg-green-50 text-green-700 border border-green-200'
                  : 'bg-red-50 text-red-700 border border-red-200'
              }`}
            >
              {syncMsg.ok ? (
                <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
              ) : (
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
              )}
              {syncMsg.text}
            </div>
          )}

          <div className="flex gap-2 mt-3">
            <button
              onClick={handleTestConnection}
              className="px-3 py-1.5 text-sm font-medium bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200"
            >
              Test Connection
            </button>
            <button
              onClick={handleSync}
              disabled={syncing || !sheets?.configured}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
              {syncing ? 'Syncing...' : 'Full Sync'}
            </button>
          </div>

          <p className="text-xs text-slate-400 mt-3">
            Set GOOGLE_SHEETS_CREDENTIALS_PATH and GOOGLE_SHEETS_SPREADSHEET_ID in .env
          </p>
        </Section>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6">
      <h3 className="text-base font-semibold text-slate-900 mb-4">{title}</h3>
      {children}
    </div>
  )
}

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
      <span className="text-sm text-slate-600">{label}</span>
      <span className="text-sm font-medium text-slate-900">{value}</span>
    </div>
  )
}
