import { useEffect, useState } from 'react'
import { api, type HealthStatus } from '../services/api'

export default function Settings() {
  const [health, setHealth] = useState<HealthStatus | null>(null)

  useEffect(() => {
    api.health().then(setHealth).catch(() => {})
  }, [])

  return (
    <div className="p-8">
      <h2 className="text-xl font-bold text-slate-900 mb-2">Settings</h2>
      <p className="text-sm text-slate-500 mb-6">Account, AI, extraction, and sync configuration</p>

      <div className="space-y-6">
        <Section title="AI Provider">
          <SettingRow label="Provider" value={health?.ai_provider ?? '—'} />
          <SettingRow label="API Key" value={health?.ai_configured ? 'Configured' : 'Not set'} />
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
          <SettingRow label="Status" value="Not configured" />
          <p className="text-xs text-slate-400 mt-2">
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
