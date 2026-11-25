import { NavLink, Outlet } from 'react-router-dom'
import {
  BarChart3,
  Play,
  Music2,
  Camera,
  ThumbsUp,
  Settings,
  Activity,
  LayoutDashboard,
} from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/youtube', label: 'YouTube', icon: Play },
  { to: '/tiktok', label: 'TikTok', icon: Music2 },
  { to: '/instagram', label: 'Instagram', icon: Camera },
  { to: '/facebook', label: 'Facebook', icon: ThumbsUp },
  { to: '/operations', label: 'Operations', icon: Activity },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Layout() {
  return (
    <div className="flex h-screen bg-slate-50">
      <aside className="w-64 bg-white border-r border-slate-200 flex flex-col">
        <div className="p-6 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-7 h-7 text-indigo-500" />
            <div>
              <h1 className="text-lg font-bold text-slate-900">Layan Je</h1>
              <p className="text-xs text-slate-500">Analytics</p>
            </div>
          </div>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-indigo-50 text-indigo-700'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                )
              }
            >
              <Icon className="w-5 h-5" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-slate-200 text-xs text-slate-400">
          Bruz Digital
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
