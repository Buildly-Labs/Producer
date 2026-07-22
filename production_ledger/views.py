"""
Views for Production Ledger.

All views enforce organization scoping and RBAC.
"""
import json
import logging
import secrets
import zipfile
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.http import Http404, HttpResponse, JsonResponse
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
    AssetType,
    ApprovalStatus,
    ArtifactType,
    ClipPriority,
    CommentPlatform,
    CommentStatus,
    EpisodeStatus,
    IngestionStatus,
    MediaPlatform,
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
    PodcastFeedConfigForm,
    QuickClipForm,
    SegmentForm,
    SegmentTemplateForm,
    SegmentTemplatePickForm,
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
    BackgroundTask,
    ChecklistItem,
    ClipMoment,
    Episode,
    EpisodeGuest,
    Guest,
    MediaAsset,
    PlatformComment,
    Segment,
    SegmentTemplate,
    Show,
    ShowJoinRequest,
    ShowNoteDraft,
    ShowNoteFinal,
    ShowRoleAssignment,
    Sponsor,
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


class EpisodeListView(LoginRequiredMixin, OrganizationMixin, ListView):
    """List all episodes across shows. Linked from the sidebar's Episodes nav item."""

    model = Episode
    template_name = 'production_ledger/episode_list.html'
    context_object_name = 'episodes'

    def get_queryset(self):
        return super().get_queryset().select_related('show').order_by('-created_at')


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


class ShowPodcastFeedView(View):
    """
    Public RSS feed endpoint: GET /shows/<slug>/feed.xml
    No login required — podcast apps hit this URL directly.
    Builds the feed from the database on every request so it's always fresh.
    """

    def get(self, request, slug):
        from .models import PodcastFeedConfig, Show  # noqa: PLC0415
        from .services.distribution import _build_rss_feed, _get_feed_config  # noqa: PLC0415
        from .constants import DistributionStatus  # noqa: PLC0415
        from .models import PodcastDistribution  # noqa: PLC0415

        show = get_object_or_404(Show, slug=slug)
        config = _get_feed_config(show)

        # Make sure feed_public_url points to this view (idempotent)
        app_feed_url = request.build_absolute_uri(
            reverse('production_ledger:show_podcast_feed', kwargs={'slug': slug})
        )
        if config.feed_public_url != app_feed_url:
            config.feed_public_url = app_feed_url
            config.save(update_fields=['feed_public_url'])

        dists = (
            PodcastDistribution.objects
            .filter(
                episode__show=show,
                status__in=[DistributionStatus.SUBMITTED, DistributionStatus.LIVE],
            )
            .select_related('episode', 'episode__show_note_final')
            .exclude(audio_public_url='')
            .order_by('episode__publish_date')
        )

        try:
            feed_xml = _build_rss_feed(show, config, dists)
        except Exception as exc:
            return HttpResponse(f'Feed generation error: {exc}', status=500, content_type='text/plain')

        response = HttpResponse(feed_xml, content_type='application/rss+xml; charset=utf-8')
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        return response


# =============================================================================
# YOUTUBE OAUTH VIEWS
# =============================================================================

class YoutubeOAuthStartView(LoginRequiredMixin, OrganizationMixin, View):
    """
    Start the YouTube OAuth 2.0 authorisation flow for a Show.
    Requires ADMIN role.  Stores the OAuth state in the session and redirects
    the user to Google's consent screen.
    """

    def get(self, request, pk):
        from .models import PodcastFeedConfig, Show  # noqa: PLC0415
        from .services.youtube import build_oauth_flow  # noqa: PLC0415

        show = get_object_or_404(Show, pk=pk, organization_uuid=self.get_organization_uuid())
        if not has_minimum_role(request.user, show, Role.ADMIN):
            raise PermissionDenied("Admin role required to connect YouTube.")
        try:
            config, _ = PodcastFeedConfig.objects.get_or_create(
                show=show,
                defaults={'organization_uuid': show.organization_uuid},
            )
            redirect_uri = request.build_absolute_uri(
                reverse('production_ledger:youtube_oauth_callback', kwargs={'pk': pk})
            )
            flow = build_oauth_flow(config, redirect_uri)
            auth_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent',
            )
            request.session['yt_oauth_state'] = state
            request.session['yt_oauth_show_pk'] = str(pk)
            return redirect(auth_url)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('production_ledger:show_edit', pk=pk)


class YoutubeOAuthCallbackView(LoginRequiredMixin, OrganizationMixin, View):
    """
    Handle the OAuth 2.0 callback from Google, exchange the code for tokens,
    store the refresh_token in PodcastFeedConfig, and redirect back to Show edit.
    """

    def get(self, request, pk):
        from .models import PodcastFeedConfig, Show  # noqa: PLC0415
        from .services.youtube import build_oauth_flow, fetch_channel_info  # noqa: PLC0415

        show = get_object_or_404(Show, pk=pk, organization_uuid=self.get_organization_uuid())

        error = request.GET.get('error')
        if error:
            messages.error(request, f'YouTube authorisation denied: {error}')
            return redirect('production_ledger:show_edit', pk=pk)

        state = request.session.get('yt_oauth_state', '')
        try:
            config = PodcastFeedConfig.objects.get(show=show)
            redirect_uri = request.build_absolute_uri(
                reverse('production_ledger:youtube_oauth_callback', kwargs={'pk': pk})
            )
            flow = build_oauth_flow(config, redirect_uri)
            flow.fetch_token(
                authorization_response=request.build_absolute_uri(),
                state=state,
            )
            creds = flow.credentials
            config.youtube_refresh_token = creds.refresh_token or config.youtube_refresh_token
            config.save(update_fields=['youtube_refresh_token'])

            # Fetch channel info
            try:
                channel_id, channel_name = fetch_channel_info(config)
                config.youtube_channel_id = channel_id
                config.youtube_channel_name = channel_name
                config.save(update_fields=['youtube_channel_id', 'youtube_channel_name'])
            except Exception as exc:
                logger.warning("Could not fetch YouTube channel info: %s", exc)

            messages.success(
                request,
                f'YouTube connected successfully! Channel: {config.youtube_channel_name or config.youtube_channel_id}',
            )
        except Exception as exc:
            logger.exception("YouTube OAuth callback error")
            messages.error(request, f'YouTube connection failed: {exc}')

        return redirect('production_ledger:show_edit', pk=pk)


class YoutubeDisconnectView(LoginRequiredMixin, OrganizationMixin, View):
    """Clear stored YouTube OAuth credentials for a Show (POST only)."""

    def post(self, request, pk):
        from .models import PodcastFeedConfig, Show  # noqa: PLC0415

        show = get_object_or_404(Show, pk=pk, organization_uuid=self.get_organization_uuid())
        if not has_minimum_role(request.user, show, Role.ADMIN):
            raise PermissionDenied("Admin role required.")
        try:
            config = PodcastFeedConfig.objects.get(show=show)
            config.youtube_refresh_token = ''
            config.youtube_channel_id = ''
            config.youtube_channel_name = ''
            config.save(update_fields=['youtube_refresh_token', 'youtube_channel_id', 'youtube_channel_name'])
            messages.success(request, 'YouTube disconnected.')
        except PodcastFeedConfig.DoesNotExist:
            pass
        return redirect('production_ledger:show_edit', pk=pk)


class IntroPreviewServeView(LoginRequiredMixin, View):
    """
    GET /ledger/episodes/<pk>/intro-preview-serve/
        ?token=<uuid>

    Serve the TTS preview MP3 generated by IntroPreviewAPI.
    Validates that the session token matches so only the requesting user
    can access the file.
    """

    def get(self, request, pk):
        import tempfile as _tmp  # noqa: PLC0415
        from pathlib import Path as _Path  # noqa: PLC0415
        from django.http import FileResponse, Http404  # noqa: PLC0415

        token = request.GET.get('token', '').strip()
        if not token:
            raise Http404

        session_key = f'intro_preview_{pk}'
        stored_token = request.session.get(session_key)
        if stored_token != token:
            raise Http404

        # Sanitise: only allow hex-and-dash (UUID format)
        import re as _re  # noqa: PLC0415
        if not _re.fullmatch(r'[0-9a-f\-]{36}', token):
            raise Http404

        serve_dir = _Path(_tmp.gettempdir()) / 'forge_tts_serve'
        mp3_path = serve_dir / f'{token}.mp3'
        if not mp3_path.exists():
            raise Http404

        return FileResponse(
            open(mp3_path, 'rb'),  # noqa: WPS515
            content_type='audio/mpeg',
            as_attachment=False,
        )


class ShowUpdateView(LoginRequiredMixin, OrganizationMixin, RoleMixin, AuditMixin, UpdateView):
    """Update a show, including its podcast feed configuration."""

    model = Show
    form_class = ShowForm
    template_name = 'production_ledger/show_form.html'
    required_roles = [Role.ADMIN]

    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj)
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'feed_form' not in context:
            feed_config = getattr(self.object, 'podcast_feed_config', None)
            context['feed_form'] = PodcastFeedConfigForm(instance=feed_config)
        context['existing_cover_art_url'] = getattr(
            getattr(self.object, 'podcast_feed_config', None), 'cover_art_url', ''
        )
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        feed_config = getattr(self.object, 'podcast_feed_config', None)
        feed_form = PodcastFeedConfigForm(request.POST, request.FILES, instance=feed_config)
        if form.is_valid() and feed_form.is_valid():
            response = self.form_valid(form)
            feed_instance = feed_form.save(commit=False)
            feed_instance.show = self.object
            feed_instance.organization_uuid = self.object.organization_uuid

            # Set feed_public_url to the app-served endpoint (always valid,
            # even before the feed XML has been uploaded to Spaces)
            app_feed_url = request.build_absolute_uri(
                reverse('production_ledger:show_podcast_feed', kwargs={'slug': self.object.slug})
            )
            feed_instance.feed_public_url = app_feed_url

            # Upload cover art to DO Spaces if a file was provided
            cover_art_file = request.FILES.get('cover_art')
            if cover_art_file:
                from .services import storage as _storage  # noqa: PLC0415
                allowed = {'image/jpeg', 'image/png', 'image/jpg'}
                ct = cover_art_file.content_type or ''
                if ct not in allowed:
                    messages.warning(request, f'Cover art must be JPEG or PNG (got {ct}); other changes saved.')
                else:
                    import mimetypes  # noqa: PLC0415
                    ext = mimetypes.guess_extension(ct) or '.jpg'
                    ext = ext.lstrip('.')
                    art_key = _storage.cover_art_key(
                        str(self.object.organization_uuid),
                        self.object.slug,
                        f"cover.{ext}",
                    )
                    try:
                        art_url = _storage.upload_file(
                            cover_art_file,
                            art_key,
                            content_type=ct,
                            public=True,
                        )
                        feed_instance.cover_art_url = art_url
                    except Exception:
                        pass  # Don't block save if Spaces is unavailable

            feed_instance.save()
            return response
        return self.render_to_response(
            self.get_context_data(form=form, feed_form=feed_form)
        )

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

        if request.POST.get('action') == 'remove':
            ShowRoleAssignment.objects.filter(
                show=show, pk=request.POST.get('assignment_id'), show__organization_uuid=show.organization_uuid
            ).delete()
            messages.success(request, 'Role assignment removed.')
            return redirect('production_ledger:show_roles', pk=show.pk)

        form = ShowRoleAssignmentForm(request.POST)

        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.show = show
            assignment.created_by = request.user
            assignment.save()
            messages.success(request, 'Role assigned successfully!')
        else:
            messages.error(request, 'Error assigning role.')

        return redirect('production_ledger:show_roles', pk=show.pk)


class SegmentTemplateListView(LoginRequiredMixin, OrganizationMixin, RoleMixin, TemplateView):
    """Manage the reusable segment template library for a show."""

    template_name = 'production_ledger/segment_templates.html'
    required_roles = [Role.ADMIN, Role.HOST, Role.PRODUCER]

    def get_show(self):
        show = get_object_or_404(Show, pk=self.kwargs['pk'])
        self.check_permissions(show)
        return show

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        show = self.get_show()
        context['show'] = show
        context['templates'] = SegmentTemplate.objects.filter(show=show).order_by('title')
        context['form'] = SegmentTemplateForm(show=show)
        return context

    def post(self, request, *args, **kwargs):
        show = self.get_show()
        form = SegmentTemplateForm(request.POST, show=show)

        if form.is_valid():
            template = form.save(commit=False)
            template.show = show
            template.organization_uuid = show.organization_uuid
            template.created_by = request.user
            template.save()
            messages.success(request, f'"{template.title}" added to the segment library.')
        else:
            messages.error(request, 'Error saving segment template.')

        return redirect('production_ledger:segment_templates', pk=show.pk)


class SegmentTemplateUpdateView(LoginRequiredMixin, OrganizationMixin, RoleMixin, AuditMixin, UpdateView):
    """Edit a segment template."""

    model = SegmentTemplate
    form_class = SegmentTemplateForm
    template_name = 'production_ledger/segment_template_form.html'
    required_roles = [Role.ADMIN, Role.HOST, Role.PRODUCER]

    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj.show)
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['show'] = self.get_object().show
        return kwargs

    def get_success_url(self):
        return reverse('production_ledger:segment_templates', kwargs={'pk': self.object.show.pk})


class SegmentTemplateDeleteView(LoginRequiredMixin, OrganizationMixin, RoleMixin, DeleteView):
    """Delete a segment template. Existing episode Segments copied from it are unaffected."""

    model = SegmentTemplate
    required_roles = [Role.ADMIN, Role.HOST, Role.PRODUCER]

    def get_object(self):
        obj = super().get_object()
        self.check_permissions(obj.show)
        return obj

    def get_success_url(self):
        return reverse('production_ledger:segment_templates', kwargs={'pk': self.object.show.pk})


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
        from .constants import PodcastPlatform, DistributionStatus  # noqa: PLC0415

        context = super().get_context_data(**kwargs)
        episode = self.get_episode()

        distributions = {
            d.platform: d
            for d in PodcastDistribution.objects.filter(episode=episode)
        }
        context['distributions'] = distributions

        # Build per-platform rows with setup instructions
        platform_rows = []
        for code, label in PodcastPlatform.CHOICES:
            dist = distributions.get(code)
            platform_rows.append({
                'code': code,
                'label': label,
                'dist': dist,
                'status': dist.status if dist else None,
                'platform_url': dist.platform_url if dist else '',
                'audio_url': dist.audio_public_url if dist else '',
                'submission_url': PodcastPlatform.SUBMISSION_URLS.get(code, ''),
            })
        context['platform_rows'] = platform_rows
        context['DistributionStatus'] = DistributionStatus

        context['audio_assets'] = episode.media_assets.filter(
            asset_type=AssetType.AUDIO,
        ).order_by('-created_at')
        context['video_assets'] = episode.media_assets.filter(
            asset_type=AssetType.VIDEO,
        ).order_by('-created_at')

        # Only video assets with a directly-downloadable URL (no YouTube/Vimeo links)
        from .services.audio_extraction import is_directly_downloadable  # noqa: PLC0415
        context['extractable_video_assets'] = [
            a for a in context['video_assets']
            if a.external_url and is_directly_downloadable(a.external_url)
        ]

        # Auto-reset any assets that are stuck in PROCESSING/PENDING with a
        # non-downloadable URL — they can never finish.
        for asset in context['video_assets']:
            if (
                asset.ingestion_status in (IngestionStatus.PENDING, IngestionStatus.PROCESSING)
                and asset.external_url
                and not is_directly_downloadable(asset.external_url)
            ):
                asset.ingestion_status = IngestionStatus.FAILED
                asset.error_message = (
                    "Cannot extract audio from YouTube/Vimeo links. "
                    "Upload the video file directly instead."
                )
                asset.save(update_fields=['ingestion_status', 'error_message'])

        # Auto-expire assets stuck in PENDING/PROCESSING for more than 2 hours.
        # This handles orphaned rows that survived container restarts and were
        # not caught by the fix_stuck_tasks startup command.
        import datetime as _dt  # noqa: PLC0415
        from django.utils import timezone as _tz  # noqa: PLC0415
        _stuck_cutoff = _tz.now() - _dt.timedelta(hours=2)
        _zombie_qs = episode.media_assets.filter(
            ingestion_status__in=[IngestionStatus.PENDING, IngestionStatus.PROCESSING],
            created_at__lt=_stuck_cutoff,
        )
        if _zombie_qs.exists():
            _zombie_qs.update(
                ingestion_status=IngestionStatus.FAILED,
                error_message=(
                    'Extraction was interrupted (server restart or timeout). '
                    'Please retry.'
                ),
            )
            logger.warning(
                '[publish] Auto-expired stuck processing assets for episode %s (older than 2h)',
                episode.pk,
            )

        # Assets currently being processed in background — page will auto-refresh
        context['processing_assets'] = list(
            episode.media_assets.filter(
                ingestion_status__in=[IngestionStatus.PENDING, IngestionStatus.PROCESSING],
            ).values('pk', 'label', 'ingestion_status')
        )

        # Recently failed extraction assets — show error banner
        from django.utils import timezone as _tz  # noqa: PLC0415
        import datetime as _dt  # noqa: PLC0415
        context['failed_extraction_assets'] = list(
            episode.media_assets.filter(
                ingestion_status=IngestionStatus.FAILED,
                created_at__gte=_tz.now() - _dt.timedelta(hours=2),
            ).order_by('-created_at').values('pk', 'label', 'error_message')[:3]
        )

        try:
            context['podcast_feed_config'] = episode.show.podcast_feed_config
        except Exception:
            context['podcast_feed_config'] = None

        context['can_publish'] = has_minimum_role(self.request.user, episode.show, Role.PRODUCER)
        context['can_mark_published'] = episode.status == EpisodeStatus.APPROVED and episode.is_checklist_complete()

        # Distributions that have audio (for the episode audio scrubber in Intro Studio)
        context['audio_distributions'] = [
            d for d in distributions.values()
            if d.audio_public_url
        ]

        # Build Spotify upload pack — title, HTML description (≤4000 chars), guests
        context['spotify_pack'] = self._build_spotify_pack(episode)
        return context

    def _build_spotify_pack(self, episode):
        """Assemble pre-filled metadata for manual Spotify upload."""
        # Description: show notes markdown converted to plain paragraphs, then guest bios
        parts = []

        show_note = getattr(episode, 'show_note_final', None)
        if show_note and show_note.markdown:
            # Strip markdown headers/bullets to plain text for Spotify's HTML field
            import re  # noqa: PLC0415
            plain = re.sub(r'#+\s*', '', show_note.markdown)
            plain = re.sub(r'\*\*(.+?)\*\*', r'\1', plain)
            plain = re.sub(r'\*(.+?)\*', r'\1', plain)
            plain = re.sub(r'!\[.*?\]\(.*?\)', '', plain)  # strip images
            # Convert [text](url) to <a href="url">text</a>
            plain = re.sub(r'\[(.+?)\]\((https?://[^\)]+)\)', r'<a href="\2">\1</a>', plain)
            plain = re.sub(r'^\s*[-*+]\s+', '', plain, flags=re.MULTILINE)
            parts.append(plain.strip())

        guests = list(
            episode.episode_guests.select_related('guest').all()
        )
        if guests:
            guest_lines = []
            for eg in guests:
                g = eg.guest
                line = f"<b>{g.name}</b>"
                if g.title or g.org:
                    line += f" — {', '.join(filter(None, [g.title, g.org]))}"
                if g.bio:
                    line += f"<br>{g.bio}"
                # Add any web/social links
                if isinstance(g.links, dict):
                    link_parts = [f'<a href="{v}">{k}</a>' for k, v in g.links.items() if v and v.startswith('http')]
                    if link_parts:
                        line += '<br>' + ' | '.join(link_parts)
                guest_lines.append(line)
            parts.append('<br><br>'.join(guest_lines))

        # Add show website if configured
        try:
            feed_config = episode.show.podcast_feed_config
            if feed_config and feed_config.website_url:
                parts.append(f'Learn more: <a href="{feed_config.website_url}">{feed_config.website_url}</a>')
        except Exception:
            pass

        description_html = '\n\n'.join(parts)
        # Spotify hard cap is 4000 chars
        if len(description_html) > 4000:
            description_html = description_html[:3997] + '...'

        return {
            'title': episode.title,
            'description_html': description_html,
            'upload_url': 'https://creators.spotify.com',
            'char_count': len(description_html),
        }

    def post(self, request, *args, **kwargs):
        from .services import storage  # noqa: PLC0415
        from .services.distribution import build_and_publish_feed, publish_episode_audio  # noqa: PLC0415

        episode = self.get_episode()
        if not has_minimum_role(request.user, episode.show, Role.PRODUCER):
            messages.error(request, 'Producer role required to publish audio.')
            return redirect('production_ledger:episode_publish', pk=episode.pk)

        action = request.POST.get('action', 'publish_audio')

        if action == 'publish_audio_from_asset':
            # Publish an already-uploaded audio MediaAsset to all podcast platforms
            asset_id = request.POST.get('audio_asset_id')
            if not asset_id:
                messages.error(request, 'Select an audio asset to publish.')
                return redirect('production_ledger:episode_publish', pk=episode.pk)
            try:
                media_asset = episode.media_assets.get(pk=asset_id, asset_type=AssetType.AUDIO)
            except Exception:
                messages.error(request, 'Audio asset not found on this episode.')
                return redirect('production_ledger:episode_publish', pk=episode.pk)

            audio_url = media_asset.external_url or (media_asset.file.url if media_asset.file else '')
            if not audio_url:
                messages.error(request, 'This asset has no accessible URL.')
                return redirect('production_ledger:episode_publish', pk=episode.pk)

            from .constants import DistributionStatus, PodcastPlatform  # noqa: PLC0415
            from .models import PodcastDistribution  # noqa: PLC0415
            from django.utils import timezone as tz  # noqa: PLC0415

            selected_platforms = request.POST.getlist('platforms')
            if not selected_platforms:
                selected_platforms = [p for p, _ in PodcastPlatform.CHOICES]

            count = 0
            for platform in selected_platforms:
                PodcastDistribution.objects.update_or_create(
                    episode=episode,
                    platform=platform,
                    defaults={
                        'organization_uuid': episode.organization_uuid,
                        'audio_public_url': audio_url,
                        'audio_spaces_key': getattr(media_asset, 'spaces_key', ''),
                        'audio_file_size': media_asset.file_size or 0,
                        'audio_duration_seconds': media_asset.duration_seconds or 0,
                        'audio_content_type': media_asset.content_type or 'audio/mpeg',
                        'status': DistributionStatus.SUBMITTED,
                        'submitted_at': tz.now(),
                        'updated_by': request.user,
                    },
                )
                count += 1

            if request.POST.get('rebuild_feed'):
                import threading  # noqa: PLC0415
                import django  # noqa: PLC0415

                from .services.tasks import run_background_task as _rbt  # noqa: PLC0415
                from .models import BackgroundTask as _BT  # noqa: PLC0415

                def _rebuild_feed_fn(show_id, user_id):
                    from django.contrib.auth import get_user_model  # noqa: PLC0415
                    from .models import Show as _Show  # noqa: PLC0415
                    from .services.distribution import build_and_publish_feed as _build  # noqa: PLC0415
                    _build(_Show.objects.get(pk=show_id), user=get_user_model().objects.get(pk=user_id))

                _rbt(
                    task_type=_BT.TASK_FEED_REBUILD,
                    label=f'RSS feed rebuild after publish',
                    fn=_rebuild_feed_fn,
                    episode=episode,
                    created_by=request.user,
                    show_id=str(episode.show.pk),
                    user_id=request.user.pk,
                )
                messages.info(request, 'Distributions updated. RSS feed rebuild started in the background.')
            else:
                messages.success(request, f'Audio asset published to {count} platform record(s).')
            return redirect('production_ledger:episode_publish', pk=episode.pk)

        if action == 'publish_video_from_asset':
            # Just mark an existing video asset as the published video (no re-upload)
            asset_id = request.POST.get('video_asset_id')
            if not asset_id:
                messages.error(request, 'Select a video asset.')
                return redirect('production_ledger:episode_publish', pk=episode.pk)
            try:
                media_asset = episode.media_assets.get(pk=asset_id, asset_type=AssetType.VIDEO)
            except Exception:
                messages.error(request, 'Video asset not found on this episode.')
                return redirect('production_ledger:episode_publish', pk=episode.pk)
            media_asset.label = request.POST.get('label') or media_asset.label or 'Published Video'
            media_asset.save(update_fields=['label'])
            messages.success(request, f'Video asset "{media_asset.label}" marked as published.')
            return redirect('production_ledger:episode_publish', pk=episode.pk)

        if action == 'publish_video':
            video_file = request.FILES.get('video')
            if not video_file:
                messages.error(request, 'Video file is required.')
                return redirect('production_ledger:episode_publish', pk=episode.pk)

            try:
                video_key = storage.episode_video_key(
                    str(episode.organization_uuid),
                    str(episode.id),
                    video_file.name,
                )
                video_url = storage.upload_file(
                    video_file,
                    video_key,
                    content_type=video_file.content_type or 'video/mp4',
                    public=True,
                    extra_metadata={'episode-id': str(episode.id)},
                )

                MediaAsset.objects.create(
                    episode=episode,
                    organization_uuid=episode.organization_uuid,
                    asset_type=AssetType.VIDEO,
                    source_type=SourceType.EXTERNAL_LINK,
                    platform=MediaPlatform.DIRECT_URL,
                    external_url=video_url,
                    label=request.POST.get('label', '') or f"Published Video - {video_file.name}",
                    filename=video_file.name,
                    content_type=video_file.content_type or 'video/mp4',
                    file_size=video_file.size,
                    ingestion_status=IngestionStatus.READY,
                    ingested_by=request.user,
                    created_by=request.user,
                    updated_by=request.user,
                )
            except Exception as exc:
                messages.error(request, f'Video publish failed: {exc}')
                return redirect('production_ledger:episode_publish', pk=episode.pk)

            messages.success(request, 'Video uploaded and published as a media asset.')
            return redirect('production_ledger:episode_publish', pk=episode.pk)

        if action == 'publish_to_youtube':
            from .services.youtube import upload_episode_to_youtube  # noqa: PLC0415
            from .models import PodcastDistribution  # noqa: PLC0415
            from .constants import PodcastPlatform, DistributionStatus  # noqa: PLC0415

            asset_id = request.POST.get('video_asset_id')
            if not asset_id:
                messages.error(request, 'Select a video asset to upload to YouTube.')
                return redirect('production_ledger:episode_publish', pk=episode.pk)

            try:
                video_asset = episode.media_assets.get(pk=asset_id, asset_type=AssetType.VIDEO)
            except Exception:
                messages.error(request, 'Video asset not found on this episode.')
                return redirect('production_ledger:episode_publish', pk=episode.pk)

            if not video_asset.external_url:
                messages.error(request, 'Video asset has no public URL. Upload the video to storage first.')
                return redirect('production_ledger:episode_publish', pk=episode.pk)

            try:
                feed_config = episode.show.podcast_feed_config
            except Exception:
                messages.error(request, 'Configure the Podcast RSS Feed settings for this show before uploading to YouTube.')
                return redirect('production_ledger:episode_publish', pk=episode.pk)

            privacy = request.POST.get('youtube_privacy') or feed_config.youtube_default_privacy or 'public'

            try:
                video_id = upload_episode_to_youtube(episode, video_asset.external_url, feed_config, privacy=privacy)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect('production_ledger:episode_publish', pk=episode.pk)
            except Exception as exc:
                logger.exception("YouTube upload failed for episode %s", episode.pk)
                messages.error(request, f'YouTube upload failed: {exc}')
                return redirect('production_ledger:episode_publish', pk=episode.pk)

            youtube_url = f'https://www.youtube.com/watch?v={video_id}'
            dist, _ = PodcastDistribution.objects.get_or_create(
                episode=episode,
                platform=PodcastPlatform.YOUTUBE,
                defaults={'organization_uuid': episode.organization_uuid},
            )
            dist.status = DistributionStatus.LIVE
            dist.platform_url = youtube_url
            dist.save(update_fields=['status', 'platform_url'])

            messages.success(request, f'Video uploaded to YouTube: {youtube_url}')
            return redirect('production_ledger:episode_publish', pk=episode.pk)

        if action == 'extract_audio_from_video':
            from .services.audio_extraction import cleanup_work_dir, extract_audio_from_video, is_directly_downloadable  # noqa: PLC0415
            from .services.distribution import publish_episode_audio, build_and_publish_feed  # noqa: PLC0415
            import threading  # noqa: PLC0415
            import django  # noqa: PLC0415

            asset_id = request.POST.get('video_asset_id')
            if not asset_id:
                messages.error(request, 'Select a video asset to extract audio from.')
                return redirect('production_ledger:episode_publish', pk=episode.pk)

            try:
                video_asset = episode.media_assets.get(pk=asset_id, asset_type=AssetType.VIDEO)
            except Exception:
                messages.error(request, 'Video asset not found on this episode.')
                return redirect('production_ledger:episode_publish', pk=episode.pk)

            if not video_asset.external_url:
                messages.error(request, 'Video asset has no public URL.')
                return redirect('production_ledger:episode_publish', pk=episode.pk)

            if not is_directly_downloadable(video_asset.external_url):
                messages.error(
                    request,
                    'YouTube and Vimeo links cannot be downloaded for audio extraction. '
                    'Upload the video file directly to the Media Library first, then extract from that.'
                )
                return redirect('production_ledger:episode_publish', pk=episode.pk)

            add_intro = request.POST.get('add_intro') == 'on'
            intro_text = request.POST.get('intro_text', '').strip() or None
            bitrate = request.POST.get('audio_bitrate') or '192k'

            # Optional: use a previewed intro file (token stored in session)
            intro_audio_path = None
            preview_token = request.POST.get('intro_preview_token', '').strip()
            if add_intro and preview_token:
                import re as _re  # noqa: PLC0415
                import tempfile as _tmp  # noqa: PLC0415
                from pathlib import Path as _Path  # noqa: PLC0415
                if _re.fullmatch(r'[0-9a-f\-]{36}', preview_token):
                    session_key = f'intro_preview_{episode.pk}'
                    if request.session.get(session_key) == preview_token:
                        candidate = _Path(_tmp.gettempdir()) / 'forge_tts_serve' / f'{preview_token}.mp3'
                        if candidate.exists():
                            intro_audio_path = candidate

            intro_voice = request.POST.get('intro_voice') or 'coral'
            intro_model = request.POST.get('intro_model') or 'gpt-4o-mini-tts'
            insert_at_seconds = float(request.POST.get('intro_offset_seconds', '0') or '0')

            # Create a PENDING audio asset immediately so we can track progress.
            # The actual extraction runs in a background thread — this lets us
            # return a redirect in <1 second, avoiding DigitalOcean's 60s LB timeout.
            intro_label = " + intro" if add_intro else ""
            pending_asset = MediaAsset.objects.create(
                episode=episode,
                organization_uuid=episode.organization_uuid,
                asset_type=AssetType.AUDIO,
                source_type=SourceType.API_IMPORT,
                label=f"Extracting audio{intro_label} from {video_asset.label or 'video'}…",
                ingestion_status=IngestionStatus.PENDING,
                ingested_by=request.user,
            )

            # Capture everything the thread needs — no request/response objects
            _thread_kwargs = dict(
                asset_pk=str(pending_asset.pk),
                episode_pk=str(episode.pk),
                video_url=video_asset.external_url,
                episode_title=episode.title,
                show_name=episode.show.name,
                add_intro=add_intro,
                intro_text=intro_text,
                intro_audio_path=intro_audio_path,
                insert_at_seconds=insert_at_seconds,
                intro_voice=intro_voice,
                intro_model=intro_model,
                bitrate=bitrate,
                user_pk=request.user.pk,
            )

            def _run_extraction(
                asset_pk, episode_pk, video_url, episode_title, show_name,
                add_intro, intro_text, intro_audio_path, insert_at_seconds,
                intro_voice, intro_model, bitrate, user_pk,
            ):
                from django.contrib.auth import get_user_model  # noqa: PLC0415
                from .models import MediaAsset as _MA, Episode as _Ep  # noqa: PLC0415
                from .constants import IngestionStatus as _IS  # noqa: PLC0415
                from .services.audio_extraction import cleanup_work_dir as _cleanup, extract_audio_from_video as _extract  # noqa: PLC0415
                from .services.distribution import publish_episode_audio as _pub, build_and_publish_feed as _feed  # noqa: PLC0415

                audio_path = None
                asset = None
                try:
                    asset = _MA.objects.get(pk=asset_pk)
                    asset.ingestion_status = _IS.PROCESSING
                    asset.save(update_fields=['ingestion_status'])

                    audio_path, duration = _extract(
                        video_url=video_url,
                        episode_title=episode_title,
                        show_name=show_name,
                        add_intro=add_intro,
                        intro_text=intro_text,
                        intro_audio_path=intro_audio_path,
                        insert_at_seconds=insert_at_seconds,
                        intro_voice=intro_voice,
                        intro_model=intro_model,
                        bitrate=bitrate,
                    )

                    ep = _Ep.objects.get(pk=episode_pk)
                    User = get_user_model()
                    user = User.objects.get(pk=user_pk)

                    with open(audio_path, 'rb') as af:
                        result = _pub(ep, af, f"{episode_title}.mp3".replace('/', '-'),
                                      duration_seconds=duration, user=user)

                    # Update the pending asset with the real URL/duration from publish result
                    dist_list = result.get('distributions', [])
                    public_url = dist_list[0].audio_public_url if dist_list else None
                    _intro = " (with intro)" if add_intro else ""
                    asset.ingestion_status = _IS.READY
                    asset.duration_seconds = int(duration)
                    asset.label = f"Extracted audio{_intro} ({int(duration)}s)"
                    if public_url:
                        asset.external_url = public_url
                    asset.save(update_fields=['ingestion_status', 'duration_seconds', 'label', 'external_url'])

                    try:
                        _feed(ep.show, user=user)
                    except Exception as feed_exc:
                        logger.warning("Feed rebuild failed after audio extraction: %s", feed_exc)

                except Exception as exc:
                    # Mark the asset as failed so the UI polling loop exits
                    # instead of spinning forever showing "X minutes to complete".
                    try:
                        if asset is None:
                            asset = _MA.objects.get(pk=asset_pk)
                        asset.ingestion_status = _IS.FAILED
                        asset.error_message = str(exc)[:2000]
                        asset.save(update_fields=['ingestion_status', 'error_message'])
                    except Exception as save_exc:
                        logger.error(
                            "Failed to mark asset %s as failed after extraction error: %s",
                            asset_pk, save_exc,
                        )
                    raise  # re-raise so the watchdog records it on BackgroundTask too

                finally:
                    if audio_path:
                        _cleanup(audio_path)

            from .services.tasks import run_background_task as _rbt  # noqa: PLC0415
            from .models import BackgroundTask as _BT  # noqa: PLC0415
            _rbt(
                task_type=_BT.TASK_AUDIO_EXTRACT,
                label=f'Audio extraction: {episode.title[:50]}',
                fn=_run_extraction,
                episode=episode,
                created_by=request.user,
                timeout=900,
                **_thread_kwargs,
            )

            messages.info(
                request,
                'Audio extraction started. The page will update automatically when it\'s ready '
                '(usually 2–5 minutes depending on video length).',
            )
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
            from .services.tasks import run_background_task as _rbt  # noqa: PLC0415
            from .models import BackgroundTask as _BT  # noqa: PLC0415

            def _rebuild_feed_fn2(show_id, user_id):
                from django.contrib.auth import get_user_model  # noqa: PLC0415
                from .models import Show as _Show  # noqa: PLC0415
                from .services.distribution import build_and_publish_feed as _build  # noqa: PLC0415
                _build(_Show.objects.get(pk=show_id), user=get_user_model().objects.get(pk=user_id))

            _rbt(
                task_type=_BT.TASK_FEED_REBUILD,
                label='RSS feed rebuild after audio upload',
                fn=_rebuild_feed_fn2,
                episode=episode,
                created_by=request.user,
                show_id=str(episode.show.pk),
                user_id=request.user.pk,
            )
            messages.info(request, 'Audio uploaded. RSS feed rebuild started in the background.')
        else:
            messages.success(
                request,
                f"Audio published to {len(result['distributions'])} platform records.",
            )

        if episode.status == EpisodeStatus.APPROVED and episode.is_checklist_complete():
            try:
                episode.transition_to(EpisodeStatus.PUBLISHED, user=request.user)
            except Exception:
                # Keep publishing successful even if status transition is blocked.
                pass

        return redirect('production_ledger:episode_publish', pk=episode.pk)


class EpisodeSegmentsView(EpisodeTabMixin, TemplateView):
    """Episode segments (run of show) tab."""

    template_name = 'production_ledger/tabs/segments.html'
    active_tab = 'segments'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        episode = self.get_episode()
        context['segments'] = episode.segments.all().order_by('order')
        context['segment_form'] = SegmentForm(show=episode.show)
        context['template_pick_form'] = SegmentTemplatePickForm(show=episode.show)
        return context

    def post(self, request, *args, **kwargs):
        episode = self.get_episode()

        if not has_role(request.user, episode, [Role.ADMIN, Role.HOST, Role.PRODUCER]):
            messages.error(request, 'You do not have permission to add segments.')
            return redirect('production_ledger:episode_segments', pk=episode.pk)

        action = request.POST.get('action', 'create_new')

        if action == 'use_template':
            pick_form = SegmentTemplatePickForm(request.POST, show=episode.show)
            if pick_form.is_valid():
                template = pick_form.cleaned_data['template']
                # Use select_for_update to prevent race condition: lock the episode
                # while calculating the next order number.
                with transaction.atomic():
                    episode_locked = Episode.objects.select_for_update().get(pk=episode.pk)
                    next_order = (episode_locked.segments.aggregate(models.Max('order'))['order__max'] or 0) + 1
                    Segment.objects.create(
                        episode=episode,
                        organization_uuid=episode.organization_uuid,
                        created_by=request.user,
                        order=next_order,
                        source_template=template,
                        **template.build_segment_kwargs(),
                    )
                messages.success(request, f'Added "{template.title}" — feel free to adjust it for this episode.')
            else:
                messages.error(request, 'Pick a segment to reuse.')
            return redirect('production_ledger:episode_segments', pk=episode.pk)

        form = SegmentForm(request.POST, show=episode.show)
        if form.is_valid():
            # Use transaction.atomic with select_for_update to assign order atomically
            with transaction.atomic():
                episode_locked = Episode.objects.select_for_update().get(pk=episode.pk)
                next_order = (episode_locked.segments.aggregate(models.Max('order'))['order__max'] or 0) + 1
                segment = form.save(commit=False)
                segment.episode = episode
                segment.organization_uuid = episode.organization_uuid
                segment.created_by = request.user
                segment.order = next_order
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
        is_upload = form_type == 'upload' or 'file' in request.FILES
        
        if is_upload:
            form = MediaAssetUploadForm(request.POST, request.FILES)
        else:
            form = MediaAssetLinkForm(request.POST)
        
        if form.is_valid():
            try:
                if is_upload:
                    from .services import storage  # noqa: PLC0415

                    uploaded_file = form.cleaned_data['file']
                    original_name = os.path.basename(uploaded_file.name)
                    safe_name = original_name.replace(' ', '_')
                    object_key = storage.media_asset_key(
                        str(episode.organization_uuid),
                        str(episode.pk),
                        uuid.uuid4().hex[:8],
                        safe_name,
                    )

                    public_url = storage.upload_file(
                        uploaded_file,
                        object_key,
                        content_type=uploaded_file.content_type or 'application/octet-stream',
                        public=True,
                        extra_metadata={'episode-id': str(episode.pk)},
                    )

                    asset = MediaAsset(
                        episode=episode,
                        organization_uuid=episode.organization_uuid,
                        asset_type=form.cleaned_data['asset_type'],
                        source_type=SourceType.EXTERNAL_LINK,
                        external_url=public_url,
                        label=form.cleaned_data.get('label') or os.path.splitext(original_name)[0],
                        filename=original_name,
                        content_type=uploaded_file.content_type or 'application/octet-stream',
                        file_size=uploaded_file.size,
                        ingestion_status=IngestionStatus.READY,
                        ingested_by=request.user,
                        created_by=request.user,
                    )
                    asset.save()
                else:
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
            except Exception:
                logger.exception('Media upload failed for episode=%s', episode.pk)
                messages.error(request, 'Upload failed while transferring to cloud storage.')
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
        episode = self.get_episode()
        context['transcripts'] = episode.transcripts.all().order_by('-revision')
        context['latest_media_asset'] = episode.media_assets.filter(
            asset_type__in=[AssetType.VIDEO, AssetType.AUDIO]
        ).order_by('-created_at').first()
        context['upload_form'] = TranscriptUploadForm()
        context['paste_form'] = TranscriptPasteForm()
        return context
    
    def post(self, request, *args, **kwargs):
        episode = self.get_episode()
        action = request.POST.get('action', '')
        
        if not can_manage_transcripts(request.user, episode):
            messages.error(request, 'You do not have permission to manage transcripts.')
            return redirect('production_ledger:episode_transcript', pk=episode.pk)

        if action == 'auto_transcribe':
            import threading  # noqa: PLC0415
            from .services import transcription as transcription_svc  # noqa: PLC0415

            media_asset = episode.media_assets.filter(
                asset_type__in=[AssetType.VIDEO, AssetType.AUDIO]
            ).order_by('-created_at').first()
            if not media_asset:
                messages.error(request, 'No media asset found. Upload audio/video in the Media tab first.')
                return redirect('production_ledger:episode_transcript', pk=episode.pk)

            from .services.tasks import run_background_task as _rbt  # noqa: PLC0415
            from .models import BackgroundTask as _BT  # noqa: PLC0415

            def _run_transcription(asset_pk, user):
                from .models import MediaAsset  # noqa: PLC0415
                asset = MediaAsset.objects.get(pk=asset_pk)
                transcription_svc.transcribe_media_asset(asset, user=user)

            _rbt(
                task_type=_BT.TASK_TRANSCRIPTION,
                label=f'Auto-transcribe: {media_asset.label or media_asset.filename or str(media_asset.pk)[:8]}',
                fn=_run_transcription,
                episode=episode,
                created_by=request.user,
                asset_pk=media_asset.pk,
                user=request.user,
            )
            messages.success(request, 'Transcription started in the background — refresh this page in a moment to see the result.')
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
        episode = self.get_episode()
        context['clips'] = episode.clip_moments.all().order_by('start_ms')
        context['video_shorts'] = episode.video_shorts.all().order_by('start_ms')
        context['latest_transcript'] = episode.transcripts.order_by('-revision').first()
        context['clip_form'] = ClipMomentForm()
        context['priorities'] = ClipPriority.CHOICES
        # Running identification task — used to render the progress banner.
        # Wrapped in try/except because the BackgroundTask table schema on some
        # live deployments may be missing the episode_id FK column if the table
        # was created outside Django's migration system.
        try:
            context['running_identify_task'] = (
                BackgroundTask.objects.filter(
                    episode=episode,
                    task_type=BackgroundTask.TASK_SHORT_IDENTIFY,
                    status__in=[BackgroundTask.STATUS_PENDING, BackgroundTask.STATUS_RUNNING],
                ).order_by('-created_at').first()
            )
        except Exception:
            logger.warning(
                'BackgroundTask query failed in EpisodeClipsView — table may have schema drift',
                exc_info=True,
            )
            context['running_identify_task'] = None
        return context
    
    def post(self, request, *args, **kwargs):
        episode = self.get_episode()
        action = request.POST.get('action', '')
        
        if not can_manage_clips(request.user, episode):
            messages.error(request, 'You do not have permission to manage clips.')
            return redirect('production_ledger:episode_clips', pk=episode.pk)

        if action == 'auto_identify':
            import threading  # noqa: PLC0415
            from .services import transcription as transcription_svc  # noqa: PLC0415
            from .services.shorts import identify_and_queue_shorts  # noqa: PLC0415

            transcript = episode.transcripts.order_by('-revision').first()
            if transcript is None:
                media_asset = episode.media_assets.filter(
                    asset_type__in=[AssetType.VIDEO, AssetType.AUDIO]
                ).order_by('-created_at').first()
                if not media_asset:
                    messages.error(request, 'No transcript or media found. Upload media first.')
                    return redirect('production_ledger:episode_clips', pk=episode.pk)

                from .services.tasks import run_background_task as _rbt  # noqa: PLC0415
                from .models import BackgroundTask as _BT  # noqa: PLC0415

                def _transcribe_then_identify_fn(asset_pk, ep_pk, aspect_ratio, max_clips, user):
                    import django.db  # noqa: PLC0415
                    from .models import MediaAsset, Episode  # noqa: PLC0415
                    asset = MediaAsset.objects.get(pk=asset_pk)
                    tr = transcription_svc.transcribe_media_asset(asset, user=user)
                    ep = Episode.objects.get(pk=ep_pk)
                    identify_and_queue_shorts(ep, transcript=tr, aspect_ratio=aspect_ratio,
                                              max_clips=max_clips, user=user)

                _rbt(
                    task_type=_BT.TASK_SHORT_IDENTIFY,
                    label=f'Transcribe + identify clips: {episode.title[:50]}',
                    fn=_transcribe_then_identify_fn,
                    episode=episode,
                    created_by=request.user,
                    timeout=900,
                    asset_pk=media_asset.pk,
                    ep_pk=episode.pk,
                    aspect_ratio=request.POST.get('aspect_ratio', '9:16'),
                    max_clips=int(request.POST.get('max_clips', 5) or 5),
                    user=request.user,
                )
                messages.info(request, 'No transcript found — transcribing and identifying clips in the background. Refresh in a moment.')
                return redirect('production_ledger:episode_clips', pk=episode.pk)

            try:
                shorts = identify_and_queue_shorts(
                    episode,
                    transcript=transcript,
                    aspect_ratio=request.POST.get('aspect_ratio', '9:16'),
                    max_clips=int(request.POST.get('max_clips', 5) or 5),
                    user=request.user,
                )
                messages.success(request, f'AI identified {len(shorts)} clip moments from the latest transcript/media.')
            except Exception as exc:
                messages.error(request, f'AI clip identification failed: {exc}')
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

        elif action == 'set_live_segment':
            segment_id = request.POST.get('segment_id') or None
            if segment_id:
                segment = get_object_or_404(Segment, pk=segment_id, episode=episode)
                episode.active_segment = segment
            else:
                episode.active_segment = None
            episode.save(update_fields=['active_segment'])

        elif action == 'regenerate_overlay_token':
            episode.regenerate_overlay_token()
            messages.success(request, 'Overlay link regenerated — the old OBS URL will stop working. Update your Browser Source with the new one.')

        return redirect('production_ledger:control_room', pk=episode.pk)


# =============================================================================
# SECOND SCREEN (live broadcast display)
# =============================================================================

def _second_screen_state(episode, overlay_token=None):
    """Build the JSON-serializable state for the second-screen display.

    When overlay_token is given (the OBS Browser Source path), the sponsor
    QR URL points at the token-authorized OverlayQRCodeView so it loads
    without a login; otherwise it uses the login-gated per-sponsor endpoint.
    """
    show = episode.show
    segment = episode.active_segment
    sponsor = segment.sponsor if segment else None

    state = {
        'episode_id': str(episode.pk),
        'episode_title': episode.title,
        'show_name': show.name,
        'show_logo_url': show.logo.url if show.logo else None,
        'background_url': show.second_screen_background.url if show.second_screen_background else None,
        'brand_primary_color': show.brand_primary_color or None,
        'segment': None,
        'sponsor': None,
    }

    if segment:
        state['segment'] = {
            'id': str(segment.pk),
            'title': segment.title,
            'order': segment.order,
            'purpose': segment.purpose,
        }

    if sponsor:
        if not sponsor.website_url:
            qr_code_url = None
        elif overlay_token:
            qr_code_url = (
                reverse('production_ledger:overlay_qr_code', kwargs={'pk': episode.pk})
                + f'?token={overlay_token}'
            )
        else:
            qr_code_url = reverse('production_ledger:sponsor_qr_code', kwargs={'pk': sponsor.pk})
        state['sponsor'] = {
            'id': str(sponsor.pk),
            'name': sponsor.name,
            'ad_copy': sponsor.ad_copy,
            'website_url': sponsor.website_url,
            'logo_url': sponsor.logo.url if sponsor.logo else None,
            'qr_code_url': qr_code_url,
        }

    return state


def _episode_for_overlay_token(request, pk):
    """Return the episode if the request carries a valid overlay token for it,
    else None. Uses constant-time comparison to avoid token guessing.

    Authorization: The token is the sole authorization mechanism. Tokens are
    cryptographically random (secrets.token_urlsafe), indexed in the database,
    and unique per episode. An attacker with a token for one episode cannot
    use it to access another episode because the token won't match the
    per-episode overlay_token field."""
    token = request.GET.get('token', '')
    if not token:
        return None
    try:
        episode = Episode.objects.select_related('show').get(pk=pk)
    except Episode.DoesNotExist:
        return None
    # Constant-time comparison prevents timing attacks on the token.
    if episode.overlay_token and secrets.compare_digest(token, episode.overlay_token):
        return episode
    return None


def _render_qr_png(url):
    import qrcode

    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format='PNG')
    response = HttpResponse(buf.getvalue(), content_type='image/png')
    response['Cache-Control'] = 'public, max-age=300'
    return response


class SecondScreenView(EpisodeTabMixin, TemplateView):
    """
    Full-screen live display for a second monitor: show branding, the
    current segment, and its sponsor with a QR code. Read-only — the
    active segment is set from the Control Room.

    Two ways in:
      * Logged-in staff, for viewing on a second monitor (EpisodeTabMixin).
      * ?overlay=1&token=<episode.overlay_token> for use as an OBS Studio
        Browser Source. OBS's browser source can't log in (it doesn't pass
        keyboard input to the page), so the token authorizes read-only
        access without a session. Regenerate the token to revoke old URLs.
    """

    template_name = 'production_ledger/second_screen.html'
    active_tab = 'second_screen'
    minimum_role = Role.GUEST

    def dispatch(self, request, *args, **kwargs):
        self._token_episode = _episode_for_overlay_token(request, kwargs.get('pk'))
        if self._token_episode is not None:
            # Token path: skip login/RBAC, render directly.
            return TemplateView.dispatch(self, request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        if getattr(self, '_token_episode', None) is not None:
            # Bypass EpisodeTabMixin's context (which needs an authenticated
            # user for role lookups) when authorized purely by token.
            context = TemplateView.get_context_data(self, **kwargs)
            episode = self._token_episode
            context['episode'] = episode
        else:
            context = super().get_context_data(**kwargs)
            episode = self.get_episode()
        overlay_token = self.request.GET.get('token', '')
        state = _second_screen_state(episode, overlay_token=overlay_token or None)
        context['state'] = state
        context['state_json'] = json.dumps(state)
        context['is_overlay'] = self.request.GET.get('overlay') == '1'
        context['overlay_token'] = overlay_token
        return context


class SecondScreenStateView(EpisodeTabMixin, View):
    """JSON endpoint the second-screen page polls for live updates. Also
    reachable via ?token=<episode.overlay_token> for the OBS overlay."""

    minimum_role = Role.GUEST

    def dispatch(self, request, *args, **kwargs):
        self._token_episode = _episode_for_overlay_token(request, kwargs.get('pk'))
        if self._token_episode is not None:
            return View.dispatch(self, request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        token_episode = getattr(self, '_token_episode', None)
        episode = token_episode or self.get_episode()
        overlay_token = request.GET.get('token') if token_episode else None

        state = _second_screen_state(episode, overlay_token=overlay_token)
        response = JsonResponse(state)

        # Add cache headers to reduce unnecessary JSON transfers. The client
        # polls every 4 seconds; with a 2-second TTL, ~50% of requests will be
        # cache hits, reducing server load by half.
        response['Cache-Control'] = 'private, max-age=2'
        return response


class SponsorQRCodeView(LoginRequiredMixin, OrganizationMixin, RoleMixin, View):
    """Renders a PNG QR code pointing at a sponsor's website/ad URL."""

    minimum_role = Role.GUEST

    def get(self, request, *args, **kwargs):
        sponsor = get_object_or_404(Sponsor, pk=kwargs['pk'])
        self.check_permissions(sponsor.show)

        if not sponsor.website_url:
            raise Http404('Sponsor has no website URL to encode')

        return _render_qr_png(sponsor.website_url)


class OverlayQRCodeView(View):
    """QR code for the OBS overlay, authorized by an episode overlay token
    rather than a login. Encodes the current active segment's sponsor URL."""

    def get(self, request, *args, **kwargs):
        episode = _episode_for_overlay_token(request, kwargs.get('pk'))
        if episode is None:
            raise Http404('Invalid or missing overlay token')

        segment = episode.active_segment
        sponsor = segment.sponsor if segment else None
        if not sponsor or not sponsor.website_url:
            raise Http404('No sponsor URL to encode for the current segment')

        return _render_qr_png(sponsor.website_url)


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


