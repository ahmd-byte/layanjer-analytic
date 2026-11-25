import { useEffect, useState } from 'react'
import { api, type ExtractionRunInfo } from '../services/api'

export default function Operations() {
  const [runs, setRuns] = useState<ExtractionRunInfo[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    api.extractionRuns().then(setRuns).catch((e) => setError(e.message))
  }, [])

  return (
    <div className="p-8">
      <h2 className="text-xl font-bold text-slate-900 mb-2">Operations</h2>
      <p className="text-sm text-slate-500 mb-6">Extraction jobs, browser sessions, system health</p>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm mb-4">
          Backend unavailable: {error}
        </div>
      )}

      <div className="bg-white rounded-xl border border-slate-200">
        <div className="px-6 py-4 border-b border-slate-200">
          <h3 className="text-base font-semibold text-slate-900">Recent Extraction Runs</h3>
        </div>
        {runs.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">
            No extraction runs yet. Run <code className="bg-slate-100 px-1 rounded">layan pull --all</code> to start.
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
