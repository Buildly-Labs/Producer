# Phase 2 Roadmap: Services & API Layer (2-3 weeks)

**Start**: Ready now  
**Baseline**: Phase 1.5 complete (6 models, 3 EditorProject fields)  
**Goal**: Implement services for local engine registration, job management, and media handling

---

## Work Breakdown

### Sprint 1: Services Layer (1 week)

#### 1. LocalEngineService (`splice/services/local_engine.py`)
Handles engine registration, heartbeat, session management.

```python
class LocalEngineService:
    def register_engine(org_uuid, engine_name, platform) -> LocalEngineInstallation
        # 1. Generate engine_uuid
        # 2. Hash registration_key
        # 3. Create installation record
        # 4. Return registration_key (ONE TIME)
    
    def create_session(engine_id, browser_origin, expires_in_minutes) -> LocalEngineSession
        # 1. Generate session_token (secrets.token_urlsafe)
        # 2. Set expires_at
        # 3. Return session_token
    
    def validate_session(session_token, browser_origin) -> LocalEngineInstallation
        # 1. Lookup session by token
        # 2. Check expiration
        # 3. Validate origin
        # 4. Update last_heartbeat
        # 5. Return engine_uuid (if valid)
    
    def heartbeat(engine_id) -> bool
        # 1. Update last_heartbeat
        # 2. Set is_online = True
        # 3. Return success
```

**Tests to add**:
- Engine registration flow (happy path, duplicate names, invalid platform)
- Session creation (correct expiration time, token format)
- Session validation (expired, wrong origin, missing token)
- Heartbeat updates last_heartbeat and is_online
- Offline detection (no heartbeat for N minutes)

#### 2. MediaService (`splice/services/media.py`)
Fingerprinting, location tracking, relinking logic.

```python
class MediaService:
    def probe_media(file_path) -> dict
        # 1. Use ffprobe to extract codec, duration, size
        # 2. Compute fingerprints (size, duration, codecs, hashes)
        # 3. Return metadata
    
    def fingerprint_media(asset_id, file_path) -> MediaFingerprint
        # 1. Get file size, duration, codecs
        # 2. Hash: first chunk, last chunk, 10%, full
        # 3. Create MediaFingerprint record
        # 4. Return fingerprint
    
    def relink_media(asset_id, new_file_path) -> bool
        # 1. Get existing MediaFingerprint
        # 2. Probe new file
        # 3. Compare: size, duration, codecs, hashes
        # 4. If match found, update MediaLocation.local_location_id
        # 5. Return success
    
    def create_location(asset_id, location_type, details) -> MediaLocation
        # 1. Validate location_type + details match
        # 2. Create MediaLocation record
        # 3. Return location
    
    def get_location_for_asset(asset_id) -> MediaLocation
        # 1. Prefer local_device over cloud
        # 2. Check availability
        # 3. If offline, mark needs_relink
        # 4. Return best location
```

**Tests to add**:
- ffprobe integration (mock or real file)
- Fingerprinting: size, duration, codec, hashes
- Multi-method matching (size → duration → codec → hash)
- Relinking with exact match
- Relinking with codec mismatch (failure)
- Location creation for each location_type
- Availability state transitions (available → offline → needs_relink)

#### 3. RenderPlanService (`splice/services/render_plan.py`)
Generate path-free rendering blueprints.

```python
class RenderPlanService:
    def create_render_plan(project_id, revision) -> RenderPlan
        # 1. Fetch project & revision state
        # 2. Collect asset UUIDs (NOT paths)
        # 3. Serialize operations
        # 4. Collect camera cuts
        # 5. Get sync offsets
        # 6. Create RenderPlan record
        # 7. Return plan
    
    def validate_render_plan(plan_id) -> bool
        # 1. Load all asset UUIDs in plan
        # 2. Check all assets exist and are accessible
        # 3. Validate operation schema
        # 4. Return valid (or raise ValidationError)
    
    def plan_to_ffmpeg_blueprint(plan_id) -> dict
        # 1. Load RenderPlan
        # 2. Convert UUIDs → S3 paths or local references (no absolute paths)
        # 3. Build FFmpeg filter_complex
        # 4. Return: filtergraph, inputs, outputs (no shell escaping)
```

**Tests to add**:
- RenderPlan creation with assets, operations, camera cuts
- Determinism test: same project/revision → same RenderPlan
- Asset UUID validation (all exist, none deleted)
- FFmpeg blueprint generation (no absolute paths)
- Blueprint determinism (same inputs → same blueprint)

### Sprint 2: Views & API (1 week)

#### 4. LocalEngineAPI Views (`splice/views.py`)
REST endpoints for engine registration and session management.

```
POST /splice/engines/register/
  Input: {engine_name, platform}
  Output: {registration_key, engine_uuid}  # ONE TIME - don't log this
  Auth: API key (from invite/email)
  
POST /splice/engines/{engine_id}/heartbeat/
  Input: {status, proxy_quality, concurrent_jobs_available}
  Output: {jobs_queued: [...]}
  Auth: Session token (via browser relay)
  
POST /splice/sessions/create/
  Input: {browser_origin}
  Output: {session_token, expires_at}
  Auth: Session token (or API key for browser setup)
  
GET /splice/sessions/{token}/
  Input: browser_origin (header)
  Output: {engine_uuid, valid: bool}
  Auth: Session token
```

#### 5. LocalProcessingJobAPI Views (`splice/views.py`)
Job management endpoints.

```
POST /splice/projects/{project_id}/jobs/
  Input: {job_type, input_data, priority}
  Output: {job_id, status}
  Auth: User authenticated + project permission
  
GET /splice/jobs/{job_id}/
  Input: (none)
  Output: {job_id, status, progress_percent, output_data}
  Auth: User authenticated + job owner
  
PATCH /splice/jobs/{job_id}/
  Input: {status, progress_percent, output_data, error_message}
  Output: {job_id, status}
  Auth: Session token (local engine updates only)
  
POST /splice/jobs/{job_id}/confirm/
  Input: {user_confirms: bool}
  Output: {job_id, status}
  Auth: User authenticated
```

**Tests to add**:
- Engine registration flow with invalid platform (400)
- Heartbeat updates is_online, job availability
- Session creation with expiration
- Session validation with wrong origin (403)
- Job creation with invalid job_type (400)
- Job status polling (200 while queued, output_data when complete)
- Permission checks (non-owner can't view job)
- Confirmation flow (job waits for user_confirmed before starting)

#### 6. Serializers (`splice/serializers.py`)
Input/output serialization for all endpoints.

```python
class LocalEngineInstallationSerializer
    # Fields: engine_name, engine_uuid, platform, is_online, last_heartbeat
    # Read-only: engine_uuid, created_at, created_by
    
class LocalEngineSessionSerializer
    # Fields: session_token, expires_at
    # Read-only: created_at
    
class LocalProcessingJobSerializer
    # Fields: job_type, status, priority, progress_percent, input_data, output_data
    # Read-only: created_at, created_by, started_at, completed_at
    
class RenderPlanSerializer
    # Fields: project, revision, asset_selections, operations, output_preset
    # Read-only: created_at
```

### Sprint 3: Testing & Integration (1 week)

#### 7. Unit Tests
- Each service method
- Each serializer
- Each view endpoint

#### 8. Integration Tests
- Full engine registration → heartbeat → session → job flow
- Job submission → local engine processing → result upload
- Media relinking with fingerprint matching
- Multi-tenant isolation (org_uuid scoping)

#### 9. Security Tests
- Path injection prevention (input_data validation)
- Command schema validation (no shell escaping)
- Origin validation on sessions
- Permission checks on all endpoints
- Token expiration

---

## File Structure

```
splice/
├── migrations/
│   ├── 0002_local_first_architecture.py  [DONE]
│   └── 0003_*.py                         [Future]
├── models.py                             [DONE - Phase 1.5]
├── views.py                              [NEW - Phase 2]
├── serializers.py                        [NEW - Phase 2]
├── services/
│   ├── __init__.py
│   ├── local_engine.py                   [NEW - Phase 2]
│   ├── media.py                          [NEW - Phase 2]
│   └── render_plan.py                    [NEW - Phase 2]
├── tests.py                              [UPDATE - Phase 2]
├── urls.py                               [NEW - Phase 2]
└── admin.py                              [UPDATE - Phase 2]
```

---

## Implementation Guidelines

### Security Checklist
- [ ] No absolute file paths in job input_data
- [ ] Session tokens expire (configurable, default 1 hour)
- [ ] Browser origin validated on every request
- [ ] Registration key returned once, never logged
- [ ] Command schema enforced (no user strings in shell commands)
- [ ] Organization scoping on all queries
- [ ] Permission checks before returning user data
- [ ] Audit trail (created_by, created_at on all records)

### Testing Checklist
- [ ] Unit tests for each service method (happy path + error cases)
- [ ] Integration tests for full workflows
- [ ] Security tests (path injection, token expiration, origin validation)
- [ ] Concurrency tests (simultaneous heartbeats, job submissions)
- [ ] Performance tests (large job queues, fingerprinting large files)

### Documentation Checklist
- [ ] API endpoint reference (OpenAPI/Swagger)
- [ ] Service method docstrings (with examples)
- [ ] Security model overview
- [ ] Deployment guide (env vars, settings)
- [ ] Troubleshooting guide

---

## Key Decisions to Make

1. **Job confirmation UX**: User clicks "render" → immediately queued, or confirmation dialog?
   - Proposal: Confirmation dialog for destructive/expensive operations (render_video, render_audio)
   - Quick auto-start for non-destructive (generate_thumbnails, generate_waveform)

2. **Fingerprinting performance**: Full hash on every file, or lazy hash?
   - Proposal: Size+duration on import, hash on relinking (only when needed)
   - Trade-off: Relinking slower, but import faster

3. **Local engine deployment**: Package as standalone Python app or container?
   - Proposal: Electron app (with Node/Python backend) for easy installer
   - Or: Docker container for server deployments
   - Decision needed from product team

4. **Heartbeat interval**: How often should local engine check in?
   - Proposal: 30 seconds (responsive to job submissions, not too noisy)
   - Configurable per installation

5. **Job timeout**: How long before a stalled job is marked failed?
   - Proposal: 12 hours (reasonable for large video rendering)
   - Configurable per project

---

## Success Criteria

✅ Engine can register and receive jobs  
✅ Browser can submit jobs via session token  
✅ Local engine can process jobs with asset UUID resolution  
✅ Job status visible in browser (polling or WebSocket)  
✅ Media fingerprinting enables relinking without re-upload  
✅ All 50+ new tests pass  
✅ No absolute file paths in cloud database  
✅ Security review passes (path injection, command validation, origin check)  

---

## Risk Mitigation

**Risk**: Local engine crashes mid-job, browser never hears about it
- *Mitigation*: Heartbeat timeout marks engine offline; browser polls job status with timeout

**Risk**: Job queues grow unbounded if engine is offline
- *Mitigation*: Auto-prune jobs older than 30 days; max queue size per engine

**Risk**: File moved locally, fingerprinting can't find it
- *Mitigation*: User file selection (File System Access API or <input>); fallback to re-upload

**Risk**: Concurrent edits create conflicting operations in RenderPlan
- *Mitigation*: Revision number prevents stale edits; revision-based locking at plan generation time

---

## Post-Phase-2 (Phase 3-4)

- Browser editor UI (timeline, camera grid, export dialog)
- WebSocket for real-time job updates (vs polling)
- Proxy generation pipeline (video, audio, waveform, thumbnails)
- Export presets (YouTube, Spotify, podcast hosting)
- Social clip export (vertical, square, landscape)

---

**Next**: Begin Phase 2 sprint 1 (LocalEngineService, MediaService, RenderPlanService)
