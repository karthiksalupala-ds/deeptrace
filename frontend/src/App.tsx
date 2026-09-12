import { useEffect, useState } from 'react'
import { Activity, FileUp, FolderOpen, History, LayoutDashboard, Settings, ShieldCheck } from 'lucide-react'
import { getJob, getJobs, Job } from './lib/api'
import { Upload } from './pages/Upload'
import { JobView } from './pages/JobView'
import { Report } from './pages/Report'
import { History as HistoryPage } from './pages/History'

const nav = [{ id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard }, { id: 'upload', label: 'Upload evidence', icon: FileUp }, { id: 'history', label: 'Case history', icon: History }]
type View = 'dashboard' | 'upload' | 'history' | 'job' | 'report'

export function App() {
  const [view, setView] = useState<View>('upload')
  const [jobId, setJobId] = useState('')
  const [currentJob, setCurrentJob] = useState<Job | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const refreshJobs = () => void getJobs().then(setJobs).catch(() => undefined)
  useEffect(() => { refreshJobs() }, [])
  const openJob = (id: string) => { setJobId(id); setView('job'); void getJob(id).then(setCurrentJob).catch(() => undefined); refreshJobs() }
  const onJobCreated = (id: string) => { setJobId(id); setCurrentJob(null); setView('job'); refreshJobs() }
  return <div className="app-shell"><aside className="sidebar"><div className="brand"><div className="brand-icon"><ShieldCheck size={21} /></div><div><strong>DEEPTRACE</strong><small>FORENSIC RECOVERY</small></div></div><div className="side-label">WORKSPACE</div><nav>{nav.map(({ id, label, icon: Icon }) => <button key={id} className={view === id || (id === 'dashboard' && view === 'job') ? 'active' : ''} onClick={() => setView(id as View)}><Icon size={17} />{label}</button>)}</nav><div className="sidebar-bottom"><div className="system-status"><span className="online-dot" /><div><strong>Engine online</strong><small>Local API connected</small></div></div><button className="settings-button"><Settings size={16} /> Settings</button></div></aside><main className="main-content"><header className="topbar"><div className="breadcrumb"><span>Evidence workspace</span><b>/</b><strong>{view === 'upload' ? 'New analysis' : view === 'history' ? 'Case history' : currentJob?.filename || 'Case review'}</strong></div><div className="topbar-meta"><Activity size={15} /> Read-only mode <span className="avatar">OP</span></div></header>{view === 'upload' && <Upload onJobCreated={onJobCreated} />}{view === 'history' && <HistoryPage jobs={jobs} onOpen={openJob} />}{view === 'job' && jobId && <JobView jobId={jobId} onReport={(job) => { setCurrentJob(job); setView('report') }} />}{view === 'report' && currentJob?.report && <Report jobId={currentJob.job_id} report={currentJob.report} />}{view === 'dashboard' && <Dashboard jobs={jobs} onOpen={openJob} onUpload={() => setView('upload')} />}</main></div>
}

function Dashboard({ jobs, onOpen, onUpload }: { jobs: Job[]; onOpen: (id: string) => void; onUpload: () => void }) { const latest = jobs[0]; return <div className="page dashboard-page"><div className="eyebrow"><LayoutDashboard size={15} /> Operations overview</div><h1>Evidence workspace</h1><p className="lede">Monitor active recoveries and revisit processed cases.</p><div className="dashboard-grid"><div className="overview-card"><span className="section-kicker">Cases processed</span><strong>{jobs.length}</strong><small>Analysis jobs this session</small></div><div className="overview-card"><span className="section-kicker">Engine status</span><strong className="engine-ready"><span className="online-dot" /> Ready</strong><small>Hikvision + Dahua parsers available</small></div></div>{latest ? <button className="recent-case" onClick={() => onOpen(latest.job_id)}><FolderOpen size={19} /><span><strong>Continue latest case</strong><small>{latest.filename} · {latest.status}</small></span><span className="arrow-icon">↗</span></button> : <div className="empty-dashboard"><p>No evidence cases yet.</p><button className="primary-button" onClick={onUpload}>Start an analysis</button></div>}</div> }
