import { useCallback, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import type { AnalysisReport } from '../../shared/types'
import ScoreRing from '../components/ScoreRing'
import TimelineChart from '../components/TimelineChart'
import CompanionPanel from '../components/CompanionPanel'
import VideoPlayer from '../components/VideoPlayer'
import VoicesPanel from '../components/VoicesPanel'
import {
  buildLanguageBreakdown,
  languageLabel,
  resolveSegmentLanguage
} from '../lib/languages'
import './ReportScreen.css'

interface Props {
  report: AnalysisReport
  reportPath: string | null
  autoplay?: boolean
  onAnalyzeAnother: () => void
}

function fmtTime(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function ReportScreen({
  report,
  reportPath,
  autoplay = true,
  onAnalyzeAnother
}: Props) {
  const [cursor, setCursor] = useState(0)
  const [seekToken, setSeekToken] = useState(0)
  const [tab, setTab] = useState<'coach' | 'metrics' | 'voices'>('coach')
  const [seekLabel, setSeekLabel] = useState<string | null>(null)
  const [previewMixPath, setPreviewMixPath] = useState<string | null>(null)
  const [usePreviewAudio, setUsePreviewAudio] = useState(false)

  const onPreviewMixReady = useCallback((mixPath: string | null) => {
    setPreviewMixPath(mixPath)
    if (!mixPath) setUsePreviewAudio(false)
  }, [])

  const cursorTranscript = useMemo(() => {
    return report.transcript.find((t) => cursor >= t.start && cursor <= t.end)
  }, [report.transcript, cursor])

  const companion = report.companion

  const languageBreakdown = useMemo(
    () => buildLanguageBreakdown(report.transcript, report.audio.languageBreakdown),
    [report.transcript, report.audio.languageBreakdown]
  )

  const seekTo = (t: number, label?: string, force = true) => {
    const safe = Number.isFinite(t) ? Math.max(0, t) : 0
    const capped =
      report.durationSec > 0 ? Math.min(report.durationSec, safe) : safe
    setCursor(capped)
    if (force) setSeekToken((n) => n + 1)
    setSeekLabel(label ? `${label} · ${fmtTime(capped)}` : `Playhead @ ${fmtTime(capped)}`)
  }

  const scoreSeek: Record<string, number> = {
    Hook: companion?.hookDoctor?.speechOnsetSec ?? companion?.hookDoctor?.content?.t ?? 0,
    Interestingness: companion?.sectionEnergy?.sections?.[1]?.valleyT ?? report.durationSec * 0.4,
    Color: 0,
    Visual: companion?.talkingHeadBalance?.t ?? 0,
    Audio: companion?.pauseTaxonomy?.t ?? 0,
    Overall: companion?.beforeAfter?.t ?? 0
  }

  return (
    <div className="report">
      <header className="report-hero">
        <div>
          <p className="eyebrow">YouTube companion</p>
          <h1>{report.sourceName}</h1>
          <p className="muted report-meta mono">
            {fmtTime(report.durationSec)} · {report.width}×{report.height} · {report.fps.toFixed(2)} fps ·{' '}
            {new Date(report.createdAt).toLocaleString()}
          </p>
        </div>
        <div className="report-actions">
          {reportPath && (
            <button
              className="ghost-btn"
              type="button"
              onClick={() => void window.garuda.openReportFolder(reportPath)}
            >
              Reveal files
            </button>
          )}
          <button className="primary-btn" type="button" onClick={onAnalyzeAnother}>
            Analyze another
          </button>
        </div>
      </header>

      <div className="report-stage">
        <VideoPlayer
          sourcePath={report.sourcePath}
          currentTime={cursor}
          duration={report.durationSec}
          onTimeUpdate={setCursor}
          label={seekLabel}
          seekToken={seekToken}
          autoplay={autoplay}
          audioOverridePath={usePreviewAudio ? previewMixPath : null}
        />

        <section className="score-row score-row-compact">
          {(
            [
              ['Overall', report.scores.overall],
              ['Hook', report.scores.hook],
              ['Interestingness', report.scores.interestingness],
              ['Color', report.scores.colorEvenness],
              ['Visual', report.scores.visualQuality],
              ['Audio', report.scores.audioQuality]
            ] as const
          ).map(([label, value], i) => (
            <motion.button
              key={label}
              type="button"
              className="score-hit"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 * i }}
              onClick={() => seekTo(scoreSeek[label] ?? 0, label)}
              title={`Jump to evidence for ${label}`}
            >
              <ScoreRing label={label} value={value} />
            </motion.button>
          ))}
        </section>
      </div>

      <div className="report-tabs">
        <button type="button" className={tab === 'coach' ? 'active' : ''} onClick={() => setTab('coach')}>
          Coach
        </button>
        <button
          type="button"
          className={tab === 'metrics' ? 'active' : ''}
          onClick={() => setTab('metrics')}
        >
          Metrics
        </button>
        <button
          type="button"
          className={tab === 'voices' ? 'active' : ''}
          onClick={() => setTab('voices')}
        >
          Voices
        </button>
      </div>

      <section className="timeline-panel">
        <div className="panel-head">
          <h2>Interestingness & waveform</h2>
          <span className="mono muted">{fmtTime(cursor)}</span>
        </div>
        <TimelineChart
          report={report}
          cursor={cursor}
          onCursorChange={(t) => seekTo(t, 'Timeline', false)}
        />
        <div className="risk-legend">
          {report.riskZones.map((z, i) => (
            <button
              key={i}
              type="button"
              className={`risk-chip ${z.severity}`}
              onClick={() => seekTo(Number(z.t ?? z.start) || 0, z.reason)}
            >
              {fmtTime(z.start)}–{fmtTime(z.end)} · {z.reason}
            </button>
          ))}
          {report.riskZones.length === 0 && (
            <span className="muted">No major retention risk zones detected.</span>
          )}
        </div>
      </section>

      {tab === 'coach' && companion && (
        <CompanionPanel companion={companion} onSeek={seekTo} fmtTime={fmtTime} />
      )}

      {tab === 'coach' && !companion && (
        <section className="panel panel-wide">
          <p className="muted">Re-analyze to unlock deep coach modules and playhead evidence.</p>
        </section>
      )}

      {tab === 'voices' && reportPath && (
        <VoicesPanel
          reportPath={reportPath}
          onPreviewMixReady={onPreviewMixReady}
          onPlayMix={(mixPath) => {
            setPreviewMixPath(mixPath)
            setUsePreviewAudio(true)
            seekTo(0, 'Preview mix')
          }}
        />
      )}

      {tab === 'voices' && !reportPath && (
        <section className="panel panel-wide">
          <p className="muted">Open a saved report to use Voices.</p>
        </section>
      )}

      {tab === 'metrics' && (
        <div className="report-grid">
          <section className="panel">
            <h2>Visual</h2>
            <dl className="metric-list">
              <div>
                <dt>Color evenness</dt>
                <dd className="mono">{Math.round(report.visual.colorEvenness)}</dd>
              </div>
              <div>
                <dt>On-camera presence</dt>
                <dd className="mono">{(report.visual.onCamPresence * 100).toFixed(0)}%</dd>
              </div>
              <div>
                <dt>Scene cuts / min</dt>
                <dd className="mono">{report.visual.sceneCutRate.toFixed(1)}</dd>
              </div>
            </dl>
          </section>
          <section className="panel">
            <h2>Audio · Languages</h2>
            <dl className="metric-list">
              {languageBreakdown.length === 0 ? (
                <div>
                  <dt>Detected</dt>
                  <dd className="mono">—</dd>
                </div>
              ) : (
                languageBreakdown.map((lang) => (
                  <div key={lang.code}>
                    <dt>{lang.label}</dt>
                    <dd className="mono">{Math.round(lang.percent)}%</dd>
                  </div>
                ))
              )}
              <div>
                <dt>Est. WPM</dt>
                <dd className="mono">{report.audio.estimatedWpm ?? '—'}</dd>
              </div>
            </dl>
            {languageBreakdown.length > 0 && (
              <div className="lang-bar" aria-hidden>
                {languageBreakdown.map((lang) => (
                  <span
                    key={lang.code}
                    className={`lang-seg lang-${lang.code}`}
                    style={{ width: `${Math.max(2, lang.percent)}%` }}
                    title={`${lang.label} ${lang.percent}%`}
                  />
                ))}
              </div>
            )}
          </section>
          <section className="panel panel-wide">
            <div className="panel-head">
              <h2>Transcript</h2>
              {cursorTranscript && (
                <span className={`lang-tag lang-${resolveSegmentLanguage(cursorTranscript)}`}>
                  {languageLabel(resolveSegmentLanguage(cursorTranscript))}
                </span>
              )}
            </div>
            <div className="transcript">
              {report.transcript.map((seg, i) => {
                const lang = resolveSegmentLanguage(seg)
                return (
                  <button
                    key={i}
                    type="button"
                    className={`seg ${cursor >= seg.start && cursor <= seg.end ? 'active' : ''} lang-${lang}`}
                    onClick={() => seekTo(seg.start, seg.text.slice(0, 40))}
                  >
                    <span className="seg-time mono">{fmtTime(seg.start)}</span>
                    <span className="seg-text">{seg.text}</span>
                  </button>
                )
              })}
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
