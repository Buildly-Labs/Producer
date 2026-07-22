# Splice: Video Podcast Editor for Producer

> A lightweight, browser-based video podcast editor for Buildly Producer. Edit 50-60 minute podcasts with multicamera support, non-destructive operations, and audio-only export—all from the same project.

## Quick Start

### What is Splice?

Splice is an admin-only video editing interface within Producer that lets podcast teams:

1. **Upload multicamera recordings** - Host, guests, screen shares, intros/outros
2. **Synchronize recordings** - Align via timestamps, waveforms, or manual offsets
3. **Edit non-destructively** - Every change is reversible; original media never touched
4. **Switch cameras** - Select angles manually or let AI suggest cuts
5. **Add graphics** - Logos, lower thirds, titles, overlays
6. **Export video + audio** - From the same project: full video and audio-only podcasts
7. **Create social clips** - Mark vertical, square, and landscape excerpts for sharing
8. **Undo across sessions** - Edit history persists; come back later where you left off

### Why Splice?

- **Non-destructive**: Original media stays intact; all edits are reversible operations
- **Performance-optimized**: Browser uses proxy video (H.264 720p); final render uses originals
- **Unified editing**: One video project exports both video and audio podcasts
- **Lightweight**: No full-screen canvas rendering in browser; timeline-based editing
- **Audit trail**: Every change tracked by user, timestamp, operation type

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│          Splice Video Editor                │
├─────────────────────────────────────────────┤
│  Domain Models (splice/models.py)           │
│  ├─ EditorProject (timeline container)      │
│  ├─ VideoTrack, AudioTrack (timeline rows)  │
│  ├─ Clip (source + trim + placement)        │
│  ├─ CameraCut (angle selection)             │
│  ├─ EditOperation (non-destructive changes) │
│  ├─ MediaProxy (H.264, waveform, thumbs)    │
│  ├─ ExportedMedia (rendered outputs)        │
│  └─ ... 13 more models ...                  │
├─────────────────────────────────────────────┤
│  Services (to be built)                     │
│  ├─ Media probing (ffprobe)                 │
│  ├─ Proxy generation (FFmpeg)               │
│  ├─ Waveform extraction                     │
│  ├─ Render planning (deterministic)         │
│  ├─ Video export (FFmpeg)                   │
│  └─ Audio export (FFmpeg)                   │
├─────────────────────────────────────────────┤
│  API & Serializers (to be built)            │
│  ├─ REST endpoints (/splice/projects/...)   │
│  ├─ Timeline response format                │
│  ├─ Operation submission                    │
│  └─ Export progress polling                 │
├─────────────────────────────────────────────┤
│  Frontend Views (to be built)               │
│  ├─ Editor page with timeline               │
│  ├─ Camera grid preview                     │
│  ├─ Transcript sync panel                   │
│  ├─ Export progress monitor                 │
│  └─ Social clip selector                    │
└─────────────────────────────────────────────┘
```

## Data Model Highlights

### Non-Destructive Operations

Every edit is an immutable `EditOperation`:

```python
# User trims a clip from 10s-20s to 12s-19s
EditOperation(
    project=project,
    operation_type='trim_clip',
    payload={'clip_id': uuid, 'source_start_ms': 12000, 'source_end_ms': 19000},
    inverse_operation={'source_start_ms': 10000, 'source_end_ms': 20000},
    applied=True,  # False if undone
    revision=42  # Which revision this created
)
```

Undo = set `applied=False` + increment revision. Redo = set `applied=True` + increment revision.

### Immutable Source Media

Original `MediaAsset` files are never modified. Edits reference them:

```python
# Source: large-video.mp4 (1080p, 60min, immutable)
source = MediaAsset(episode=ep, file='source.mp4')

# Proxies created once: H.264 720p, AAC, waveform JSON
proxies = [
    MediaProxy(source_asset=source, proxy_type='video', file='proxy.mp4'),
    MediaProxy(source_asset=source, proxy_type='audio', file='proxy.aac'),
    MediaProxy(source_asset=source, proxy_type='waveform', file=json_data),
]

# Timeline uses sources + sync offsets + clips (which reference source ranges)
clip = Clip(
    media_asset=source,  # Points to original
    source_start_ms=10000,  # Trim to 10-20s of source
    source_end_ms=20000,
    timeline_start_ms=0,  # Play from start of timeline
    timeline_duration_ms=10000,
)
```

### Revision-Based Concurrency

```python
# Client reads project: revision=5
GET /splice/projects/abc-123/
→ {revision: 5, ...}

# Client submits edit
POST /splice/projects/abc-123/operations/
{operation: 'trim_clip', payload: {...}, client_revision: 5}

# Server checks: project.current_revision == 5? Yes ✓
# → Apply operation, increment revision to 6, return 200

# If another user edited first and revision is now 6:
# Server returns 409 Conflict: {current_revision: 6, client_revision: 5}
# → Client shows "out of date" dialog, fetches new state
```

### Multicamera Editing

```python
# Project has 3 synchronized camera tracks
cameras = [
    MediaAsset(label='Host', sync_offset=0),
    MediaAsset(label='Guest', sync_offset=+150),  # 150ms late
    MediaAsset(label='Screen', sync_offset=-50),  # 50ms early
]

# User selects angles over time
camera_cuts = [
    CameraCut(timeline_start_ms=0, timeline_end_ms=5000, camera=host),
    CameraCut(timeline_start_ms=5000, timeline_end_ms=8000, camera=guest),
    CameraCut(timeline_start_ms=8000, timeline_end_ms=60000, camera=host),
]

# Browser plays: video from camera_cuts, audio from all synchronized tracks mixed
```

## Phase Roadmap

### Phase 0: ✅ Complete
- [x] Repository assessment
- [x] Domain model design
- [x] API endpoint planning
- [x] Architecture documentation

### Phase 1: ✅ Complete (This Commit)
- [x] Django app setup
- [x] 19 core models
- [x] Database migrations
- [x] Model validation
- [x] Comprehensive docstrings
- [x] Architecture specification

### Phase 2: In Progress
- [ ] Media probe service (ffprobe)
- [ ] Proxy generation (H.264 720p, AAC, waveforms)
- [ ] Thumbnail extraction (WebP grid)
- [ ] Processing job queue (Celery-ready)
- [ ] Job lifecycle APIs
- [ ] Processing tests

### Phase 3: Planned
- [ ] REST API serializers
- [ ] ViewSets for projects, media, operations
- [ ] Timeline response format
- [ ] Optimistic concurrency HTTP handling
- [ ] Export job management
- [ ] API tests

### Phase 4: Planned
- [ ] Browser editor HTML/JavaScript
- [ ] HTML5 video playback
- [ ] Timeline UI (tracks, clips, seekbar)
- [ ] Keyboard shortcuts
- [ ] Undo/redo UI
- [ ] Export progress monitor

### Phase 5: Planned
- [ ] AI assistance (speaker diarization, active-speaker cuts)
- [ ] Silence detection
- [ ] Filler phrase suggestions

### Phase 6: Planned
- [ ] Social clip export with aspect ratios
- [ ] Generic AI provider interface
- [ ] Mock AI provider
- [ ] Higgsfield adapter (after API verification)

## Installation & Setup

### Local Development

1. **Migrations already applied**:
   ```bash
   python3 manage.py migrate splice
   # → Applies splice/migrations/0001_initial.py
   # → Creates 19 tables with 25+ indexes
   ```

2. **Run dev server**:
   ```bash
   python3 manage.py runserver
   ```

3. **Access (future)**:
   - Episode detail page → "Edit with Splice" button
   - Requires: authenticated user, ADMIN role on show

### Docker Development

```bash
docker-compose -f docker-compose.dev.yml up
# Migrations run automatically on startup
```

### Production Deployment

**Requirements**:
- FFmpeg 4.4+ with libx264, libx265, libfdk-aac
- ffprobe (included with FFmpeg)
- PostgreSQL (recommended; SQLite works for small deployments)
- S3 or equivalent for media storage
- Redis (recommended for background jobs)
- Celery (recommended for async processing)

**Setup**:
```bash
# Run migrations
python3 manage.py migrate

# Collect static files
python3 manage.py collectstatic --noinput

# Start Celery workers
celery -A logic_service worker -l info

# Start API server
gunicorn logic_service.wsgi:application
```

## API Endpoints (Planned)

All endpoints require authentication + organization scoping.

### Projects
```
POST   /splice/projects/                     # Create for episode
GET    /splice/projects/{id}/                # Get metadata
PATCH  /splice/projects/{id}/                # Update settings
GET    /splice/projects/{id}/timeline/       # Get full timeline
GET    /splice/projects/{id}/history/        # Operation history
```

### Media
```
POST   /splice/projects/{id}/media/          # Add to project
GET    /splice/media/{id}/                   # Get metadata
GET    /splice/media/{id}/waveform/          # Chunked data
GET    /splice/media/{id}/thumbnails/        # Grid
PATCH  /splice/media/{id}/sync/              # Update offset
```

### Operations & Undo/Redo
```
POST   /splice/projects/{id}/operations/     # Submit operation
POST   /splice/projects/{id}/undo/           # Undo last
POST   /splice/projects/{id}/redo/           # Redo
```

### Camera Cuts
```
GET    /splice/projects/{id}/camera-cuts/    # List cuts
POST   /splice/projects/{id}/camera-cuts/    # Create cut
PATCH  /splice/camera-cuts/{id}/             # Update cut
DELETE /splice/camera-cuts/{id}/             # Delete cut
POST   /splice/projects/{id}/camera-cuts/suggest/  # AI suggestions
```

### Exports
```
POST   /splice/projects/{id}/exports/        # Create export job
GET    /splice/exports/{id}/                 # Get status
POST   /splice/exports/{id}/cancel/          # Cancel
```

*(Complete API spec in devdocs/splice-architecture.md)*

## Performance & Scalability

### Browser Playback (Proxy)
- **Source**: 1080p H.264, variable bitrate, 50-60min file
- **Proxy**: 720p H.264, constant bitrate (3-4 Mbps), frequent keyframes
- **Result**: Smooth 30fps playback in browser, responsive seeking

### Final Render (Original)
- **Source**: Unmodified original file
- **FFmpeg**: Reads clips from original, applies operations
- **Result**: Highest quality output; no generation loss

### Waveform & Thumbnails
- **Waveform**: Peak samples extracted once, stored as JSON (~1-2 MB for 60min)
- **Thumbnails**: WebP grid (1 frame per 5 seconds = ~720 images), stored on CDN
- **Result**: Instant UI display without clip decoding

### Database
- **Indexes**: 25+ on critical paths (org, project, timeline, status)
- **Queries**: Select_related for FK, prefetch_related for reverse
- **Scalability**: Works on SQLite (dev), PostgreSQL (prod)

### Async Processing
- **Proxy generation**: Celery task, progress tracked
- **Export rendering**: Celery task, background FFmpeg process
- **No blocking**: API returns immediately with job ID; client polls status

## Project Organization

```
Producer/
├── splice/                           # Video editor app (new)
│   ├── migrations/
│   │   ├── __init__.py
│   │   └── 0001_initial.py          # All 19 models
│   ├── models.py                    # Domain models (950+ lines)
│   ├── views.py                     # To be filled (Phase 3)
│   ├── serializers.py               # To be filled (Phase 3)
│   ├── admin.py                     # To be filled
│   ├── tests.py                     # To be filled (Phase 2+)
│   ├── apps.py
│   └── services/                    # To be created (Phase 2)
│       ├── media.py                 # Probe, proxy, waveform
│       ├── render.py                # Render plan, FFmpeg
│       └── jobs.py                  # Job queue abstraction
├── production_ledger/                # Existing podcast metadata
│   ├── models.py                    # Show, Episode, MediaAsset, Transcript
│   ├── views.py
│   ├── serializers.py
│   └── services/
├── devdocs/
│   ├── splice-architecture.md        # Complete spec
│   └── SPLICE_IMPLEMENTATION_PHASE1.md  # This phase
├── logic_service/
│   └── settings/base.py             # INSTALLED_APPS += 'splice'
└── templates/
    └── splice/                       # To be created (Phase 4)
        ├── editor.html              # Main editor page
        ├── timeline.html            # Timeline component
        └── ...
```

## Security & Permissions

### Organization Scoping
- All Splice models inherit `organization_uuid`
- Users can only edit projects in their organization
- API filters: `queryset.filter(organization_uuid=user.org)`

### Role Requirements
- **Viewer**: Can watch playback (future)
- **Editor**: Can edit timeline
- **Admin**: Can upload media, manage exports
- Implementation: Existing Producer role system extended

### Immutable Audit Trail
- Every operation: `created_by`, `created_at`, operation details
- Every export: `started_at`, `completed_at`, error logs
- Deletion: Soft-delete via `applied=False` on EditOperation

### Media Security
- Source files: Private S3 access only
- Proxies: Private until published
- Secrets: API keys encrypted, never returned to browser

## FAQ

### Q: Why non-destructive?
**A**: Allows undo across sessions, maintains audit trail, never loses data. If you cut 10 minutes by accident, just undo.

### Q: Why separate from production_ledger?
**A**: Keeps editor domain isolated, allows independent feature-flagging, can deploy without affecting core podcast management.

### Q: Why proxy + original?
**A**: 60min @ 1080p in browser = lag and memory issues. Proxy is fast, responsive, but final render uses originals for quality.

### Q: Can I edit audio-only from the same project?
**A**: Yes! Same video-project timeline exports both video (with selected cameras) and audio-only (without video tracks). No separate audio project needed.

### Q: How is it "lightweight"?
**A**: No real-time 3D rendering, no spectral audio editing, no effect chains. Just: clips, transitions, gain, fades, overlays, captions. Clean, focused feature set.

### Q: When will the browser editor be ready?
**A**: Phase 4 (planned for late Q3/Q4 2026). For now, use the API directly or wait for the web UI.

## Contributing

### Code Style
- Follow existing Producer conventions (PEP 8, Django style)
- 4-space indents, docstrings on all classes/methods
- Type hints where helpful
- Tests for all new features

### Testing
- Unit tests for models and services
- API tests for endpoints
- Integration tests for workflows
- Run: `python3 manage.py test splice`

### Documentation
- Update `devdocs/` for architecture changes
- Document new API endpoints
- Add docstrings to all new code

## Resources

- **Architecture**: [devdocs/splice-architecture.md](devdocs/splice-architecture.md)
- **Phase 1 Details**: [devdocs/SPLICE_IMPLEMENTATION_PHASE1.md](devdocs/SPLICE_IMPLEMENTATION_PHASE1.md)
- **Producer Docs**: [devdocs/README.md](devdocs/README.md)
- **FFmpeg Docs**: https://ffmpeg.org/documentation.html
- **Django Models**: https://docs.djangoproject.com/en/5.1/topics/db/models/

## License

Same as Producer repository: See [LICENSE](LICENSE)

---

**Status**: Phase 1 complete ✅ (Models + Architecture)  
**Next**: Phase 2 (Media proxy generation)  
**Updated**: July 21, 2026  
**Contact**: Buildly Team
