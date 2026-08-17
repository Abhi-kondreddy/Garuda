import type { ReactNode } from 'react'
import type { CompanionBundle } from '../../shared/types'
import './CompanionPanel.css'

interface Props {
  companion: CompanionBundle
  onSeek: (t: number, label?: string) => void
  fmtTime: (sec: number) => string
}

function Lift({ lift }: { lift?: Record<string, number> }) {
  if (!lift || !Object.keys(lift).length) return null
  const parts = Object.entries(lift)
    .filter(([, v]) => v)
    .map(([k, v]) => `${k} +${v}`)
  if (!parts.length) return null
  return <span className="lift mono">{parts.join(' · ')}</span>
}

function SeekBtn({
  t,
  children,
  onSeek,
  label,
  className
}: {
  t: number
  children: ReactNode
  onSeek: (t: number, label?: string) => void
  label?: string
  className?: string
}) {
  return (
    <button type="button" className={className ?? 'seek-btn'} onClick={() => onSeek(Number(t) || 0, label)}>
      {children}
    </button>
  )
}

export default function CompanionPanel({ companion, onSeek, fmtTime }: Props) {
  const {
    coachFeed,
    hookDoctor,
    titlesThumbnails,
    pacing,
    publishChecklist,
    talkingPoints,
    cutList,
    shortsClips,
    nextGoals,
    endingCta,
    sectionEnergy,
    patternInterrupts,
    talkingHeadBalance,
    exposureFlicker,
    codeSwitch,
    musicUnderVo,
    pauseTaxonomy,
    scoreDrivers,
    fixActions,
    beforeAfter,
    falseRisksRemoved
  } = companion

  return (
    <div className="companion">
      {beforeAfter && (
        <section className="panel panel-wide sim-panel">
          <div className="panel-head">
            <h2>Before → after simulation</h2>
            <button type="button" className="ghost-btn" onClick={() => onSeek(beforeAfter.t, 'Top fix')}>
              Jump to top fix
            </button>
          </div>
          <div className="sim-grid">
            {(['overall', 'hook', 'interestingness'] as const).map((k) => (
              <div key={k} className="sim-card">
                <span className="angle">{k}</span>
                <strong className="mono">
                  {beforeAfter.current[k]} → {beforeAfter.simulated[k]}
                </strong>
                <span className="lift mono">+{beforeAfter.delta[k]}</span>
              </div>
            ))}
          </div>
          <p className="muted talk-summary">{beforeAfter.assumption}</p>
        </section>
      )}

      <section className="panel panel-wide coach-hero">
        <div className="panel-head">
          <h2>Coach feed</h2>
          <span className="muted">Click any item to scrub the playhead</span>
        </div>
        <ol className="feed-list">
          {coachFeed.map((item, i) => (
            <li key={`${item.title}-${i}`} className={`feed-item impact-${item.impact}`}>
              <span className="feed-rank mono">{i + 1}</span>
              <SeekBtn t={item.t ?? 0} onSeek={onSeek} label={item.title} className="feed-seek">
                <div className="feed-title">
                  <span className={`impact-pill ${item.impact}`}>{item.impact}</span>
                  <strong>{item.title}</strong>
                  {typeof item.t === 'number' && <span className="mono dim">{fmtTime(item.t)}</span>}
                </div>
                <p>{item.action}</p>
                <Lift lift={item.expectedLift} />
              </SeekBtn>
            </li>
          ))}
        </ol>
      </section>

      {scoreDrivers && (
        <section className="panel panel-wide">
          <h2>Why these scores</h2>
          <div className="drivers">
            {scoreDrivers.drivers.map((d) => (
              <SeekBtn key={d.scoreKey} t={d.t} onSeek={onSeek} label={d.label} className="driver-card">
                <div className="goal-top">
                  <strong>{d.label}</strong>
                  <span className="mono saffron">{Math.round(d.value)}</span>
                </div>
                <ul>
                  {d.why.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </SeekBtn>
            ))}
          </div>
        </section>
      )}

      {fixActions && fixActions.length > 0 && (
        <section className="panel panel-wide">
          <h2>Fixes with expected lift</h2>
          <ul className="cut-list">
            {fixActions.map((a) => (
              <li key={a.id}>
                <SeekBtn t={a.t} onSeek={onSeek} label={a.title}>
                  <span className="mono">{fmtTime(a.t)}</span>
                  <span>{a.title}</span>
                </SeekBtn>
                <span className="muted">{a.detail}</span>
                <Lift lift={a.expectedLift} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="report-grid">
        <section className="panel">
          <div className="panel-head">
            <h2>Hook doctor</h2>
            <span className="mono saffron">{Math.round(hookDoctor.score)}</span>
          </div>
          <p className="verdict">{hookDoctor.verdict}</p>
          {hookDoctor.content?.openingLine && (
            <SeekBtn
              t={hookDoctor.content.t}
              onSeek={onSeek}
              label="Opening line"
              className="quote-btn"
            >
              “{hookDoctor.content.openingLine}”
            </SeekBtn>
          )}
          <ul className="finding-list">
            {hookDoctor.findings.map((f) => (
              <li key={f.id} className={`finding ${f.severity}`}>
                <SeekBtn t={f.t ?? 0} onSeek={onSeek} label={f.title} className="finding-seek">
                  <strong>{f.title}</strong>
                  {typeof f.t === 'number' && <span className="mono dim">{fmtTime(f.t)}</span>}
                </SeekBtn>
                <span className="muted">{f.detail}</span>
                <em>{f.fix}</em>
                <Lift lift={f.expectedLift} />
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Ending / CTA</h2>
            <span className="mono saffron">{endingCta ? Math.round(endingCta.score) : '—'}</span>
          </div>
          {endingCta ? (
            <>
              <p className="verdict">{endingCta.verdict}</p>
              <SeekBtn t={endingCta.t} onSeek={onSeek} label="Ending" className="ghost-btn">
                Jump to ending · {fmtTime(endingCta.t)}
              </SeekBtn>
              <ul className="finding-list">
                {endingCta.findings.map((f) => (
                  <li key={f.id} className={`finding ${f.severity}`}>
                    <SeekBtn t={f.t ?? endingCta.t} onSeek={onSeek} label={f.title} className="finding-seek">
                      <strong>{f.title}</strong>
                    </SeekBtn>
                    <span className="muted">{f.detail}</span>
                    <em>{f.fix}</em>
                    <Lift lift={f.expectedLift} />
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="muted">Re-analyze to unlock ending analysis.</p>
          )}
        </section>

        {sectionEnergy && (
          <section className="panel panel-wide">
            <h2>Section energy map</h2>
            <div className="acts">
              {sectionEnergy.sections.map((s) => (
                <SeekBtn key={s.name} t={s.valleyT} onSeek={onSeek} label={s.name} className="act">
                  <div className="act-head">
                    <strong>{s.name}</strong>
                    <span className="mono muted">
                      {fmtTime(s.start)}–{fmtTime(s.end)}
                    </span>
                  </div>
                  <p className="mono saffron">{s.avgInterestingness}</p>
                  <p className="muted">{s.note}</p>
                  <span className="muted">Valley @ {fmtTime(s.valleyT)} · Peak @ {fmtTime(s.peakT)}</span>
                </SeekBtn>
              ))}
            </div>
          </section>
        )}

        <section className="panel">
          <div className="panel-head">
            <h2>Pacing coach</h2>
            <span className="format-pill">{pacing.format === 'shorts' ? 'Shorts' : 'Long-form'}</span>
          </div>
          <dl className="metric-list compact">
            <div>
              <dt>Cuts / min</dt>
              <dd className="mono">{pacing.measured.cutsPerMin}</dd>
            </div>
            <div>
              <dt>WPM</dt>
              <dd className="mono">{pacing.measured.wpm ?? '—'}</dd>
            </div>
            <div>
              <dt>Dead air</dt>
              <dd className="mono">{(pacing.measured.deadAirRatio * 100).toFixed(0)}%</dd>
            </div>
          </dl>
          {patternInterrupts && (
            <SeekBtn t={patternInterrupts.t} onSeek={onSeek} label="Pattern gap" className="quote-btn">
              Pattern interrupts · avg gap {patternInterrupts.avgGapSec}s (score {patternInterrupts.score})
            </SeekBtn>
          )}
          <ul className="finding-list">
            {pacing.tips.map((t) => (
              <li key={t.id} className={`finding ${t.severity}`}>
                <strong>{t.title}</strong>
                <span className="muted">{t.detail}</span>
                <em>{t.fix}</em>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Publish checklist</h2>
            <span className={`ready-pill ${publishChecklist.ready ? 'go' : 'wait'}`}>
              {publishChecklist.passed}/{publishChecklist.total}
            </span>
          </div>
          <ul className="check-list">
            {publishChecklist.items.map((item) => (
              <li key={item.id} className={item.status}>
                <span className="check-mark mono">{item.status === 'pass' ? 'PASS' : 'FAIL'}</span>
                <div>
                  <strong>{item.label}</strong>
                  <span className="muted">{item.detail}</span>
                  {item.status === 'fail' && <em>{item.fix}</em>}
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <h2>Title angles</h2>
          <ul className="title-list">
            {titlesThumbnails.titles.map((t) => (
              <li key={t.angle}>
                <span className="angle">{t.angle}</span>
                <strong>{t.title}</strong>
                <span className="muted">{t.why}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <h2>Thumbnail scores</h2>
          <ul className="thumb-list">
            {titlesThumbnails.thumbnails.map((th) => (
              <li key={th.t}>
                <SeekBtn t={th.t} onSeek={onSeek} label={th.label}>
                  <span className="mono">{fmtTime(th.t)}</span>
                  <span>{th.label}</span>
                  <span className="mono score">{Math.round(th.score)}</span>
                </SeekBtn>
                <span className="muted tip">{th.tip}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel panel-wide">
          <h2>Talking points · Promise → Proof → Payoff</h2>
          <p className="muted talk-summary">{talkingPoints.summary}</p>
          <div className="acts">
            {talkingPoints.structure.map((act) => (
              <div key={act.act} className="act">
                <div className="act-head">
                  <strong>{act.act}</strong>
                  <span className="mono muted">{act.window}</span>
                </div>
                <p className="muted">{act.coach}</p>
                <ul>
                  {act.beats.length === 0 && <li className="muted">No spoken beats in this act.</li>}
                  {act.beats.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <h2>Cut list</h2>
          <ul className="cut-list">
            {cutList.map((c, i) => (
              <li key={i} className={c.severity}>
                <SeekBtn t={c.t ?? c.start} onSeek={onSeek} label={c.reason}>
                  <span className="mono">
                    {fmtTime(c.start)}–{fmtTime(c.end)}
                  </span>
                  <span>{c.reason}</span>
                </SeekBtn>
                <span className="muted">{c.suggestion}</span>
                <Lift lift={c.expectedLift} />
              </li>
            ))}
          </ul>
          {falseRisksRemoved && falseRisksRemoved.length > 0 && (
            <p className="muted tip">
              Filtered {falseRisksRemoved.length} false risk zone(s) (dense speech storytelling).
            </p>
          )}
        </section>

        <section className="panel">
          <h2>Shorts clips</h2>
          <ul className="shorts-list">
            {shortsClips.map((c, i) => (
              <li key={i}>
                <SeekBtn t={c.t ?? c.start} onSeek={onSeek} label={c.label}>
                  <span className="mono">
                    {fmtTime(c.start)}–{fmtTime(c.end)}
                  </span>
                  <span>{c.label}</span>
                  <span className="mono score">{Math.round(c.score)}</span>
                </SeekBtn>
                <span className="muted">“{c.captionHook}”</span>
              </li>
            ))}
          </ul>
        </section>

        {pauseTaxonomy && (
          <section className="panel">
            <h2>Pause taxonomy</h2>
            <p className="muted">
              Dead air {pauseTaxonomy.deadAirCount} · Think pauses {pauseTaxonomy.thinkCount}
            </p>
            <ul className="cut-list">
              {pauseTaxonomy.items.slice(0, 10).map((p, i) => (
                <li key={i} className={p.severity}>
                  <SeekBtn t={p.t} onSeek={onSeek} label={p.kind}>
                    <span className="mono">{fmtTime(p.start)}</span>
                    <span>
                      {p.kind} · {p.duration}s
                    </span>
                  </SeekBtn>
                  <span className="muted">{p.action}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {codeSwitch && (
          <section className="panel">
            <h2>Code-switch quality</h2>
            <p className="mono saffron">Score {codeSwitch.score}</p>
            <ul className="finding-list">
              {codeSwitch.issues.length === 0 && <li className="muted">No tight mid-phrase switches flagged.</li>}
              {codeSwitch.issues.map((iss, i) => (
                <li key={i} className={`finding ${iss.severity}`}>
                  <SeekBtn t={iss.t} onSeek={onSeek} label={iss.title} className="finding-seek">
                    <strong>
                      {iss.title} · {iss.from}→{iss.to}
                    </strong>
                    <span className="mono dim">{fmtTime(iss.t)}</span>
                  </SeekBtn>
                  <span className="muted">{iss.detail}</span>
                  <em>{iss.fix}</em>
                </li>
              ))}
            </ul>
          </section>
        )}

        {musicUnderVo && (
          <section className="panel">
            <h2>Music under VO</h2>
            <SeekBtn t={musicUnderVo.t} onSeek={onSeek} label="Music/VO" className="quote-btn">
              Score {musicUnderVo.score} · music/speech {musicUnderVo.musicSpeechRatio}
            </SeekBtn>
            <ul className="cut-list">
              {musicUnderVo.conflictWindows.map((w, i) => (
                <li key={i}>
                  <SeekBtn t={w.t} onSeek={onSeek} label={w.reason}>
                    <span className="mono">{fmtTime(w.t)}</span>
                    <span>{w.reason}</span>
                  </SeekBtn>
                  <span className="muted">{w.fix}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {talkingHeadBalance && (
          <section className="panel">
            <h2>Talking-head vs B-roll</h2>
            <SeekBtn t={talkingHeadBalance.t} onSeek={onSeek} label="A-cam balance" className="quote-btn">
              Head {(talkingHeadBalance.talkingHeadRatio * 100).toFixed(0)}% · score {talkingHeadBalance.score}
            </SeekBtn>
            <ul className="finding-list">
              {talkingHeadBalance.findings.map((f) => (
                <li key={f.id} className={`finding ${f.severity}`}>
                  <SeekBtn t={f.t ?? 0} onSeek={onSeek} label={f.title} className="finding-seek">
                    <strong>{f.title}</strong>
                  </SeekBtn>
                  <em>{f.fix}</em>
                </li>
              ))}
            </ul>
          </section>
        )}

        {exposureFlicker && (
          <section className="panel">
            <h2>Exposure flicker</h2>
            <p className="mono saffron">Score {exposureFlicker.score}</p>
            <ul className="cut-list">
              {exposureFlicker.events.map((e, i) => (
                <li key={i} className={e.severity}>
                  <SeekBtn t={e.t} onSeek={onSeek} label={e.reason}>
                    <span className="mono">{fmtTime(e.t)}</span>
                    <span>
                      Δ{e.delta} · {e.reason}
                    </span>
                  </SeekBtn>
                  <span className="muted">{e.fix}</span>
                </li>
              ))}
              {exposureFlicker.events.length === 0 && <li className="muted">No harsh brightness jumps.</li>}
            </ul>
          </section>
        )}

        <section className="panel panel-wide">
          <h2>Next video goals</h2>
          <ul className="goals">
            {nextGoals.map((g) => (
              <li key={g.metric}>
                <div className="goal-top">
                  <strong>{g.metric}</strong>
                  <span className="mono">
                    {g.current} → {g.target}
                  </span>
                </div>
                <p>{g.plan}</p>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
