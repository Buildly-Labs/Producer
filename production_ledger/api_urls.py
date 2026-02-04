"""
API URL configuration for Production Ledger.
"""
from django.urls import path

from . import api

urlpatterns = [
    # Shows
    path('shows/', api.ShowListCreateAPI.as_view(), name='api_show_list'),
    path('shows/<uuid:pk>/', api.ShowDetailAPI.as_view(), name='api_show_detail'),
    
    # Episodes
    path('episodes/', api.EpisodeListCreateAPI.as_view(), name='api_episode_list'),
    path('episodes/<uuid:pk>/', api.EpisodeDetailAPI.as_view(), name='api_episode_detail'),
    path('episodes/<uuid:pk>/status/', api.EpisodeStatusAPI.as_view(), name='api_episode_status'),
    
    # Segments
    path('episodes/<uuid:episode_id>/segments/', api.SegmentListCreateAPI.as_view(), name='api_segment_list'),
    path('segments/<uuid:pk>/', api.SegmentDetailAPI.as_view(), name='api_segment_detail'),
    
    # Guests
    path('guests/', api.GuestListCreateAPI.as_view(), name='api_guest_list'),
    path('guests/<uuid:pk>/', api.GuestDetailAPI.as_view(), name='api_guest_detail'),
    
    # Episode Guests
    path('episodes/<uuid:episode_id>/guests/', api.EpisodeGuestListCreateAPI.as_view(), name='api_episode_guest_list'),
    path('episode-guests/<uuid:pk>/', api.EpisodeGuestDetailAPI.as_view(), name='api_episode_guest_detail'),
    
    # Media Assets
    path('episodes/<uuid:episode_id>/media/', api.MediaAssetListCreateAPI.as_view(), name='api_media_list'),
    path('media/<uuid:pk>/', api.MediaAssetDetailAPI.as_view(), name='api_media_detail'),
    
    # Transcripts
    path('episodes/<uuid:episode_id>/transcripts/', api.TranscriptListCreateAPI.as_view(), name='api_transcript_list'),
    path('transcripts/<uuid:pk>/', api.TranscriptDetailAPI.as_view(), name='api_transcript_detail'),
    
    # Clips
    path('episodes/<uuid:episode_id>/clips/', api.ClipMomentListCreateAPI.as_view(), name='api_clip_list'),
    path('clips/<uuid:pk>/', api.ClipMomentDetailAPI.as_view(), name='api_clip_detail'),
    
    # AI Artifacts
    path('episodes/<uuid:episode_id>/ai-artifacts/', api.AIArtifactListAPI.as_view(), name='api_ai_artifact_list'),
    path('episodes/<uuid:episode_id>/ai-artifacts/generate/', api.AIArtifactGenerateAPI.as_view(), name='api_ai_artifact_generate'),
    path('ai-artifacts/<uuid:pk>/', api.AIArtifactDetailAPI.as_view(), name='api_ai_artifact_detail'),
    path('ai-artifacts/<uuid:pk>/approve/', api.AIArtifactApproveAPI.as_view(), name='api_ai_artifact_approve'),
    
    # Show Notes
    path('episodes/<uuid:episode_id>/show-notes/drafts/', api.ShowNoteDraftListCreateAPI.as_view(), name='api_show_note_draft_list'),
    path('show-notes/drafts/<uuid:pk>/', api.ShowNoteDraftDetailAPI.as_view(), name='api_show_note_draft_detail'),
    path('episodes/<uuid:episode_id>/show-notes/final/', api.ShowNoteFinalAPI.as_view(), name='api_show_note_final'),
    
    # Checklist
    path('episodes/<uuid:episode_id>/checklist/', api.ChecklistAPI.as_view(), name='api_checklist'),
    path('checklist/<uuid:pk>/toggle/', api.ChecklistToggleAPI.as_view(), name='api_checklist_toggle'),
    
    # Exports
    path('episodes/<uuid:pk>/export/json/', api.ExportJSONAPI.as_view(), name='api_export_json'),
    path('episodes/<uuid:pk>/export/markdown/', api.ExportMarkdownAPI.as_view(), name='api_export_markdown'),
    path('episodes/<uuid:pk>/export/clips/', api.ExportClipsAPI.as_view(), name='api_export_clips'),
]
