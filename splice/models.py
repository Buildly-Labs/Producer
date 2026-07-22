"""
Splice Video Podcast Editor Models.

Non-destructive edit-decision model:
- Original media remains unchanged
- Proxy media is used for browser preview
- Edit operations are stored as timeline mutations
- Final video/audio are rendered by backend workers
"""
import uuid
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from production_ledger.models import BaseModel, Episode, MediaAsset


# =============================================================================
# EDITOR PROJECT & REVISIONS
# =============================================================================

class EditorProject(BaseModel):
    """
    Video editor project for an episode.
    Stores timeline configuration, tracks, and current revision.
    """
    episode = models.ForeignKey(
        Episode,
        on_delete=models.CASCADE,
        related_name='editor_projects',
        help_text="Episode being edited"
    )

    # Canvas and timing
    frame_rate = models.PositiveIntegerField(
        default=30,
        help_text="Project frame rate (23.976, 24, 25, 29.97, 30, 50, 59.94, 60)"
    )
    canvas_width = models.PositiveIntegerField(default=1920)
    canvas_height = models.PositiveIntegerField(default=1080)
    aspect_ratio = models.CharField(
        max_length=10,
        choices=[
            ('16:9', '16:9 (Landscape)'),
            ('9:16', '9:16 (Vertical)'),
            ('1:1', '1:1 (Square)'),
            ('4:3', '4:3 (Standard)'),
        ],
        default='16:9'
    )
    timeline_duration_ms = models.PositiveIntegerField(
        default=3600000,  # 1 hour
        help_text="Total project duration in milliseconds"
    )

    # Workflow
    autosave_enabled = models.BooleanField(default=True)
    current_revision = models.PositiveIntegerField(default=0)
    last_autosave_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Editor Project"
        verbose_name_plural = "Editor Projects"
        indexes = [
            models.Index(fields=['organization_uuid', 'episode']),
        ]

    def __str__(self):
        return f"Editor: {self.episode.title}"

    def increment_revision(self):
        """Atomically increment and return the new revision."""
        from django.db.models import F
        self.current_revision = F('current_revision') + 1
        self.save(update_fields=['current_revision', 'updated_at'])
        self.refresh_from_db()
        return self.current_revision


class ProjectRevision(BaseModel):
    """
    Immutable snapshot of project state at a given revision.
    Used for undo/redo and render plan reproducibility.
    """
    project = models.ForeignKey(
        EditorProject,
        on_delete=models.CASCADE,
        related_name='revisions',
    )
    revision_number = models.PositiveIntegerField()
    operation_count = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Project Revision"
        verbose_name_plural = "Project Revisions"
        unique_together = [('project', 'revision_number')]
        indexes = [
            models.Index(fields=['project', 'revision_number']),
        ]

    def __str__(self):
        return f"Revision {self.revision_number}"


# =============================================================================
# TIMELINE TRACKS
# =============================================================================

class VideoTrack(BaseModel):
    """
    Video track in the timeline. Holds clips, effects, and camera cuts.
    """
    project = models.ForeignKey(
        EditorProject,
        on_delete=models.CASCADE,
        related_name='video_tracks',
    )
    index = models.PositiveIntegerField(help_text="Track order (0 = primary/bottom)")
    name = models.CharField(max_length=255, default="Video")
    enabled = models.BooleanField(default=True, help_text="Include in preview/export")
    visible = models.BooleanField(default=True, help_text="Show in timeline UI")

    class Meta:
        verbose_name = "Video Track"
        verbose_name_plural = "Video Tracks"
        unique_together = [('project', 'index')]
        indexes = [
            models.Index(fields=['project', 'index']),
        ]

    def __str__(self):
        return f"{self.name} (V{self.index})"


class AudioTrack(BaseModel):
    """
    Audio track in the timeline. Holds audio clips and mixing settings.
    """
    project = models.ForeignKey(
        EditorProject,
        on_delete=models.CASCADE,
        related_name='audio_tracks',
    )
    index = models.PositiveIntegerField(help_text="Track order (0 = primary)")
    name = models.CharField(max_length=255, default="Audio")
    enabled = models.BooleanField(default=True, help_text="Include in mix")
    muted = models.BooleanField(default=False)
    volume_db = models.FloatField(default=0.0, help_text="Gain in dB (-inf to +12)")

    class Meta:
        verbose_name = "Audio Track"
        verbose_name_plural = "Audio Tracks"
        unique_together = [('project', 'index')]
        indexes = [
            models.Index(fields=['project', 'index']),
        ]

    def __str__(self):
        return f"{self.name} (A{self.index})"


# =============================================================================
# CLIPS
# =============================================================================

class Clip(BaseModel):
    """
    A clip on a track. Non-destructive: references source_start and source_end.
    """
    track = models.ForeignKey(
        'VideoTrack',
        on_delete=models.CASCADE,
        related_name='clips',
        null=True,
        blank=True,
        help_text="For video clips; null for audio"
    )
    audio_track = models.ForeignKey(
        AudioTrack,
        on_delete=models.CASCADE,
        related_name='clips',
        null=True,
        blank=True,
        help_text="For audio clips; null for video"
    )
    media_asset = models.ForeignKey(
        MediaAsset,
        on_delete=models.CASCADE,
        related_name='editor_clips',
    )

    # Source media range (ms)
    source_start_ms = models.PositiveIntegerField(help_text="Trim start in source")
    source_end_ms = models.PositiveIntegerField(help_text="Trim end in source")

    # Timeline placement (ms)
    timeline_start_ms = models.PositiveIntegerField(help_text="When this clip plays")
    timeline_duration_ms = models.PositiveIntegerField(help_text="How long it plays")

    # Audio properties
    muted = models.BooleanField(default=False)
    volume_db = models.FloatField(default=0.0)
    fade_in_ms = models.PositiveIntegerField(default=0)
    fade_out_ms = models.PositiveIntegerField(default=0)

    # Video properties
    playback_rate = models.FloatField(default=1.0, help_text="1.0 = normal speed")
    disabled = models.BooleanField(default=False, help_text="Hide but don't delete")
    excluded = models.BooleanField(default=False, help_text="Ripple-edit removed")

    class Meta:
        verbose_name = "Clip"
        verbose_name_plural = "Clips"
        indexes = [
            models.Index(fields=['track', 'timeline_start_ms']),
            models.Index(fields=['audio_track', 'timeline_start_ms']),
        ]

    def __str__(self):
        return f"Clip {self.media_asset.label} @ {self.timeline_start_ms}ms"

    def clean(self):
        super().clean()
        if not self.track and not self.audio_track:
            raise ValidationError("Clip must be on either a video or audio track.")
        if self.track and self.audio_track:
            raise ValidationError("Clip cannot be on both video and audio track.")
        if self.source_start_ms >= self.source_end_ms:
            raise ValidationError("source_start_ms must be less than source_end_ms.")

    @property
    def timeline_end_ms(self):
        return self.timeline_start_ms + self.timeline_duration_ms


# =============================================================================
# MULTICAMERA SUPPORT
# =============================================================================

class CameraCut(BaseModel):
    """
    A camera angle selection on the timeline.
    Points to a MediaAsset (camera role) during a time range.
    """
    project = models.ForeignKey(
        EditorProject,
        on_delete=models.CASCADE,
        related_name='camera_cuts',
    )

    # Timeline range
    timeline_start_ms = models.PositiveIntegerField()
    timeline_end_ms = models.PositiveIntegerField()

    # Selected camera (references MediaAsset id, role='camera')
    selected_camera_uuid = models.UUIDField()

    # Source of this cut
    source = models.CharField(
        max_length=20,
        choices=[
            ('manual', 'Manually set'),
            ('automatic', 'Auto-detected'),
            ('suggestion', 'AI suggestion'),
        ],
        default='manual'
    )
    confidence = models.FloatField(
        null=True,
        blank=True,
        help_text="0.0-1.0 for automatic/suggestion cuts"
    )
    user_override = models.BooleanField(
        default=False,
        help_text="User manually changed an automatic cut"
    )
    revision = models.PositiveIntegerField(help_text="Project revision when created")

    class Meta:
        verbose_name = "Camera Cut"
        verbose_name_plural = "Camera Cuts"
        indexes = [
            models.Index(fields=['project', 'timeline_start_ms']),
        ]

    def __str__(self):
        return f"Cut {self.timeline_start_ms}-{self.timeline_end_ms}ms (rev {self.revision})"

    def clean(self):
        super().clean()
        if self.timeline_start_ms >= self.timeline_end_ms:
            raise ValidationError("timeline_start_ms must be less than timeline_end_ms.")


# =============================================================================
# EDIT OPERATIONS
# =============================================================================

class EditOperation(BaseModel):
    """
    A non-destructive timeline edit. Immutable once created.
    Operations are replayed during render or undo.
    """
    project = models.ForeignKey(
        EditorProject,
        on_delete=models.CASCADE,
        related_name='operations',
    )
    revision = models.PositiveIntegerField(help_text="Project revision after this op")

    operation_type = models.CharField(
        max_length=50,
        choices=[
            ('split_clip', 'Split clip'),
            ('trim_clip', 'Trim clip'),
            ('exclude_range', 'Exclude range (ripple)'),
            ('restore_range', 'Restore excluded range'),
            ('move_clip', 'Move clip'),
            ('set_audio_gain', 'Set audio gain'),
            ('set_audio_fade', 'Set audio fade'),
            ('mute_audio', 'Mute/unmute audio'),
            ('disable_video', 'Disable/enable video'),
            ('insert_asset', 'Insert asset'),
            ('remove_asset', 'Remove asset'),
            ('set_camera_angle', 'Set camera angle'),
            ('add_camera_cut', 'Add camera cut'),
            ('remove_camera_cut', 'Remove camera cut'),
            ('add_overlay', 'Add overlay'),
            ('update_overlay', 'Update overlay'),
            ('remove_overlay', 'Remove overlay'),
            ('add_caption', 'Add caption'),
            ('update_caption', 'Update caption'),
            ('remove_caption', 'Remove caption'),
            ('add_marker', 'Add marker'),
            ('delete_marker', 'Delete marker'),
        ]
    )

    # Immutable operation data
    payload = models.JSONField(help_text="Operation parameters")
    inverse_operation = models.JSONField(
        null=True,
        blank=True,
        help_text="Data needed to undo this operation"
    )

    source = models.CharField(
        max_length=20,
        choices=[
            ('manual', 'User action'),
            ('transcript', 'Transcript edit'),
            ('speaker_detection', 'Speaker detection'),
            ('ai_suggestion', 'AI suggestion'),
            ('import', 'Imported from file'),
        ],
        default='manual'
    )

    parent_operation = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_operations',
        help_text="For batched/dependent operations"
    )
    applied = models.BooleanField(default=True, help_text="False if undone")

    class Meta:
        verbose_name = "Edit Operation"
        verbose_name_plural = "Edit Operations"
        indexes = [
            models.Index(fields=['project', 'revision']),
            models.Index(fields=['project', 'applied']),
        ]

    def __str__(self):
        return f"{self.operation_type} (rev {self.revision})"


# =============================================================================
# MEDIA SYNCHRONIZATION
# =============================================================================

class MediaSyncPoint(BaseModel):
    """
    Synchronization anchor between two media assets.
    Used to align multicamera recordings.
    """
    project = models.ForeignKey(
        EditorProject,
        on_delete=models.CASCADE,
        related_name='sync_points',
    )

    asset1 = models.ForeignKey(
        MediaAsset,
        on_delete=models.CASCADE,
        related_name='sync_as_asset1',
    )
    asset2 = models.ForeignKey(
        MediaAsset,
        on_delete=models.CASCADE,
        related_name='sync_as_asset2',
    )

    # Time in each asset where they should be synchronized
    asset1_time_ms = models.PositiveIntegerField()
    asset2_time_ms = models.PositiveIntegerField()

    sync_method = models.CharField(
        max_length=20,
        choices=[
            ('manual', 'Manually entered'),
            ('waveform', 'Waveform correlation'),
            ('timecode', 'Embedded timecode'),
            ('marker', 'Shared clap/marker'),
        ],
        default='manual'
    )
    confidence = models.FloatField(
        null=True,
        blank=True,
        help_text="0.0-1.0 for automatic methods"
    )

    class Meta:
        verbose_name = "Media Sync Point"
        verbose_name_plural = "Media Sync Points"
        unique_together = [('asset1', 'asset2')]
        indexes = [
            models.Index(fields=['project']),
        ]

    def __str__(self):
        return f"Sync {self.asset1.label} <-> {self.asset2.label}"


# =============================================================================
# PROXY MEDIA
# =============================================================================

class MediaProxy(BaseModel):
    """
    Lower-resolution or proxy version of a source MediaAsset.
    Used for browser preview; original used for final render.
    """
    source_asset = models.ForeignKey(
        MediaAsset,
        on_delete=models.CASCADE,
        related_name='proxies',
    )

    proxy_type = models.CharField(
        max_length=20,
        choices=[
            ('video', 'Video proxy'),
            ('audio', 'Audio proxy'),
            ('waveform', 'Waveform data'),
            ('thumbnails', 'Thumbnail grid'),
        ]
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Queued'),
            ('processing', 'In progress'),
            ('ready', 'Complete'),
            ('failed', 'Failed'),
            ('cancelled', 'Cancelled'),
        ],
        default='pending'
    )

    file = models.FileField(
        upload_to='proxies/%Y/%m/%d/',
        null=True,
        blank=True,
        help_text="Proxy file (video/audio) or JSON (waveform)"
    )
    error_message = models.TextField(blank=True)
    quality_preset = models.CharField(
        max_length=20,
        default='720p',
        help_text="Resolution or quality level"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Media Proxy"
        verbose_name_plural = "Media Proxies"
        unique_together = [('source_asset', 'proxy_type')]
        indexes = [
            models.Index(fields=['source_asset', 'proxy_type']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.get_proxy_type_display()} for {self.source_asset.label}"


# =============================================================================
# GRAPHICS & OVERLAYS
# =============================================================================

class GraphicOverlay(BaseModel):
    """
    Visual element on top of video: logo, lower third, title, etc.
    """
    project = models.ForeignKey(
        EditorProject,
        on_delete=models.CASCADE,
        related_name='overlays',
    )

    overlay_type = models.CharField(
        max_length=30,
        choices=[
            ('logo', 'Logo'),
            ('lower_third', 'Lower third'),
            ('title', 'Title card'),
            ('background', 'Background'),
            ('watermark', 'Watermark'),
            ('image', 'Full-screen image'),
            ('graphic', 'Custom graphic'),
        ]
    )

    # Timeline range
    timeline_start_ms = models.PositiveIntegerField()
    timeline_end_ms = models.PositiveIntegerField()

    # Content: either asset or text
    asset = models.ForeignKey(
        MediaAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='overlay_uses',
    )
    text_content = models.CharField(max_length=1000, null=True, blank=True)

    # Positioning and sizing
    position_x = models.IntegerField(default=0, help_text="X position in pixels")
    position_y = models.IntegerField(default=0, help_text="Y position in pixels")
    width = models.PositiveIntegerField(help_text="Width in pixels")
    height = models.PositiveIntegerField(help_text="Height in pixels")

    # Effects
    opacity = models.FloatField(default=1.0, help_text="0.0-1.0")
    z_index = models.IntegerField(default=0, help_text="Layer order")
    fade_in_ms = models.PositiveIntegerField(default=0)
    fade_out_ms = models.PositiveIntegerField(default=0)

    # Style reference
    template_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Template identifier for styling"
    )

    class Meta:
        verbose_name = "Graphic Overlay"
        verbose_name_plural = "Graphic Overlays"
        indexes = [
            models.Index(fields=['project', 'timeline_start_ms']),
        ]

    def __str__(self):
        return f"{self.get_overlay_type_display()} @ {self.timeline_start_ms}ms"


# =============================================================================
# CAPTIONS
# =============================================================================

class CaptionCue(BaseModel):
    """
    Caption text for a time range. Can be burned into video or exported as .vtt.
    """
    project = models.ForeignKey(
        EditorProject,
        on_delete=models.CASCADE,
        related_name='captions',
    )

    timeline_start_ms = models.PositiveIntegerField()
    timeline_end_ms = models.PositiveIntegerField()

    text = models.TextField(help_text="Caption text (UTF-8)")
    speaker = models.CharField(max_length=255, null=True, blank=True)
    auto_generated = models.BooleanField(default=False)
    burned_in = models.BooleanField(default=False, help_text="Include in video export")

    class Meta:
        verbose_name = "Caption Cue"
        verbose_name_plural = "Caption Cues"
        indexes = [
            models.Index(fields=['project', 'timeline_start_ms']),
        ]

    def __str__(self):
        preview = self.text[:50]
        return f"Caption @ {self.timeline_start_ms}ms: {preview}"


# =============================================================================
# MARKERS & NOTES
# =============================================================================

class EditorMarker(BaseModel):
    """
    Temporal bookmark or flag on the timeline.
    """
    project = models.ForeignKey(
        EditorProject,
        on_delete=models.CASCADE,
        related_name='markers',
    )

    timeline_position_ms = models.PositiveIntegerField()
    label = models.CharField(max_length=255)
    color = models.CharField(
        max_length=7,
        default='#FF0000',
        help_text="Hex color code"
    )

    class Meta:
        verbose_name = "Editor Marker"
        verbose_name_plural = "Editor Markers"
        indexes = [
            models.Index(fields=['project', 'timeline_position_ms']),
        ]

    def __str__(self):
        return f"Marker: {self.label} @ {self.timeline_position_ms}ms"


class EditorNote(BaseModel):
    """
    Timestamped note or comment in the project.
    """
    project = models.ForeignKey(
        EditorProject,
        on_delete=models.CASCADE,
        related_name='notes',
    )

    title = models.CharField(max_length=255)
    content = models.TextField()
    timeline_position_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional reference timestamp"
    )

    class Meta:
        verbose_name = "Editor Note"
        verbose_name_plural = "Editor Notes"
        indexes = [
            models.Index(fields=['project']),
        ]

    def __str__(self):
        return f"Note: {self.title}"


# =============================================================================
# EXPORT CONFIGURATION & JOBS
# =============================================================================

class ExportPreset(BaseModel):
    """
    Template for export settings (video codec, bitrate, etc.).
    """
    project = models.ForeignKey(
        EditorProject,
        on_delete=models.CASCADE,
        related_name='export_presets',
    )

    name = models.CharField(max_length=255, help_text="e.g., 'Full Podcast 1080p'")
    description = models.TextField(blank=True)

    # Container
    container = models.CharField(
        max_length=20,
        choices=[
            ('mp4', 'MP4'),
            ('mov', 'MOV'),
            ('webm', 'WebM'),
            ('mkv', 'Matroska'),
        ],
        default='mp4'
    )

    # Video
    video_codec = models.CharField(
        max_length=20,
        choices=[
            ('h264', 'H.264/AVC'),
            ('h265', 'H.265/HEVC'),
            ('vp9', 'VP9'),
        ],
        default='h264'
    )
    video_bitrate_kbps = models.PositiveIntegerField(default=5000)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    frame_rate = models.PositiveIntegerField(default=30)

    # Audio
    audio_codec = models.CharField(
        max_length=20,
        choices=[
            ('aac', 'AAC'),
            ('mp3', 'MP3'),
            ('opus', 'Opus'),
        ],
        default='aac'
    )
    audio_bitrate_kbps = models.PositiveIntegerField(default=128)
    audio_channels = models.PositiveIntegerField(
        choices=[(1, 'Mono'), (2, 'Stereo')],
        default=2
    )

    # Loudness
    loudness_preset = models.CharField(
        max_length=50,
        default='PODCAST_STEREO',
        help_text="Loudness normalization profile"
    )

    class Meta:
        verbose_name = "Export Preset"
        verbose_name_plural = "Export Presets"
        indexes = [
            models.Index(fields=['project']),
        ]

    def __str__(self):
        return f"{self.name} ({self.container.upper()})"


class ExportedMedia(BaseModel):
    """
    Rendered output from a project revision using an export preset.
    """
    project = models.ForeignKey(
        EditorProject,
        on_delete=models.CASCADE,
        related_name='exports',
    )
    revision = models.PositiveIntegerField(
        help_text="Project revision used for this export"
    )
    export_preset = models.ForeignKey(
        ExportPreset,
        on_delete=models.SET_NULL,
        null=True,
        related_name='exports',
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ('queued', 'Queued'),
            ('processing', 'Processing'),
            ('ready', 'Ready'),
            ('failed', 'Failed'),
            ('cancelled', 'Cancelled'),
        ],
        default='queued'
    )

    output_file = models.FileField(
        upload_to='exports/%Y/%m/%d/',
        null=True,
        blank=True,
        help_text="Final rendered media file"
    )

    # Progress and metadata
    progress_percent = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    file_size_bytes = models.BigIntegerField(null=True, blank=True)

    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Exported Media"
        verbose_name_plural = "Exported Media"
        indexes = [
            models.Index(fields=['project', 'revision']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Export: {self.project.episode.title} (rev {self.revision})"


# =============================================================================
# SOCIAL CLIPS
# =============================================================================

class SocialClip(BaseModel):
    """
    A marked excerpt of the main timeline for social media posting.
    """
    project = models.ForeignKey(
        EditorProject,
        on_delete=models.CASCADE,
        related_name='social_clips',
    )
    revision = models.PositiveIntegerField(help_text="Project revision for render")

    timeline_start_ms = models.PositiveIntegerField()
    timeline_end_ms = models.PositiveIntegerField()

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    aspect_ratio = models.CharField(
        max_length=10,
        choices=[
            ('16:9', '16:9 Landscape'),
            ('9:16', '9:16 Vertical'),
            ('1:1', '1:1 Square'),
        ],
        default='16:9'
    )

    template_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Layout template identifier"
    )

    export_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Not exported'),
            ('ready', 'Ready'),
            ('failed', 'Export failed'),
        ],
        default='pending'
    )

    class Meta:
        verbose_name = "Social Clip"
        verbose_name_plural = "Social Clips"
        indexes = [
            models.Index(fields=['project']),
        ]

    def __str__(self):
        return f"Social: {self.title} ({self.aspect_ratio})"


# =============================================================================
# PROCESSING JOBS
# =============================================================================

class ProcessingJob(BaseModel):
    """
    Background job for media processing, rendering, or other async work.
    """
    job_type = models.CharField(
        max_length=50,
        choices=[
            ('probe_media', 'Probe media file'),
            ('create_proxy_video', 'Create video proxy'),
            ('create_proxy_audio', 'Create audio proxy'),
            ('generate_waveform', 'Generate waveform'),
            ('generate_thumbnails', 'Generate thumbnails'),
            ('synchronize_media', 'Synchronize media'),
            ('render_video', 'Render video'),
            ('render_audio', 'Render audio'),
            ('render_social_clip', 'Render social clip'),
            ('generate_transcription', 'Generate transcription'),
            ('detect_speakers', 'Detect speakers'),
            ('suggest_camera_cuts', 'Suggest camera cuts'),
        ]
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ('queued', 'Queued'),
            ('processing', 'In progress'),
            ('completed', 'Complete'),
            ('failed', 'Failed'),
            ('cancelled', 'Cancelled'),
        ],
        default='queued'
    )

    # Related objects
    editor_project = models.ForeignKey(
        EditorProject,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='processing_jobs',
    )
    media_asset = models.ForeignKey(
        MediaAsset,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='processing_jobs',
    )

    # Job data
    input_data = models.JSONField(help_text="Job parameters")
    output_data = models.JSONField(null=True, blank=True, help_text="Job results")

    # Progress and metadata
    progress_percent = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)

    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Processing Job"
        verbose_name_plural = "Processing Jobs"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['editor_project', 'job_type']),
            models.Index(fields=['media_asset']),
        ]

    def __str__(self):
        return f"{self.get_job_type_display()} - {self.get_status_display()}"


# =============================================================================
# AI SUGGESTIONS & PROVIDERS
# =============================================================================

class AISuggestion(BaseModel):
    """
    AI-generated suggestion (camera cuts, captions, etc.) pending user review.
    """
    project = models.ForeignKey(
        EditorProject,
        on_delete=models.CASCADE,
        related_name='ai_suggestions',
    )

    suggestion_type = models.CharField(
        max_length=50,
        choices=[
            ('camera_cut', 'Camera cut'),
            ('caption', 'Caption'),
            ('silence_cut', 'Silence removal'),
            ('filler_phrase', 'Filler phrase'),
            ('speaker_label', 'Speaker label'),
        ]
    )

    suggestion_data = models.JSONField(help_text="Proposed edit data")
    confidence = models.FloatField(help_text="0.0-1.0 confidence score")

    # Acceptance tracking
    accepted = models.BooleanField(default=False)
    rejected = models.BooleanField(default=False)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accepted_suggestions',
    )

    # Provenance
    ai_provider = models.CharField(max_length=100, blank=True)
    ai_model = models.CharField(max_length=100, blank=True)
    prompt_template = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "AI Suggestion"
        verbose_name_plural = "AI Suggestions"
        indexes = [
            models.Index(fields=['project', 'suggestion_type']),
            models.Index(fields=['accepted']),
        ]

    def __str__(self):
        return f"{self.get_suggestion_type_display()} suggestion"


class AIProviderConfiguration(BaseModel):
    """
    Configuration for an AI provider (Higgsfield, etc.).
    Secrets are never returned to the browser.
    """
    organization = models.UUIDField(help_text="Organization UUID for scoping")
    provider_name = models.CharField(max_length=100)
    api_key = models.CharField(max_length=1000, help_text="Encrypted secret")
    api_endpoint = models.URLField(max_length=2000, blank=True)
    enabled = models.BooleanField(default=True)
    capabilities = models.JSONField(
        default=list,
        help_text="List of capabilities this provider supports"
    )

    class Meta:
        verbose_name = "AI Provider Configuration"
        verbose_name_plural = "AI Provider Configurations"
        unique_together = [('organization', 'provider_name')]
        indexes = [
            models.Index(fields=['organization', 'enabled']),
        ]

    def __str__(self):
        return f"{self.provider_name}"
