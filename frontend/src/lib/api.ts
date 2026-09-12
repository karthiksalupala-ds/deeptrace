export type JobStatus = 'queued' | 'processing' | 'done' | 'failed'

export interface Job {
  job_id: string
  filename: string
  status: JobStatus
  created_at: string
  report: Report | null
  error: string | null
}

export interface Report {
  tool: string
  generated_at: string
  disk_metadata: {
    filename: string
    path: string
    size_bytes: number
    md5: string
    sha256: string
    processed_at: string
  }
  device_identification: {
    vendor_id: string
    vendor_name: string
    signature_found_at_offset: number | null
    fully_implemented: boolean
    detection_confidence: string
  }
  recovery_stats: {
    total_frames_scanned: number
    valid_frames: number
    invalid_frames: number
    invalid_by_rejection_reason: Record<string, number>
    rejected_frames_by_reason: Record<string, number>
    frames_in_sequences: number
    frames_dropped_noise: number
    sequences_found: number
    gaps_detected: number
    recovery_rate: {
      recovery_rate_pct?: number
      recovery_rate_basis: 'ground_truth' | 'scanned_only'
      actual_valid_recovered?: number
      expected_total_frames?: number
      expected_corrupted_frames?: number
      note: string
    }
  }
  recovered_files: RecoveredFile[]
  sequences: Sequence[]
  chain_of_custody: {
    source_image_sha256: string
    acquired_by: string
    acquired_at: string
    tool: string
    hash_algorithms: string[]
    processing_note: string
    prev_entry_hash: string | null
  }
  section_65b_certificate?: Record<string, string>
}

export interface Sequence {
  vendor_id: string
  channel_id: number
  frame_count: number
  start_ts: string
  end_ts: string
  gap_count: number
  gap_before: boolean
}

export interface RecoveredFile {
  filename: string
  path: string
  size_bytes: number
  md5: string
  sha256: string
  frame_count: number
  duration_seconds: number
  vendor_id: string
  channel_id: number
  start_ts: string
  end_ts: string
  is_demo: boolean
  is_raw_fallback: boolean
}

const request = async <T>(path: string, options?: RequestInit): Promise<T> => {
  const response = await fetch(path, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const createDemoJob = (vendor: 'hikvision' | 'dahua', scenario = 'fragmented') =>
  request<{ job_id: string }>('/api/demo/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ vendor, scenario }),
  })

export const uploadImage = (file: File) => {
  const body = new FormData()
  body.append('file', file)
  return request<{ job_id: string }>('/api/jobs', { method: 'POST', body })
}

export const getJob = (jobId: string) => request<Job>(`/api/jobs/${jobId}`)
export const getJobs = () => request<Job[]>('/api/jobs')
export const reportUrl = (jobId: string) => `/api/jobs/${jobId}/report.json`
export const pdfReportUrl = (jobId: string) => `/api/jobs/${jobId}/report.pdf`
export const fileUrl = (jobId: string, filename: string) => `/api/jobs/${jobId}/files/${encodeURIComponent(filename)}`
export const getJobFiles = (jobId: string) => request<{ files: string[] }>(`/api/jobs/${jobId}/files`)
export const searchEvidence = (jobId: string, query: string) =>
  request<{ query: string; match_method: string; files: RecoveredFile[] }>(
    `/api/jobs/${jobId}/search?q=${encodeURIComponent(query)}`,
  )
export const analyzeMotion = (jobId: string, filename: string) =>
  request<{ method: string; threshold: number; motion_events: MotionEvent[] }>(`/api/jobs/${jobId}/motion/${encodeURIComponent(filename)}`)

export interface MotionEvent { start_sec: number; end_sec: number; intensity: number }
