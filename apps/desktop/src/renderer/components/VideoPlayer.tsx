import { useEffect, useRef, useState } from 'react'
import './VideoPlayer.css'

interface Props {
  sourcePath: string | null
  currentTime: number
  duration: number
  onTimeUpdate: (t: number) => void
  label?: string | null
  /** Bumps on every explicit seek click so we re-apply even to the same time. */
  seekToken?: number
  autoplay?: boolean
}

function fmt(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function VideoPlayer({
  sourcePath,
  currentTime,
  duration,
  onTimeUpdate,
  label,
  seekToken = 0,
  autoplay = false
}: Props) {
  const ref = useRef<HTMLVideoElement>(null)
  const [src, setSrc] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const suppressUpdates = useRef(false)
  const lastToken = useRef(-1)
  const seekTarget = useRef(0)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (!sourcePath) {
        setSrc(null)
        return
      }
      try {
        const url = await window.garuda.mediaUrl(sourcePath)
        if (!cancelled) {
          setSrc(url)
          setError(url ? null : 'Video file not found on disk.')
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not open video')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [sourcePath])

  useEffect(() => {
    const v = ref.current
    if (!v || !src) return

    const target = Math.max(0, Number(currentTime) || 0)
    seekTarget.current = target
    const forced = seekToken !== lastToken.current
    if (forced) lastToken.current = seekToken

    // Skip tiny drifts from timeupdate unless this was an explicit click
    if (!forced && Math.abs(v.currentTime - target) < 0.25) return

    let cancelled = false

    const finish = () => {
      if (cancelled) return
      suppressUpdates.current = false
      onTimeUpdate(v.currentTime)
    }

    const applySeek = () => {
      if (cancelled) return false
      // HAVE_METADATA or better — required before currentTime assignment sticks
      if (v.readyState < 1) return false
      suppressUpdates.current = true
      try {
        if (typeof v.fastSeek === 'function') {
          v.fastSeek(target)
        } else {
          v.currentTime = target
        }
      } catch {
        suppressUpdates.current = false
        return false
      }
      // If already at target (no seeked event), release suppress promptly
      if (Math.abs(v.currentTime - target) < 0.05) {
        finish()
      }
      return true
    }

    const onSeeked = () => {
      if (Math.abs(seekTarget.current - target) > 0.01) return
      finish()
    }
    v.addEventListener('seeked', onSeeked)

    if (v.readyState >= 1) {
      applySeek()
    } else {
      const onMeta = () => {
        applySeek()
      }
      v.addEventListener('loadedmetadata', onMeta, { once: true })
      return () => {
        cancelled = true
        v.removeEventListener('loadedmetadata', onMeta)
        v.removeEventListener('seeked', onSeeked)
      }
    }

    return () => {
      cancelled = true
      v.removeEventListener('seeked', onSeeked)
    }
  }, [currentTime, src, seekToken, onTimeUpdate])

  return (
    <div className="video-player">
      <div className="video-frame">
        {src ? (
          <video
            ref={ref}
            src={src}
            controls
            playsInline
            preload="auto"
            onLoadedMetadata={() => {
              setError(null)
              if (autoplay && ref.current) {
                void ref.current.play().catch(() => {
                  /* autoplay may be blocked — ignore */
                })
              }
            }}
            onTimeUpdate={() => {
              if (suppressUpdates.current || !ref.current) return
              onTimeUpdate(ref.current.currentTime)
            }}
            onError={() => {
              const mediaError = ref.current?.error
              const code = mediaError?.code
              if (code === MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED) {
                setError('Playback failed — file missing or format not supported.')
              } else if (code === MediaError.MEDIA_ERR_NETWORK) {
                setError('Playback failed — could not stream the local file.')
              } else {
                setError('Playback failed — check that the source file is still on disk.')
              }
            }}
          />
        ) : (
          <div className="video-empty muted">No video source</div>
        )}
        <div className="playhead-badge mono">
          {fmt(currentTime)} / {fmt(duration || 0)}
        </div>
      </div>
      {label && <p className="video-label">{label}</p>}
      {error && <p className="video-error">{error}</p>}
      <p className="video-hint muted">Click any metric, cut, or finding to scrub the playhead here.</p>
    </div>
  )
}
