export default function Instagram() {
  return (
    <div className="p-8">
      <h2 className="text-xl font-bold text-slate-900 mb-2">Instagram Analytics</h2>
      <p className="text-sm text-slate-500 mb-6">Reach, views, Reels, engagement, follower growth</p>
      <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
        <div className="text-4xl mb-3">📸</div>
        <h3 className="text-lg font-semibold text-slate-700 mb-2">No Instagram data yet</h3>
        <p className="text-sm text-slate-500 mb-4">
          Connect your Instagram Professional account to start collecting analytics.
        </p>
        <code className="bg-slate-100 px-3 py-1.5 rounded text-sm text-slate-700">
          layan login --platform instagram
        </code>
      </div>
    </div>
  )
}
