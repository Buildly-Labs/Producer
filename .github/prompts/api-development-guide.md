# API Development Guide for Buildly Services

## Overview

This guide provides specific standards for developing REST APIs in Buildly microservices. Follow these patterns to ensure API consistency across all Buildly services.

## API Design Principles

### 1. RESTful Design
- Use nouns for resource names (not verbs)
- Use HTTP methods appropriately (GET, POST, PUT, PATCH, DELETE)
- Maintain consistent URL structure
- Use proper HTTP status codes

### 2. Versioning Strategy
- Always version your APIs: `/api/v1/`
- Use semantic versioning for major changes
- Maintain backward compatibility when possible
- Document version deprecation policies

### 3. Resource Naming Conventions
```
Good:
/api/v1/entities/
/api/v1/entities/123/
/api/v1/entities/123/relationships/

Avoid:
/api/v1/getEntities/
/api/v1/entity-data/
/api/v1/EntityList/
```

## Standard API Patterns

### 1. List Resources
```http
GET /api/v1/entities/
```

**Response Structure:**
```json
{
    "count": 100,
    "next": "http://example.com/api/v1/entities/?page=2",
    "previous": null,
    "results": [
        {
            "id": 1,
            "name": "Entity Name",
            "description": "Entity Description",
            "is_active": true,
            "created_at": "2025-11-03T10:00:00Z",
            "updated_at": "2025-11-03T10:00:00Z"
        }
    ]
}
```

### 2. Retrieve Single Resource
```http
GET /api/v1/entities/123/
```

**Response Structure:**
```json
{
    "id": 123,
    "name": "Entity Name",
    "description": "Entity Description",
    "is_active": true,
    "created_at": "2025-11-03T10:00:00Z",
    "updated_at": "2025-11-03T10:00:00Z"
}
```

### 3. Create Resource
```http
POST /api/v1/entities/
Content-Type: application/json

{
    "name": "New Entity",
    "description": "New entity description",
    "is_active": true
}
```

**Success Response (201 Created):**
```json
{
    "id": 124,
    "name": "New Entity",
    "description": "New entity description",
    "is_active": true,
    "created_at": "2025-11-03T10:30:00Z",
    "updated_at": "2025-11-03T10:30:00Z"
}
```

### 4. Update Resource (Full)
```http
PUT /api/v1/entities/123/
Content-Type: application/json

{
    "name": "Updated Entity",
    "description": "Updated description",
    "is_active": false
}
```

### 5. Update Resource (Partial)
```http
PATCH /api/v1/entities/123/
Content-Type: application/json

{
    "is_active": false
}
```

### 6. Delete Resource
```http
DELETE /api/v1/entities/123/
```

**Success Response (204 No Content):**
```
(Empty response body)
```

## Filtering and Searching

### 1. Query Parameters
```http
GET /api/v1/entities/?is_active=true&created_by=123
GET /api/v1/entities/?search=entity+name
GET /api/v1/entities/?ordering=-created_at
```

### 2. Django Filter Implementation
```python
class LogicEntityViewSet(viewsets.ModelViewSet):
    queryset = LogicEntity.objects.all()
    serializer_class = LogicEntitySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'created_by']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-created_at']
```

## Custom Actions

### 1. Collection Actions (no specific resource)
```python
@action(detail=False, methods=['get'])
def active(self, request):
    """Get only active entities"""
    active_entities = self.queryset.filter(is_active=True)
    serializer = self.get_serializer(active_entities, many=True)
    return Response(serializer.data)
```

**Usage:**
```http
GET /api/v1/entities/active/
```

### 2. Member Actions (specific resource)
```python
@action(detail=True, methods=['post'])
def activate(self, request, pk=None):
    """Activate a specific entity"""
    entity = self.get_object()
    entity.is_active = True
    entity.save()
    return Response({'status': 'activated'})
```

**Usage:**
```http
POST /api/v1/entities/123/activate/
```

## Error Handling

### 1. Standard Error Format
```json
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Invalid input data",
        "details": {
            "name": ["This field is required."],
            "description": ["Ensure this value has at most 500 characters."]
        }
    }
}
```

### 2. HTTP Status Codes
- `200 OK` - Successful GET, PUT, PATCH
- `201 Created` - Successful POST
- `204 No Content` - Successful DELETE
- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Authentication required
- `403 Forbidden` - Permission denied
- `404 Not Found` - Resource not found
- `409 Conflict` - Resource conflict
- `422 Unprocessable Entity` - Validation error
- `500 Internal Server Error` - Server error

### 3. Error Response Implementation
```python
from rest_framework.views import exception_handler
from rest_framework.response import Response

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    
    if response is not None:
        custom_response_data = {
            'error': {
                'code': exc.__class__.__name__.upper(),
                'message': str(exc),
                'details': response.data
            }
        }
        response.data = custom_response_data
    
    return response
```

## Authentication and Authorization

### 1. Token Authentication
```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}
```

### 2. Permission Classes
```python
from rest_framework.permissions import IsAuthenticated, AllowAny

class LogicEntityViewSet(viewsets.ModelViewSet):
    def get_permissions(self):
        """Set permissions based on action"""
        if self.action == 'list':
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        
        return [permission() for permission in permission_classes]
```

### 3. Custom Permissions
```python
from rest_framework import permissions

class IsOwnerOrReadOnly(permissions.BasePermission):
    """Custom permission to only allow owners to edit objects."""
    
    def has_object_permission(self, request, view, obj):
        # Read permissions for any request
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only to the owner
        return obj.created_by == request.user
```

## API Documentation

### 1. Swagger/OpenAPI Integration
```python
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

class LogicEntityViewSet(viewsets.ModelViewSet):
    @swagger_auto_schema(
        operation_description="List all entities with optional filtering",
        manual_parameters=[
            openapi.Parameter(
                'is_active', openapi.IN_QUERY,
                description="Filter by active status",
                type=openapi.TYPE_BOOLEAN
            ),
        ],
        responses={
            200: LogicEntitySerializer(many=True),
            400: "Bad Request"
        }
    )
    def list(self, request):
        return super().list(request)
```

### 2. Serializer Documentation
```python
class LogicEntitySerializer(serializers.ModelSerializer):
    """
    Serializer for LogicEntity model.
    
    Fields:
    - name: The entity name (required, max 255 characters)
    - description: Optional description text
    - is_active: Boolean flag for entity status
    """
    
    name = serializers.CharField(
        max_length=255,
        help_text="The name of the entity"
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional description of the entity"
    )
    
    class Meta:
        model = LogicEntity
        fields = ['id', 'name', 'description', 'is_active', 'created_at', 'updated_at']
```

## Pagination

### 1. Standard Pagination
```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20
}
```

### 2. Custom Pagination
```python
from rest_framework.pagination import PageNumberPagination

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
```

## Data Validation

### 1. Serializer Validation
```python
class LogicEntitySerializer(serializers.ModelSerializer):
    def validate_name(self, value):
        """Validate entity name"""
        if len(value) < 3:
            raise serializers.ValidationError(
                "Name must be at least 3 characters long."
            )
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        if data.get('is_active') and not data.get('description'):
            raise serializers.ValidationError(
                "Active entities must have a description."
            )
        return data
```

### 2. Custom Validators
```python
from django.core.exceptions import ValidationError

def validate_entity_name(value):
    """Custom validator for entity names"""
    if value.startswith('_'):
        raise ValidationError(
            "Entity names cannot start with underscore."
        )
```

## Performance Considerations

### 1. Query Optimization
```python
class LogicEntityViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        """Optimize queries with select_related and prefetch_related"""
        return LogicEntity.objects.select_related(
            'created_by'
        ).prefetch_related(
            'related_entities'
        )
```

### 2. Response Caching
```python
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

class LogicEntityViewSet(viewsets.ModelViewSet):
    @method_decorator(cache_page(60 * 15))  # Cache for 15 minutes
    def list(self, request):
        return super().list(request)
```

## Testing API Endpoints

### 1. Basic API Tests
```python
from rest_framework.test import APITestCase
from rest_framework import status

class LogicEntityAPITest(APITestCase):
    def test_create_entity(self):
        """Test creating a new entity"""
        url = '/api/v1/entities/'
        data = {
            'name': 'Test Entity',
            'description': 'Test description'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Test Entity')
```

### 2. Authentication Tests
```python
def test_authenticated_access(self):
    """Test that authenticated users can create entities"""
    self.client.force_authenticate(user=self.user)
    url = '/api/v1/entities/'
    data = {'name': 'Authenticated Entity'}
    response = self.client.post(url, data, format='json')
    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
```

## API Security Best Practices

### 1. Input Sanitization
- Always validate and sanitize input data
- Use Django's built-in validators
- Implement custom validation for business logic
- Prevent SQL injection with ORM queries

### 2. Rate Limiting
```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '1000/day'
    }
}
```

### 3. CORS Configuration
```python
# settings.py
CORS_ALLOWED_ORIGINS = [
    "https://example.com",
    "https://www.example.com",
]

# For development only
CORS_ALLOW_ALL_ORIGINS = True
```

## Questions to Clarify

When developing APIs, always ask about:
1. **Authentication requirements**: Which endpoints need authentication?
2. **Permission levels**: Who can perform which operations?
3. **Data validation rules**: What are the business rules for data?
4. **Response formats**: Are there specific format requirements?
5. **Performance requirements**: Expected load and response times?
6. **Integration needs**: How will this API be consumed by other services?
7. **Versioning strategy**: How should API changes be handled?

Remember: Always prioritize security, performance, and maintainability when designing APIs for Buildly services.