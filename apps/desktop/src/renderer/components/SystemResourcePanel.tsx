import { useEffect, useState } from 'react'
import type {
  PerformanceMode,
  ResourcePressure,
  SystemHardwareInfo,
  SystemResourceSnapshot
} from '../../shared/types'
import './SystemResourcePanel.css'

const PERF_MODES: { id: PerformanceMode; label: string; hint: string }[] = [
  { id: 'eco', label: 'Eco', hint: 'Slower · light on CPU' },
  { id: 'balanced', label: 'Balanced', hint: 'Default' },
  { id: 'high', label: 'High', hint: 'Full speed' }
]

function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n < 0) return '—'
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(0)} MB`
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function pressureLabel(p: ResourcePressure): string {
  if (p === 'critical') return 'Critical'
  if (p === 'high') return 'Heavy'
  if (p === 'moderate') return 'Busy'
  return 'OK'
}

interface Props {
  compact?: boolean
  pollMs?: number
  enabled?: boolean
  showPerformanceToggle?: boolean
}

export default function SystemResourcePanel({
  compact = false,
  pollMs = 2000,
  enabled = true,
  showPerformanceToggle = true
}: Props) {
  const [hardware, setHardware] = useState<SystemHardwareInfo | null>(null)
  const [live, setLive] = useState<SystemResourceSnapshot | null>(null)
  const [performanceMode, setPerformanceMode] = useState<PerformanceMode>('balanced')

  useEffect(() => {
    void window.garuda.getSystemHardware().then(setHardware)
    void window.garuda.getSettings().then((s) => setPerformanceMode(s.performanceMode || 'balanced'))
  }, [])

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    const tick = async () => {
      try {
        const snap = await window.garuda.getSystemResources()
        if (!cancelled) setLive(snap)
      } catch {
        /* ignore */
      }
    }
    void tick()
    const id = window.setInterval(() => void tick(), pollMs)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [enabled, pollMs])

  if (!hardware && !live) return null

  const pressure = live?.pressure ?? 'ok'

  const setMode = async (mode: PerformanceMode) => {
    const next = await window.garuda.setSettings({ performanceMode: mode })
    setPerformanceMode(next.performanceMode)
    if (mode === 'eco') {
      const status = await window.garuda.getPerformanceOverride()
      await window.garuda.setPerformanceOverride('eco', status.jobActive)
    } else {
      await window.garuda.clearPerformanceOverride()
    }
  }

  return (
    <div className={`sys-panel ${compact ? 'compact' : ''} pressure-${pressure}`} role="status" aria-live="polite">
      {showPerformanceToggle && (
        <div className="sys-perf">
          <div className="sys-live-head">
            <p className="eyebrow mono">SPEED</p>
            <span className="sys-chip ok mono">Same depth · live Eco via guard</span>
          </div>
          <div className="sys-perf-pills">
            {PERF_MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                className={`sys-perf-pill ${performanceMode === m.id ? 'active' : ''}`}
                title={m.hint}
                onClick={() => void setMode(m.id)}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {!compact && hardware && (
        <div className="sys-hardware">
          <p className="eyebrow mono">THIS MACHINE</p>
          <div className="sys-hardware-grid">
            <div>
              <span className="sys-dim">Chip</span>
              <strong>{hardware.chip}</strong>
            </div>
            <div>
              <span className="sys-dim">CPU</span>
              <strong className="mono">
                {hardware.physicalCores}P / {hardware.logicalCores}T
              </strong>
            </div>
            <div>
              <span className="sys-dim">RAM</span>
              <strong className="mono">{formatBytes(hardware.totalRamBytes)}</strong>
            </div>
            <div>
              <span className="sys-dim">GPU</span>
              <strong>{hardware.gpu}</strong>
            </div>
          </div>
        </div>
      )}

      {live && (
        <div className="sys-live">
          <div className="sys-live-head">
            <p className="eyebrow mono">{compact ? 'SYSTEM' : 'LIVE LOAD'}</p>
            <span className={`sys-badge pressure-${pressure}`}>{pressureLabel(pressure)}</span>
          </div>

          <div className="sys-metric">
            <div className="sys-metric-meta">
              <span>CPU</span>
              <span className="mono">{live.cpuPercent}%</span>
            </div>
            <div className="sys-track">
              <div className="sys-fill cpu" style={{ width: `${live.cpuPercent}%` }} />
            </div>
            <p className="sys-hint mono">
              Load {live.loadAvg1} · {live.loadPerCore.toFixed(2)}× per core
            </p>
          </div>

          <div className="sys-metric">
            <div className="sys-metric-meta">
              <span>Memory</span>
              <span className="mono">{live.memoryUsedPercent}%</span>
            </div>
            <div className="sys-track">
              <div className="sys-fill mem" style={{ width: `${live.memoryUsedPercent}%` }} />
            </div>
            <p className="sys-hint mono">
              {formatBytes(live.memoryUsedBytes)} used · {formatBytes(live.memoryFreeBytes)} free
            </p>
          </div>

          {live.garudaCpuPercent > 0 && (
            <div className="sys-metric">
              <div className="sys-metric-meta">
                <span>Garuda</span>
                <span className="mono">{live.garudaCpuPercent}% CPU</span>
              </div>
              <div className="sys-track">
                <div
                  className="sys-fill garuda"
                  style={{ width: `${Math.min(100, live.garudaCpuPercent)}%` }}
                />
              </div>
            </div>
          )}

          {!compact && live.garudaProcesses.length > 0 && (
            <ul className="sys-procs">
              {live.garudaProcesses.map((p) => (
                <li key={p.pid}>
                  <span>{p.name}</span>
                  <span className="mono">
                    {Math.round(p.cpuPercent)}% · {p.memoryPercent.toFixed(1)}%
                  </span>
                </li>
              ))}
            </ul>
          )}

          <div className="sys-status-row">
            {live.onBattery && (
              <span className="sys-chip warn mono">
                Battery{live.batteryPercent != null ? ` ${live.batteryPercent}%` : ''}
              </span>
            )}
            {live.thermalWarning && <span className="sys-chip danger mono">Thermal warning</span>}
            {!live.onBattery && !live.thermalWarning && (
              <span className="sys-chip ok mono">Thermals OK</span>
            )}
          </div>

          {live.advice.length > 0 && (
            <ul className="sys-advice">
              {live.advice.map((tip) => (
                <li key={tip}>{tip}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
