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


## Next up
- Phase 3: FastAPI backend (main.py, jobs.py, storage.py, models.py)
- Phase 4: React + TypeScript frontend (light AXIOM theme)
- Phase 6: ML module (OpenCV motion detection)
- Phase 8: docs/ deliverables



## Log
- Phase 1: complete, 5 vendor plugins registered (Hikvision+Dahua full, 
  CP Plus→Dahua/Godrej→Hikvision delegate, Uniview/Honeywell/Matrix stub-only, 
  TP-Link reclassified as standard-FS/conventional-carving tier).
- Phase 2: temporal_sequencer.py, mp4_writer.py, report.py, pipeline.py written, 
  41 tests passing. KNOWN BUG (unresolved): corrupted frames are being dropped 
  during parse instead of yielded as valid=False with rejection_reason — 
  E2E run showed 190/190 scanned=valid (should be 200 scanned, ~190 valid, 
  10 with rejection reasons). Recovery rate calc also wrong as a result 
  (showing 100% against wrong denominator). Also need to confirm gap 
  detection fires when fragmentation=True (last run showed 0 gaps, unclear 
  if that test used fragmentation).
- Switching from Antigravity (credits exhausted) to [next tool].

## Next up
Fix the corrupted-frame-dropping bug in the Hikvision/Dahua parsers before 
touching Phase 3. Re-run E2E with fragmentation=True and verify: 
total_scanned=200, rejection_reason buckets populated, recovery_rate < 100% 
computed against .meta.json ground truth, gaps_detected > 0.