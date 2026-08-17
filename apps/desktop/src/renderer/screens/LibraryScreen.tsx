import { useEffect, useMemo, useState } from 'react'
import type { PastReportSummary } from '../../shared/types'
import './LibraryScreen.css'

interface Props {
  reports: PastReportSummary[]
  confirmDelete: boolean
  onOpen: (item: PastReportSummary) => void
  onRefresh: () => void
  onDelete: (item: PastReportSummary) => Promise<void>
  onAnalyze: () => void
  onReveal: (item: PastReportSummary) => void
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export default function LibraryScreen({
  reports,
  confirmDelete,
  onOpen,
  onRefresh,
  onDelete,
  onAnalyze,
  onReveal
}: Props) {
  const [query, setQuery] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [exportsById, setExportsById] = useState<Record<string, string | null>>({})

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return reports
    return reports.filter((r) => r.sourceName.toLowerCase().includes(q))
  }, [reports, query])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const entries = await Promise.all(
        reports.map(async (r) => {
          const path = await window.garuda.voicesLatestExport(r.reportPath)
          return [r.id, path] as const
        })
      )
      if (!cancelled) {
        setExportsById(Object.fromEntries(entries))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [reports])

  const handleDelete = async (item: PastReportSummary) => {
    if (confirmDelete) {
      const ok = window.confirm(`Delete report for “${item.sourceName}”? This cannot be undone.`)
      if (!ok) return
    }
    setBusyId(item.id)
    try {
      await onDelete(item)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="library">
      <header className="library-head">
        <div>
          <p className="eyebrow">Archive</p>
          <h1>Library</h1>
          <p className="muted library-sub">All local analysis reports stored on this machine.</p>
        </div>
        <div className="library-actions">
          <button className="ghost-btn" type="button" onClick={onRefresh}>
            Refresh
          </button>
          <button className="primary-btn" type="button" onClick={onAnalyze}>
            Analyze video
          </button>
        </div>
      </header>

      <div className="library-toolbar">
        <input
          className="library-search"
          type="search"
          placeholder="Search by filename…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="mono muted">{filtered.length} reports</span>
      </div>

      {filtered.length === 0 ? (
        <div className="library-empty">
          <p>{reports.length === 0 ? 'No reports yet.' : 'No matches.'}</p>
          <button className="primary-btn" type="button" onClick={onAnalyze}>
            Analyze your first video
          </button>
        </div>
      ) : (
        <ul className="library-list">
          {filtered.map((item) => (
            <li key={item.id} className="library-row">
              <button type="button" className="library-main" onClick={() => onOpen(item)}>
                <span className="library-score mono">{Math.round(item.overall)}</span>
                <span className="library-meta">
                  <span className="library-name">{item.sourceName}</span>
                  <span className="library-date mono muted">{fmtTime(item.createdAt)}</span>
                </span>
              </button>
              <div className="library-row-actions">
                {exportsById[item.id] && (
                  <button
                    className="ghost-btn"
                    type="button"
                    onClick={() => void window.garuda.voicesRevealExport(exportsById[item.id]!)}
                  >
                    Reveal export
                  </button>
                )}
                <button className="ghost-btn" type="button" onClick={() => onReveal(item)}>
                  Reveal
                </button>
                <button
                  className="danger-btn"
                  type="button"
                  disabled={busyId === item.id}
                  onClick={() => void handleDelete(item)}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
