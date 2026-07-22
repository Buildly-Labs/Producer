"""
URL routing for Splice REST API.

Routes for local engine registration, session management, job submission,
render plans, and project management.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from splice.views import (
    LocalEngineViewSet, LocalEngineSessionViewSet,
    LocalProcessingJobViewSet, RenderPlanViewSet,
    EditorProjectViewSet,
)

app_name = 'splice'

router = DefaultRouter()
router.register(r'engines', LocalEngineViewSet, basename='local-engine')
router.register(r'sessions', LocalEngineSessionViewSet, basename='local-engine-session')
router.register(r'jobs', LocalProcessingJobViewSet, basename='local-processing-job')
router.register(r'render-plans', RenderPlanViewSet, basename='render-plan')
router.register(r'projects', EditorProjectViewSet, basename='editor-project')

urlpatterns = [
    path('api/v1/', include(router.urls)),
]
