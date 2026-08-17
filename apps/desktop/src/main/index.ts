import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  shell,
  protocol,
  Menu
} from 'electron'
import { join, dirname, basename } from 'path'
import { spawn, ChildProcessWithoutNullStreams } from 'child_process'
import {
  createReadStream,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync
} from 'fs'
import { Readable } from 'stream'
import type {
  AnalysisReport,
  AppInfo,
  AppSettings,
  DataStats,
  PastReportSummary,
  AnalyzerEvent
} from '../shared/types'
import { DEFAULT_SETTINGS } from '../shared/types'

// Must be before app ready — allows <video> to stream local files.
protocol.registerSchemesAsPrivileged([
  {
    scheme: 'garuda',
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      stream: true,
      bypassCSP: true,
      corsEnabled: true
    }
  }
])

const isDev = !app.isPackaged

let mainWindow: BrowserWindow | null = null
let analysisChild: ChildProcessWithoutNullStreams | null = null

function reportsRoot(): string {
  const root = join(app.getPath('userData'), 'garuda', 'reports')
  mkdirSync(root, { recursive: true })
  return root
}

function garudaRoot(): string {
  const root = join(app.getPath('userData'), 'garuda')
  mkdirSync(root, { recursive: true })
  return root
}

function settingsPath(): string {
  return join(garudaRoot(), 'settings.json')
}

function readSettings(): AppSettings {
  try {
    const raw = readFileSync(settingsPath(), 'utf8')
    return { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<AppSettings>) }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

function writeSettings(next: AppSettings): AppSettings {
  writeFileSync(settingsPath(), JSON.stringify(next, null, 2), 'utf8')
  return next
}

function dirBytes(path: string): number {
  if (!existsSync(path)) return 0
  let total = 0
  const walk = (p: string) => {
    const st = statSync(p)
    if (st.isFile()) {
      total += st.size
      return
    }
    if (st.isDirectory()) {
      for (const name of readdirSync(p)) walk(join(p, name))
    }
  }
  try {
    walk(path)
  } catch {
    /* ignore */
  }
  return total
}

function dataStats(): DataStats {
  const path = garudaRoot()
  return {
    path,
    reportCount: listPastReports().length,
    bytes: dirBytes(path)
  }
}

function clearAllData(): DataStats {
  killAnalysis()
  const root = garudaRoot()
  rmSync(root, { recursive: true, force: true })
  mkdirSync(reportsRoot(), { recursive: true })
  writeSettings({ ...DEFAULT_SETTINGS })
  return dataStats()
}

function resolveRepoRoot(): string {
  // Prefer filesystem discovery so both electron-vite dev and packaged builds work.
  if (isDev) {
    const candidates = [
      join(__dirname, '..', '..', '..', '..'), // out/main -> Garuda
      join(app.getAppPath(), '..', '..'), // apps/desktop -> Garuda
      join(process.cwd(), '..', '..'),
      process.cwd()
    ]
    for (const c of candidates) {
      if (existsSync(join(c, 'packages', 'analysis', 'garuda_analyze'))) {
        return c
      }
    }
    return candidates[0]
  }
  return process.resourcesPath
}

function resolvePython(): string {
  const venv = join(resolveRepoRoot(), 'packages', 'analysis', '.venv', 'bin', 'python')
  if (existsSync(venv)) return venv
  const venvWin = join(resolveRepoRoot(), 'packages', 'analysis', '.venv', 'Scripts', 'python.exe')
  if (existsSync(venvWin)) return venvWin
  return process.platform === 'win32' ? 'python' : 'python3'
}

function resolveAnalysisDir(): string {
  if (isDev) {
    return join(resolveRepoRoot(), 'packages', 'analysis')
  }
  return join(process.resourcesPath, 'analysis')
}

function resolveFfmpeg(): { ffmpeg: string; ffprobe: string } {
  const tools = isDev
    ? join(resolveRepoRoot(), 'tools', 'ffmpeg')
    : join(process.resourcesPath, 'ffmpeg')
  const ffmpeg = join(tools, process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg')
  const ffprobe = join(tools, process.platform === 'win32' ? 'ffprobe.exe' : 'ffprobe')
  return {
    ffmpeg: existsSync(ffmpeg) ? ffmpeg : 'ffmpeg',
    ffprobe: existsSync(ffprobe) ? ffprobe : 'ffprobe'
  }
}

function mediaContentType(filePath: string): string {
  const lower = filePath.toLowerCase()
  if (lower.endsWith('.webm')) return 'video/webm'
  if (lower.endsWith('.mkv')) return 'video/x-matroska'
  if (lower.endsWith('.mov')) return 'video/quicktime'
  if (lower.endsWith('.avi')) return 'video/x-msvideo'
  if (lower.endsWith('.m4v')) return 'video/x-m4v'
  if (lower.endsWith('.wav')) return 'audio/wav'
  return 'video/mp4'
}

/** Serve local media with HTTP Range support so <video> can scrub. */
function serveLocalMedia(request: Request, filePath: string): Response {
  const stats = statSync(filePath)
  const size = stats.size
  const contentType = mediaContentType(filePath)
  const rangeHeader = request.headers.get('range') || request.headers.get('Range')

  const headersBase: Record<string, string> = {
    'Content-Type': contentType,
    'Accept-Ranges': 'bytes',
    'Cache-Control': 'no-cache'
  }

  if (!rangeHeader) {
    const stream = createReadStream(filePath)
    return new Response(Readable.toWeb(stream) as ReadableStream, {
      status: 200,
      headers: {
        ...headersBase,
        'Content-Length': String(size)
      }
    })
  }

  const match = /bytes=(\d*)-(\d*)/.exec(rangeHeader)
  if (!match) {
    return new Response('Invalid range', { status: 416 })
  }

  let start = match[1] ? Number.parseInt(match[1], 10) : 0
  let end = match[2] ? Number.parseInt(match[2], 10) : size - 1
  if (!Number.isFinite(start) || start < 0) start = 0
  if (!Number.isFinite(end) || end >= size) end = size - 1
  if (start > end || start >= size) {
    return new Response('Range not satisfiable', {
      status: 416,
      headers: { 'Content-Range': `bytes */${size}` }
    })
  }

  const chunkSize = end - start + 1
  const stream = createReadStream(filePath, { start, end })
  return new Response(Readable.toWeb(stream) as ReadableStream, {
    status: 206,
    headers: {
      ...headersBase,
      'Content-Length': String(chunkSize),
      'Content-Range': `bytes ${start}-${end}/${size}`
    }
  })
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 1024,
    minHeight: 700,
    title: 'Garuda',
    backgroundColor: '#010104',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  })

  if (isDev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

function send(channel: string, payload: unknown): void {
  mainWindow?.webContents.send(channel, payload)
}

function killAnalysis(): void {
  if (!analysisChild) return
  const child = analysisChild
  analysisChild = null
  try {
    child.kill('SIGTERM')
    setTimeout(() => {
      try {
        child.kill('SIGKILL')
      } catch {
        /* ignore */
      }
    }, 1500)
  } catch {
    /* ignore */
  }
}

function listPastReports(): PastReportSummary[] {
  const root = reportsRoot()
  const dirs = readdirSync(root, { withFileTypes: true }).filter((d) => d.isDirectory())
  const out: PastReportSummary[] = []
  for (const d of dirs) {
    const reportPath = join(root, d.name, 'report.json')
    if (!existsSync(reportPath)) continue
    try {
      const report = JSON.parse(readFileSync(reportPath, 'utf8')) as AnalysisReport
      out.push({
        id: d.name,
        sourceName: report.sourceName,
        createdAt: report.createdAt,
        overall: report.scores.overall,
        reportPath
      })
    } catch {
      /* skip corrupt */
    }
  }
  return out.sort((a, b) => b.createdAt.localeCompare(a.createdAt))
}

function startAnalysis(videoPath: string): void {
  if (analysisChild) {
    send('analysis:error', { message: 'An analysis is already running.' })
    return
  }
  if (!existsSync(videoPath)) {
    send('analysis:error', { message: 'Video file not found.', detail: videoPath })
    return
  }

  const settings = readSettings()
  const id = `${Date.now()}-${basename(videoPath).replace(/[^\w.-]+/g, '_').slice(0, 40)}`
  const outDir = join(reportsRoot(), id)
  mkdirSync(outDir, { recursive: true })

  const { ffmpeg, ffprobe } = resolveFfmpeg()
  const python = resolvePython()
  const analysisDir = resolveAnalysisDir()

  const args = [
    '-u',
    '-m',
    'garuda_analyze',
    '--path',
    videoPath,
    '--out',
    outDir,
    '--ffmpeg',
    ffmpeg,
    '--ffprobe',
    ffprobe,
    '--whisper-model',
    settings.whisperModel
  ]

  const child = spawn(python, args, {
    cwd: analysisDir,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      PYTHONPATH: analysisDir
    }
  })
  analysisChild = child

  let buffer = ''
  child.stdout.on('data', (chunk: Buffer) => {
    buffer += chunk.toString('utf8')
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue
      try {
        const evt = JSON.parse(trimmed) as AnalyzerEvent
        if (evt.type === 'progress') {
          send('analysis:progress', evt)
        } else if (evt.type === 'error') {
          send('analysis:error', evt)
        } else if (evt.type === 'done') {
          send('analysis:done', { reportPath: evt.reportPath || join(outDir, 'report.json') })
        }
      } catch {
        // non-JSON log line — ignore for IPC
      }
    }
  })

  child.stderr.on('data', (chunk: Buffer) => {
    const text = chunk.toString('utf8')
    console.error('[garuda-analyze]', text)
  })

  child.on('error', (err) => {
    analysisChild = null
    send('analysis:error', {
      message: 'Failed to start analysis engine.',
      detail: err.message
    })
  })

  child.on('close', (code) => {
    const wasRunning = analysisChild === child
    analysisChild = null
    if (!wasRunning) return
    if (code !== 0) {
      send('analysis:error', {
        message: 'Analysis failed.',
        detail: `Engine exited with code ${code}`
      })
    }
  })
}

function buildAppMenu(): void {
  const isMac = process.platform === 'darwin'
  const template: Electron.MenuItemConstructorOptions[] = [
    ...(isMac
      ? [
          {
            label: app.name,
            submenu: [
              { role: 'about' as const },
              { type: 'separator' as const },
              {
                label: 'Settings…',
                accelerator: 'CmdOrCtrl+,',
                click: () => send('app:navigate', 'settings')
              },
              { type: 'separator' as const },
              { role: 'services' as const },
              { type: 'separator' as const },
              { role: 'hide' as const },
              { role: 'hideOthers' as const },
              { role: 'unhide' as const },
              { type: 'separator' as const },
              { role: 'quit' as const }
            ]
          }
        ]
      : []),
    {
      label: 'File',
      submenu: [
        {
          label: 'Open Video…',
          accelerator: 'CmdOrCtrl+O',
          click: () => send('app:menu', 'open-video')
        },
        {
          label: 'Reveal Data Folder',
          click: () => {
            shell.openPath(garudaRoot())
          }
        },
        { type: 'separator' },
        isMac ? { role: 'close' } : { role: 'quit' }
      ]
    },
    {
      label: 'View',
      submenu: [
        {
          label: 'Analyze',
          accelerator: 'CmdOrCtrl+1',
          click: () => send('app:navigate', 'analyze')
        },
        {
          label: 'Library',
          accelerator: 'CmdOrCtrl+2',
          click: () => send('app:navigate', 'library')
        },
        {
          label: 'Report',
          accelerator: 'CmdOrCtrl+3',
          click: () => send('app:navigate', 'report')
        },
        {
          label: 'Settings',
          accelerator: isMac ? undefined : 'CmdOrCtrl+,',
          click: () => send('app:navigate', 'settings')
        },
        { type: 'separator' },
        { role: 'reload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'togglefullscreen' }
      ]
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'About Garuda Storage',
          click: () => send('app:menu', 'about-storage')
        }
      ]
    }
  ]

  if (!isMac) {
    template.unshift({
      label: 'Garuda',
      submenu: [
        {
          label: 'Settings…',
          accelerator: 'CmdOrCtrl+,',
          click: () => send('app:navigate', 'settings')
        },
        { type: 'separator' },
        { role: 'quit' }
      ]
    })
  }

  Menu.setApplicationMenu(Menu.buildFromTemplate(template))
}

app.whenReady().then(() => {
  protocol.handle('garuda', (request) => {
    try {
      const parsed = new URL(request.url)
      const filePath = parsed.searchParams.get('path')
      if (!filePath || !existsSync(filePath)) {
        return new Response('Not found', { status: 404 })
      }
      return serveLocalMedia(request, filePath)
    } catch (err) {
      console.error('[garuda-media]', err)
      return new Response('Bad request', { status: 400 })
    }
  })

  createWindow()
  buildAppMenu()

  ipcMain.handle('dialog:openVideo', async () => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      title: 'Choose a video for Garuda',
      properties: ['openFile'],
      filters: [
        {
          name: 'Videos',
          extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi', 'm4v']
        }
      ]
    })
    if (result.canceled || !result.filePaths[0]) return null
    return result.filePaths[0]
  })

  ipcMain.handle('analysis:start', (_e, videoPath: string) => {
    startAnalysis(videoPath)
    return true
  })

  ipcMain.handle('analysis:cancel', () => {
    killAnalysis()
    send('analysis:cancelled', {})
    return true
  })

  ipcMain.handle('report:load', (_e, reportPath: string) => {
    const raw = readFileSync(reportPath, 'utf8')
    return JSON.parse(raw) as AnalysisReport
  })

  ipcMain.handle('report:list', () => listPastReports())

  ipcMain.handle('report:openFolder', (_e, reportPath: string) => {
    shell.showItemInFolder(reportPath)
  })

  ipcMain.handle('report:delete', (_e, reportPath: string) => {
    const dir = dirname(reportPath)
    if (dir.startsWith(reportsRoot())) {
      rmSync(dir, { recursive: true, force: true })
    }
    return listPastReports()
  })

  ipcMain.handle('media:url', (_e, filePath: string) => {
    if (!filePath || !existsSync(filePath)) return null
    return `garuda://local/?path=${encodeURIComponent(filePath)}`
  })

  ipcMain.handle('settings:get', () => readSettings())

  ipcMain.handle('settings:set', (_e, patch: Partial<AppSettings>) => {
    const next = { ...readSettings(), ...patch }
    if (!['tiny', 'base', 'small'].includes(next.whisperModel)) {
      next.whisperModel = DEFAULT_SETTINGS.whisperModel
    }
    next.recentLimit = Math.min(24, Math.max(3, Number(next.recentLimit) || 8))
    return writeSettings(next)
  })

  ipcMain.handle('data:stats', () => dataStats())

  ipcMain.handle('data:clearAll', () => clearAllData())

  ipcMain.handle('data:openFolder', async () => {
    await shell.openPath(garudaRoot())
  })

  ipcMain.handle('app:info', (): AppInfo => ({
    version: app.getVersion(),
    name: app.getName(),
    platform: process.platform
  }))

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  killAnalysis()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  killAnalysis()
})
