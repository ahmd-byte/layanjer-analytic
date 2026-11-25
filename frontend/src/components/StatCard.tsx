import clsx from 'clsx'
import type { LucideIcon } from 'lucide-react'

interface StatCardProps {
  title: string
  value: string | number
  subtitle?: string
  icon: LucideIcon
  color?: string
}

export default function StatCard({ title, value, subtitle, icon: Icon, color = 'text-indigo-500' }: StatCardProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-slate-500">{title}</span>
        <Icon className={clsx('w-5 h-5', color)} />
      </div>
      <div className="text-2xl font-bold text-slate-900">{value}</div>
      {subtitle && <p className="text-xs text-slate-400 mt-1">{subtitle}</p>}
    </div>
  )
}
