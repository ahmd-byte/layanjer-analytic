import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell } from 'recharts'

const STATUS_COLORS: Record<string, string> = {
  completed: '#22c55e',
  failed: '#ef4444',
  running: '#f59e0b',
  partial: '#f97316',
}

interface Run {
  run_id: string
  platform: string
  status: string
  metrics_extracted: number
  metrics_failed: number
  duration_seconds: number | null
  started_at: string | null
  completed_at: string | null
}

interface ExtractionHistoryChartProps {
  data: Run[]
  title: string
  height?: number
}

function shortDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export default function ExtractionHistoryChart({ data, title, height = 260 }: ExtractionHistoryChartProps) {
  if (!data.length) return null

  const chartData = [...data]
    .reverse()
    .map((r) => ({
      label: `${capitalize(r.platform)} ${shortDate(r.started_at)}`,
      metrics: r.metrics_extracted,
      failed: r.metrics_failed,
      status: r.status,
      platform: r.platform,
      duration: r.duration_seconds,
    }))

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <h3 className="text-sm font-semibold text-slate-700 mb-4">{title}</h3>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#94a3b8' }} tickLine={false} angle={-30} textAnchor="end" height={60} />
          <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickLine={false} axisLine={false} />
          <Tooltip
            contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
            labelStyle={{ fontWeight: 600, color: '#1e293b' }}
            formatter={(value, name) => [value, name === 'metrics' ? 'Extracted' : 'Failed']}
          />
          <Bar dataKey="metrics" name="Extracted" radius={[4, 4, 0, 0]}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={STATUS_COLORS[entry.status] ?? '#6366f1'} />
            ))}
          </Bar>
          <Bar dataKey="failed" name="Failed" fill="#fca5a5" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
