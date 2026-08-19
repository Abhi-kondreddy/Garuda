import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  SpeakersManifest,
  VoiceFxParams,
  VoicesProject,
  VoicesProgressEvent
} from '../../shared/types'
import { DEFAULT_VOICE_FX } from '../../shared/types'
import HudPanel from './HudPanel'
import './VoicesPanel.css'

interface Props {
  reportPath: string
  onPreviewMixReady: (mixPath: string | null) => void
  onPlayMix: (mixPath: string) => void
}

function fmtDur(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function reportDirOf(reportPath: string): string {
  const i = Math.max(reportPath.lastIndexOf('/'), reportPath.lastIndexOf('\\'))
  return i >= 0 ? reportPath.slice(0, i) : reportPath
}

function asJobKind(
  kind: string | null | undefined
): 'idle' | 'analyze' | 'preview' | 'solo' | 'export' {
  if (kind === 'analyze' || kind === 'preview' || kind === 'solo' || kind === 'export') return kind
  return 'analyze'
}

const SLIDERS: Array<{ key: keyof VoiceFxParams; label: string; min: number; max: number; step: number }> =
  [
    { key: 'gainDb', label: 'Gain', min: -12, max: 12, step: 0.5 },
    { key: 'bassDb', label: 'Bass', min: -8, max: 8, step: 0.5 },
    { key: 'clarityDb', label: 'Clarity', min: -8, max: 8, step: 0.5 },
    { key: 'presenceDb', label: 'Presence', min: -8, max: 8, step: 0.5 },
    { key: 'compress', label: 'Compress', min: 0, max: 1, step: 0.05 },
    { key: 'deess', label: 'De-ess', min: 0, max: 1, step: 0.05 },
    { key: 'gate', label: 'Gate', min: 0, max: 1, step: 0.05 }
  ]

export default function VoicesPanel({ reportPath, onPreviewMixReady, onPlayMix }: Props) {
  const [manifest, setManifest] = useState<SpeakersManifest | null>(null)
  const [project, setProject] = useState<VoicesProject | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [jobKind, setJobKind] = useState<'idle' | 'analyze' | 'preview' | 'solo' | 'export'>('idle')
  const [progress, setProgress] = useState<VoicesProgressEvent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [exportPath, setExportPath] = useState<string | null>(null)
  const [soloUrl, setSoloUrl] = useState<string | null>(null)
  const soloAudioRef = useRef<HTMLAudioElement | null>(null)
  const debounceRef = useRef<number | null>(null)
  const pendingJob = useRef<'idle' | 'analyze' | 'preview' | 'solo' | 'export'>('idle')

  const refresh = useCallback(async () => {
    const [m, p, exp] = await Promise.all([
      window.garuda.voicesGetManifest(reportPath),
      window.garuda.voicesGetProject(reportPath),
      window.garuda.voicesLatestExport(reportPath)
    ])
    setManifest(m)
    setProject(p)
    setExportPath(exp)
    onPreviewMixReady(p?.previewMixPath ?? null)
    if (m?.speakers?.length) {
      setSelectedId((prev) => prev ?? m.speakers[0].id)
    }
  }, [reportPath, onPreviewMixReady])

  const reconnectRunningJob = useCallback(async (): Promise<boolean> => {
    try {
      const status = await window.garuda.voicesJobStatus?.()
      if (!status?.running) return false
      const mine = reportDirOf(reportPath)
      if (status.reportDir && status.reportDir !== mine) {
        setBusy(false)
        setJobKind('idle')
        pendingJob.current = 'idle'
        setProgress(null)
        setError(
          'A voices job is already running on another report. Cancel it or wait for it to finish.'
        )
        return true
      }
      const kind = asJobKind(status.kind)
      setError(null)
      setBusy(true)
      setJobKind(kind)
      pendingJob.current = kind
      setProgress(
        status.progress ?? {
          type: 'progress',
          stage: kind,
          percent: 1,
          message: `Resuming ${kind}…`
        }
      )
      return true
    } catch {
      // Preload/main not ready (e.g. HMR) — treat as idle so Detect still works
      return false
    }
  }, [reportPath])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    void reconnectRunningJob()
  }, [reconnectRunningJob])

  useEffect(() => {
    const offP = window.garuda.onVoicesProgress((evt) => {
      setBusy(true)
      setError(null)
      setProgress(evt)
      if (pendingJob.current === 'idle') {
        const kind = asJobKind(evt.stage)
        setJobKind(kind)
        pendingJob.current = kind
      }
    })
    const offD = window.garuda.onVoicesDone(async (evt) => {
      setBusy(false)
      setProgress(null)
      const kind = pendingJob.current
      pendingJob.current = 'idle'
      setJobKind('idle')
      if (kind === 'solo' && typeof evt.path === 'string') {
        const url = await window.garuda.mediaUrl(evt.path)
        setSoloUrl(url)
        if (url && soloAudioRef.current) {
          soloAudioRef.current.src = url
          void soloAudioRef.current.play().catch(() => undefined)
        }
      } else if (kind === 'export' && typeof evt.outputPath === 'string') {
        setExportPath(evt.outputPath)
      }
      await refresh()
    })
    const offE = window.garuda.onVoicesError((evt) => {
      if (String(evt.message).includes('already running')) {
        void reconnectRunningJob()
        return
      }
      setBusy(false)
      setJobKind('idle')
      pendingJob.current = 'idle'
      setProgress(null)
      setError(evt.message + (evt.detail ? ` — ${evt.detail}` : ''))
    })
    const offC = window.garuda.onVoicesCancelled(() => {
      setBusy(false)
      setJobKind('idle')
      pendingJob.current = 'idle'
      setProgress(null)
      setError(null)
    })
    return () => {
      offP()
      offD()
      offE()
      offC()
    }
  }, [refresh, reconnectRunningJob])

  const selected = manifest?.speakers.find((s) => s.id === selectedId) ?? null
  const fx: VoiceFxParams =
    (selectedId && project?.fx[selectedId]) || DEFAULT_VOICE_FX

  const persistFx = async (nextFx: VoiceFxParams) => {
    if (!project || !selectedId) return
    const next: VoicesProject = {
      ...project,
      fx: { ...project.fx, [selectedId]: nextFx }
    }
    setProject(next)
    await window.garuda.voicesSaveProject(reportPath, next)
  }

  const setFxKey = (key: keyof VoiceFxParams, value: number | boolean) => {
    const next = { ...fx, [key]: value } as VoiceFxParams
    void persistFx(next)
  }

  const cancelJob = () => {
    void window.garuda.voicesCancel()
    setBusy(false)
    setJobKind('idle')
    pendingJob.current = 'idle'
    setProgress(null)
    setError(null)
  }

  const runJob = async (kind: typeof jobKind, start: () => Promise<unknown>) => {
    let adopted = false
    try {
      adopted = await reconnectRunningJob()
    } catch {
      adopted = false
    }
    if (adopted) return

    setError(null)
    setBusy(true)
    setJobKind(kind)
    pendingJob.current = kind
    setProgress({ type: 'progress', stage: kind, percent: 0, message: 'Starting…' })
    try {
      await start()
    } catch (e) {
      setBusy(false)
      setJobKind('idle')
      pendingJob.current = 'idle'
      setProgress(null)
      setError(e instanceof Error ? e.message : 'Job failed')
    }
  }

  const detect = () =>
    void runJob('analyze', () => window.garuda.voicesAnalyze(reportPath))

  const applyMix = () =>
    void runJob('preview', () => window.garuda.voicesBuildPreview(reportPath))

  const exportVideo = () =>
    void runJob('export', () => window.garuda.voicesRender(reportPath))

  const playSolo = async (speakerId?: string) => {
    const id = speakerId ?? selectedId
    if (!id) return
    const stem = manifest?.speakers.find((s) => s.id === id)?.stemPath
    if (stem) {
      const url = await window.garuda.mediaUrl(stem)
      setSoloUrl(url)
      if (url && soloAudioRef.current) {
        soloAudioRef.current.src = url
        void soloAudioRef.current.play().catch(() => undefined)
      }
    }
    if (debounceRef.current) window.clearTimeout(debounceRef.current)
    debounceRef.current = window.setTimeout(() => {
      void runJob('solo', () => window.garuda.voicesSoloEnhance(reportPath, id))
    }, 280)
  }

  const renameSpeaker = async (id: string, label: string) => {
    if (!manifest) return
    const next: SpeakersManifest = {
      ...manifest,
      speakers: manifest.speakers.map((s) => (s.id === id ? { ...s, label } : s))
    }
    setManifest(next)
    await window.garuda.voicesSaveManifest(reportPath, next)
  }

  return (
    <div className="voices">
      <audio ref={soloAudioRef} className="voices-hidden-audio" />
      <HudPanel title="Voice lanes" eyebrow="Separation" delay={0.05} className="voices-left">
        {!manifest ? (
          <div className="voices-empty">
            <p className="muted">
              Detect overlapping speakers, isolate stems, then shape each voice before export.
            </p>
            <div className="voices-actions">
              <button className="primary-btn" type="button" disabled={busy || !reportPath} onClick={detect}>
                {busy && jobKind === 'analyze' ? 'Detecting…' : 'Detect voices'}
              </button>
              {busy && (
                <button className="ghost-btn" type="button" onClick={cancelJob}>
                  Cancel
                </button>
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="voices-mode-row">
              <span className={`voices-mode mono ${manifest.mode}`}>
                {manifest.mode === 'separated' ? 'NEURAL' : 'STFT MASKED'}
              </span>
              <button className="ghost-btn" type="button" disabled={busy} onClick={detect}>
                Re-detect
              </button>
            </div>
            {manifest.warning && <p className="voices-warn">{manifest.warning}</p>}
            {manifest.mode === 'masked' && (
              <p className="voices-hint muted">
                Soft isolation from who-spoke-when. For stronger overlap cleanup on 2–4 voices,
                install torch + speechbrain in the analysis venv, keep Download voice models on,
                then Re-detect.
              </p>
            )}
            <ul className="voices-list">
              {manifest.speakers.map((spk) => (
                <li key={spk.id}>
                  <button
                    type="button"
                    className={`voices-row ${selectedId === spk.id ? 'selected' : ''}`}
                    onClick={() => setSelectedId(spk.id)}
                  >
                    <span className="voices-chip" style={{ background: spk.color }} />
                    <span className="voices-row-meta">
                      <input
                        className="voices-rename"
                        value={spk.label}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => void renameSpeaker(spk.id, e.target.value)}
                      />
                      <span className="mono muted">{fmtDur(spk.durationSec)}</span>
                    </span>
                    <span
                      className="voices-solo-btn"
                      role="button"
                      tabIndex={0}
                      onClick={(e) => {
                        e.stopPropagation()
                        setSelectedId(spk.id)
                        void playSolo(spk.id)
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.stopPropagation()
                          setSelectedId(spk.id)
                          void playSolo(spk.id)
                        }
                      }}
                    >
                      Solo
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </HudPanel>

      <HudPanel title="Enhancement" eyebrow="Per speaker" delay={0.1} className="voices-right" tone="lime">
        {!selected || !project ? (
          <p className="muted">Select a speaker after detection to tune FX.</p>
        ) : (
          <>
            <p className="voices-selected mono" style={{ color: selected.color }}>
              {selected.label}
            </p>
            <div className="voices-sliders">
              {SLIDERS.map((s) => (
                <label key={s.key} className="voices-slider">
                  <span>
                    {s.label}
                    <em className="mono">{Number(fx[s.key]).toFixed(s.step < 1 ? 2 : 1)}</em>
                  </span>
                  <input
                    type="range"
                    min={s.min}
                    max={s.max}
                    step={s.step}
                    value={Number(fx[s.key])}
                    disabled={busy}
                    onChange={(e) => setFxKey(s.key, Number(e.target.value))}
                  />
                </label>
              ))}
            </div>
            <button
              type="button"
              className={`toggle-card voices-ml ${fx.mlEnhance ? 'on' : ''}`}
              disabled={busy}
              onClick={() => setFxKey('mlEnhance', !fx.mlEnhance)}
            >
              <span className="toggle-led" />
              <span>ML speech enhance</span>
            </button>
            <div className="voices-actions">
              <button className="ghost-btn" type="button" disabled={busy} onClick={() => void playSolo()}>
                Play solo
              </button>
              <button className="primary-btn" type="button" disabled={busy} onClick={applyMix}>
                Apply to mix
              </button>
              <button
                className="ghost-btn"
                type="button"
                disabled={busy || !project.previewMixPath}
                onClick={() => {
                  if (project.previewMixPath) onPlayMix(project.previewMixPath)
                }}
              >
                Play full with changes
              </button>
              <button className="primary-btn" type="button" disabled={busy} onClick={exportVideo}>
                Export video
              </button>
            </div>
            {exportPath && (
              <button
                className="ghost-btn voices-reveal"
                type="button"
                onClick={() => void window.garuda.voicesRevealExport(exportPath)}
              >
                Reveal export
              </button>
            )}
            {soloUrl && <p className="hint muted mono">Solo cache ready</p>}
          </>
        )}
      </HudPanel>

      {(busy || progress) && (
        <div className="voices-progress">
          <div className="voices-progress-head">
            <span className="mono voices-progress-pct">
              {Math.round(Math.min(100, progress?.percent ?? 0))}%
            </span>
            {typeof progress?.phasePercent === 'number' && (
              <span className="mono muted voices-progress-phase-label">
                {progress.phase === 'sepformer'
                  ? 'pass'
                  : progress.phase === 'cascade'
                    ? 'cascade'
                    : progress.phase || 'phase'}{' '}
                {Math.round(progress.phasePercent)}%
              </span>
            )}
          </div>
          <div
            className={`voices-progress-bar${
              progress?.phase === 'sepformer' ? ' voices-progress-bar--live' : ''
            }`}
          >
            <span style={{ width: `${Math.min(100, Math.max(4, progress?.percent ?? 8))}%` }} />
          </div>
          {typeof progress?.phasePercent === 'number' && (
            <div className="voices-progress-phase">
              <span style={{ width: `${Math.min(100, Math.max(2, progress.phasePercent))}%` }} />
            </div>
          )}
          <div className="voices-progress-meta">
            <span className="mono">{progress?.message ?? 'Working…'}</span>
            <button className="ghost-btn" type="button" onClick={cancelJob}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {error && <p className="voices-error">{error}</p>}
    </div>
  )
}
