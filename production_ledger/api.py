"""
API Views for Production Ledger.

All endpoints enforce organization scoping and RBAC.
"""
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .constants import ApprovalStatus, ArtifactType, Role
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
            return Response({'error': 'Admin role required'}, status=status.HTTP_403_FORBIDDEN)
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
            return Response({'error': 'Insufficient permissions'}, status=status.HTTP_403_FORBIDDEN)
        serializer.save(updated_by=self.request.user)


class EpisodeStatusAPI(APIView):
    """Change episode status."""
    
    permission_classes = [IsAuthenticated]
    
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
