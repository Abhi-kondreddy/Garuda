import { motion } from 'framer-motion'
import type { AnalysisStage, ProgressEvent } from '../../shared/types'
import ProgressTheater from '../components/ProgressTheater'
import SystemResourcePanel from '../components/SystemResourcePanel'
import './AnalyzingScreen.css'

interface Props {
  videoPath: string | null
  progress: ProgressEvent | null
  overall: number
  stagePercents: Partial<Record<AnalysisStage, number>>
  error: string | null
  onCancel: () => void
}

function formatClock(sec: number): string {
  const s = Math.max(0, Math.ceil(sec))
  const m = Math.floor(s / 60)
  const r = s % 60
  return m > 0 ? `${m}:${r.toString().padStart(2, '0')}` : `${s}s`
}

export default function AnalyzingScreen({
  videoPath,
  progress,
  overall,
  stagePercents,
  error,
  onCancel
}: Props) {
  const name = videoPath?.split(/[/\\]/).pop() ?? 'video'
  const elapsed = typeof progress?.elapsedSec === 'number' ? progress.elapsedSec : null
  const eta = typeof progress?.etaSec === 'number' && progress.etaSec > 0 ? progress.etaSec : null

  return (
    <div className="analyzing">
      <div className="analyzing-frame" aria-hidden>
        <span className="af-corner tl" />
        <span className="af-corner tr" />
        <span className="af-corner bl" />
        <span className="af-corner br" />
        <span className="af-scan" />
      </div>

      <div className="analyzing-head">
        <div>
          <p className="eyebrow">Mission · Active</p>
          <h1 className="analyzing-title">{name}</h1>
          <p className="muted analyzing-sub">
            Frame decode · face sampling · local Telugu / English ASR · scoring
          </p>
          <div className="analyzing-chips">
            <span className="mono chip live">LIVE</span>
            <span className="mono chip">{Math.round(overall)}% complete</span>
            {elapsed != null && <span className="mono chip">T+{formatClock(elapsed)}</span>}
            {eta != null && <span className="mono chip eta">ETA {formatClock(eta)}</span>}
          </div>
        </div>
        <button className="danger-btn" type="button" onClick={onCancel}>
          Abort run
        </button>
      </div>

      <ProgressTheater progress={progress} overall={overall} stagePercents={stagePercents} />

      <SystemResourcePanel compact pollMs={2000} />

      {error && (
        <motion.div
          className="analyzing-error"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <strong>Signal failure</strong>
          <p>{error}</p>
        </motion.div>
      )}
    </div>
  )
}
