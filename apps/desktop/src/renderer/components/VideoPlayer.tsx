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
  /** When set, mute video and sync this audio track to the playhead. */
  audioOverridePath?: string | null
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
  autoplay = false,
  audioOverridePath = null
}: Props) {
  const ref = useRef<HTMLVideoElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const [src, setSrc] = useState<string | null>(null)
  const [audioSrc, setAudioSrc] = useState<string | null>(null)
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
    let cancelled = false
    ;(async () => {
      if (!audioOverridePath) {
        setAudioSrc(null)
        return
      }
      const url = await window.garuda.mediaUrl(audioOverridePath)
      if (!cancelled) setAudioSrc(url)
    })()
    return () => {
      cancelled = true
    }
  }, [audioOverridePath])

  useEffect(() => {
    const v = ref.current
    if (!v) return
    v.muted = Boolean(audioSrc)
  }, [audioSrc])

  useEffect(() => {
    const v = ref.current
    const a = audioRef.current
    if (!v || !src) return

    const target = Math.max(0, Number(currentTime) || 0)
    seekTarget.current = target
    const forced = seekToken !== lastToken.current
    if (forced) lastToken.current = seekToken

    if (!forced && Math.abs(v.currentTime - target) < 0.25) return

    let cancelled = false

    const finish = () => {
      if (cancelled) return
      suppressUpdates.current = false
      onTimeUpdate(v.currentTime)
      if (a && audioSrc) {
        try {
          a.currentTime = v.currentTime
        } catch {
          /* ignore */
        }
      }
    }

    const applySeek = () => {
      if (cancelled) return false
      if (v.readyState < 1) return false
      suppressUpdates.current = true
      try {
        if (typeof v.fastSeek === 'function') {
          v.fastSeek(target)
        } else {
          v.currentTime = target
        }
        if (a && audioSrc) {
          a.currentTime = target
        }
      } catch {
        suppressUpdates.current = false
        return false
      }
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
  }, [currentTime, src, seekToken, onTimeUpdate, audioSrc])

  useEffect(() => {
    const v = ref.current
    const a = audioRef.current
    if (!v || !a || !audioSrc) return

    const syncPlay = () => {
      void a.play().catch(() => undefined)
    }
    const syncPause = () => {
      a.pause()
    }
    const syncTime = () => {
      if (Math.abs(a.currentTime - v.currentTime) > 0.35) {
        try {
          a.currentTime = v.currentTime
        } catch {
          /* ignore */
        }
      }
    }

    v.addEventListener('play', syncPlay)
    v.addEventListener('pause', syncPause)
    v.addEventListener('timeupdate', syncTime)
    if (!v.paused) syncPlay()

    return () => {
      v.removeEventListener('play', syncPlay)
      v.removeEventListener('pause', syncPause)
      v.removeEventListener('timeupdate', syncTime)
      a.pause()
    }
  }, [audioSrc, src])

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
        {audioSrc && <audio ref={audioRef} src={audioSrc} preload="auto" />}
        <div className="playhead-badge mono">
          {fmt(currentTime)} / {fmt(duration || 0)}
        </div>
      </div>
      {label && <p className="video-label">{label}</p>}
      {audioSrc && <p className="video-label">Preview mix audio active</p>}
      {error && <p className="video-error">{error}</p>}
      <p className="video-hint muted">Click any metric, cut, or finding to scrub the playhead here.</p>
    </div>
  )
}
