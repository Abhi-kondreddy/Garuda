import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import AppNav from './components/AppNav'
import FxLayer from './components/FxLayer'
import HomeScreen from './screens/HomeScreen'
import AnalyzingScreen from './screens/AnalyzingScreen'
import ReportScreen from './screens/ReportScreen'
import LibraryScreen from './screens/LibraryScreen'
import SettingsScreen from './screens/SettingsScreen'
import EditorScreen from './screens/EditorScreen'
import type {
  AnalysisReport,
  AnalysisStage,
  AppRoute,
  AppSettings,
  PastReportSummary,
  ProgressEvent
} from '../shared/types'
import { DEFAULT_SETTINGS } from '../shared/types'

const STAGE_WEIGHTS: Record<string, number> = {
  ingest: 0.05,
  audio_extract: 0.08,
  visual: 0.47,
  asr: 0.22,
  audio_features: 0.08,
  scoring: 0.05,
  export: 0.05
}

const STAGE_ORDER = [
  'ingest',
  'audio_extract',
  'visual',
  'asr',
  'audio_features',
  'scoring',
  'export'
] as const

function normalizeStage(stage: string): string {
  if (stage === 'frames' || stage === 'dense_sample') return 'visual'
  return stage
}

function overallPercent(stage: string, stagePercent: number): number {
  const normalized = normalizeStage(stage)
  let base = 0
  for (const s of STAGE_ORDER) {
    if (s === normalized) {
      return Math.min(99, Math.round((base + STAGE_WEIGHTS[s] * (stagePercent / 100)) * 100))
    }
    base += STAGE_WEIGHTS[s] ?? 0
  }
  return Math.min(99, Math.round(base * 100))
}

export default function App() {
  const [route, setRoute] = useState<AppRoute>('analyze')
  const [analyzing, setAnalyzing] = useState(false)
  const [videoPath, setVideoPath] = useState<string | null>(null)
  const [progress, setProgress] = useState<ProgressEvent | null>(null)
  const [overall, setOverall] = useState(0)
  const [stagePercents, setStagePercents] = useState<Partial<Record<AnalysisStage, number>>>({})
  const [error, setError] = useState<string | null>(null)
  const [report, setReport] = useState<AnalysisReport | null>(null)
  const [reportPath, setReportPath] = useState<string | null>(null)
  const [pastReports, setPastReports] = useState<PastReportSummary[]>([])
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS)

  const refreshPast = useCallback(async () => {
    try {
      const list = await window.garuda.listReports()
      setPastReports(list)
    } catch {
      setPastReports([])
    }
  }, [])

  const loadSettings = useCallback(async () => {
    try {
      setSettings(await window.garuda.getSettings())
    } catch {
      setSettings(DEFAULT_SETTINGS)
    }
  }, [])

  useEffect(() => {
    void refreshPast()
    void loadSettings()
  }, [refreshPast, loadSettings])

  const beginAnalysis = useCallback(async (path: string) => {
    setVideoPath(path)
    setProgress(null)
    setOverall(0)
    setStagePercents({})
    setError(null)
    setReport(null)
    setReportPath(null)
    setAnalyzing(true)
    setRoute('analyze')
    await window.garuda.startAnalysis(path)
  }, [])

  const pickVideo = useCallback(async () => {
    const path = await window.garuda.openVideoDialog()
    if (path) await beginAnalysis(path)
  }, [beginAnalysis])

  useEffect(() => {
    const offProgress = window.garuda.onProgress((evt) => {
      const stage = normalizeStage(evt.stage) as AnalysisStage
      const next: ProgressEvent = { ...evt, stage }
      setProgress(next)
      setOverall(overallPercent(stage, evt.percent))
      setStagePercents((prev) => {
        const updated: Partial<Record<AnalysisStage, number>> = { ...prev }
        for (const s of STAGE_ORDER) {
          if (s === stage) {
            updated[s] = Math.max(updated[s] ?? 0, evt.percent)
            break
          }
          updated[s] = 100
        }
        return updated
      })
      setError(null)
    })
    const offError = window.garuda.onError((evt) => {
      setError(evt.detail ? `${evt.message} — ${evt.detail}` : evt.message)
    })
    const offDone = window.garuda.onDone(async ({ reportPath: path }) => {
      setOverall(100)
      setAnalyzing(false)
      try {
        const loaded = await window.garuda.loadReport(path)
        setReport(loaded)
        setReportPath(path)
        setRoute('report')
        void refreshPast()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load report')
        setRoute('analyze')
      }
    })
    const offCancelled = window.garuda.onCancelled(() => {
      setAnalyzing(false)
      setProgress(null)
      setOverall(0)
      setStagePercents({})
      setVideoPath(null)
      setRoute('analyze')
    })
    const offMenu = window.garuda.onMenuAction((action) => {
      if (action === 'open-video') void pickVideo()
      if (action === 'about-storage') setRoute('settings')
    })
    return () => {
      offProgress()
      offError()
      offDone()
      offCancelled()
      offMenu()
    }
  }, [refreshPast, pickVideo])

  useEffect(() => {
    return window.garuda.onNavigate((next) => {
      if (next === 'report' && !report) return
      setRoute(next)
    })
  }, [report])

  const openPast = async (item: PastReportSummary) => {
    const loaded = await window.garuda.loadReport(item.reportPath)
    setReport(loaded)
    setReportPath(item.reportPath)
    setRoute('report')
  }

  const navigate = (next: AppRoute) => {
    if (next === 'report' && !report) return
    setRoute(next)
  }

  const saveSettings = async (patch: Partial<AppSettings>) => {
    const next = await window.garuda.setSettings(patch)
    setSettings(next)
  }

  const onDataCleared = () => {
    setReport(null)
    setReportPath(null)
    setPastReports([])
    setAnalyzing(false)
    setProgress(null)
    setVideoPath(null)
    setError(null)
    setSettings(DEFAULT_SETTINGS)
    setRoute('analyze')
    void refreshPast()
    void loadSettings()
  }

  const showAnalyzing = analyzing && route === 'analyze'

  return (
    <div className="app-shell">
      <FxLayer />
      <header className="titlebar">
        <div className="titlebar-mark">
          <span className="titlebar-pip" />
          GARUDA
          <span className="titlebar-ticker mono">SIGNAL · LOCAL</span>
        </div>
        <div className="titlebar-actions">
          {analyzing && (
            <button
              className="danger-btn"
              type="button"
              onClick={() => void window.garuda.cancelAnalysis()}
            >
              Cancel analysis
            </button>
          )}
        </div>
      </header>

      <div className="app-body">
        <AppNav
          route={route}
          analyzing={analyzing}
          hasReport={Boolean(report)}
          reportCount={pastReports.length}
          onNavigate={navigate}
        />

        <main className="content">
          <AnimatePresence mode="wait">
            {route === 'analyze' && !showAnalyzing && (
              <motion.div
                key="analyze"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.35 }}
                style={{ height: '100%' }}
              >
                <HomeScreen
                  onPick={pickVideo}
                  onDropPath={beginAnalysis}
                  pastReports={pastReports}
                  recentLimit={settings.recentLimit}
                  onOpenPast={openPast}
                  onRefreshPast={refreshPast}
                  onOpenLibrary={() => setRoute('library')}
                />
              </motion.div>
            )}

            {showAnalyzing && (
              <motion.div
                key="analyzing"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.35 }}
                style={{ height: '100%' }}
              >
                <AnalyzingScreen
                  videoPath={videoPath}
                  progress={progress}
                  overall={overall}
                  stagePercents={stagePercents}
                  error={error}
                  onCancel={() => void window.garuda.cancelAnalysis()}
                />
              </motion.div>
            )}

            {route === 'editor' && (
              <motion.div
                key="editor"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.35 }}
                style={{ height: '100%' }}
              >
                <EditorScreen />
              </motion.div>
            )}

            {route === 'library' && (
              <motion.div
                key="library"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.35 }}
                style={{ height: '100%' }}
              >
                <LibraryScreen
                  reports={pastReports}
                  confirmDelete={settings.confirmDelete}
                  onOpen={openPast}
                  onRefresh={refreshPast}
                  onDelete={async (item) => {
                    const list = await window.garuda.deleteReport(item.reportPath)
                    setPastReports(list)
                    if (reportPath === item.reportPath) {
                      setReport(null)
                      setReportPath(null)
                      setRoute('library')
                    }
                  }}
                  onAnalyze={pickVideo}
                  onReveal={(item) => void window.garuda.openReportFolder(item.reportPath)}
                />
              </motion.div>
            )}

            {route === 'report' && report && (
              <motion.div
                key="report"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.4 }}
                style={{ height: '100%' }}
              >
                <ReportScreen
                  report={report}
                  reportPath={reportPath}
                  autoplay={settings.autoplay}
                  onAnalyzeAnother={pickVideo}
                />
              </motion.div>
            )}

            {route === 'settings' && (
              <motion.div
                key="settings"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.35 }}
                style={{ height: '100%' }}
              >
                <SettingsScreen
                  settings={settings}
                  onSave={saveSettings}
                  onCleared={onDataCleared}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </main>
      </div>
    </div>
  )
}
