# Buildly Microservice Development Standards

## Overview

This document outlines the core standards for developing microservices that integrate with Buildly Core. All AI developers should follow these guidelines when building or modifying Buildly microservices.

## Core Architecture Principles

### 1. Django REST Framework Foundation
- Use Django REST Framework as the primary web framework
- Implement ViewSets for CRUD operations
- Use Django's built-in ORM for database interactions
- Follow Django project structure conventions

### 2. Service Structure
```
service_name/
├── manage.py
├── requirements.txt
├── requirements-dev.txt
├── requirements-prod.txt
├── docker-compose.yml
├── Dockerfile
├── logic/                  # Main app logic
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── admin.py
│   └── migrations/
├── service_name/           # Django project settings
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── production.py
│   ├── urls.py
│   └── wsgi.py
└── scripts/                # Utility scripts
    ├── docker-entrypoint.sh
    └── run-tests.sh
```

### 3. Required Dependencies
Always include these core dependencies:
- `Django>=5.1,<5.2`
- `djangorestframework`
- `drf-yasg` (for API documentation)
- `django-filter` (for filtering)
- `django-cors-headers` (for CORS support)

## API Standards

### 1. REST API Patterns
- Use standard HTTP methods (GET, POST, PUT, PATCH, DELETE)
- Implement consistent URL patterns: `/api/v1/resource/`
- Use proper HTTP status codes
- Return JSON responses with consistent structure

### 2. Authentication & Authorization
- Implement token-based authentication when required
- Use Django's permission system
- Support both authenticated and anonymous access as appropriate

### 3. API Documentation
- Use drf-yasg for automatic Swagger documentation
- Document all endpoints with proper descriptions
- Include request/response examples
- Maintain up-to-date API documentation

## Database Standards

### 1. Model Design
- Use Django's built-in model fields
- Implement proper relationships (ForeignKey, ManyToMany)
- Add appropriate indexes for performance
- Use migrations for all schema changes

### 2. Data Validation
- Implement validation at the serializer level
- Use Django's built-in validators when possible
- Create custom validators for business logic

## Docker & Deployment

### 1. Docker Configuration
- Multi-stage Docker builds for production
- Separate development and production configurations
- Use docker-compose for local development
- Include proper health checks

### 2. Environment Configuration
- Use environment variables for configuration
- Separate settings files (base, dev, production)
- Never commit sensitive data to version control

## Testing Standards

### 1. Test Coverage
- Minimum 80% test coverage
- Test all API endpoints
- Include unit tests for models and serializers
- Add integration tests for complex workflows

### 2. Test Structure
- Use Django's built-in test framework
- Organize tests in test modules
- Use factories for test data generation
- Mock external dependencies

## Code Quality

### 1. Code Style
- Follow PEP 8 Python style guide
- Use meaningful variable and function names
- Add docstrings to all classes and functions
- Keep functions small and focused

### 2. Error Handling
- Use proper exception handling
- Return appropriate HTTP status codes
- Provide meaningful error messages
- Log errors appropriately

## Security Best Practices

### 1. Input Validation
- Validate all input data
- Sanitize user input
- Use parameterized queries
- Implement rate limiting

### 2. Security Headers
- Enable CORS properly
- Use HTTPS in production
- Implement proper authentication
- Follow Django security best practices

## Integration with Buildly Core

### 1. Service Registration
- Services should be discoverable by Buildly Core
- Implement health check endpoints
- Follow naming conventions for service identification

### 2. Data Exchange
- Use consistent API patterns across all services
- Implement proper error handling for service communication
- Support both synchronous and asynchronous communication patterns

## Development Workflow

### 1. Version Control
- Use Git with meaningful commit messages
- Follow GitFlow branching strategy
- Create pull requests for all changes
- Include tests with all new features

### 2. Documentation
- Update API documentation with changes
- Maintain README files
- Document configuration changes
- Keep deployment instructions current

## Performance Guidelines

### 1. Database Optimization
- Use select_related and prefetch_related for queries
- Implement proper database indexes
- Monitor query performance
- Use pagination for large datasets

### 2. Caching Strategy
- Implement caching where appropriate
- Use Django's caching framework
- Cache expensive computations
- Consider Redis for session storage

## Monitoring and Logging

### 1. Logging
- Use Django's logging framework
- Log important events and errors
- Include request IDs for tracing
- Avoid logging sensitive information

### 2. Health Checks
- Implement health check endpoints
- Monitor service availability
- Include dependency checks
- Return proper status information

## Questions for Clarification

When implementing features, always ask about:
1. Authentication requirements for new endpoints
2. Data persistence needs and model relationships
3. Integration points with other Buildly services
4. Performance requirements and expected load
5. Specific business logic validation rules

Remember: When in doubt, follow Django best practices and ask for clarification rather than making assumptions.