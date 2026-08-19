import os from 'os'
import { spawnSync } from 'child_process'

export type ResourcePressure = 'ok' | 'moderate' | 'high' | 'critical'

export interface SystemHardwareInfo {
  chip: string
  physicalCores: number
  logicalCores: number
  totalRamBytes: number
  gpu: string
  platform: string
}

export interface SystemProcessUsage {
  pid: number
  name: string
  cpuPercent: number
  memoryPercent: number
}

export interface SystemResourceSnapshot {
  at: string
  cpuPercent: number
  loadAvg1: number
  loadPerCore: number
  memoryUsedBytes: number
  memoryFreeBytes: number
  memoryUsedPercent: number
  pressure: ResourcePressure
  thermalWarning: boolean
  onBattery: boolean
  batteryPercent: number | null
  garudaProcesses: SystemProcessUsage[]
  garudaCpuPercent: number
  advice: string[]
}

let cachedHardware: SystemHardwareInfo | null = null

function readSysctl(key: string): string {
  try {
    return spawnSync('sysctl', ['-n', key], { encoding: 'utf8' }).stdout.trim()
  } catch {
    return ''
  }
}

function shortenCommand(cmd: string): string {
  if (cmd.includes('garuda_analyze.editor')) return 'Editor engine'
  if (cmd.includes('garuda_analyze')) return 'Analysis engine'
  if (cmd.includes('ffmpeg') && cmd.includes('garuda')) return 'FFmpeg'
  if (cmd.includes('Electron Helper (GPU)')) return 'Garuda GPU'
  if (cmd.includes('Electron Helper (Renderer)')) return 'Garuda UI'
  if (cmd.includes('Electron.app') && cmd.includes('Garuda')) return 'Garuda'
  const base = cmd.split(/[/\\]/).pop() ?? cmd
  return base.length > 42 ? `${base.slice(0, 39)}…` : base
}

function sampleCpuTimes(): { idle: number; total: number } {
  let idle = 0
  let total = 0
  for (const cpu of os.cpus()) {
    const t = cpu.times
    idle += t.idle
    total += t.user + t.nice + t.sys + t.idle + t.irq
  }
  return { idle, total }
}

function readPowerState(): { onBattery: boolean; batteryPercent: number | null } {
  if (process.platform !== 'darwin') {
    return { onBattery: false, batteryPercent: null }
  }
  try {
    const out = spawnSync('pmset', ['-g', 'batt'], { encoding: 'utf8' }).stdout
    const onBattery = /Battery Power|discharging/i.test(out)
    const m = out.match(/(\d+)%/)
    return { onBattery, batteryPercent: m ? Number(m[1]) : null }
  } catch {
    return { onBattery: false, batteryPercent: null }
  }
}

function readThermalWarning(): boolean {
  if (process.platform !== 'darwin') return false
  try {
    const out = spawnSync('pmset', ['-g', 'therm'], { encoding: 'utf8' }).stdout
    return /warning level has been recorded/i.test(out) && !/No thermal warning/i.test(out)
  } catch {
    return false
  }
}

function listGarudaProcesses(activePids: number[]): SystemProcessUsage[] {
  const active = new Set(activePids.filter((p) => p > 0))
  try {
    const out = spawnSync('ps', ['-A', '-o', 'pid=,pcpu=,pmem=,command='], { encoding: 'utf8' }).stdout
    const rows: SystemProcessUsage[] = []
    for (const line of out.split('\n')) {
      const m = line.trim().match(/^(\d+)\s+([\d.]+)\s+([\d.]+)\s+(.+)$/)
      if (!m) continue
      const pid = Number(m[1])
      const cmd = m[4]
      const garuda =
        active.has(pid) ||
        /garuda_analyze|garuda-desktop|garuda\/tools\/ffmpeg/.test(cmd) ||
        (cmd.includes('Electron') && /Garuda|garuda-desktop/.test(cmd))
      if (!garuda) continue
      rows.push({
        pid,
        name: shortenCommand(cmd),
        cpuPercent: Number(m[2]) || 0,
        memoryPercent: Number(m[3]) || 0
      })
    }
    return rows.sort((a, b) => b.cpuPercent - a.cpuPercent).slice(0, 6)
  } catch {
    return []
  }
}

function computePressure(cpu: number, memPct: number, loadPerCore: number): ResourcePressure {
  let score = 0
  if (memPct >= 92) score += 3
  else if (memPct >= 85) score += 2
  else if (memPct >= 75) score += 1
  if (cpu >= 90) score += 2
  else if (cpu >= 70) score += 1
  if (loadPerCore >= 1.5) score += 2
  else if (loadPerCore >= 1.0) score += 1
  if (score >= 4) return 'critical'
  if (score >= 2) return 'high'
  if (score >= 1) return 'moderate'
  return 'ok'
}

function buildAdvice(
  pressure: ResourcePressure,
  onBattery: boolean,
  memPct: number,
  garudaCpu: number
): string[] {
  const tips: string[] = []
  if (pressure === 'critical' || pressure === 'high') {
    tips.push('System is under heavy load — consider pausing other apps.')
  }
  if (memPct >= 85) {
    tips.push('RAM is nearly full — close browser tabs or other heavy apps.')
  }
  if (onBattery && garudaCpu > 50) {
    tips.push('On battery — plug in for faster analysis and less throttling.')
  }
  if (pressure === 'ok' && tips.length === 0) {
    tips.push('Resources look healthy for local analysis.')
  }
  return tips.slice(0, 3)
}

export function getSystemHardware(): SystemHardwareInfo {
  if (cachedHardware) return cachedHardware
  const logicalCores = os.cpus().length
  let chip = os.cpus()[0]?.model ?? 'Unknown CPU'
  let physicalCores = logicalCores
  let gpu = 'Integrated GPU'

  if (process.platform === 'darwin') {
    chip = readSysctl('machdep.cpu.brand_string') || chip
    physicalCores = Number(readSysctl('hw.physicalcpu')) || logicalCores
    const gpuOut = spawnSync('system_profiler', ['SPDisplaysDataType'], { encoding: 'utf8' }).stdout
    const m = gpuOut.match(/Chipset Model:\s*(.+)/)
    if (m) gpu = m[1].trim()
  }

  cachedHardware = {
    chip,
    physicalCores,
    logicalCores,
    totalRamBytes: os.totalmem(),
    gpu,
    platform: process.platform
  }
  return cachedHardware
}

export async function getSystemResources(activePids: number[] = []): Promise<SystemResourceSnapshot> {
  const sample1 = sampleCpuTimes()
  await new Promise((r) => setTimeout(r, 280))
  const sample2 = sampleCpuTimes()

  const idleDelta = sample2.idle - sample1.idle
  const totalDelta = sample2.total - sample1.total
  const cpuPercent =
    totalDelta > 0 ? Math.max(0, Math.min(100, Math.round(100 * (1 - idleDelta / totalDelta)))) : 0

  const totalRam = os.totalmem()
  const freeRam = os.freemem()
  const usedRam = totalRam - freeRam
  const memoryUsedPercent = Math.round((usedRam / totalRam) * 100)
  const loadAvg1 = os.loadavg()[0] ?? 0
  const cores = Math.max(1, os.cpus().length)
  const loadPerCore = loadAvg1 / cores
  const pressure = computePressure(cpuPercent, memoryUsedPercent, loadPerCore)
  const { onBattery, batteryPercent } = readPowerState()
  const thermalWarning = readThermalWarning()
  const garudaProcesses = listGarudaProcesses(activePids)
  const garudaCpuPercent = Math.round(
    garudaProcesses.reduce((sum, p) => sum + p.cpuPercent, 0)
  )
  const advice = buildAdvice(pressure, onBattery, memoryUsedPercent, garudaCpuPercent)

  return {
    at: new Date().toISOString(),
    cpuPercent,
    loadAvg1: Math.round(loadAvg1 * 100) / 100,
    loadPerCore: Math.round(loadPerCore * 100) / 100,
    memoryUsedBytes: usedRam,
    memoryFreeBytes: freeRam,
    memoryUsedPercent,
    pressure,
    thermalWarning,
    onBattery,
    batteryPercent,
    garudaProcesses,
    garudaCpuPercent,
    advice
  }
}
