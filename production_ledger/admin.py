"""
Django Admin configuration for Production Ledger.
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import (
    AIArtifact,
    ChecklistItem,
    ClipMoment,
    Episode,
    EpisodeGuest,
    EpisodeRoleOverride,
    EpisodeType,
    ExportRecord,
    Guest,
    MediaAsset,
    Segment,
    Show,
    ShowNoteDraft,
    ShowNoteFinal,
    ShowRoleAssignment,
    Transcript,
)


class BaseModelAdmin(admin.ModelAdmin):
    """Base admin class with common configuration."""
    readonly_fields = ('id', 'created_at', 'updated_at', 'created_by', 'updated_by')
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


# =============================================================================
# INLINES
# =============================================================================

class SegmentInline(admin.TabularInline):
    model = Segment
    extra = 1
    fields = ('order', 'title', 'timebox_minutes', 'owner_role', 'purpose')
    ordering = ['order']


class EpisodeGuestInline(admin.TabularInline):
    model = EpisodeGuest
    extra = 1
    fields = ('guest', 'role', 'quote_approval_status')
    autocomplete_fields = ['guest']


class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0
    fields = ('sort_order', 'title', 'is_required', 'is_done', 'done_by', 'done_at')
    readonly_fields = ('done_by', 'done_at')
    ordering = ['sort_order']


class ShowRoleAssignmentInline(admin.TabularInline):
    model = ShowRoleAssignment
    extra = 1
    fields = ('user', 'role')
    autocomplete_fields = ['user']


# =============================================================================
# SHOW
# =============================================================================

@admin.register(Show)
class ShowAdmin(BaseModelAdmin):
    list_display = ('name', 'slug', 'organization_uuid', 'created_at')
    list_filter = ('organization_uuid', 'created_at')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    
    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'description', 'organization_uuid')
        }),
        ('Branding', {
            'fields': ('brand_primary_color', 'default_intro_text', 'default_outro_text'),
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': ('id', 'created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    inlines = [ShowRoleAssignmentInline]


# =============================================================================
# EPISODE TYPE
# =============================================================================

@admin.register(EpisodeType)
class EpisodeTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'color_preview', 'icon', 'sort_order', 'is_active', 'organization_uuid')
    list_filter = ('is_active', 'organization_uuid')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['sort_order', 'name']
    
    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'description', 'organization_uuid')
        }),
        ('Display', {
            'fields': ('color', 'icon', 'sort_order', 'is_active'),
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = ('id', 'created_at', 'updated_at')
    
    def color_preview(self, obj):
        if obj.color:
            return format_html(
                '<span style="background-color: {}; padding: 2px 10px; border-radius: 3px; color: white;">{}</span>',
                obj.color, obj.color
            )
        return '-'
    color_preview.short_description = 'Color'


# =============================================================================
# EPISODE
# =============================================================================

@admin.register(Episode)
class EpisodeAdmin(BaseModelAdmin):
    list_display = ('title', 'show', 'status', 'episode_type', 'scheduled_for', 'created_at')
    list_filter = ('status', 'episode_type', 'recording_context', 'show', 'organization_uuid')
    search_fields = ('title', 'show__name')
    date_hierarchy = 'created_at'
    autocomplete_fields = ['show']
    
    fieldsets = (
        (None, {
            'fields': ('show', 'title', 'organization_uuid')
        }),
        ('Configuration', {
            'fields': ('episode_type', 'target_minutes', 'recording_context'),
        }),
        ('Workflow', {
            'fields': ('status', 'scheduled_for', 'publish_date'),
        }),
        ('Notes', {
            'fields': ('live_notes',),
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': ('id', 'created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    inlines = [SegmentInline, EpisodeGuestInline, ChecklistItemInline]
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('show')


# =============================================================================
# SEGMENT
# =============================================================================

@admin.register(Segment)
class SegmentAdmin(BaseModelAdmin):
    list_display = ('title', 'episode', 'order', 'timebox_minutes', 'owner_role')
    list_filter = ('owner_role', 'episode__show')
    search_fields = ('title', 'episode__title')
    ordering = ['episode', 'order']
    autocomplete_fields = ['episode']


# =============================================================================
# GUEST
# =============================================================================

@admin.register(Guest)
class GuestAdmin(BaseModelAdmin):
    list_display = ('name', 'title', 'org', 'consent_audio', 'consent_video')
    list_filter = ('consent_audio', 'consent_video', 'organization_uuid')
    search_fields = ('name', 'title', 'org', 'bio')
    
    fieldsets = (
        (None, {
            'fields': ('name', 'title', 'org', 'organization_uuid')
        }),
        ('Details', {
            'fields': ('bio', 'links', 'timezone'),
        }),
        ('Consent', {
            'fields': ('consent_audio', 'consent_video'),
        }),
        ('Metadata', {
            'fields': ('id', 'created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(EpisodeGuest)
class EpisodeGuestAdmin(BaseModelAdmin):
    list_display = ('guest', 'episode', 'role', 'quote_approval_status')
    list_filter = ('role', 'quote_approval_status')
    search_fields = ('guest__name', 'episode__title')
    autocomplete_fields = ['guest', 'episode']


# =============================================================================
# MEDIA ASSET
# =============================================================================

@admin.register(MediaAsset)
class MediaAssetAdmin(BaseModelAdmin):
    list_display = ('filename', 'episode', 'asset_type', 'source_type', 'ingestion_status', 'file_size_display')
    list_filter = ('asset_type', 'source_type', 'ingestion_status', 'organization_uuid')
    search_fields = ('filename', 'episode__title')
    readonly_fields = BaseModelAdmin.readonly_fields + ('checksum_sha256',)
    autocomplete_fields = ['episode']
    
    def file_size_display(self, obj):
        if obj.file_size:
            if obj.file_size < 1024:
                return f"{obj.file_size} B"
            elif obj.file_size < 1024 * 1024:
                return f"{obj.file_size / 1024:.1f} KB"
            else:
                return f"{obj.file_size / (1024 * 1024):.1f} MB"
        return "-"
    file_size_display.short_description = "File Size"


# =============================================================================
# TRANSCRIPT
# =============================================================================

@admin.register(Transcript)
class TranscriptAdmin(BaseModelAdmin):
    list_display = ('episode', 'source_type', 'format', 'revision', 'confidence_overall', 'created_at')
    list_filter = ('source_type', 'format', 'organization_uuid')
    search_fields = ('episode__title', 'raw_text')
    autocomplete_fields = ['episode', 'created_from_media_asset']
    
    fieldsets = (
        (None, {
            'fields': ('episode', 'organization_uuid', 'revision')
        }),
        ('Content', {
            'fields': ('source_type', 'format', 'raw_text', 'normalized_json'),
        }),
        ('Quality', {
            'fields': ('confidence_overall',),
        }),
        ('Provenance', {
            'fields': ('created_from_media_asset', 'ingested_by'),
        }),
        ('Metadata', {
            'fields': ('id', 'created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


# =============================================================================
# CLIP MOMENT
# =============================================================================

@admin.register(ClipMoment)
class ClipMomentAdmin(BaseModelAdmin):
    list_display = ('title', 'episode', 'time_range', 'priority', 'created_at')
    list_filter = ('priority', 'organization_uuid')
    search_fields = ('title', 'hook', 'episode__title')
    autocomplete_fields = ['episode', 'transcript']
    
    def time_range(self, obj):
        return f"{obj.start_formatted} - {obj.end_formatted}"
    time_range.short_description = "Time Range"


# =============================================================================
# AI ARTIFACT
# =============================================================================

@admin.register(AIArtifact)
class AIArtifactAdmin(BaseModelAdmin):
    list_display = ('artifact_type', 'episode', 'provider', 'model', 'approval_status_display', 'created_at')
    list_filter = ('artifact_type', 'approval_status', 'provider', 'organization_uuid')
    search_fields = ('episode__title', 'output_text', 'input_prompt')
    autocomplete_fields = ['episode']
    readonly_fields = BaseModelAdmin.readonly_fields + ('approved_by', 'approved_at')
    
    fieldsets = (
        (None, {
            'fields': ('episode', 'artifact_type', 'organization_uuid')
        }),
        ('Input', {
            'fields': ('input_prompt', 'input_context_refs'),
        }),
        ('Output', {
            'fields': ('output_text',),
        }),
        ('AI Provider', {
            'fields': ('provider', 'model', 'params'),
        }),
        ('Approval', {
            'fields': ('approval_status', 'approved_by', 'approved_at', 'transparency_summary', 'notes'),
        }),
        ('Metadata', {
            'fields': ('id', 'created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    def approval_status_display(self, obj):
        colors = {
            'pending': 'orange',
            'approved': 'green',
            'rejected': 'red',
        }
        color = colors.get(obj.approval_status, 'gray')
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_approval_status_display()
        )
    approval_status_display.short_description = "Status"


# =============================================================================
# SHOW NOTES
# =============================================================================

@admin.register(ShowNoteDraft)
class ShowNoteDraftAdmin(BaseModelAdmin):
    list_display = ('episode', 'created_from_ai_artifact', 'created_at')
    list_filter = ('organization_uuid',)
    search_fields = ('episode__title', 'markdown')
    autocomplete_fields = ['episode', 'created_from_ai_artifact']


@admin.register(ShowNoteFinal)
class ShowNoteFinalAdmin(BaseModelAdmin):
    list_display = ('episode', 'approved_by', 'approved_at')
    list_filter = ('organization_uuid',)
    search_fields = ('episode__title', 'markdown')
    autocomplete_fields = ['episode', 'source_draft']
    readonly_fields = BaseModelAdmin.readonly_fields + ('approved_by', 'approved_at')


# =============================================================================
# CHECKLIST
# =============================================================================

@admin.register(ChecklistItem)
class ChecklistItemAdmin(BaseModelAdmin):
    list_display = ('title', 'episode', 'is_required', 'is_done', 'done_by')
    list_filter = ('is_required', 'is_done', 'organization_uuid')
    search_fields = ('title', 'episode__title')
    autocomplete_fields = ['episode']


# =============================================================================
# ROLES
# =============================================================================

@admin.register(ShowRoleAssignment)
class ShowRoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'show', 'role', 'created_at')
    list_filter = ('role', 'show')
    search_fields = ('user__username', 'user__email', 'show__name')
    autocomplete_fields = ['user', 'show']


@admin.register(EpisodeRoleOverride)
class EpisodeRoleOverrideAdmin(admin.ModelAdmin):
    list_display = ('user', 'episode', 'role', 'created_at')
    list_filter = ('role',)
    search_fields = ('user__username', 'episode__title')
    autocomplete_fields = ['user', 'episode']


# =============================================================================
# EXPORT
# =============================================================================

@admin.register(ExportRecord)
class ExportRecordAdmin(BaseModelAdmin):
    list_display = ('export_type', 'episode', 'filename', 'generated_by', 'created_at')
    list_filter = ('export_type', 'organization_uuid')
    search_fields = ('filename', 'episode__title')
    autocomplete_fields = ['episode']
