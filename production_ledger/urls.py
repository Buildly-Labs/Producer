"""
URL configuration for Production Ledger.
"""
from django.contrib.auth import views as auth_views
from django.urls import path, include

from . import views
from . import api

app_name = 'production_ledger'

# Main UI URLs
urlpatterns = [
    # Authentication (namespaced so templates can use production_ledger:login)
    path('auth/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('auth/logout/', auth_views.LogoutView.as_view(), name='logout'),
    # register currently redirects to login (no self-registration yet)
    path('auth/register/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='register'),

    # Dashboard
    path('', views.DashboardView.as_view(), name='dashboard'),
    
    # Shows
    path('shows/', views.ShowListView.as_view(), name='show_list'),
    path('shows/create/', views.ShowCreateView.as_view(), name='show_create'),
    path('shows/<uuid:pk>/', views.ShowDetailView.as_view(), name='show_detail'),
    path('shows/<uuid:pk>/edit/', views.ShowUpdateView.as_view(), name='show_edit'),
    path('shows/<uuid:pk>/roles/', views.ShowRolesView.as_view(), name='show_roles'),
    
    # Episodes
    path('episodes/create/', views.EpisodeCreateSelectShowView.as_view(), name='episode_create'),
    path('shows/<uuid:show_id>/episodes/create/', views.EpisodeCreateView.as_view(), name='episode_create_for_show'),
    path('episodes/<uuid:pk>/', views.EpisodeDetailView.as_view(), name='episode_detail'),
    path('episodes/<uuid:pk>/edit/', views.EpisodeUpdateView.as_view(), name='episode_edit'),
    path('episodes/<uuid:pk>/status/', views.EpisodeStatusView.as_view(), name='episode_status'),
    
    # Episode tabs (sub-views)
    path('episodes/<uuid:pk>/overview/', views.EpisodeOverviewView.as_view(), name='episode_overview'),
    path('episodes/<uuid:pk>/segments/', views.EpisodeSegmentsView.as_view(), name='episode_segments'),
    path('episodes/<uuid:pk>/guests/', views.EpisodeGuestsView.as_view(), name='episode_guests'),
    path('episodes/<uuid:pk>/media/', views.EpisodeMediaView.as_view(), name='episode_media'),
    path('episodes/<uuid:pk>/transcript/', views.EpisodeTranscriptView.as_view(), name='episode_transcript'),
    path('episodes/<uuid:pk>/clips/', views.EpisodeClipsView.as_view(), name='episode_clips'),
    path('episodes/<uuid:pk>/ai-drafts/', views.EpisodeAIDraftsView.as_view(), name='episode_ai_drafts'),
    path('episodes/<uuid:pk>/show-notes/', views.EpisodeShowNotesView.as_view(), name='episode_show_notes'),
    path('episodes/<uuid:pk>/exports/', views.EpisodeExportsView.as_view(), name='episode_exports'),
    path('episodes/<uuid:pk>/checklist/', views.EpisodeChecklistView.as_view(), name='episode_checklist'),
    
    # Control Room
    path('episodes/<uuid:pk>/control-room/', views.ControlRoomView.as_view(), name='control_room'),
    
    # Segments
    path('segments/<uuid:pk>/edit/', views.SegmentUpdateView.as_view(), name='segment_edit'),
    path('segments/<uuid:pk>/delete/', views.SegmentDeleteView.as_view(), name='segment_delete'),
    
    # Guests
    path('guests/', views.GuestListView.as_view(), name='guest_list'),
    path('guests/create/', views.GuestCreateView.as_view(), name='guest_create'),
    path('guests/<uuid:pk>/', views.GuestDetailView.as_view(), name='guest_detail'),
    path('guests/<uuid:pk>/edit/', views.GuestUpdateView.as_view(), name='guest_edit'),
    
    # Episode Guests
    path('episode-guests/<uuid:pk>/edit/', views.EpisodeGuestUpdateView.as_view(), name='episode_guest_edit'),
    path('episode-guests/<uuid:pk>/delete/', views.EpisodeGuestDeleteView.as_view(), name='episode_guest_delete'),
    path('episode-guests/<uuid:pk>/approve-quotes/', views.ApproveQuotesView.as_view(), name='approve_quotes'),
    
    # Media Assets
    path('media/<uuid:pk>/delete/', views.MediaAssetDeleteView.as_view(), name='media_delete'),
    
    # Transcripts
    path('transcripts/<uuid:pk>/edit/', views.TranscriptEditView.as_view(), name='transcript_edit'),
    
    # Clips
    path('clips/<uuid:pk>/edit/', views.ClipMomentUpdateView.as_view(), name='clip_edit'),
    path('clips/<uuid:pk>/delete/', views.ClipMomentDeleteView.as_view(), name='clip_delete'),
    
    # AI Artifacts
    path('ai-artifacts/<uuid:pk>/approve/', views.AIArtifactApproveView.as_view(), name='ai_artifact_approve'),
    path('ai-artifacts/<uuid:pk>/use/', views.AIArtifactUseView.as_view(), name='ai_artifact_use'),
    
    # Show Notes
    path('show-notes/drafts/<uuid:pk>/edit/', views.ShowNoteDraftEditView.as_view(), name='show_note_draft_edit'),
    path('show-notes/finalize/<uuid:episode_id>/', views.FinalizeShowNotesView.as_view(), name='finalize_show_notes'),
    
    # Checklist
    path('checklist/<uuid:pk>/toggle/', views.ChecklistToggleView.as_view(), name='checklist_toggle'),
    
    # Exports
    path('exports/episode/<uuid:pk>/json/', views.ExportEpisodeJSONView.as_view(), name='export_episode_json'),
    path('exports/episode/<uuid:pk>/markdown/', views.ExportShowNotesMarkdownView.as_view(), name='export_show_notes_markdown'),
    path('exports/episode/<uuid:pk>/clips-csv/', views.ExportClipsCSVView.as_view(), name='export_clips_csv'),
    path('exports/episode/<uuid:pk>/guest-brief/<uuid:guest_id>/', views.ExportGuestBriefView.as_view(), name='export_guest_brief'),
    path('exports/episode/<uuid:pk>/package/', views.ExportFullPackageView.as_view(), name='export_full_package'),
    
    # API endpoints
    path('api/', include('production_ledger.api_urls')),
]
