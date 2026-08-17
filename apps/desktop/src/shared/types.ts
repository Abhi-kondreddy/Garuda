export type AnalysisStage =
  | 'ingest'
  | 'audio_extract'
  | 'visual'
  | 'asr'
  | 'audio_features'
  | 'scoring'
  | 'export'

export interface ProgressEvent {
  type: 'progress'
  stage: AnalysisStage
  percent: number
  message: string
  etaSec?: number | null
  /** Optional finer-grained task inside a stage (e.g. download, transcribe). */
  phase?: string | null
  phasePercent?: number | null
}

export interface ErrorEvent {
  type: 'error'
  message: string
  detail?: string
}

export interface DoneEvent {
  type: 'done'
  reportPath: string
}

export type AnalyzerEvent = ProgressEvent | ErrorEvent | DoneEvent

export interface TranscriptSegment {
  start: number
  end: number
  text: string
  language: string
  confidence: number
}

export interface TimelinePoint {
  t: number
  interestingness: number
  motion: number
  audioEnergy: number
  brightness: number
}

export interface RiskZone {
  start: number
  end: number
  reason: string
  severity: 'low' | 'medium' | 'high'
  t?: number
  filterReason?: string
}

export interface Highlight {
  t: number
  score: number
  label: string
  thumb?: string
}

export interface PaletteColor {
  hex: string
  weight: number
}

export interface LanguageShare {
  code: string
  label: string
  percent: number
}

export interface AudioMetrics {
  loudnessConsistency: number
  clarity: number
  deadAirRatio: number
  clippingRatio: number
  musicSpeechRatio: number
  teluguPercent: number
  englishPercent: number
  hindiPercent?: number
  otherPercent: number
  languageBreakdown?: LanguageShare[]
  estimatedWpm: number | null
  silenceGaps: Array<{ start: number; end: number }>
}

export interface VisualMetrics {
  colorEvenness: number
  brightnessConsistency: number
  contrastConsistency: number
  exposureFlicker: number
  sceneCutRate: number
  staticStretchRatio: number
  onCamPresence: number
}

export interface AnalysisReport {
  version: 1 | 2 | 3
  createdAt: string
  sourcePath: string
  sourceName: string
  durationSec: number
  fps: number
  width: number
  height: number
  scores: {
    hook: number
    interestingness: number
    colorEvenness: number
    visualQuality: number
    audioQuality: number
    overall: number
  }
  visual: VisualMetrics
  audio: AudioMetrics
  timeline: TimelinePoint[]
  waveform: number[]
  transcript: TranscriptSegment[]
  riskZones: RiskZone[]
  highlights: Highlight[]
  palette: PaletteColor[]
  notes: string[]
  companion?: CompanionBundle
}

export interface CoachFinding {
  id: string
  severity: 'low' | 'medium' | 'high'
  title: string
  detail: string
  fix: string
  metric?: number | null
  t?: number | null
  tEnd?: number | null
  expectedLift?: Record<string, number>
  evidence?: string
}

export interface HookDoctor {
  score: number
  verdict: string
  speechOnsetSec: number | null
  firstCutSec: number | null
  findings: CoachFinding[]
  content?: {
    openingLine: string | null
    hasPromise: boolean
    hasQuestion: boolean
    isVague: boolean
    score: number
    t: number
    findings: CoachFinding[]
  }
}

export interface TitleIdea {
  angle: string
  title: string
  why: string
}

export interface ThumbCandidate {
  t: number
  score: number
  label: string
  tip: string
  brightness?: number
  faceBias?: number
  textSafeHint?: string
}

export interface PacingCoach {
  format: 'shorts' | 'long_form'
  score: number
  targets: {
    cutsPerMin: [number, number]
    wpm: [number, number]
    maxDeadAir: number
  }
  measured: {
    cutsPerMin: number
    wpm: number | null
    deadAirRatio: number
    longSilenceGaps: number
  }
  tips: Array<{
    id: string
    severity: 'low' | 'medium' | 'high'
    title: string
    detail: string
    fix: string
    t?: number
  }>
}

export interface ChecklistItem {
  id: string
  label: string
  status: 'pass' | 'fail'
  detail: string
  fix: string
  t?: number
}

export interface PublishChecklist {
  passed: number
  total: number
  ready: boolean
  items: ChecklistItem[]
}

export interface TalkingPoints {
  structure: Array<{
    act: string
    window: string
    beats: string[]
    coach: string
  }>
  outline: Array<{
    t: number
    text: string
    language: string
    role: string
  }>
  summary: string
}

export interface CutListItem {
  start: number
  end: number
  action: string
  reason: string
  severity: string
  suggestion: string
  t?: number
  expectedLift?: Record<string, number>
  evidence?: string
}

export interface ShortsClip {
  start: number
  end: number
  score: number
  label: string
  captionHook: string
  tip: string
  t?: number
}

export interface CoachFeedItem {
  source: string
  impact: 'critical' | 'high' | 'medium' | string
  title: string
  action: string
  t?: number
  expectedLift?: Record<string, number>
}

export interface NextGoal {
  metric: string
  current: number
  target: number
  plan: string
  t?: number
}

export interface ScoreDriver {
  scoreKey: string
  label: string
  value: number
  weight: number
  why: string[]
  t: number
}

export interface BeforeAfter {
  current: { overall: number; interestingness: number; hook: number }
  simulated: { overall: number; interestingness: number; hook: number }
  delta: { overall: number; interestingness: number; hook: number }
  assumption: string
  actionsUsed: number
  t: number
}

export interface CompanionBundle {
  hookDoctor: HookDoctor
  titlesThumbnails: {
    titles: TitleIdea[]
    thumbnails: ThumbCandidate[]
    seedPhrase: string
  }
  pacing: PacingCoach
  publishChecklist: PublishChecklist
  talkingPoints: TalkingPoints
  cutList: CutListItem[]
  shortsClips: ShortsClip[]
  coachFeed: CoachFeedItem[]
  nextGoals: NextGoal[]
  endingCta?: {
    score: number
    verdict: string
    windowStart: number
    energy: number
    hasCta: boolean
    ctaExcerpt: string | null
    findings: CoachFinding[]
    t: number
  }
  sectionEnergy?: {
    sections: Array<{
      name: string
      start: number
      end: number
      avgInterestingness: number
      peakT: number
      valleyT: number
      t: number
      note: string
    }>
    t: number
  }
  patternInterrupts?: {
    format: string
    score: number
    avgGapSec: number
    targetGapSec: number[]
    interruptCount: number
    longGaps: Array<{ start: number; end: number; gap: number }>
    events: number[]
    findings: CoachFinding[]
    t: number
  }
  talkingHeadBalance?: {
    score: number
    talkingHeadRatio: number
    brollProxy: number
    staticRatio: number
    cutsPerMin: number
    findings: CoachFinding[]
    t: number
  }
  exposureFlicker?: {
    score: number
    events: Array<{ t: number; delta: number; severity: string; reason: string; fix: string }>
    t: number
  }
  codeSwitch?: {
    score: number
    issues: Array<{
      t: number
      from: string
      to: string
      severity: string
      title: string
      detail: string
      fix: string
      expectedLift?: Record<string, number>
    }>
    t: number
  }
  musicUnderVo?: {
    score: number
    musicSpeechRatio: number
    clarity: number
    conflictWindows: Array<{ t: number; end: number; severity: string; reason: string; fix: string }>
    t: number
  }
  pauseTaxonomy?: {
    items: Array<{
      start: number
      end: number
      duration: number
      kind: string
      severity: string
      action: string
      t: number
      expectedLift?: Record<string, number>
    }>
    deadAirCount: number
    thinkCount: number
    t: number
  }
  scoreDrivers?: {
    overall: number
    drivers: ScoreDriver[]
  }
  fixActions?: Array<{
    id: string
    title: string
    detail: string
    t: number
    tEnd?: number
    expectedLift?: Record<string, number>
  }>
  beforeAfter?: BeforeAfter
  falseRisksRemoved?: RiskZone[]
  riskZonesFiltered?: RiskZone[]
}

export interface PastReportSummary {
  id: string
  sourceName: string
  createdAt: string
  overall: number
  reportPath: string
}

export type AppRoute = 'analyze' | 'library' | 'report' | 'settings'

export interface AppSettings {
  whisperModel: 'tiny' | 'base' | 'small'
  autoplay: boolean
  recentLimit: number
  confirmDelete: boolean
  /** Optional HuggingFace token for gated voice models (pyannote). */
  huggingfaceToken?: string
  /** Allow downloading large voice ML models on first use. */
  downloadVoiceModels?: boolean
}

export interface DataStats {
  path: string
  reportCount: number
  bytes: number
}

export interface AppInfo {
  version: string
  name: string
  platform: string
}

export const DEFAULT_SETTINGS: AppSettings = {
  whisperModel: 'tiny',
  autoplay: true,
  recentLimit: 8,
  confirmDelete: true,
  huggingfaceToken: '',
  downloadVoiceModels: true
}

/** ---- Voices / Render ---- */

export interface SpeakerSegment {
  start: number
  end: number
}

export interface SpeakerInfo {
  id: string
  label: string
  color: string
  durationSec: number
  stemPath: string
  segments: SpeakerSegment[]
}

export interface SpeakersManifest {
  version: 1
  createdAt: string
  audioPath: string
  residualPath: string | null
  mode: 'separated' | 'masked'
  warning?: string | null
  speakers: SpeakerInfo[]
}

export interface VoiceFxParams {
  gainDb: number
  bassDb: number
  clarityDb: number
  presenceDb: number
  compress: number
  deess: number
  gate: number
  mlEnhance: boolean
}

export const DEFAULT_VOICE_FX: VoiceFxParams = {
  gainDb: 0,
  bassDb: 0,
  clarityDb: 0,
  presenceDb: 0,
  compress: 0,
  deess: 0,
  gate: 0,
  mlEnhance: false
}

export interface VoicesProject {
  version: 1
  reportDir: string
  speakersPath: string
  previewMixPath: string | null
  fx: Record<string, VoiceFxParams>
}

export type RenderOp =
  | { type: 'audioRemix'; projectPath: string }
  | { type: 'muxVideo'; videoPath: string; audioPath: string }
  | { type: 'timelineCuts'; cuts: Array<{ start: number; end: number }> }
  | { type: 'colorGrade'; lut?: string; params?: Record<string, number> }

export interface RenderJob {
  id: string
  reportId: string
  ops: RenderOp[]
  status: 'queued' | 'running' | 'done' | 'error'
  progress: number
  outputPath?: string
  error?: string
}

export interface VoicesProgressEvent {
  type: 'progress'
  stage: string
  percent: number
  message: string
}
