"""
Views for Production Ledger.

All views enforce organization scoping and RBAC.
"""
import json
import logging
import zipfile
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import OperationalError, ProgrammingError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from .constants import (
    ApprovalStatus,
    ArtifactType,
    ClipPriority,
    EpisodeStatus,
    QuoteApproval,
    Role,
    SourceType,
    TranscriptSourceType,
)
from .forms import (
    ApproveArtifactForm,
    ClipMomentForm,
    EpisodeForm,
    EpisodeGuestForm,
    EpisodeStatusForm,
    FinalizeShowNotesForm,
    GenerateAIArtifactForm,
    GuestForm,
    LiveNotesForm,
    MediaAssetLinkForm,
    MediaAssetUploadForm,
    QuickClipForm,
    SegmentForm,
    ShowForm,
    ShowJoinRequestForm,
    ShowNoteDraftForm,
    ShowRoleAssignmentForm,
    TranscriptEditForm,
    TranscriptPasteForm,
    TranscriptUploadForm,
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
    ShowJoinRequest,
    ShowNoteDraft,
    ShowNoteFinal,
    ShowRoleAssignment,
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
    get_user_role_for_episode,
    get_user_role_for_show,
    has_minimum_role,
    has_role,
)


logger = logging.getLogger(__name__)
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
    export_episode_package_json_string,
    export_guest_brief_html,
    export_show_notes_markdown,
    generate_full_export_package,
)


# =============================================================================
# PUBLIC VIEWS
# =============================================================================

class LandingPageView(TemplateView):
    """Public landing page."""
    template_name = 'production_ledger/landing.html'


# =============================================================================
# BASE MIXINS
# =============================================================================

class OrganizationMixin:
    """Mixin to handle organization scoping."""
    
    def get_organization_uuid(self):
        """Get the organization UUID for the current user."""
        org_uuid = get_user_organization_uuid(self.request.user)
        if not org_uuid:
            # For non-superusers without an org, deny access
            if not self.request.user.is_superuser:
                raise PermissionDenied("No organization found for user")
            # Superusers get a default org (handled in get_user_organization_uuid)
            import uuid
            return uuid.uuid5(uuid.NAMESPACE_DNS, f'org.default.{self.request.user.pk}')
        return org_uuid
    
    def get_queryset(self):
        """Filter queryset by organization."""
        qs = super().get_queryset()
        return qs.filter(organization_uuid=self.get_organization_uuid())


class RoleMixin:
    """Mixin to handle RBAC checks."""
    
    required_roles = None  # Override in subclass
    minimum_role = None  # Override in subclass
    
    def check_permissions(self, obj):
        """Check if user has required permissions."""
        if self.required_roles:
            if not has_role(self.request.user, obj, self.required_roles):
                raise PermissionDenied(
                    f"Required roles: {', '.join(self.required_roles)}"
                )
        elif self.minimum_role:
            if not has_minimum_role(self.request.user, obj, self.minimum_role):
                raise PermissionDenied(
                    f"Minimum required role: {self.minimum_role}"
                )
    
    def get_user_role(self, obj):
        """Get the user's role for the object."""
        if isinstance(obj, Episode):
            return get_user_role_for_episode(self.request.user, obj)
        elif isinstance(obj, Show):
            return get_user_role_for_show(self.request.user, obj)
        return None


class AuditMixin:
    """Mixin to handle audit fields."""
    
    def form_valid(self, form):
        """Set created_by/updated_by on save."""
        obj = form.save(commit=False)
        
        if not obj.pk:  # New object
            obj.created_by = self.request.user
            if hasattr(obj, 'organization_uuid') and not obj.organization_uuid:
                obj.organization_uuid = self.get_organization_uuid()
        
        obj.updated_by = self.request.user
        obj.save()
        
        return super().form_valid(form)


# =============================================================================
# DASHBOARD
# =============================================================================

class DashboardView(LoginRequiredMixin, OrganizationMixin, TemplateView):
    """Main dashboard showing shows and recent episodes."""
    
    template_name = 'production_ledger/dashboard.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_superuser:
            has_non_guest_role = ShowRoleAssignment.objects.filter(
                user=request.user
            ).exclude(role='guest').exists()
            if not has_non_guest_role:
                return redirect('production_ledger:guest_portal')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org_uuid = self.get_organization_uuid()
        
        # Counts for stats
        context['show_count'] = Show.objects.filter(
            organization_uuid=org_uuid
        ).count()
        
        context['episode_count'] = Episode.objects.filter(
            organization_uuid=org_uuid
        ).count()
        
        context['guest_count'] = Guest.objects.filter(
            organization_uuid=org_uuid
        ).count()
        
        context['published_count'] = Episode.objects.filter(
            organization_uuid=org_uuid,
            status=EpisodeStatus.PUBLISHED
        ).count()
        
        # Recent episodes
        context['recent_episodes'] = Episode.objects.filter(
            organization_uuid=org_uuid
        ).select_related('show').order_by('-updated_at')[:5]
        
        # Upcoming episodes (scheduled recording date in the future)
        context['upcoming_episodes'] = Episode.objects.filter(
            organization_uuid=org_uuid,
            scheduled_for__gte=timezone.now()
        ).exclude(
            status=EpisodeStatus.PUBLISHED
        ).select_related('show').order_by('scheduled_for')[:5]
        
        # Legacy context for old template
        context['shows'] = Show.objects.filter(
            organization_uuid=org_uuid
        ).prefetch_related('episodes')[:10]
        
        context['episodes_by_status'] = {
            status: Episode.objects.filter(
                organization_uuid=org_uuid,
                status=status
            ).count()
            for status, _ in EpisodeStatus.CHOICES
        }
        
        return context


class EpisodeCreateSelectShowView(LoginRequiredMixin, OrganizationMixin, TemplateView):
    """Select a show to create an episode for."""
    
    template_name = 'production_ledger/episode_select_show.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org_uuid = self.get_organization_uuid()
        
        context['shows'] = Show.objects.filter(
            organization_uuid=org_uuid
        ).order_by('name')
        
        return context


# =============================================================================
# SHOWS
# =============================================================================

class ShowListView(LoginRequiredMixin, OrganizationMixin, ListView):
    """List all shows."""
    
    model = Show
    template_name = 'production_ledger/show_list.html'
    context_object_name = 'shows'


class ShowCreateView(LoginRequiredMixin, OrganizationMixin, AuditMixin, CreateView):
    """Create a new show."""
    
    model = Show
    form_class = ShowForm
    template_name = 'production_ledger/show_form.html'
    
    def get_success_url(self):
        return reverse('production_ledger:show_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        form.instance.organization_uuid = self.get_organization_uuid()
        response = super().form_valid(form)
        
        # Auto-assign creator as admin
        ShowRoleAssignment.objects.create(
            show=self.object,
            user=self.request.user,
            role=Role.ADMIN,
            created_by=self.request.user,
        )
        
        messages.success(self.request, f'Show "{self.object.name}" created successfully!')
        return response


class ShowDetailView(LoginRequiredMixin, OrganizationMixin, RoleMixin, DetailView):
    """Show detail with episodes list."""
    
    model = Show
    template_name = 'production_ledger/show_detail.html'
    context_object_name = 'show'
    minimum_role = Role.GUEST
    
    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj)
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['episodes'] = self.object.episodes.all().order_by('-created_at')
        user_role = self.get_user_role(self.object)
        context['user_role'] = user_role
        context['can_request_join'] = user_role is None
        context['join_request_form'] = ShowJoinRequestForm()
        context['pending_join_request'] = ShowJoinRequest.objects.filter(
            show=self.object,
            user=self.request.user,
            status='pending',
        ).first()
        return context


class ShowUpdateView(LoginRequiredMixin, OrganizationMixin, RoleMixin, AuditMixin, UpdateView):
    """Update a show."""
    
    model = Show
    form_class = ShowForm
    template_name = 'production_ledger/show_form.html'
    required_roles = [Role.ADMIN]
    
    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj)
        return obj
    
    def get_success_url(self):
        return reverse('production_ledger:show_detail', kwargs={'pk': self.object.pk})


class ShowRolesView(LoginRequiredMixin, OrganizationMixin, RoleMixin, TemplateView):
    """Manage role assignments for a show."""
    
    template_name = 'production_ledger/show_roles.html'
    required_roles = [Role.ADMIN]
    
    def get_show(self):
        show = get_object_or_404(Show, pk=self.kwargs['pk'])
        self.check_permissions(show)
        return show
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['show'] = self.get_show()
        context['role_assignments'] = ShowRoleAssignment.objects.filter(
            show=context['show']
        ).select_related('user')
        form = ShowRoleAssignmentForm()
        form.fields['user'].queryset = form.fields['user'].queryset.filter(is_active=True).order_by('username')
        context['form'] = form
        context['roles'] = Role.CHOICES
        context['pending_join_requests'] = ShowJoinRequest.objects.filter(
            show=context['show'],
            status='pending',
        ).select_related('user')
        return context
    
    def post(self, request, *args, **kwargs):
        show = self.get_show()

        action = request.POST.get('action', 'assign_role')
        if action == 'review_join_request':
            join_request_id = request.POST.get('join_request_id')
            decision = request.POST.get('decision')

            join_request = get_object_or_404(ShowJoinRequest, pk=join_request_id, show=show)
            if join_request.status != 'pending':
                messages.info(request, 'This request has already been reviewed.')
                return redirect('production_ledger:show_roles', pk=show.pk)

            join_request.reviewed_by = request.user
            join_request.reviewed_at = timezone.now()

            if decision == 'approve':
                assignment, created = ShowRoleAssignment.objects.get_or_create(
                    show=show,
                    user=join_request.user,
                    defaults={
                        'role': join_request.desired_role,
                        'created_by': request.user,
                    }
                )
                if not created and assignment.role != join_request.desired_role:
                    assignment.role = join_request.desired_role
                    assignment.save(update_fields=['role'])

                join_request.status = 'approved'
                join_request.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
                messages.success(request, f'Approved request and assigned {join_request.user.username} as {join_request.desired_role}.')
            else:
                join_request.status = 'declined'
                join_request.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
                messages.info(request, f'Declined join request from {join_request.user.username}.')
        else:
            form = ShowRoleAssignmentForm(request.POST)
            form.fields['user'].queryset = form.fields['user'].queryset.filter(is_active=True)

            if form.is_valid():
                user = form.cleaned_data['user']
                role = form.cleaned_data['role']
                assignment, created = ShowRoleAssignment.objects.get_or_create(
                    show=show,
                    user=user,
                    defaults={
                        'role': role,
                        'created_by': request.user,
                    }
                )

                if created:
                    messages.success(request, 'Role assigned successfully!')
                else:
                    if assignment.role != role:
                        assignment.role = role
                        assignment.save(update_fields=['role'])
                        messages.success(request, 'Existing role assignment updated successfully!')
                    else:
                        messages.info(request, 'User already has that role for this show.')
            else:
                messages.error(request, 'Error assigning role.')
        
        return redirect('production_ledger:show_roles', pk=show.pk)


# =============================================================================
# EPISODES
# =============================================================================

class EpisodeCreateView(LoginRequiredMixin, OrganizationMixin, RoleMixin, AuditMixin, CreateView):
    """Create a new episode."""
    
    model = Episode
    form_class = EpisodeForm
    template_name = 'production_ledger/episode_form.html'
    required_roles = [Role.ADMIN, Role.HOST, Role.PRODUCER]
    
    def get_show(self):
        show = get_object_or_404(Show, pk=self.kwargs['show_id'])
        self.check_permissions(show)
        return show
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organization_uuid'] = self.get_organization_uuid()
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['show'] = self.get_show()
        return context
    
    def form_valid(self, form):
        show = self.get_show()
        form.instance.show = show
        form.instance.organization_uuid = show.organization_uuid
        response = super().form_valid(form)
        messages.success(self.request, f'Episode "{self.object.title}" created!')
        return response
    
    def get_success_url(self):
        return reverse('production_ledger:episode_detail', kwargs={'pk': self.object.pk})


class EpisodeDetailView(LoginRequiredMixin, OrganizationMixin, RoleMixin, DetailView):
    """Episode detail - redirects to overview tab."""
    
    model = Episode
    template_name = 'production_ledger/episode_detail.html'
    context_object_name = 'episode'
    minimum_role = Role.GUEST
    
    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj)
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user_role'] = self.get_user_role(self.object)
        context['active_tab'] = self.kwargs.get('tab', 'overview')
        return context


class EpisodeUpdateView(LoginRequiredMixin, OrganizationMixin, RoleMixin, AuditMixin, UpdateView):
    """Update an episode."""
    
    model = Episode
    form_class = EpisodeForm
    template_name = 'production_ledger/episode_form.html'
    required_roles = [Role.ADMIN, Role.HOST, Role.PRODUCER]
    
    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj)
        return obj
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organization_uuid'] = self.get_organization_uuid()
        return kwargs
    
    def get_success_url(self):
        return reverse('production_ledger:episode_detail', kwargs={'pk': self.object.pk})


class EpisodeStatusView(LoginRequiredMixin, OrganizationMixin, RoleMixin, FormView):
    """Change episode status."""
    
    template_name = 'production_ledger/episode_status.html'
    form_class = EpisodeStatusForm
    
    def get_episode(self):
        episode = get_object_or_404(Episode, pk=self.kwargs['pk'])
        return episode
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['episode'] = self.get_episode()
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        episode = self.get_episode()
        context['episode'] = episode

        allowed = EpisodeStatus.TRANSITIONS.get(episode.status, [])
        status_labels = dict(EpisodeStatus.CHOICES)
        context['available_transitions'] = [
            (status_code, status_labels.get(status_code, status_code.title()))
            for status_code in allowed
        ]

        blocked = []
        if episode.status == EpisodeStatus.EDITED and not episode.is_checklist_complete():
            blocked.append('Checklist must be completed before moving to Approved.')
        if episode.status == EpisodeStatus.APPROVED and not episode.is_checklist_complete():
            blocked.append('Checklist must be completed before moving to Published.')
        context['blocked_transitions'] = blocked
        return context
    
    def form_valid(self, form):
        episode = self.get_episode()
        new_status = form.cleaned_data['new_status']
        
        # Check permission for this transition
        if not can_transition_status(self.request.user, episode, new_status):
            messages.error(self.request, 'You do not have permission to make this transition.')
            return redirect('production_ledger:episode_detail', pk=episode.pk)
        
        try:
            episode.transition_to(new_status, user=self.request.user)
            messages.success(self.request, f'Episode status changed to {episode.get_status_display()}')
        except Exception as e:
            messages.error(self.request, str(e))
        
        return redirect('production_ledger:episode_detail', pk=episode.pk)


# =============================================================================
# EPISODE TABS
# =============================================================================

class EpisodeTabMixin(LoginRequiredMixin, OrganizationMixin, RoleMixin):
    """Base mixin for episode tab views."""
    
    minimum_role = Role.GUEST
    
    def get_episode(self):
        if not hasattr(self, '_episode'):
            self._episode = get_object_or_404(Episode, pk=self.kwargs['pk'])
            self.check_permissions(self._episode)
        return self._episode
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['episode'] = self.get_episode()
        context['user_role'] = self.get_user_role(self.get_episode())
        context['active_tab'] = self.active_tab
        return context


class EpisodeOverviewView(EpisodeTabMixin, TemplateView):
    """Episode overview tab."""
    
    template_name = 'production_ledger/tabs/overview.html'
    active_tab = 'overview'


class EpisodePublishView(EpisodeTabMixin, TemplateView):
    """Episode publish and distribution tab."""

    template_name = 'production_ledger/tabs/publish.html'
    active_tab = 'publish'

    def get_context_data(self, **kwargs):
        from .models import PodcastDistribution  # noqa: PLC0415

        context = super().get_context_data(**kwargs)
        episode = self.get_episode()
        context['distributions'] = PodcastDistribution.objects.filter(episode=episode).order_by('platform')
        context['can_publish'] = has_minimum_role(self.request.user, episode.show, Role.PRODUCER)
        context['can_mark_published'] = episode.status == EpisodeStatus.APPROVED and episode.is_checklist_complete()
        return context

    def post(self, request, *args, **kwargs):
        from .services.distribution import build_and_publish_feed, publish_episode_audio  # noqa: PLC0415

        episode = self.get_episode()
        if not has_minimum_role(request.user, episode.show, Role.PRODUCER):
            messages.error(request, 'Producer role required to publish audio.')
            return redirect('production_ledger:episode_publish', pk=episode.pk)

        audio_file = request.FILES.get('audio')
        if not audio_file:
            messages.error(request, 'Audio file is required.')
            return redirect('production_ledger:episode_publish', pk=episode.pk)

        duration_seconds = int(request.POST.get('duration_seconds', 0) or 0)
        rebuild_feed = request.POST.get('rebuild_feed', 'true').lower() != 'false'

        try:
            result = publish_episode_audio(
                episode,
                audio_file,
                audio_file.name,
                duration_seconds=duration_seconds,
                user=request.user,
            )
        except Exception as exc:
            messages.error(request, f'Audio publish failed: {exc}')
            return redirect('production_ledger:episode_publish', pk=episode.pk)

        if rebuild_feed:
            try:
                build_and_publish_feed(episode.show, user=request.user)
            except Exception as exc:
                messages.warning(request, f'Audio uploaded, but feed rebuild failed: {exc}')

        if episode.status == EpisodeStatus.APPROVED and episode.is_checklist_complete():
            try:
                episode.transition_to(EpisodeStatus.PUBLISHED, user=request.user)
            except Exception:
                # Keep publishing successful even if status transition is blocked.
                pass

        messages.success(
            request,
            f"Audio published to {len(result['distributions'])} platform records.",
        )
        return redirect('production_ledger:episode_publish', pk=episode.pk)


class EpisodeSegmentsView(EpisodeTabMixin, TemplateView):
    """Episode segments (run of show) tab."""
    
    template_name = 'production_ledger/tabs/segments.html'
    active_tab = 'segments'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['segments'] = self.get_episode().segments.all().order_by('order')
        context['segment_form'] = SegmentForm()
        return context
    
    def post(self, request, *args, **kwargs):
        episode = self.get_episode()
        
        if not has_role(request.user, episode, [Role.ADMIN, Role.HOST, Role.PRODUCER]):
            messages.error(request, 'You do not have permission to add segments.')
            return redirect('production_ledger:episode_segments', pk=episode.pk)
        
        form = SegmentForm(request.POST)
        if form.is_valid():
            segment = form.save(commit=False)
            segment.episode = episode
            segment.organization_uuid = episode.organization_uuid
            segment.created_by = request.user
            segment.save()
            messages.success(request, 'Segment added!')
        else:
            messages.error(request, 'Error adding segment.')
        
        return redirect('production_ledger:episode_segments', pk=episode.pk)


class EpisodeGuestsView(EpisodeTabMixin, TemplateView):
    """Episode guests tab."""
    
    template_name = 'production_ledger/tabs/guests.html'
    active_tab = 'guests'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        episode = self.get_episode()
        context['episode_guests'] = episode.episode_guests.select_related('guest').all()
        context['available_guests'] = Guest.objects.filter(
            organization_uuid=episode.organization_uuid
        ).exclude(
            id__in=episode.episode_guests.values_list('guest_id', flat=True)
        )
        context['guest_form'] = EpisodeGuestForm()
        return context
    
    def post(self, request, *args, **kwargs):
        episode = self.get_episode()
        
        if not can_manage_guests(request.user, episode):
            messages.error(request, 'You do not have permission to manage guests.')
            return redirect('production_ledger:episode_guests', pk=episode.pk)
        
        form = EpisodeGuestForm(request.POST)
        if form.is_valid():
            eg = form.save(commit=False)
            eg.episode = episode
            eg.organization_uuid = episode.organization_uuid
            eg.created_by = request.user
            eg.save()
            messages.success(request, f'Guest {eg.guest.name} added to episode!')
        else:
            messages.error(request, 'Error adding guest.')
        
        return redirect('production_ledger:episode_guests', pk=episode.pk)


class EpisodeMediaView(EpisodeTabMixin, TemplateView):
    """Episode media assets tab."""
    
    template_name = 'production_ledger/tabs/media.html'
    active_tab = 'media'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context['media_assets'] = self.get_episode().media_assets.all().order_by('asset_type', '-created_at')
        except (OperationalError, ProgrammingError) as exc:
            logger.exception(
                'Episode media tab query failed for episode=%s; rendering empty state',
                getattr(self.get_episode(), 'pk', None),
            )
            context['media_assets'] = []
            messages.error(
                self.request,
                'Media assets are temporarily unavailable due to a database schema mismatch. '
                'The page loaded in safe mode.',
            )
        context['upload_form'] = MediaAssetUploadForm()
        context['link_form'] = MediaAssetLinkForm()
        return context
    
    def post(self, request, *args, **kwargs):
        episode = self.get_episode()
        
        if not has_role(request.user, episode, [Role.ADMIN, Role.HOST, Role.PRODUCER, Role.EDITOR]):
            messages.error(request, 'You do not have permission to add media.')
            return redirect('production_ledger:episode_media', pk=episode.pk)
        
        # Determine which form was submitted based on form_type or file presence
        form_type = request.POST.get('form_type', '')
        
        if form_type == 'upload' or 'file' in request.FILES:
            form = MediaAssetUploadForm(request.POST, request.FILES)
        else:
            form = MediaAssetLinkForm(request.POST)
        
        if form.is_valid():
            try:
                asset = form.save(commit=False)
                asset.episode = episode
                asset.organization_uuid = episode.organization_uuid
                asset.ingested_by = request.user
                asset.created_by = request.user
                asset.save()
                messages.success(request, 'Media asset added!')
            except (OperationalError, ProgrammingError):
                logger.exception('Media asset save failed for episode=%s', episode.pk)
                messages.error(
                    request,
                    'Could not save this media asset because the database schema is out of sync. '
                    'Please re-run Producer migrations.',
                )
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
        
        return redirect('production_ledger:episode_media', pk=episode.pk)


class EpisodeTranscriptView(EpisodeTabMixin, TemplateView):
    """Episode transcript tab."""
    
    template_name = 'production_ledger/tabs/transcript.html'
    active_tab = 'transcript'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['transcripts'] = self.get_episode().transcripts.all().order_by('-revision')
        context['upload_form'] = TranscriptUploadForm()
        context['paste_form'] = TranscriptPasteForm()
        return context
    
    def post(self, request, *args, **kwargs):
        episode = self.get_episode()
        
        if not can_manage_transcripts(request.user, episode):
            messages.error(request, 'You do not have permission to manage transcripts.')
            return redirect('production_ledger:episode_transcript', pk=episode.pk)
        
        # Determine which form was submitted
        if 'file' in request.FILES:
            form = TranscriptUploadForm(request.POST, request.FILES)
            source_type = TranscriptSourceType.UPLOAD
            if form.is_valid():
                raw_text = request.FILES['file'].read().decode('utf-8')
        else:
            form = TranscriptPasteForm(request.POST)
            source_type = TranscriptSourceType.PASTE
            if form.is_valid():
                raw_text = form.cleaned_data['raw_text']
        
        if form.is_valid():
            # Get current max revision
            max_rev = episode.transcripts.aggregate(
                max_rev=models.Max('revision')
            )['max_rev'] or 0
            
            Transcript.objects.create(
                episode=episode,
                organization_uuid=episode.organization_uuid,
                source_type=source_type,
                format=form.cleaned_data['format'],
                raw_text=raw_text,
                revision=max_rev + 1,
                ingested_by=request.user,
                created_by=request.user,
            )
            messages.success(request, 'Transcript added!')
        else:
            messages.error(request, 'Error adding transcript.')
        
        return redirect('production_ledger:episode_transcript', pk=episode.pk)


class EpisodeClipsView(EpisodeTabMixin, TemplateView):
    """Episode clips tab."""
    
    template_name = 'production_ledger/tabs/clips.html'
    active_tab = 'clips'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['clips'] = self.get_episode().clip_moments.all().order_by('start_ms')
        context['clip_form'] = ClipMomentForm()
        context['priorities'] = ClipPriority.CHOICES
        return context
    
    def post(self, request, *args, **kwargs):
        episode = self.get_episode()
        
        if not can_manage_clips(request.user, episode):
            messages.error(request, 'You do not have permission to manage clips.')
            return redirect('production_ledger:episode_clips', pk=episode.pk)
        
        form = ClipMomentForm(request.POST)
        if form.is_valid():
            clip = form.save(commit=False)
            clip.episode = episode
            clip.organization_uuid = episode.organization_uuid
            clip.created_by = request.user
            clip.save()
            messages.success(request, 'Clip added!')
        else:
            messages.error(request, 'Error adding clip.')
        
        return redirect('production_ledger:episode_clips', pk=episode.pk)


class EpisodeAIDraftsView(EpisodeTabMixin, TemplateView):
    """Episode AI drafts tab."""
    
    template_name = 'production_ledger/tabs/ai_drafts.html'
    active_tab = 'ai_drafts'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['ai_artifacts'] = self.get_episode().ai_artifacts.all().order_by('-created_at')
        context['generate_form'] = GenerateAIArtifactForm()
        context['artifact_types'] = ArtifactType.CHOICES
        return context
    
    def post(self, request, *args, **kwargs):
        episode = self.get_episode()
        
        if not can_create_ai_artifact(request.user, episode):
            messages.error(request, 'You do not have permission to generate AI content.')
            return redirect('production_ledger:episode_ai_drafts', pk=episode.pk)
        
        form = GenerateAIArtifactForm(request.POST)
        if form.is_valid():
            artifact_type = form.cleaned_data['artifact_type']
            topic_prompt = form.cleaned_data.get('topic_prompt', '')
            use_transcript = form.cleaned_data.get('use_transcript', True)
            use_clips = form.cleaned_data.get('use_clips', True)
            
            # Get transcript and clips if requested
            transcript = None
            clips = None
            
            if use_transcript:
                transcript = episode.transcripts.order_by('-revision').first()
            if use_clips:
                clips = list(episode.clip_moments.all())
            
            # Call appropriate generation function
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
                    raise ValueError(f"Unknown artifact type: {artifact_type}")
                
                messages.success(request, f'AI {artifact.get_artifact_type_display()} generated! Review and approve before using.')
            except Exception as e:
                messages.error(request, f'Error generating AI content: {str(e)}')
        else:
            messages.error(request, 'Invalid form submission.')
        
        return redirect('production_ledger:episode_ai_drafts', pk=episode.pk)


class EpisodeShowNotesView(EpisodeTabMixin, TemplateView):
    """Episode show notes tab."""
    
    template_name = 'production_ledger/tabs/show_notes.html'
    active_tab = 'show_notes'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        episode = self.get_episode()
        context['drafts'] = episode.show_note_drafts.all().order_by('-created_at')
        context['draft_form'] = ShowNoteDraftForm()
        
        try:
            context['final'] = episode.show_note_final
        except ShowNoteFinal.DoesNotExist:
            context['final'] = None
        
        context['can_finalize'] = can_approve_show_notes(self.request.user, episode)
        return context
    
    def post(self, request, *args, **kwargs):
        episode = self.get_episode()
        
        if not has_role(request.user, episode, [Role.ADMIN, Role.HOST, Role.PRODUCER, Role.EDITOR]):
            messages.error(request, 'You do not have permission to edit show notes.')
            return redirect('production_ledger:episode_show_notes', pk=episode.pk)
        
        form = ShowNoteDraftForm(request.POST)
        if form.is_valid():
            draft = form.save(commit=False)
            draft.episode = episode
            draft.organization_uuid = episode.organization_uuid
            draft.created_by = request.user
            draft.save()
            messages.success(request, 'Show notes draft saved!')
        else:
            messages.error(request, 'Error saving draft.')
        
        return redirect('production_ledger:episode_show_notes', pk=episode.pk)


class EpisodeExportsView(EpisodeTabMixin, TemplateView):
    """Episode exports tab."""
    
    template_name = 'production_ledger/tabs/exports.html'
    active_tab = 'exports'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        episode = self.get_episode()
        context['can_export'] = can_export(self.request.user, episode)
        context['guests'] = episode.episode_guests.select_related('guest').all()
        return context


class EpisodeChecklistView(EpisodeTabMixin, TemplateView):
    """Episode checklist tab."""
    
    template_name = 'production_ledger/tabs/checklist.html'
    active_tab = 'checklist'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['checklist_items'] = self.get_episode().checklist_items.all().order_by('sort_order')
        context['is_complete'] = self.get_episode().is_checklist_complete()
        return context


# =============================================================================
# CONTROL ROOM
# =============================================================================

class ControlRoomView(EpisodeTabMixin, TemplateView):
    """Control room for live production."""

    active_tab = 'control_room'
    required_roles = [Role.ADMIN, Role.HOST, Role.PRODUCER]

    def get_template_names(self):
        """Return different template based on mode."""
        mode = self.request.GET.get('mode', 'dashboard')
        view_type = self.request.GET.get('view', 'host')

        if view_type == 'guest':
            return ['production_ledger/control_room_guest.html']
        elif mode == 'live':
            return ['production_ledger/control_room_live.html']
        else:
            return ['production_ledger/control_room.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        episode = self.get_episode()
        segments = episode.segments.all().order_by('order')

        context['segments'] = segments
        context['live_notes_form'] = LiveNotesForm(instance=episode)
        context['quick_clip_form'] = QuickClipForm()
        context['guests'] = episode.episode_guests.select_related('guest').all()

        # Calculate progress
        total_segments = segments.count()
        completed_segments = segments.filter(is_completed=True).count()
        context['total_segments'] = total_segments
        context['completed_segments'] = completed_segments
        context['progress_percentage'] = int((completed_segments / total_segments * 100) if total_segments > 0 else 0)

        return context

    def post(self, request, *args, **kwargs):
        episode = self.get_episode()

        # Handle different POST actions
        action = request.POST.get('action')

        if action == 'save_notes':
            form = LiveNotesForm(request.POST, instance=episode)
            if form.is_valid():
                form.save()
                messages.success(request, 'Notes saved!')

        elif action == 'quick_clip':
            form = QuickClipForm(request.POST)
            if form.is_valid():
                ClipMoment.objects.create(
                    episode=episode,
                    organization_uuid=episode.organization_uuid,
                    title=form.cleaned_data['title'],
                    hook=form.cleaned_data.get('hook', ''),
                    priority=form.cleaned_data['priority'],
                    start_ms=form.cleaned_data['start_ms'],
                    end_ms=form.cleaned_data['start_ms'] + 30000,  # Default 30s clip
                    created_by=request.user,
                )
                messages.success(request, 'Moment flagged!')

        elif action == 'toggle_segment':
            segment_id = request.POST.get('segment_id')
            try:
                segment = Segment.objects.get(pk=segment_id, episode=episode)
                segment.is_completed = not segment.is_completed
                segment.completed_at = timezone.now() if segment.is_completed else None
                segment.save()
                return JsonResponse({
                    'success': True,
                    'is_completed': segment.is_completed,
                    'completed_at': segment.completed_at.isoformat() if segment.completed_at else None
                })
            except Segment.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Segment not found'}, status=404)

        elif action == 'save_segment_notes':
            segment_id = request.POST.get('segment_id')
            notes = request.POST.get('notes', '')
            try:
                segment = Segment.objects.get(pk=segment_id, episode=episode)
                segment.live_notes = notes
                segment.save()
                return JsonResponse({'success': True})
            except Segment.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Segment not found'}, status=404)

        return redirect('production_ledger:control_room', pk=episode.pk)


# =============================================================================
# SEGMENTS
# =============================================================================

class SegmentUpdateView(LoginRequiredMixin, OrganizationMixin, RoleMixin, AuditMixin, UpdateView):
    """Update a segment."""
    
    model = Segment
    form_class = SegmentForm
    template_name = 'production_ledger/segment_form.html'
    required_roles = [Role.ADMIN, Role.HOST, Role.PRODUCER]
    
    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj.episode)
        return obj
    
    def get_success_url(self):
        return reverse('production_ledger:episode_segments', kwargs={'pk': self.object.episode.pk})


class SegmentDeleteView(LoginRequiredMixin, OrganizationMixin, RoleMixin, DeleteView):
    """Delete a segment."""
    
    model = Segment
    required_roles = [Role.ADMIN, Role.HOST, Role.PRODUCER]
    
    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj.episode)
        return obj
    
    def get_success_url(self):
        return reverse('production_ledger:episode_segments', kwargs={'pk': self.object.episode.pk})


# =============================================================================
# GUESTS
# =============================================================================

class GuestListView(LoginRequiredMixin, OrganizationMixin, ListView):
    """List all guests."""
    
    model = Guest
    template_name = 'production_ledger/guest_list.html'
    context_object_name = 'guests'


class GuestCreateView(LoginRequiredMixin, OrganizationMixin, AuditMixin, CreateView):
    """Create a new guest."""
    
    model = Guest
    form_class = GuestForm
    template_name = 'production_ledger/guest_form.html'
    
    def form_valid(self, form):
        form.instance.organization_uuid = self.get_organization_uuid()
        response = super().form_valid(form)
        messages.success(self.request, f'Guest "{self.object.name}" created!')
        return response
    
    def get_success_url(self):
        return reverse('production_ledger:guest_detail', kwargs={'pk': self.object.pk})


class GuestDetailView(LoginRequiredMixin, OrganizationMixin, DetailView):
    """Guest detail view."""
    
    model = Guest
    template_name = 'production_ledger/guest_detail.html'
    context_object_name = 'guest'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['appearances'] = self.object.episode_appearances.select_related('episode', 'episode__show').all()
        return context


class GuestUpdateView(LoginRequiredMixin, OrganizationMixin, AuditMixin, UpdateView):
    """Update a guest."""
    
    model = Guest
    form_class = GuestForm
    template_name = 'production_ledger/guest_form.html'
    
    def get_success_url(self):
        return reverse('production_ledger:guest_detail', kwargs={'pk': self.object.pk})


class EpisodeGuestUpdateView(LoginRequiredMixin, OrganizationMixin, RoleMixin, AuditMixin, UpdateView):
    """Update episode guest details."""
    
    model = EpisodeGuest
    form_class = EpisodeGuestForm
    template_name = 'production_ledger/episode_guest_form.html'
    required_roles = [Role.ADMIN, Role.HOST, Role.PRODUCER]
    
    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj.episode)
        return obj
    
    def get_success_url(self):
        return reverse('production_ledger:episode_guests', kwargs={'pk': self.object.episode.pk})


class EpisodeGuestDeleteView(LoginRequiredMixin, OrganizationMixin, RoleMixin, DeleteView):
    """Remove guest from episode."""
    
    model = EpisodeGuest
    required_roles = [Role.ADMIN, Role.HOST, Role.PRODUCER]
    
    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj.episode)
        return obj
    
    def get_success_url(self):
        return reverse('production_ledger:episode_guests', kwargs={'pk': self.object.episode.pk})


class ApproveQuotesView(LoginRequiredMixin, OrganizationMixin, RoleMixin, View):
    """Approve or reject guest quotes."""
    
    def post(self, request, pk):
        eg = get_object_or_404(EpisodeGuest, pk=pk)
        
        # Guests can approve their own quotes
        # Others need manage_guests permission
        is_own_quotes = False  # Would need user-guest linking
        if not is_own_quotes and not can_manage_guests(request.user, eg.episode):
            raise PermissionDenied("You cannot approve these quotes.")
        
        action = request.POST.get('action')
        if action == 'approve':
            eg.quote_approval_status = QuoteApproval.APPROVED
        elif action == 'reject':
            eg.quote_approval_status = QuoteApproval.REJECTED
        
        eg.updated_by = request.user
        eg.save()
        
        messages.success(request, f'Quote approval status updated to {eg.get_quote_approval_status_display()}')
        return redirect('production_ledger:episode_guests', pk=eg.episode.pk)


# =============================================================================
# MEDIA ASSETS
# =============================================================================

class MediaAssetDeleteView(LoginRequiredMixin, OrganizationMixin, RoleMixin, DeleteView):
    """Delete a media asset."""
    
    model = MediaAsset
    required_roles = [Role.ADMIN, Role.HOST, Role.PRODUCER]
    
    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj.episode)
        return obj
    
    def get_success_url(self):
        return reverse('production_ledger:episode_media', kwargs={'pk': self.object.episode.pk})


# =============================================================================
# TRANSCRIPTS
# =============================================================================

class TranscriptEditView(LoginRequiredMixin, OrganizationMixin, RoleMixin, AuditMixin, UpdateView):
    """Edit a transcript."""
    
    model = Transcript
    form_class = TranscriptEditForm
    template_name = 'production_ledger/transcript_form.html'
    required_roles = [Role.ADMIN, Role.HOST, Role.PRODUCER, Role.EDITOR]
    
    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj.episode)
        return obj
    
    def get_success_url(self):
        return reverse('production_ledger:episode_transcript', kwargs={'pk': self.object.episode.pk})


# =============================================================================
# CLIPS
# =============================================================================

class ClipMomentUpdateView(LoginRequiredMixin, OrganizationMixin, RoleMixin, AuditMixin, UpdateView):
    """Edit a clip moment."""
    
    model = ClipMoment
    form_class = ClipMomentForm
    template_name = 'production_ledger/clip_form.html'
    required_roles = [Role.ADMIN, Role.HOST, Role.PRODUCER, Role.EDITOR]
    
    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj.episode)
        return obj
    
    def get_success_url(self):
        return reverse('production_ledger:episode_clips', kwargs={'pk': self.object.episode.pk})


class ClipMomentDeleteView(LoginRequiredMixin, OrganizationMixin, RoleMixin, DeleteView):
    """Delete a clip moment."""
    
    model = ClipMoment
    required_roles = [Role.ADMIN, Role.HOST, Role.PRODUCER, Role.EDITOR]
    
    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj.episode)
        return obj
    
    def get_success_url(self):
        return reverse('production_ledger:episode_clips', kwargs={'pk': self.object.episode.pk})


# =============================================================================
# AI ARTIFACTS
# =============================================================================

class AIArtifactApproveView(LoginRequiredMixin, OrganizationMixin, RoleMixin, View):
    """Approve or reject an AI artifact."""
    
    def post(self, request, pk):
        artifact = get_object_or_404(AIArtifact, pk=pk)
        
        if not can_approve_ai_artifact(request.user, artifact.episode):
            raise PermissionDenied("You cannot approve AI artifacts.")
        
        form = ApproveArtifactForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            notes = form.cleaned_data.get('notes', '')
            
            if action == 'approve':
                artifact.approve(request.user)
                messages.success(request, 'AI artifact approved!')
            else:
                artifact.reject(request.user, notes)
                messages.info(request, 'AI artifact rejected.')
        else:
            messages.error(request, 'Invalid form submission.')
        
        return redirect('production_ledger:episode_ai_drafts', pk=artifact.episode.pk)


class AIArtifactUseView(LoginRequiredMixin, OrganizationMixin, RoleMixin, View):
    """Use an approved AI artifact to create a draft."""
    
    def post(self, request, pk):
        artifact = get_object_or_404(AIArtifact, pk=pk)
        
        if artifact.approval_status != ApprovalStatus.APPROVED:
            messages.error(request, 'Only approved artifacts can be used.')
            return redirect('production_ledger:episode_ai_drafts', pk=artifact.episode.pk)
        
        if artifact.artifact_type == ArtifactType.SHOW_NOTES:
            # Create a show note draft from the artifact
            ShowNoteDraft.objects.create(
                episode=artifact.episode,
                organization_uuid=artifact.organization_uuid,
                markdown=artifact.output_text,
                created_from_ai_artifact=artifact,
                created_by=request.user,
            )
            messages.success(request, 'Show notes draft created from AI artifact!')
            return redirect('production_ledger:episode_show_notes', pk=artifact.episode.pk)
        
        messages.info(request, 'Artifact copied. Check the relevant section.')
        return redirect('production_ledger:episode_ai_drafts', pk=artifact.episode.pk)


# =============================================================================
# SHOW NOTES
# =============================================================================

class ShowNoteDraftEditView(LoginRequiredMixin, OrganizationMixin, RoleMixin, AuditMixin, UpdateView):
    """Edit a show note draft."""
    
    model = ShowNoteDraft
    form_class = ShowNoteDraftForm
    template_name = 'production_ledger/show_note_draft_form.html'
    required_roles = [Role.ADMIN, Role.HOST, Role.PRODUCER, Role.EDITOR]
    
    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj.episode)
        return obj
    
    def get_success_url(self):
        return reverse('production_ledger:episode_show_notes', kwargs={'pk': self.object.episode.pk})


class FinalizeShowNotesView(LoginRequiredMixin, OrganizationMixin, RoleMixin, FormView):
    """Finalize show notes."""
    
    template_name = 'production_ledger/finalize_show_notes.html'
    form_class = FinalizeShowNotesForm
    required_roles = [Role.ADMIN, Role.HOST]
    
    def get_episode(self):
        episode = get_object_or_404(Episode, pk=self.kwargs['episode_id'])
        self.check_permissions(episode)
        return episode
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['episode'] = self.get_episode()
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        episode = self.get_episode()
        context['episode'] = episode
        context['checklist_complete'] = episode.is_checklist_complete()
        return context
    
    def form_valid(self, form):
        episode = self.get_episode()
        
        # Check checklist
        if not episode.is_checklist_complete():
            messages.error(self.request, 'Cannot finalize until all required checklist items are complete.')
            return redirect('production_ledger:episode_checklist', pk=episode.pk)
        
        # Create or update final
        final, created = ShowNoteFinal.objects.update_or_create(
            episode=episode,
            defaults={
                'organization_uuid': episode.organization_uuid,
                'source_draft': form.cleaned_data['source_draft'],
                'markdown': form.cleaned_data['markdown'],
                'approved_by': self.request.user,
                'approved_at': timezone.now(),
                'created_by': self.request.user if created else None,
                'updated_by': self.request.user,
            }
        )
        
        messages.success(self.request, 'Show notes finalized!')
        return redirect('production_ledger:episode_show_notes', pk=episode.pk)


# =============================================================================
# CHECKLIST
# =============================================================================

class ChecklistToggleView(LoginRequiredMixin, OrganizationMixin, View):
    """Toggle checklist item status."""
    
    def post(self, request, pk):
        item = get_object_or_404(ChecklistItem, pk=pk)
        
        if item.is_done:
            item.mark_undone()
            messages.info(request, f'"{item.title}" marked as not done.')
        else:
            item.mark_done(request.user)
            messages.success(request, f'"{item.title}" completed!')
        
        return redirect('production_ledger:episode_checklist', pk=item.episode.pk)


# =============================================================================
# EXPORTS
# =============================================================================

class ExportMixin(LoginRequiredMixin, OrganizationMixin, RoleMixin):
    """Mixin for export views."""
    
    def get_episode(self):
        episode = get_object_or_404(Episode, pk=self.kwargs['pk'])
        if not can_export(self.request.user, episode):
            raise PermissionDenied("You cannot export this episode.")
        return episode


class ExportEpisodeJSONView(ExportMixin, View):
    """Export episode as JSON."""
    
    def get(self, request, pk):
        episode = self.get_episode()
        content = export_episode_package_json_string(episode)
        
        response = HttpResponse(content, content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="{episode.show.slug}-{episode.pk}.json"'
        return response


class ExportShowNotesMarkdownView(ExportMixin, View):
    """Export show notes as Markdown."""
    
    def get(self, request, pk):
        episode = self.get_episode()
        content = export_show_notes_markdown(episode)
        
        response = HttpResponse(content, content_type='text/markdown')
        response['Content-Disposition'] = f'attachment; filename="{episode.show.slug}-{episode.pk}-show-notes.md"'
        return response


class ExportClipsCSVView(ExportMixin, View):
    """Export clips as CSV."""
    
    def get(self, request, pk):
        episode = self.get_episode()
        content = export_clips_csv(episode)
        
        response = HttpResponse(content, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{episode.show.slug}-{episode.pk}-clips.csv"'
        return response


class ExportGuestBriefView(ExportMixin, View):
    """Export guest brief as HTML."""
    
    def get(self, request, pk, guest_id):
        episode = self.get_episode()
        guest = get_object_or_404(Guest, pk=guest_id)
        content = export_guest_brief_html(episode, guest)
        
        response = HttpResponse(content, content_type='text/html')
        response['Content-Disposition'] = f'attachment; filename="guest-brief-{guest.name.replace(" ", "-")}.html"'
        return response


class ExportFullPackageView(ExportMixin, View):
    """Export full publishing package as ZIP."""
    
    def get(self, request, pk):
        episode = self.get_episode()
        package = generate_full_export_package(episode)
        
        # Create ZIP file
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('episode.json', package['json'])
            zf.writestr('show-notes.md', package['markdown'])
            zf.writestr('clips.csv', package['clips_csv'])
            zf.writestr('segments.csv', package['segments_csv'])
            
            for guest_id, brief_data in package['guest_briefs'].items():
                filename = f"guest-brief-{brief_data['guest_name'].replace(' ', '-')}.html"
                zf.writestr(filename, brief_data['html'])
        
        buffer.seek(0)
        
        response = HttpResponse(buffer.read(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{episode.show.slug}-{episode.pk}-package.zip"'
        return response


# Need to import models for the aggregate function
from django.db import models


# =============================================================================
# CONTENT LIST VIEWS
# =============================================================================

class TranscriptListView(LoginRequiredMixin, OrganizationMixin, ListView):
    """List all transcripts across episodes."""
    model = Transcript
    template_name = 'production_ledger/transcript_list.html'
    context_object_name = 'transcripts'

    def get_queryset(self):
        return Transcript.objects.filter(
            organization_uuid=self.get_organization_uuid()
        ).select_related('episode', 'episode__show').order_by('-created_at')


class MediaAssetListView(LoginRequiredMixin, OrganizationMixin, ListView):
    """List all media assets across episodes."""
    model = MediaAsset
    template_name = 'production_ledger/asset_list.html'
    context_object_name = 'assets'

    def get_queryset(self):
        return MediaAsset.objects.filter(
            organization_uuid=self.get_organization_uuid()
        ).select_related('episode', 'episode__show').order_by('-created_at')


class AIToolsView(LoginRequiredMixin, OrganizationMixin, ListView):
    """List all AI artifacts across episodes."""
    model = AIArtifact
    template_name = 'production_ledger/ai_tools.html'
    context_object_name = 'artifacts'

    def get_queryset(self):
        return AIArtifact.objects.filter(
            organization_uuid=self.get_organization_uuid()
        ).select_related('episode', 'episode__show').order_by('-created_at')


class IntegrationsView(LoginRequiredMixin, OrganizationMixin, TemplateView):
    """Show available integrations and connection status."""
    template_name = 'production_ledger/integrations.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['integrations'] = [
            {
                'name': 'Riverside.fm',
                'description': 'Import recordings automatically from Riverside.fm sessions.',
                'icon': '🎙️',
                'status': 'coming_soon',
            },
            {
                'name': 'Zoom',
                'description': 'Sync cloud recordings from your Zoom meetings.',
                'icon': '📹',
                'status': 'coming_soon',
            },
            {
                'name': 'Google Meet',
                'description': 'Import recordings from Google Meet via Google Drive.',
                'icon': '📞',
                'status': 'coming_soon',
            },
            {
                'name': 'YouTube',
                'description': 'Publish episodes directly to your YouTube channel.',
                'icon': '▶️',
                'status': 'coming_soon',
            },
            {
                'name': 'Spotify for Podcasters',
                'description': 'Submit and manage your podcast on Spotify.',
                'icon': '🎵',
                'status': 'coming_soon',
            },
            {
                'name': 'Apple Podcasts',
                'description': 'Manage your Apple Podcasts listing and episodes.',
                'icon': '🍎',
                'status': 'coming_soon',
            },
        ]
        return context


class SettingsView(LoginRequiredMixin, OrganizationMixin, TemplateView):
    """Organization settings and configuration."""
    template_name = 'production_ledger/settings.html'

    def get_context_data(self, **kwargs):
        from .models import EpisodeType
        context = super().get_context_data(**kwargs)
        org_uuid = self.get_organization_uuid()
        context['episode_types'] = EpisodeType.objects.filter(
            models.Q(organization_uuid=org_uuid) | models.Q(organization_uuid__isnull=True)
        ).order_by('sort_order')
        context['show_count'] = Show.objects.filter(organization_uuid=org_uuid).count()
        context['episode_count'] = Episode.objects.filter(organization_uuid=org_uuid).count()
        context['guest_count'] = Guest.objects.filter(organization_uuid=org_uuid).count()
        context['transcript_count'] = Transcript.objects.filter(organization_uuid=org_uuid).count()
        context['asset_count'] = MediaAsset.objects.filter(organization_uuid=org_uuid).count()
        return context


# =============================================================================
# REQUEST ACCESS (PUBLIC)
# =============================================================================

class RequestAccessView(TemplateView):
    """Public page for requesting access to the platform."""
    template_name = 'production_ledger/request_access.html'

    def post(self, request, *args, **kwargs):
        from .forms import AccessRequestForm
        from django.contrib.auth.models import User
        from .services.email import send_access_request_received
        form = AccessRequestForm(request.POST)
        if form.is_valid():
            access_request = form.save()
            # Notify all superusers
            admin_emails = list(
                User.objects.filter(is_superuser=True)
                .exclude(email='')
                .values_list('email', flat=True)
            )
            send_access_request_received(access_request, admin_emails)
            return self.render_to_response(self.get_context_data(
                submitted=True,
                submitted_email=form.cleaned_data['email'],
            ))
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'form' not in context and not context.get('submitted'):
            from .forms import AccessRequestForm
            context['form'] = AccessRequestForm()
        return context


# =============================================================================
# ACCEPT INVITATION (PUBLIC)
# =============================================================================

class AcceptInviteView(TemplateView):
    """Accept an invitation and set a password."""
    template_name = 'production_ledger/accept_invite.html'

    def _get_invitation(self):
        from .models import Invitation
        token = self.kwargs.get('token', '')
        try:
            return Invitation.objects.get(token=token)
        except Invitation.DoesNotExist:
            return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invitation = self._get_invitation()
        if not invitation:
            context['error'] = 'This invitation link is invalid or has expired.'
        elif invitation.is_accepted:
            context['error'] = 'This invitation has already been used. Please sign in.'
        else:
            context['invitation'] = invitation
        return context

    def post(self, request, *args, **kwargs):
        from django.contrib.auth.models import User
        from django.utils import timezone as tz
        invitation = self._get_invitation()
        if not invitation or invitation.is_accepted:
            return self.render_to_response(self.get_context_data())

        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        first_name = request.POST.get('first_name', '').strip()[:30]

        if len(password) < 8:
            return self.render_to_response(self.get_context_data(
                form_errors='Password must be at least 8 characters.',
            ))
        if password != password2:
            return self.render_to_response(self.get_context_data(
                form_errors='Passwords do not match.',
            ))

        email = invitation.email.lower().strip()
        username = email.split('@')[0][:150]
        # Ensure unique username
        base = username
        n = 1
        while User.objects.filter(username=username).exists():
            username = f'{base}{n}'
            n += 1

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name or (invitation.name or '').split()[0][:30],
        )
        invitation.accepted_at = tz.now()
        invitation.save()

        # Log the user in
        from django.contrib.auth import login
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, 'Welcome to ProducerForge!')

        # Redirect based on role
        if invitation.role == 'guest':
            return redirect('production_ledger:guest_portal')
        return redirect('production_ledger:dashboard')


# =============================================================================
# GUEST PORTAL
# =============================================================================

class GuestPortalView(LoginRequiredMixin, TemplateView):
    """
    Simplified dashboard for podcast guests.
    Shows only episodes the user is linked to.
    """
    template_name = 'production_ledger/guest_portal.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Find episodes where this user is a guest via EpisodeGuest → Guest → email match
        guest_records = Guest.objects.filter(email=user.email)
        episode_ids = EpisodeGuest.objects.filter(
            guest__in=guest_records
        ).values_list('episode_id', flat=True)

        # Also include episodes from shows where user has GUEST role
        guest_show_ids = ShowRoleAssignment.objects.filter(
            user=user, role='guest'
        ).values_list('show_id', flat=True)

        context['episodes'] = Episode.objects.filter(
            models.Q(id__in=episode_ids) | models.Q(show_id__in=guest_show_ids)
        ).select_related('show').distinct().order_by('-updated_at')

        assigned_show_ids = set(
            ShowRoleAssignment.objects.filter(user=user).values_list('show_id', flat=True)
        )
        context['available_shows'] = Show.objects.exclude(id__in=assigned_show_ids).order_by('name')
        context['pending_show_request_ids'] = set(
            ShowJoinRequest.objects.filter(user=user, status='pending').values_list('show_id', flat=True)
        )
        context['roles'] = Role.CHOICES
        return context


class RequestShowJoinView(LoginRequiredMixin, View):
    """Allow an authenticated user to request access to a specific show."""

    def post(self, request, show_id):
        show = get_object_or_404(Show, pk=show_id)

        if ShowRoleAssignment.objects.filter(show=show, user=request.user).exists():
            messages.info(request, 'You already have access to this show.')
            return redirect('production_ledger:guest_portal')

        if ShowJoinRequest.objects.filter(show=show, user=request.user, status='pending').exists():
            messages.info(request, 'You already have a pending request for this show.')
            return redirect('production_ledger:guest_portal')

        form = ShowJoinRequestForm(request.POST)
        if form.is_valid():
            join_request = form.save(commit=False)
            join_request.show = show
            join_request.user = request.user
            join_request.status = 'pending'
            join_request.save()
            messages.success(request, f'Request sent to join {show.name} as {join_request.desired_role}.')
        else:
            messages.error(request, 'Could not submit request. Please try again.')

        return redirect('production_ledger:guest_portal')


# =============================================================================
# ADMIN – USER MANAGEMENT
# =============================================================================

class UserManagementView(LoginRequiredMixin, TemplateView):
    """Admin view for managing users, invitations, and access requests."""
    template_name = 'production_ledger/user_management.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied("Only admins can manage users.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        from django.contrib.auth.models import User
        from .models import AccessRequest, Invitation
        context = super().get_context_data(**kwargs)
        context['users'] = User.objects.all().order_by('-date_joined')
        context['invitations'] = Invitation.objects.all()
        context['access_requests'] = AccessRequest.objects.all()
        context['pending_requests'] = AccessRequest.objects.filter(status='pending')
        context['active_tab'] = self.request.GET.get('tab', 'users')
        return context


class InviteUserView(LoginRequiredMixin, TemplateView):
    """Admin view to send an invitation."""
    template_name = 'production_ledger/invite_user.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied("Only admins can invite users.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        from .forms import InvitationForm
        from .constants import Role
        context = super().get_context_data(**kwargs)
        if 'form' not in context:
            context['form'] = InvitationForm()
        context['role_choices'] = Role.CHOICES
        return context

    def post(self, request, *args, **kwargs):
        from .forms import InvitationForm
        from .services.email import send_invitation_email
        form = InvitationForm(request.POST)
        if form.is_valid():
            invitation = form.save(commit=False)
            invitation.invited_by = request.user
            invitation.save()
            invite_link = request.build_absolute_uri(
                reverse('production_ledger:accept_invite', kwargs={'token': invitation.token})
            )
            send_invitation_email(invitation, invite_link)
            messages.success(request, f'Invitation sent to {invitation.email}')
            return self.render_to_response(self.get_context_data(
                form=InvitationForm(),
                invite_link=invite_link,
            ))
        return self.render_to_response(self.get_context_data(form=form))


class ReviewAccessRequestView(LoginRequiredMixin, View):
    """Admin action to approve or decline an access request."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied("Only admins can review access requests.")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        from .models import AccessRequest, Invitation
        from django.utils import timezone as tz
        ar = get_object_or_404(AccessRequest, pk=kwargs['pk'])
        action = request.POST.get('action')

        if action == 'approve':
            ar.status = 'approved'
            ar.reviewed_by = request.user
            ar.reviewed_at = tz.now()
            ar.save()
            # Auto-create an invitation
            invitation = Invitation.objects.create(
                email=ar.email,
                name=ar.name,
                role='guest',
                invited_by=request.user,
            )
            invite_link = request.build_absolute_uri(
                reverse('production_ledger:accept_invite', kwargs={'token': invitation.token})
            )
            from .services.email import send_access_approved
            send_access_approved(invitation, invite_link)
            messages.success(
                request,
                f'Approved {ar.name}. Invite link: {invite_link}'
            )
        elif action == 'decline':
            ar.status = 'declined'
            ar.reviewed_by = request.user
            ar.reviewed_at = tz.now()
            ar.save()
            from .services.email import send_access_declined
            send_access_declined(ar)
            messages.info(request, f'Declined request from {ar.name}.')

        return redirect(reverse('production_ledger:user_management') + '?tab=requests')


class UserAccountActionView(LoginRequiredMixin, View):
    """Admin actions for existing users: edit, disable, and password resets."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied("Only admins can manage users.")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        import secrets
        import string
        from django.contrib.auth.models import User

        user = get_object_or_404(User, pk=kwargs['pk'])
        action = request.POST.get('action', '').strip()

        if action == 'update':
            email = (request.POST.get('email', '') or '').strip().lower()
            first_name = (request.POST.get('first_name', '') or '').strip()[:30]
            last_name = (request.POST.get('last_name', '') or '').strip()[:150]
            is_active = request.POST.get('is_active') == 'on'
            is_superuser = request.POST.get('is_superuser') == 'on'

            if email and User.objects.exclude(pk=user.pk).filter(email=email).exists():
                messages.error(request, f'Email {email} is already in use by another user.')
                return redirect(reverse('production_ledger:user_management') + '?tab=users')

            if email:
                user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.is_active = is_active
            user.is_superuser = is_superuser
            user.is_staff = is_superuser
            user.save()
            messages.success(request, f'Updated user {user.username}.')

        elif action == 'disable':
            if user.pk == request.user.pk:
                messages.error(request, 'You cannot disable your own account.')
                return redirect(reverse('production_ledger:user_management') + '?tab=users')

            user.is_active = False
            user.save(update_fields=['is_active'])
            messages.success(request, f'Disabled user {user.username}.')

        elif action == 'delete':
            if user.pk == request.user.pk:
                messages.error(request, 'You cannot delete your own account.')
                return redirect(reverse('production_ledger:user_management') + '?tab=users')

            username = user.username
            user.delete()
            messages.success(request, f'Deleted user {username}.')

        elif action in {'set_temp_password', 'reset_password'}:
            temp_password = (request.POST.get('temp_password', '') or '').strip()
            if action == 'reset_password' or not temp_password:
                alphabet = string.ascii_letters + string.digits
                temp_password = ''.join(secrets.choice(alphabet) for _ in range(12))

            if len(temp_password) < 8:
                messages.error(request, 'Temporary password must be at least 8 characters.')
                return redirect(reverse('production_ledger:user_management') + '?tab=users')

            user.set_password(temp_password)
            user.save()
            messages.success(
                request,
                f'Temporary password for {user.username}: {temp_password}'
            )
        else:
            messages.error(request, 'Unknown user action.')

        return redirect(reverse('production_ledger:user_management') + '?tab=users')


class InvitationActionView(LoginRequiredMixin, View):
    """Admin actions for invitations: edit, delete, and resend."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied("Only admins can manage invitations.")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        from .models import Invitation
        from .services.email import send_invitation_email

        invitation = get_object_or_404(Invitation, pk=kwargs['pk'])
        action = request.POST.get('action', '').strip()

        if action == 'update':
            email = (request.POST.get('email', '') or '').strip().lower()
            name = (request.POST.get('name', '') or '').strip()[:200]
            role = (request.POST.get('role', '') or '').strip()

            if not email:
                messages.error(request, 'Invitation email is required.')
                return redirect(reverse('production_ledger:user_management') + '?tab=invitations')

            valid_roles = {choice[0] for choice in Role.CHOICES}
            if role and role not in valid_roles:
                messages.error(request, 'Invalid invitation role.')
                return redirect(reverse('production_ledger:user_management') + '?tab=invitations')

            invitation.email = email
            invitation.name = name
            if role:
                invitation.role = role
            invitation.save()
            messages.success(request, f'Updated invitation for {invitation.email}.')

        elif action == 'delete':
            target_email = invitation.email
            invitation.delete()
            messages.success(request, f'Deleted invitation for {target_email}.')

        elif action == 'resend':
            invite_link = request.build_absolute_uri(
                reverse('production_ledger:accept_invite', kwargs={'token': invitation.token})
            )
            send_invitation_email(invitation, invite_link)
            messages.success(request, f'Resent invitation to {invitation.email}.')
        else:
            messages.error(request, 'Unknown invitation action.')

        return redirect(reverse('production_ledger:user_management') + '?tab=invitations')
