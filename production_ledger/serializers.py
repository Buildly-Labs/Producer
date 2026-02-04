"""
Serializers for Production Ledger API.
"""
from rest_framework import serializers

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


class ShowSerializer(serializers.ModelSerializer):
    """Serializer for Show model."""
    
    class Meta:
        model = Show
        fields = [
            'id', 'organization_uuid', 'name', 'slug', 'description',
            'brand_primary_color', 'default_intro_text', 'default_outro_text',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']


class EpisodeSerializer(serializers.ModelSerializer):
    """Serializer for Episode model."""
    
    show_name = serializers.CharField(source='show.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    checklist_complete = serializers.SerializerMethodField()
    
    class Meta:
        model = Episode
        fields = [
            'id', 'organization_uuid', 'show', 'show_name', 'title',
            'episode_type', 'target_minutes', 'recording_context',
            'status', 'status_display', 'scheduled_for', 'publish_date',
            'live_notes', 'checklist_complete',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']
    
    def get_checklist_complete(self, obj):
        return obj.is_checklist_complete()


class SegmentSerializer(serializers.ModelSerializer):
    """Serializer for Segment model."""
    
    class Meta:
        model = Segment
        fields = [
            'id', 'organization_uuid', 'episode', 'order', 'title', 'purpose',
            'timebox_minutes', 'owner_role', 'bullet_prompts', 'key_questions',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class GuestSerializer(serializers.ModelSerializer):
    """Serializer for Guest model."""
    
    class Meta:
        model = Guest
        fields = [
            'id', 'organization_uuid', 'name', 'title', 'org', 'bio',
            'links', 'timezone', 'consent_audio', 'consent_video',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class EpisodeGuestSerializer(serializers.ModelSerializer):
    """Serializer for EpisodeGuest model."""
    
    guest_name = serializers.CharField(source='guest.name', read_only=True)
    guest_details = GuestSerializer(source='guest', read_only=True)
    
    class Meta:
        model = EpisodeGuest
        fields = [
            'id', 'organization_uuid', 'episode', 'guest', 'guest_name', 'guest_details',
            'role', 'prep_notes', 'key_topics', 'no_go_topics', 'quote_approval_status',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MediaAssetSerializer(serializers.ModelSerializer):
    """Serializer for MediaAsset model."""
    
    class Meta:
        model = MediaAsset
        fields = [
            'id', 'organization_uuid', 'episode', 'asset_type', 'source_type',
            'file', 'external_url', 'filename', 'content_type', 'file_size',
            'checksum_sha256', 'duration_seconds', 'recorded_at',
            'ingested_by', 'ingestion_status', 'error_message',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'checksum_sha256', 'created_at', 'updated_at']


class TranscriptSerializer(serializers.ModelSerializer):
    """Serializer for Transcript model."""
    
    class Meta:
        model = Transcript
        fields = [
            'id', 'organization_uuid', 'episode', 'source_type', 'format',
            'raw_text', 'normalized_json', 'confidence_overall', 'revision',
            'created_from_media_asset', 'ingested_by',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'revision', 'created_at', 'updated_at']


class ClipMomentSerializer(serializers.ModelSerializer):
    """Serializer for ClipMoment model."""
    
    start_formatted = serializers.CharField(read_only=True)
    end_formatted = serializers.CharField(read_only=True)
    duration_ms = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = ClipMoment
        fields = [
            'id', 'organization_uuid', 'episode', 'transcript',
            'start_ms', 'end_ms', 'start_formatted', 'end_formatted', 'duration_ms',
            'title', 'hook', 'caption_draft', 'tags', 'priority',
            'created_at', 'updated_at', 'created_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']


class AIArtifactSerializer(serializers.ModelSerializer):
    """Serializer for AIArtifact model."""
    
    artifact_type_display = serializers.CharField(source='get_artifact_type_display', read_only=True)
    approval_status_display = serializers.CharField(source='get_approval_status_display', read_only=True)
    
    class Meta:
        model = AIArtifact
        fields = [
            'id', 'organization_uuid', 'episode', 'artifact_type', 'artifact_type_display',
            'input_prompt', 'input_context_refs', 'output_text',
            'provider', 'model', 'params',
            'approval_status', 'approval_status_display', 'approved_by', 'approved_at',
            'transparency_summary', 'notes',
            'created_at', 'created_by',
        ]
        read_only_fields = [
            'id', 'output_text', 'provider', 'model', 'params',
            'approved_by', 'approved_at', 'created_at', 'created_by',
        ]


class AIArtifactGenerateSerializer(serializers.Serializer):
    """Serializer for AI artifact generation requests."""
    
    artifact_type = serializers.CharField()
    topic_prompt = serializers.CharField(required=False, allow_blank=True, default='')
    use_transcript = serializers.BooleanField(default=True)
    use_clips = serializers.BooleanField(default=True)


class ShowNoteDraftSerializer(serializers.ModelSerializer):
    """Serializer for ShowNoteDraft model."""
    
    class Meta:
        model = ShowNoteDraft
        fields = [
            'id', 'organization_uuid', 'episode', 'markdown',
            'chapters_json', 'resources_json', 'created_from_ai_artifact',
            'created_at', 'updated_at', 'created_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']


class ShowNoteFinalSerializer(serializers.ModelSerializer):
    """Serializer for ShowNoteFinal model."""
    
    class Meta:
        model = ShowNoteFinal
        fields = [
            'id', 'organization_uuid', 'episode', 'source_draft', 'markdown',
            'approved_by', 'approved_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'approved_by', 'approved_at', 'created_at', 'updated_at']


class ChecklistItemSerializer(serializers.ModelSerializer):
    """Serializer for ChecklistItem model."""
    
    class Meta:
        model = ChecklistItem
        fields = [
            'id', 'organization_uuid', 'episode', 'title',
            'is_required', 'is_done', 'done_by', 'done_at', 'sort_order',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'done_by', 'done_at', 'created_at', 'updated_at']


class ShowRoleAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for ShowRoleAssignment model."""
    
    username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = ShowRoleAssignment
        fields = ['id', 'show', 'user', 'username', 'role', 'created_at']
        read_only_fields = ['id', 'created_at']
