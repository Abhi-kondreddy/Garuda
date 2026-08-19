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
import { spawn, spawnSync, ChildProcessWithoutNullStreams } from 'child_process'
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
  TranscriptSegment,
  AnalyzerEvent,
  VoicesProject,
  SpeakersManifest,
  RenderJob,
  EditProject,
  EditProjectSummary,
  EditClip,
  EditExportOptions
} from '../shared/types'
import {
  DEFAULT_SETTINGS,
  createEmptyEditProject,
  normalizeEditProject,
  normalizeReport
} from '../shared/types'

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
let voicesChild: ChildProcessWithoutNullStreams | null = null
let editorChild: ChildProcessWithoutNullStreams | null = null

function killVoices(): void {
  if (!voicesChild) return
  const child = voicesChild
  ;(child as ChildProcessWithoutNullStreams & { __garudaKill?: boolean }).__garudaKill = true
  voicesChild = null
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

function killEditor(): void {
  if (!editorChild) return
  const child = editorChild
  ;(child as ChildProcessWithoutNullStreams & { __garudaKill?: boolean }).__garudaKill = true
  editorChild = null
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

function projectsRoot(): string {
  const root = join(app.getPath('userData'), 'garuda', 'projects')
  mkdirSync(root, { recursive: true })
  return root
}

function listEditProjects(): EditProjectSummary[] {
  const root = projectsRoot()
  const items: EditProjectSummary[] = []
  for (const name of readdirSync(root)) {
    const projectPath = join(root, name, 'project.json')
    if (!existsSync(projectPath)) continue
    try {
      const p = JSON.parse(readFileSync(projectPath, 'utf8')) as EditProject
      items.push({
        id: p.id,
        name: p.name,
        createdAt: p.createdAt,
        updatedAt: p.updatedAt,
        projectPath,
        clipCount: p.clips?.length ?? 0,
        longCount: p.briefing?.format?.longCount ?? 0,
        shortsCount: p.briefing?.format?.shortsCount ?? 0,
        status: p.status
      })
    } catch {
      /* skip corrupt */
    }
  }
  return items.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
}

function probeDuration(ffprobe: string, videoPath: string): number | null {
  try {
    const proc = spawnSync(
      ffprobe,
      ['-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', videoPath],
      { encoding: 'utf8' }
    )
    if (proc.status !== 0 || !proc.stdout) return null
    const data = JSON.parse(proc.stdout) as {
      format?: { duration?: string }
      streams?: Array<{ codec_type?: string; duration?: string }>
    }
    const fromFormat = Number(data.format?.duration)
    if (Number.isFinite(fromFormat) && fromFormat > 0) return fromFormat
    const vs = data.streams?.find((s) => s.codec_type === 'video')
    const fromStream = Number(vs?.duration)
    if (Number.isFinite(fromStream) && fromStream > 0) return fromStream
    return null
  } catch {
    return null
  }
}

function runEditorSync(args: string[]): { stdout: string; stderr: string; status: number | null } {
  const analysisDir = resolveAnalysisDir()
  const python = resolvePython()
  const proc = spawnSync(python, ['-u', '-m', 'garuda_analyze.editor', ...args], {
    cwd: analysisDir,
    encoding: 'utf8',
    env: editorPythonEnv(),
    maxBuffer: 20 * 1024 * 1024
  })
  return {
    stdout: proc.stdout || '',
    stderr: proc.stderr || '',
    status: proc.status
  }
}

function parseEditorDone(stdout: string): Record<string, unknown> | null {
  const lines = stdout
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
  for (let i = lines.length - 1; i >= 0; i--) {
    let evt: Record<string, unknown>
    try {
      evt = JSON.parse(lines[i]) as Record<string, unknown>
    } catch {
      continue
    }
    if (evt.type === 'error') {
      throw new Error(String(evt.detail || evt.message || 'Editor job failed'))
    }
    if (evt.type === 'done') return evt
  }
  return null
}

function spawnEditor(args: string[]): void {
  if (editorChild) {
    send('editor:error', { message: 'An editor job is already running.' })
    return
  }
  const { ffmpeg } = resolveFfmpeg()
  const fullArgs = ['-u', '-m', 'garuda_analyze.editor', ...args]
  if (!fullArgs.includes('--ffmpeg') && args[0] === 'export') {
    fullArgs.push('--ffmpeg', ffmpeg)
  }
  const child = spawn(resolvePython(), fullArgs, {
    cwd: resolveAnalysisDir(),
    env: editorPythonEnv()
  })
  editorChild = child
  let buf = ''
  let sawTerminal = false
  const flushLines = (chunk: string) => {
    buf += chunk
    const lines = buf.split('\n')
    buf = lines.pop() || ''
    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const evt = JSON.parse(line) as Record<string, unknown>
        if (evt.type === 'progress') send('editor:progress', evt)
        else if (evt.type === 'error') {
          sawTerminal = true
          send('editor:error', evt)
        } else if (evt.type === 'done') {
          sawTerminal = true
          send('editor:done', evt)
        }
      } catch {
        /* ignore non-JSON */
      }
    }
  }
  child.stdout.on('data', (chunk: Buffer) => flushLines(chunk.toString('utf8')))
  let errBuf = ''
  child.stderr.on('data', (chunk: Buffer) => {
    const text = chunk.toString('utf8')
    errBuf += text
    console.error('[garuda-editor]', text)
  })
  child.on('error', (err) => {
    editorChild = null
    send('editor:error', { message: 'Failed to start editor engine.', detail: err.message })
  })
  child.on('close', (code) => {
    if (buf.trim()) flushLines('\n')
    if (editorChild === child) editorChild = null
    const killed = (child as ChildProcessWithoutNullStreams & { __garudaKill?: boolean }).__garudaKill
    if (!killed && !sawTerminal && code !== 0) {
      const detail =
        errBuf.slice(-1500) ||
        `python=${resolvePython()} cwd=${resolveAnalysisDir()} (no stderr — often OOM on 4K; try Quick propose or shorter clips)`
      send('editor:error', {
        message: `Editor engine exited with code ${code ?? 'unknown'}.`,
        detail
      })
    }
  })
}

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
  killVoices()
  killEditor()
  const root = garudaRoot()
  rmSync(root, { recursive: true, force: true })
  mkdirSync(reportsRoot(), { recursive: true })
  mkdirSync(projectsRoot(), { recursive: true })
  writeSettings({ ...DEFAULT_SETTINGS })
  return dataStats()
}

function resolveRepoRoot(): string {
  // Prefer filesystem discovery so both electron-vite dev and packaged builds work.
  if (isDev) {
    const candidates = [
      join(__dirname, '..', '..', '..', '..'), // out/main -> Garuda
      join(__dirname, '..', '..', '..'), // out/main alternate
      join(app.getAppPath(), '..', '..'), // apps/desktop -> Garuda
      join(app.getAppPath(), '..', '..', '..'),
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

function editorPythonEnv(): NodeJS.ProcessEnv {
  const analysisDir = resolveAnalysisDir()
  const prev = process.env.PYTHONPATH || ''
  const parts = [analysisDir, prev].filter(Boolean)
  return {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    PYTHONPATH: parts.join(process.platform === 'win32' ? ';' : ':')
  }
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

function subtitleTimestamp(t: number, sep: string): string {
  const clamped = Math.max(0, t)
  const h = Math.floor(clamped / 3600)
  const m = Math.floor((clamped % 3600) / 60)
  const s = Math.floor(clamped % 60)
  let ms = Math.round((clamped - Math.floor(clamped)) * 1000)
  if (ms >= 1000) ms = 999
  const pad = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${pad(h)}:${pad(m)}:${pad(s)}${sep}${pad(ms, 3)}`
}

function buildSubtitles(transcript: TranscriptSegment[]): { srt: string; vtt: string } {
  let srt = ''
  let n = 1
  const vtt: string[] = ['WEBVTT', '']
  for (const seg of transcript) {
    const text = (seg.text || '').trim()
    if (!text) continue
    const start = seg.start || 0
    const end = seg.end || 0
    srt += `${n}\n${subtitleTimestamp(start, ',')} --> ${subtitleTimestamp(end, ',')}\n${text}\n\n`
    vtt.push(`${subtitleTimestamp(start, '.')} --> ${subtitleTimestamp(end, '.')}`, text, '')
    n += 1
  }
  return { srt, vtt: vtt.join('\n') }
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

function spawnVoices(args: string[], onDone?: (payload: Record<string, unknown>) => void): void {
  if (voicesChild) {
    send('voices:error', { message: 'A voices job is already running.' })
    return
  }
  const { ffmpeg } = resolveFfmpeg()
  const python = resolvePython()
  const analysisDir = resolveAnalysisDir()
  const fullArgs = ['-u', '-m', 'garuda_analyze.voices', ...args]
  if (!fullArgs.includes('--ffmpeg')) {
    fullArgs.push('--ffmpeg', ffmpeg)
  }
  const child = spawn(python, fullArgs, {
    cwd: analysisDir,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      PYTHONPATH: analysisDir
    }
  })
  voicesChild = child
  let buffer = ''
  let terminalSent = false
  child.stdout.on('data', (chunk: Buffer) => {
    buffer += chunk.toString('utf8')
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue
      try {
        const evt = JSON.parse(trimmed) as { type: string; [k: string]: unknown }
        if (evt.type === 'progress') send('voices:progress', evt)
        else if (evt.type === 'error') {
          terminalSent = true
          voicesChild = null
          send('voices:error', evt)
        } else if (evt.type === 'done') {
          terminalSent = true
          voicesChild = null
          send('voices:done', evt)
          onDone?.(evt)
        }
      } catch {
        /* ignore */
      }
    }
  })
  child.stderr.on('data', (chunk: Buffer) => {
    console.error('[garuda-voices]', chunk.toString('utf8'))
  })
  child.on('error', (err) => {
    voicesChild = null
    if (!terminalSent) {
      terminalSent = true
      send('voices:error', { message: 'Failed to start voices engine.', detail: err.message })
    }
  })
  child.on('close', (code) => {
    const intentional = Boolean(
      (child as ChildProcessWithoutNullStreams & { __garudaKill?: boolean }).__garudaKill
    )
    if (voicesChild === child) voicesChild = null
    if (intentional || terminalSent) return
    if (code !== 0) {
      send('voices:error', {
        message: 'Voices job failed.',
        detail: `Engine exited with code ${code}`
      })
    }
  })
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
          label: 'Editor',
          accelerator: 'CmdOrCtrl+4',
          click: () => send('app:navigate', 'editor')
        },
        {
          label: 'Report',
          accelerator: 'CmdOrCtrl+5',
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
    return normalizeReport(JSON.parse(raw) as AnalysisReport)
  })

  ipcMain.handle('report:list', () => listPastReports())

  ipcMain.handle('report:openFolder', (_e, reportPath: string) => {
    shell.showItemInFolder(reportPath)
  })

  ipcMain.handle('report:exportCaptions', (_e, reportPath: string) => {
    if (!reportPath || !existsSync(reportPath)) return null
    let report: AnalysisReport
    try {
      report = JSON.parse(readFileSync(reportPath, 'utf8')) as AnalysisReport
    } catch {
      return null
    }
    const segments = report.transcript || []
    if (!segments.length) return null
    const { srt, vtt } = buildSubtitles(segments)
    const dir = dirname(reportPath)
    const srtPath = join(dir, 'captions.srt')
    const vttPath = join(dir, 'captions.vtt')
    writeFileSync(srtPath, srt, 'utf8')
    writeFileSync(vttPath, vtt, 'utf8')
    shell.showItemInFolder(srtPath)
    return { srt: srtPath, vtt: vttPath }
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

  ipcMain.handle('voices:getManifest', (_e, reportPath: string) => {
    const dir = dirname(reportPath)
    const p = join(dir, 'voices', 'speakers.json')
    if (!existsSync(p)) return null
    return JSON.parse(readFileSync(p, 'utf8')) as SpeakersManifest
  })

  ipcMain.handle('voices:getProject', (_e, reportPath: string) => {
    const dir = dirname(reportPath)
    const p = join(dir, 'voices', 'project.json')
    if (!existsSync(p)) return null
    return JSON.parse(readFileSync(p, 'utf8')) as VoicesProject
  })

  ipcMain.handle('voices:saveProject', (_e, reportPath: string, project: VoicesProject) => {
    const dir = dirname(reportPath)
    const p = join(dir, 'voices', 'project.json')
    mkdirSync(dirname(p), { recursive: true })
    writeFileSync(p, JSON.stringify(project, null, 2), 'utf8')
    return project
  })

  ipcMain.handle('voices:saveManifest', (_e, reportPath: string, manifest: SpeakersManifest) => {
    const dir = dirname(reportPath)
    const p = join(dir, 'voices', 'speakers.json')
    mkdirSync(dirname(p), { recursive: true })
    writeFileSync(p, JSON.stringify(manifest, null, 2), 'utf8')
    return manifest
  })

  ipcMain.handle('voices:latestExport', (_e, reportPath: string) => {
    const dir = join(dirname(reportPath), 'exports')
    if (!existsSync(dir)) return null
    const jobs = readdirSync(dir)
      .map((name) => {
        const outputPath = join(dir, name, 'output.mp4')
        if (!existsSync(outputPath)) return null
        try {
          return { outputPath, mtime: statSync(outputPath).mtimeMs }
        } catch {
          return null
        }
      })
      .filter((x): x is { outputPath: string; mtime: number } => Boolean(x))
      .sort((a, b) => b.mtime - a.mtime)
    return jobs[0]?.outputPath ?? null
  })

  ipcMain.handle('voices:analyze', (_e, reportPath: string) => {
    const settings = readSettings()
    const dir = dirname(reportPath)
    const args = ['analyze', '--report-dir', dir]
    if (settings.huggingfaceToken) {
      args.push('--hf-token', settings.huggingfaceToken)
    }
    if (settings.downloadVoiceModels !== false) {
      args.push('--allow-download')
    }
    spawnVoices(args)
    return true
  })

  ipcMain.handle('voices:buildPreview', (_e, reportPath: string) => {
    const dir = dirname(reportPath)
    const projectFile = join(dir, 'voices', 'project.json')
    spawnVoices(['preview', '--report-dir', dir, '--project', projectFile])
    return true
  })

  ipcMain.handle('voices:soloEnhance', (_e, reportPath: string, speakerId: string) => {
    const dir = dirname(reportPath)
    const projectFile = join(dir, 'voices', 'project.json')
    const out = join(dir, 'voices', 'stems', '.cache', `solo_${speakerId}.wav`)
    spawnVoices([
      'solo-enhance',
      '--report-dir',
      dir,
      '--speaker-id',
      speakerId,
      '--project',
      projectFile,
      '--out',
      out
    ])
    return out
  })

  ipcMain.handle('voices:render', (_e, reportPath: string) => {
    const dir = dirname(reportPath)
    const report = JSON.parse(readFileSync(reportPath, 'utf8')) as AnalysisReport
    const jobId = `export-${Date.now()}`
    const exportDir = join(dir, 'exports', jobId)
    mkdirSync(exportDir, { recursive: true })
    const projectFile = join(dir, 'voices', 'project.json')
    const outputPath = join(exportDir, 'output.mp4')
    const job: RenderJob = {
      id: jobId,
      reportId: basename(dir),
      status: 'queued',
      progress: 0,
      outputPath,
      ops: [
        { type: 'audioRemix', projectPath: projectFile },
        {
          type: 'muxVideo',
          videoPath: report.sourcePath,
          audioPath: join(dir, 'voices', 'preview_mix.wav')
        }
      ]
    }
    const jobPath = join(exportDir, 'job.json')
    writeFileSync(jobPath, JSON.stringify(job, null, 2), 'utf8')
    spawnVoices(['render', '--job', jobPath])
    return job
  })

  ipcMain.handle('voices:cancel', () => {
    killVoices()
    send('voices:cancelled', {})
    return true
  })

  ipcMain.handle('voices:revealExport', (_e, outputPath: string) => {
    if (outputPath && existsSync(outputPath)) shell.showItemInFolder(outputPath)
  })

  ipcMain.handle('editor:list', () => listEditProjects())

  ipcMain.handle('editor:create', (_e, name?: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const dir = join(projectsRoot(), id)
    mkdirSync(dir, { recursive: true })
    mkdirSync(join(dir, 'exports'), { recursive: true })
    const projectPath = join(dir, 'project.json')
    const project = createEmptyEditProject(id, name?.trim() || `Day edit ${new Date().toLocaleDateString()}`, projectPath)
    writeFileSync(projectPath, JSON.stringify(project, null, 2), 'utf8')
    return project
  })

  ipcMain.handle('editor:load', (_e, projectPath: string) => {
    if (!existsSync(projectPath)) throw new Error('Project not found')
    return normalizeEditProject(JSON.parse(readFileSync(projectPath, 'utf8')) as EditProject)
  })

  ipcMain.handle('editor:save', (_e, project: EditProject) => {
    const next = normalizeEditProject({ ...project, updatedAt: new Date().toISOString() })
    writeFileSync(project.projectPath, JSON.stringify(next, null, 2), 'utf8')
    return next
  })

  ipcMain.handle('editor:delete', (_e, projectPath: string) => {
    const dir = dirname(projectPath)
    if (dir.startsWith(projectsRoot())) {
      rmSync(dir, { recursive: true, force: true })
    }
    return listEditProjects()
  })

  ipcMain.handle('editor:openVideos', async () => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      title: 'Add clips to edit project',
      properties: ['openFile', 'multiSelections'],
      filters: [
        {
          name: 'Videos',
          extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi', 'm4v']
        }
      ]
    })
    if (result.canceled || !result.filePaths.length) return [] as EditClip[]
    const { ffprobe } = resolveFfmpeg()
    return result.filePaths.map((filePath) => {
      let mtimeMs: number | undefined
      try {
        mtimeMs = statSync(filePath).mtimeMs
      } catch {
        mtimeMs = undefined
      }
      const clip: EditClip = {
        id: `clip-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        path: filePath,
        name: basename(filePath),
        durationSec: probeDuration(ffprobe, filePath),
        mtimeMs
      }
      return clip
    })
  })

  ipcMain.handle('editor:propose', (_e, projectPath: string, opts?: { quick?: boolean }) => {
    if (!projectPath || !existsSync(projectPath)) {
      throw new Error('Project file not found. Save the project and try again.')
    }
    const { ffmpeg, ffprobe } = resolveFfmpeg()
    const settings = readSettings()
    const args = [
      'propose',
      '--project',
      projectPath,
      '--ffmpeg',
      ffmpeg,
      '--ffprobe',
      ffprobe,
      '--whisper-model',
      settings.whisperModel || 'tiny',
      // Visual+audio read by default; ASR is heavy and often crashes first-run without models.
      '--skip-asr'
    ]
    if (opts?.quick) args.push('--quick')
    send('editor:progress', {
      type: 'progress',
      stage: 'propose',
      percent: 1,
      message: opts?.quick
        ? 'Quick propose…'
        : `Starting deep read (python=${resolvePython()})…`
    })
    spawnEditor(args)
    return true
  })

  ipcMain.handle(
    'editor:export',
    (_e, projectPath: string, outputId: string, options?: Partial<EditExportOptions>) => {
      const dir = dirname(projectPath)
      const out = join(dir, 'exports', `${outputId}.mp4`)
      const quality = options?.quality || 'good'
      const resolution = options?.resolution || '1080'
      const burnTitle = options?.burnTitle !== false
      const fps = options?.fps || 30
      spawnEditor([
        'export',
        '--project',
        projectPath,
        '--output-id',
        outputId,
        '--out',
        out,
        '--quality',
        quality,
        '--resolution',
        String(resolution),
        '--burn-title',
        burnTitle ? '1' : '0',
        '--fps',
        String(fps)
      ])
      return out
    }
  )

  ipcMain.handle('editor:cancel', () => {
    killEditor()
    send('editor:cancelled', {})
    return true
  })

  ipcMain.handle('editor:revealExport', (_e, outputPath: string) => {
    if (outputPath && existsSync(outputPath)) shell.showItemInFolder(outputPath)
  })

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  killAnalysis()
  killVoices()
  killEditor()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  killAnalysis()
  killVoices()
  killEditor()
})