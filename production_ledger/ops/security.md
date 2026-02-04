# Security Considerations

## Overview

Production Ledger implements role-based access control (RBAC) with show-level permissions and organization-level data isolation.

## Multi-Tenancy

All data is scoped to organizations via `organization_uuid`:

- Every model includes `organization_uuid` as a required field
- All querysets are filtered by organization
- Users can only see data within their organization

**Implementation**: The `OrganizationMixin` in views automatically filters data.

## Role-Based Access Control (RBAC)

### Role Hierarchy

Roles are hierarchical (higher roles inherit all lower permissions):

1. **admin** - Full control over show and all episodes
2. **host** - Create/edit episodes, approve content, publish
3. **producer** - Manage episodes, segments, guests, generate AI
4. **editor** - Edit content, upload media, manage transcripts
5. **guest** - View own appearances, limited data access

### Role Assignment

Roles are assigned per-show via `ShowRoleAssignment`:

```python
ShowRoleAssignment.objects.create(
    show=show,
    user=user,
    role='producer',
    organization_uuid=org_uuid
)
```

### Episode Overrides

For specific episodes, roles can be elevated via `EpisodeRoleOverride`:

```python
EpisodeRoleOverride.objects.create(
    episode=episode,
    user=user,
    override_role='host'  # Temporarily elevate to host
)
```

### Permission Checks

Use the provided permission helpers:

```python
from production_ledger.permissions import (
    has_role,
    has_minimum_role,
    can_approve_artifact,
    can_finalize_show_notes
)

# Check exact role
if has_role(user, show, 'admin'):
    ...

# Check minimum role level
if has_minimum_role(user, show, 'producer'):
    ...

# Check specific permissions
if can_approve_artifact(user, episode):
    ...
```

### View Protection

Views use the `require_role` decorator:

```python
from production_ledger.permissions import require_role

@require_role('producer')
def my_view(request, episode):
    # Only accessible by producers and above
    ...
```

## AI Content Security

### Approval Gates

All AI-generated content requires explicit human approval:

- AI artifacts start with `approval_status='pending'`
- Only users with appropriate roles can approve/reject
- Approval records who approved and when
- Rejected content includes reason notes

### Provenance Tracking

AI artifacts track:

- Provider and model used
- Original prompt text
- Full output text
- Timestamps
- Approving user

## Data Integrity

### Checksums

Media assets compute SHA-256 checksums:

- Verifies file integrity
- Detects duplicate uploads
- Provides audit trail

### Audit Fields

All models include:

- `created_at` - Creation timestamp
- `updated_at` - Last modification timestamp
- `created_by` - User who created the record

### Status Transitions

Episode status changes are validated:

- Only valid transitions allowed
- Certain transitions require checklist completion
- All transitions logged

## API Security

### Authentication

API endpoints require authentication:

- Session authentication (for UI)
- Token authentication (for API clients)

### Authorization

All API endpoints check:

1. User is authenticated
2. User belongs to the organization
3. User has appropriate role for the action

### Example Protected Endpoint

```python
class EpisodeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Episode.objects.filter(
            organization_uuid=self.request.session.get('organization_uuid')
        )
```

## Best Practices

1. **Always use organization filtering** - Never expose data across organizations
2. **Check roles before sensitive actions** - Especially for approval/publish
3. **Log security-relevant events** - Status changes, approvals, exports
4. **Review AI content before approval** - AI can produce incorrect/harmful content
5. **Use HTTPS in production** - Protect credentials and session tokens
6. **Rotate API tokens periodically** - Limit exposure from compromised tokens

## Security Checklist

- [ ] Database credentials secured (not in code)
- [ ] DEBUG=False in production
- [ ] HTTPS enabled
- [ ] CORS properly configured
- [ ] API tokens rotated
- [ ] Sensitive data encrypted at rest
- [ ] Regular security audits
- [ ] Logging enabled for security events
