import { useEffect, useState } from 'react'
import { motion, useMotionValue, useTransform, animate } from 'framer-motion'
import './ScoreRing.css'

interface Props {
  label: string
  value: number
}

export default function ScoreRing({ label, value }: Props) {
  const mv = useMotionValue(0)
  const [display, setDisplay] = useState(0)
  const r = 36
  const c = 2 * Math.PI * r
  const dash = useTransform(mv, (v) => c - (Math.min(100, Math.max(0, v)) / 100) * c)

  useEffect(() => {
    const controls = animate(mv, value, { duration: 1.1, ease: [0.22, 1, 0.36, 1] })
    const unsub = mv.on('change', (v) => setDisplay(Math.round(v)))
    return () => {
      controls.stop()
      unsub()
    }
  }, [value, mv])

  return (
    <div className="score-ring">
      <svg viewBox="0 0 100 100" className="ring-svg">
        <circle cx="50" cy="50" r={r} className="ring-track" />
        <motion.circle
          cx="50"
          cy="50"
          r={r}
          className="ring-value"
          style={{ strokeDasharray: c, strokeDashoffset: dash }}
          transform="rotate(-90 50 50)"
        />
      </svg>
      <div className="ring-center">
        <span className="ring-num mono">{display}</span>
        <span className="ring-label">{label}</span>
      </div>
    </div>
  )
}
