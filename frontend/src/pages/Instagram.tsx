import { useEffect, useState } from 'react'
import { Eye, Users, Heart, MessageCircle, MousePointer, Camera, RefreshCw, LogIn, AlertCircle } from 'lucide-react'
import StatCard from '../components/StatCard'
import { api, type YouTubeMetric, type YouTubeAccount } from '../services/api'

type ExtractionStatus = { running: boolean; lastResult: string | null; error: string | null }

export default function Instagram() {
  const [accounts, setAccounts] = useState<YouTubeAccount[]>([])
  const [metrics, setMetrics] = useState<YouTubeMetric[]>([])
  const [status, setStatus] = useState<ExtractionStatus>({ running: false, lastResult: null, error: null })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    setLoading(true)
    try {
      const [accts, mets] = await Promise.all([
        api.instagram.accounts().catch(() => [] as YouTubeAccount[]),
        api.instagram.metrics().catch(() => [] as YouTubeMetric[]),
      ])
      setAccounts(accts)
      setMetrics(mets)
    } finally {
      setLoading(false)
    }
  }

  async function handleLogin() {
    setStatus({ running: true, lastResult: null, error: null })
    try {
      const res = await api.instagram.login()
      setStatus({ running: false, lastResult: res.message, error: res.status === 'failed' ? res.message : null })
      if (res.status === 'authenticated') loadData()
    } catch (e) {
      setStatus({ running: false, lastResult: null, error: String(e) })
    }
  }

  async function handleExtract(accountId: string) {
    const today = new Date().toISOString().slice(0, 10)
    const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10)
    setStatus({ running: true, lastResult: null, error: null })
    try {
      const res = await api.instagram.extract({ account_id: accountId, date_start: weekAgo, date_end: today })
      setStatus({
        running: false,
        lastResult: `Extracted ${res.metrics_extracted} metrics (${res.status})`,
        error: res.errors.length ? res.errors.join('; ') : null,
      })
      if (res.status === 'completed') loadData()
    } catch (e) {
      setStatus({ running: false, lastResult: null, error: String(e) })
    }
  }

  function metricValue(name: string): number | null {
    const m = metrics.find((m) => m.metric_name === name)
    return m?.metric_value ?? null
  }

  function formatNum(val: number | null): string {
    if (val === null) return '—'
    if (Math.abs(val) >= 1_000_000) return (val / 1_000_000).toFixed(1) + 'M'
    if (Math.abs(val) >= 1_000) return (val / 1_000).toFixed(1) + 'K'
    return val.toLocaleString()
  }

  const hasData = metrics.length > 0
  const hasAccounts = accounts.length > 0

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Instagram Analytics</h2>
          <p className="text-sm text-slate-500">Reach, engagement, Reels, follower growth</p>
        </div>
        <div className="flex gap-2">
          {hasAccounts && (
            <button
              onClick={() => handleExtract(accounts[0].account_id)}
              disabled={status.running}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-purple-600 to-pink-500 text-white rounded-lg text-sm font-medium hover:from-purple-700 hover:to-pink-600 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${status.running ? 'animate-spin' : ''}`} />
              Pull Analytics
            </button>
          )}
          <button
            onClick={handleLogin}
            disabled={status.running}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 text-white rounded-lg text-sm font-medium hover:bg-slate-900 disabled:opacity-50"
          >
            <LogIn className="w-4 h-4" />
            {hasAccounts ? 'Re-authenticate' : 'Connect Account'}
          </button>
        </div>
      </div>

      {/* Status bar */}
      {(status.lastResult || status.error) && (
        <div className={`mb-4 px-4 py-2 rounded-lg text-sm flex items-center gap-2 ${status.error ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-green-50 text-green-700 border border-green-200'}`}>
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {status.error || status.lastResult}
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-slate-400">Loading...</div>
      ) : !hasData ? (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
          <div className="text-4xl mb-3">📸</div>
          <h3 className="text-lg font-semibold text-slate-700 mb-2">No Instagram data yet</h3>
          <p className="text-sm text-slate-500 mb-4">
            {hasAccounts
              ? 'Account connected. Click "Pull Analytics" to extract data from Instagram Insights.'
              : 'Click "Connect Account" to log in to Instagram and start collecting analytics. Requires a Professional (Business or Creator) account.'}
          </p>
          {!hasAccounts && (
            <code className="bg-slate-100 px-3 py-1.5 rounded text-sm text-slate-700">
              layan login --platform instagram
            </code>
          )}
        </div>
      ) : (
        <>
          {/* Metric cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <StatCard
              title="Accounts Reached"
              value={formatNum(metricValue('accounts_reached'))}
              subtitle="Last 7 days"
              icon={Eye}
              color="text-purple-500"
            />
            <StatCard
              title="Accounts Engaged"
              value={formatNum(metricValue('accounts_engaged'))}
              subtitle="Last 7 days"
              icon={Heart}
              color="text-pink-500"
            />
            <StatCard
              title="Total Followers"
              value={formatNum(metricValue('total_followers'))}
              subtitle="Current"
              icon={Users}
              color="text-blue-500"
            />
            <StatCard
              title="Profile Visits"
              value={formatNum(metricValue('profile_visits'))}
              subtitle="Last 7 days"
              icon={MousePointer}
              color="text-amber-500"
            />
          </div>

          {/* All metrics table */}
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <div className="px-5 py-3 border-b border-slate-100 flex items-center gap-2">
              <Camera className="w-4 h-4 text-purple-500" />
              <span className="font-semibold text-slate-700 text-sm">All Extracted Metrics</span>
              <span className="text-xs text-slate-400 ml-auto">{metrics.length} metrics</span>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 text-xs border-b border-slate-100">
                  <th className="px-5 py-2 font-medium">Metric</th>
                  <th className="px-5 py-2 font-medium">Value</th>
                  <th className="px-5 py-2 font-medium">Period</th>
                  <th className="px-5 py-2 font-medium">Source</th>
                  <th className="px-5 py-2 font-medium">Extracted</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map((m) => (
                  <tr key={m.id} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="px-5 py-2 font-medium text-slate-700">{m.metric_name}</td>
                    <td className="px-5 py-2 text-slate-900">{formatNum(m.metric_value)}</td>
                    <td className="px-5 py-2 text-slate-500">{m.date_start} → {m.date_end}</td>
                    <td className="px-5 py-2 text-slate-400">{m.extraction_method || '—'}</td>
                    <td className="px-5 py-2 text-slate-400">
                      {m.extracted_at ? new Date(m.extracted_at).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
