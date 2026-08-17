import { contextBridge, ipcRenderer } from 'electron'
import type {
  AnalysisReport,
  AppInfo,
  AppRoute,
  AppSettings,
  DataStats,
  PastReportSummary,
  ProgressEvent,
  ErrorEvent
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
  onProgress: (cb: (evt: ProgressEvent) => void) => () => void
  onError: (cb: (evt: ErrorEvent) => void) => () => void
  onDone: (cb: (evt: { reportPath: string }) => void) => () => void
  onCancelled: (cb: () => void) => () => void
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
