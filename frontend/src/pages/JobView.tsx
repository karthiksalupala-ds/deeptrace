import { ReactNode, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, Clock3, Copy, Download, FileVideo, Grid2X2, List, LoaderCircle, Search, ShieldCheck } from 'lucide-react'
import { analyzeMotion, fileUrl, getJob, Job, MotionEvent, RecoveredFile, Report, searchEvidence } from '../lib/api'

interface JobViewProps { jobId: string; onReport: (job: Job) => void }
const stages = ['Signature Detection', 'Frame Extraction', 'Integrity Validation', 'Temporal Sequencing', 'Video Reconstruction']

export function JobView({ jobId, onReport }: JobViewProps) {
  const [job, setJob] = useState<Job | null>(null)
  const [started] = useState(Date.now())
  const [view, setView] = useState<'table' | 'grid'>('table')
  const [tab, setTab] = useState<'overview' | 'files' | 'timeline'>('overview')
  const [filter, setFilter] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<RecoveredFile[]>([])
  const [copied, setCopied] = useState('')

  useEffect(() => {
    let active = true
    const poll = async () => { try { const next = await getJob(jobId); if (active) setJob(next) } catch { /* next poll retries */ } }
    void poll()
    const timer = window.setInterval(() => { if (job?.status === 'done' || job?.status === 'failed') return; void poll() }, 1500)
    return () => { active = false; window.clearInterval(timer) }
  }, [jobId, job?.status])

  const stageIndex = job?.status === 'done' ? stages.length : job?.status === 'processing' ? Math.min(stages.length - 1, Math.floor((Date.now() - started) / 1800)) : 0
  const report = job?.report
  useEffect(() => {
    if (!report) return
    let active = true
    const timer = window.setTimeout(async () => {
      try {
        const result = await searchEvidence(jobId, searchQuery)
        if (active) setSearchResults(result.files)
      } catch {
        if (active) setSearchResults([])
      }
    }, 250)
    return () => { active = false; window.clearTimeout(timer) }
  }, [jobId, searchQuery, report])
  const files = useMemo(() => searchResults.filter((file) => filter === 'all' || (filter === 'demo' ? file.is_demo : file.is_raw_fallback)), [searchResults, filter])

  if (!job) return <div className="page loading-state"><LoaderCircle className="spin" size={28} /><h2>Connecting to recovery job…</h2><p>Job reference {jobId.slice(0, 12)}…</p></div>
  if (job.status === 'failed') return <div className="page"><div className="failure-state"><AlertTriangle size={34} /><span className="section-kicker">Recovery failed</span><h1>Analysis could not be completed.</h1><p>{job.error || 'The backend returned an unknown error.'}</p></div></div>
  if (!report) return <div className="page loading-state"><LoaderCircle className="spin" size={28} /><h2>Reconstructing evidence…</h2><p>Job reference {jobId.slice(0, 12)}…</p></div>

  return <div className="page job-page">
    <div className="case-header"><div><span className="section-kicker">Case / {job.job_id.slice(0, 8).toUpperCase()}</span><h1>{job.filename}</h1><p>{report.device_identification.vendor_name} · detected at offset {report.device_identification.signature_found_at_offset ?? '—'} · {new Date(job.created_at).toLocaleString()}</p></div><div className="case-actions"><span className={`status-badge ${job.status}`}>{job.status === 'done' ? <CheckCircle2 size={14} /> : <Clock3 size={14} />}{job.status}</span>{job.status === 'done' && <button className="secondary-button" onClick={() => onReport(job)}>View report <Download size={15} /></button>}</div></div>
    {job.status === 'done' && <div className="case-tabs"><button className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}>Overview</button><button className={tab === 'files' ? 'active' : ''} onClick={() => setTab('files')}>Recovered Files</button><button className={tab === 'timeline' ? 'active' : ''} onClick={() => setTab('timeline')}>Timeline</button></div>}
    {job.status !== 'done' ? <Processing stages={stages} active={stageIndex} /> : tab === 'timeline' ? <Timeline sequences={report.sequences} /> : <DoneContent report={report} files={files} view={view} setView={setView} filter={filter} setFilter={setFilter} searchQuery={searchQuery} setSearchQuery={setSearchQuery} copied={copied} setCopied={setCopied} />}
  </div>
}

function Processing({ stages: stageList, active }: { stages: string[]; active: number }) { return <section className="processing-panel"><div className="processing-top"><div><span className="section-kicker">Live recovery pipeline</span><h2>Reconstructing evidence</h2></div><span className="processing-label"><LoaderCircle className="spin" size={15} /> Processing</span></div><div className="stage-track">{stageList.map((stage, index) => <div className={`stage ${index < active ? 'complete' : index === active ? 'active' : ''}`} key={stage}><div className="stage-node">{index < active ? <CheckCircle2 size={15} /> : index === active ? <LoaderCircle className="spin" size={15} /> : index + 1}</div><span>{stage}</span></div>)}</div><div className="progress-line"><span style={{ width: `${Math.max(8, (active / (stageList.length - 1)) * 100)}%` }} /></div><p className="muted-note">Substep telemetry is simulated from elapsed processing time. Granular SSE events are planned for the next backend iteration.</p></section> }

function DoneContent({ report, files, view, setView, filter, setFilter, searchQuery, setSearchQuery, copied, setCopied }: { report: Report; files: Report['recovered_files']; view: 'table' | 'grid'; setView: (view: 'table' | 'grid') => void; filter: string; setFilter: (value: string) => void; searchQuery: string; setSearchQuery: (value: string) => void; copied: string; setCopied: (value: string) => void }) {
  const stats = report.recovery_stats
  const rate = stats.recovery_rate.recovery_rate_pct ?? 0
  const rejectionReasons = stats.rejected_frames_by_reason ?? stats.invalid_by_rejection_reason
  const topRejection = Object.entries(rejectionReasons).sort(([, left], [, right]) => right - left)[0]
  const copy = async (value: string) => { await navigator.clipboard?.writeText(value); setCopied(value); window.setTimeout(() => setCopied(''), 1200) }
  return <>
    <div className="stat-grid"><Stat icon={<ShieldCheck />} label="Recovery rate" value={`${rate}%`} detail={`${stats.valid_frames} of ${stats.recovery_rate.expected_total_frames ?? stats.total_frames_scanned} frames · ${stats.recovery_rate.recovery_rate_basis}`} tone="blue" /><Stat icon={<FileVideo />} label="Frames recovered" value={stats.valid_frames.toLocaleString()} detail={`${stats.sequences_found} sequence${stats.sequences_found === 1 ? '' : 's'} reconstructed`} tone="green" /><Stat icon={<AlertTriangle />} label="Rejected frames" value={stats.invalid_frames.toLocaleString()} detail={topRejection ? `${topRejection[0]} (${topRejection[1]})` : 'None'} tone="red" /><Stat icon={<Clock3 />} label="Gaps detected" value={stats.gaps_detected.toLocaleString()} detail="Temporal discontinuities" tone="amber" /></div><div className="rejection-breakdown">{Object.entries(rejectionReasons).map(([reason, count]) => <span key={reason}><b>{reason}</b> {count}</span>)}</div>
    <section className="evidence-section"><div className="section-toolbar"><div><span className="section-kicker">Recovered evidence</span><h2>Video reconstruction output</h2></div><div className="toolbar-actions"><div className="search-box"><Search size={15} /><input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search camera, vendor, time…" aria-label="Search evidence metadata" /></div><select value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Filter recovered files"><option value="all">All artifacts</option><option value="demo">Playable demo</option><option value="raw">Raw fallback</option></select><div className="view-toggle"><button className={view === 'table' ? 'selected' : ''} onClick={() => setView('table')} title="Table view"><List size={16} /></button><button className={view === 'grid' ? 'selected' : ''} onClick={() => setView('grid')} title="Grid view"><Grid2X2 size={16} /></button></div></div></div><p className="search-note">Metadata search matches camera/channel, vendor, filename, and simple time expressions. It does not claim OCR or AI interpretation.</p>{view === 'table' ? <FileTable files={files} copied={copied} onCopy={copy} /> : <div className="clip-grid">{files.map((file) => <ClipCard key={file.filename} file={file} />)}</div>}{files.length === 0 && <div className="empty-state">No artifacts match this search.</div>}</section>
  </>
}
function Stat({ icon, label, value, detail, tone }: { icon: ReactNode; label: string; value: string; detail: string; tone: string }) { return <div className="stat-card"><div className={`stat-icon ${tone}`}>{icon}</div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div> }
function FileTable({ files, copied, onCopy }: { files: Report['recovered_files']; copied: string; onCopy: (value: string) => void }) { return <div className="table-wrap"><table><thead><tr><th>Artifact</th><th>Timestamp</th><th>Frames</th><th>Size</th><th>SHA-256</th><th /></tr></thead><tbody>{files.map((file) => <tr key={file.filename}><td><div className="file-name"><FileVideo size={17} /><span>{file.filename}<small>{file.is_demo ? 'Playable MP4' : 'Raw recovery fallback'}</small></span></div></td><td className="mono">{new Date(file.start_ts).toLocaleString()}</td><td>{file.frame_count}</td><td>{(file.size_bytes / 1024).toFixed(1)} KB</td><td><button className="hash-button mono" onClick={() => onCopy(file.sha256)} title="Copy SHA-256">{copied === file.sha256 ? 'Copied' : `${file.sha256.slice(0, 12)}…`} <Copy size={13} /></button></td><td><a className="icon-button" href={fileUrl((file.path.match(/[\\/]([a-f0-9]{32})[\\/]/)?.[1] ?? ''), file.filename)} download title="Download"><Download size={16} /></a></td></tr>)}</tbody></table></div> }
function ClipCard({ file }: { file: RecoveredFile }) { const jobId = file.path.match(/[\\/]([a-f0-9]{32})[\\/]/)?.[1] ?? ''; const [events, setEvents] = useState<MotionEvent[] | null>(null); const [motionError, setMotionError] = useState(''); const runMotion = async () => { try { const result = await analyzeMotion(jobId, file.filename); setEvents(result.motion_events); setMotionError('') } catch (error) { setMotionError(error instanceof Error ? error.message : 'Motion detection unavailable') } }; return <article className="clip-card"><div className="video-frame">{file.filename.endsWith('.mp4') ? <video controls preload="metadata" src={fileUrl(jobId, file.filename)} /> : <div className="raw-preview"><FileVideo size={28} /><span>Raw stream artifact</span></div>}<span className="clip-status" /></div><div className="clip-info"><strong>{file.filename}</strong><span>{new Date(file.start_ts).toLocaleString()} · {file.frame_count} frames</span>{file.filename.endsWith('.mp4') && <button className="motion-button" onClick={() => void runMotion()}>Motion detection</button>}{events && <small className="motion-result">{events.length} motion event{events.length === 1 ? '' : 's'} · frame difference</small>}{motionError && <small className="motion-error">{motionError}</small>}</div></article> }

function Timeline({ sequences }: { sequences: Report['sequences'] }) {
  if (!sequences.length) return <section className="timeline-panel"><div className="empty-state">No recovered sequences available.</div></section>
  const starts = sequences.map((sequence) => new Date(sequence.start_ts).getTime())
  const ends = sequences.map((sequence) => new Date(sequence.end_ts).getTime())
  const min = Math.min(...starts)
  const max = Math.max(...ends)
  const span = Math.max(max - min, 1)
  return <section className="timeline-panel"><div className="section-toolbar"><div><span className="section-kicker">Temporal reconstruction</span><h2>Sequence timeline</h2></div><span className="record-count">{sequences.length} sequence{sequences.length === 1 ? '' : 's'}</span></div><div className="timeline-axis"><span>{new Date(min).toLocaleTimeString()}</span><span>{new Date(max).toLocaleTimeString()}</span></div>{sequences.map((sequence) => { const left = ((new Date(sequence.start_ts).getTime() - min) / span) * 100; const width = Math.max(((new Date(sequence.end_ts).getTime() - new Date(sequence.start_ts).getTime()) / span) * 100, 4); return <div className="timeline-row" key={`${sequence.start_ts}-${sequence.channel_id}`}><span className="timeline-label">CH{sequence.channel_id + 1}</span><div className="timeline-track"><div className={`timeline-sequence ${sequence.gap_before ? 'after-gap' : ''}`} style={{ left: `${left}%`, width: `${width}%` }} title={`${sequence.start_ts} - ${sequence.end_ts} · ${sequence.frame_count} frames`}>{sequence.frame_count} frames</div></div></div>})}<p className="muted-note">Green bars are recovered sequences. Dashed starts indicate a detected temporal or frame-number gap before that sequence.</p></section>
}
