# Django Service Patterns for Buildly

## Overview

This document provides Django-specific implementation patterns for Buildly microservices. Follow these patterns to ensure consistency across all Buildly services.

## Models Pattern

### Base Model Structure
```python
from django.db import models
from django.contrib.auth.models import User

class BaseModel(models.Model):
    """Base model with common fields for all entities"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        abstract = True
```

### Entity Models
```python
class LogicEntity(BaseModel):
    """Example entity model following Buildly patterns"""
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Logic Entity"
        verbose_name_plural = "Logic Entities"
    
    def __str__(self):
        return self.name
```

## Serializers Pattern

### Base Serializer
```python
from rest_framework import serializers
from .models import LogicEntity

class BaseSerializer(serializers.ModelSerializer):
    """Base serializer with common behavior"""
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    
    class Meta:
        fields = ['id', 'created_at', 'updated_at']
```

### Entity Serializers
```python
class LogicEntitySerializer(BaseSerializer):
    """Serializer for LogicEntity with validation"""
    
    class Meta:
        model = LogicEntity
        fields = BaseSerializer.Meta.fields + [
            'name', 'description', 'is_active'
        ]
    
    def validate_name(self, value):
        """Custom validation for name field"""
        if len(value) < 3:
            raise serializers.ValidationError(
                "Name must be at least 3 characters long."
            )
        return value
```

## Views Pattern

### Base ViewSet
```python
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

class BaseViewSet(viewsets.ModelViewSet):
    """Base ViewSet with common functionality"""
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    def perform_create(self, serializer):
        """Set created_by field on creation"""
        if self.request.user.is_authenticated:
            serializer.save(created_by=self.request.user)
        else:
            serializer.save()
```

### Entity ViewSet
```python
class LogicEntityViewSet(BaseViewSet):
    """ViewSet for LogicEntity with custom actions"""
    queryset = LogicEntity.objects.all()
    serializer_class = LogicEntitySerializer
    filterset_fields = ['is_active', 'created_by']
    search_fields = ['name', 'description']
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get only active entities"""
        active_entities = self.queryset.filter(is_active=True)
        serializer = self.get_serializer(active_entities, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle active status of entity"""
        entity = self.get_object()
        entity.is_active = not entity.is_active
        entity.save()
        serializer = self.get_serializer(entity)
        return Response(serializer.data)
```

## URL Patterns

### Main URLs
```python
# logic_service/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

# API Documentation setup
schema_view = get_schema_view(
   openapi.Info(
      title="Logic Service API",
      default_version='v1',
      description="API documentation for Logic Service",
   ),
   public=True,
)

# API Router
router = DefaultRouter()

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('logic.urls')),
    path('docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
```

### App URLs
```python
# logic/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LogicEntityViewSet

router = DefaultRouter()
router.register(r'entities', LogicEntityViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
```

## Settings Pattern

### Base Settings
```python
# logic_service/settings/base.py
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'drf_yasg',
    'django_filters',
    'corsheaders',
]

LOCAL_APPS = [
    'logic',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'logic_service.urls'

# REST Framework configuration
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

# CORS settings
CORS_ALLOW_ALL_ORIGINS = True  # Only for development
```

### Development Settings
```python
# logic_service/settings/dev.py
from .base import *

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

# Development database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

# Development-specific CORS settings
CORS_ALLOW_ALL_ORIGINS = True
```

### Production Settings
```python
# logic_service/settings/production.py
from .base import *

DEBUG = False

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')

# Production database configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# Security settings for production
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
```

## Admin Configuration

### Model Admin
```python
# logic/admin.py
from django.contrib import admin
from .models import LogicEntity

@admin.register(LogicEntity)
class LogicEntityAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at', 'created_by']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )
```

## Testing Patterns

### Model Tests
```python
# logic/tests/test_models.py
from django.test import TestCase
from django.contrib.auth.models import User
from ..models import LogicEntity

class LogicEntityModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
    def test_entity_creation(self):
        entity = LogicEntity.objects.create(
            name='Test Entity',
            description='Test description',
            created_by=self.user
        )
        self.assertEqual(entity.name, 'Test Entity')
        self.assertTrue(entity.is_active)
        self.assertEqual(entity.created_by, self.user)
```

### API Tests
```python
# logic/tests/test_views.py
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth.models import User
from ..models import LogicEntity

class LogicEntityAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.entity = LogicEntity.objects.create(
            name='Test Entity',
            created_by=self.user
        )
        
    def test_get_entities(self):
        url = '/api/v1/entities/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
    def test_create_entity(self):
        url = '/api/v1/entities/'
        data = {
            'name': 'New Entity',
            'description': 'New description'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
```

## Docker Patterns

### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Run migrations and start server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

### Docker Compose
```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - .:/app
    environment:
      - DJANGO_SETTINGS_MODULE=logic_service.settings.dev
    depends_on:
      - db
      
  db:
    image: postgres:13
    environment:
      - POSTGRES_DB=logic_service
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

## Common Patterns to Follow

1. **Always use Django's built-in authentication and permissions**
2. **Implement proper error handling and logging**
3. **Use environment variables for configuration**
4. **Follow RESTful API conventions**
5. **Include comprehensive tests for all functionality**
6. **Document all API endpoints properly**
7. **Use consistent naming conventions throughout the codebase**

## Questions to Ask

When implementing Django patterns:
1. Should this endpoint require authentication?
2. What validation rules apply to this data?
3. How should this relate to other models?
4. What permissions are needed for this operation?
5. Should this action be logged or audited?