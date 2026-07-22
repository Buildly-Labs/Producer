# Splice Video Podcast Editor - Architecture & Implementation Plan

## Phase 0: Repository Assessment

### Current Architecture Summary

**Repository**: Buildly Producer (Django + Django REST Framework)
- **Framework**: Django 5.1+ with DRF
- **Database**: PostgreSQL (prod), SQLite (dev)
- **Existing Models**:
  - `Show`: Podcast series with branding
  - `Episode`: Single episode with status workflow
  - `MediaAsset`: Video/audio files with ingestion tracking
  - `Transcript`: Episode transcripts with versions
  - `ClipMoment`: Marked moments with timestamps
  - `Segment`, `SegmentTemplate`: Show segments for recording
  - `Speaker`, `Sponsor`, `Guest`: Content relationships

- **Existing Services**:
  - `production_ledger/services/ai.py`: AI integrations (generation, etc.)
  - `production_ledger/services/exports.py`: Media export handling
  - Audit fields (`created_by`, `updated_by`, timestamps)
  - Organization scoping (UUID-based multi-tenancy)
  - Role-based permissions (RBAC)

- **API Structure**:
  - REST API with DRF ViewSets
  - Token authentication via `rest_framework.authtoken`
  - CORS enabled
  - API documentation via drf-yasg

- **Frontend**:
  - Django templates (server-rendered)
  - Tailwind CSS for styling
  - No existing SPA frontend
  - HTML/JavaScript for interactive features (second-screen, control room)

### Extension Points for Splice

1. **Models**: Add video editor domain models as separate app (`splice`)
2. **Services**: Extend `services/` with media proxy, waveform, and render planning
3. **API**: Add `/splice/` API routes alongside `/production_ledger/`
4. **Frontend**: Add dedicated Splice editor views; consider SPA later
5. **Jobs**: Implement async processing (media prep, rendering)
6. **Permissions**: Reuse existing RBAC; admin-only for Splice initially

### Design Decisions

**Why a separate `splice` Django app**:
- Keeps video-editor domain isolated
- Can be feature-flagged or deployed independently
- Doesn't disrupt existing Episode/Show workflows
- Scales independently

**Why browser-side preview uses proxies**:
- Full-resolution video in browser is impractical (50-60 min @ 1080p+ = GB)
- Proxy generation happens once; preview uses H.264 720p or lower
- Final render uses original sources (highest quality)

**Why edit operations are non-destructive**:
- Undo/redo across sessions
- Reproducible renders
- Revisions as append-only history
- User can always recover intermediate states

## Phase 1: Video Editor Domain Models

### New Models (Splice App)

```python
# Core editor project
class EditorProject(BaseModel):
    episode = ForeignKey(Episode)
    frame_rate = IntegerField(default=30)
    canvas_width = IntegerField(default=1920)
    canvas_height = IntegerField(default=1080)
    timeline_duration_ms = IntegerField()
    aspect_ratio = CharField(choices=[...])
    autosave_enabled = BooleanField(default=True)
    current_revision = IntegerField(default=0)

# Immutable revision snapshots
class ProjectRevision(BaseModel):
    project = ForeignKey(EditorProject)
    revision_number = IntegerField()
    snapshot = JSONField()  # Compressed state for undo/redo
    operation_count = IntegerField()
    created_at = DateTimeField(auto_now_add=True)

# Timeline tracks
class VideoTrack(BaseModel):
    project = ForeignKey(EditorProject)
    index = IntegerField()
    name = CharField(max_length=255)
    enabled = BooleanField(default=True)
    visible = BooleanField(default=True)

class AudioTrack(BaseModel):
    project = ForeignKey(EditorProject)
    index = IntegerField()
    name = CharField(max_length=255)
    enabled = BooleanField(default=True)
    muted = BooleanField(default=False)
    volume = FloatField(default=1.0)  # 0.0 to 2.0

# Clips on tracks
class Clip(BaseModel):
    track = ForeignKey(VideoTrack|AudioTrack)
    media_asset = ForeignKey(MediaAsset)
    source_start_ms = IntegerField()
    source_end_ms = IntegerField()
    timeline_start_ms = IntegerField()
    timeline_duration_ms = IntegerField()
    enabled = BooleanField(default=True)
    muted = BooleanField(default=False)
    playback_rate = FloatField(default=1.0)
    audio_gain_db = FloatField(default=0.0)
    fade_in_ms = IntegerField(default=0)
    fade_out_ms = IntegerField(default=0)
    excluded = BooleanField(default=False)

# Multicamera support
class CameraCut(BaseModel):
    project = ForeignKey(EditorProject)
    timeline_start_ms = IntegerField()
    timeline_end_ms = IntegerField()
    selected_camera_id = UUIDField()  # Refers to MediaAsset id
    source = CharField(choices=['manual', 'automatic', 'suggestion'])
    confidence = FloatField(null=True)
    user_override = BooleanField(default=False)
    revision = IntegerField()

# Edit operations
class EditOperation(BaseModel):
    project = ForeignKey(EditorProject)
    revision = IntegerField()
    operation_type = CharField(choices=[...])
    payload = JSONField()
    source = CharField(choices=['manual', 'transcript', 'ai_suggestion'])
    inverse_operation = JSONField(null=True)
    parent_operation = ForeignKey(EditOperation, null=True)
    applied = BooleanField(default=True)

# Media synchronization
class MediaSyncPoint(BaseModel):
    project = ForeignKey(EditorProject)
    asset1 = ForeignKey(MediaAsset)
    asset2 = ForeignKey(MediaAsset)
    asset1_time_ms = IntegerField()
    asset2_time_ms = IntegerField()
    sync_method = CharField(choices=['manual', 'waveform', 'timecode'])
    confidence = FloatField(null=True)

# Proxy and processing
class MediaProxy(BaseModel):
    source_asset = ForeignKey(MediaAsset)
    proxy_type = CharField(choices=['video', 'audio', 'waveform'])
    status = CharField(choices=['pending', 'processing', 'ready', 'failed'])
    file = FileField(null=True)
    error_message = TextField(blank=True)
    quality_preset = CharField(default='720p')

# Graphics and overlays
class GraphicOverlay(BaseModel):
    project = ForeignKey(EditorProject)
    timeline_start_ms = IntegerField()
    timeline_end_ms = IntegerField()
    overlay_type = CharField(choices=['logo', 'lower_third', 'title', 'background'])
    asset = ForeignKey(MediaAsset, null=True)
    text_content = CharField(null=True)
    position_x = IntegerField(default=0)
    position_y = IntegerField(default=0)
    width = IntegerField()
    height = IntegerField()
    opacity = FloatField(default=1.0)
    z_index = IntegerField(default=0)
    fade_in_ms = IntegerField(default=0)
    fade_out_ms = IntegerField(default=0)

# Captions
class CaptionCue(BaseModel):
    project = ForeignKey(EditorProject)
    timeline_start_ms = IntegerField()
    timeline_end_ms = IntegerField()
    text = TextField()
    speaker = CharField(null=True)
    auto_generated = BooleanField(default=False)
    burned_in = BooleanField(default=False)

# Markers and notes
class EditorMarker(BaseModel):
    project = ForeignKey(EditorProject)
    timeline_position_ms = IntegerField()
    label = CharField(max_length=255)
    color = CharField(max_length=7)  # Hex color

class EditorNote(BaseModel):
    project = ForeignKey(EditorProject)
    title = CharField(max_length=255)
    content = TextField()
    timestamp_ms = IntegerField(null=True)

# Export definitions
class ExportPreset(BaseModel):
    project = ForeignKey(EditorProject)
    name = CharField(max_length=255)
    container = CharField(choices=['mp4', 'webm', 'mkv'])
    video_codec = CharField(choices=['h264', 'vp9'])
    audio_codec = CharField(choices=['aac', 'mp3', 'opus'])
    video_bitrate_kbps = IntegerField()
    audio_bitrate_kbps = IntegerField()
    width = IntegerField()
    height = IntegerField()
    frame_rate = IntegerField()

class ExportedMedia(BaseModel):
    project = ForeignKey(EditorProject)
    revision = IntegerField()
    export_preset = ForeignKey(ExportPreset)
    status = CharField(choices=['queued', 'processing', 'ready', 'failed'])
    output_file = FileField(null=True)
    progress_percent = IntegerField(default=0)
    error_message = TextField(blank=True)
    duration_ms = IntegerField(null=True)
    file_size_bytes = BigIntegerField(null=True)

# Social clips
class SocialClip(BaseModel):
    project = ForeignKey(EditorProject)
    start_ms = IntegerField()
    end_ms = IntegerField()
    title = CharField(max_length=255)
    description = TextField(blank=True)
    aspect_ratio = CharField(choices=['16:9', '9:16', '1:1'])
    template_id = CharField(null=True)

# Processing jobs
class ProcessingJob(BaseModel):
    job_type = CharField(choices=['probe', 'proxy_video', 'proxy_audio', 'waveform', 'sync', 'render'])
    status = CharField(choices=['queued', 'processing', 'completed', 'failed', 'cancelled'])
    input_data = JSONField()
    output_data = JSONField(null=True)
    progress_percent = IntegerField(default=0)
    error_code = CharField(null=True)
    error_message = TextField(blank=True)
    started_at = DateTimeField(null=True)
    completed_at = DateTimeField(null=True)
    retry_count = IntegerField(default=0)
```

## Phase 2: API Endpoints

All endpoints require authentication and organization scoping.

### Editor Projects
- `POST /splice/projects/` - Create project for episode
- `GET /splice/projects/{id}/` - Get project metadata
- `PATCH /splice/projects/{id}/` - Update project settings
- `GET /splice/projects/{id}/timeline/` - Get compact timeline (tracks, clips, cuts, etc.)
- `GET /splice/projects/{id}/history/` - Paginated revision history

### Media
- `POST /splice/projects/{id}/media/` - Add media asset to project
- `GET /splice/media/{id}/` - Get media metadata and proxies
- `GET /splice/media/{id}/waveform/` - Get chunked waveform data
- `GET /splice/media/{id}/thumbnails/` - Get thumbnail grid
- `PATCH /splice/media/{id}/sync/` - Update sync offset

### Operations
- `POST /splice/projects/{id}/operations/` - Submit single operation
- `POST /splice/projects/{id}/operations/batch/` - Batch operations
- `POST /splice/projects/{id}/undo/` - Undo last operation
- `POST /splice/projects/{id}/redo/` - Redo operation

### Camera Cuts
- `GET /splice/projects/{id}/camera-cuts/` - List cuts
- `POST /splice/projects/{id}/camera-cuts/` - Create cut
- `PATCH /splice/camera-cuts/{id}/` - Update cut
- `DELETE /splice/camera-cuts/{id}/` - Delete cut
- `POST /splice/projects/{id}/camera-cuts/suggest/` - Get AI suggestions
- `POST /splice/projects/{id}/camera-cuts/accept-suggestions/` - Accept batch

### Exports
- `POST /splice/projects/{id}/exports/` - Start export job
- `GET /splice/exports/{id}/` - Get export status
- `POST /splice/exports/{id}/cancel/` - Cancel export

## Phase 3: Media Proxy Strategy

### Proxy Generation Workflow
1. User uploads `large-video.mp4` (source, immutable)
2. Backend probes media (ffprobe)
3. Backend generates:
   - **Video proxy**: H.264 720p, keyframes every 2 seconds, AAC stereo
   - **Audio proxy**: AAC stereo or mono
   - **Waveform data**: Peak samples, stored as JSON
   - **Thumbnails**: 1 frame every 5 seconds, WebP
4. Browser loads editor with proxy URLs
5. Timeline playback uses proxies
6. Export render uses original source

### Storage
- Source assets: `media/source/{episode_uuid}/{media_uuid}.{ext}`
- Proxy video: `media/proxies/{episode_uuid}/{media_uuid}_proxy.mp4`
- Proxy audio: `media/proxies/{episode_uuid}/{media_uuid}_audio.aac`
- Waveform: Stored in `MediaProxy` JSONField (gzipped)
- Thumbnails: `media/thumbnails/{episode_uuid}/{media_uuid}/{frame_number}.webp`

## Phase 4: Revision & Concurrency Model

### Optimistic Concurrency
```
1. Client fetches EditorProject (current_revision = 5)
2. Client makes edit: POST /operations/ with revision=5
3. Server checks: current_revision still 5? ✓
4. Server applies operation, increments revision to 6
5. Server returns 200 + new revision

If revision changed between fetch and post:
6. Server returns 409 Conflict:
   {
     "error": "Revision mismatch",
     "current_revision": 7,
     "client_revision": 5,
     "can_replay": true/false
   }
```

### Undo/Redo Persistence
- Each EditOperation stores inverse data
- Undo creates new EditOperation(applied=False) + increments revision
- Redo creates EditOperation(applied=True) + increments revision
- Survives session reload via ProjectRevision snapshots

## Phase 5: Render Planning

### Deterministic Render Plans
```python
class RenderPlan:
    project_id: UUID
    revision: int
    source_media: List[{asset_id, role, sync_offset_ms, included_ranges}]
    program_tracks: List[VideoTrack|AudioTrack]
    camera_cuts: List[{start_ms, end_ms, camera_id}]
    overlays: List[GraphicOverlay]
    captions: List[CaptionCue]
    audio_mix: {tracks, gains, fades}
    export_preset: ExportPreset
    loudness_preset: str  # "PODCAST_STEREO" etc.
```

Same project + revision + preset = same render plan = deterministic output.

### FFmpeg Safe Subprocess
```python
# NEVER: cmd = f"ffmpeg {user_input} ..."
# ALWAYS:
ffmpeg_args = [
    'ffmpeg',
    '-i', source_path,
    '-filter_complex', build_filter_graph(operations),
    '-c:v', 'libx264',
    '-c:a', 'aac',
    output_path,
]
subprocess.run(ffmpeg_args, check=True)
```

## Phase 6: Browser Editor Features (MVP)

### Required Interface
- Play/pause/seek
- Current time display
- Zoom controls
- Undo/redo buttons
- Video preview (proxy playback)
- Timeline with tracks
- Camera preview grid
- Waveform + thumbnails
- Transcript panel
- Markers
- Inspector for selected clip
- Export button

### Essential Interactions
- Click timeline to seek
- Drag to select range
- Right-click to split at playhead
- Drag clip boundaries to trim
- Click camera thumbnail to cut
- Select transcript words to ripple-edit
- Double-click to zoom

### Virtualization
- Transcript words: render visible window only
- Waveform: chunk data, render visible range
- Thumbnails: lazy-load on scroll
- Timeline: window-based clipping

## Phase 7: Testing Strategy

### Model Tests
- Clip timing invariants
- Sync offset application
- Camera cut boundary logic
- Revision increments
- Undo/redo state

### API Tests
- Project creation
- Multi-media upload
- Operation submission
- Revision conflict (409)
- Undo/redo across requests
- Export job creation
- Proxy readiness checks

### Processing Tests
- Media probing
- Proxy planning
- Synchronization offset calculation
- Render plan determinism
- Mock FFmpeg runner

### Frontend Tests (Later)
- Synchronized playback
- Timeline seeking
- Transcript selection
- Revision conflict handling
- Export progress

## Known Limitations (MVP)

1. **Single timeline**: No nesting or sequences
2. **No real-time collaboration**: Optimistic concurrency handles async users, not live co-editing
3. **Limited compositing**: Logo, lower third, title overlays only
4. **No spectral audio editing**: Waveform is visual only
5. **No color grading**: Can adjust gain, no LUT or 3D color workflows
6. **No keyframe animation**: Overlays have simple fade in/out, not full animation
7. **Browser-only rendering**: Proxies play in browser; full renders on backend
8. **SQLite limitations**: CheckConstraint with joined fields not supported; validation in clean() instead

## Recommended Next Phases

### Phase 8: AI Assistance
- Speaker diarization (identify who's speaking)
- Active-speaker camera cuts (auto-select based on audio)
- Silence detection (shorter gaps)
- Filler phrase suggestions

### Phase 9: Social Clips
- Aspect-ratio presets (16:9, 9:16, 1:1)
- Template-driven layouts
- Social clip export job
- Aspect-ratio-specific rendering

### Phase 10: AI Providers
- Generic provider interface
- Mock provider
- Higgsfield adapter (after API verification)
- Result import workflow

### Phase 11: Frontend SPA
- React-based editor
- Real-time websocket for job updates
- IndexedDB caching
- Keyboard shortcuts
- Advanced audio mixing (pan, EQ)

## Dependencies

### Python Packages
- `ffmpeg-python` or `ffprobe` CLI (video probe)
- Existing: `Pillow` (thumbnails), `qrcode` (future markers)

### System
- FFmpeg 4.4+ with libx264, libx265, libfdk-aac
- ffprobe (included with FFmpeg)
- ImageMagick or equivalent (WebP conversion)

### Browser
- HTML5 `<video>` element
- Web Audio API (waveform visualization, future audio mixing)
- Fetch API (XHR not needed)
- IndexedDB (future: local caching)

## Deployment

### Development
```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Production
- Same Django + Gunicorn + Postgres
- Celery + Redis for async jobs (recommended)
- S3 or equivalent for media storage
- CDN for proxy video/audio distribution

## Success Criteria for Phase 1 Milestone

- ✓ Authenticated users can create video editor projects for episodes
- ✓ Multiple camera and audio assets can be uploaded and synchronized
- ✓ Proxy generation jobs can be created and tracked
- ✓ API returns compact synchronized timeline (tracks, clips, camera cuts)
- ✓ Users can submit split, trim, exclude, restore operations
- ✓ Operations create revisions; stale revisions return 409 Conflict
- ✓ Undo/redo work across requests
- ✓ Transcript selection creates synchronized ripple edits
- ✓ Video and audio export jobs can be created
- ✓ Deterministic render plans work for both outputs
- ✓ Audio-only export reflects video-project edits
- ✓ Tests cover critical paths
- ✓ Documentation covers architecture and local setup

---

**Next Step**: Phase 1 implementation begins with domain models and migrations.
