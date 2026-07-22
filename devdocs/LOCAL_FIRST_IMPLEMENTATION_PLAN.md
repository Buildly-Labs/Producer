# Splice Local-First Implementation Plan

**Version**: 2.0  
**Updated**: July 21, 2026  
**Status**: Ready for Phase 1 Update

## Objective

Transform Splice from cloud-only to **local-first, cloud-managed**:
- Users keep large media files on their local computer, external drive, or network storage
- Cloud stores lightweight project metadata, edit decisions, transcripts, and collaboration data
- Optional Producer Local Media Engine runs securely on localhost for proxy generation and rendering
- No requirement to upload full source media

---

## Key Changes from Phase 1

### What Was Built
✅ 19 domain models for non-destructive editing  
✅ Revision-based optimistic concurrency  
✅ Database schema with 25+ indexes  

### What Must Change

| Component | Phase 1 Assumption | Phase 2 Reality |
|-----------|-------------------|-----------------|
| **MediaAsset** | Cloud storage | Reference to asset anywhere (local/cloud/URL) |
| **Storage** | All in cloud | Cloud stores metadata only |
| **Paths** | Cloud can access any file | Cloud never sees absolute paths |
| **Rendering** | Server-side workers | Local engine preferred, cloud fallback |
| **Proxies** | Generated and stored in cloud | Generated locally, optionally uploaded |
| **File Relinking** | N/A | Fingerprints enable smart relinking |
| **Offline Support** | Not possible | Project readable, renders blocked |

### New Models (Phase 2)

```
MediaAsset (updated)        → Stores metadata only (filename, size, codec, fingerprint)
MediaLocation (new)         → Where asset lives (local, cloud, URL, etc.)
MediaFingerprint (new)      → For relinking without uploading
LocalEngineInstallation     → Registration record for a local machine
LocalEngineSession          → Active connection with browser
LocalAssetRegistry          → LOCAL-ONLY mapping of cloud UUIDs to local paths
LocalProcessingJob          → Job queued for local engine
RenderPlan                  → Path-free rendering blueprint
```

---

## Implementation Phases (Revised)

### Phase 1.5: Update Existing Models (This Week)

**Goal**: Adapt Phase 1 models to support local storage.

**Changes**:
1. Update `MediaAsset` model
   - ✅ Remove cloud-storage assumptions
   - Add `source_mode` (local_only, local_with_proxy, cloud_original, etc.)
   - Add fingerprint fields
   - Never store file paths

2. Create migration `0002_local_first_models.py`
   - Add `MediaLocation` table
   - Add `MediaFingerprint` table
   - Add `LocalEngineInstallation` table
   - Add `LocalEngineSession` table
   - Add `LocalProcessingJob` table
   - Add `RenderPlan` table
   - Add fields to `EditorProject` (processing_mode, render_location)

3. Create services
   - `splice/services/local_engine.py` - Engine registration, job queue
   - `splice/services/media.py` - Asset registration, fingerprinting, relinking
   - `splice/services/render_plan.py` - Path-free render blueprints

4. Create views
   - `LocalEngineRegisterView` - One-time registration
   - `LocalEngineSessionView` - Create/destroy sessions
   - `LocalEngineJobsView` - Queue management
   - `MediaRegisterLocalView` - Register file without upload
   - `MediaRelinkView` - Relink after moving file

**Est**: 1.5 weeks  
**Tests**: Model, service, API endpoint tests

---

### Phase 2: Browser Local-File Mode (2-3 Weeks After 1.5)

**Goal**: Users can select local files, edit project metadata, preview without upload.

**Features**:
- File input picker (File API)
- IndexedDB for file handles (persist across page reloads)
- Local metadata display (no upload required)
- HTML5 video/audio playback of local proxy
- Saves project to cloud (metadata only)
- Reconnect files after reload (if permissions remain valid)

**Deliverables**:
- ✅ Frontend: File picker UI
- ✅ Frontend: IndexedDB storage
- ✅ Frontend: Local file playback
- ✅ Backend: Media registration API
- ✅ Tests: File selection, metadata storage, offline project open
- ✅ Documentation: Browser capabilities & limitations

**Not in Phase 2**:
- No transcription (complex, requires server/ML)
- No waveform generation (requires encoding)
- No proxy creation (requires encoding)
- No final render (requires multi-track mixing)

**Upgrade path**: "Export" → "Install local engine" → Full-quality render

---

### Phase 3: Local Engine Registration & Connection (Parallel with 2)

**Goal**: Secure registration and job-queue communication between browser and local engine.

**Deliverables**:
- ✅ Localhost detection (browser → 127.0.0.1:8765)
- ✅ One-time registration (key-based, cloud validates)
- ✅ Short-lived token auth (expires 1 hour)
- ✅ Heartbeat mechanism (keep-alive)
- ✅ Job queue API (browser → server → local engine)
- ✅ Recovery after restart
- ✅ Origin validation
- ✅ Command validation schema
- ✅ Tests: Registration, auth, job flow, failure modes
- ✅ Documentation: Security model, setup

**Local Engine Skeleton** (separate repo):
- Language: Python (or Rust/Go for performance, TBD)
- Listens: localhost:8765 (HTTPS, self-signed OK)
- Auth: Token-based
- Commands: Strict schema (no arbitrary shell)
- Storage: Local registry (SQLite or JSON)
- Cleanup: Temp files per policy

---

### Phase 4: Local Media Preparation (2-3 Weeks)

**Goal**: Local engine generates proxies, waveforms, thumbnails without uploading source.

**Deliverables**:
- ✅ Local ffprobe integration
- ✅ Proxy video generation (H.264 720p)
- ✅ Proxy audio generation (AAC)
- ✅ Waveform extraction (peak samples → JSON)
- ✅ Thumbnail grid generation (WebP, 1 frame per 5s)
- ✅ Progress reporting
- ✅ Job cancellation
- ✅ Error recovery
- ✅ Tests: Proxy quality, waveform accuracy, thumbnail grid
- ✅ Documentation: Proxy specs, performance expectations

**Path-Free Job Payload**:
```json
{
  "job_type": "create_proxy_video",
  "asset_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "quality_preset": "720p"
}
```

Local engine: `uuid → local_file_path` (private mapping)

---

### Phase 5: Local Rendering (2-3 Weeks)

**Goal**: Local engine renders final video and audio from project revision.

**Deliverables**:
- ✅ Path-free render plan builder
  - Asset selections by UUID
  - Operations as JSON
  - Camera cuts by timeline
  - Sync offsets
  - Output format (preset, canvas, frame rate)
- ✅ Local FFmpeg command builder (no string concatenation)
  - Resolves UUIDs → local paths (private)
  - Constructs safe argument array
  - Multi-track video/audio mixing
- ✅ Video export (MP4, H.264, AAC)
- ✅ Audio-only export (MP3, WAV)
- ✅ Progress polling
- ✅ Error reporting
- ✅ Export result stored locally (no forced upload)
- ✅ Tests: Render determinism, audio sync, exports
- ✅ Documentation: Render plan format, FFmpeg safety

---

### Phase 6: Browser Editor UI (3-4 Weeks)

**Goal**: Full-featured timeline editor in browser.

**Deliverables**:
- ✅ Timeline component (virtualized for long episodes)
- ✅ Video tracks + audio tracks
- ✅ Clip display and selection
- ✅ Waveform display (from local/cloud proxy)
- ✅ Thumbnail strip (from local/cloud proxy)
- ✅ Transcript panel (sync with timeline)
- ✅ Camera preview grid (multicamera)
- ✅ Markers and notes
- ✅ Export controls
- ✅ Local engine status indicator
- ✅ "File offline" warnings
- ✅ "Locate File" relinking UI
- ✅ Undo/redo
- ✅ Tests: Timeline interaction, clip operations, offline state
- ✅ Documentation: UI conventions, keyboard shortcuts

---

### Phase 7: Advanced Local Features (2-3 Weeks, After 6)

**Goal**: Local processing for transcription, speaker detection, silence removal.

**Deliverables**:
- ✅ Local transcription (Whisper, faster-whisper, whisper.cpp)
- ✅ Speaker diarization (local model)
- ✅ Silence detection
- ✅ Camera-cut suggestions (from speaker activity)
- ✅ Privacy mode: transcript stays local, not synced to cloud
- ✅ Tests: Transcription accuracy, speaker detection, suggestions
- ✅ Documentation: Local ML models, privacy settings

---

### Phase 8: Hybrid Collaboration (2-3 Weeks, After 6)

**Goal**: Remote collaborators can review via proxies while original media stays local.

**Deliverables**:
- ✅ Optional proxy/waveform/thumbnail upload
- ✅ Remote collaborator views (read-only, via proxies)
- ✅ Comments and annotations
- ✅ Sync: Comments back to originating user
- ✅ Final render: Still happens locally from originals
- ✅ Tests: Proxy sharing, comment sync, final render
- ✅ Documentation: Collaboration workflow, privacy boundaries

---

### Phase 9: AI Providers (2-3 Weeks, After 8)

**Goal**: Selective media upload to AI providers (not full source).

**Deliverables**:
- ✅ Generic provider interface
- ✅ Selective clip export (user chooses range)
- ✅ Temporary clip rendering locally
- ✅ Only clip uploaded (not full source)
- ✅ Provider processing (external, optional)
- ✅ Result download and import
- ✅ Mock provider for testing
- ✅ Tests: Clip selection, upload, result import, cleanup
- ✅ Documentation: Provider integration, privacy

**Higgsfield Adapter**: Only after official API verification

---

## Data Model Summary

### Cloud Stores
```
Users, Organizations, Shows, Episodes
EditorProject, ProjectRevision
EditOperation (non-destructive)
VideoTrack, AudioTrack, Clip
CameraCut, MediaSyncPoint
Transcript, TranscriptSegment, TranscriptWord
Caption, Marker, Note
GraphicOverlay, SocialClip
ExportPreset, ExportedMedia
ProcessingJob (cloud location)
LocalProcessingJob (local location)
LocalEngineInstallation (registration record)
LocalEngineSession (connection record)

MediaAsset (metadata only - NO paths):
  - UUID (public, cloud-facing)
  - filename, file_size, duration, codec, frame_rate
  - fingerprint, fingerprint_method
  - source_mode (local_only, cloud_original, etc.)

MediaLocation (where asset lives):
  - location_type (local_device, cloud_original, remote_url, etc.)
  - availability (available, offline, needs_relink, etc.)
  - local_engine_id (which engine manages it)
  - local_location_id (opaque reference, not path)
  - cloud_path, remote_url (if applicable)

MediaFingerprint (for relinking):
  - asset_id, fingerprint_method, fingerprint_version
  - file_size, duration, codec_metadata
  - first_chunk_hash, last_chunk_hash, partial_hash, full_hash
```

### Local Device Stores (Private, Never Synced)
```
LocalAssetRegistry:
  - cloud_asset_uuid
  - local_asset_uuid
  - local_file_path (NEVER sent to cloud)
  - fingerprint
  - proxy_path, waveform_path, thumbnail_paths
  - availability, verified_at

Local proxy files, waveform files, thumbnail files
Local temporary render files
Local transcript (if privacy_mode=local)
Local transcription models, speaker models
Local configuration, credentials, secrets
```

---

## API Endpoints (Phase 1.5+)

### Local Engine Endpoints
```
POST   /local-engines/register/
       {engine_uuid, registration_key}
       → LocalEngineInstallation created

POST   /local-engines/{id}/connect/
       {browser_origin}
       → LocalEngineSession created, token returned

POST   /local-engines/{id}/heartbeat/
       → Update last_heartbeat, verify online

POST   /local-engines/{id}/jobs/
       → Return queued jobs for this engine

POST   /local-engines/{id}/jobs/{job_id}/accept/
       → Mark job accepted, local engine starting

POST   /local-engines/{id}/jobs/{job_id}/progress/
       {progress_percent, message}
       → Update job progress

POST   /local-engines/{id}/jobs/{job_id}/complete/
       {output_data}
       → Mark complete, save results

POST   /local-engines/{id}/jobs/{job_id}/fail/
       {error_code, error_message}
       → Mark failed, save error

POST   /local-engines/{id}/disconnect/
       → End session
```

### Media Endpoints (Updated)
```
POST   /editor/projects/{id}/media/register-local/
       {filename, file_size, duration_seconds, codec_*, fingerprint}
       → MediaAsset created (NO path stored)
       → MediaLocation created (source_mode=local_only, offline)

GET    /editor/media/{id}/
       → Return metadata (NO paths)

PATCH  /editor/media/{id}/availability/
       {availability}
       → Update offline/available state

POST   /editor/media/{id}/relink/
       {fingerprint}
       → Verify file match, update availability

POST   /editor/projects/{id}/media/upload-local/
       {asset_id, local_file: File}
       → For debugging only; production uses local engine
```

### Job Submission (Updated)
```
POST   /editor/projects/{id}/exports/
       {export_preset, render_location: "local_engine"|"cloud"|"browser"}
       → Create ExportedMedia
       → Create LocalProcessingJob (if render_location=local_engine)
       → Cloud validates before queueing

GET    /editor/exports/{id}/
       → Return export metadata + job status
       → NO path to local file returned
```

---

## Security Implementation

### Registration
```
1. User downloads Producer Local Media Engine
2. User opens Producer web
3. Click "Register Local Engine"
4. Producer generates one-time key (short TTL)
5. Local engine CLI: `engine-register --key ABC123`
6. Engine contacts: POST /local-engines/register/ with key
7. Cloud validates key, creates LocalEngineInstallation
8. Cloud returns engine_uuid (permanent, stored locally)
9. Browser stores engine_uuid for detection
```

### Per-Session Auth
```
1. Browser detects localhost:8765
2. Browser requests: POST /local-engines/{uuid}/connect/
3. Cloud generates token (expires 1 hour)
4. Returns token via secure channel (browser ↔ cloud)
5. Browser sends token with job submitting
6. Local engine verifies token with cloud per request
7. Token expires; next session requires new token
```

### Command Validation
```
SCHEMA (not strings):
  probe_media(asset_uuid, quality_preset)
  create_proxy(asset_uuid, proxy_type, quality)
  generate_waveform(asset_uuid)
  render_video(project_uuid, revision, preset)

Local engine CONSTRUCTS FFmpeg args:
  ffmpeg -i {local_path_resolved_privately} \
         -vf scale=1280:720 \
         -c:v libx264 -crf 23 \
         -c:a aac -b:a 128k \
         output.mp4

Never accepts:
  POST /jobs/shell/ {cmd: "..."}  ← REJECTED
  POST /jobs/render/ {ffmpeg: "-i ... "}  ← REJECTED
```

---

## File Structure

```
Producer/
├── splice/
│   ├── models.py (UPDATED)
│   │   ├─ MediaAsset (updated: no paths)
│   │   ├─ MediaLocation (new)
│   │   ├─ MediaFingerprint (new)
│   │   ├─ LocalEngineInstallation (new)
│   │   ├─ LocalEngineSession (new)
│   │   ├─ LocalProcessingJob (new)
│   │   ├─ RenderPlan (new)
│   │   └─ ... 19 existing models ...
│   │
│   ├── services/
│   │   ├─ local_engine.py (new)
│   │   │  ├─ LocalEngineManager class
│   │   │  ├─ register_installation()
│   │   │  ├─ create_session()
│   │   │  ├─ queue_job()
│   │   │  ├─ get_pending_jobs()
│   │   │  └─ update_job_status()
│   │   │
│   │   ├─ media.py (new)
│   │   │  ├─ register_local_media()
│   │   │  ├─ fingerprint_file()
│   │   │  ├─ relink_asset()
│   │   │  ├─ verify_fingerprint()
│   │   │  └─ update_availability()
│   │   │
│   │   ├─ render_plan.py (new)
│   │   │  ├─ build_render_plan()
│   │   │  ├─ validate_render_plan()
│   │   │  └─ resolve_assets_locally() ← local engine only
│   │   │
│   │   └─ ... existing services ...
│   │
│   ├── views.py (UPDATED)
│   │   ├─ LocalEngineRegisterView (new)
│   │   ├─ LocalEngineSessionView (new)
│   │   ├─ LocalEngineJobsView (new)
│   │   ├─ MediaRegisterLocalView (new)
│   │   ├─ MediaRelinkView (new)
│   │   └─ ... existing views ...
│   │
│   ├── migrations/
│   │   ├─ 0001_initial.py (existing)
│   │   └─ 0002_local_first_models.py (NEW)
│   │
│   ├── tests/ (new directory)
│   │   ├─ test_local_engine_registration.py
│   │   ├─ test_media_fingerprinting.py
│   │   ├─ test_local_jobs.py
│   │   ├─ test_render_plans.py
│   │   └─ ...
│   │
│   └── admin.py (UPDATED)
│       ├─ LocalEngineInstallation admin
│       ├─ LocalProcessingJob admin
│       └─ ...
│
├── producer-local-media-engine/
│   └─ (SEPARATE GITHUB REPO)
│       ├── main.py (or package.json + index.js)
│       ├── engine.py (or engine.ts)
│       ├── registry.py (or registry.ts)
│       ├── ffmpeg_builder.py
│       ├── auth.py
│       ├── server.py (localhost HTTPS)
│       ├── tests/
│       │   ├─ test_registration.py
│       │   ├─ test_job_queue.py
│       │   ├─ test_ffmpeg_safety.py
│       │   └─ ...
│       ├── requirements.txt / package.json
│       ├── README.md
│       └── setup.py / webpack.config.js
│
├── devdocs/
│   ├─ LOCAL_FIRST_ARCHITECTURE.md (this document)
│   ├─ LOCAL_FIRST_IMPLEMENTATION_PLAN.md (detailed phases)
│   ├─ LOCAL_ENGINE_SECURITY.md (new)
│   ├─ LOCAL_ENGINE_SETUP.md (new)
│   └─ ...
│
└── ...
```

---

## Glossary

| Term | Definition |
|------|------------|
| **Local-First** | User's original media stays on their device |
| **Cloud-Managed** | Edit decisions, metadata, collaboration stored in cloud |
| **Fingerprint** | Hash-based or metadata-based file identity for relinking |
| **Relink** | Reconnect cloud asset to local file (e.g., after user moves file) |
| **Proxy** | Lower-resolution copy for fast browser preview |
| **Render Plan** | Path-free blueprint for exporting (resolves UUIDs locally) |
| **Local Engine** | Optional localhost service for proxy generation and rendering |
| **Hybrid Mode** | Local media + optional cloud proxies for collaboration |
| **Immutable Source** | Original files never modified; edits are operations |

---

## Success Criteria

### Phase 1.5
- [ ] MediaAsset updated (no cloud assumptions)
- [ ] MediaLocation, MediaFingerprint models created
- [ ] LocalEngineInstallation, LocalProcessingJob models created
- [ ] Migration created and applied
- [ ] Services implemented (local_engine, media, render_plan)
- [ ] Views implemented (registration, job queue, media register)
- [ ] Tests pass (>80% coverage)
- [ ] Documentation updated

### Phase 2
- [ ] User can select local file without uploading
- [ ] Cloud stores metadata + fingerprint (not path)
- [ ] Project reopens with asset offline (read-only)
- [ ] Relinking UI and workflow works
- [ ] Browser preview plays local file (if allowed)
- [ ] Tests pass

### Phases 3+
- [ ] Local engine registers and authenticates securely
- [ ] Proxies generated locally (no upload required)
- [ ] Rendering happens locally (optional cloud fallback)
- [ ] Full editor UI works
- [ ] Tests cover critical workflows
- [ ] Documentation complete

---

## Timeline Estimate

| Phase | Duration | Start | Finish |
|-------|----------|-------|--------|
| 1.5 | 1.5 weeks | Week 1 | Week 2.5 |
| 2 | 2-3 weeks | Week 2.5 | Week 5 |
| 3 | 2-3 weeks | Week 2.5 (parallel) | Week 5 |
| 4 | 2-3 weeks | Week 5 | Week 8 |
| 5 | 2-3 weeks | Week 8 | Week 11 |
| 6 | 3-4 weeks | Week 11 | Week 15 |
| 7 | 2-3 weeks | Week 15 | Week 18 |
| 8 | 2-3 weeks | Week 15 (parallel) | Week 18 |
| 9 | 2-3 weeks | Week 18 | Week 21 |

**Total**: ~21 weeks (5 months) from Phase 1.5 to production-ready local-first editor.

---

## Rollout Strategy

1. **Phase 1.5**: Internal testing only
2. **Phase 2**: Beta: Browser-only local-file selection (no local engine required)
3. **Phase 3-4**: Beta: Local engine available for testing
4. **Phase 5**: Early access: Local export working
5. **Phase 6-8**: General availability with full editor
6. **Phase 9**: GA with AI provider support (optional)

---

## Open Questions for Stakeholders

1. **Local engine language**: Python (simplicity) or Rust/Go (performance)?
2. **Transcription model**: Whisper, faster-whisper, or Hugging Face?
3. **Browser requirement**: Chrome/Firefox only or Safari support needed?
4. **Relinking strategy**: Smart fingerprinting or user manual selection?
5. **Hybrid collaboration**: Initial scope (read-only via proxies) sufficient?
6. **AI provider**: Higgsfield only or generic interface?
7. **Cloud fallback**: Optional or required?
8. **File size limits**: Browser mode max file size? Network limits?

---

## References

- Local-First Architecture: `devdocs/LOCAL_FIRST_ARCHITECTURE.md`
- Original Phase 1: `devdocs/SPLICE_IMPLEMENTATION_PHASE1.md`
- Security Model: `devdocs/LOCAL_ENGINE_SECURITY.md` (to write)
- Setup Guide: `devdocs/LOCAL_ENGINE_SETUP.md` (to write)

