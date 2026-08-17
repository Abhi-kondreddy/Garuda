import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import './HudPanel.css'

interface Props {
  children: ReactNode
  title?: string
  eyebrow?: string
  tone?: 'default' | 'danger' | 'lime'
  className?: string
  delay?: number
}

export default function HudPanel({
  children,
  title,
  eyebrow,
  tone = 'default',
  className = '',
  delay = 0
}: Props) {
  return (
    <motion.section
      className={`hud-panel tone-${tone} ${className}`}
      initial={{ opacity: 0, y: 16, filter: 'blur(4px)' }}
      animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      transition={{ duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -2 }}
    >
      <span className="hud-corner tl" />
      <span className="hud-corner tr" />
      <span className="hud-corner bl" />
      <span className="hud-corner br" />
      <span className="hud-scan" />
      {(title || eyebrow) && (
        <header className="hud-panel-head">
          {eyebrow && <p className="eyebrow">{eyebrow}</p>}
          {title && <h2>{title}</h2>}
          <span className="hud-head-line" />
        </header>
      )}
      <div className="hud-panel-body">{children}</div>
    </motion.section>
  )
}
