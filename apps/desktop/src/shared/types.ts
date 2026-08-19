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

export interface WordTiming {
  start: number
  end: number
  word: string
}

export interface TranscriptSegment {
  start: number
  end: number
  text: string
  language: string
  confidence: number
  words?: WordTiming[]
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

export interface DeliveryMetrics {
  energyDynamics?: number
  pitchHz?: number | null
  pitchVarHz?: number | null
  speechActivity?: number
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
  /** Integrated loudness (EBU R128) and platform target in LUFS. */
  lufs?: number | null
  lufsTarget?: number | null
  lufsGap?: number | null
  delivery?: DeliveryMetrics
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

export interface Chapter {
  t: number
  time: string
  title: string
}

export interface Keyword {
  term: string
  count: number
}

export interface FaceBox {
  t: number
  cx: number
  cy: number
  w: number
  h: number
}

export interface RetentionPoint {
  t: number
  retention: number
  dropRisk: number
}

export interface RetentionCurve {
  points: RetentionPoint[]
  predictedRetention: number | null
  worstDropT: number | null
}

export interface BrollSegment {
  start: number
  end: number
  kind: 'talking_head' | 'broll'
}

export interface Framing {
  hasFaceData: boolean
  meanCenter?: { cx: number; cy: number } | null
  ruleOfThirds?: boolean
  findings: CoachFinding[]
  brollTimeline: BrollSegment[]
}

export interface ThumbnailFile {
  t: number
  path: string
}

export interface MetricContract {
  id: string
  label: string
  value: number | string | boolean | number[] | null
  unit: string
  range: [number, number] | null
  method: string
  version: string
  confidence: number
  lowConfidence: boolean
  evidence: Array<{ t: number; tEnd?: number }>
  severity: 'low' | 'medium' | 'high' | null
  recommendation: string | null
  group: string
}

export interface Provenance {
  scoringVersion: string
  engine: string
  python: string
  platform: string
  configHash: string
  seed: number
  ffmpeg?: string | null
  ffprobe?: string | null
  models: Record<string, string>
}

export interface PredictionInterval {
  value: number
  lo: number
  hi: number
}

export interface Predictions {
  calibrationVersion: string
  method: string
  targets: Record<string, PredictionInterval>
  retentionCurve?: Array<{ tFrac: number; retentionPct: number }>
}

export interface DropRiskPoint {
  t: number
  risk: number
  reasons: string[]
}

export interface MetricDriver {
  metricId: string
  label: string
  value: number | string | boolean | number[] | null
  severity: string
  recommendation: string
  t: number
}

export interface MetricBenchmark {
  percentile: number
  cohortN: number
}

export interface AnalysisReport {
  version: 1 | 2 | 3
  /** Heuristic scoring model version (distinct from schema `version`). */
  scoringVersion?: string
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
  chapters?: Chapter[]
  keywords?: Keyword[]
  faceBoxes?: FaceBox[]
  retentionCurve?: RetentionCurve
  retentionCurveCalibrated?: Array<{ tFrac: number; retentionPct: number }>
  framing?: Framing
  thumbnailFiles?: ThumbnailFile[]
  /** Metric-contract layer: every parameter with unit/range/method/confidence. */
  metrics?: Record<string, MetricContract>
  provenance?: Provenance
  diagnostics?: Record<string, unknown>
  predictions?: Predictions
  benchmarks?: Record<string, MetricBenchmark>
  dropRiskTimeline?: DropRiskPoint[]
  topDrivers?: MetricDriver[]
  contentHash?: string
  notes: string[]
  companion?: CompanionBundle
}

/** Defensive backfill so older/newer reports never crash consumers. */
export function normalizeReport(raw: AnalysisReport): AnalysisReport {
  const r = { ...(raw || {}) } as AnalysisReport
  r.timeline = Array.isArray(r.timeline) ? r.timeline : []
  r.transcript = Array.isArray(r.transcript) ? r.transcript : []
  r.riskZones = Array.isArray(r.riskZones) ? r.riskZones : []
  r.highlights = Array.isArray(r.highlights) ? r.highlights : []
  r.palette = Array.isArray(r.palette) ? r.palette : []
  r.waveform = Array.isArray(r.waveform) ? r.waveform : []
  r.notes = Array.isArray(r.notes) ? r.notes : []
  r.metrics = r.metrics && typeof r.metrics === 'object' ? r.metrics : {}
  r.dropRiskTimeline = Array.isArray(r.dropRiskTimeline) ? r.dropRiskTimeline : []
  r.topDrivers = Array.isArray(r.topDrivers) ? r.topDrivers : []
  return r
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

export type AppRoute = 'analyze' | 'library' | 'report' | 'settings' | 'editor'

/** ---- Edit projects (YouTube assembly) ---- */

export type EditLook = 'neutral' | 'warm' | 'contrast'
export type EditMusicMood = 'none' | 'chill' | 'upbeat' | 'cinematic' | 'custom'

export interface EditClip {
  id: string
  path: string
  name: string
  durationSec: number | null
  mtimeMs?: number
}

export interface EditTextCue {
  id: string
  when: 'hook' | 'chapter' | 'end' | 'custom'
  text: string
  style: 'title' | 'lower_third' | 'big_center'
  timeSec?: number
}

export interface EditBriefing {
  title: string
  subtitle: string
  cta: string
  look: EditLook
  musicMood: EditMusicMood
  customMusicPath?: string
  texts: EditTextCue[]
  format: { longCount: number; shortsCount: number }
  longTargetMin: number
  shortMaxSec: number
}

export interface EditSectionHint {
  id: string
  name: string
  clipIds: string[]
}

export interface EditShortBin {
  id: string
  topic: string
  clipIds: string[]
  shortsOnly: boolean
}

export interface EditTimelineClip {
  id: string
  clipId: string
  path: string
  /** Trim start (seconds). Prefer inSec; `in` kept for older project files. */
  inSec: number
  outSec: number | null
  /** @deprecated use inSec */
  in?: number
  /** @deprecated use outSec */
  out?: number | null
  enabled: boolean
}

export interface EditOverlay {
  type: 'title' | 'subtitle' | 'lower_third' | 'cta'
  start: number
  end: number
  text: string
}

export interface EditSuccessHint {
  score: number
  why: string[]
}

export interface EditOutput {
  id: string
  kind: 'long' | 'short'
  aspect: '16:9' | '9:16'
  title?: string
  topic?: string
  source: 'proposed' | 'pinned'
  /** For pinned Shorts: which day-pool clips are reserved */
  clipIds: string[]
  shortsOnly?: boolean
  success?: EditSuccessHint
  proposalReasons: string[]
  timeline: {
    clips: EditTimelineClip[]
    overlays: EditOverlay[]
  }
  exportPath?: string | null
}

export interface EditProject {
  version: 1
  id: string
  name: string
  createdAt: string
  updatedAt: string
  projectPath: string
  clips: EditClip[]
  sectionHints: EditSectionHint[]
  shortBins: EditShortBin[]
  briefing: EditBriefing
  outputs: EditOutput[]
  status: 'draft' | 'proposed' | 'exported'
}

export interface EditProjectSummary {
  id: string
  name: string
  createdAt: string
  updatedAt: string
  projectPath: string
  clipCount: number
  longCount: number
  shortsCount: number
  status: EditProject['status']
}

export type EditExportQuality = 'draft' | 'good' | 'high'
export type EditExportResolution = '720' | '1080' | '1440'

export interface EditExportOptions {
  quality: EditExportQuality
  resolution: EditExportResolution
  burnTitle: boolean
  fps: 24 | 30 | 60
}

export const DEFAULT_EDIT_EXPORT_OPTIONS: EditExportOptions = {
  quality: 'good',
  resolution: '1080',
  burnTitle: true,
  fps: 30
}

export const DEFAULT_EDIT_BRIEFING: EditBriefing = {
  title: '',
  subtitle: '',
  cta: 'Subscribe for more',
  look: 'warm',
  musicMood: 'chill',
  texts: [],
  format: { longCount: 1, shortsCount: 5 },
  longTargetMin: 10,
  shortMaxSec: 60
}

export function createEmptyEditProject(
  id: string,
  name: string,
  projectPath: string
): EditProject {
  const now = new Date().toISOString()
  return {
    version: 1,
    id,
    name,
    createdAt: now,
    updatedAt: now,
    projectPath,
    clips: [],
    sectionHints: [],
    shortBins: [],
    briefing: { ...DEFAULT_EDIT_BRIEFING, texts: [] },
    outputs: [],
    status: 'draft'
  }
}

/** Normalize project JSON from disk/IPC so the Editor never crashes on missing fields. */
export function normalizeEditProject(raw: EditProject): EditProject {
  const briefing = {
    ...DEFAULT_EDIT_BRIEFING,
    ...(raw?.briefing || {}),
    format: {
      ...DEFAULT_EDIT_BRIEFING.format,
      ...(raw?.briefing?.format || {})
    },
    texts: Array.isArray(raw?.briefing?.texts) ? raw.briefing.texts : []
  }
  const outputs = Array.isArray(raw?.outputs)
    ? raw.outputs.map((o) => {
        const clips = Array.isArray(o?.timeline?.clips)
          ? o.timeline.clips.map((c) => {
              const inSec = Number(c.inSec ?? c.in ?? 0)
              const outRaw = c.outSec ?? c.out
              return {
                id: c.id || `tc-${Math.random().toString(36).slice(2, 8)}`,
                clipId: c.clipId,
                path: c.path,
                inSec: Number.isFinite(inSec) ? inSec : 0,
                outSec: outRaw == null ? null : Number(outRaw),
                enabled: c.enabled !== false
              }
            })
          : []
        return {
          ...o,
          id: o.id || 'output',
          kind: o.kind === 'short' ? 'short' : 'long',
          aspect: o.aspect === '9:16' ? '9:16' : '16:9',
          source: o.source === 'pinned' ? 'pinned' : 'proposed',
          clipIds: Array.isArray(o.clipIds) ? o.clipIds : [],
          proposalReasons: Array.isArray(o.proposalReasons) ? o.proposalReasons : [],
          success: o.success
            ? {
                score: Number(o.success.score) || 0,
                why: Array.isArray(o.success.why) ? o.success.why.map(String) : []
              }
            : undefined,
          timeline: {
            clips,
            overlays: Array.isArray(o?.timeline?.overlays) ? o.timeline.overlays : []
          },
          exportPath: o.exportPath ?? null
        } as EditOutput
      })
    : []
  return {
    version: 1,
    id: raw?.id || 'unknown',
    name: raw?.name || 'Untitled',
    createdAt: raw?.createdAt || new Date().toISOString(),
    updatedAt: raw?.updatedAt || new Date().toISOString(),
    projectPath: raw?.projectPath || '',
    clips: Array.isArray(raw?.clips) ? raw.clips : [],
    sectionHints: Array.isArray(raw?.sectionHints) ? raw.sectionHints : [],
    shortBins: Array.isArray(raw?.shortBins) ? raw.shortBins : [],
    briefing,
    outputs,
    status: raw?.status === 'proposed' || raw?.status === 'exported' ? raw.status : 'draft'
  }
}

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
  phase?: string | null
  phasePercent?: number | null
  clipIndex?: number | null
  clipTotal?: number | null
  clipName?: string | null
}

export type EditorProgressEvent = VoicesProgressEvent
