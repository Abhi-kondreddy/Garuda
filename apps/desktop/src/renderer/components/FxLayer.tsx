import { motion } from 'framer-motion'
import './FxLayer.css'

/** Ambient neon graphics behind every screen. */
export default function FxLayer() {
  return (
    <div className="fx-layer" aria-hidden>
      <div className="fx-aurora fx-aurora-a" />
      <div className="fx-aurora fx-aurora-b" />
      <div className="fx-radar">
        <span className="fx-radar-ring r1" />
        <span className="fx-radar-ring r2" />
        <span className="fx-radar-ring r3" />
        <span className="fx-radar-beam" />
      </div>
      <svg className="fx-constellation" viewBox="0 0 400 300" preserveAspectRatio="none">
        <g stroke="rgba(0,240,255,0.22)" strokeWidth="0.8" fill="none">
          <path d="M40 40 L120 70 L90 140 L180 110 L220 40" />
          <path d="M260 200 L320 160 L360 240 L280 260 Z" />
          <path d="M30 220 L80 250 L140 210" />
        </g>
        {[
          [40, 40],
          [120, 70],
          [90, 140],
          [180, 110],
          [220, 40],
          [260, 200],
          [320, 160],
          [360, 240],
          [280, 260],
          [30, 220],
          [80, 250],
          [140, 210]
        ].map(([x, y], i) => (
          <motion.circle
            key={i}
            cx={x}
            cy={y}
            r={2.2}
            fill="#00f0ff"
            initial={{ opacity: 0.25 }}
            animate={{ opacity: [0.25, 1, 0.25] }}
            transition={{ duration: 2.4 + (i % 4) * 0.35, repeat: Infinity, delay: i * 0.12 }}
          />
        ))}
      </svg>
      <div className="fx-particles">
        {Array.from({ length: 18 }).map((_, i) => (
          <span
            key={i}
            className="fx-particle"
            style={
              {
                '--x': `${(i * 17) % 100}%`,
                '--delay': `${i * 0.4}s`,
                '--dur': `${8 + (i % 5)}s`,
                '--hue': i % 3 === 0 ? 'var(--lime)' : i % 3 === 1 ? 'var(--magenta)' : 'var(--neon)'
              } as React.CSSProperties
            }
          />
        ))}
      </div>
      <div className="fx-vignette" />
    </div>
  )
}
