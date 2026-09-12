import { ChangeEvent, DragEvent, useRef, useState } from 'react'
import { ArrowUpFromLine, Database, FileImage, ShieldCheck, Sparkles } from 'lucide-react'
import { createDemoJob, uploadImage } from '../lib/api'

interface UploadProps { onJobCreated: (jobId: string) => void }

export function Upload({ onJobCreated }: UploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [selected, setSelected] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submitFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.img')) { setError('Select a .img disk image.'); return }
    setSelected(file); setError('')
  }

  const upload = async () => {
    if (!selected) return
    setBusy(true); setError('')
    try { onJobCreated((await uploadImage(selected)).job_id) }
    catch (err) { setError(err instanceof Error ? err.message : 'Upload failed.') }
    finally { setBusy(false) }
  }

  const demo = async (vendor: 'hikvision' | 'dahua') => {
    setBusy(true); setError('')
    try { onJobCreated((await createDemoJob(vendor)).job_id) }
    catch (err) { setError(err instanceof Error ? err.message : 'Demo generation failed.') }
    finally { setBusy(false) }
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault(); setDragging(false)
    const file = event.dataTransfer.files[0]
    if (file) void submitFile(file)
  }
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) void submitFile(file)
  }

  return <div className="page upload-page">
    <div className="eyebrow"><Sparkles size={15} /> Evidence recovery workspace</div>
    <h1>Recover what the drive still remembers.</h1>
    <p className="lede">DeepTrace reconstructs fragmented DVR footage, validates each frame, and preserves an auditable trail for review.</p>

    <section className="demo-panel">
      <div className="panel-heading"><div><span className="section-kicker">Fastest path</span><h2>Run a controlled evidence demo</h2></div><span className="live-dot">READY</span></div>
      <p>Generate a 200-frame forensic image with realistic corruption and fragmentation. No file preparation required.</p>
      <div className="demo-actions">
        <button className="demo-button" disabled={busy} onClick={() => void demo('hikvision')}><span className="vendor-mark hik">H</span><span><strong>Hikvision dataset</strong><small>Signature + frame integrity</small></span><ArrowUpFromLine size={17} /></button>
        <button className="demo-button" disabled={busy} onClick={() => void demo('dahua')}><span className="vendor-mark dah">D</span><span><strong>Dahua dataset</strong><small>Dual-signature validation</small></span><ArrowUpFromLine size={17} /></button>
      </div>
    </section>

    <div className="or-rule"><span>OR ANALYZE A SOURCE IMAGE</span></div>
    <section className={`dropzone ${dragging ? 'dragging' : ''}`} onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={handleDrop} onClick={() => inputRef.current?.click()}>
      <input ref={inputRef} type="file" accept=".img" hidden onChange={handleChange} />
      <div className="drop-icon"><FileImage size={25} /></div>
      <strong>{selected ? selected.name : 'Drop a disk image here'}</strong>
      <span>{selected ? `${(selected.size / 1024 / 1024).toFixed(1)} MB ready to upload` : 'or click to browse · .img files only'}</span>
      {selected && <button className="primary-button upload-button" disabled={busy} onClick={(event) => { event.stopPropagation(); void upload() }}>{busy ? 'Uploading…' : 'Start recovery'}</button>}
    </section>
    {error && <div className="error-banner">{error}</div>}
    <div className="trust-row"><ShieldCheck size={16} /> Read-only analysis · Original source is never modified <span /> <Database size={16} /> Local processing pipeline</div>
  </div>
}
