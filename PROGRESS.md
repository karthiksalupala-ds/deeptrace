# DeepTrace — Progress

## Completed
- [2026-09-12] Repo scaffolded: all directories created
- [2026-09-12] OEM research completed (see docs/OEM_COMPARISON.md for findings)
- [2026-09-12] Phase 1: engine/base_parser.py — BaseVendorParser ABC; FrameRecord dataclass with valid + rejection_reason fields
- [2026-09-12] Phase 1: engine/registry.py — VendorRegistry + identify_vendor() dispatch; generate_image() plugin dispatcher
- [2026-09-12] Phase 1: engine/vendors/hikvision.py — full detect() + parse_frames() → Iterator[FrameRecord]; yields invalid frames with rejection_reason
- [2026-09-12] Phase 1: engine/vendors/dahua.py — full detect() + parse_frames() → Iterator[FrameRecord]; dual-sig validation; rejection reasons: header_magic_mismatch, checksum_mismatch, footer_magic_mismatch, footer_size_mismatch
- [2026-09-12] Phase 1: engine/vendors/cpplus.py — detect() + delegates parse_frames() to Dahua (Iterator chain)
- [2026-09-12] Phase 1: engine/vendors/godrej.py — detect() + delegates parse_frames() to Hikvision (Iterator chain)
- [2026-09-12] Phase 1: engine/vendors/uniview.py — detect()-only stub (independent FS, roadmap)
- [2026-09-12] Phase 1: engine/vendors/honeywell.py — detect()-only stub (MAXPRO format, roadmap)
- [2026-09-12] Phase 1: engine/vendors/tplink.py — detect()-only stub (VIGI series, roadmap)
- [2026-09-12] Phase 1: engine/vendors/matrix.py — detect()-only stub (COSEC platform, roadmap)
- [2026-09-12] Phase 1: engine/synthetic_image_gen.py — generate_hikvision_image() / generate_dahua_image() / generate_image() dispatcher + CLI (--manufacturer / --out / --frames / --corruption_rate); fragmentation via gap insertion
- [2026-09-12] Phase 1: Demo dataset: sample_data/hik_test1.img (200 frames, 10 corrupted, 20 gaps), sample_data/dahua_test1.img (200 frames, 10 corrupted, 20 gaps); 190 valid frames recovered per image
- [2026-09-12] Phase 1: 41 tests passing (parser round-trips, dual-sig rejection, datetime decode, registry routing, stub detection + NotImplementedError)
- [2026-09-12] Phase 2: engine/temporal_sequencer.py — adaptive gap detection with running median DT (slider window), sequencing stats, FrameSequence gap_before flag
- [2026-09-12] Phase 2: engine/mp4_writer.py — MP4 raw multiplexer with .raw fallback. Added lavfi-based write_demo_mp4() with burned-in TS and gracefully handling Windows ffmpeg drawtext errors
- [2026-09-12] Phase 2: engine/report.py — JSON forensic report builder: disk SHA-256, rejection_reason aggregation, ground-truth recovery rate via sidecar, and Section 65B stub
- [2026-09-12] Phase 2: engine/pipeline.py — single entrypoint (run_recovery) tying device ID, parser, sequencer, mp4 writer, and report builder. Supports --demo mode
- [2026-09-12] Phase 2: Test suite fully updated. Pipeline tested E2E with demo dataset (100% recovery rate vs ground truth sidecar). All 41 tests passing
- [2026-09-12] Parser recovery fix: Hikvision/Dahua now retain truncated magic candidates as invalid FrameRecords; fragmented 200-frame E2E runs report 200 scanned, 190 valid, 10 invalid, and 95% recovery against ground truth
- [2026-09-12] Phase 3: FastAPI backend implemented with in-memory jobs, local `backend/data/{job_id}` storage, upload/demo processing, status/report/file routes, CORS, validation, and API tests
- [2026-09-12] Phase 4: React + TypeScript dashboard implemented with AXIOM-style shell, upload/demo flow, polling job view, recovery stats, table/grid artifact views, report view, history, and typed API client
- [2026-09-12] Phase 5: reportlab PDF reports implemented with cover, recovery summary, evidence index, methodology appendix, and draft Section 65B content; PDF download route and frontend button wired
- [2026-09-12] Phase 6 Option A: transparent evidence search added for camera/channel, vendor, filename, and simple time expressions; backend route and frontend search box are wired


## Next up
- Phase 6: ML module (OpenCV motion detection)
- Phase 8: docs/ deliverables



## Log
- Phase 1: complete, 5 vendor plugins registered (Hikvision+Dahua full, 
  CP Plus→Dahua/Godrej→Hikvision delegate, Uniview/Honeywell/Matrix stub-only, 
  TP-Link reclassified as standard-FS/conventional-carving tier).
- Phase 2: temporal_sequencer.py, mp4_writer.py, report.py, pipeline.py written. 
  Parser accounting bug resolved: fragmented E2E runs now show 200 scanned, 
  190 valid, 10 invalid, and 95% recovery against the 200-frame sidecar 
  denominator. Dahua rejection buckets are checksum_mismatch/footer_size_mismatch; 
  Hikvision uses invalid_frame_size. Physical zero-filled fragmentation does not 
  itself create a temporal gap when timestamps and frame numbers remain continuous.
- Phase 3: FastAPI routes are available at `/api/jobs`, `/api/jobs/{job_id}`, 
  `/api/jobs/{job_id}/files/{filename}`, `/api/jobs/{job_id}/report.json`, 
  `/api/jobs`, and `/api/demo/generate`; `/api/v1` aliases remain for compatibility. 
  Local storage is zero-config under `backend/data`. Synthetic uploads may produce 
  `.raw` fallback artifacts because their fake H.264 payloads are not muxable; demo 
  jobs generate playable MP4s.
- Phase 4: Frontend runs at `http://127.0.0.1:5173/` via `npm --prefix frontend run dev`. 
  Uploads and Hikvision/Dahua demo buttons call the Phase 3 API, jobs poll every 1.5s, 
  and completed cases show recovery rate, valid/rejected frames, gaps, recovered 
  artifacts, playable demo clips, downloads, hashes, report metadata, chain of custody, 
  and case history. Pipeline substeps are elapsed-time UI simulation until SSE events 
  exist; the PDF export button is now wired to the Phase 5 report endpoint.
- Phase 5: `GET /api/jobs/{job_id}/report.pdf` renders a polished 5-page PDF on demand. 
  It includes the case cover, recovery metrics, hashed evidence index, methodology, 
  and a clearly marked Section 65B draft with blank examiner/signature fields. The 
  PDF and JSON report explicitly state that DeepTrace cannot legally issue or sign 
  the certificate; human review and signature are required. The frontend report page 
  downloads the PDF directly.
- Phase 6 Option A: `GET /api/jobs/{job_id}/search?q=...` searches recovered-file 
  metadata with explainable keyword, camera/channel, vendor, and time-expression 
  matching. The recovered-evidence view now includes a debounced search field. This 
  is intentionally not OCR, an LLM, or a claim of visual understanding; it matches 
  indexed report fields and is explainable in one sentence to a judge.
- Switching from Antigravity (credits exhausted) to [next tool].

## Next up
Proceed to Phase 8. Phase 6 Option A validation is complete: Python tests pass (`48 
passed`), the frontend TypeScript/Vite build passes, and the search route is covered 
for a query such as `show camera 1 after 9am`. Options B and C remain intentionally 
unimplemented because multi-image graph correlation and real tamper/deepfake models 
would need additional evidence and validation.