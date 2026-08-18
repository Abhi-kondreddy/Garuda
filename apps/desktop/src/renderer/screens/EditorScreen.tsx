import { Component, useCallback, useEffect, useRef, useState, type ErrorInfo, type ReactNode } from 'react'
import type {
  EditBriefing,
  EditClip,
  EditExportOptions,
  EditorProgressEvent,
  EditOutput,
  EditProject,
  EditProjectSummary,
  EditShortBin,
  EditTimelineClip
} from '../../shared/types'
import { DEFAULT_EDIT_EXPORT_OPTIONS, normalizeEditProject } from '../../shared/types'
import EditorProgressPanel from '../components/EditorProgressPanel'
import '../components/EditorProgressPanel.css'
import HudPanel from '../components/HudPanel'
import TimelinePreview from '../components/TimelinePreview'
import './EditorScreen.css'

function fmtDur(sec: number | null | undefined): string {
  if (sec == null || !Number.isFinite(sec)) return '—'
  const s = Math.round(sec)
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}:${r.toString().padStart(2, '0')}`
}

function clipIn(tc: EditTimelineClip): number {
  return Number(tc.inSec ?? tc.in ?? 0)
}

function clipOut(tc: EditTimelineClip): number | null {
  const v = tc.outSec ?? tc.out
  return v == null ? null : Number(v)
}

function moveItem<T>(arr: T[], from: number, to: number): T[] {
  if (to < 0 || to >= arr.length || from === to) return arr
  const next = [...arr]
  const [item] = next.splice(from, 1)
  next.splice(to, 0, item)
  return next
}

class EditorErrorBoundary extends Component<
  { children: ReactNode; onReset?: () => void },
  { error: string | null }
> {
  state = { error: null as string | null }

  static getDerivedStateFromError(error: Error) {
    return { error: error.message || 'Editor UI crashed' }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[EditorScreen]', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="editor">
          <p className="editor-error">
            Editor hit a display error: {this.state.error}
          </p>
          <button
            type="button"
            className="primary-btn"
            onClick={() => {
              this.setState({ error: null })
              this.props.onReset?.()
            }}
          >
            Reset editor view
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function EditorScreenInner() {
  const [list, setList] = useState<EditProjectSummary[]>([])
  const [project, setProject] = useState<EditProject | null>(null)
  const [busy, setBusy] = useState(false)
  const [progressMsg, setProgressMsg] = useState<string | null>(null)
  const [progressPct, setProgressPct] = useState(0)
  const [editorProgress, setEditorProgress] = useState<EditorProgressEvent | null>(null)
  const [stagePercents, setStagePercents] = useState<
    Partial<Record<'propose' | 'analyze' | 'assemble' | 'export', number>>
  >({})
  const [jobLabel, setJobLabel] = useState('Deep propose')
  const [error, setError] = useState<string | null>(null)
  const [newName, setNewName] = useState('')
  const [binTopic, setBinTopic] = useState('')
  const [selectedOutputId, setSelectedOutputId] = useState<string | null>(null)
  const [exportOpts, setExportOpts] = useState<EditExportOptions>({ ...DEFAULT_EDIT_EXPORT_OPTIONS })
  const projectPathRef = useRef<string | null>(null)

  const applyProject = useCallback((raw: EditProject) => {
    const next = normalizeEditProject(raw)
    setProject(next)
    projectPathRef.current = next.projectPath
    return next
  }, [])

  const refreshList = useCallback(async () => {
    setList(await window.garuda.editorList())
  }, [])

  useEffect(() => {
    projectPathRef.current = project?.projectPath ?? null
  }, [project?.projectPath])

  useEffect(() => {
    void refreshList()
  }, [refreshList])

  useEffect(() => {
    const offP = window.garuda.onEditorProgress((evt) => {
      const e = evt as EditorProgressEvent
      setEditorProgress(e)
      setProgressMsg(e.message)
      setProgressPct(e.percent)
      setBusy(true)
      const stage = String(e.stage || 'propose')
      const key =
        stage === 'export' || stage === 'render'
          ? 'export'
          : stage === 'assemble'
            ? 'assemble'
            : stage === 'propose'
              ? 'propose'
              : 'analyze'
      setStagePercents((prev) => {
        const next = { ...prev }
        const order = ['propose', 'analyze', 'assemble', 'export'] as const
        for (const s of order) {
          if (s === key) {
            // Map overall job % into a stage-local bar when possible.
            let stagePct = e.percent
            if (key === 'analyze' && e.clipIndex && e.clipTotal) {
              const clipShare = 100 / Math.max(e.clipTotal, 1)
              const phase = typeof e.phasePercent === 'number' ? e.phasePercent : e.percent
              stagePct = Math.min(99, (e.clipIndex - 1) * clipShare + (phase / 100) * clipShare)
            } else if (key === 'assemble') {
              stagePct = Math.min(100, Math.max(0, ((e.percent - 88) / 12) * 100))
            }
            next[s] = Math.max(next[s] ?? 0, Math.round(stagePct))
            break
          }
          next[s] = 100
        }
        return next
      })
    })
    const offD = window.garuda.onEditorDone(async (evt) => {
      setBusy(false)
      setProgressMsg(null)
      setProgressPct(0)
      setEditorProgress(null)
      setStagePercents({})
      const path = projectPathRef.current
      if (path) {
        try {
          const loaded = await window.garuda.editorLoad(path)
          const next = applyProject(loaded)
          if (Array.isArray(evt.outputs) && evt.outputs.length) {
            setSelectedOutputId((evt.outputs[0] as EditOutput).id)
          } else {
            setSelectedOutputId((prev) => prev ?? next.outputs[0]?.id ?? null)
          }
        } catch (e) {
          setError(e instanceof Error ? e.message : 'Failed to reload project after job')
        }
      }
      void refreshList()
    })
    const offE = window.garuda.onEditorError((evt) => {
      setBusy(false)
      setProgressMsg(null)
      setProgressPct(0)
      setEditorProgress(null)
      setStagePercents({})
      setError(evt.detail ? `${evt.message} — ${evt.detail}` : evt.message)
    })
    const offC = window.garuda.onEditorCancelled(() => {
      setBusy(false)
      setProgressMsg(null)
      setProgressPct(0)
      setEditorProgress(null)
      setStagePercents({})
    })
    return () => {
      offP()
      offD()
      offE()
      offC()
    }
  }, [refreshList, applyProject])

  const persist = async (next: EditProject) => {
    const saved = await window.garuda.editorSave(normalizeEditProject(next))
    return applyProject(saved)
  }

  const createProject = async () => {
    setError(null)
    const p = await window.garuda.editorCreate(newName || undefined)
    setNewName('')
    applyProject(p)
    setSelectedOutputId(null)
    void refreshList()
  }

  const openProject = async (item: EditProjectSummary) => {
    setError(null)
    const p = await window.garuda.editorLoad(item.projectPath)
    const next = applyProject(p)
    setSelectedOutputId(next.outputs[0]?.id ?? null)
  }

  const addClips = async () => {
    if (!project) return
    const clips = await window.garuda.editorOpenVideos()
    if (!clips.length) return
    await persist({ ...project, clips: [...project.clips, ...clips] })
  }

  const removeClip = async (id: string) => {
    if (!project) return
    await persist({
      ...project,
      clips: project.clips.filter((c) => c.id !== id),
      shortBins: project.shortBins.map((b) => ({
        ...b,
        clipIds: b.clipIds.filter((cid) => cid !== id)
      })),
      sectionHints: project.sectionHints.map((s) => ({
        ...s,
        clipIds: s.clipIds.filter((cid) => cid !== id)
      }))
    })
  }

  const moveClip = async (from: number, to: number) => {
    if (!project) return
    await persist({ ...project, clips: moveItem(project.clips, from, to) })
  }

  const patchBriefing = async (patch: Partial<EditBriefing>) => {
    if (!project) return
    await persist({
      ...project,
      briefing: { ...project.briefing, ...patch }
    })
  }

  const addShortBin = async () => {
    if (!project || !binTopic.trim()) return
    const bin: EditShortBin = {
      id: `bin-${Date.now()}`,
      topic: binTopic.trim(),
      clipIds: [],
      shortsOnly: false
    }
    setBinTopic('')
    await persist({ ...project, shortBins: [...project.shortBins, bin] })
  }

  const addClipsToBin = async (binId: string) => {
    if (!project) return
    const clips = await window.garuda.editorOpenVideos()
    if (!clips.length) return
    const existingPaths = new Set(project.clips.map((c) => c.path))
    const newClips = clips.filter((c) => !existingPaths.has(c.path))
    const allClips = [...project.clips, ...newClips]
    const ids = clips.map((c) => {
      const found = allClips.find((x) => x.path === c.path)
      return found!.id
    })
    await persist({
      ...project,
      clips: allClips,
      shortBins: project.shortBins.map((b) =>
        b.id === binId ? { ...b, clipIds: [...new Set([...b.clipIds, ...ids])] } : b
      )
    })
  }

  const propose = async (quick = false) => {
    if (!project) return
    setError(null)
    setBusy(true)
    setJobLabel(quick ? 'Quick propose' : 'Deep propose')
    setProgressMsg(quick ? 'Quick propose…' : 'Reading clips (visual + audio)…')
    setProgressPct(2)
    setStagePercents({ propose: 5 })
    setEditorProgress({
      type: 'progress',
      stage: 'propose',
      percent: 2,
      message: quick ? 'Quick propose…' : 'Starting deep read…',
      phase: 'probe',
      phasePercent: 10
    })
    try {
      const saved = await persist(project)
      await window.garuda.editorPropose(saved.projectPath, { quick })
    } catch (e) {
      console.error('[editor propose]', e)
      setBusy(false)
      setProgressMsg(null)
      setProgressPct(0)
      setEditorProgress(null)
      setStagePercents({})
      setError(e instanceof Error ? e.message : 'Propose failed')
    }
  }

  const exportOutput = async (outputId: string) => {
    if (!project) return
    setError(null)
    setBusy(true)
    setJobLabel('Export')
    setProgressMsg('Exporting…')
    setProgressPct(5)
    setStagePercents({ propose: 100, analyze: 100, assemble: 100, export: 5 })
    setEditorProgress({
      type: 'progress',
      stage: 'export',
      percent: 5,
      message: 'Preparing export…',
      phase: 'encode',
      phasePercent: 5
    })
    try {
      const saved = await persist(project)
      await window.garuda.editorExport(saved.projectPath, outputId, exportOpts)
    } catch (e) {
      setBusy(false)
      setProgressMsg(null)
      setProgressPct(0)
      setEditorProgress(null)
      setStagePercents({})
      setError(e instanceof Error ? e.message : 'Export failed to start')
    }
  }

  const moveTimelineClip = async (outputId: string, from: number, to: number) => {
    if (!project) return
    await persist({
      ...project,
      outputs: project.outputs.map((o) => {
        if (o.id !== outputId) return o
        return {
          ...o,
          timeline: {
            ...o.timeline,
            clips: moveItem(o.timeline.clips, from, to)
          }
        }
      })
    })
  }

  const selected: EditOutput | null =
    project?.outputs.find((o) => o.id === selectedOutputId) ?? project?.outputs[0] ?? null

  if (!project) {
    return (
      <div className="editor">
        <header className="editor-head">
          <div>
            <p className="eyebrow mono">ASSEMBLE</p>
            <h1>Editor</h1>
            <p className="muted">
              Build a day project: add clips, set 1 long + N Shorts, propose, drag-fix, export.
            </p>
          </div>
        </header>

        <HudPanel title="New project" eyebrow="Start" delay={0}>
          <div className="editor-row">
            <input
              className="editor-input"
              placeholder="Project name (e.g. Hyderabad day)"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <button className="primary-btn" type="button" onClick={() => void createProject()}>
              Create project
            </button>
          </div>
        </HudPanel>

        <HudPanel title="Recent projects" eyebrow="Library" delay={0} tone="lime">
          {list.length === 0 && <p className="muted">No edit projects yet.</p>}
          <ul className="editor-project-list">
            {list.map((item) => (
              <li key={item.id}>
                <button type="button" className="editor-project-btn" onClick={() => void openProject(item)}>
                  <strong>{item.name}</strong>
                  <span className="mono muted">
                    {item.clipCount} clips · {item.longCount}L + {item.shortsCount}S · {item.status}
                  </span>
                </button>
                <button
                  type="button"
                  className="ghost-btn"
                  onClick={() =>
                    void window.garuda.editorDelete(item.projectPath).then(setList)
                  }
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        </HudPanel>
      </div>
    )
  }

  const b = project.briefing

  return (
    <div className="editor">
      <header className="editor-head">
        <div>
          <button type="button" className="ghost-btn editor-back" onClick={() => setProject(null)}>
            ← Projects
          </button>
          <h1>{project.name}</h1>
          <p className="muted mono">
            {project.clips.length} clips · {project.status}
            {busy ? ` · ${jobLabel} · ${Math.round(progressPct)}%` : ''}
          </p>
        </div>
        <div className="editor-head-actions">
          <button
            className="ghost-btn"
            type="button"
            disabled={busy || project.clips.length === 0}
            onClick={() => void propose(true)}
            title="Order from filenames/duration only — no deep read"
          >
            Quick propose
          </button>
          <button
            className="primary-btn"
            type="button"
            disabled={busy || project.clips.length === 0}
            onClick={() => void propose(false)}
          >
            Propose timelines
          </button>
        </div>
      </header>

      {error && <p className="editor-error">{error}</p>}

      {busy ? (
        <EditorProgressPanel
          progress={editorProgress}
          overall={progressPct}
          stagePercents={stagePercents}
          jobLabel={jobLabel}
          onCancel={() => void window.garuda.editorCancel()}
        />
      ) : null}

      <div className="editor-grid">
        <HudPanel title="Day pool" eyebrow="Clips" delay={0}>
          <div className="editor-row">
            <button className="primary-btn" type="button" onClick={() => void addClips()} disabled={busy}>
              + Add clips
            </button>
          </div>
          <ul className="editor-clip-list">
            {project.clips.map((c: EditClip, i) => (
              <li key={c.id}>
                <span className="editor-clip-meta">
                  <strong>{c.name}</strong>
                  <span className="mono muted">{fmtDur(c.durationSec)}</span>
                </span>
                <span className="editor-clip-actions">
                  <button type="button" className="ghost-btn" disabled={i === 0} onClick={() => void moveClip(i, i - 1)}>
                    ↑
                  </button>
                  <button
                    type="button"
                    className="ghost-btn"
                    disabled={i === project.clips.length - 1}
                    onClick={() => void moveClip(i, i + 1)}
                  >
                    ↓
                  </button>
                  <button type="button" className="ghost-btn" onClick={() => void removeClip(c.id)}>
                    Remove
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </HudPanel>

        <HudPanel title="Format & briefing" eyebrow="You decide" delay={0} tone="lime">
          <div className="editor-form">
            <label>
              Title
              <input
                className="editor-input"
                value={b.title}
                onChange={(e) => void patchBriefing({ title: e.target.value })}
              />
            </label>
            <label>
              Subtitle
              <input
                className="editor-input"
                value={b.subtitle}
                onChange={(e) => void patchBriefing({ subtitle: e.target.value })}
              />
            </label>
            <label>
              CTA (end card)
              <input
                className="editor-input"
                value={b.cta}
                onChange={(e) => void patchBriefing({ cta: e.target.value })}
              />
            </label>
            <div className="editor-form-row">
              <label>
                Long videos
                <input
                  className="editor-input"
                  type="number"
                  min={0}
                  max={3}
                  value={b.format.longCount}
                  onChange={(e) =>
                    void patchBriefing({
                      format: { ...b.format, longCount: Math.max(0, Number(e.target.value) || 0) }
                    })
                  }
                />
              </label>
              <label>
                Shorts
                <input
                  className="editor-input"
                  type="number"
                  min={0}
                  max={20}
                  value={b.format.shortsCount}
                  onChange={(e) =>
                    void patchBriefing({
                      format: { ...b.format, shortsCount: Math.max(0, Number(e.target.value) || 0) }
                    })
                  }
                />
              </label>
            </div>
            <div className="editor-form-row">
              <label>
                Long target (min)
                <input
                  className="editor-input"
                  type="number"
                  min={1}
                  max={60}
                  value={b.longTargetMin}
                  onChange={(e) =>
                    void patchBriefing({ longTargetMin: Math.max(1, Number(e.target.value) || 10) })
                  }
                />
              </label>
              <label>
                Short max (sec)
                <input
                  className="editor-input"
                  type="number"
                  min={15}
                  max={60}
                  value={b.shortMaxSec}
                  onChange={(e) =>
                    void patchBriefing({ shortMaxSec: Math.max(15, Number(e.target.value) || 60) })
                  }
                />
              </label>
            </div>
            <label>
              Look
              <select
                className="editor-input"
                value={b.look}
                onChange={(e) => void patchBriefing({ look: e.target.value as EditBriefing['look'] })}
              >
                <option value="neutral">Neutral</option>
                <option value="warm">Warm</option>
                <option value="contrast">Contrast</option>
              </select>
            </label>
            <label>
              Music mood (slot)
              <select
                className="editor-input"
                value={b.musicMood}
                onChange={(e) =>
                  void patchBriefing({ musicMood: e.target.value as EditBriefing['musicMood'] })
                }
              >
                <option value="none">None yet</option>
                <option value="chill">Chill</option>
                <option value="upbeat">Upbeat</option>
                <option value="cinematic">Cinematic</option>
              </select>
            </label>
          </div>
        </HudPanel>

        <HudPanel title="Pinned Short bins" eyebrow="Optional" delay={0}>
          <p className="muted tip">
            “Shorts about this place” — name the topic, add clips for that Short only.
          </p>
          <div className="editor-row">
            <input
              className="editor-input"
              placeholder="Topic e.g. Charminar"
              value={binTopic}
              onChange={(e) => setBinTopic(e.target.value)}
            />
            <button className="ghost-btn" type="button" onClick={() => void addShortBin()}>
              + Bin
            </button>
          </div>
          <ul className="editor-bin-list">
            {project.shortBins.map((bin) => (
              <li key={bin.id}>
                <div className="editor-bin-head">
                  <strong>{bin.topic}</strong>
                  <label className="editor-check">
                    <input
                      type="checkbox"
                      checked={bin.shortsOnly}
                      onChange={(e) =>
                        void persist({
                          ...project,
                          shortBins: project.shortBins.map((x) =>
                            x.id === bin.id ? { ...x, shortsOnly: e.target.checked } : x
                          )
                        })
                      }
                    />
                    Shorts-only
                  </label>
                </div>
                <span className="mono muted">
                  {bin.clipIds.length} clip(s):{' '}
                  {bin.clipIds
                    .map((id) => project.clips.find((c) => c.id === id)?.name)
                    .filter(Boolean)
                    .join(', ') || 'none'}
                </span>
                <div className="editor-row">
                  <button type="button" className="ghost-btn" onClick={() => void addClipsToBin(bin.id)}>
                    + Clips for this Short
                  </button>
                  <button
                    type="button"
                    className="ghost-btn"
                    onClick={() =>
                      void persist({
                        ...project,
                        shortBins: project.shortBins.filter((x) => x.id !== bin.id)
                      })
                    }
                  >
                    Remove bin
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </HudPanel>
      </div>

      {project.outputs.length > 0 && (
        <section className="editor-deliverables">
          <header className="editor-deliverables-head">
            <p className="eyebrow mono">PROPOSAL</p>
            <h2>Deliverables</h2>
          </header>
          <div className="editor-outputs">
            {project.outputs.map((o) => (
              <button
                key={o.id}
                type="button"
                className={`editor-output-card ${selected?.id === o.id ? 'active' : ''} ${o.kind}`}
                onClick={() => setSelectedOutputId(o.id)}
              >
                <span className="mono">{o.kind === 'long' ? '16:9' : '9:16'}</span>
                <strong>{o.title || o.id}</strong>
                {o.success && (
                  <span className="mono score">{Math.round(o.success.score)}</span>
                )}
                <span className="muted">{o.source}</span>
              </button>
            ))}
          </div>

          {selected && (
            <div className="editor-output-detail">
              <div className="editor-output-detail-head">
                <div>
                  <h3>{selected.title || selected.id}</h3>
                </div>
              </div>

              <div className="editor-why">
                <div className="editor-why-head">
                  <p className="eyebrow mono">WHY THIS CUT</p>
                  {selected.success && (
                    <span className="editor-why-score mono">
                      Score {Math.round(selected.success.score)}
                    </span>
                  )}
                </div>
                <ul className="editor-why-list">
                  {(selected.proposalReasons || []).length === 0 &&
                    (selected.success?.why || []).length === 0 && (
                      <li className="muted">No reasons recorded for this output.</li>
                    )}
                  {(selected.proposalReasons || []).map((r, i) => (
                    <li key={`r-${i}`}>
                      <span className="editor-why-tag">Proposal</span>
                      <span>{String(r)}</span>
                    </li>
                  ))}
                  {(selected.success?.why || []).map((w, i) => (
                    <li key={`w-${i}`}>
                      <span className="editor-why-tag success">Shorts fit</span>
                      <span>{String(w)}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <TimelinePreview
                clips={selected.timeline?.clips || []}
                aspect={selected.aspect}
                title={
                  exportOpts.burnTitle
                    ? (project.briefing.title || selected.topic || undefined)
                    : undefined
                }
                label={`${selected.kind} · ${selected.aspect}`}
              />

              <div className="editor-export-opts">
                <h4>Export settings</h4>
                <div className="editor-form-row">
                  <label>
                    Quality
                    <select
                      className="editor-input"
                      value={exportOpts.quality}
                      onChange={(e) =>
                        setExportOpts((o) => ({
                          ...o,
                          quality: e.target.value as EditExportOptions['quality']
                        }))
                      }
                    >
                      <option value="draft">Draft — fast, smaller file</option>
                      <option value="good">Good — balanced (default)</option>
                      <option value="high">High — slower, sharper</option>
                    </select>
                  </label>
                  <label>
                    Resolution
                    <select
                      className="editor-input"
                      value={exportOpts.resolution}
                      onChange={(e) =>
                        setExportOpts((o) => ({
                          ...o,
                          resolution: e.target.value as EditExportOptions['resolution']
                        }))
                      }
                    >
                      <option value="720">
                        {selected.aspect === '9:16' ? '720×1280' : '1280×720'}
                      </option>
                      <option value="1080">
                        {selected.aspect === '9:16' ? '1080×1920' : '1920×1080'}
                      </option>
                      <option value="1440">
                        {selected.aspect === '9:16' ? '1440×2560' : '2560×1440'}
                      </option>
                    </select>
                  </label>
                </div>
                <div className="editor-form-row">
                  <label>
                    Frame rate
                    <select
                      className="editor-input"
                      value={exportOpts.fps}
                      onChange={(e) =>
                        setExportOpts((o) => ({
                          ...o,
                          fps: Number(e.target.value) as EditExportOptions['fps']
                        }))
                      }
                    >
                      <option value={24}>24 fps</option>
                      <option value={30}>30 fps</option>
                      <option value={60}>60 fps</option>
                    </select>
                  </label>
                  <label className="editor-check export-check">
                    <input
                      type="checkbox"
                      checked={exportOpts.burnTitle}
                      onChange={(e) =>
                        setExportOpts((o) => ({ ...o, burnTitle: e.target.checked }))
                      }
                    />
                    Burn title into export
                  </label>
                </div>
                <p className="muted tip">
                  {exportOpts.quality === 'draft' && 'Ultrafast encode, CRF 28 — quick review files.'}
                  {exportOpts.quality === 'good' && 'Veryfast encode, CRF 20 — solid YouTube upload.'}
                  {exportOpts.quality === 'high' && 'Slow encode, CRF 17 — best quality, longer wait.'}
                </p>
                <div className="editor-row">
                  <button
                    className="primary-btn"
                    type="button"
                    disabled={busy}
                    onClick={() => void exportOutput(selected.id)}
                  >
                    Export {selected.aspect} · {exportOpts.quality}
                  </button>
                  {selected.exportPath && (
                    <button
                      className="ghost-btn"
                      type="button"
                      onClick={() => void window.garuda.editorRevealExport(selected.exportPath!)}
                    >
                      Reveal file
                    </button>
                  )}
                </div>
              </div>

              <ol className="editor-timeline">
                {(selected.timeline?.clips || []).map((tc, i) => (
                  <li key={tc.id || `clip-${i}`}>
                    <span className="mono">
                      {fmtDur(clipIn(tc))}–{fmtDur(clipOut(tc))}
                    </span>
                    <span>{project.clips.find((c) => c.id === tc.clipId)?.name || tc.path}</span>
                    <span className="editor-clip-actions">
                      <button
                        type="button"
                        className="ghost-btn"
                        disabled={i === 0}
                        onClick={() => void moveTimelineClip(selected.id, i, i - 1)}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="ghost-btn"
                        disabled={i >= (selected.timeline?.clips?.length || 0) - 1}
                        onClick={() => void moveTimelineClip(selected.id, i, i + 1)}
                      >
                        ↓
                      </button>
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </section>
      )}
    </div>
  )
}

export default function EditorScreen() {
  return (
    <EditorErrorBoundary>
      <EditorScreenInner />
    </EditorErrorBoundary>
  )
}
