# Splice: Local-First Architecture Update

## Executive Summary

The Splice video editor is evolving from a cloud-only architecture to a **local-first, cloud-managed** system:

- **Local device**: Stores and processes original media files
- **Cloud**: Stores project state, edit decisions, metadata, collaboration
- **Local Media Engine**: Optional secure localhost service for proxy generation, waveform extraction, and rendering
- **Browser-only mode**: Optional lightweight local-file editing without server installation

This document outlines the architectural shift and revised implementation approach.

---

## Current State (Phase 1)

**What exists** (from previous implementation):
- 19 domain models for non-destructive editing
- Revision-based optimistic concurrency
- Edit operation tracking
- Project and clip management
- Database migrations applied

**What was cloud-only**:
- MediaAsset model assumed cloud storage
- Proxy generation planned for cloud workers
- All rendering assumed server-side
- No support for local file references

**What must change**:
1. MediaAsset → MediaAsset + MediaLocation (support multiple storage modes)
2. Add media fingerprinting for relinking
3. Add local asset registry model
4. Add local engine registration and sessions
5. Add local processing jobs
6. Separate local vs. cloud rendering paths
7. Update APIs to support local file registration without upload

---

## Three Operating Modes

### Mode 1: Local-Only (Browser + Optional Local Engine)

```
User's Computer
├─ Browser Tab
│  └─ Splice Editor UI
│     ├─ Select local video files
│     ├─ Register metadata (no upload)
│     ├─ Sync, trim, cut, edit
│     ├─ Send render job to local engine
│     └─ Save project to cloud (metadata only)
├─ Local Media Files
│  ├─ episode-host-camera.mov (immutable)
│  ├─ episode-guest-camera.mov (immutable)
│  └─ episode-microphone-lavalier.wav (immutable)
└─ Producer Local Media Engine (optional)
   ├─ Securely access approved files
   ├─ Generate proxies locally
   ├─ Generate waveforms locally
   ├─ Render final video locally
   └─ Return results to browser

Cloud (Producer)
└─ Project metadata only
   ├─ Edit operations
   ├─ Timeline structure
   ├─ Transcript
   ├─ Asset fingerprints
   └─ Render plans (no paths)
```

### Mode 2: Hybrid (Local Media + Cloud Proxies)

```
User's Computer
├─ Browser Tab (Splice Editor)
├─ Original Media Files (immutable, local)
└─ Local Engine (optional)

Cloud (Producer)
├─ Project metadata
├─ Proxies (optional upload)
├─ Waveforms (optional upload)
├─ Thumbnails (optional upload)
├─ Transcript
└─ For remote collaborators
```

### Mode 3: Cloud (Media Uploaded)

```
User's Computer
└─ Browser Tab (Splice Editor)

Cloud (Producer)
├─ Original media (uploaded)
├─ Project metadata
├─ Proxies
├─ Rendering
└─ Exports
```

---

## Architecture Components

### 1. MediaAsset + MediaLocation

Currently: `MediaAsset` assumes cloud storage.

**Change**: Separate storage from asset metadata.

```python
class MediaAsset(BaseModel):
    """Cloud record: metadata only, never contains local paths."""
    episode = ForeignKey(Episode)
    label = CharField()
    filename = CharField()
    file_size = BigIntegerField()
    duration_seconds = PositiveIntegerField()
    codec_video = CharField(null=True)
    codec_audio = CharField(null=True)
    frame_rate = PositiveIntegerField(null=True)
    sample_rate = PositiveIntegerField(null=True)
    channels = PositiveIntegerField(null=True)
    source_mode = CharField(choices=[
        'local_only',
        'local_with_cloud_proxy',
        'cloud_original',
        'cloud_proxy_only',
        'remote_url',
        'generated_media',
    ])
    # Fingerprint for relinking
    fingerprint_version = CharField()
    fingerprint_hash = CharField(null=True)  # Full hash
    fingerprint_partial = CharField(null=True)  # Partial hash
    fingerprint_size = BigIntegerField(null=True)
    fingerprint_duration = PositiveIntegerField(null=True)

class MediaLocation(BaseModel):
    """Where a media asset actually lives (local, S3, etc.)"""
    asset = ForeignKey(MediaAsset)
    location_type = CharField(choices=[
        'local_device',
        'local_network',
        'external_drive',
        'cloud_original',
        'cloud_proxy',
        'remote_url',
        'generated',
    ])
    availability = CharField(choices=[
        'available',
        'offline',
        'needs_relink',
        'proxy_available',
        'cloud_available',
        'processing',
        'invalid',
    ])
    
    # Cloud-facing fields only
    local_engine_id = UUIDField(null=True)  # Which engine manages it
    local_location_id = CharField(null=True)  # Opaque local reference
    cloud_path = CharField(null=True)  # S3 key, etc.
    remote_url = URLField(null=True)  # If from external source
    
    last_verified = DateTimeField(null=True)
    proxy_available = BooleanField(default=False)
    waveform_available = BooleanField(default=False)
    thumbnail_available = BooleanField(default=False)
```

### 2. Local Asset Registry (LocalEngineInstallation + LocalAssetRegistry)

Runs **locally** on user's machine. Never synced to cloud.

```python
class LocalEngineInstallation(BaseModel):
    """Registration of a local Media Engine instance."""
    organization = UUIDField()
    engine_name = CharField()
    engine_uuid = UUIDField(unique=True)
    registration_key = CharField()  # One-time setup key
    
    # Latest connection state
    last_heartbeat = DateTimeField(null=True)
    is_online = BooleanField(default=False)
    version = CharField()
    platform = CharField()  # Windows, macOS, Linux
    
    # Configuration
    auto_process_jobs = BooleanField(default=False)  # Auto-start work
    max_concurrent_jobs = PositiveIntegerField(default=1)
    proxy_quality = CharField(default='720p')
    
    class Meta:
        verbose_name = "Local Engine Installation"
        unique_together = [('organization', 'engine_uuid')]

class LocalAssetRegistry(BaseModel):
    """Private local mapping of cloud asset IDs to local files.
    Stored ONLY on local device, never synced to cloud."""
    # This model is conceptual; actual storage is local filesystem/SQLite
    
    # Cloud reference
    cloud_asset_uuid = UUIDField()
    local_asset_uuid = UUIDField()
    
    # Local file information (NEVER sent to cloud)
    local_file_path = CharField()  # /Users/name/Videos/...
    file_size = BigIntegerField()
    last_modified = DateTimeField()
    
    # For relinking
    fingerprint = CharField()
    partial_fingerprint = CharField()
    
    # Derived local data
    proxy_path = CharField(null=True)
    waveform_path = CharField(null=True)
    thumbnail_paths = JSONField(default=list)
    
    # State
    availability = CharField()
    verified_at = DateTimeField(null=True)
```

**Key principle**: Local registry is stored locally (filesystem, SQLite file, or similar). Cloud never sees absolute paths.

### 3. Media Fingerprinting

Support relinking without uploading files.

```python
class MediaFingerprint(BaseModel):
    """Fingerprint for matching local files to cloud assets."""
    asset = ForeignKey(MediaAsset)
    
    fingerprint_version = PositiveIntegerField()  # Evolution of algorithm
    fingerprint_method = CharField(choices=[
        'size_duration',
        'size_duration_codec',
        'partial_hash',
        'full_hash',
        'multi_method',
    ])
    
    # Fingerprint components
    file_size = BigIntegerField()
    duration_ms = PositiveIntegerField()
    codec_metadata = JSONField()
    first_chunk_hash = CharField(null=True)  # First 1MB
    last_chunk_hash = CharField(null=True)  # Last 1MB
    partial_hash = CharField(null=True)  # Hash of first 10%
    full_hash = CharField(null=True)  # Complete file hash
    
    created_at = DateTimeField(auto_now_add=True)
    verified_at = DateTimeField(null=True)

# Relinking workflow
# 1. Asset missing, marked as offline
# 2. User clicks "Locate File"
# 3. File picker opens
# 4. Selected file probed (ffprobe)
# 5. Fingerprint compared
# 6. If match: accept
# 7. If mismatch: warn, allow override
# 8. Update local registry
# 9. Asset marked available
```

### 4. Local Processing Jobs

Separate from cloud job queue.

```python
class LocalProcessingJob(BaseModel):
    """Job sent to or executed by local engine."""
    editor_project = ForeignKey(EditorProject)
    media_asset = ForeignKey(MediaAsset, null=True)
    
    local_engine = ForeignKey(LocalEngineInstallation)
    
    job_type = CharField(choices=[
        'probe_media',
        'create_proxy_video',
        'create_proxy_audio',
        'generate_waveform',
        'generate_thumbnails',
        'synchronize_media',
        'transcribe_asset',
        'render_video',
        'render_audio',
        'render_social_clip',
    ])
    
    status = CharField(choices=[
        'queued',
        'waiting_for_engine',
        'waiting_for_media',
        'processing',
        'completed',
        'failed',
        'cancelled',
    ])
    
    priority = PositiveIntegerField(default=5)
    progress_percent = PositiveIntegerField(default=0)
    
    # Job parameters (path-free)
    input_data = JSONField()  # References asset UUID, not local paths
    output_data = JSONField(null=True)
    
    error_code = CharField(null=True)
    error_message = TextField(blank=True)
    
    started_at = DateTimeField(null=True)
    completed_at = DateTimeField(null=True)
    
    # User acknowledgment
    user_confirmed = BooleanField(default=False)
    auto_start_approved = BooleanField(default=False)

class LocalEngineSession(BaseModel):
    """Active connection between browser and local engine."""
    local_engine = ForeignKey(LocalEngineInstallation)
    session_token = CharField()  # Short-lived credential
    browser_origin = CharField()  # Origin validation
    created_at = DateTimeField(auto_now_add=True)
    expires_at = DateTimeField()
    heartbeat_at = DateTimeField(auto_now=True)
```

### 5. Render Plans (Path-Free)

```python
class RenderPlan(BaseModel):
    """Deterministic plan for rendering a project."""
    project = ForeignKey(EditorProject)
    revision = PositiveIntegerField()
    
    # What to render (asset UUIDs, not paths)
    asset_selections = JSONField()  # [{'asset_uuid': '...', 'role': 'camera', ...}]
    
    # How to render (operations)
    operations = JSONField()  # Serialized edit operations
    camera_cuts = JSONField()  # Camera selection by time
    sync_offsets = JSONField()  # Asset sync offsets
    
    # Output format
    output_preset = CharField()  # 'full_podcast_1080p', etc.
    canvas_width = PositiveIntegerField()
    canvas_height = PositiveIntegerField()
    frame_rate = PositiveIntegerField()
    
    # Loudness
    loudness_preset = CharField()
    
    # No local file paths
    # Local engine will map UUIDs → local paths privately
    
    created_at = DateTimeField(auto_now_add=True)
```

---

## Data Flow

### Workflow: Local File Editing

```
1. USER ACTION: Select local file in browser
   └─ Browser: File input picker
   └─ Browser: Get File object (no upload)

2. BROWSER ACTION: Register asset
   POST /editor/projects/{id}/media/register-local/
   {
     filename: "guest-camera.mov",
     file_size: 5368709120,
     duration_seconds: 3600,
     codec_video: "h264",
   }
   └─ Server: Create MediaAsset (no path)
   └─ Server: Create MediaLocation (local_device, offline)
   └─ Server: Return asset UUID
   └─ Browser: Store local path in IndexedDB (never sent to server)

3. BROWSER ACTION: Connect to local engine
   POST /local-engines/register/
   {
     engine_uuid: "...",
     installation_key: "...",
   }
   └─ Server: Register LocalEngineInstallation
   └─ Server: Return connection token

4. BROWSER ACTION: Probe file
   POST /local-engines/{id}/probe/
   {
     cloud_asset_uuid: "...",
     local_file_path: "...",  // From IndexedDB
   }
   └─ Local engine: ffprobe
   └─ Local engine: Return metadata
   └─ Browser: Update UI with codec, duration, etc.
   └─ Browser: Store in IndexedDB
   └─ Local engine: Store in local registry

5. BROWSER ACTION: Create proxy
   POST /editor/projects/{id}/media/{asset_id}/process/
   {
     job_type: "create_proxy_video",
     processor: "local_engine",  // Prefer local
   }
   └─ Server: Create LocalProcessingJob
   └─ Server: Queue for local engine
   └─ Browser: Poll job status

6. LOCAL ENGINE ACTION: Generate proxy
   GET /local-engines/{id}/jobs/
   └─ Server: Return queued jobs
   └─ Local engine: Accept job
   └─ Local engine: Resolve asset UUID → local path (private)
   └─ Local engine: ffmpeg -i /Users/.../source.mov -vf scale=1280:720 /tmp/proxy.mp4
   └─ Local engine: POST /local-engines/{id}/jobs/{job_id}/complete/
   └─ Server: Update MediaProxy, MediaLocation
   └─ Browser: Display proxy in timeline

7. BROWSER ACTION: Edit timeline
   POST /editor/projects/{id}/operations/
   {
     operation_type: "trim_clip",
     payload: {clip_uuid: "...", source_start_ms: 10000, ...}
   }
   └─ Server: Create EditOperation
   └─ Server: Increment revision

8. BROWSER ACTION: Render video
   POST /editor/projects/{id}/exports/
   {
     export_preset: "full_podcast_1080p",
     render_location: "local_engine",
   }
   └─ Server: Build RenderPlan (path-free)
   └─ Server: Create ExportedMedia
   └─ Server: Queue LocalProcessingJob
   └─ Browser: Poll status

9. LOCAL ENGINE ACTION: Render
   GET /local-engines/{id}/jobs/
   └─ Server: Return render job with RenderPlan
   └─ Local engine: Accept job
   └─ Local engine: Resolve asset UUIDs → local paths (private)
   └─ Local engine: Build ffmpeg command internally
   └─ Local engine: ffmpeg -i /Users/.../host.mov -i /Users/.../guest.mov ... output.mp4
   └─ Local engine: POST progress updates
   └─ Local engine: POST /local-engines/{id}/jobs/{job_id}/complete/
   └─ Server: Update ExportedMedia
   └─ Browser: "Ready for download" button
   └─ Browser: Download from local storage (via file system)
```

---

## Security Model

### Local Engine Authentication

```
REGISTRATION (One-time setup):
1. User downloads Producer Local Media Engine
2. User opens Producer web app
3. User clicks "Register Local Engine"
4. Producer generates one-time registration key
5. Local engine prompts for key
6. Local engine contacts cloud with key + unique_id
7. Cloud validates, stores LocalEngineInstallation
8. Cloud returns permanent engine_uuid
9. Local engine stores locally, never cloud-stored again

ONGOING (Per-session):
1. User reopens Producer
2. Browser detects local engine (localhost:8765 check)
3. Browser requests connection token
4. Cloud generates short-lived token (expires 1 hour)
5. Browser gets token via secure channel
6. Browser can send jobs; local engine accepts with token
7. Token validated per request
8. Token expires; new one required for next session
```

### Command Validation

```
INVALID requests (rejected immediately):
- POST /local-engines/{id}/shell/ with arbitrary command
- POST /local-engines/{id}/render/ with raw ffmpeg args
- POST /local-engines/{id}/process/ with absolute paths
- POST /local-engines/{id}/process/ with parent directory traversal

VALID requests (processed):
- POST /local-engines/{id}/probe/
  {asset_uuid: "...", [no paths]}
- POST /local-engines/{id}/jobs/{id}/accept/
  [cloud provides path-free RenderPlan]
- Local engine ONLY sees asset UUIDs
- Local engine PRIVATELY resolves UUIDs to paths
```

### File Access

```
LOCAL ENGINE FILE ACCESS:
1. User-approved: File was selected by user in browser file picker
2. User-approved: Asset was registered by user in UI
3. Protected: Absolute paths never sent from cloud
4. Protected: Commands never concatenated from user input
5. Protected: FFmpeg arguments built from schema, not strings
6. Protected: Temporary files cleaned up per policy

CLOUD FILE ACCESS:
1. No direct access to user's local files
2. No storage of local paths
3. Only fingerprints, asset UUIDs, metadata
4. Optional: Accept deliberately uploaded proxies
5. Optional: Accept deliberately uploaded source (cloud mode)
```

---

## Browser-Local File Mode

Before users need to install the local engine, support browser-only local-file editing:

```javascript
// Browser capabilities
- File input picker (File API)
- Read file metadata (ffprobe-lite via WebAssembly? future)
- Create object URLs (play in HTML5 video)
- Store file handles (File System Access API, if available)
- Use Web Workers for parsing/metadata
- Store handles in IndexedDB (persist across page reloads)
- Reconnect to files if user approves re-granting permission

// Limitations
- No transcription (requires ML models)
- No waveform generation (complex)
- No proxy creation (encoding)
- No final render (complex multi-track)
- Browser is read-only, can't modify files
- Best for: Quick preview, clip selection, annotation

// Upgrade path
User clicks "Export" → "Upgrade to full quality"
→ Browser prompts to install Producer Local Media Engine
→ User installs, registers local engine
→ Browser re-submits render job
→ Local engine completes render
→ Returns high-quality file
```

---

## Implementation Phases (Revised)

### Phase 1: Local-First Models ✅ (Previous - update in progress)
- ✅ 19 core models exist
- ⬜ Update MediaAsset to not assume cloud storage
- ⬜ Add MediaLocation model
- ⬜ Add LocalEngineInstallation model
- ⬜ Add MediaFingerprint model
- ⬜ Add LocalProcessingJob model
- ⬜ Add LocalEngineSession model
- ⬜ Update EditorProject with mode selection

### Phase 2: Browser Local-File Mode
- Add File input + registration API
- Add IndexedDB for local file handles
- Add metadata display without upload
- Add tests

### Phase 3: Local Engine Registration & Connection
- Add localhost detection
- Add secure token-based auth
- Add heartbeat mechanism
- Add job queue communication
- Add tests

### Phase 4: Local Media Preparation
- Add local proxy generation
- Add local waveform generation
- Add local thumbnail generation
- Add local synchronization (waveform correlation)
- Add tests

### Phase 5: Local Rendering
- Add render-plan builder (path-free)
- Add local video export
- Add local audio export
- Add render progress
- Add tests

### Phase 6: Browser Editor & Hybrid Collaboration
- Add timeline UI
- Add optional proxy upload
- Add remote collaborator support
- Add transcript editing
- Add tests

### Phase 7: Advanced Local Features
- Add local transcription (Whisper)
- Add speaker detection
- Add silence detection
- Add camera-cut suggestions
- Add tests

### Phase 8: AI Providers
- Add generic provider interface
- Add selective clip upload
- Add mock provider
- Add Higgsfield adapter (post-verification)

---

## New API Endpoints

### Local Engine APIs
```
POST   /local-engines/register/          # Initial registration
POST   /local-engines/{id}/connect/      # Start session
POST   /local-engines/{id}/heartbeat/    # Keep-alive
POST   /local-engines/{id}/disconnect/   # End session

GET    /local-engines/                   # List installations
GET    /local-engines/{id}/jobs/         # Get queued jobs
POST   /local-engines/{id}/jobs/{job_id}/accept/
POST   /local-engines/{id}/jobs/{job_id}/progress/
POST   /local-engines/{id}/jobs/{job_id}/complete/
POST   /local-engines/{id}/jobs/{job_id}/fail/
POST   /local-engines/{id}/jobs/{job_id}/cancel/
```

### Media Registration APIs
```
POST   /editor/projects/{id}/media/register-local/
       {filename, file_size, duration_seconds, codec_*, ...}
       → Returns asset UUID (NO path stored)

POST   /editor/media/{id}/relink/
       {fingerprint, ...}
       → Update availability after user relocates file

PATCH  /editor/media/{id}/availability/
       {available, offline, needs_relink, ...}
```

### Job Submission
```
POST   /editor/projects/{id}/exports/
       {export_preset, render_location: "local_engine"|"cloud"|"browser"}
```

---

## File Organization

```
Producer/
├── splice/
│   ├── models.py (UPDATED)
│   │   ├─ MediaAsset (updated)
│   │   ├─ MediaLocation (new)
│   │   ├─ MediaFingerprint (new)
│   │   ├─ LocalEngineInstallation (new)
│   │   ├─ LocalEngineSession (new)
│   │   ├─ LocalAssetRegistry (conceptual local storage)
│   │   ├─ LocalProcessingJob (new)
│   │   ├─ RenderPlan (new, path-free)
│   │   └─ ... existing models ...
│   ├── services/
│   │   ├─ local_engine.py (new)
│   │   │  ├─ register_installation()
│   │   │  ├─ create_session()
│   │   │  ├─ queue_job()
│   │   │  ├─ get_pending_jobs()
│   │   │  └─ update_job_status()
│   │   ├─ media.py (new)
│   │   │  ├─ register_local_media()
│   │   │  ├─ relink_asset()
│   │   │  ├─ fingerprint_media()
│   │   │  └─ verify_fingerprint()
│   │   ├─ render_plan.py (new)
│   │   │  ├─ build_render_plan()
│   │   │  └─ resolve_assets()
│   │   └─ ...
│   ├── views.py (UPDATED)
│   │   ├─ LocalEngineRegisterView (new)
│   │   ├─ LocalEngineJobView (new)
│   │   ├─ MediaRegisterLocalView (new)
│   │   └─ ...
│   └── migrations/
│       └─ 0002_local_first_architecture.py (new)
├── devdocs/
│   ├── LOCAL_FIRST_ARCHITECTURE.md (this file)
│   └── LOCAL_ENGINE_SECURITY.md (new)
├── producer-local-media-engine/
│   └─ (Separate GitHub repo)
│       ├── main.py (or package.json)
│       ├── registry.py
│       ├── ffmpeg_builder.py
│       ├── local_server.py (localhost HTTPS)
│       └── tests/
└── ...
```

---

## Implementation Priorities

### Milestone 1: Metadata-Only Local File Support
- ✅ User selects local video file
- ✅ Cloud stores asset UUID, filename, fingerprint (no path)
- ✅ Cloud stores MediaLocation(source_mode='local_only', offline)
- ✅ Project can reopen with asset metadata
- ✅ UI shows "File offline" + "Locate File" action
- ⬜ RelinkingWorkflow
- ⬜ Tests
- **Est**: 1-2 weeks

### Milestone 2: Browser-Only Preview
- ⬜ IndexedDB for file handles
- ⬜ Local metadata display
- ⬜ HTML5 video playback
- ⬜ No upload required
- ⬜ Tests
- **Est**: 1-2 weeks

### Milestone 3: Local Engine Registration
- ⬜ Localhost detection
- ⬜ Secure token auth
- ⬜ Job queue communication
- ⬜ Recovery after restart
- ⬜ Tests
- **Est**: 2-3 weeks

### Milestone 4: Local Proxy Generation
- ⬜ Queue management
- ⬜ Path-free render plans
- ⬜ ffmpeg command builders
- ⬜ Progress reporting
- ⬜ Tests
- **Est**: 2-3 weeks

### Milestone 5: Local Export
- ⬜ Video export
- ⬜ Audio export
- ⬜ File handling
- ⬜ Tests
- **Est**: 1-2 weeks

---

## Security Checklist

- [ ] Local paths never stored in cloud database
- [ ] Local paths never included in API responses
- [ ] Render plans are path-free; local engine resolves privately
- [ ] FFmpeg arguments constructed from schema, never concatenated
- [ ] Local engine bound to loopback only (no network by default)
- [ ] Origin validation (browser → local engine)
- [ ] Token validation (short-lived, per-session)
- [ ] User confirmation required for deliberate uploads
- [ ] Absolute paths never accepted from cloud API
- [ ] File access restricted to user-approved selections
- [ ] Temporary files cleaned up per policy
- [ ] Audit logs for local engine operations
- [ ] Secrets encrypted in local registry
- [ ] No arbitrary shell commands
- [ ] No parent directory traversal in paths

---

## Known Limitations (Local-First MVP)

### Browser-Only Mode
- No transcription (requires models)
- No waveform generation
- No proxy creation
- No final render
- Limited to preview/annotation

### Local Engine Phase 1
- Single-user per installation
- No automatic workload distribution
- Basic error recovery only
- Manual relinking for moved files (future: smart matching)

### Hybrid Mode Phase 1
- Optional proxy upload only
- Remote collaborators see proxies only (no live co-editing)
- Final render must happen locally

### Cloud-Only Mode
- Still supported but not preferred
- User still required to upload source
- Renders happen on cloud workers

---

## Comparison: Old vs. New Architecture

| Aspect | Old (Cloud-Only) | New (Local-First) |
|--------|------------------|-------------------|
| Source storage | Cloud (upload required) | Local (immutable) |
| Proxy storage | Cloud | Local, optional cloud |
| Metadata | Cloud | Cloud (no paths) |
| Rendering | Cloud workers | Local engine (preferred) |
| Edit decisions | Cloud | Cloud |
| Availability offline | No | Yes (read-only) |
| Original file safety | Depends on upload | Always local & immutable |
| Collaboration | None planned | Hybrid (via proxies) |
| AI providers | Cloud uploads source | Local uploads clip only |
| File relinking | N/A | Supported via fingerprints |
| Browser requirements | High (full editor) | Low (metadata, preview) |

---

## Next Steps

1. **Phase 1 Update** (This week)
   - Update MediaAsset model (remove cloud-only assumptions)
   - Add MediaLocation, MediaFingerprint models
   - Add LocalEngineInstallation, LocalProcessingJob models
   - Create migration

2. **Phase 2 Design** (Next week)
   - Design local engine registration API
   - Design auth/token model
   - Identify localhost communication method

3. **Phase 3 Prototype** (Following week)
   - Build minimal local engine skeleton
   - Test registration flow
   - Test job queue

---

## References

- Current: `devdocs/splice-architecture.md`
- Current: `devdocs/SPLICE_IMPLEMENTATION_PHASE1.md`
- New: `devdocs/LOCAL_ENGINE_SECURITY.md` (to write)
- New: `devdocs/LOCAL_ENGINE_SETUP.md` (to write)
- New: Separate repo for Producer Local Media Engine

