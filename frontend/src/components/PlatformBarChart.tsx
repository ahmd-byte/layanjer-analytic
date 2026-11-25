import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell } from 'recharts'

const PLATFORM_COLORS: Record<string, string> = {
  youtube: '#ef4444',
  tiktok: '#000000',
  instagram: '#e1306c',
  facebook: '#1877f2',
}

interface PlatformBarChartProps {
  data: { platform: string; metric_count: number; unique_metrics: number; total_runs: number; successful_runs: number }[]
  title: string
  height?: number
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export default function PlatformBarChart({ data, title, height = 300 }: PlatformBarChartProps) {
  if (!data.length) return null

  const chartData = data.map((d) => ({
    ...d,
    name: capitalize(d.platform),
    color: PLATFORM_COLORS[d.platform] ?? '#6366f1',
  }))

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <h3 className="text-sm font-semibold text-slate-700 mb-4">{title}</h3>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#475569' }} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickLine={false} axisLine={false} />
          <Tooltip
            contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
            labelStyle={{ fontWeight: 600, color: '#1e293b' }}
          />
          <Legend iconType="circle" wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
          <Bar dataKey="metric_count" name="Metrics Collected" radius={[4, 4, 0, 0]}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.color} />
            ))}
          </Bar>
          <Bar dataKey="successful_runs" name="Successful Runs" fill="#22c55e" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
