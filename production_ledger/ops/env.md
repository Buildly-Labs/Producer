# Environment Variables

## Required Variables

The `production_ledger` app uses the same database configuration as the parent Django project. No additional required environment variables.

## Optional Variables

### AI Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_PROVIDER` | `mock` | AI provider to use: `mock`, `openai`, `anthropic` |
| `OPENAI_API_KEY` | - | OpenAI API key (if using openai provider) |
| `ANTHROPIC_API_KEY` | - | Anthropic API key (if using anthropic provider) |
| `AI_MODEL` | Provider default | Specific model to use |

### Storage Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MEDIA_ROOT` | `media/` | Root directory for uploaded media files |
| `MAX_UPLOAD_SIZE_MB` | `500` | Maximum file upload size in MB |

### Export Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `EXPORT_TEMP_DIR` | `/tmp/exports` | Temporary directory for export generation |

## Example .env File

```bash
# AI Configuration
AI_PROVIDER=mock

# For production with OpenAI:
# AI_PROVIDER=openai
# OPENAI_API_KEY=sk-your-key-here

# Storage
MEDIA_ROOT=/var/www/media/
MAX_UPLOAD_SIZE_MB=500
```

## Provider-Specific Configuration

### Mock Provider (Default)

No configuration needed. Returns template responses for testing.

### OpenAI Provider (Future)

```bash
AI_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
AI_MODEL=gpt-4o  # Optional, defaults to gpt-4o
```

### Anthropic Provider (Future)

```bash
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-your-key-here
AI_MODEL=claude-3-opus  # Optional
```

## Organization Context

The app is designed for multi-tenant use. Each request requires an `organization_uuid` in the session/context. This is typically set by the Buildly authentication middleware.

For local development without Buildly auth:

```python
# In your view or middleware
request.session['organization_uuid'] = 'your-test-org-uuid'
```
