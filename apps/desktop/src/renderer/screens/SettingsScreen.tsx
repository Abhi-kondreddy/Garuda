import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import type { AppInfo, AppSettings, DataStats } from '../../shared/types'
import HudPanel from '../components/HudPanel'
import './SettingsScreen.css'

interface Props {
  settings: AppSettings
  onSave: (patch: Partial<AppSettings>) => Promise<void>
  onCleared: () => void
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export default function SettingsScreen({ settings, onSave, onCleared }: Props) {
  const [stats, setStats] = useState<DataStats | null>(null)
  const [info, setInfo] = useState<AppInfo | null>(null)
  const [clearText, setClearText] = useState('')
  const [clearing, setClearing] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const refreshStats = async () => {
    const next = await window.garuda.getDataStats()
    setStats(next)
  }

  useEffect(() => {
    void refreshStats()
    void window.garuda.getAppInfo().then(setInfo)
  }, [])

  const patch = async (partial: Partial<AppSettings>) => {
    await onSave(partial)
    setMessage('Saved')
    window.setTimeout(() => setMessage(null), 1400)
  }

  const clearAll = async () => {
    if (clearText.trim().toUpperCase() !== 'CLEAR') return
    setClearing(true)
    try {
      await window.garuda.clearAllData()
      setClearText('')
      await refreshStats()
      onCleared()
      setMessage('All Garuda data cleared')
    } finally {
      setClearing(false)
    }
  }

  const fill = useMemo(() => {
    const bytes = stats?.bytes ?? 0
    // Visual only — soft scale against ~500MB
    return Math.min(100, Math.round((bytes / (500 * 1024 * 1024)) * 100))
  }, [stats])

  const ring = 2 * Math.PI * 42
  const dash = ring - (fill / 100) * ring

  return (
    <div className="settings">
      <header className="settings-head">
        <div>
          <p className="eyebrow">Preferences</p>
          <motion.h1
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.45 }}
          >
            Settings
          </motion.h1>
          <p className="muted settings-sub">Local-only controls. Nothing leaves this machine.</p>
        </div>
        {message && (
          <motion.span
            className="settings-toast mono"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
          >
            {message}
          </motion.span>
        )}
      </header>

      <div className="settings-hero-grid">
        <HudPanel title="Signal core" eyebrow="Status" delay={0.05} className="settings-hero-card">
          <div className="signal-viz">
            <div className="signal-ring-wrap">
              <svg viewBox="0 0 100 100" className="signal-ring">
                <circle cx="50" cy="50" r="42" className="signal-track" />
                <motion.circle
                  cx="50"
                  cy="50"
                  r="42"
                  className="signal-value"
                  style={{ strokeDasharray: ring, strokeDashoffset: dash }}
                  transform="rotate(-90 50 50)"
                  initial={{ strokeDashoffset: ring }}
                  animate={{ strokeDashoffset: dash }}
                  transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
                />
              </svg>
              <div className="signal-ring-label">
                <strong className="mono">{stats?.reportCount ?? 0}</strong>
                <span>REPORTS</span>
              </div>
            </div>
            <div className="signal-meta">
              <div>
                <span className="dim">Storage</span>
                <strong className="mono">{stats ? formatBytes(stats.bytes) : '—'}</strong>
              </div>
              <div>
                <span className="dim">Platform</span>
                <strong className="mono">{info?.platform ?? '—'}</strong>
              </div>
              <div className="signal-bars" aria-hidden>
                {Array.from({ length: 16 }).map((_, i) => (
                  <span key={i} style={{ animationDelay: `${i * 0.07}s` }} />
                ))}
              </div>
            </div>
          </div>
        </HudPanel>

        <HudPanel title="Analysis" eyebrow="Engine" delay={0.12}>
          <label className="settings-field">
            <span>Whisper model</span>
            <div className="model-pills">
              {(['tiny', 'base', 'small'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  className={`model-pill ${settings.whisperModel === m ? 'active' : ''}`}
                  onClick={() => void patch({ whisperModel: m })}
                >
                  {m}
                </button>
              ))}
            </div>
          </label>
          <p className="hint muted">Used on the next run. Larger = slower + more disk.</p>
        </HudPanel>
      </div>

      <HudPanel title="Library" eyebrow="Playback" delay={0.18}>
        <label className="settings-field inline">
          <span>Recent on Analyze</span>
          <input
            type="number"
            min={3}
            max={24}
            value={settings.recentLimit}
            onChange={(e) => void patch({ recentLimit: Number(e.target.value) })}
          />
        </label>
        <div className="toggle-grid">
          <button
            type="button"
            className={`toggle-card ${settings.confirmDelete ? 'on' : ''}`}
            onClick={() => void patch({ confirmDelete: !settings.confirmDelete })}
          >
            <span className="toggle-led" />
            <span>Confirm before delete</span>
          </button>
          <button
            type="button"
            className={`toggle-card ${settings.autoplay ? 'on' : ''}`}
            onClick={() => void patch({ autoplay: !settings.autoplay })}
          >
            <span className="toggle-led" />
            <span>Autoplay report video</span>
          </button>
        </div>
      </HudPanel>

      <HudPanel title="Storage & privacy" eyebrow="Data vault" tone="danger" delay={0.24}>
        <dl className="settings-stats">
          <div>
            <dt>Data folder</dt>
            <dd className="mono">{stats?.path ?? '…'}</dd>
          </div>
        </dl>
        <div className="settings-row">
          <button className="ghost-btn" type="button" onClick={() => void window.garuda.openDataFolder()}>
            Open data folder
          </button>
          <button className="ghost-btn" type="button" onClick={() => void refreshStats()}>
            Refresh stats
          </button>
        </div>

        <div className="clear-box">
          <div className="clear-head">
            <h3>Clear all app data</h3>
            <span className="clear-warn mono">DESTRUCTIVE</span>
          </div>
          <p className="muted">
            Deletes every report and Garuda cache under its data folder, and resets settings. Original
            video files on disk are not touched.
          </p>
          <label className="settings-field">
            <span>Type CLEAR to arm the wipe</span>
            <input
              value={clearText}
              onChange={(e) => setClearText(e.target.value)}
              placeholder="CLEAR"
              autoComplete="off"
            />
          </label>
          <button
            className="danger-btn"
            type="button"
            disabled={clearing || clearText.trim().toUpperCase() !== 'CLEAR'}
            onClick={() => void clearAll()}
          >
            {clearing ? 'Clearing…' : 'Clear all app data'}
          </button>
        </div>
      </HudPanel>

      <HudPanel title="About" eyebrow="Build" delay={0.3} tone="lime">
        <div className="about-grid">
          <div>
            <span className="dim">App</span>
            <strong>{info?.name ?? 'Garuda'}</strong>
          </div>
          <div>
            <span className="dim">Version</span>
            <strong className="mono">{info?.version ?? '—'}</strong>
          </div>
          <div>
            <span className="dim">Mode</span>
            <strong>Local-first · no cloud</strong>
          </div>
        </div>
      </HudPanel>
    </div>
  )
}
