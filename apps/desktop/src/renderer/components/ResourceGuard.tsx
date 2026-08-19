import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  AppSettings,
  ResourcePressure,
  SystemResourceSnapshot
} from '../../shared/types'
import './ResourceGuard.css'

const SNOOZE_KEY = 'garuda-resource-guard-snooze'

function pressureRank(p: ResourcePressure): number {
  if (p === 'critical') return 4
  if (p === 'high') return 3
  if (p === 'moderate') return 2
  return 1
}

function shouldTrigger(
  live: SystemResourceSnapshot,
  settings: AppSettings
): boolean {
  if (settings.resourceGuard === 'off') return false
  const minRank = settings.resourceGuardTrigger === 'high' ? 3 : 4
  if (pressureRank(live.pressure) < minRank) return false
  return live.garudaJobActive || live.garudaCpuPercent >= 15
}

interface Props {
  settings: AppSettings
  onOpenSettings?: () => void
}

export default function ResourceGuard({ settings, onOpenSettings }: Props) {
  const [live, setLive] = useState<SystemResourceSnapshot | null>(null)
  const [visible, setVisible] = useState(false)
  const [ecoNote, setEcoNote] = useState<string | null>(null)
  const autoEcoDone = useRef(false)

  const poll = useCallback(async () => {
    try {
      const snap = await window.garuda.getSystemResources()
      setLive(snap)
      const snoozeUntil = Number(localStorage.getItem(SNOOZE_KEY) || 0)
      if (Date.now() < snoozeUntil) {
        setVisible(false)
        return
      }
      const hot = shouldTrigger(snap, settings)
      setVisible(hot)
      if (
        hot &&
        settings.resourceGuard === 'auto_eco' &&
        !autoEcoDone.current &&
        snap.garudaJobActive
      ) {
        autoEcoDone.current = true
        await applyForceEco()
      }
    } catch {
      /* ignore */
    }
  }, [settings])

  const applyForceEco = async () => {
    const result = await window.garuda.setPerformanceOverride('eco', true)
    await window.garuda.setSettings({ performanceMode: 'eco' })
    if (!result.jobActive) {
      setEcoNote('Saved Eco for the next job — no Garuda engine is running right now.')
      return
    }
    if (result.applied) {
      setEcoNote(
        'Force Eco active — lowered process priority and throttled the running engine (same depth, slower).'
      )
    } else {
      setEcoNote('Could not apply Force Eco. Try Stop job, set Eco in Settings, then restart the job.')
    }
  }

  useEffect(() => {
    autoEcoDone.current = false
    setEcoNote(null)
  }, [settings.resourceGuard, settings.resourceGuardTrigger])

  useEffect(() => {
    void poll()
    const id = window.setInterval(() => void poll(), 2000)
    return () => window.clearInterval(id)
  }, [poll])

  const stopJobs = async () => {
    await window.garuda.cancelAllGarudaJobs()
    setVisible(false)
    autoEcoDone.current = false
    setEcoNote(null)
  }

  const snooze = () => {
    localStorage.setItem(SNOOZE_KEY, String(Date.now() + 5 * 60 * 1000))
    setVisible(false)
  }

  if (!visible || !live) return null

  const label = live.pressure === 'critical' ? 'Critical load' : 'Heavy load'

  return (
    <div className={`resource-guard pressure-${live.pressure}`} role="alertdialog" aria-live="assertive">
      <div className="rg-body">
        <p className="eyebrow mono">RESOURCE GUARD</p>
        <h2>{label}</h2>
        <p className="rg-detail mono">
          CPU {live.cpuPercent}% · RAM {live.memoryUsedPercent}% · Garuda {live.garudaCpuPercent}%
          {live.garudaJobActive ? ' · job running' : ' · idle'}
        </p>
        {ecoNote && <p className="rg-note">{ecoNote}</p>}
        <div className="rg-actions">
          <button type="button" className="primary-btn" onClick={() => void applyForceEco()}>
            Force Eco now
          </button>
          <button type="button" className="danger-btn" onClick={() => void stopJobs()}>
            Stop Garuda job
          </button>
          <button type="button" className="ghost-btn" onClick={snooze}>
            Snooze 5 min
          </button>
          {onOpenSettings && (
            <button type="button" className="ghost-btn" onClick={onOpenSettings}>
              Guard settings
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
