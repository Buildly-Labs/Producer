from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import path, include, re_path
from django.views.static import serve
from django.conf import settings

from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from .views import health_check
from production_ledger.views import LandingPageView

schema_view = get_schema_view(
    openapi.Info(
        title="Producer API",
        default_version='v1',
        description="Buildly Producer - Podcast & Media Production Platform. Includes Production Ledger for managing shows, episodes, transcripts, AI-assisted drafts, and publishing workflows.",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)


urlpatterns = [
    # Static files
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
    # Media files (local dev only; production uses DO Spaces)
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    
    # API Documentation
    re_path(r'^docs/swagger(?P<format>\.json|\.yaml)$',
            schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('docs/', schema_view.with_ui('swagger', cache_timeout=0),
         name='schema-swagger-ui'),
    
    # Authentication
    path('auth/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('auth/logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # Admin
    path('admin/', admin.site.urls),
    
    # Health check
    path('health_check/', view=health_check, name='health_check'),
    
    # Production Ledger - Main Application
    path('ledger/', include('production_ledger.urls')),
    path('api/', include('production_ledger.api_urls')),
    
    # Landing page (public)
    path('', LandingPageView.as_view(), name='home'),
]

# Add debug toolbar URLs in development
if settings.DEBUG:
    try:
        import debug_toolbar
        urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass

urlpatterns += staticfiles_urlpatterns()
