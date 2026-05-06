"""
API Views for Production Ledger.

All endpoints enforce organization scoping and RBAC.
"""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import OperationalError, ProgrammingError

from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .constants import ApprovalStatus, ArtifactType, EpisodeStatus, Role
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
    Transcript,
)
from .permissions import (
    can_approve_ai_artifact,
    can_approve_show_notes,
    can_create_ai_artifact,
    can_export,
    can_manage_clips,
    can_manage_guests,
    can_manage_transcripts,
    can_transition_status,
    get_user_organization_uuid,
    has_minimum_role,
    has_role,
)
from .serializers import (
    AIArtifactGenerateSerializer,
    AIArtifactSerializer,
    ChecklistItemSerializer,
    ClipMomentSerializer,
    EpisodeGuestSerializer,
    EpisodeSerializer,
    GuestSerializer,
    MediaAssetSerializer,
    SegmentSerializer,
    ShowNoteDraftSerializer,
    ShowNoteFinalSerializer,
    ShowSerializer,
    TranscriptSerializer,
)
from .services.ai import (
    generate_chapters,
    generate_questions,
    generate_segment_suggestions,
    generate_show_notes,
    generate_social_posts,
    generate_titles,
)
from .services.exports import (
    export_clips_csv,
    export_episode_package_json,
    export_show_notes_markdown,
)


# =============================================================================
# BASE CLASSES
# =============================================================================

class OrganizationScopedMixin:
    """Mixin to handle organization scoping in API views."""
    
    def get_organization_uuid(self):
        """Get the organization UUID for the current user."""
        org_uuid = get_user_organization_uuid(self.request.user)
        if not org_uuid:
            return None
        return org_uuid
    
    def get_queryset(self):
        """Filter queryset by organization."""
        qs = super().get_queryset()
        org_uuid = self.get_organization_uuid()
        if org_uuid:
            return qs.filter(organization_uuid=org_uuid)
        return qs.none()
    
    def perform_create(self, serializer):
        """Set organization and audit fields on create."""
        serializer.save(
            organization_uuid=self.get_organization_uuid(),
            created_by=self.request.user,
        )


# =============================================================================
# SHOWS
# =============================================================================

class ShowListCreateAPI(OrganizationScopedMixin, generics.ListCreateAPIView):
    """List and create shows."""
    
    queryset = Show.objects.all()
    serializer_class = ShowSerializer
    permission_classes = [IsAuthenticated]


class ShowDetailAPI(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a show."""
    
    queryset = Show.objects.all()
    serializer_class = ShowSerializer
    permission_classes = [IsAuthenticated]
    
    def perform_update(self, serializer):
        if not has_role(self.request.user, self.get_object(), [Role.ADMIN]):
            raise PermissionDenied('Admin role required')
        serializer.save(updated_by=self.request.user)


# =============================================================================
# EPISODES
# =============================================================================

class EpisodeListCreateAPI(OrganizationScopedMixin, generics.ListCreateAPIView):
    """List and create episodes."""
    
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        qs = super().get_queryset()
        
        # Filter by show if provided
        show_id = self.request.query_params.get('show')
        if show_id:
            qs = qs.filter(show_id=show_id)
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        
        return qs.select_related('show')


class EpisodeDetailAPI(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete an episode."""
    
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer
    permission_classes = [IsAuthenticated]
    
    def perform_update(self, serializer):
        episode = self.get_object()
        if not has_role(self.request.user, episode, [Role.ADMIN, Role.HOST, Role.PRODUCER]):
            raise PermissionDenied('Insufficient permissions')
        serializer.save(updated_by=self.request.user)


class EpisodeStatusAPI(APIView):
    """Change episode status."""
    
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        """Return current status and available transitions for an episode."""
        episode = get_object_or_404(Episode, pk=pk)

        if not has_minimum_role(request.user, episode.show, Role.GUEST):
            return Response({'error': 'Guest role required.'}, status=status.HTTP_403_FORBIDDEN)

        available = EpisodeStatus.TRANSITIONS.get(episode.status, [])
        choices = dict(EpisodeStatus.CHOICES)
        return Response({
            'episode_id': str(episode.id),
            'current_status': episode.status,
            'current_status_label': episode.get_status_display(),
            'available_transitions': [
                {'status': s, 'label': choices.get(s, s.title())}
                for s in available
            ],
            'checklist_complete': episode.is_checklist_complete(),
        })
    
    def post(self, request, pk):
        episode = get_object_or_404(Episode, pk=pk)
        new_status = request.data.get('status')
        
        if not new_status:
            return Response({'error': 'Status is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not can_transition_status(request.user, episode, new_status):
            return Response(
                {'error': 'You do not have permission to make this transition'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            episode.transition_to(new_status, user=request.user)
            return Response(EpisodeSerializer(episode).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# =============================================================================
# SEGMENTS
# =============================================================================

class SegmentListCreateAPI(OrganizationScopedMixin, generics.ListCreateAPIView):
    """List and create segments for an episode."""
    
    queryset = Segment.objects.all()
    serializer_class = SegmentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        qs = super().get_queryset()
        episode_id = self.kwargs.get('episode_id')
        return qs.filter(episode_id=episode_id).order_by('order')
    
    def perform_create(self, serializer):
        episode = get_object_or_404(Episode, pk=self.kwargs['episode_id'])
        if not has_role(self.request.user, episode, [Role.ADMIN, Role.HOST, Role.PRODUCER]):
            raise PermissionError("Insufficient permissions")
        serializer.save(
            episode=episode,
            organization_uuid=episode.organization_uuid,
            created_by=self.request.user,
        )


class SegmentDetailAPI(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a segment."""
    
    queryset = Segment.objects.all()
    serializer_class = SegmentSerializer
    permission_classes = [IsAuthenticated]


# =============================================================================
# GUESTS
# =============================================================================

class GuestListCreateAPI(OrganizationScopedMixin, generics.ListCreateAPIView):
    """List and create guests."""
    
    queryset = Guest.objects.all()
    serializer_class = GuestSerializer
    permission_classes = [IsAuthenticated]


class GuestDetailAPI(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a guest."""
    
    queryset = Guest.objects.all()
    serializer_class = GuestSerializer
    permission_classes = [IsAuthenticated]


# =============================================================================
# EPISODE GUESTS
# =============================================================================

class EpisodeGuestListCreateAPI(OrganizationScopedMixin, generics.ListCreateAPIView):
    """List and add guests to an episode."""
    
    queryset = EpisodeGuest.objects.all()
    serializer_class = EpisodeGuestSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        qs = super().get_queryset()
        episode_id = self.kwargs.get('episode_id')
        return qs.filter(episode_id=episode_id).select_related('guest')
    
    def perform_create(self, serializer):
        episode = get_object_or_404(Episode, pk=self.kwargs['episode_id'])
        if not can_manage_guests(self.request.user, episode):
            raise PermissionError("Cannot manage guests")
        serializer.save(
            episode=episode,
            organization_uuid=episode.organization_uuid,
            created_by=self.request.user,
        )


class EpisodeGuestDetailAPI(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete an episode guest."""
    
    queryset = EpisodeGuest.objects.all()
    serializer_class = EpisodeGuestSerializer
    permission_classes = [IsAuthenticated]


# =============================================================================
# MEDIA ASSETS
# =============================================================================

class MediaAssetListCreateAPI(OrganizationScopedMixin, generics.ListCreateAPIView):
    """List and create media assets for an episode."""
    
    queryset = MediaAsset.objects.all()
    serializer_class = MediaAssetSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        qs = super().get_queryset()
        episode_id = self.kwargs.get('episode_id')
        return qs.filter(episode_id=episode_id)
    
    def perform_create(self, serializer):
        episode = get_object_or_404(Episode, pk=self.kwargs['episode_id'])
        serializer.save(
            episode=episode,
            organization_uuid=episode.organization_uuid,
            ingested_by=self.request.user,
            created_by=self.request.user,
        )


class MediaAssetDetailAPI(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a media asset."""
    
    queryset = MediaAsset.objects.all()
    serializer_class = MediaAssetSerializer
    permission_classes = [IsAuthenticated]


# =============================================================================
# TRANSCRIPTS
# =============================================================================

class TranscriptListCreateAPI(OrganizationScopedMixin, generics.ListCreateAPIView):
    """List and create transcripts for an episode."""
    
    queryset = Transcript.objects.all()
    serializer_class = TranscriptSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        qs = super().get_queryset()
        episode_id = self.kwargs.get('episode_id')
        return qs.filter(episode_id=episode_id).order_by('-revision')
    
    def perform_create(self, serializer):
        episode = get_object_or_404(Episode, pk=self.kwargs['episode_id'])
        if not can_manage_transcripts(self.request.user, episode):
            raise PermissionError("Cannot manage transcripts")
        
        # Get next revision number
        max_rev = episode.transcripts.order_by('-revision').values_list('revision', flat=True).first() or 0
        
        serializer.save(
            episode=episode,
            organization_uuid=episode.organization_uuid,
            revision=max_rev + 1,
            ingested_by=self.request.user,
            created_by=self.request.user,
        )


class TranscriptDetailAPI(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a transcript."""
    
    queryset = Transcript.objects.all()
    serializer_class = TranscriptSerializer
    permission_classes = [IsAuthenticated]


# =============================================================================
# CLIPS
# =============================================================================

class ClipMomentListCreateAPI(OrganizationScopedMixin, generics.ListCreateAPIView):
    """List and create clip moments for an episode."""
    
    queryset = ClipMoment.objects.all()
    serializer_class = ClipMomentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        qs = super().get_queryset()
        episode_id = self.kwargs.get('episode_id')
        return qs.filter(episode_id=episode_id).order_by('start_ms')
    
    def perform_create(self, serializer):
        episode = get_object_or_404(Episode, pk=self.kwargs['episode_id'])
        if not can_manage_clips(self.request.user, episode):
            raise PermissionError("Cannot manage clips")
        serializer.save(
            episode=episode,
            organization_uuid=episode.organization_uuid,
            created_by=self.request.user,
        )


class ClipMomentDetailAPI(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a clip moment."""
    
    queryset = ClipMoment.objects.all()
    serializer_class = ClipMomentSerializer
    permission_classes = [IsAuthenticated]


# =============================================================================
# AI ARTIFACTS
# =============================================================================

class AIArtifactListAPI(OrganizationScopedMixin, generics.ListAPIView):
    """List AI artifacts for an episode."""
    
    queryset = AIArtifact.objects.all()
    serializer_class = AIArtifactSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        qs = super().get_queryset()
        episode_id = self.kwargs.get('episode_id')
        return qs.filter(episode_id=episode_id).order_by('-created_at')


class AIArtifactGenerateAPI(APIView):
    """Generate a new AI artifact."""
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request, episode_id):
        episode = get_object_or_404(Episode, pk=episode_id)
        
        if not can_create_ai_artifact(request.user, episode):
            return Response(
                {'error': 'You do not have permission to generate AI content'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = AIArtifactGenerateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        artifact_type = serializer.validated_data['artifact_type']
        topic_prompt = serializer.validated_data.get('topic_prompt', '')
        use_transcript = serializer.validated_data.get('use_transcript', True)
        use_clips = serializer.validated_data.get('use_clips', True)
        
        # Get context
        transcript = None
        clips = None
        
        if use_transcript:
            transcript = episode.transcripts.order_by('-revision').first()
        if use_clips:
            clips = list(episode.clip_moments.all())
        
        try:
            if artifact_type == ArtifactType.QUESTIONS:
                artifact = generate_questions(episode, topic_prompt, request.user, transcript)
            elif artifact_type == ArtifactType.SHOW_NOTES:
                artifact = generate_show_notes(episode, request.user, transcript, clips)
            elif artifact_type == ArtifactType.SOCIAL_POSTS:
                draft = episode.show_note_drafts.order_by('-created_at').first()
                artifact = generate_social_posts(episode, request.user, draft.markdown if draft else None)
            elif artifact_type == ArtifactType.SEGMENT_SUGGESTIONS:
                artifact = generate_segment_suggestions(episode, request.user, topic_prompt)
            elif artifact_type == ArtifactType.TITLES:
                artifact = generate_titles(episode, request.user, transcript)
            elif artifact_type == ArtifactType.CHAPTERS:
                artifact = generate_chapters(episode, request.user, transcript)
            else:
                return Response(
                    {'error': f'Unknown artifact type: {artifact_type}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            return Response(AIArtifactSerializer(artifact).data, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AIArtifactDetailAPI(OrganizationScopedMixin, generics.RetrieveAPIView):
    """Retrieve an AI artifact."""
    
    queryset = AIArtifact.objects.all()
    serializer_class = AIArtifactSerializer
    permission_classes = [IsAuthenticated]


class AIArtifactApproveAPI(APIView):
    """Approve or reject an AI artifact."""
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        artifact = get_object_or_404(AIArtifact, pk=pk)
        
        if not can_approve_ai_artifact(request.user, artifact.episode):
            return Response(
                {'error': 'You do not have permission to approve AI artifacts'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        action = request.data.get('action')
        notes = request.data.get('notes', '')
        
        if action == 'approve':
            artifact.approve(request.user)
        elif action == 'reject':
            artifact.reject(request.user, notes)
        else:
            return Response(
                {'error': 'Action must be "approve" or "reject"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(AIArtifactSerializer(artifact).data)


# =============================================================================
# SHOW NOTES
# =============================================================================

class ShowNoteDraftListCreateAPI(OrganizationScopedMixin, generics.ListCreateAPIView):
    """List and create show note drafts."""
    
    queryset = ShowNoteDraft.objects.all()
    serializer_class = ShowNoteDraftSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        qs = super().get_queryset()
        episode_id = self.kwargs.get('episode_id')
        return qs.filter(episode_id=episode_id).order_by('-created_at')
    
    def perform_create(self, serializer):
        episode = get_object_or_404(Episode, pk=self.kwargs['episode_id'])
        serializer.save(
            episode=episode,
            organization_uuid=episode.organization_uuid,
            created_by=self.request.user,
        )


class ShowNoteDraftDetailAPI(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a show note draft."""
    
    queryset = ShowNoteDraft.objects.all()
    serializer_class = ShowNoteDraftSerializer
    permission_classes = [IsAuthenticated]


class ShowNoteFinalAPI(APIView):
    """Get or create final show notes."""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, episode_id):
        episode = get_object_or_404(Episode, pk=episode_id)
        try:
            final = episode.show_note_final
            return Response(ShowNoteFinalSerializer(final).data)
        except ShowNoteFinal.DoesNotExist:
            return Response({'error': 'No final show notes'}, status=status.HTTP_404_NOT_FOUND)
    
    def post(self, request, episode_id):
        episode = get_object_or_404(Episode, pk=episode_id)
        
        if not can_approve_show_notes(request.user, episode):
            return Response(
                {'error': 'You do not have permission to finalize show notes'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not episode.is_checklist_complete():
            return Response(
                {'error': 'Cannot finalize until all required checklist items are complete'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = ShowNoteFinalSerializer(data=request.data)
        if serializer.is_valid():
            final, created = ShowNoteFinal.objects.update_or_create(
                episode=episode,
                defaults={
                    'organization_uuid': episode.organization_uuid,
                    'markdown': serializer.validated_data['markdown'],
                    'source_draft': serializer.validated_data.get('source_draft'),
                    'approved_by': request.user,
                    'approved_at': timezone.now(),
                    'created_by': request.user if created else None,
                    'updated_by': request.user,
                }
            )
            return Response(ShowNoteFinalSerializer(final).data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# =============================================================================
# CHECKLIST
# =============================================================================

class ChecklistAPI(OrganizationScopedMixin, generics.ListAPIView):
    """List checklist items for an episode."""
    
    queryset = ChecklistItem.objects.all()
    serializer_class = ChecklistItemSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        qs = super().get_queryset()
        episode_id = self.kwargs.get('episode_id')
        return qs.filter(episode_id=episode_id).order_by('sort_order')


class ChecklistToggleAPI(APIView):
    """Toggle a checklist item."""
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        item = get_object_or_404(ChecklistItem, pk=pk)
        
        if item.is_done:
            item.mark_undone()
        else:
            item.mark_done(request.user)
        
        return Response(ChecklistItemSerializer(item).data)


# =============================================================================
# EXPORTS
# =============================================================================

class ExportJSONAPI(APIView):
    """Export episode as JSON."""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        episode = get_object_or_404(Episode, pk=pk)
        
        if not can_export(request.user, episode):
            return Response(
                {'error': 'You do not have permission to export'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        data = export_episode_package_json(episode)
        return Response(data)


class ExportMarkdownAPI(APIView):
    """Export show notes as Markdown."""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        episode = get_object_or_404(Episode, pk=pk)
        
        if not can_export(request.user, episode):
            return Response(
                {'error': 'You do not have permission to export'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        content = export_show_notes_markdown(episode)
        return Response({'markdown': content})


class ExportClipsAPI(APIView):
    """Export clips as CSV."""
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        episode = get_object_or_404(Episode, pk=pk)
        
        if not can_export(request.user, episode):
            return Response(
                {'error': 'You do not have permission to export'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        content = export_clips_csv(episode)
        return Response({'csv': content})


# =============================================================================
# VIDEO UPLOAD + TRANSCRIPTION
# =============================================================================

class UploadVideoAPI(APIView):
    """
    POST /api/episodes/<episode_id>/upload-video/

    Upload a video file to DO Spaces, create a MediaAsset, and optionally
    auto-trigger transcription.

    Form fields:
        video       — multipart video file (required)
        label       — display label (optional)
        auto_transcribe — 'true' to immediately trigger Whisper (default: true)

    Returns:
        {media_asset_id, spaces_key, public_url, transcript_id (if transcribed)}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, episode_id):
        from .models import MediaAsset  # noqa: PLC0415
        from .constants import AssetType, IngestionStatus, SourceType  # noqa: PLC0415
        from .services import storage, transcription as transcription_svc  # noqa: PLC0415

        episode = get_object_or_404(Episode, pk=episode_id)
        if not has_minimum_role(request.user, episode.show, Role.PRODUCER):
            return Response({'error': 'Producer role required.'}, status=status.HTTP_403_FORBIDDEN)

        video_file = request.FILES.get('video')
        if not video_file:
            return Response({'error': 'video file is required.'}, status=status.HTTP_400_BAD_REQUEST)

        label = request.data.get('label', video_file.name)
        auto_transcribe = request.data.get('auto_transcribe', 'true').lower() != 'false'

        # Upload to DO Spaces
        spaces_key = storage.episode_video_key(
            str(episode.organization_uuid),
            str(episode.id),
            video_file.name,
        )
        try:
            public_url = storage.upload_file(
                video_file,
                spaces_key,
                content_type=video_file.content_type or 'video/mp4',
                public=True,
                extra_metadata={'episode-id': str(episode.id)},
            )
        except Exception as exc:
            return Response({'error': f'Upload failed: {exc}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Create MediaAsset record
        media_asset = MediaAsset.objects.create(
            episode=episode,
            organization_uuid=episode.organization_uuid,
            asset_type=AssetType.VIDEO,
            source_type=SourceType.EXTERNAL_LINK,
            external_url=public_url,
            label=label,
            filename=video_file.name,
            content_type=video_file.content_type or 'video/mp4',
            file_size=video_file.size,
            ingestion_status=IngestionStatus.READY,
            ingested_by=request.user,
            created_by=request.user,
            updated_by=request.user,
        )

        result = {
            'media_asset_id': str(media_asset.id),
            'spaces_key': spaces_key,
            'public_url': public_url,
            'transcript_id': None,
        }

        # Optionally trigger transcription
        if auto_transcribe:
            try:
                transcript = transcription_svc.transcribe_media_asset(media_asset, user=request.user)
                result['transcript_id'] = str(transcript.id)
            except Exception as exc:
                result['transcription_error'] = str(exc)

        return Response(result, status=status.HTTP_201_CREATED)


class TranscribeMediaAssetAPI(APIView):
    """
    POST /api/media/<pk>/transcribe/

    Trigger Whisper transcription on an existing MediaAsset.

    Returns:
        {transcript_id, revision, provider, model}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from .models import MediaAsset  # noqa: PLC0415
        from .services import transcription as transcription_svc  # noqa: PLC0415

        media_asset = get_object_or_404(MediaAsset, pk=pk)
        if not has_minimum_role(request.user, media_asset.episode.show, Role.PRODUCER):
            return Response({'error': 'Producer role required.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            transcript = transcription_svc.transcribe_media_asset(media_asset, user=request.user)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        normalized = transcript.normalized_json or {}
        return Response({
            'transcript_id': str(transcript.id),
            'revision': transcript.revision,
            'provider': normalized.get('provider'),
            'model': normalized.get('model'),
            'duration_seconds': normalized.get('duration'),
            'segment_count': len(normalized.get('segments', [])),
        }, status=status.HTTP_201_CREATED)


# =============================================================================
# PODCAST DISTRIBUTION
# =============================================================================

class PodcastFeedConfigAPI(APIView):
    """
    GET  /api/shows/<show_id>/podcast-feed/  — retrieve feed config
    PUT  /api/shows/<show_id>/podcast-feed/  — update feed config fields
    """
    permission_classes = [IsAuthenticated]

    def _get_show(self, show_id, user):
        show = get_object_or_404(Show, pk=show_id)
        if not has_minimum_role(user, show, Role.PRODUCER):
            return None, Response({'error': 'Producer role required.'}, status=status.HTTP_403_FORBIDDEN)
        return show, None

    def get(self, request, show_id):
        from .models import PodcastFeedConfig  # noqa: PLC0415
        from .services.distribution import _get_feed_config  # noqa: PLC0415

        show, err = self._get_show(show_id, request.user)
        if err:
            return err
        config = _get_feed_config(show)
        return Response({
            'id': str(config.id),
            'show': str(show.id),
            'feed_title': config.feed_title,
            'feed_description': config.feed_description,
            'feed_language': config.feed_language,
            'author_name': config.author_name,
            'author_email': config.author_email,
            'category': config.category,
            'subcategory': config.subcategory,
            'explicit': config.explicit,
            'website_url': config.website_url,
            'cover_art_url': config.cover_art_url,
            'feed_public_url': config.feed_public_url,
            'feed_last_built': config.feed_last_built,
        })

    def put(self, request, show_id):
        from .services.distribution import _get_feed_config  # noqa: PLC0415

        show, err = self._get_show(show_id, request.user)
        if err:
            return err
        config = _get_feed_config(show)

        updatable = [
            'feed_title', 'feed_description', 'feed_language',
            'author_name', 'author_email', 'category', 'subcategory',
            'explicit', 'website_url', 'cover_art_url',
        ]
        for field in updatable:
            if field in request.data:
                setattr(config, field, request.data[field])
        config.updated_by = request.user
        config.save()
        return Response({'status': 'updated', 'feed_public_url': config.feed_public_url})


class RebuildPodcastFeedAPI(APIView):
    """
    POST /api/shows/<show_id>/podcast-feed/rebuild/

    Regenerate and re-upload the RSS feed XML to DO Spaces.
    Returns the new public feed URL.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, show_id):
        from .services.distribution import build_and_publish_feed  # noqa: PLC0415

        show = get_object_or_404(Show, pk=show_id)
        if not has_minimum_role(request.user, show, Role.PRODUCER):
            return Response({'error': 'Producer role required.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            feed_url = build_and_publish_feed(show, user=request.user)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'feed_url': feed_url, 'status': 'rebuilt'})


class UploadCoverArtAPI(APIView):
    """
    POST /api/shows/<show_id>/podcast-feed/cover-art/

    Upload podcast cover art to DO Spaces and update PodcastFeedConfig.
    Apple Podcasts requires 1400×1400 – 3000×3000 px JPEG or PNG.

    Form fields:
        cover_art  — multipart image file (jpg / png)

    Returns:
        {cover_art_url}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, show_id):
        from .services import storage  # noqa: PLC0415
        from .services.distribution import _get_feed_config  # noqa: PLC0415

        show = get_object_or_404(Show, pk=show_id)
        if not has_minimum_role(request.user, show, Role.PRODUCER):
            return Response({'error': 'Producer role required.'}, status=status.HTTP_403_FORBIDDEN)

        image_file = request.FILES.get('cover_art')
        if not image_file:
            return Response({'error': 'cover_art file is required.'}, status=status.HTTP_400_BAD_REQUEST)

        allowed_types = {'image/jpeg', 'image/png', 'image/jpg'}
        if image_file.content_type not in allowed_types:
            return Response(
                {'error': f'cover_art must be JPEG or PNG, got {image_file.content_type}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        spaces_key = storage.cover_art_key(
            str(show.organization_uuid), show.slug, image_file.name
        )
        try:
            public_url = storage.upload_file(
                image_file,
                spaces_key,
                content_type=image_file.content_type,
                public=True,
                extra_metadata={'show-slug': show.slug},
            )
        except Exception as exc:
            return Response({'error': f'Upload failed: {exc}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        config = _get_feed_config(show)
        config.cover_art_url = public_url
        config.updated_by = request.user
        config.save(update_fields=['cover_art_url', 'updated_by', 'updated_at'])

        return Response({'cover_art_url': public_url}, status=status.HTTP_200_OK)


class PodcastDistributionGuideAPI(APIView):
    """
    GET /api/shows/<show_id>/podcast-distribution-guide/

    Returns a step-by-step guide for submitting the show's RSS feed to each
    major podcast platform, including current distribution status.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, show_id):
        from .services.distribution import get_platform_submission_guide  # noqa: PLC0415

        show = get_object_or_404(Show, pk=show_id)
        if not has_minimum_role(request.user, show, Role.HOST):
            return Response({'error': 'Host role required.'}, status=status.HTTP_403_FORBIDDEN)

        guide = get_platform_submission_guide(show)
        return Response({'show': str(show.id), 'platforms': guide})


class PublishEpisodeAudioAPI(APIView):
    """
    POST /api/episodes/<episode_id>/publish-audio/

    Upload episode audio to DO Spaces and create PodcastDistribution records
    for all platforms.  Rebuilds the RSS feed automatically.

    Form fields:
        audio          — multipart audio file (mp3 / m4a required)
        duration_seconds — integer (optional, auto-detected when possible)
        rebuild_feed   — 'true' to also rebuild the RSS feed (default: true)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, episode_id):
        from .services.distribution import build_and_publish_feed, publish_episode_audio  # noqa: PLC0415

        episode = get_object_or_404(Episode, pk=episode_id)
        if not has_minimum_role(request.user, episode.show, Role.PRODUCER):
            return Response({'error': 'Producer role required.'}, status=status.HTTP_403_FORBIDDEN)

        audio_file = request.FILES.get('audio')
        if not audio_file:
            return Response({'error': 'audio file is required.'}, status=status.HTTP_400_BAD_REQUEST)

        duration_seconds = int(request.data.get('duration_seconds', 0) or 0)
        rebuild_feed = request.data.get('rebuild_feed', 'true').lower() != 'false'

        try:
            result = publish_episode_audio(
                episode,
                audio_file,
                audio_file.name,
                duration_seconds=duration_seconds,
                user=request.user,
            )
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        feed_url = None
        if rebuild_feed:
            try:
                feed_url = build_and_publish_feed(episode.show, user=request.user)
            except Exception as exc:
                feed_url = f'Feed rebuild failed: {exc}'

        return Response({
            'audio_url': result['audio_url'],
            'distribution_count': len(result['distributions']),
            'feed_url': feed_url,
        }, status=status.HTTP_201_CREATED)


class EpisodeDistributionListAPI(APIView):
    """
    GET /api/episodes/<episode_id>/distributions/

    List PodcastDistribution records for an episode (one per platform).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, episode_id):
        from .models import PodcastDistribution  # noqa: PLC0415

        episode = get_object_or_404(Episode, pk=episode_id)
        if not has_minimum_role(request.user, episode.show, Role.HOST):
            return Response({'error': 'Host role required.'}, status=status.HTTP_403_FORBIDDEN)

        dists = PodcastDistribution.objects.filter(episode=episode).order_by('platform')
        data = [
            {
                'id': str(d.id),
                'platform': d.platform,
                'platform_label': d.get_platform_display(),
                'status': d.status,
                'audio_public_url': d.audio_public_url,
                'platform_url': d.platform_url,
                'submitted_at': d.submitted_at,
                'went_live_at': d.went_live_at,
                'error_message': d.error_message,
            }
            for d in dists
        ]
        return Response({'episode': str(episode.id), 'distributions': data})


# =============================================================================
# VIDEO SHORTS
# =============================================================================

class VideoShortListAPI(APIView):
    """
    GET /api/episodes/<episode_id>/shorts/

    List all VideoShorts for an episode.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, episode_id):
        from .models import VideoShort  # noqa: PLC0415

        episode = get_object_or_404(Episode, pk=episode_id)
        if not has_minimum_role(request.user, episode.show, Role.HOST):
            return Response({'error': 'Host role required.'}, status=status.HTTP_403_FORBIDDEN)

        shorts = VideoShort.objects.filter(episode=episode).order_by('start_ms')
        data = [
            {
                'id': str(s.id),
                'title': s.title,
                'caption': s.caption,
                'hashtags': s.hashtags,
                'start_ms': s.start_ms,
                'end_ms': s.end_ms,
                'start_formatted': s.start_formatted,
                'end_formatted': s.end_formatted,
                'duration_ms': s.duration_ms,
                'aspect_ratio': s.aspect_ratio,
                'status': s.status,
                'public_url': s.public_url,
                'shareable_link': s.shareable_link,
                'error_message': s.error_message,
            }
            for s in shorts
        ]
        return Response({'episode': str(episode.id), 'shorts': data})


class IdentifyShortsAPI(APIView):
    """
    POST /api/episodes/<episode_id>/shorts/identify/

    Use AI to identify compelling clip moments and queue VideoShort objects.

    Body (JSON):
        aspect_ratio   — '9:16' | '1:1' | '16:9' (default: '9:16')
        max_clips      — integer 1-10 (default: 5)
        transcript_id  — UUID of specific transcript to use (optional)

    Returns:
        {queued: [{id, title, start_ms, end_ms, status}, ...]}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, episode_id):
        from .models import Transcript, VideoShort  # noqa: PLC0415
        from .services.shorts import identify_and_queue_shorts  # noqa: PLC0415
        from .constants import ShortAspectRatio  # noqa: PLC0415

        episode = get_object_or_404(Episode, pk=episode_id)
        if not has_minimum_role(request.user, episode.show, Role.PRODUCER):
            return Response({'error': 'Producer role required.'}, status=status.HTTP_403_FORBIDDEN)

        aspect_ratio = request.data.get('aspect_ratio', ShortAspectRatio.VERTICAL)
        valid_ratios = [r for r, _ in ShortAspectRatio.CHOICES]
        if aspect_ratio not in valid_ratios:
            return Response({'error': f'aspect_ratio must be one of {valid_ratios}'}, status=status.HTTP_400_BAD_REQUEST)

        max_clips = int(request.data.get('max_clips', 5))
        if not 1 <= max_clips <= 10:
            return Response({'error': 'max_clips must be between 1 and 10.'}, status=status.HTTP_400_BAD_REQUEST)

        transcript = None
        transcript_id = request.data.get('transcript_id')
        if transcript_id:
            transcript = get_object_or_404(Transcript, pk=transcript_id, episode=episode)

        try:
            video_shorts = identify_and_queue_shorts(
                episode,
                transcript=transcript,
                aspect_ratio=aspect_ratio,
                max_clips=max_clips,
                user=request.user,
            )
        except RuntimeError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        data = [
            {'id': str(s.id), 'title': s.title, 'start_ms': s.start_ms, 'end_ms': s.end_ms, 'status': s.status}
            for s in video_shorts
        ]
        return Response({'queued': data, 'count': len(data)}, status=status.HTTP_201_CREATED)


class VideoShortDetailAPI(APIView):
    """
    GET  /api/shorts/<pk>/  — retrieve a VideoShort
    PATCH /api/shorts/<pk>/ — update title, caption, hashtags
    DELETE /api/shorts/<pk>/ — delete
    """
    permission_classes = [IsAuthenticated]

    def _get_short(self, pk, user, min_role=Role.HOST):
        from .models import VideoShort  # noqa: PLC0415

        short = get_object_or_404(VideoShort, pk=pk)
        if not has_minimum_role(user, short.episode.show, min_role):
            return None, Response({'error': 'Insufficient role.'}, status=status.HTTP_403_FORBIDDEN)
        return short, None

    def get(self, request, pk):
        short, err = self._get_short(pk, request.user)
        if err:
            return err
        return Response({
            'id': str(short.id),
            'title': short.title,
            'caption': short.caption,
            'hashtags': short.hashtags,
            'start_ms': short.start_ms,
            'end_ms': short.end_ms,
            'start_formatted': short.start_formatted,
            'end_formatted': short.end_formatted,
            'duration_ms': short.duration_ms,
            'aspect_ratio': short.aspect_ratio,
            'status': short.status,
            'public_url': short.public_url,
            'shareable_link': short.shareable_link,
            'file_size': short.file_size,
            'duration_seconds': short.duration_seconds,
            'render_completed_at': short.render_completed_at,
            'error_message': short.error_message,
        })

    def patch(self, request, pk):
        short, err = self._get_short(pk, request.user, min_role=Role.PRODUCER)
        if err:
            return err
        for field in ('title', 'caption', 'hashtags'):
            if field in request.data:
                setattr(short, field, request.data[field])
        short.updated_by = request.user
        short.save()
        return Response({'status': 'updated'})

    def delete(self, request, pk):
        short, err = self._get_short(pk, request.user, min_role=Role.PRODUCER)
        if err:
            return err
        short.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RenderShortAPI(APIView):
    """
    POST /api/shorts/<pk>/render/

    Render a single VideoShort using ffmpeg and upload to DO Spaces.
    The episode must have at least one video MediaAsset stored (with an
    external_url pointing at a downloadable video).

    Returns:
        {status, public_url, shareable_link, duration_seconds, file_size}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from .models import VideoShort  # noqa: PLC0415
        from .services.shorts import render_short  # noqa: PLC0415

        short = get_object_or_404(VideoShort, pk=pk)
        if not has_minimum_role(request.user, short.episode.show, Role.PRODUCER):
            return Response({'error': 'Producer role required.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            public_url = render_short(short, user=request.user)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        short.refresh_from_db()
        return Response({
            'status': short.status,
            'public_url': short.public_url,
            'shareable_link': short.shareable_link,
            'duration_seconds': short.duration_seconds,
            'file_size': short.file_size,
        })


class RenderAllShortsAPI(APIView):
    """
    POST /api/episodes/<episode_id>/shorts/render-all/

    Render all QUEUED VideoShorts for an episode in sequence.

    Returns:
        {results: [{short_id, title, status, public_url, error}, ...]}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, episode_id):
        from .services.shorts import render_all_queued_shorts  # noqa: PLC0415

        episode = get_object_or_404(Episode, pk=episode_id)
        if not has_minimum_role(request.user, episode.show, Role.PRODUCER):
            return Response({'error': 'Producer role required.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            results = render_all_queued_shorts(episode, user=request.user)
        except RuntimeError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        return Response({'results': results, 'count': len(results)})


# =============================================================================
# DIRECT-TO-SPACES UPLOAD  (presigned PUT — bypasses nginx/gunicorn)
# =============================================================================

class MediaPresignUploadAPI(APIView):
    """
    POST /api/episodes/<episode_id>/media/presign/

    Generate a short-lived presigned PUT URL so the browser can upload a file
    directly to DigitalOcean Spaces without streaming through the Django server.

    Body (JSON):
        filename      — original filename (used to build the storage key)
        content_type  — MIME type of the file
        asset_type    — value from AssetType choices

    Returns:
        {url, key, public_url, expires_in}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, episode_id):
        import logging
        import os as _os
        import signal
        import uuid as _uuid
        from .services import storage  # noqa: PLC0415

        logger = logging.getLogger(__name__)

        episode = get_object_or_404(Episode, pk=episode_id)
        if not has_minimum_role(request.user, episode, Role.EDITOR):
            return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        filename = request.data.get('filename', 'upload')
        content_type = request.data.get('content_type', 'application/octet-stream')

        # Sanitise filename — strip path traversal, collapse whitespace
        safe_name = _os.path.basename(filename).replace(' ', '_')
        if not safe_name:
            safe_name = 'upload'
        unique_prefix = _uuid.uuid4().hex[:8]

        key = storage.media_asset_key(
            str(episode.organization_uuid),
            str(episode_id),
            unique_prefix,
            safe_name,
        )

        EXPIRES = 3600

        class _PresignTimeout(Exception):
            pass

        def _timeout_handler(signum, frame):  # noqa: ARG001
            raise _PresignTimeout('Presign generation timed out')

        try:
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(8)
            result = storage.generate_presigned_upload_url(key, content_type, expires=EXPIRES)
            signal.alarm(0)
        except _PresignTimeout:
            logger.exception('Presign timeout for episode=%s user=%s key=%s', episode_id, request.user.id, key)
            return Response(
                {'detail': 'Upload URL generation timed out. Please retry in a few seconds.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            signal.alarm(0)
            logger.exception('Presign generation failed for episode=%s user=%s key=%s', episode_id, request.user.id, key)
            return Response({'detail': f'Could not generate upload URL: {exc}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        result['expires_in'] = EXPIRES
        return Response(result)


class MediaAssetConfirmUploadAPI(APIView):
    """
    POST /api/episodes/<episode_id>/media/confirm/

    After the browser finishes uploading directly to DO Spaces, call this
    endpoint to create the MediaAsset record in the database.

    Body (JSON):
        key           — storage key returned by the presign endpoint
        public_url    — CDN URL returned by the presign endpoint
        asset_type    — value from AssetType choices
        filename      — original filename
        file_size     — byte size of the uploaded file
        content_type  — MIME type
        label         — (optional) display name

    Returns:
        {id, public_url}  with HTTP 201
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, episode_id):
        import os as _os
        from .constants import AssetType, IngestionStatus, SourceType  # noqa: PLC0415

        episode = get_object_or_404(Episode, pk=episode_id)
        if not has_minimum_role(request.user, episode, Role.EDITOR):
            return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        key = (request.data.get('key') or '').strip()
        public_url = (request.data.get('public_url') or '').strip()
        asset_type = (request.data.get('asset_type') or '').strip()
        filename = (request.data.get('filename') or _os.path.basename(key))
        file_size = request.data.get('file_size')
        content_type = (request.data.get('content_type') or '').strip()
        label = (request.data.get('label') or '').strip()

        if not key or not public_url or not asset_type:
            return Response(
                {'detail': 'key, public_url, and asset_type are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_asset_types = {c[0] for c in AssetType.CHOICES}
        if asset_type not in valid_asset_types:
            return Response(
                {'detail': f'Invalid asset_type. Valid values: {sorted(valid_asset_types)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            asset = MediaAsset(
                episode=episode,
                organization_uuid=episode.organization_uuid,
                asset_type=asset_type,
                source_type=SourceType.EXTERNAL_LINK,
                external_url=public_url,
                label=label or _os.path.splitext(filename)[0],
                filename=filename,
                content_type=content_type,
                file_size=int(file_size) if file_size else None,
                ingestion_status=IngestionStatus.READY,
                ingested_by=request.user,
                created_by=request.user,
            )
            asset.save()
        except (OperationalError, ProgrammingError):
            return Response(
                {
                    'detail': (
                        'Media upload reached storage, but database schema is out of sync. '
                        'Run Producer migrations and retry confirm.'
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({'id': str(asset.id), 'public_url': public_url},
                        status=status.HTTP_201_CREATED)

