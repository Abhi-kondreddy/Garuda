import { useEffect, useMemo, useRef, useState } from 'react'
import type { EditTimelineClip } from '../../shared/types'
import './TimelinePreview.css'

function clipIn(tc: EditTimelineClip): number {
  return Number(tc.inSec ?? tc.in ?? 0)
}

function clipOut(tc: EditTimelineClip): number | null {
  const v = tc.outSec ?? tc.out
  return v == null ? null : Number(v)
}

function clipDur(tc: EditTimelineClip): number {
  const inn = clipIn(tc)
  const out = clipOut(tc)
  if (out == null || !Number.isFinite(out)) return Math.max(0.5, 30 - inn)
  return Math.max(0.2, out - inn)
}

function fmt(sec: number): string {
  const s = Math.max(0, Math.floor(sec))
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}:${r.toString().padStart(2, '0')}`
}

interface Props {
  clips: EditTimelineClip[]
  aspect: '16:9' | '9:16'
  title?: string
  label?: string
}

/** Instant preview: plays timeline clips in order with in/out trims (no FFmpeg wait). */
export default function TimelinePreview({ clips, aspect, title, label }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [index, setIndex] = useState(0)
  const [src, setSrc] = useState<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const [localT, setLocalT] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const enabled = useMemo(() => clips.filter((c) => c.enabled !== false), [clips])

  const durations = useMemo(() => enabled.map(clipDur), [enabled])
  const totalDur = useMemo(() => durations.reduce((a, b) => a + b, 0), [durations])
  const offsets = useMemo(() => {
    const o: number[] = []
    let acc = 0
    for (const d of durations) {
      o.push(acc)
      acc += d
    }
    return o
  }, [durations])

  const globalT = (offsets[index] || 0) + localT
  const current = enabled[index] || null

  useEffect(() => {
    setIndex(0)
    setLocalT(0)
    setPlaying(false)
  }, [enabled.map((c) => `${c.id}:${clipIn(c)}:${clipOut(c)}`).join('|')])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (!current?.path) {
        setSrc(null)
        return
      }
      try {
        const url = await window.garuda.mediaUrl(current.path)
        if (!cancelled) {
          setSrc(url)
          setError(url ? null : 'Clip file not found')
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not open clip')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [current?.path, index])

  useEffect(() => {
    const v = videoRef.current
    if (!v || !src || !current) return
    const inn = clipIn(current)
    const onMeta = () => {
      try {
        v.currentTime = inn
      } catch {
        /* ignore */
      }
      if (playing) void v.play().catch(() => setPlaying(false))
    }
    v.addEventListener('loadedmetadata', onMeta)
    if (v.readyState >= 1) onMeta()
    return () => v.removeEventListener('loadedmetadata', onMeta)
  }, [src, current, index, playing])

  const onTimeUpdate = () => {
    const v = videoRef.current
    if (!v || !current) return
    const inn = clipIn(current)
    const out = clipOut(current)
    const rel = Math.max(0, v.currentTime - inn)
    setLocalT(rel)
    if (out != null && v.currentTime >= out - 0.05) {
      advance()
    }
  }

  const advance = () => {
    if (index + 1 < enabled.length) {
      setIndex(index + 1)
      setLocalT(0)
    } else {
      setPlaying(false)
      const v = videoRef.current
      if (v) v.pause()
    }
  }

  const togglePlay = () => {
    const v = videoRef.current
    if (!v) return
    if (playing) {
      v.pause()
      setPlaying(false)
      return
    }
    setPlaying(true)
    void v.play().catch(() => setPlaying(false))
  }

  const seekGlobal = (t: number) => {
    if (!enabled.length) return
    let target = Math.max(0, Math.min(totalDur, t))
    let i = 0
    while (i < offsets.length - 1 && target >= offsets[i + 1]) i++
    const local = target - offsets[i]
    setIndex(i)
    setLocalT(local)
    const clip = enabled[i]
    const v = videoRef.current
    if (v && clip) {
      const seekTo = clipIn(clip) + local
      const apply = () => {
        try {
          v.currentTime = seekTo
        } catch {
          /* ignore */
        }
      }
      if (v.src && i === index) apply()
      else {
        // src will reload via effect; stash local
      }
    }
  }

  if (!enabled.length) {
    return <p className="muted tip">No clips on this timeline to preview.</p>
  }

  return (
    <div className={`timeline-preview aspect-${aspect === '9:16' ? 'vertical' : 'wide'}`}>
      <div className="tp-frame">
        {title && <div className="tp-title-overlay">{title}</div>}
        {src ? (
          <video
            ref={videoRef}
            key={`${current?.id}-${index}`}
            src={src}
            playsInline
            onTimeUpdate={onTimeUpdate}
            onEnded={advance}
            onClick={togglePlay}
          />
        ) : (
          <div className="tp-empty muted">Loading preview…</div>
        )}
        {label && <span className="tp-label mono">{label}</span>}
      </div>
      {error && <p className="editor-error">{error}</p>}
      <div className="tp-controls">
        <button type="button" className="primary-btn" onClick={togglePlay}>
          {playing ? 'Pause' : 'Play preview'}
        </button>
        <span className="mono muted">
          {fmt(globalT)} / {fmt(totalDur)} · clip {index + 1}/{enabled.length}
        </span>
      </div>
      <input
        className="tp-scrub"
        type="range"
        min={0}
        max={Math.max(0.1, totalDur)}
        step={0.05}
        value={Math.min(globalT, totalDur)}
        onChange={(e) => seekGlobal(Number(e.target.value))}
      />
      <p className="muted tip">
        Live preview of order + trims (source files). Export applies crop, color, and quality settings.
      </p>
    </div>
  )
}
