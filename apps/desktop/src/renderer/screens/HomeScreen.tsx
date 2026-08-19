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
        <div className="hero-horizon" aria-hidden />
        <div className="hero-grid" aria-hidden />
        <div className="hero-orbits" aria-hidden>
          <div className="hero-orbit o1" />
          <div className="hero-orbit o2" />
          <div className="hero-orbit o3" />
          <div className="hero-core" />
        </div>
        <div className="hero-hud" aria-hidden>
          <span className="hud-corner tl" />
          <span className="hud-corner tr" />
          <span className="hud-corner bl" />
          <span className="hud-corner br" />
          <span className="hud-chip mono">UPLINK · LOCAL · SECURE</span>
          <span className="hud-chip-right mono">FPS · FRAME · FACE · VOICE</span>
        </div>

        <motion.div
          className="hero-telemetry"
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4, duration: 0.5 }}
          aria-hidden
        >
          <span className="mono">NODE 01</span>
          <span className="mono">LATENCY &lt;1ms</span>
          <span className="mono">AIRGAP READY</span>
          <span className="mono pulse">REC · IDLE</span>
        </motion.div>

        <motion.svg
          className="hero-mark"
          viewBox="0 0 220 140"
          initial={{ opacity: 0, scale: 0.88, rotate: -4 }}
          animate={{ opacity: 1, scale: 1, rotate: 0 }}
          transition={{ duration: 0.85, ease: [0.22, 1, 0.36, 1] }}
        >
          <defs>
            <linearGradient id="neonWing" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#9afff5" />
              <stop offset="45%" stopColor="#00f0ff" />
              <stop offset="100%" stopColor="#c8ff3d" />
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
            opacity="0.2"
          />
          <path
            d="M110 38 L118 56 L140 54 L122 66 L128 88 L110 74 L92 88 L98 66 L80 54 L102 56 Z"
            fill="#000208"
            stroke="#00f0ff"
            strokeWidth="1.2"
            opacity="0.95"
          />
          <circle cx="110" cy="62" r="3.2" fill="#c8ff3d">
            <animate attributeName="opacity" values="0.35;1;0.35" dur="2s" repeatCount="indefinite" />
          </circle>
        </motion.svg>

        <motion.h1
          className="brand"
          initial={{ opacity: 0, y: 22 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.14, duration: 0.6 }}
        >
          GARUDA
        </motion.h1>
        <motion.p
          className="brand-sub mono"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.28, duration: 0.45 }}
        >
          VIDEO INTELLIGENCE ENGINE
        </motion.p>
        <motion.p
          className="tagline"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.26, duration: 0.5 }}
        >
          End-to-end local analysis for creators who refuse to guess.
        </motion.p>
        <motion.div
          className="cta-row"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.36, duration: 0.45 }}
        >
          <button className="primary-btn cta" type="button" onClick={onPick}>
            Initialize analysis
          </button>
          <span className="drop-hint muted">Drop footage onto this deck to begin</span>
        </motion.div>
      </section>

      {pastReports.length > 0 && (
        <section className="past">
          <div className="past-head">
            <div>
              <p className="eyebrow">Archives</p>
              <h2>Recent signal logs</h2>
            </div>
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
            {pastReports.slice(0, recentLimit).map((item, i) => (
              <motion.li
                key={item.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05 * i, duration: 0.35 }}
              >
                <button type="button" className="past-item" onClick={() => onOpenPast(item)}>
                  <span className="past-index mono">{String(i + 1).padStart(2, '0')}</span>
                  <span className="past-body">
                    <span className="past-name">{item.sourceName}</span>
                    <span className="past-meta mono">
                      {new Date(item.createdAt).toLocaleString()} · SCORE {Math.round(item.overall)}
                    </span>
                  </span>
                  <span className="past-chevron" aria-hidden />
                </button>
              </motion.li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
