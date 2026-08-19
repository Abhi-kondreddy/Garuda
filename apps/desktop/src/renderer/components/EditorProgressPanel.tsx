import type { EditorProgressEvent } from '../../shared/types'
import './EditorProgressPanel.css'

const STAGES = [
  { id: 'propose', label: 'Start' },
  { id: 'analyze', label: 'Read clips' },
  { id: 'assemble', label: 'Assemble' },
  { id: 'export', label: 'Export' }
] as const

type StageId = (typeof STAGES)[number]['id']

function normalizeStage(stage: string): StageId {
  if (
    stage === 'analyze' ||
    stage === 'visual' ||
    stage === 'asr' ||
    stage === 'audio_features' ||
    stage === 'scoring' ||
    stage === 'ingest' ||
    stage === 'audio_extract'
  ) {
    return 'analyze'
  }
  if (stage === 'export' || stage === 'render') return 'export'
  if (stage === 'assemble') return 'assemble'
  return 'propose'
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
    decode: 'Decoding frames',
    faces: 'Face / on-cam sampling',
    extract: 'Extracting audio',
    features: 'Audio features',
    score: 'Scoring hook & energy',
    write: 'Writing clip report',
    cache: 'Using cached analysis',
    assemble: 'Building timelines',
    encode: 'Encoding',
    concat: 'Concatenating',
    title: 'Burning title',
    transcribe: 'Speech (ASR)'
  }
  if (!phase) return 'Current task'
  return labels[phase] ?? phase.replace(/_/g, ' ')
}

function parseClipFromMessage(message: string): { index?: number; total?: number; rest: string } {
  const m = message.match(/\[(\d+)\/(\d+)\]\s*(.*)/)
  if (!m) return { rest: message }
  return { index: Number(m[1]), total: Number(m[2]), rest: m[3] || message }
}

function clampPct(n: number): number {
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.min(100, n))
}

interface Props {
  progress: EditorProgressEvent | null
  overall: number
  stagePercents: Partial<Record<StageId, number>>
  jobLabel?: string
  onCancel: () => void
}

export default function EditorProgressPanel({
  progress,
  overall,
  stagePercents,
  jobLabel = 'Deep propose',
  onCancel
}: Props) {
  const active = normalizeStage(progress?.stage || 'propose')
  const activeIndex = Math.max(0, STAGES.findIndex((s) => s.id === active))
  const parsed = parseClipFromMessage(progress?.message || '')
  const clipIndex = progress?.clipIndex ?? parsed.index ?? null
  const clipTotal = progress?.clipTotal ?? parsed.total ?? null
  const phase = progress?.phase ?? null
  const overallPct = clampPct(overall)
  const phasePercent = clampPct(
    typeof progress?.phasePercent === 'number' ? progress.phasePercent : progress?.percent ?? 0
  )

  return (
    <div className="editor-progress-panel" role="status" aria-live="polite">
      <div className="epp-head">
        <div>
          <p className="eyebrow mono">PROGRESS</p>
          <h2>{jobLabel}</h2>
          <p className="muted epp-sub">
            {clipIndex && clipTotal
              ? `Clip ${clipIndex} of ${clipTotal}`
              : 'Reading footage and assembling timelines'}
            {progress?.clipName ? ` · ${progress.clipName}` : ''}
          </p>
        </div>
        <button type="button" className="danger-btn" onClick={onCancel}>
          Cancel
        </button>
      </div>

      <div className="epp-completion">
        <div className="epp-completion-meta">
          <span className="epp-label">Overall</span>
          <span className="epp-pct mono">{Math.round(overallPct)}%</span>
        </div>
        <div
          className="epp-track epp-track-lg"
          role="progressbar"
          aria-valuenow={overallPct}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div className="epp-fill epp-fill-main" style={{ width: `${overallPct}%` }} />
        </div>
      </div>

      <div className="epp-stages" aria-label="Stage progress">
        {STAGES.map((stage, i) => {
          const state = i < activeIndex ? 'done' : i === activeIndex ? 'active' : 'pending'
          const pct = clampPct(
            state === 'done'
              ? 100
              : state === 'active'
                ? stagePercents[stage.id] ?? progress?.percent ?? 0
                : stagePercents[stage.id] ?? 0
          )
          return (
            <div key={stage.id} className={`epp-stage ${state}`}>
              <div className="epp-stage-top">
                <span className="epp-stage-dot" />
                <span className="epp-stage-name">{stage.label}</span>
                <span className="mono epp-stage-pct">{Math.round(pct)}%</span>
              </div>
              <div className="epp-track epp-track-sm">
                <div className="epp-fill" style={{ width: `${pct}%` }} />
              </div>
            </div>
          )
        })}
      </div>

      <div className="epp-phase">
        <div className="epp-phase-meta">
          <span className="epp-label">{phase ? phaseLabel(phase) : 'Current task'}</span>
          <span className="mono epp-phase-pct">{Math.round(phasePercent)}%</span>
        </div>
        <div className="epp-track epp-track-phase">
          <div className="epp-fill epp-fill-phase" style={{ width: `${phasePercent}%` }} />
        </div>
        <p className="epp-msg">
          {progress?.message || 'Working…'}
          <span className="epp-timing mono">
            {typeof progress?.elapsedSec === 'number' && (
              <> · {formatClock(progress.elapsedSec)} elapsed</>
            )}
            {typeof progress?.etaSec === 'number' && progress.etaSec > 0 && (
              <> · ~{formatClock(progress.etaSec)} remaining</>
            )}
          </span>
        </p>
      </div>

      {clipTotal != null && clipTotal > 0 && (
        <div className="epp-clips" aria-label="Clip queue">
          {Array.from({ length: Math.min(clipTotal, 40) }).map((_, i) => {
            const n = i + 1
            const state =
              clipIndex == null ? 'pending' : n < clipIndex ? 'done' : n === clipIndex ? 'active' : 'pending'
            return (
              <div key={n} className={`epp-clip-pill ${state}`}>
                <span className="mono">{n}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
