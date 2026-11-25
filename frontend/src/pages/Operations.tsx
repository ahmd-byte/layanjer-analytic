import { useEffect, useState } from 'react'
import { Plus, Play, Pause, Trash2, Zap, Clock, AlertCircle } from 'lucide-react'
import { api, type ExtractionRunInfo, type ScheduleInfo } from '../services/api'

export default function Operations() {
  const [runs, setRuns] = useState<ExtractionRunInfo[]>([])
  const [schedules, setSchedules] = useState<ScheduleInfo[]>([])
  const [schedulerRunning, setSchedulerRunning] = useState(false)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [triggering, setTriggering] = useState<number | null>(null)
  const [actionMsg, setActionMsg] = useState<{ text: string; ok: boolean } | null>(null)

  useEffect(() => {
    loadAll()
  }, [])

  async function loadAll() {
    api.extractionRuns().then(setRuns).catch((e) => setError(e.message))
    api.scheduler.list().then(setSchedules).catch(() => {})
    api.scheduler.status().then((s) => setSchedulerRunning(s.running)).catch(() => {})
  }

  async function handleTrigger(id: number) {
    setTriggering(id)
    setActionMsg(null)
    try {
      const res = await api.scheduler.trigger(id)
      setActionMsg({ text: res.error || `Completed — ${res.metrics_saved} metrics`, ok: !res.error })
      loadAll()
    } catch (e) {
      setActionMsg({ text: String(e), ok: false })
    } finally {
      setTriggering(null)
    }
  }

  async function handleToggle(s: ScheduleInfo) {
    try {
      await api.scheduler.update(s.id, { is_active: !s.is_active })
      loadAll()
    } catch (e) {
      setActionMsg({ text: String(e), ok: false })
    }
  }

  async function handleDelete(id: number) {
    try {
      await api.scheduler.delete(id)
      setSchedules((prev) => prev.filter((s) => s.id !== id))
    } catch (e) {
      setActionMsg({ text: String(e), ok: false })
    }
  }

  function formatInterval(mins: number): string {
    if (mins >= 1440) return `${(mins / 1440).toFixed(0)}d`
    if (mins >= 60) return `${(mins / 60).toFixed(0)}h`
    return `${mins}m`
  }

  return (
    <div className="p-8">
      <h2 className="text-xl font-bold text-slate-900 mb-2">Operations</h2>
      <p className="text-sm text-slate-500 mb-6">Extraction schedules, jobs, and system health</p>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm mb-4">
          Backend unavailable: {error}
        </div>
      )}

      {actionMsg && (
        <div className={`mb-4 px-4 py-2 rounded-lg text-sm flex items-center gap-2 ${actionMsg.ok ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {actionMsg.text}
        </div>
      )}

      {/* Scheduler section */}
      <div className="bg-white rounded-xl border border-slate-200 mb-6">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Clock className="w-5 h-5 text-indigo-500" />
            <h3 className="text-base font-semibold text-slate-900">Extraction Schedules</h3>
            <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${schedulerRunning ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-700'}`}>
              {schedulerRunning ? 'Running' : 'Stopped'}
            </span>
          </div>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700"
          >
            <Plus className="w-4 h-4" /> New Schedule
          </button>
        </div>

        {showCreate && <CreateScheduleForm onCreated={() => { setShowCreate(false); loadAll() }} />}

        {schedules.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">
            No schedules yet. Create one to automate extraction.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left">
                  <th className="px-6 py-3 font-medium text-slate-500">Name</th>
                  <th className="px-6 py-3 font-medium text-slate-500">Platform</th>
                  <th className="px-6 py-3 font-medium text-slate-500">Interval</th>
                  <th className="px-6 py-3 font-medium text-slate-500">Status</th>
                  <th className="px-6 py-3 font-medium text-slate-500">Last Run</th>
                  <th className="px-6 py-3 font-medium text-slate-500">Next Run</th>
                  <th className="px-6 py-3 font-medium text-slate-500">Actions</th>
                </tr>
              </thead>
              <tbody>
                {schedules.map((s) => (
                  <tr key={s.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-6 py-3 font-medium text-slate-700">{s.name}</td>
                    <td className="px-6 py-3 capitalize">{s.platform}</td>
                    <td className="px-6 py-3">{formatInterval(s.interval_minutes)} / {s.lookback_days}d lookback</td>
                    <td className="px-6 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                        !s.is_active ? 'bg-slate-100 text-slate-500' :
                        s.last_status === 'completed' ? 'bg-green-100 text-green-700' :
                        s.last_status === 'failed' ? 'bg-red-100 text-red-700' :
                        'bg-blue-100 text-blue-700'
                      }`}>
                        {!s.is_active ? 'paused' : s.last_status || 'pending'}
                      </span>
                      {s.consecutive_failures > 0 && (
                        <span className="ml-1 text-xs text-red-500">({s.consecutive_failures} fails)</span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-slate-500 text-xs">
                      {s.last_run_at ? new Date(s.last_run_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-6 py-3 text-slate-500 text-xs">
                      {s.is_active && s.next_run_at ? new Date(s.next_run_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-6 py-3">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleTrigger(s.id)}
                          disabled={triggering === s.id}
                          className="p-1 text-indigo-600 hover:bg-indigo-50 rounded"
                          title="Run now"
                        >
                          <Zap className={`w-4 h-4 ${triggering === s.id ? 'animate-pulse' : ''}`} />
                        </button>
                        <button
                          onClick={() => handleToggle(s)}
                          className={`p-1 rounded ${s.is_active ? 'text-amber-600 hover:bg-amber-50' : 'text-green-600 hover:bg-green-50'}`}
                          title={s.is_active ? 'Pause' : 'Resume'}
                        >
                          {s.is_active ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                        </button>
                        <button
                          onClick={() => handleDelete(s.id)}
                          className="p-1 text-red-500 hover:bg-red-50 rounded"
                          title="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Extraction runs table */}
      <div className="bg-white rounded-xl border border-slate-200">
        <div className="px-6 py-4 border-b border-slate-200">
          <h3 className="text-base font-semibold text-slate-900">Recent Extraction Runs</h3>
        </div>
        {runs.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">
            No extraction runs yet. Create a schedule or trigger a manual extraction.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left">
                  <th className="px-6 py-3 font-medium text-slate-500">Platform</th>
                  <th className="px-6 py-3 font-medium text-slate-500">Type</th>
                  <th className="px-6 py-3 font-medium text-slate-500">Status</th>
                  <th className="px-6 py-3 font-medium text-slate-500">Metrics</th>
                  <th className="px-6 py-3 font-medium text-slate-500">Duration</th>
                  <th className="px-6 py-3 font-medium text-slate-500">Started</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.run_id} className="border-b border-slate-100 last:border-0">
                    <td className="px-6 py-3 font-medium capitalize">{r.platform}</td>
                    <td className="px-6 py-3">{r.job_type}</td>
                    <td className="px-6 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                        r.status === 'completed' ? 'bg-green-100 text-green-700' :
                        r.status === 'failed' ? 'bg-red-100 text-red-700' :
                        r.status === 'running' ? 'bg-blue-100 text-blue-700' :
                        'bg-slate-100 text-slate-700'
                      }`}>
                        {r.status}
                      </span>
                    </td>
                    <td className="px-6 py-3">{r.metrics_extracted} / {r.metrics_extracted + r.metrics_failed}</td>
                    <td className="px-6 py-3">{r.duration_seconds ? `${r.duration_seconds.toFixed(1)}s` : '—'}</td>
                    <td className="px-6 py-3 text-slate-500">
                      {r.started_at ? new Date(r.started_at).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}


function CreateScheduleForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('')
  const [platform, setPlatform] = useState('youtube')
  const [accountId, setAccountId] = useState('default')
  const [jobType, setJobType] = useState('full')
  const [interval, setInterval] = useState(360)
  const [lookback, setLookback] = useState(7)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) { setError('Name is required'); return }
    setSubmitting(true)
    setError('')
    try {
      await api.scheduler.create({
        name: name.trim(),
        platform,
        account_id: accountId,
        job_type: jobType,
        interval_minutes: interval,
        lookback_days: lookback,
      })
      onCreated()
    } catch (e) {
      setError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="px-6 py-4 border-b border-slate-200 bg-slate-50">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} className="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm" placeholder="e.g. YouTube Daily" />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Platform</label>
          <select value={platform} onChange={(e) => setPlatform(e.target.value)} className="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm bg-white">
            <option value="youtube">YouTube</option>
            <option value="tiktok">TikTok</option>
            <option value="instagram">Instagram</option>
            <option value="facebook">Facebook</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Account ID</label>
          <input value={accountId} onChange={(e) => setAccountId(e.target.value)} className="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm" />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Job Type</label>
          <select value={jobType} onChange={(e) => setJobType(e.target.value)} className="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm bg-white">
            <option value="full">Full</option>
            <option value="account_metrics">Account Metrics</option>
            <option value="content_metrics">Content Metrics</option>
            <option value="audience_metrics">Audience Metrics</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Interval (minutes)</label>
          <input type="number" min={15} value={interval} onChange={(e) => setInterval(Number(e.target.value))} className="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm" />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Lookback (days)</label>
          <input type="number" min={1} max={90} value={lookback} onChange={(e) => setLookback(Number(e.target.value))} className="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm" />
        </div>
      </div>
      {error && <div className="text-red-600 text-xs mb-2">{error}</div>}
      <div className="flex gap-2">
        <button type="submit" disabled={submitting} className="px-4 py-1.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
          {submitting ? 'Creating...' : 'Create Schedule'}
        </button>
      </div>
    </form>
  )
}
