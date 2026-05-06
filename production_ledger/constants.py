"""
Constants and choices for the Production Ledger app.
"""

# =============================================================================
# EPISODE STATUS WORKFLOW
# =============================================================================
# draft → planned → scheduled → recorded → ingested → transcribed → edited → approved → published

class EpisodeStatus:
    DRAFT = 'draft'
    PLANNED = 'planned'
    SCHEDULED = 'scheduled'
    RECORDED = 'recorded'
    INGESTED = 'ingested'
    TRANSCRIBED = 'transcribed'
    EDITED = 'edited'
    APPROVED = 'approved'
    PUBLISHED = 'published'

    CHOICES = [
        (DRAFT, 'Draft'),
        (PLANNED, 'Planned'),
        (SCHEDULED, 'Scheduled'),
        (RECORDED, 'Recorded'),
        (INGESTED, 'Ingested'),
        (TRANSCRIBED, 'Transcribed'),
        (EDITED, 'Edited'),
        (APPROVED, 'Approved'),
        (PUBLISHED, 'Published'),
    ]

    # Valid transitions: current_status -> list of allowed next statuses
    TRANSITIONS = {
        DRAFT: [PLANNED],
        PLANNED: [SCHEDULED, DRAFT],
        SCHEDULED: [RECORDED, PLANNED],
        RECORDED: [INGESTED, SCHEDULED],
        INGESTED: [TRANSCRIBED, RECORDED],
        TRANSCRIBED: [EDITED, INGESTED],
        EDITED: [APPROVED, TRANSCRIBED],
        APPROVED: [PUBLISHED, EDITED],
        PUBLISHED: [APPROVED],  # Can unpublish back to approved
    }

    # Statuses that require checklist completion
    REQUIRES_CHECKLIST = [APPROVED, PUBLISHED]


# =============================================================================
# ROLES
# =============================================================================

class Role:
    ADMIN = 'admin'
    HOST = 'host'
    PRODUCER = 'producer'
    EDITOR = 'editor'
    GUEST = 'guest'

    CHOICES = [
        (ADMIN, 'Admin'),
        (HOST, 'Host'),
        (PRODUCER, 'Producer'),
        (EDITOR, 'Editor'),
        (GUEST, 'Guest'),
    ]

    # Role hierarchy for permission checks (higher number = more permissions)
    HIERARCHY = {
        GUEST: 1,
        EDITOR: 2,
        PRODUCER: 3,
        HOST: 4,
        ADMIN: 5,
    }


# =============================================================================
# EPISODE TYPES
# =============================================================================

class EpisodeType:
    GLOBAL = 'global'
    OPS = 'ops'
    ETHICS = 'ethics'
    OTHER = 'other'

    CHOICES = [
        (GLOBAL, 'Global'),
        (OPS, 'Ops'),
        (ETHICS, 'Ethics'),
        (OTHER, 'Other'),
    ]


# =============================================================================
# RECORDING CONTEXT
# =============================================================================

class RecordingContext:
    REMOTE = 'remote'
    IN_PERSON = 'in_person'
    HYBRID = 'hybrid'

    CHOICES = [
        (REMOTE, 'Remote'),
        (IN_PERSON, 'In Person'),
        (HYBRID, 'Hybrid'),
    ]


# =============================================================================
# SEGMENT OWNER ROLES
# =============================================================================

class SegmentOwner:
    HOST = 'host'
    PRODUCER = 'producer'

    CHOICES = [
        (HOST, 'Host'),
        (PRODUCER, 'Producer'),
    ]


# =============================================================================
# GUEST ROLES
# =============================================================================

class GuestRole:
    GUEST = 'guest'
    PANELIST = 'panelist'
    COHOST = 'cohost'

    CHOICES = [
        (GUEST, 'Guest'),
        (PANELIST, 'Panelist'),
        (COHOST, 'Co-Host'),
    ]


# =============================================================================
# QUOTE APPROVAL
# =============================================================================

class QuoteApproval:
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'

    CHOICES = [
        (PENDING, 'Pending'),
        (APPROVED, 'Approved'),
        (REJECTED, 'Rejected'),
    ]


# =============================================================================
# MEDIA ASSET TYPES
# =============================================================================

class AssetType:
    AUDIO = 'audio'
    VIDEO = 'video'

    CHOICES = [
        (AUDIO, 'Audio'),
        (VIDEO, 'Video'),
    ]


class SourceType:
    UPLOAD = 'upload'
    EXTERNAL_LINK = 'external_link'
    API_IMPORT = 'api_import'

    CHOICES = [
        (UPLOAD, 'Upload'),
        (EXTERNAL_LINK, 'External Link'),
        (API_IMPORT, 'API Import'),
    ]


class MediaPlatform:
    """
    Supported external media platforms for linking/integration.
    
    LINK_PLATFORMS: Work now with shareable URLs (no auth needed)
    OAUTH_PLATFORMS: Planned for future - will require OAuth integration
    """
    # === LINK PLATFORMS (work now with shareable URLs) ===
    YOUTUBE = 'youtube'
    VIMEO = 'vimeo'
    GOOGLE_DRIVE = 'google_drive'
    DROPBOX = 'dropbox'
    S3 = 's3'
    DIRECT_URL = 'direct_url'
    
    # === OAUTH PLATFORMS (future integration) ===
    # These are defined but hidden from UI until OAuth is implemented
    RIVERSIDE = 'riverside'
    ZOOM = 'zoom'
    GOOGLE_MEET = 'google_meet'
    STREAMYARD = 'streamyard'
    
    # Platform categories for reference
    LINK_PLATFORMS = [YOUTUBE, VIMEO, GOOGLE_DRIVE, DROPBOX, S3, DIRECT_URL]
    OAUTH_PLATFORMS = [RIVERSIDE, ZOOM, GOOGLE_MEET, STREAMYARD]

    # Choices shown in forms (only link-based platforms for now)
    CHOICES = [
        ('Video Platforms', (
            (YOUTUBE, 'YouTube'),
            (VIMEO, 'Vimeo'),
        )),
        ('Cloud Storage', (
            (GOOGLE_DRIVE, 'Google Drive (shareable link)'),
            (DROPBOX, 'Dropbox (shareable link)'),
            (S3, 'Amazon S3 (public URL)'),
        )),
        ('Other', (
            (DIRECT_URL, 'Direct URL'),
        )),
    ]

    # Flat choices for forms
    CHOICES_FLAT = [
        (YOUTUBE, 'YouTube'),
        (VIMEO, 'Vimeo'),
        (GOOGLE_DRIVE, 'Google Drive'),
        (DROPBOX, 'Dropbox'),
        (S3, 'Amazon S3'),
        (DIRECT_URL, 'Direct URL'),
    ]
    
    # All choices including OAuth platforms (for database/admin)
    ALL_CHOICES_FLAT = CHOICES_FLAT + [
        (RIVERSIDE, 'Riverside.fm'),
        (ZOOM, 'Zoom'),
        (GOOGLE_MEET, 'Google Meet'),
        (STREAMYARD, 'StreamYard'),
    ]

    # URL patterns for auto-detection
    URL_PATTERNS = {
        YOUTUBE: ['youtube.com', 'youtu.be'],
        VIMEO: ['vimeo.com'],
        GOOGLE_DRIVE: ['drive.google.com', 'docs.google.com'],
        DROPBOX: ['dropbox.com', 'dl.dropboxusercontent.com'],
        S3: ['s3.amazonaws.com', '.s3.'],
    }
    
    # Help text for each platform
    HELP_TEXT = {
        YOUTUBE: 'Paste the video URL (e.g., https://youtube.com/watch?v=...)',
        VIMEO: 'Paste the video URL (e.g., https://vimeo.com/123456)',
        GOOGLE_DRIVE: 'Use "Get link" and set to "Anyone with the link"',
        DROPBOX: 'Use "Copy link" from Dropbox sharing',
        S3: 'Use a public URL or pre-signed URL',
        DIRECT_URL: 'Any direct URL to an audio/video file',
    }


class IngestionStatus:
    PENDING = 'pending'
    PROCESSING = 'processing'
    READY = 'ready'
    FAILED = 'failed'

    CHOICES = [
        (PENDING, 'Pending'),
        (PROCESSING, 'Processing'),
        (READY, 'Ready'),
        (FAILED, 'Failed'),
    ]


# =============================================================================
# TRANSCRIPT FORMATS
# =============================================================================

class TranscriptFormat:
    TXT = 'txt'
    VTT = 'vtt'
    SRT = 'srt'

    CHOICES = [
        (TXT, 'Plain Text'),
        (VTT, 'WebVTT'),
        (SRT, 'SubRip'),
    ]


class TranscriptSourceType:
    UPLOAD = 'upload'
    PASTE = 'paste'

    CHOICES = [
        (UPLOAD, 'Upload'),
        (PASTE, 'Paste'),
    ]


# =============================================================================
# CLIP PRIORITIES
# =============================================================================

class ClipPriority:
    GOLD = 'gold'
    SILVER = 'silver'
    BRONZE = 'bronze'

    CHOICES = [
        (GOLD, 'Gold'),
        (SILVER, 'Silver'),
        (BRONZE, 'Bronze'),
    ]


# =============================================================================
# AI ARTIFACT TYPES
# =============================================================================

class ArtifactType:
    QUESTIONS = 'questions'
    SHOW_NOTES = 'show_notes'
    SEGMENT_SUGGESTIONS = 'segment_suggestions'
    SOCIAL_POSTS = 'social_posts'
    TITLES = 'titles'
    CHAPTERS = 'chapters'
    SHORTS = 'shorts'

    CHOICES = [
        (QUESTIONS, 'Questions'),
        (SHOW_NOTES, 'Show Notes'),
        (SEGMENT_SUGGESTIONS, 'Segment Suggestions'),
        (SOCIAL_POSTS, 'Social Posts'),
        (TITLES, 'Titles'),
        (CHAPTERS, 'Chapters'),
        (SHORTS, 'Shorts'),
    ]


class ApprovalStatus:
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'

    CHOICES = [
        (PENDING, 'Pending'),
        (APPROVED, 'Approved'),
        (REJECTED, 'Rejected'),
    ]


# =============================================================================
# DEFAULT CHECKLIST ITEMS
# =============================================================================

DEFAULT_CHECKLIST_ITEMS = [
    {'title': 'Transcript ingested', 'is_required': True, 'sort_order': 1},
    {'title': 'Transcript reviewed', 'is_required': True, 'sort_order': 2},
    {'title': 'Quotes approved (if guests exist)', 'is_required': False, 'sort_order': 3},
    {'title': 'AI show notes reviewed', 'is_required': True, 'sort_order': 4},
    {'title': 'Final show notes approved', 'is_required': True, 'sort_order': 5},
    {'title': 'Export package generated', 'is_required': True, 'sort_order': 6},
]


# =============================================================================
# PODCAST PLATFORMS
# =============================================================================

class PodcastPlatform:
    APPLE = 'apple'
    SPOTIFY = 'spotify'
    AMAZON = 'amazon'
    GOOGLE = 'google'
    IHEART = 'iheart'
    STITCHER = 'stitcher'
    POCKET_CASTS = 'pocket_casts'
    OVERCAST = 'overcast'
    CASTBOX = 'castbox'
    RSS = 'rss'

    CHOICES = [
        (APPLE, 'Apple Podcasts'),
        (SPOTIFY, 'Spotify'),
        (AMAZON, 'Amazon Music / Audible'),
        (GOOGLE, 'Google Podcasts'),
        (IHEART, 'iHeartRadio'),
        (STITCHER, 'Stitcher'),
        (POCKET_CASTS, 'Pocket Casts'),
        (OVERCAST, 'Overcast'),
        (CASTBOX, 'Castbox'),
        (RSS, 'RSS Feed'),
    ]

    # Platforms that accept RSS submissions (vs. proprietary API)
    RSS_SUBMISSION_PLATFORMS = [APPLE, SPOTIFY, AMAZON, GOOGLE, IHEART, STITCHER, POCKET_CASTS, OVERCAST, CASTBOX]

    # Submission / directory URLs for each platform
    SUBMISSION_URLS = {
        APPLE: 'https://podcastsconnect.apple.com/my-podcasts/new-feed',
        SPOTIFY: 'https://podcasters.spotify.com/pod/submit',
        AMAZON: 'https://music.amazon.com/podcasts/submit',
        GOOGLE: 'https://podcastsmanager.google.com/',
        IHEART: 'https://www.iheart.com/content/submit-your-podcast/',
        STITCHER: 'https://partners.stitcher.com/join',
        POCKET_CASTS: 'https://pocketcasts.com/submit/',
        OVERCAST: 'https://overcast.fm/podcasterinfo',
        CASTBOX: 'https://helpcenter.castbox.fm/hc/en-us/articles/360003534751',
    }


# =============================================================================
# DISTRIBUTION STATUS
# =============================================================================

class DistributionStatus:
    PENDING = 'pending'
    SUBMITTED = 'submitted'
    LIVE = 'live'
    FAILED = 'failed'
    REMOVED = 'removed'

    CHOICES = [
        (PENDING, 'Pending'),
        (SUBMITTED, 'Submitted'),
        (LIVE, 'Live'),
        (FAILED, 'Failed'),
        (REMOVED, 'Removed'),
    ]


# =============================================================================
# VIDEO SHORT STATUS
# =============================================================================

class ShortStatus:
    QUEUED = 'queued'
    RENDERING = 'rendering'
    UPLOADING = 'uploading'
    READY = 'ready'
    FAILED = 'failed'

    CHOICES = [
        (QUEUED, 'Queued'),
        (RENDERING, 'Rendering'),
        (UPLOADING, 'Uploading'),
        (READY, 'Ready'),
        (FAILED, 'Failed'),
    ]


# =============================================================================
# SHORT ASPECT RATIOS
# =============================================================================

class ShortAspectRatio:
    VERTICAL = '9:16'    # TikTok / Reels / Shorts
    SQUARE = '1:1'       # Instagram / Twitter
    HORIZONTAL = '16:9'  # YouTube horizontal clip

    CHOICES = [
        (VERTICAL, 'Vertical (9:16) — TikTok / Reels / Shorts'),
        (SQUARE, 'Square (1:1) — Instagram / Twitter'),
        (HORIZONTAL, 'Horizontal (16:9) — YouTube Clip'),
    ]
