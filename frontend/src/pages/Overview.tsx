import { useEffect, useState } from 'react'
import { Users, BarChart3, Database, RefreshCw } from 'lucide-react'
import StatCard from '../components/StatCard'
import PlatformBarChart from '../components/PlatformBarChart'
import ExtractionHistoryChart from '../components/ExtractionHistoryChart'
import { api, type SystemStatus } from '../services/api'

type PlatformSummary = { platform: string; metric_count: number; unique_metrics: number; total_runs: number; successful_runs: number; last_extraction: string | null }
type ExtractionRun = { run_id: string; platform: string; status: string; metrics_extracted: number; metrics_failed: number; duration_seconds: number | null; started_at: string | null; completed_at: string | null }

export default function Overview() {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [platformSummary, setPlatformSummary] = useState<PlatformSummary[]>([])
  const [extractionHistory, setExtractionHistory] = useState<ExtractionRun[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    api.systemStatus().then(setStatus).catch((e) => setError(e.message))
    api.platformSummary().then(setPlatformSummary).catch(() => {})
    api.extractionHistory().then(setExtractionHistory).catch(() => {})
  }, [])

  if (error) {
    return (
      <div className="p-8">
        <h2 className="text-xl font-bold text-slate-900 mb-4">Overview</h2>
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm">
          Backend unavailable: {error}. Start the backend with <code className="bg-red-100 px-1 rounded">layan run</code>.
        </div>
      </div>
    )
  }

  if (!status) {
    return (
      <div className="p-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-slate-200 rounded w-48" />
          <div className="grid grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-28 bg-slate-200 rounded-xl" />
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Overview</h2>
          <p className="text-sm text-slate-500">Cross-platform analytics summary</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          title="Accounts"
          value={status.accounts.total}
          subtitle={`${status.accounts.authenticated} authenticated`}
          icon={Users}
        />
        <StatCard
          title="Account Metrics"
          value={status.metrics.account_metrics.toLocaleString()}
          icon={BarChart3}
        />
        <StatCard
          title="Content Metrics"
          value={status.metrics.content_metrics.toLocaleString()}
          icon={Database}
        />
        <StatCard
          title="Pending Sync"
          value={status.sync.pending}
          subtitle={status.last_extraction.completed_at
            ? `Last: ${new Date(status.last_extraction.completed_at).toLocaleDateString()}`
            : 'No extractions yet'}
          icon={RefreshCw}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <PlatformBarChart data={platformSummary} title="Metrics by Platform" />
        <ExtractionHistoryChart data={extractionHistory} title="Recent Extractions" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h3 className="text-lg font-semibold text-slate-900 mb-4">System Status</h3>
          <div className="space-y-3">
            <StatusRow label="AI Provider" value={status.ai.provider} ok={status.ai.configured} />
            <StatusRow label="Google Sheets" value={status.google_sheets.configured ? 'Connected' : 'Not configured'} ok={status.google_sheets.configured} />
            <StatusRow
              label="Last Extraction"
              value={status.last_extraction.platform
                ? `${status.last_extraction.platform} — ${status.last_extraction.status}`
                : 'None'}
              ok={status.last_extraction.status === 'completed'}
            />
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h3 className="text-lg font-semibold text-slate-900 mb-4">Getting Started</h3>
          <ol className="space-y-2 text-sm text-slate-600 list-decimal list-inside">
            <li>Configure your AI API key in <code className="bg-slate-100 px-1 rounded">.env</code></li>
            <li>Run <code className="bg-slate-100 px-1 rounded">layan login --platform youtube</code></li>
            <li>Run <code className="bg-slate-100 px-1 rounded">layan pull --platform youtube</code></li>
            <li>View extracted analytics on the YouTube page</li>
          </ol>
        </div>
      </div>
    </div>
  )
}

function StatusRow({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
      <span className="text-sm text-slate-600">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-slate-900">{value}</span>
        <div className={`w-2 h-2 rounded-full ${ok ? 'bg-green-500' : 'bg-slate-300'}`} />
      </div>
    </div>
  )
}
