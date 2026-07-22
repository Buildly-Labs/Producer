"""
REST API serializers for Splice video editor.

Handles input/output serialization for all API endpoints.
"""
from rest_framework import serializers

from splice.models import (
    EditorProject, LocalEngineInstallation, LocalEngineSession,
    LocalProcessingJob, RenderPlan, MediaLocation, MediaFingerprint,
)


class LocalEngineInstallationSerializer(serializers.ModelSerializer):
    """Serializer for LocalEngineInstallation."""

    registration_key = serializers.SerializerMethodField()

    class Meta:
        model = LocalEngineInstallation
        fields = [
            'id', 'engine_uuid', 'engine_name', 'platform',
            'is_online', 'version', 'last_heartbeat',
            'auto_process_jobs', 'max_concurrent_jobs', 'proxy_quality',
            'registration_key',  # Only in response to registration
        ]
        read_only_fields = [
            'id', 'engine_uuid', 'is_online', 'last_heartbeat',
        ]

    def get_registration_key(self, obj):
        """Don't expose registration_key_hash."""
        # Only populated in create response, otherwise None
        return None


class LocalEngineSessionSerializer(serializers.ModelSerializer):
    """Serializer for LocalEngineSession."""

    class Meta:
        model = LocalEngineSession
        fields = [
            'id', 'session_token', 'browser_origin',
            'expires_at', 'last_heartbeat',
        ]
        read_only_fields = [
            'id', 'session_token', 'expires_at', 'last_heartbeat',
        ]


class LocalProcessingJobSerializer(serializers.ModelSerializer):
    """Serializer for LocalProcessingJob."""

    job_type_display = serializers.CharField(
        source='get_job_type_display',
        read_only=True
    )
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )

    class Meta:
        model = LocalProcessingJob
        fields = [
            'id', 'job_type', 'job_type_display', 'status', 'status_display',
            'priority', 'progress_percent',
            'input_data', 'output_data',
            'error_code', 'error_message',
            'started_at', 'completed_at',
            'user_confirmed', 'auto_start_approved',
            'created_at', 'created_by',
        ]
        read_only_fields = [
            'id', 'created_at', 'created_by',
            'started_at', 'completed_at',
        ]


class MediaLocationSerializer(serializers.ModelSerializer):
    """Serializer for MediaLocation."""

    location_type_display = serializers.CharField(
        source='get_location_type_display',
        read_only=True
    )
    availability_display = serializers.CharField(
        source='get_availability_display',
        read_only=True
    )

    class Meta:
        model = MediaLocation
        fields = [
            'id', 'asset_id', 'location_type', 'location_type_display',
            'availability', 'availability_display',
            'local_engine_id', 'local_location_id',
            'cloud_path', 'remote_url',
            'proxy_available', 'waveform_available', 'thumbnail_available',
            'last_verified',
        ]
        read_only_fields = ['id', 'last_verified']


class MediaFingerprintSerializer(serializers.ModelSerializer):
    """Serializer for MediaFingerprint."""

    fingerprint_method_display = serializers.CharField(
        source='get_fingerprint_method_display',
        read_only=True
    )

    class Meta:
        model = MediaFingerprint
        fields = [
            'id', 'asset_id',
            'fingerprint_version', 'fingerprint_method', 'fingerprint_method_display',
            'file_size', 'duration_ms',
            'codec_metadata',
            'first_chunk_hash', 'last_chunk_hash', 'partial_hash', 'full_hash',
            'verified_at',
        ]
        read_only_fields = ['id', 'verified_at']


class RenderPlanSerializer(serializers.ModelSerializer):
    """Serializer for RenderPlan."""

    class Meta:
        model = RenderPlan
        fields = [
            'id', 'project_id', 'revision',
            'asset_selections', 'operations',
            'camera_cuts', 'sync_offsets',
            'output_preset',
            'canvas_width', 'canvas_height', 'frame_rate',
            'loudness_preset',
            'created_at', 'created_by',
        ]
        read_only_fields = ['id', 'created_at', 'created_by']


class EditorProjectSerializer(serializers.ModelSerializer):
    """Serializer for EditorProject."""

    processing_mode_display = serializers.CharField(
        source='get_processing_mode_display',
        read_only=True
    )
    render_location_display = serializers.CharField(
        source='get_render_location_display',
        read_only=True
    )

    class Meta:
        model = EditorProject
        fields = [
            'id', 'episode_id',
            'frame_rate', 'canvas_width', 'canvas_height', 'aspect_ratio',
            'timeline_duration_ms',
            'autosave_enabled', 'current_revision',
            'processing_mode', 'processing_mode_display',
            'render_location', 'render_location_display',
            'allow_cloud_upload',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'current_revision', 'created_at', 'updated_at']
