# Splice Video Podcast Editor - Phase 1 Implementation Summary

**Date**: July 21, 2026  
**Status**: ✅ Complete - Foundation models and architecture documented  
**Next Phase**: Phase 2 - Media preparation, proxy generation, and processing jobs

## Executive Summary

The Splice video podcast editor foundation is now in place. This document covers the Phase 1 implementation: domain models, database schema, architectural decisions, and the extension strategy for the Buildly Producer platform.

## What Was Built

### 1. **New Django App: `splice`**
A dedicated Django application for the video editor, isolated from the existing `production_ledger` app. This allows independent development, feature-flagging, and future deployment flexibility.

**Directory Structure**:
```
splice/
├── migrations/
│   └── 0001_initial.py (19 models, 25+ indexes)
├── models.py (950+ lines)
├── admin.py
├── views.py (to be populated)
├── serializers.py (to be populated)
├── services/ (to be populated)
├── tests.py
└── apps.py
```

### 2. **19 Core Domain Models**

#### Project & Revision Management
- **`EditorProject`**: Top-level project for an episode
  - Stores canvas dimensions, frame rate, aspect ratio
  - Tracks current revision for optimistic concurrency
  - Autosave configuration
  - Extends `BaseModel` for organization scoping, audit fields

- **`ProjectRevision`**: Immutable snapshots at each revision
  - Enables undo/redo across sessions
  - Render plan reproducibility (same revision = same output)
  - Append-only operation history

#### Timeline Structure
- **`VideoTrack`**: Video track in timeline (multiple per project)
  - Track index for ordering
  - Visibility and enabled state
  - Holds video clips

- **`AudioTrack`**: Audio track in timeline (multiple per project)
  - Volume, muting, enable/disable
  - Mixing state per track

- **`Clip`**: Individual video or audio clip on a track
  - Non-destructive: `source_start_ms`, `source_end_ms` (trim points)
  - Timeline placement: `timeline_start_ms`, `timeline_duration_ms`
  - Audio controls: volume, fade-in/out, muting
  - Video controls: playback rate, disabled/excluded state
  - Can be on either a VideoTrack OR AudioTrack (validated in `clean()`)

#### Multicamera Support
- **`CameraCut`**: Angle selection during a time range
  - References MediaAsset UUID (camera role)
  - Source: manual, automatic, or suggestion
  - Confidence score for automatic cuts
  - Revision tracking for undo

#### Edit Operations
- **`EditOperation`**: Non-destructive timeline mutation
  - 21 operation types (split, trim, exclude, restore, etc.)
  - Immutable once created; `applied` field for undo tracking
  - Stores `payload` (operation data) and `inverse_operation` (undo data)
  - Source tracking: manual, transcript, AI, speaker detection
  - Parent/child relationships for batched operations

#### Synchronization
- **`MediaSyncPoint`**: Alignment anchor between two media assets
  - Stores time correspondence in both assets
  - Methods: manual, waveform correlation, timecode, marker-based
  - Confidence scores for automatic methods

#### Media Processing
- **`MediaProxy`**: Lower-resolution copy for browser preview
  - Types: video, audio, waveform, thumbnails
  - Status: pending, processing, ready, failed
  - Quality preset (e.g., "720p")
  - Original MediaAsset never modified; proxy is copy

- **`ProcessingJob`**: Background job for async work
  - 12 job types (probe, proxy creation, waveform, render, etc.)
  - Full lifecycle: queued → processing → completed/failed
  - Progress tracking, error handling, retry count
  - Related to either EditorProject or MediaAsset

#### Graphics & Captions
- **`GraphicOverlay`**: Visual elements on video
  - Types: logo, lower_third, title, background, watermark, etc.
  - Content: either image asset or text
  - Position, size, opacity, z-index
  - Fade in/out timing
  - Template reference for styling

- **`CaptionCue`**: Caption for a time range
  - Text, speaker label, auto-generated flag
  - Burned-in flag for video export
  - Timeline scoped (part of project, not file-based)

#### Project Annotations
- **`EditorMarker`**: Temporal bookmark
  - Position, label, color (hex)
  - For marking important moments

- **`EditorNote`**: Timestamped comment or reminder
  - Title, content, optional timestamp

#### Exports
- **`ExportPreset`**: Template for export settings
  - Container (MP4, MOV, WebM, MKV)
  - Video codec, bitrate, resolution, frame rate
  - Audio codec, bitrate, channels
  - Loudness preset reference

- **`ExportedMedia`**: Rendered output from a revision
  - Links to project, revision, and preset
  - Status: queued, processing, ready, failed
  - Progress, error tracking
  - Output file, metadata (duration, size)
  - Timestamps for monitoring

#### Social Clips
- **`SocialClip`**: Excerpt of main timeline for social posting
  - Timeline range (start/end ms)
  - Title, description
  - Aspect ratio preset (16:9, 9:16, 1:1)
  - Template ID for layout
  - Export status

#### AI Features
- **`AISuggestion`**: AI-generated edit pending review
  - Types: camera_cut, caption, silence_cut, filler_phrase, speaker_label
  - Confidence score
  - Acceptance tracking with timestamp and user
  - Provenance: provider, model, prompt template

- **`AIProviderConfiguration`**: Provider credentials
  - Scoped to organization
  - Secret API key (never returned to browser)
  - Enabled flag
  - Supported capabilities list

### 3. **Database Schema Characteristics**

**Indexes**: 25+ strategic indexes for fast queries
- Organization scoping on all models extending BaseModel
- Timeline queries (project, timeline_start_ms)
- Status/state filtering (processing job status, export status)
- Revision tracking (project, revision_number)

**Unique Constraints**:
- `(project, index)` on VideoTrack and AudioTrack
- `(asset1, asset2)` on MediaSyncPoint
- `(source_asset, proxy_type)` on MediaProxy
- `(organization, provider_name)` on AIProviderConfiguration
- `(project, revision_number)` on ProjectRevision

**Validation**:
- Clips validated to be on exactly one track type (video XOR audio)
- CameraCut timeline bounds checked (`start_ms < end_ms`)
- Source/end trim points validated (`source_start_ms < source_end_ms`)
- All models inherit organization_uuid and audit fields from BaseModel

### 4. **Architectural Decisions**

#### Non-Destructive Edits
- Original MediaAsset files are immutable
- Clips reference source_start/end; no file modification
- All edits are operations stored separately
- Undo/redo via EditOperation.applied flag and inverse_operation data
- Same project revision always renders identically

#### Optimistic Concurrency
- EditorProject.current_revision tracks state
- Client submits operations with revision they saw
- Server checks: `project.current_revision == client_revision?`
- If mismatch: return 409 Conflict with current revision
- Allows async, offline clients without real-time locks

#### Revision-Based Rendering
- Exports tied to specific project revision
- Different revisions produce different outputs
- Same (project, revision, preset) always gives same render
- Future: full determinism via RenderPlan snapshot

#### Separation of Concerns
- Models describe data structure only
- Services (to be built in Phase 2) handle:
  - Proxy generation
  - Waveform extraction
  - Render planning
  - FFmpeg invocation
- Views/Serializers (to be built) expose APIs

#### Media Strategy
- Source media: immutable, full-resolution, original storage
- Proxy video: H.264 720p, frequent keyframes
- Proxy audio: AAC stereo or mono
- Waveform: peak samples as JSON
- Thumbnails: WebP at regular intervals
- All stored separately; original never touched

## Files Added

1. **`splice/migrations/0001_initial.py`** (auto-generated)
   - 19 model creation operations
   - 25+ strategic indexes
   - Unique constraints

2. **`splice/models.py`** (950+ lines)
   - 19 domain models
   - Comprehensive docstrings
   - Validation logic in clean() methods
   - Strategic indexes

3. **`devdocs/splice-architecture.md`** (Phase 0 assessment)
   - Repository analysis
   - Extension points
   - Complete domain specification
   - API endpoints planned
   - Testing strategy

4. **`devdocs/SPLICE_IMPLEMENTATION_PHASE1.md`** (this file)
   - Implementation details
   - Model relationships
   - Architectural rationale

## Files Modified

1. **`logic_service/settings/base.py`**
   - Added `'splice'` to `INSTALLED_APPS_LOCAL`

## Database State

**Migration Status**: ✅ Applied
```bash
python3 manage.py migrate splice
# Operations to perform: Apply all migrations: splice
# Running migrations: Applying splice.0001_initial... OK
```

**Models in Database**:
- 19 tables created
- 25+ indexes created
- Full audit trail support (created_by, updated_by, timestamps)
- Organization scoping enabled on all BaseModel subclasses

## API Endpoints (Planned - Not Yet Implemented)

Will follow Django REST Framework conventions:

### Editor Projects
- `POST /splice/projects/` - Create project for episode
- `GET /splice/projects/{id}/` - Get project and metadata
- `PATCH /splice/projects/{id}/` - Update settings
- `GET /splice/projects/{id}/timeline/` - Get compact timeline (tracks, clips, cuts)
- `GET /splice/projects/{id}/history/` - Paginated operation history

### Operations
- `POST /splice/projects/{id}/operations/` - Submit operation
- `POST /splice/projects/{id}/undo/` - Undo last
- `POST /splice/projects/{id}/redo/` - Redo

### Media
- `POST /splice/projects/{id}/media/` - Add media to project
- `GET /splice/media/{id}/` - Get media metadata
- `GET /splice/media/{id}/waveform/` - Chunked waveform
- `GET /splice/media/{id}/thumbnails/` - Thumbnail grid

### Exports
- `POST /splice/projects/{id}/exports/` - Create export job
- `GET /splice/exports/{id}/` - Get export status

*(Full API spec in splice-architecture.md)*

## Testing Strategy (To Implement in Phase 2)

### Unit Tests
- Model invariants (clip timing, sync, camera cuts)
- Revision increments and concurrency
- Undo/redo state management
- Operation payload validation

### API Tests
- Project CRUD with organization scoping
- Revision conflict handling (409)
- Media asset association
- Export job creation and tracking

### Integration Tests
- Multi-user concurrent edits
- Proxy generation job creation
- Sync offset application
- Render plan determinism

## Performance Considerations

### Database Indexes
All critical query paths indexed:
- Organization + resource type
- Project + timeline range (for seeking, export building)
- Status queries (job monitoring, export progress)
- Revision tracking for undo/redo

### Query Optimization
- Use `select_related()` for ForeignKey accesses (Track → Project)
- Use `prefetch_related()` for reverse relations (Project → Clips)
- Pagination for long lists (history, media assets)
- JSONField for operation payloads (no extra queries)

### Storage
- Original media: S3/object store (large files)
- Proxies: S3 with public read URLs (browser playback)
- Waveform JSON: Database JSONField (small, frequently accessed)
- Thumbnails: S3 with CDN (browser display)

## Known Limitations (MVP Scope)

### Not Implemented
- Real-time collaborative editing (optimistic concurrency only)
- Spectral audio editing
- Keyframe animation systems
- Color grading
- Advanced compositing
- Browser-only full rendering
- Automatic platform publication
- Automatic AI edge application without review

### Database Limitations
- SQLite doesn't support CheckConstraint with joined fields
  - Mitigation: validation in model clean() method
  - Will work on PostgreSQL (production)

### Future Extensions
- Real-time updates via WebSocket
- Advanced audio mixing (pan, EQ)
- Effect chains
- Custom plugin architecture
- Mobile editing interface

## Deployment Checklist

### Development
- ✅ Models defined
- ✅ Migrations created and applied
- ✅ App registered in settings
- ⬜ Admin interface (admin.py)
- ⬜ Serializers
- ⬜ ViewSets/Views
- ⬜ URL routing
- ⬜ Tests
- ⬜ Services (media proxy, waveform, render)

### Production
- ✅ Database schema ready
- ⬜ FFmpeg installed and configured
- ⬜ Media storage (S3/equivalent) configured
- ⬜ Async job queue configured (Celery + Redis or similar)
- ⬜ Proxy storage accessible via CDN
- ⬜ Backup and disaster recovery for immutable source media

## Environment Setup

### Local Development
```bash
# Install dependencies (already in requirements.txt)
pip install Django djangorestframework Pillow

# Create migrations
python3 manage.py makemigrations splice

# Apply migrations
python3 manage.py migrate splice

# Run dev server
python3 manage.py runserver
```

### Docker
```bash
# Build with splice app already in INSTALLED_APPS
docker-compose -f docker-compose.dev.yml up

# Run migrations inside container
docker-compose exec web python manage.py migrate
```

## Next Phase: Phase 2 - Media Preparation

### Deliverables
1. **Media Probe Service**
   - ffprobe integration
   - Extract: duration, resolution, codec, frame rate, etc.

2. **Proxy Generation**
   - Video proxy: H.264 720p
   - Audio proxy: AAC
   - Thumbnail strip: WebP at 5-second intervals

3. **Waveform Extraction**
   - Peak samples from audio
   - Store as JSON in MediaProxy
   - Compress for efficient transfer

4. **Processing Job Queue**
   - Job creation and lifecycle
   - Synchronous runner for development
   - Redis/Celery support for production

5. **Tests**
   - Probe accuracy
   - Proxy quality
   - Waveform data format

### Phase 2 Estimated Scope
- 3-4 new service classes
- 10-15 tests
- Small UI for monitoring job progress
- ~2-3 weeks development

## Conclusion

Splice Phase 1 establishes a robust, scalable foundation for a non-destructive, browser-based video editor. The domain models are comprehensive, well-indexed, and ready for the services and APIs that will be built in subsequent phases.

The architecture favors:
- **Immutability**: Original media never changes
- **Auditability**: Every change tracked as an operation
- **Recoverability**: Undo/redo across sessions
- **Determinism**: Same input always produces same output
- **Scalability**: Async processing via background jobs
- **Security**: Organization scoping, permission checks to follow

---

**Repository**: https://github.com/Buildly-Marketplace/Producer  
**Branch**: `main` (Phase 1 merged)  
**Test Status**: ✅ Models migrate cleanly, no fixture conflicts  
**Documentation**: Complete in `devdocs/splice-architecture.md` and this file
