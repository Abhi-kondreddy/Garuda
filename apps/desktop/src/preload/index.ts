import { contextBridge, ipcRenderer } from 'electron'
import type {
  AnalysisReport,
  AppInfo,
  AppRoute,
  AppSettings,
  DataStats,
  PastReportSummary,
  ProgressEvent,
  ErrorEvent,
  SpeakersManifest,
  VoicesProject,
  RenderJob,
  VoicesProgressEvent
} from '../shared/types'

export interface GarudaApi {
  openVideoDialog: () => Promise<string | null>
  startAnalysis: (videoPath: string) => Promise<boolean>
  cancelAnalysis: () => Promise<boolean>
  loadReport: (reportPath: string) => Promise<AnalysisReport>
  listReports: () => Promise<PastReportSummary[]>
  openReportFolder: (reportPath: string) => Promise<void>
  deleteReport: (reportPath: string) => Promise<PastReportSummary[]>
  mediaUrl: (filePath: string) => Promise<string | null>
  getSettings: () => Promise<AppSettings>
  setSettings: (patch: Partial<AppSettings>) => Promise<AppSettings>
  getDataStats: () => Promise<DataStats>
  clearAllData: () => Promise<DataStats>
  openDataFolder: () => Promise<void>
  getAppInfo: () => Promise<AppInfo>
  voicesGetManifest: (reportPath: string) => Promise<SpeakersManifest | null>
  voicesGetProject: (reportPath: string) => Promise<VoicesProject | null>
  voicesSaveProject: (reportPath: string, project: VoicesProject) => Promise<VoicesProject>
  voicesSaveManifest: (reportPath: string, manifest: SpeakersManifest) => Promise<SpeakersManifest>
  voicesAnalyze: (reportPath: string) => Promise<boolean>
  voicesBuildPreview: (reportPath: string) => Promise<boolean>
  voicesSoloEnhance: (reportPath: string, speakerId: string) => Promise<string>
  voicesRender: (reportPath: string) => Promise<RenderJob>
  voicesCancel: () => Promise<boolean>
  voicesRevealExport: (outputPath: string) => Promise<void>
  voicesLatestExport: (reportPath: string) => Promise<string | null>
  onProgress: (cb: (evt: ProgressEvent) => void) => () => void
  onError: (cb: (evt: ErrorEvent) => void) => () => void
  onDone: (cb: (evt: { reportPath: string }) => void) => () => void
  onCancelled: (cb: () => void) => () => void
  onVoicesProgress: (cb: (evt: VoicesProgressEvent) => void) => () => void
  onVoicesDone: (cb: (evt: Record<string, unknown>) => void) => () => void
  onVoicesError: (cb: (evt: ErrorEvent) => void) => () => void
  onVoicesCancelled: (cb: () => void) => () => void
  onNavigate: (cb: (route: AppRoute) => void) => () => void
  onMenuAction: (cb: (action: string) => void) => () => void
}

const api: GarudaApi = {
  openVideoDialog: () => ipcRenderer.invoke('dialog:openVideo'),
  startAnalysis: (videoPath) => ipcRenderer.invoke('analysis:start', videoPath),
  cancelAnalysis: () => ipcRenderer.invoke('analysis:cancel'),
  loadReport: (reportPath) => ipcRenderer.invoke('report:load', reportPath),
  listReports: () => ipcRenderer.invoke('report:list'),
  openReportFolder: (reportPath) => ipcRenderer.invoke('report:openFolder', reportPath),
  deleteReport: (reportPath) => ipcRenderer.invoke('report:delete', reportPath),
  mediaUrl: (filePath) => ipcRenderer.invoke('media:url', filePath),
  getSettings: () => ipcRenderer.invoke('settings:get'),
  setSettings: (patch) => ipcRenderer.invoke('settings:set', patch),
  getDataStats: () => ipcRenderer.invoke('data:stats'),
  clearAllData: () => ipcRenderer.invoke('data:clearAll'),
  openDataFolder: () => ipcRenderer.invoke('data:openFolder'),
  getAppInfo: () => ipcRenderer.invoke('app:info'),
  voicesGetManifest: (reportPath) => ipcRenderer.invoke('voices:getManifest', reportPath),
  voicesGetProject: (reportPath) => ipcRenderer.invoke('voices:getProject', reportPath),
  voicesSaveProject: (reportPath, project) =>
    ipcRenderer.invoke('voices:saveProject', reportPath, project),
  voicesSaveManifest: (reportPath, manifest) =>
    ipcRenderer.invoke('voices:saveManifest', reportPath, manifest),
  voicesAnalyze: (reportPath) => ipcRenderer.invoke('voices:analyze', reportPath),
  voicesBuildPreview: (reportPath) => ipcRenderer.invoke('voices:buildPreview', reportPath),
  voicesSoloEnhance: (reportPath, speakerId) =>
    ipcRenderer.invoke('voices:soloEnhance', reportPath, speakerId),
  voicesRender: (reportPath) => ipcRenderer.invoke('voices:render', reportPath),
  voicesCancel: () => ipcRenderer.invoke('voices:cancel'),
  voicesRevealExport: (outputPath) => ipcRenderer.invoke('voices:revealExport', outputPath),
  voicesLatestExport: (reportPath) => ipcRenderer.invoke('voices:latestExport', reportPath),
  onProgress: (cb) => {
    const listener = (_: unknown, evt: ProgressEvent) => cb(evt)
    ipcRenderer.on('analysis:progress', listener)
    return () => ipcRenderer.removeListener('analysis:progress', listener)
  },
  onError: (cb) => {
    const listener = (_: unknown, evt: ErrorEvent) => cb(evt)
    ipcRenderer.on('analysis:error', listener)
    return () => ipcRenderer.removeListener('analysis:error', listener)
  },
  onDone: (cb) => {
    const listener = (_: unknown, evt: { reportPath: string }) => cb(evt)
    ipcRenderer.on('analysis:done', listener)
    return () => ipcRenderer.removeListener('analysis:done', listener)
  },
  onCancelled: (cb) => {
    const listener = () => cb()
    ipcRenderer.on('analysis:cancelled', listener)
    return () => ipcRenderer.removeListener('analysis:cancelled', listener)
  },
  onVoicesProgress: (cb) => {
    const listener = (_: unknown, evt: VoicesProgressEvent) => cb(evt)
    ipcRenderer.on('voices:progress', listener)
    return () => ipcRenderer.removeListener('voices:progress', listener)
  },
  onVoicesDone: (cb) => {
    const listener = (_: unknown, evt: Record<string, unknown>) => cb(evt)
    ipcRenderer.on('voices:done', listener)
    return () => ipcRenderer.removeListener('voices:done', listener)
  },
  onVoicesError: (cb) => {
    const listener = (_: unknown, evt: ErrorEvent) => cb(evt)
    ipcRenderer.on('voices:error', listener)
    return () => ipcRenderer.removeListener('voices:error', listener)
  },
  onVoicesCancelled: (cb) => {
    const listener = () => cb()
    ipcRenderer.on('voices:cancelled', listener)
    return () => ipcRenderer.removeListener('voices:cancelled', listener)
  },
  onNavigate: (cb) => {
    const listener = (_: unknown, route: AppRoute) => cb(route)
    ipcRenderer.on('app:navigate', listener)
    return () => ipcRenderer.removeListener('app:navigate', listener)
  },
  onMenuAction: (cb) => {
    const listener = (_: unknown, action: string) => cb(action)
    ipcRenderer.on('app:menu', listener)
    return () => ipcRenderer.removeListener('app:menu', listener)
  }
}

contextBridge.exposeInMainWorld('garuda', api)
