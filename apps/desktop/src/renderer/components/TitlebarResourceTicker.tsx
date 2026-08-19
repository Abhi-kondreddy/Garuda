import { useEffect, useState } from 'react'
import type { ResourcePressure, SystemResourceSnapshot } from '../../shared/types'
import './TitlebarResourceTicker.css'

function pressureClass(p: ResourcePressure): string {
  return `ticker-pressure-${p}`
}

export default function TitlebarResourceTicker({ enabled = true }: { enabled?: boolean }) {
  const [live, setLive] = useState<SystemResourceSnapshot | null>(null)

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    const tick = async () => {
      try {
        const snap = await window.garuda.getSystemResources()
        if (!cancelled) setLive(snap)
      } catch {
        /* ignore */
      }
    }
    void tick()
    const id = window.setInterval(() => void tick(), 2500)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [enabled])

  if (!live) return null

  return (
    <span className={`titlebar-resources mono ${pressureClass(live.pressure)}`} title={live.advice[0]}>
      CPU {live.cpuPercent}% · RAM {live.memoryUsedPercent}%
      {live.garudaCpuPercent > 5 ? ` · Garuda ${live.garudaCpuPercent}%` : ''}
      {live.onBattery ? ' · BAT' : ''}
    </span>
  )
}
