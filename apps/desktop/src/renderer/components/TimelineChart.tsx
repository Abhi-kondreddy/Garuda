import { useMemo, useRef } from 'react'
import type { AnalysisReport } from '../../shared/types'
import './TimelineChart.css'

interface Props {
  report: AnalysisReport
  cursor: number
  onCursorChange: (t: number) => void
}

export default function TimelineChart({ report, cursor, onCursorChange }: Props) {
  const ref = useRef<SVGSVGElement>(null)
  const duration = Math.max(report.durationSec, 0.001)
  const w = 1000
  const h = 180

  const interestPath = useMemo(() => {
    const pts = report.timeline
    if (!pts.length) return ''
    return pts
      .map((p, i) => {
        const x = (p.t / duration) * w
        const y = h - 20 - (p.interestingness / 100) * (h - 40)
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ')
  }, [report.timeline, duration])

  const wavePath = useMemo(() => {
    const wave = report.waveform
    if (!wave.length) return ''
    const mid = h - 8
    return wave
      .map((v, i) => {
        const x = (i / Math.max(wave.length - 1, 1)) * w
        const amp = Math.min(1, Math.abs(v)) * 28
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${(mid - amp).toFixed(1)}`
      })
      .join(' ')
  }, [report.waveform])

  const onMove = (e: React.MouseEvent) => {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const x = Math.min(Math.max(0, e.clientX - rect.left), rect.width)
    onCursorChange((x / rect.width) * duration)
  }

  const cx = (cursor / duration) * w

  return (
    <svg
      ref={ref}
      className="timeline-chart"
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      onMouseMove={onMove}
      onClick={onMove}
    >
      <defs>
        <linearGradient id="interestFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#00f0ff" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#00f0ff" stopOpacity="0" />
        </linearGradient>
      </defs>

      {report.riskZones.map((z, i) => {
        const x = (z.start / duration) * w
        const width = ((z.end - z.start) / duration) * w
        return (
          <rect
            key={i}
            x={x}
            y={0}
            width={Math.max(2, width)}
            height={h}
            className={`risk-band ${z.severity}`}
            style={{ cursor: 'pointer', pointerEvents: 'all' }}
            onClick={(e) => {
              e.stopPropagation()
              onCursorChange(z.start)
            }}
          />
        )
      })}

      {interestPath && (
        <>
          <path d={`${interestPath} L${w},${h} L0,${h} Z`} fill="url(#interestFill)" />
          <path d={interestPath} className="interest-line" />
        </>
      )}
      {wavePath && <path d={wavePath} className="wave-line" />}

      <line x1={cx} y1={0} x2={cx} y2={h} className="cursor-line" />
      <circle cx={cx} cy={12} r={4} className="cursor-dot" />
    </svg>
  )
}
