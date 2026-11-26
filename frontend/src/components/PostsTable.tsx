import { ExternalLink, ListVideo } from 'lucide-react'
import type { PostRow } from '../services/api'

type Props = {
  posts: PostRow[]
  columns: { key: string; label: string }[]
}

function formatNum(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—'
  if (Math.abs(val) >= 1_000_000) return (val / 1_000_000).toFixed(1) + 'M'
  if (Math.abs(val) >= 1_000) return (val / 1_000).toFixed(1) + 'K'
  return val.toLocaleString()
}

export default function PostsTable({ posts, columns }: Props) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden mb-6">
      <div className="px-5 py-3 border-b border-slate-100 flex items-center gap-2">
        <ListVideo className="w-4 h-4 text-slate-500" />
        <span className="font-semibold text-slate-700 text-sm">Posts</span>
        <span className="text-xs text-slate-400 ml-auto">{posts.length} posts</span>
      </div>
      {posts.length === 0 ? (
        <p className="px-5 py-6 text-sm text-slate-400">No posts found on this account yet.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 text-xs border-b border-slate-100">
              <th className="px-5 py-2 font-medium">Post</th>
              <th className="px-5 py-2 font-medium">Posted</th>
              {columns.map((c) => (
                <th key={c.key} className="px-5 py-2 font-medium text-right">{c.label}</th>
              ))}
              <th className="px-5 py-2 font-medium">As of</th>
            </tr>
          </thead>
          <tbody>
            {posts.map((p) => (
              <tr key={p.content_id} className="border-b border-slate-50 hover:bg-slate-50">
                <td className="px-5 py-2 max-w-md">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] uppercase tracking-wide bg-slate-100 text-slate-500 rounded px-1.5 py-0.5">
                      {p.content_type}
                    </span>
                    <span className="truncate text-slate-700">{p.title || p.content_id}</span>
                    {p.content_url && (
                      <a href={p.content_url} target="_blank" rel="noreferrer" className="text-slate-400 hover:text-slate-600">
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}
                  </div>
                </td>
                <td className="px-5 py-2 text-slate-500 whitespace-nowrap">
                  {p.published_at ? new Date(p.published_at).toLocaleDateString() : '—'}
                </td>
                {columns.map((c) => (
                  <td key={c.key} className="px-5 py-2 text-right text-slate-900">{formatNum(p.metrics[c.key])}</td>
                ))}
                <td className="px-5 py-2 text-slate-400 whitespace-nowrap">{p.as_of || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
