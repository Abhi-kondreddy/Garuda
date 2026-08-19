import { motion } from 'framer-motion'
import type { ProgressEvent, AnalysisStage } from '../../shared/types'
import './ProgressTheater.css'

const STAGES: { id: AnalysisStage; label: string; short: string }[] = [
  { id: 'ingest', label: 'Ingest', short: 'Ingest' },
  { id: 'audio_extract', label: 'Audio extract', short: 'Audio' },
  { id: 'visual', label: 'Visual analysis', short: 'Visual' },
  { id: 'asr', label: 'Speech ASR', short: 'ASR' },
  { id: 'audio_features', label: 'Audio features', short: 'Features' },
  { id: 'scoring', label: 'Scoring', short: 'Score' },
  { id: 'export', label: 'Export', short: 'Export' }
]

interface Props {
  progress: ProgressEvent | null
  overall: number
  stagePercents: Partial<Record<AnalysisStage, number>>
}

function formatClock(sec: number): string {
  const s = Math.max(0, Math.ceil(sec))
  const m = Math.floor(s / 60)
  const r = s % 60
  return m > 0 ? `${m}:${r.toString().padStart(2, '0')}` : `${s}s`
}

function phaseLabel(phase?: string | null): string {
  const labels: Record<string, string> = {
    probe: 'Probing media',
    download: 'Downloading Whisper model',
    load: 'Loading Whisper into memory',
    transcribe: 'Transcribing speech',
    decode: 'Decoding frames',
    faces: 'Face / on-cam sampling',
    extract: 'Extracting audio',
    features: 'Computing audio features',
    score: 'Scoring metrics',
    write: 'Writing report'
  }
  if (!phase) return 'Current task'
  return labels[phase] ?? phase.replace(/_/g, ' ')
}

export default function ProgressTheater({ progress, overall, stagePercents }: Props) {
  const raw = String(progress?.stage ?? 'ingest')
  const active = (raw === 'frames' || raw === 'dense_sample' ? 'visual' : raw) as AnalysisStage
  const activeIndex = Math.max(
    0,
    STAGES.findIndex((s) => s.id === active)
  )

  const phase = progress?.phase ?? null
  const phasePercent =
    typeof progress?.phasePercent === 'number'
      ? progress.phasePercent
      : progress?.percent ?? 0

  return (
    <div className="theater">
      <div className="completion">
        <div className="completion-shine" aria-hidden />
        <div className="completion-meta">
          <span className="completion-label">Completion</span>
          <span className="completion-pct mono">{overall}%</span>
        </div>
        <div
          className="completion-track"
          role="progressbar"
          aria-valuenow={overall}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <motion.div
            className="completion-fill"
            initial={{ width: 0 }}
            animate={{ width: `${overall}%` }}
            transition={{ type: 'spring', stiffness: 80, damping: 20 }}
          />
          <div className="completion-glow" style={{ left: `${overall}%` }} />
        </div>
        <p className="completion-msg">
          {progress?.message ?? 'Preparing analysis engine…'}
          <span className="eta mono">
            {typeof progress?.elapsedSec === 'number' && (
              <> · {formatClock(progress.elapsedSec)} elapsed</>
            )}
            {typeof progress?.etaSec === 'number' && progress.etaSec > 0 && (
              <> · ~{formatClock(progress.etaSec)} remaining</>
            )}
          </span>
        </p>
      </div>

      <div className="mini-stack" aria-label="Stage progress">
        <div className="mini-stack-head">
          <span className="completion-label">Stage progress</span>
          {phase && (
            <span className="mini-phase mono">
              {phaseLabel(phase)} · {Math.round(phasePercent)}%
            </span>
          )}
        </div>
        <div className="mini-rows">
          {STAGES.map((stage, i) => {
            const state =
              i < activeIndex ? 'done' : i === activeIndex ? 'active' : 'pending'
            const pct =
              state === 'done'
                ? 100
                : state === 'active'
                  ? Math.max(0, Math.min(100, stagePercents[stage.id] ?? progress?.percent ?? 0))
                  : Math.max(0, Math.min(100, stagePercents[stage.id] ?? 0))
            return (
              <div key={stage.id} className={`mini-row ${state}`}>
                <span className="mini-label" title={stage.label}>
                  {stage.label}
                </span>
                <div className="mini-track">
                  <motion.div
                    className="mini-fill"
                    initial={false}
                    animate={{ width: `${pct}%` }}
                    transition={{ type: 'spring', stiffness: 120, damping: 22 }}
                  />
                </div>
                <span className="mini-pct mono">{Math.round(pct)}%</span>
              </div>
            )
          })}
        </div>
        {phase && (
          <div className="phase-bar">
            <div className="phase-meta">
              <span className="phase-label">{phaseLabel(phase)}</span>
              <span className="phase-pct mono">{Math.round(phasePercent)}%</span>
            </div>
            <div className="phase-track">
              <motion.div
                className="phase-fill"
                initial={false}
                animate={{ width: `${Math.max(0, Math.min(100, phasePercent))}%` }}
                transition={{ type: 'spring', stiffness: 100, damping: 20 }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
