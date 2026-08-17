import { motion } from 'framer-motion'
import type { AnalysisStage, ProgressEvent } from '../../shared/types'
import ProgressTheater from '../components/ProgressTheater'
import './AnalyzingScreen.css'

interface Props {
  videoPath: string | null
  progress: ProgressEvent | null
  overall: number
  stagePercents: Partial<Record<AnalysisStage, number>>
  error: string | null
  onCancel: () => void
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

  return (
    <div className="analyzing">
      <div className="analyzing-head">
        <div>
          <p className="eyebrow">Analyzing</p>
          <h1 className="analyzing-title">{name}</h1>
          <p className="muted analyzing-sub">
            One visual pass (every frame + face sampling) · local Telugu/English ASR
          </p>
        </div>
        <button className="danger-btn" type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>

      <ProgressTheater progress={progress} overall={overall} stagePercents={stagePercents} />

      {error && (
        <motion.div
          className="analyzing-error"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <strong>Something went wrong</strong>
          <p>{error}</p>
        </motion.div>
      )}
    </div>
  )
}
