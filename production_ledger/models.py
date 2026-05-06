"""
Data models for Production Ledger.

All models use UUID primary keys and include organization_uuid for multi-tenancy.
Every model includes created_by/updated_by and timestamps for auditability.
"""
import hashlib
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .constants import (
    ApprovalStatus,
    ArtifactType,
    AssetType,
    ClipPriority,
    DEFAULT_CHECKLIST_ITEMS,
    DistributionStatus,
    EpisodeStatus,
    GuestRole,
    IngestionStatus,
    MediaPlatform,
    PodcastPlatform,
    QuoteApproval,
    RecordingContext,
    Role,
    SegmentOwner,
    ShortAspectRatio,
    ShortStatus,
    SourceType,
    TranscriptFormat,
    TranscriptSourceType,
)


# =============================================================================
# BASE MODEL
# =============================================================================

class BaseModel(models.Model):
    """
    Abstract base model with UUID primary key, organization scoping, and audit fields.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization_uuid = models.UUIDField(db_index=True, help_text="Organization UUID for multi-tenancy")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_updated",
    )

    class Meta:
        abstract = True


# =============================================================================
# SHOW
# =============================================================================

class Show(BaseModel):
    """
    A podcast show/series. Contains branding and default content.
    """
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    
    # Branding
    brand_primary_color = models.CharField(max_length=7, blank=True, help_text="Hex color code, e.g. #FF5733")
    default_intro_text = models.TextField(blank=True, help_text="Default intro text for episodes")
    default_outro_text = models.TextField(blank=True, help_text="Default outro text for episodes")
    
    class Meta:
        verbose_name = "Show"
        verbose_name_plural = "Shows"
        indexes = [
            models.Index(fields=['organization_uuid', 'slug']),
        ]
        unique_together = [['organization_uuid', 'slug']]

    def __str__(self):
        return self.name


# =============================================================================
# EPISODE TYPE (Data-Driven)
# =============================================================================

class EpisodeType(models.Model):
    """
    Data-driven episode types that can be customized per organization.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization_uuid = models.UUIDField(
        db_index=True, 
        null=True, 
        blank=True,
        help_text="Organization UUID. Null means it's a global/default type."
    )
    
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    color = models.CharField(
        max_length=7, 
        blank=True, 
        default='#6B7280',
        help_text="Hex color for UI display, e.g. #3B82F6"
    )
    icon = models.CharField(
        max_length=50, 
        blank=True,
        help_text="Emoji or icon identifier"
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Episode Type"
        verbose_name_plural = "Episode Types"
        ordering = ['sort_order', 'name']
        unique_together = [['organization_uuid', 'slug']]
    
    def __str__(self):
        return self.name
    
    @classmethod
    def get_default_types(cls):
        """Return the default episode types to seed on first install."""
        return [
            {
                'name': 'Global',
                'slug': 'global',
                'description': 'Global perspective episodes covering worldwide AI developments',
                'color': '#3B82F6',  # Blue
                'icon': '🌍',
                'sort_order': 1,
            },
            {
                'name': 'Ops',
                'slug': 'ops',
                'description': 'Operations and implementation focused episodes',
                'color': '#10B981',  # Green
                'icon': '⚙️',
                'sort_order': 2,
            },
            {
                'name': 'Ethics',
                'slug': 'ethics',
                'description': 'AI ethics, policy, and responsible AI discussions',
                'color': '#8B5CF6',  # Purple
                'icon': '⚖️',
                'sort_order': 3,
            },
            {
                'name': 'Interview',
                'slug': 'interview',
                'description': 'Guest interview format episodes',
                'color': '#F59E0B',  # Amber
                'icon': '🎤',
                'sort_order': 4,
            },
            {
                'name': 'Deep Dive',
                'slug': 'deep-dive',
                'description': 'In-depth technical or topic exploration',
                'color': '#EF4444',  # Red
                'icon': '🔬',
                'sort_order': 5,
            },
            {
                'name': 'News Roundup',
                'slug': 'news-roundup',
                'description': 'Weekly or periodic news summary episodes',
                'color': '#06B6D4',  # Cyan
                'icon': '📰',
                'sort_order': 6,
            },
            {
                'name': 'Other',
                'slug': 'other',
                'description': 'Other episode formats',
                'color': '#6B7280',  # Gray
                'icon': '📋',
                'sort_order': 99,
            },
        ]
    
    @classmethod
    def seed_defaults(cls, organization_uuid=None):
        """
        Seed default episode types. Can be called for global defaults (org=None)
        or for a specific organization.
        """
        created_types = []
        for type_data in cls.get_default_types():
            obj, created = cls.objects.get_or_create(
                organization_uuid=organization_uuid,
                slug=type_data['slug'],
                defaults=type_data
            )
            if created:
                created_types.append(obj)
        return created_types
    
    @classmethod
    def get_for_organization(cls, organization_uuid):
        """
        Get episode types available for an organization.
        Returns org-specific types if they exist, otherwise global defaults.
        """
        org_types = cls.objects.filter(
            organization_uuid=organization_uuid,
            is_active=True
        )
        if org_types.exists():
            return org_types
        # Fall back to global defaults
        return cls.objects.filter(
            organization_uuid__isnull=True,
            is_active=True
        )


# =============================================================================
# EPISODE
# =============================================================================

class Episode(BaseModel):
    """
    A single episode of a show. Tracks workflow status and metadata.
    """
    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name='episodes')
    title = models.CharField(max_length=500)
    
    episode_type = models.ForeignKey(
        EpisodeType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='episodes',
        help_text="Type/format of the episode"
    )
    target_minutes = models.PositiveIntegerField(default=45)
    recording_context = models.CharField(
        max_length=20,
        choices=RecordingContext.CHOICES,
        default=RecordingContext.REMOTE,
    )
    
    # Workflow status
    status = models.CharField(
        max_length=20,
        choices=EpisodeStatus.CHOICES,
        default=EpisodeStatus.DRAFT,
    )
    
    # Scheduling
    scheduled_for = models.DateTimeField(null=True, blank=True)
    publish_date = models.DateField(null=True, blank=True)
    
    # Live notes (for Control Room)
    live_notes = models.TextField(blank=True, help_text="Notes captured during recording")

    class Meta:
        verbose_name = "Episode"
        verbose_name_plural = "Episodes"
        indexes = [
            models.Index(fields=['organization_uuid', 'show']),
            models.Index(fields=['organization_uuid', 'status']),
            models.Index(fields=['organization_uuid', 'scheduled_for']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.show.name}: {self.title}"

    def can_transition_to(self, new_status):
        """Check if status transition is allowed."""
        allowed = EpisodeStatus.TRANSITIONS.get(self.status, [])
        return new_status in allowed

    def transition_to(self, new_status, user=None):
        """
        Transition episode to a new status.
        Raises ValidationError if transition is not allowed.
        """
        if not self.can_transition_to(new_status):
            raise ValidationError(
                f"Cannot transition from '{self.status}' to '{new_status}'. "
                f"Allowed transitions: {EpisodeStatus.TRANSITIONS.get(self.status, [])}"
            )
        
        # Check if checklist is required
        if new_status in EpisodeStatus.REQUIRES_CHECKLIST:
            if not self.is_checklist_complete():
                raise ValidationError(
                    f"Cannot transition to '{new_status}' until all required checklist items are complete."
                )
        
        self.status = new_status
        if user:
            self.updated_by = user
        self.save()

    def is_checklist_complete(self):
        """Check if all required checklist items are complete."""
        required_incomplete = self.checklist_items.filter(
            is_required=True,
            is_done=False
        ).exists()
        return not required_incomplete

    def seed_checklist(self):
        """Create default checklist items for this episode."""
        for item_data in DEFAULT_CHECKLIST_ITEMS:
            ChecklistItem.objects.get_or_create(
                episode=self,
                organization_uuid=self.organization_uuid,
                title=item_data['title'],
                defaults={
                    'is_required': item_data['is_required'],
                    'sort_order': item_data['sort_order'],
                }
            )


# =============================================================================
# SHOW ROLE ASSIGNMENT (RBAC)
# =============================================================================

class ShowRoleAssignment(models.Model):
    """
    Assigns a role to a user for a specific show.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name='role_assignments')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='show_roles',
    )
    role = models.CharField(max_length=20, choices=Role.CHOICES)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='role_assignments_created',
    )

    class Meta:
        verbose_name = "Show Role Assignment"
        verbose_name_plural = "Show Role Assignments"
        unique_together = [['show', 'user']]
        indexes = [
            models.Index(fields=['show', 'role']),
            models.Index(fields=['user', 'role']),
        ]

    def __str__(self):
        return f"{self.user} - {self.role} on {self.show.name}"


class ShowJoinRequest(models.Model):
    """
    Request by a signed-in user to join a specific show with a target role.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name='join_requests')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='show_join_requests',
    )
    desired_role = models.CharField(max_length=20, choices=Role.CHOICES, default=Role.GUEST)
    message = models.TextField(blank=True, default='')

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_show_join_requests',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Show Join Request'
        verbose_name_plural = 'Show Join Requests'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['show', 'status']),
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f"{self.user} -> {self.show.name} ({self.desired_role}, {self.status})"


class EpisodeRoleOverride(models.Model):
    """
    Optional: Override a user's role for a specific episode.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='role_overrides')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='episode_role_overrides',
    )
    role = models.CharField(max_length=20, choices=Role.CHOICES)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Episode Role Override"
        verbose_name_plural = "Episode Role Overrides"
        unique_together = [['episode', 'user']]

    def __str__(self):
        return f"{self.user} - {self.role} on {self.episode.title}"


# =============================================================================
# SEGMENT (Run of Show)
# =============================================================================

class Segment(BaseModel):
    """
    A segment in the run of show for an episode.
    """
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='segments')
    
    order = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=255)
    purpose = models.TextField(blank=True)
    timebox_minutes = models.PositiveIntegerField(default=5)
    
    owner_role = models.CharField(
        max_length=20,
        choices=SegmentOwner.CHOICES,
        default=SegmentOwner.HOST,
    )
    
    bullet_prompts = models.TextField(blank=True, help_text="Bullet points for this segment")
    key_questions = models.TextField(blank=True, help_text="Key questions to cover")

    # Live recording tracking
    is_completed = models.BooleanField(default=False, help_text="Marked complete during live recording")
    completed_at = models.DateTimeField(null=True, blank=True, help_text="When this segment was marked complete")
    live_notes = models.TextField(blank=True, help_text="Notes captured during live recording of this segment")

    class Meta:
        verbose_name = "Segment"
        verbose_name_plural = "Segments"
        ordering = ['order']
        indexes = [
            models.Index(fields=['organization_uuid', 'episode']),
        ]

    def __str__(self):
        return f"{self.episode.title} - Segment {self.order}: {self.title}"


# =============================================================================
# GUEST
# =============================================================================

class Guest(BaseModel):
    """
    A guest who can appear on episodes.
    """
    name = models.CharField(max_length=255)
    title = models.CharField(max_length=255, blank=True, help_text="Job title")
    org = models.CharField(max_length=255, blank=True, help_text="Organization")
    bio = models.TextField(blank=True)
    
    # Contact info
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    
    links = models.JSONField(default=dict, blank=True, help_text="Social/web links as JSON")
    timezone = models.CharField(max_length=50, blank=True, help_text="e.g., America/Los_Angeles")
    
    consent_audio = models.BooleanField(default=False)
    consent_video = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Guest"
        verbose_name_plural = "Guests"
        indexes = [
            models.Index(fields=['organization_uuid', 'name']),
        ]

    def __str__(self):
        return f"{self.name} ({self.org})" if self.org else self.name


# =============================================================================
# EPISODE GUEST (Join Table)
# =============================================================================

class EpisodeGuest(BaseModel):
    """
    Links a guest to an episode with episode-specific metadata.
    """
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='episode_guests')
    guest = models.ForeignKey(Guest, on_delete=models.CASCADE, related_name='episode_appearances')
    
    role = models.CharField(
        max_length=20,
        choices=GuestRole.CHOICES,
        default=GuestRole.GUEST,
    )
    
    prep_notes = models.TextField(blank=True, help_text="Preparation notes for this guest")
    key_topics = models.TextField(blank=True, help_text="Key topics to cover with this guest")
    no_go_topics = models.TextField(blank=True, help_text="Topics to avoid")
    
    quote_approval_status = models.CharField(
        max_length=20,
        choices=QuoteApproval.CHOICES,
        default=QuoteApproval.PENDING,
    )

    class Meta:
        verbose_name = "Episode Guest"
        verbose_name_plural = "Episode Guests"
        unique_together = [['episode', 'guest']]
        indexes = [
            models.Index(fields=['organization_uuid', 'episode']),
        ]

    def __str__(self):
        return f"{self.guest.name} on {self.episode.title}"


# =============================================================================
# MEDIA ASSET
# =============================================================================

def media_upload_path(instance, filename):
    """Generate upload path for media files."""
    return f"media_assets/{instance.organization_uuid}/{instance.episode_id}/{filename}"


class MediaAsset(BaseModel):
    """
    A media file (audio/video) associated with an episode.
    Supports both local uploads and links to external platforms.
    Maintains chain of custody with checksums and audit fields.
    """
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='media_assets')
    
    asset_type = models.CharField(max_length=20, choices=AssetType.CHOICES)
    source_type = models.CharField(max_length=20, choices=SourceType.CHOICES)
    
    # Platform for external links (YouTube, Riverside, etc.)
    platform = models.CharField(
        max_length=30,
        choices=MediaPlatform.CHOICES_FLAT,
        blank=True,
        help_text="Source platform for external links"
    )
    
    # File or external link (one must be provided)
    file = models.FileField(upload_to=media_upload_path, null=True, blank=True)
    external_url = models.URLField(max_length=2000, null=True, blank=True)
    
    # User-friendly label
    label = models.CharField(max_length=200, blank=True, help_text="Display name for this asset")
    
    # Metadata
    filename = models.CharField(max_length=500, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    recorded_at = models.DateTimeField(null=True, blank=True)
    
    # Ingestion tracking
    ingested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='ingested_media',
    )
    ingestion_status = models.CharField(
        max_length=20,
        choices=IngestionStatus.CHOICES,
        default=IngestionStatus.PENDING,
    )
    error_message = models.TextField(blank=True)

    class Meta:
        verbose_name = "Media Asset"
        verbose_name_plural = "Media Assets"
        indexes = [
            models.Index(fields=['organization_uuid', 'episode']),
            models.Index(fields=['organization_uuid', 'checksum_sha256']),
        ]

    def __str__(self):
        display = self.label or self.filename or self.external_url
        return f"{self.get_asset_type_display()} - {display}"

    def clean(self):
        """Validate that either file or external_url is provided, not both."""
        if self.source_type == SourceType.UPLOAD and not self.file:
            raise ValidationError("File is required for upload source type.")
        if self.source_type in (SourceType.EXTERNAL_LINK, SourceType.API_IMPORT) and not self.external_url:
            raise ValidationError("External URL is required for external link source type.")
        if self.file and self.external_url:
            raise ValidationError("Provide either file or external URL, not both.")

    @classmethod
    def detect_platform_from_url(cls, url):
        """Auto-detect platform from URL patterns."""
        if not url:
            return MediaPlatform.DIRECT_URL
        url_lower = url.lower()
        for platform, patterns in MediaPlatform.URL_PATTERNS.items():
            for pattern in patterns:
                if pattern in url_lower:
                    return platform
        return MediaPlatform.DIRECT_URL

    def compute_checksum(self):
        """Compute SHA256 checksum of the file."""
        if not self.file:
            return None
        
        sha256_hash = hashlib.sha256()
        self.file.seek(0)
        for chunk in iter(lambda: self.file.read(8192), b""):
            sha256_hash.update(chunk)
        self.file.seek(0)
        return sha256_hash.hexdigest()

    def save(self, *args, **kwargs):
        # Compute checksum on save if file is provided and checksum is empty
        if self.file and not self.checksum_sha256:
            self.checksum_sha256 = self.compute_checksum()
        super().save(*args, **kwargs)


# =============================================================================
# TRANSCRIPT
# =============================================================================

class Transcript(BaseModel):
    """
    A transcript of an episode. First-class artifact with versioning.
    """
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='transcripts')
    
    source_type = models.CharField(max_length=20, choices=TranscriptSourceType.CHOICES)
    format = models.CharField(max_length=10, choices=TranscriptFormat.CHOICES, default=TranscriptFormat.TXT)
    
    raw_text = models.TextField(help_text="Raw transcript text")
    normalized_json = models.JSONField(
        null=True, 
        blank=True, 
        help_text="Normalized JSON with speaker blocks and timestamps"
    )
    
    confidence_overall = models.FloatField(null=True, blank=True, help_text="Overall confidence score 0-1")
    revision = models.PositiveIntegerField(default=1)
    
    # Provenance
    created_from_media_asset = models.ForeignKey(
        MediaAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transcripts',
    )
    ingested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='ingested_transcripts',
    )

    class Meta:
        verbose_name = "Transcript"
        verbose_name_plural = "Transcripts"
        ordering = ['-revision']
        indexes = [
            models.Index(fields=['organization_uuid', 'episode']),
        ]

    def __str__(self):
        return f"Transcript v{self.revision} for {self.episode.title}"


# =============================================================================
# CLIP MOMENT
# =============================================================================

class ClipMoment(BaseModel):
    """
    A marked moment/clip within an episode, tied to timestamps.
    """
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='clip_moments')
    transcript = models.ForeignKey(
        Transcript,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='clip_moments',
    )
    
    start_ms = models.PositiveIntegerField(help_text="Start time in milliseconds")
    end_ms = models.PositiveIntegerField(help_text="End time in milliseconds")
    
    title = models.CharField(max_length=255)
    hook = models.CharField(max_length=500, blank=True, help_text="Hook/teaser text")
    caption_draft = models.TextField(blank=True, help_text="Draft caption for social")
    
    tags = models.JSONField(default=list, blank=True, help_text="List of tags")
    priority = models.CharField(
        max_length=20,
        choices=ClipPriority.CHOICES,
        default=ClipPriority.SILVER,
    )

    class Meta:
        verbose_name = "Clip Moment"
        verbose_name_plural = "Clip Moments"
        ordering = ['start_ms']
        indexes = [
            models.Index(fields=['organization_uuid', 'episode']),
            models.Index(fields=['organization_uuid', 'priority']),
        ]

    def __str__(self):
        return f"{self.title} ({self.start_ms}ms - {self.end_ms}ms)"

    @property
    def duration_ms(self):
        return self.end_ms - self.start_ms

    @property
    def start_formatted(self):
        """Format start time as HH:MM:SS."""
        seconds = self.start_ms // 1000
        return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"

    @property
    def end_formatted(self):
        """Format end time as HH:MM:SS."""
        seconds = self.end_ms // 1000
        return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


# =============================================================================
# AI ARTIFACT (Provenance + Approval)
# =============================================================================

class AIArtifact(BaseModel):
    """
    An AI-generated artifact with full provenance and approval workflow.
    
    AI output is NEVER written directly into final content. AI outputs must be
    stored as separate AIArtifact objects with full provenance, then explicitly
    approved and copied into final fields.
    """
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='ai_artifacts')
    
    artifact_type = models.CharField(max_length=30, choices=ArtifactType.CHOICES)
    
    # Input provenance
    input_prompt = models.TextField(help_text="The prompt sent to the AI")
    input_context_refs = models.JSONField(
        default=dict,
        help_text="References to input data: transcript_id, clip_ids, etc."
    )
    
    # Output
    output_text = models.TextField(help_text="The AI-generated output")
    
    # AI provider metadata
    provider = models.CharField(max_length=50, help_text="AI provider name")
    model = models.CharField(max_length=100, help_text="Model identifier")
    params = models.JSONField(default=dict, help_text="Parameters: temperature, etc.")
    
    # Approval workflow
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.CHOICES,
        default=ApprovalStatus.PENDING,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_artifacts',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Transparency
    transparency_summary = models.CharField(
        max_length=255,
        blank=True,
        help_text="Short label shown in UI for transparency"
    )
    notes = models.TextField(blank=True, help_text="Reviewer notes")

    class Meta:
        verbose_name = "AI Artifact"
        verbose_name_plural = "AI Artifacts"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization_uuid', 'episode']),
            models.Index(fields=['organization_uuid', 'artifact_type']),
            models.Index(fields=['organization_uuid', 'approval_status']),
        ]

    def __str__(self):
        return f"{self.artifact_type} for {self.episode.title} ({self.approval_status})"

    def approve(self, user):
        """Approve this artifact."""
        self.approval_status = ApprovalStatus.APPROVED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()

    def reject(self, user, notes=''):
        """Reject this artifact."""
        self.approval_status = ApprovalStatus.REJECTED
        self.approved_by = user
        self.approved_at = timezone.now()
        if notes:
            self.notes = notes
        self.save()


# =============================================================================
# SHOW NOTE DRAFT
# =============================================================================

class ShowNoteDraft(BaseModel):
    """
    A draft of show notes, potentially created from an AI artifact.
    """
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='show_note_drafts')
    
    markdown = models.TextField(help_text="Show notes in Markdown format")
    chapters_json = models.JSONField(null=True, blank=True, help_text="Chapter markers as JSON")
    resources_json = models.JSONField(null=True, blank=True, help_text="Resources/links as JSON")
    
    # Provenance
    created_from_ai_artifact = models.ForeignKey(
        AIArtifact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='show_note_drafts',
    )

    class Meta:
        verbose_name = "Show Note Draft"
        verbose_name_plural = "Show Note Drafts"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization_uuid', 'episode']),
        ]

    def __str__(self):
        return f"Draft for {self.episode.title}"


# =============================================================================
# PODCAST FEED CONFIG (per-Show)
# =============================================================================

class PodcastFeedConfig(BaseModel):
    """
    Podcast RSS feed configuration for a Show.
    One per show. The generated RSS feed is hosted on DO Spaces and submitted
    to podcast directories.
    """
    show = models.OneToOneField(Show, on_delete=models.CASCADE, related_name='podcast_feed_config')

    # Feed metadata
    feed_title = models.CharField(max_length=255, blank=True, help_text="Podcast title (defaults to show name)")
    feed_description = models.TextField(blank=True, help_text="Podcast description / summary")
    feed_language = models.CharField(max_length=10, default='en', help_text="BCP-47 language code, e.g. 'en'")
    author_name = models.CharField(max_length=255, blank=True)
    author_email = models.EmailField(blank=True)
    category = models.CharField(max_length=100, default='Technology', help_text="iTunes top-level category")
    subcategory = models.CharField(max_length=100, blank=True)
    explicit = models.BooleanField(default=False)
    website_url = models.URLField(blank=True)

    # Cover art (DO Spaces public URL)
    cover_art_url = models.URLField(blank=True, help_text="Podcast cover art (min 1400×1400 px, max 3000×3000 px)")

    # DO Spaces path where feed XML is stored
    feed_spaces_key = models.CharField(max_length=500, blank=True, help_text="Key/path within the DO Spaces bucket")
    feed_public_url = models.URLField(blank=True, help_text="Public CDN URL of the RSS feed XML")

    # Timestamps
    feed_last_built = models.DateTimeField(null=True, blank=True, help_text="When the feed was last re-built and uploaded")

    class Meta:
        verbose_name = "Podcast Feed Config"
        verbose_name_plural = "Podcast Feed Configs"

    def __str__(self):
        return f"Feed config for {self.show.name}"


# =============================================================================
# PODCAST DISTRIBUTION (per-Episode, per-Platform)
# =============================================================================

class PodcastDistribution(BaseModel):
    """
    Tracks the distribution status of an episode on each podcast platform.
    When the episode RSS item is published and the feed is re-built, each
    platform entry moves to SUBMITTED then eventually LIVE.
    """
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='distributions')
    platform = models.CharField(max_length=30, choices=PodcastPlatform.CHOICES)

    status = models.CharField(
        max_length=20,
        choices=DistributionStatus.CHOICES,
        default=DistributionStatus.PENDING,
    )

    # Direct episode audio on DO Spaces
    audio_spaces_key = models.CharField(max_length=500, blank=True, help_text="DO Spaces key for the episode audio file")
    audio_public_url = models.URLField(blank=True, help_text="Public URL of the episode audio on DO Spaces / CDN")
    audio_file_size = models.BigIntegerField(null=True, blank=True, help_text="Audio file size in bytes")
    audio_duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    audio_content_type = models.CharField(max_length=50, default='audio/mpeg')

    # Platform-specific identifiers returned after submission
    platform_episode_id = models.CharField(max_length=255, blank=True)
    platform_url = models.URLField(blank=True, help_text="URL of this episode on the platform once live")

    submitted_at = models.DateTimeField(null=True, blank=True)
    went_live_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        verbose_name = "Podcast Distribution"
        verbose_name_plural = "Podcast Distributions"
        unique_together = [['episode', 'platform']]
        indexes = [
            models.Index(fields=['organization_uuid', 'episode']),
            models.Index(fields=['organization_uuid', 'platform', 'status']),
        ]

    def __str__(self):
        return f"{self.episode.title} → {self.get_platform_display()} ({self.status})"

    def mark_submitted(self):
        self.status = DistributionStatus.SUBMITTED
        self.submitted_at = timezone.now()
        self.save()

    def mark_live(self, platform_url='', platform_episode_id=''):
        self.status = DistributionStatus.LIVE
        self.went_live_at = timezone.now()
        if platform_url:
            self.platform_url = platform_url
        if platform_episode_id:
            self.platform_episode_id = platform_episode_id
        self.save()


# =============================================================================
# VIDEO SHORT
# =============================================================================

class VideoShort(BaseModel):
    """
    A rendered short-form video clip derived from an episode (for TikTok, Reels, Shorts, etc.).
    Each short corresponds to a ClipMoment but also carries the rendered file stored in DO Spaces.
    Shareable links are generated from the CDN URL.
    """
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='video_shorts')
    clip_moment = models.ForeignKey(
        ClipMoment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='video_shorts',
        help_text="Source clip moment this short was rendered from",
    )
    source_media_asset = models.ForeignKey(
        MediaAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='video_shorts',
        help_text="Source media asset used for rendering",
    )

    title = models.CharField(max_length=255)
    caption = models.TextField(blank=True, help_text="Platform caption / description for the short")
    hashtags = models.JSONField(default=list, blank=True, help_text="List of hashtag strings")

    # Timing (copied from ClipMoment or set manually)
    start_ms = models.PositiveIntegerField(help_text="Start time in milliseconds")
    end_ms = models.PositiveIntegerField(help_text="End time in milliseconds")

    aspect_ratio = models.CharField(
        max_length=10,
        choices=ShortAspectRatio.CHOICES,
        default=ShortAspectRatio.VERTICAL,
    )

    # Render / upload status
    status = models.CharField(
        max_length=20,
        choices=ShortStatus.CHOICES,
        default=ShortStatus.QUEUED,
    )
    error_message = models.TextField(blank=True)

    # DO Spaces storage
    spaces_key = models.CharField(max_length=500, blank=True, help_text="DO Spaces key for the rendered video")
    public_url = models.URLField(blank=True, help_text="Public CDN URL of the rendered short")
    file_size = models.BigIntegerField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)

    # AI-generated content (requires approval like other AI artifacts)
    ai_caption_artifact = models.ForeignKey(
        AIArtifact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='video_shorts',
        help_text="AI artifact that generated the caption/hashtags",
    )

    render_started_at = models.DateTimeField(null=True, blank=True)
    render_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Video Short"
        verbose_name_plural = "Video Shorts"
        ordering = ['start_ms']
        indexes = [
            models.Index(fields=['organization_uuid', 'episode']),
            models.Index(fields=['organization_uuid', 'status']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_aspect_ratio_display()}) — {self.get_status_display()}"

    @property
    def duration_ms(self):
        return self.end_ms - self.start_ms

    @property
    def shareable_link(self):
        """CDN public link ready to share."""
        return self.public_url or None

    @property
    def start_formatted(self):
        seconds = self.start_ms // 1000
        return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"

    @property
    def end_formatted(self):
        seconds = self.end_ms // 1000
        return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


# =============================================================================
# SHOW NOTE FINAL
# =============================================================================

class ShowNoteFinal(BaseModel):
    """
    The final, approved show notes for an episode.
    
    Cannot be created unless:
    1. All required checklist items are complete
    2. User has HOST or ADMIN role
    """
    episode = models.OneToOneField(
        Episode,
        on_delete=models.CASCADE,
        related_name='show_note_final',
    )
    
    source_draft = models.ForeignKey(
        ShowNoteDraft,
        on_delete=models.SET_NULL,
        null=True,
        related_name='final_versions',
    )
    
    markdown = models.TextField(help_text="Final show notes in Markdown format")
    
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='approved_show_notes',
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Show Note Final"
        verbose_name_plural = "Show Notes Final"
        indexes = [
            models.Index(fields=['organization_uuid', 'episode']),
        ]

    def __str__(self):
        return f"Final for {self.episode.title}"

    def save(self, *args, **kwargs):
        if not self.approved_at:
            self.approved_at = timezone.now()
        super().save(*args, **kwargs)


# =============================================================================
# CHECKLIST ITEM
# =============================================================================

class ChecklistItem(BaseModel):
    """
    A checklist item for an episode. Used as a gate before certain status transitions.
    """
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='checklist_items')
    
    title = models.CharField(max_length=255)
    is_required = models.BooleanField(default=True)
    is_done = models.BooleanField(default=False)
    
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_checklist_items',
    )
    done_at = models.DateTimeField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Checklist Item"
        verbose_name_plural = "Checklist Items"
        ordering = ['sort_order']
        indexes = [
            models.Index(fields=['organization_uuid', 'episode']),
        ]

    def __str__(self):
        status = "✓" if self.is_done else "○"
        return f"{status} {self.title}"

    def mark_done(self, user):
        """Mark this item as done."""
        self.is_done = True
        self.done_by = user
        self.done_at = timezone.now()
        self.save()

    def mark_undone(self):
        """Mark this item as not done."""
        self.is_done = False
        self.done_by = None
        self.done_at = None
        self.save()


# =============================================================================
# EXPORT RECORD (Optional)
# =============================================================================

class ExportRecord(BaseModel):
    """
    Optional: Track exports generated for an episode.
    """
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='export_records')
    
    export_type = models.CharField(max_length=50, help_text="Type of export: json, markdown, csv, html")
    filename = models.CharField(max_length=255)
    file = models.FileField(upload_to='exports/', null=True, blank=True)
    
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='generated_exports',
    )

    class Meta:
        verbose_name = "Export Record"
        verbose_name_plural = "Export Records"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization_uuid', 'episode']),
        ]

    def __str__(self):
        return f"{self.export_type} export for {self.episode.title}"


# =============================================================================
# ACCESS REQUEST
# =============================================================================

class AccessRequest(models.Model):
    """
    Track requests from people who want access to the platform.
    Admin reviews and either creates an account or ignores.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    email = models.EmailField()
    organization = models.CharField(max_length=200, blank=True, default='')
    message = models.TextField(blank=True, default='')

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_access_requests',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Access Request"
        verbose_name_plural = "Access Requests"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} <{self.email}> — {self.status}"


# =============================================================================
# INVITATION
# =============================================================================

class Invitation(models.Model):
    """
    Admin-created invitation to join the platform.
    Stores a unique token that the invitee uses to set their password.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    name = models.CharField(max_length=200, blank=True, default='')
    role = models.CharField(max_length=20, choices=Role.CHOICES, default=Role.GUEST)
    token = models.CharField(max_length=64, unique=True, editable=False)

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_invitations',
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Invitation"
        verbose_name_plural = "Invitations"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.token:
            import secrets
            self.token = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    @property
    def is_accepted(self):
        return self.accepted_at is not None

    def __str__(self):
        return f"Invite for {self.email} ({self.get_role_display()})"
