import type { AppRoute } from '../../shared/types'
import { motion } from 'framer-motion'
import './AppNav.css'

interface Props {
  route: AppRoute
  analyzing: boolean
  hasReport: boolean
  reportCount: number
  onNavigate: (route: AppRoute) => void
}

const ITEMS: Array<{
  id: AppRoute
  label: string
  hint: string
  icon: string
}> = [
  {
    id: 'analyze',
    label: 'Analyze',
    hint: '01',
    icon: 'M4 12h16M12 4v16M7 7l10 10M17 7L7 17'
  },
  {
    id: 'library',
    label: 'Library',
    hint: '02',
    icon: 'M4 6h16M4 12h16M4 18h10'
  },
  {
    id: 'report',
    label: 'Report',
    hint: '03',
    icon: 'M5 19V5h10l4 4v10H5zm10-14v4h4'
  },
  {
    id: 'settings',
    label: 'Settings',
    hint: '04',
    icon: 'M12 8a4 4 0 100 8 4 4 0 000-8zm0-5v2m0 14v2m9-9h-2M5 12H3m12.5-6.5l-1.4 1.4M7.9 16.1l-1.4 1.4m10 0l-1.4-1.4M7.9 7.9L6.5 6.5'
  }
]

export default function AppNav({
  route,
  analyzing,
  hasReport,
  reportCount,
  onNavigate
}: Props) {
  return (
    <nav className="app-nav" aria-label="Primary">
      <div className="nav-glow" aria-hidden />
      <div className="nav-brand">
        <motion.span
          className="nav-brand-mark"
          animate={{ boxShadow: ['0 0 12px rgba(0,240,255,0.25)', '0 0 28px rgba(0,240,255,0.55)', '0 0 12px rgba(0,240,255,0.25)'] }}
          transition={{ duration: 2.8, repeat: Infinity }}
        >
          G
        </motion.span>
        <div>
          <div className="nav-brand-name">GARUDA</div>
          <div className="nav-brand-sub mono">LOCAL CORE</div>
        </div>
      </div>

      <div className="nav-eq" aria-hidden>
        {Array.from({ length: 12 }).map((_, i) => (
          <span
            key={i}
            style={{ animationDelay: `${i * 0.08}s`, height: `${30 + ((i * 17) % 60)}%` }}
          />
        ))}
      </div>

      <ul className="nav-list">
        {ITEMS.map((item) => {
          const disabled = item.id === 'report' && !hasReport
          const active = route === item.id
          return (
            <li key={item.id}>
              <button
                type="button"
                className={`nav-item ${active ? 'active' : ''} ${disabled ? 'disabled' : ''}`}
                disabled={disabled}
                onClick={() => onNavigate(item.id)}
              >
                {active && (
                  <motion.span
                    className="nav-active-bar"
                    layoutId="nav-active"
                    transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                  />
                )}
                <span className="nav-hint mono">{item.hint}</span>
                <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden>
                  <path d={item.icon} fill="none" stroke="currentColor" strokeWidth="1.6" />
                </svg>
                <span className="nav-label">{item.label}</span>
                {item.id === 'analyze' && analyzing && <span className="nav-pulse" />}
                {item.id === 'library' && reportCount > 0 && (
                  <span className="nav-count mono">{reportCount}</span>
                )}
              </button>
            </li>
          )
        })}
      </ul>

      <div className="nav-foot">
        <span className={`nav-foot-dot ${analyzing ? 'busy' : ''}`} />
        <span className="mono">{analyzing ? 'ANALYZING' : 'READY'}</span>
        <span className="nav-foot-wave" aria-hidden />
      </div>
    </nav>
  )
}
