import { useCallback, useState } from 'react'
import { motion } from 'framer-motion'
import type { PastReportSummary } from '../../shared/types'
import './HomeScreen.css'

interface Props {
  onPick: () => void
  onDropPath: (path: string) => void
  pastReports: PastReportSummary[]
  recentLimit: number
  onOpenPast: (item: PastReportSummary) => void
  onRefreshPast: () => void
  onOpenLibrary: () => void
}

export default function HomeScreen({
  onPick,
  onDropPath,
  pastReports,
  recentLimit,
  onOpenPast,
  onRefreshPast,
  onOpenLibrary
}: Props) {
  const [dragging, setDragging] = useState(false)

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(true)
  }, [])

  const onDragLeave = useCallback(() => setDragging(false), [])

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      const file = e.dataTransfer.files?.[0]
      const path = (file as File & { path?: string })?.path
      if (path) onDropPath(path)
      else onPick()
    },
    [onDropPath, onPick]
  )

  return (
    <div className="home">
      <section
        className={`home-hero ${dragging ? 'is-dragging' : ''}`}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <div className="hero-atmosphere" aria-hidden />
        <div className="hero-grid" aria-hidden />
        <div className="hero-orbits" aria-hidden>
          <div className="hero-orbit o1" />
          <div className="hero-orbit o2" />
          <div className="hero-orbit o3" />
        </div>
        <div className="hero-hud" aria-hidden>
          <span className="hud-corner tl" />
          <span className="hud-corner tr" />
          <span className="hud-corner bl" />
          <span className="hud-corner br" />
          <span className="hud-chip mono">LOCAL · SIGNAL LIVE</span>
        </div>

        <motion.svg
          className="hero-mark"
          viewBox="0 0 220 140"
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.75, ease: [0.22, 1, 0.36, 1] }}
        >
          <defs>
            <linearGradient id="neonWing" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#7dfff6" />
              <stop offset="45%" stopColor="#00f0ff" />
              <stop offset="100%" stopColor="#b8ff2e" />
            </linearGradient>
            <filter id="neonGlow" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="3.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <path
            d="M110 22 L128 52 L182 44 L144 72 L162 116 L110 88 L58 116 L76 72 L38 44 L92 52 Z"
            fill="none"
            stroke="url(#neonWing)"
            strokeWidth="2.5"
            filter="url(#neonGlow)"
          />
          <path
            d="M110 22 L128 52 L182 44 L144 72 L162 116 L110 88 L58 116 L76 72 L38 44 L92 52 Z"
            fill="url(#neonWing)"
            opacity="0.18"
          />
          <path
            d="M110 38 L118 56 L140 54 L122 66 L128 88 L110 74 L92 88 L98 66 L80 54 L102 56 Z"
            fill="#010104"
            stroke="#00f0ff"
            strokeWidth="1.2"
            opacity="0.95"
          />
          <circle cx="110" cy="62" r="3" fill="#b8ff2e">
            <animate attributeName="opacity" values="0.4;1;0.4" dur="2.2s" repeatCount="indefinite" />
          </circle>
        </motion.svg>

        <motion.h1
          className="brand"
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.12, duration: 0.55 }}
        >
          GARUDA
        </motion.h1>
        <motion.p
          className="tagline"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.22, duration: 0.5 }}
        >
          End-to-end local video intelligence for creators who refuse to guess.
        </motion.p>
        <motion.div
          className="cta-row"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.32, duration: 0.45 }}
        >
          <button className="primary-btn cta" type="button" onClick={onPick}>
            Analyze video
          </button>
          <span className="drop-hint muted">or drop a file anywhere on this screen</span>
        </motion.div>
      </section>

      {pastReports.length > 0 && (
        <section className="past">
          <div className="past-head">
            <h2>Recent reports</h2>
            <div className="past-head-actions">
              <button className="ghost-btn" type="button" onClick={onRefreshPast}>
                Refresh
              </button>
              <button className="ghost-btn" type="button" onClick={onOpenLibrary}>
                Open library
              </button>
            </div>
          </div>
          <ul className="past-list">
            {pastReports.slice(0, recentLimit).map((item) => (
              <li key={item.id}>
                <button type="button" className="past-item" onClick={() => onOpenPast(item)}>
                  <span className="past-name">{item.sourceName}</span>
                  <span className="past-meta mono">
                    {new Date(item.createdAt).toLocaleString()} · {Math.round(item.overall)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
