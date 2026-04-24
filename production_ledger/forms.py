"""
Forms for Production Ledger.
"""
from django import forms
from django.core.exceptions import ValidationError

from .constants import (
    ArtifactType,
    ClipPriority,
    EpisodeStatus,
    GuestRole,
    RecordingContext,
    SegmentOwner,
    SourceType,
    TranscriptFormat,
    TranscriptSourceType,
)
from .models import (
    AIArtifact,
    ChecklistItem,
    ClipMoment,
    Episode,
    EpisodeGuest,
    Guest,
    MediaAsset,
    Segment,
    Show,
    ShowNoteDraft,
    ShowNoteFinal,
    ShowRoleAssignment,
    Transcript,
)


# =============================================================================
# BASE FORM
# =============================================================================

class TailwindFormMixin:
    """Mixin to add Tailwind CSS classes to form fields."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_classes()
    
    def apply_tailwind_classes(self):
        for field_name, field in self.fields.items():
            # Base classes
            base_classes = "block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
            
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs['class'] = f"{base_classes} min-h-[100px]"
                field.widget.attrs['rows'] = 4
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = base_classes
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = "h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            elif isinstance(field.widget, forms.FileInput):
                field.widget.attrs['class'] = "block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            else:
                field.widget.attrs['class'] = base_classes
            
            # Add placeholder if help_text exists
            if field.help_text:
                field.widget.attrs['placeholder'] = field.help_text


# =============================================================================
# SHOW FORMS
# =============================================================================

class ShowForm(TailwindFormMixin, forms.ModelForm):
    """Form for creating/editing Shows."""
    
    class Meta:
        model = Show
        fields = [
            'name', 'slug', 'description',
            'brand_primary_color', 'default_intro_text', 'default_outro_text',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'default_intro_text': forms.Textarea(attrs={'rows': 3}),
            'default_outro_text': forms.Textarea(attrs={'rows': 3}),
            'brand_primary_color': forms.TextInput(attrs={'type': 'color'}),
        }


# =============================================================================
# EPISODE FORMS
# =============================================================================

class EpisodeForm(TailwindFormMixin, forms.ModelForm):
    """Form for creating/editing Episodes."""
    
    class Meta:
        model = Episode
        fields = [
            'title', 'episode_type', 'target_minutes',
            'recording_context', 'scheduled_for', 'publish_date',
        ]
        widgets = {
            'scheduled_for': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),
            'publish_date': forms.DateInput(
                attrs={'type': 'date'},
                format='%Y-%m-%d'
            ),
        }
    
    def __init__(self, *args, organization_uuid=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['scheduled_for'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['publish_date'].input_formats = ['%Y-%m-%d']
        
        # Filter episode types for the organization
        from .models import EpisodeType
        if organization_uuid:
            self.fields['episode_type'].queryset = EpisodeType.get_for_organization(organization_uuid)
        else:
            # Fall back to global defaults
            self.fields['episode_type'].queryset = EpisodeType.objects.filter(
                organization_uuid__isnull=True,
                is_active=True
            )


class EpisodeStatusForm(TailwindFormMixin, forms.Form):
    """Form for changing episode status."""
    
    new_status = forms.ChoiceField(choices=EpisodeStatus.CHOICES)
    
    def __init__(self, *args, episode=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.episode = episode
        
        if episode:
            # Only show allowed transitions
            allowed = EpisodeStatus.TRANSITIONS.get(episode.status, [])
            self.fields['new_status'].choices = [
                (s, label) for s, label in EpisodeStatus.CHOICES if s in allowed
            ]
    
    def clean_new_status(self):
        new_status = self.cleaned_data['new_status']
        if self.episode and not self.episode.can_transition_to(new_status):
            raise ValidationError(f"Cannot transition to {new_status} from {self.episode.status}")
        return new_status


class LiveNotesForm(TailwindFormMixin, forms.ModelForm):
    """Form for updating live notes during recording."""
    
    class Meta:
        model = Episode
        fields = ['live_notes']
        widgets = {
            'live_notes': forms.Textarea(attrs={'rows': 10}),
        }


# =============================================================================
# SEGMENT FORMS
# =============================================================================

class SegmentForm(TailwindFormMixin, forms.ModelForm):
    """Form for creating/editing Segments."""
    
    class Meta:
        model = Segment
        fields = [
            'order', 'title', 'purpose', 'timebox_minutes',
            'owner_role', 'bullet_prompts', 'key_questions',
        ]
        widgets = {
            'purpose': forms.Textarea(attrs={'rows': 2}),
            'bullet_prompts': forms.Textarea(attrs={'rows': 3}),
            'key_questions': forms.Textarea(attrs={'rows': 3}),
        }


SegmentFormSet = forms.inlineformset_factory(
    Episode, Segment,
    form=SegmentForm,
    extra=1,
    can_delete=True,
)


# =============================================================================
# GUEST FORMS
# =============================================================================

# Common timezone choices
TIMEZONE_CHOICES = [
    ('', '-- Select Timezone --'),
    ('US & Canada', (
        ('America/New_York', 'Eastern Time (US & Canada)'),
        ('America/Chicago', 'Central Time (US & Canada)'),
        ('America/Denver', 'Mountain Time (US & Canada)'),
        ('America/Los_Angeles', 'Pacific Time (US & Canada)'),
        ('America/Anchorage', 'Alaska'),
        ('Pacific/Honolulu', 'Hawaii'),
    )),
    ('Europe', (
        ('Europe/London', 'London'),
        ('Europe/Paris', 'Paris / Berlin / Rome'),
        ('Europe/Amsterdam', 'Amsterdam'),
        ('Europe/Moscow', 'Moscow'),
    )),
    ('Asia & Pacific', (
        ('Asia/Tokyo', 'Tokyo'),
        ('Asia/Shanghai', 'Beijing / Shanghai'),
        ('Asia/Hong_Kong', 'Hong Kong'),
        ('Asia/Singapore', 'Singapore'),
        ('Asia/Kolkata', 'Mumbai / New Delhi'),
        ('Asia/Dubai', 'Dubai'),
        ('Australia/Sydney', 'Sydney'),
        ('Australia/Melbourne', 'Melbourne'),
        ('Pacific/Auckland', 'Auckland'),
    )),
    ('Other', (
        ('America/Sao_Paulo', 'São Paulo'),
        ('America/Mexico_City', 'Mexico City'),
        ('Africa/Johannesburg', 'Johannesburg'),
        ('Africa/Lagos', 'Lagos'),
        ('UTC', 'UTC'),
    )),
]


class GuestForm(TailwindFormMixin, forms.ModelForm):
    """Form for creating/editing Guests."""
    
    # Convenience fields for common links
    twitter = forms.CharField(max_length=100, required=False, help_text="Twitter/X handle (without @)")
    linkedin = forms.URLField(required=False, help_text="LinkedIn profile URL")
    website = forms.URLField(required=False, help_text="Personal website")
    
    # Timezone dropdown
    timezone = forms.ChoiceField(
        choices=TIMEZONE_CHOICES,
        required=False,
        help_text="Guest's timezone for scheduling"
    )
    
    class Meta:
        model = Guest
        fields = [
            'name', 'title', 'org', 'email', 'phone', 'bio', 'timezone',
            'consent_audio', 'consent_video',
        ]
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4}),
            'email': forms.EmailInput(attrs={'placeholder': 'guest@example.com'}),
            'phone': forms.TextInput(attrs={'placeholder': '+1 555-123-4567'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate link fields from instance
        if self.instance and self.instance.pk and self.instance.links:
            self.fields['twitter'].initial = self.instance.links.get('twitter', '')
            self.fields['linkedin'].initial = self.instance.links.get('linkedin', '')
            self.fields['website'].initial = self.instance.links.get('website', '')
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        # Build links JSON
        instance.links = {
            'twitter': self.cleaned_data.get('twitter', ''),
            'linkedin': self.cleaned_data.get('linkedin', ''),
            'website': self.cleaned_data.get('website', ''),
        }
        # Remove empty values
        instance.links = {k: v for k, v in instance.links.items() if v}
        
        if commit:
            instance.save()
        return instance


class EpisodeGuestForm(TailwindFormMixin, forms.ModelForm):
    """Form for adding/editing Episode Guests."""
    
    class Meta:
        model = EpisodeGuest
        fields = [
            'guest', 'role', 'prep_notes', 'key_topics', 'no_go_topics',
        ]
        widgets = {
            'prep_notes': forms.Textarea(attrs={'rows': 3}),
            'key_topics': forms.Textarea(attrs={'rows': 2}),
            'no_go_topics': forms.Textarea(attrs={'rows': 2}),
        }


# =============================================================================
# MEDIA ASSET FORMS
# =============================================================================

class MediaAssetUploadForm(TailwindFormMixin, forms.ModelForm):
    """Form for uploading small media files (intros, outros, sound effects, artwork)."""
    
    class Meta:
        model = MediaAsset
        fields = ['asset_type', 'label', 'file']
        widgets = {
            'label': forms.TextInput(attrs={'placeholder': 'e.g., Intro Music, Episode Artwork'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['file'].required = True
        self.fields['label'].required = False
        self.fields['label'].help_text = "Optional display name"
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.source_type = SourceType.UPLOAD
        
        if instance.file:
            instance.filename = instance.file.name
            instance.file_size = instance.file.size
            # Set label from filename if not provided
            if not instance.label:
                instance.label = instance.file.name.rsplit('.', 1)[0]
        
        if commit:
            instance.save()
        return instance


class MediaAssetLinkForm(TailwindFormMixin, forms.ModelForm):
    """Form for linking to external media (YouTube, Riverside, etc.)."""
    
    class Meta:
        model = MediaAsset
        fields = ['asset_type', 'platform', 'label', 'external_url']
        widgets = {
            'label': forms.TextInput(attrs={'placeholder': 'e.g., Raw Recording, Final Mix'}),
            'external_url': forms.URLInput(attrs={'placeholder': 'https://...'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .constants import MediaPlatform
        
        self.fields['external_url'].required = True
        self.fields['external_url'].label = "URL"
        self.fields['label'].required = False
        self.fields['label'].help_text = "Display name for this link"
        self.fields['platform'].required = False
        self.fields['platform'].help_text = "Auto-detected from URL if left blank"
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.source_type = SourceType.EXTERNAL_LINK
        
        # Auto-detect platform if not specified
        if not instance.platform and instance.external_url:
            instance.platform = MediaAsset.detect_platform_from_url(instance.external_url)
        
        if commit:
            instance.save()
        return instance


# =============================================================================
# TRANSCRIPT FORMS
# =============================================================================

class TranscriptUploadForm(TailwindFormMixin, forms.Form):
    """Form for uploading transcript files."""
    
    file = forms.FileField(
        help_text="Upload a .txt, .vtt, or .srt file"
    )
    format = forms.ChoiceField(
        choices=TranscriptFormat.CHOICES,
        initial=TranscriptFormat.TXT,
    )
    
    def clean_file(self):
        file = self.cleaned_data['file']
        # Validate file extension
        ext = file.name.split('.')[-1].lower()
        if ext not in ['txt', 'vtt', 'srt']:
            raise ValidationError("File must be .txt, .vtt, or .srt")
        return file


class TranscriptPasteForm(TailwindFormMixin, forms.Form):
    """Form for pasting transcript text."""
    
    raw_text = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 15}),
        help_text="Paste your transcript text here"
    )
    format = forms.ChoiceField(
        choices=TranscriptFormat.CHOICES,
        initial=TranscriptFormat.TXT,
    )


class TranscriptEditForm(TailwindFormMixin, forms.ModelForm):
    """Form for editing transcript content."""
    
    class Meta:
        model = Transcript
        fields = ['raw_text', 'normalized_json']
        widgets = {
            'raw_text': forms.Textarea(attrs={'rows': 20}),
        }


# =============================================================================
# CLIP MOMENT FORMS
# =============================================================================

class ClipMomentForm(TailwindFormMixin, forms.ModelForm):
    """Form for creating/editing Clip Moments."""
    
    # Helper fields for time input
    start_time = forms.CharField(
        max_length=12,
        help_text="Format: HH:MM:SS or MM:SS",
        required=False,
    )
    end_time = forms.CharField(
        max_length=12,
        help_text="Format: HH:MM:SS or MM:SS",
        required=False,
    )
    tags_text = forms.CharField(
        max_length=500,
        required=False,
        help_text="Comma-separated tags",
    )
    
    class Meta:
        model = ClipMoment
        fields = [
            'title', 'start_ms', 'end_ms', 'hook',
            'caption_draft', 'priority',
        ]
        widgets = {
            'caption_draft': forms.Textarea(attrs={'rows': 3}),
            'start_ms': forms.HiddenInput(),
            'end_ms': forms.HiddenInput(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Use _state.adding rather than pk check: UUID models always have a
        # non-None pk even before saving, so pk alone cannot distinguish a new
        # instance from an existing one.
        if self.instance and not self.instance._state.adding:
            # Convert ms to time format for display
            self.fields['start_time'].initial = self._ms_to_time(self.instance.start_ms)
            self.fields['end_time'].initial = self._ms_to_time(self.instance.end_ms)
            self.fields['tags_text'].initial = ', '.join(self.instance.tags or [])
    
    def _ms_to_time(self, ms):
        """Convert milliseconds to HH:MM:SS format."""
        seconds = ms // 1000
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"
    
    def _time_to_ms(self, time_str):
        """Convert HH:MM:SS or MM:SS to milliseconds."""
        parts = time_str.split(':')
        if len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
        elif len(parts) == 2:
            hours = 0
            minutes, seconds = map(int, parts)
        else:
            raise ValidationError("Invalid time format. Use HH:MM:SS or MM:SS")
        
        return ((hours * 3600) + (minutes * 60) + seconds) * 1000
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Convert time fields to ms if provided
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        
        if start_time and not cleaned_data.get('start_ms'):
            try:
                cleaned_data['start_ms'] = self._time_to_ms(start_time)
            except Exception:
                self.add_error('start_time', 'Invalid time format')
        
        if end_time and not cleaned_data.get('end_ms'):
            try:
                cleaned_data['end_ms'] = self._time_to_ms(end_time)
            except Exception:
                self.add_error('end_time', 'Invalid time format')
        
        # Validate start < end
        start = cleaned_data.get('start_ms', 0)
        end = cleaned_data.get('end_ms', 0)
        if end <= start:
            raise ValidationError("End time must be after start time")
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Parse tags
        tags_text = self.cleaned_data.get('tags_text', '')
        if tags_text:
            instance.tags = [t.strip() for t in tags_text.split(',') if t.strip()]
        else:
            instance.tags = []
        
        if commit:
            instance.save()
        return instance


class QuickClipForm(TailwindFormMixin, forms.Form):
    """Quick form for flagging moments during Control Room."""
    
    title = forms.CharField(max_length=255)
    hook = forms.CharField(max_length=500, required=False)
    priority = forms.ChoiceField(
        choices=ClipPriority.CHOICES,
        initial=ClipPriority.SILVER,
    )
    # start_ms will be provided by JavaScript timer
    start_ms = forms.IntegerField(widget=forms.HiddenInput())


# =============================================================================
# AI ARTIFACT FORMS
# =============================================================================

class GenerateAIArtifactForm(TailwindFormMixin, forms.Form):
    """Form for generating AI artifacts."""
    
    artifact_type = forms.ChoiceField(choices=ArtifactType.CHOICES)
    topic_prompt = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        help_text="Additional context or focus for the AI",
    )
    use_transcript = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Include transcript as context",
    )
    use_clips = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Include clip moments as context",
    )


class ApproveArtifactForm(TailwindFormMixin, forms.Form):
    """Form for approving/rejecting AI artifacts."""
    
    action = forms.ChoiceField(
        choices=[('approve', 'Approve'), ('reject', 'Reject')],
        widget=forms.RadioSelect,
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        help_text="Optional notes (required for rejection)",
    )
    
    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('action') == 'reject' and not cleaned_data.get('notes'):
            raise ValidationError("Please provide a reason for rejection")
        return cleaned_data


# =============================================================================
# SHOW NOTES FORMS
# =============================================================================

class ShowNoteDraftForm(TailwindFormMixin, forms.ModelForm):
    """Form for editing show note drafts."""
    
    class Meta:
        model = ShowNoteDraft
        fields = ['markdown', 'chapters_json', 'resources_json']
        widgets = {
            'markdown': forms.Textarea(attrs={'rows': 20}),
        }


class FinalizeShowNotesForm(TailwindFormMixin, forms.Form):
    """Form for finalizing show notes."""
    
    source_draft = forms.ModelChoiceField(
        queryset=ShowNoteDraft.objects.none(),
        help_text="Select the draft to finalize",
    )
    markdown = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 20}),
        help_text="Final show notes content",
    )
    
    def __init__(self, *args, episode=None, **kwargs):
        super().__init__(*args, **kwargs)
        if episode:
            self.fields['source_draft'].queryset = episode.show_note_drafts.all()


# =============================================================================
# CHECKLIST FORMS
# =============================================================================

class ChecklistItemForm(TailwindFormMixin, forms.ModelForm):
    """Form for editing checklist items."""
    
    class Meta:
        model = ChecklistItem
        fields = ['title', 'is_required', 'is_done', 'sort_order']


class ChecklistToggleForm(forms.Form):
    """Simple form for toggling checklist item status."""
    
    is_done = forms.BooleanField(required=False)


# =============================================================================
# ROLE ASSIGNMENT FORMS
# =============================================================================

class ShowRoleAssignmentForm(TailwindFormMixin, forms.ModelForm):
    """Form for assigning roles to shows."""
    
    class Meta:
        model = ShowRoleAssignment
        fields = ['user', 'role']


# =============================================================================
# ACCESS REQUEST & INVITATION FORMS
# =============================================================================

class AccessRequestForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        from .models import AccessRequest
        model = AccessRequest
        fields = ['name', 'email', 'organization', 'message']


class InvitationForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        from .models import Invitation
        model = Invitation
        fields = ['email', 'name', 'role']
