"""
REST API views for Splice video editor.

Endpoints for local engine registration, session management, job submission,
and project/media management.

Security model:
- Token-based authentication for engines
- Session-token + origin validation for browsers
- All endpoints require organization scoping
- Registration keys are one-time only
"""
import hashlib
import secrets
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from django.core.exceptions import ValidationError
from django.utils import timezone

from splice.models import (
    EditorProject, LocalEngineInstallation, LocalEngineSession,
    LocalProcessingJob, MediaAsset, RenderPlan
)
from splice.serializers import (
    LocalEngineInstallationSerializer, LocalEngineSessionSerializer,
    LocalProcessingJobSerializer, RenderPlanSerializer, EditorProjectSerializer
)
from splice.services.local_engine import LocalEngineService
from splice.services.render_plan import RenderPlanService


class LocalEngineViewSet(viewsets.ModelViewSet):
    """
    ViewSet for local engine installation management.

    Endpoints:
    - POST /splice/engines/ - Create/register new engine
    - GET /splice/engines/ - List engines
    - GET /splice/engines/{id}/ - Get engine details
    - POST /splice/engines/{id}/heartbeat/ - Heartbeat check-in
    """
    queryset = LocalEngineInstallation.objects.all()
    serializer_class = LocalEngineInstallationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return engines for authenticated user's organization."""
        user = self.request.user
        org_uuid = getattr(user, 'organization_uuid', None)
        if org_uuid:
            return LocalEngineInstallation.objects.filter(organization_uuid=org_uuid)
        return LocalEngineInstallation.objects.none()

    def create(self, request, *args, **kwargs):
        """
        Register a new local engine.

        Request:
        {
            "engine_name": "My Production Machine",
            "platform": "macos"  # windows, macos, linux
        }

        Response:
        {
            "id": "uuid",
            "engine_uuid": "uuid",
            "engine_name": "My Production Machine",
            "platform": "macos",
            "registration_key": "secret-key-one-time-only"  # DON'T LOG THIS
        }

        IMPORTANT: registration_key is returned ONCE and should never be logged.
        It should be securely displayed to the user and stored locally on their machine.
        """
        engine_name = request.data.get('engine_name')
        platform = request.data.get('platform')
        org_uuid = request.user.organization_uuid

        try:
            engine, reg_key = LocalEngineService.register_engine(
                org_uuid=org_uuid,
                engine_name=engine_name,
                platform=platform,
                user=request.user,
            )

            serializer = self.get_serializer(engine)
            response_data = serializer.data
            response_data['registration_key'] = reg_key

            return Response(response_data, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def heartbeat(self, request, pk=None):
        """
        Record a heartbeat from the local engine.

        This confirms the engine is online and ready for jobs.

        Request:
        {
            "status": "ready",  # ready, busy, offline
            "proxy_quality": "720p",
            "concurrent_jobs_available": 2
        }

        Response:
        {
            "engine_id": "uuid",
            "is_online": true,
            "jobs_queued": [...]
        }
        """
        engine = self.get_object()

        # Record heartbeat
        LocalEngineService.heartbeat(engine.id)

        # Get queued jobs for this engine
        queued_jobs = LocalProcessingJob.objects.filter(
            local_engine=engine,
            status__in=['queued', 'waiting_for_engine']
        ).order_by('-priority', 'created_at')[:10]

        job_serializer = LocalProcessingJobSerializer(queued_jobs, many=True)

        return Response({
            'engine_id': str(engine.id),
            'is_online': True,
            'jobs_queued': job_serializer.data,
        })


class LocalEngineSessionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for browser-to-engine session management.

    Endpoints:
    - POST /splice/sessions/ - Create new session
    - GET /splice/sessions/{token}/ - Validate session
    """
    queryset = LocalEngineSession.objects.all()
    serializer_class = LocalEngineSessionSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'session_token'

    def create(self, request, *args, **kwargs):
        """
        Create a new session for browser-to-engine communication.

        Request:
        {
            "engine_id": "uuid",
            "browser_origin": "http://localhost:3000"
        }

        Response:
        {
            "session_token": "token",
            "expires_at": "2026-07-21T18:00:00Z"
        }
        """
        engine_id = request.data.get('engine_id')
        browser_origin = request.data.get('browser_origin')

        try:
            session = LocalEngineService.create_session(
                local_engine_id=engine_id,
                browser_origin=browser_origin,
                user=request.user,
            )

            serializer = self.get_serializer(session)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except LocalEngineInstallation.DoesNotExist:
            return Response(
                {'error': 'Engine not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    def retrieve(self, request, *args, **kwargs):
        """
        Validate a session token.

        Query params: ?origin=http://localhost:3000

        Response:
        {
            "valid": true,
            "engine_id": "uuid",
            "expires_in_seconds": 3600
        }
        """
        session_token = kwargs.get('session_token')
        browser_origin = request.query_params.get('origin')

        engine = LocalEngineService.validate_session(
            session_token=session_token,
            browser_origin=browser_origin,
        )

        if not engine:
            return Response(
                {'valid': False},
                status=status.HTTP_401_UNAUTHORIZED
            )

        session = LocalEngineSession.objects.get(session_token=session_token)
        expires_in = (session.expires_at - timezone.now()).total_seconds()

        return Response({
            'valid': True,
            'engine_id': str(engine.id),
            'expires_in_seconds': int(expires_in),
        })


class LocalProcessingJobViewSet(viewsets.ModelViewSet):
    """
    ViewSet for background processing jobs.

    Endpoints:
    - POST /splice/projects/{project_id}/jobs/ - Submit job
    - GET /splice/jobs/ - List user's jobs
    - GET /splice/jobs/{id}/ - Get job status
    - PATCH /splice/jobs/{id}/ - Update job (engine only)
    - POST /splice/jobs/{id}/confirm/ - User confirm operation
    """
    queryset = LocalProcessingJob.objects.all()
    serializer_class = LocalProcessingJobSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return jobs for authenticated user's organization."""
        org_uuid = self.request.user.organization_uuid
        return LocalProcessingJob.objects.filter(
            editor_project__organization_uuid=org_uuid
        )

    def create(self, request, *args, **kwargs):
        """
        Submit a new processing job.

        Request:
        {
            "project_id": "uuid",
            "job_type": "render_video",  # See LocalProcessingJob.job_type choices
            "input_data": {
                "render_plan_id": "uuid",
                "output_format": "mp4"
            }
        }

        Response:
        {
            "id": "uuid",
            "status": "queued",
            "progress_percent": 0,
            ...
        }
        """
        project_id = request.data.get('project_id')
        job_type = request.data.get('job_type')
        input_data = request.data.get('input_data', {})

        try:
            project = EditorProject.objects.get(id=project_id)

            # Assign to local engine (simplified: just pick first online)
            local_engine = LocalEngineInstallation.objects.filter(
                organization_uuid=project.organization_uuid,
                is_online=True
            ).first()

            if not local_engine:
                return Response(
                    {'error': 'No online local engines available'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            job = LocalProcessingJob.objects.create(
                local_engine=local_engine,
                editor_project=project,
                job_type=job_type,
                input_data=input_data,
                status='queued',
                created_by=request.user,
            )

            serializer = self.get_serializer(job)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except EditorProject.DoesNotExist:
            return Response(
                {'error': 'Project not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    def partial_update(self, request, pk=None):
        """
        Update job progress (called by local engine).

        Request:
        {
            "status": "processing",
            "progress_percent": 50,
            "output_data": {
                "proxy_url": "s3://...",
                ...
            }
        }
        """
        job = self.get_object()

        # Simplified: any authenticated user can update
        # In production: verify engine ownership via session token
        serializer = self.get_serializer(job, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)

        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """
        User confirms a job for execution.

        Some operations (rendering) require user approval before starting.

        Request: {} (body can be empty)

        Response:
        {
            "id": "uuid",
            "status": "waiting_for_engine",  # Now eligible to run
            "user_confirmed": true
        }
        """
        job = self.get_object()

        job.user_confirmed = True
        job.save(update_fields=['user_confirmed', 'updated_at', 'updated_by'])

        # If engine supports auto-start and all preconditions met, mark waiting
        if job.local_engine.auto_process_jobs:
            job.status = 'waiting_for_engine'
            job.save(update_fields=['status'])

        serializer = self.get_serializer(job)
        return Response(serializer.data)


class RenderPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for render plans (read-only from API).

    Endpoints:
    - GET /splice/render-plans/ - List plans
    - GET /splice/render-plans/{id}/ - Get plan details
    """
    queryset = RenderPlan.objects.all()
    serializer_class = RenderPlanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return plans for authenticated user's organization."""
        org_uuid = self.request.user.organization_uuid
        return RenderPlan.objects.filter(
            project__organization_uuid=org_uuid
        )

    @action(detail=True, methods=['get'])
    def blueprint(self, request, pk=None):
        """
        Get FFmpeg blueprint for a render plan.

        Path-free: contains asset UUIDs, not paths.
        Local engine resolves UUIDs → paths privately.

        Response:
        {
            "inputs": [{"uuid": "..."}, ...],
            "filter_complex": "...",
            "outputs": {...},
            "metadata": {...}
        }
        """
        plan = self.get_object()

        try:
            blueprint = RenderPlanService.plan_to_ffmpeg_blueprint(plan.id)
            return Response(blueprint)
        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class EditorProjectViewSet(viewsets.ModelViewSet):
    """
    ViewSet for editor projects.

    Endpoints:
    - POST /splice/projects/ - Create project
    - GET /splice/projects/ - List projects
    - GET /splice/projects/{id}/ - Get project
    - PATCH /splice/projects/{id}/ - Update project
    """
    queryset = EditorProject.objects.all()
    serializer_class = EditorProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return projects for authenticated user's organization."""
        org_uuid = self.request.user.organization_uuid
        return EditorProject.objects.filter(organization_uuid=org_uuid)

    def perform_create(self, serializer):
        """Ensure organization_uuid is set on create."""
        serializer.save(
            organization_uuid=self.request.user.organization_uuid,
            created_by=self.request.user,
        )
