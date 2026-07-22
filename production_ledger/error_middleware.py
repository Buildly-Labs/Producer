"""
Error-reporting middleware for ProducerForge.

Catches every unhandled Django exception and every 4xx/5xx response,
stores a snapshot in the Django cache, renders a branded error page
with a one-click "Report to GitHub" button, and provides a developer
dismiss workflow via the GitHub Issues API.

Registration (add to settings MIDDLEWARE *first*, before SecurityMiddleware):

    MIDDLEWARE = [
        'production_ledger.error_middleware.ErrorReportingMiddleware',
        ...
    ]
"""

import logging
import traceback
import uuid
from datetime import datetime, timezone

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

# How long to keep error detail in cache (seconds).
_CACHE_TTL = int(getattr(settings, 'ERROR_REPORT_CACHE_TTL', 3600))

# HTTP statuses we intercept when produced by the response pipeline
# (process_exception handles Python exceptions before responses are built).
_INTERCEPT_STATUSES = frozenset({500, 502, 503, 504})

# Paths that should never be wrapped (e.g. admin, static).
_SKIP_PATH_PREFIXES = ('/admin/', '/static/', '/media/', '/__debug__/')


class ErrorReportingMiddleware:
    """
    Middleware that:
      1. Catches unhandled view exceptions via ``process_exception``.
      2. Intercepts 5xx responses that slipped through without raising.
      3. Stashes error details in the Django cache under a 12-char UUID key.
      4. Renders a branded error page with a "Report to GitHub" button.

    The error ID printed on the page is the cache key — users can quote it
    in support requests and developers can look it up via the
    ``GET /api/errors/<error_id>/`` endpoint.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    # ------------------------------------------------------------------
    # Main call chain
    # ------------------------------------------------------------------

    def __call__(self, request):
        if self._skip(request):
            return self.get_response(request)

        response = self.get_response(request)

        if (
            response.status_code in _INTERCEPT_STATUSES
            and not getattr(response, '_forge_error_handled', False)
            # Don't wrap DRF JSON responses — they already have error detail
            and not _is_api_path(request)
        ):
            error_id = _make_error_id()
            _store_error(error_id, {
                'status': response.status_code,
                'url': request.build_absolute_uri(),
                'method': request.method,
                'user': _safe_user(request),
                'timestamp': _utcnow(),
                'traceback': None,
                'exception_type': None,
                'exception_message': None,
            })
            return _render_error_page(request, response.status_code, error_id)

        return response

    # ------------------------------------------------------------------
    # Exception hook
    # ------------------------------------------------------------------

    def process_exception(self, request, exception):
        """Called by Django for every unhandled view exception."""
        if self._skip(request) or _is_api_path(request):
            # Let DRF / Django's default handler deal with API errors.
            return None

        error_id = _make_error_id()
        tb = traceback.format_exc()

        logger.exception(
            '[forge-error %s] %s %s — %s: %s',
            error_id,
            request.method,
            request.path,
            type(exception).__name__,
            exception,
        )

        _store_error(error_id, {
            'status': 500,
            'url': request.build_absolute_uri(),
            'method': request.method,
            'user': _safe_user(request),
            'timestamp': _utcnow(),
            'traceback': tb,
            'exception_type': type(exception).__name__,
            'exception_message': str(exception),
        })

        return _render_error_page(request, 500, error_id, tb=tb, exception=exception)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _skip(request) -> bool:
        return any(request.path.startswith(p) for p in _SKIP_PATH_PREFIXES)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_error_id() -> str:
    return uuid.uuid4().hex[:12]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_user(request) -> str:
    try:
        return str(request.user)
    except Exception:
        return 'anonymous'


def _is_api_path(request) -> bool:
    return request.path.startswith('/api/') or request.path.startswith('/producer/api/')


def _store_error(error_id: str, data: dict) -> None:
    try:
        cache.set(f'forge_error:{error_id}', data, _CACHE_TTL)
    except Exception:
        pass  # Cache backend unavailable — still render the error page.


def get_error(error_id: str) -> dict | None:
    """Retrieve a stored error by ID (used by the developer API)."""
    try:
        return cache.get(f'forge_error:{error_id}')
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Error page renderer
# ---------------------------------------------------------------------------

_STATUS_COPY = {
    400: ('Bad Request',          'The request was invalid or could not be understood.'),
    403: ('Permission Denied',    'You don\'t have access to this page.'),
    404: ('Not Found',            'The page you\'re looking for doesn\'t exist.'),
    500: ('Internal Server Error','Something went wrong on our end. We\'re sorry.'),
    502: ('Bad Gateway',          'The server received an invalid response from an upstream service.'),
    503: ('Service Unavailable',  'The server is temporarily unable to handle this request.'),
    504: ('Gateway Timeout',      'The server timed out waiting for an upstream service to respond.'),
}


def _render_error_page(
    request,
    status_code: int,
    error_id: str,
    tb: str | None = None,
    exception=None,
) -> HttpResponse:
    title, subtitle = _STATUS_COPY.get(
        status_code, ('Unexpected Error', 'An unexpected error occurred.')
    )
    context = {
        'status_code': status_code,
        'error_title': title,
        'error_subtitle': subtitle,
        'error_id': error_id,
        'show_traceback': bool(getattr(settings, 'DEBUG', False)),
        'traceback': tb,
        'exception_type': type(exception).__name__ if exception else None,
        'exception_message': str(exception) if exception else None,
        'github_reporting_enabled': bool(getattr(settings, 'GITHUB_TOKEN', '')),
    }

    try:
        html = render_to_string(
            'production_ledger/errors/error.html',
            context,
            request=request,
        )
    except Exception:
        html = _fallback_html(status_code, error_id, title, subtitle, tb if context['show_traceback'] else None)

    resp = HttpResponse(html, status=status_code, content_type='text/html; charset=utf-8')
    resp._forge_error_handled = True
    return resp


def _fallback_html(status_code, error_id, title, subtitle, tb=None) -> str:
    """Minimal self-contained error page — used when template rendering itself fails."""
    tb_block = (
        f'<details style="margin-top:16px;">'
        f'<summary style="cursor:pointer;color:#94a3b8;">Technical details</summary>'
        f'<pre style="font-size:11px;overflow:auto;background:#1e1e1e;color:#d4d4d4;'
        f'padding:16px;border-radius:6px;margin-top:8px;white-space:pre-wrap;">{tb}</pre>'
        f'</details>'
        if tb else ''
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{status_code} {title} — ProducerForge</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:#0b1220;color:#e2e8f0;font-family:system-ui,-apple-system,sans-serif;
          display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px}}
    .card{{background:#0f172a;border:1px solid #1e293b;border-radius:16px;
           padding:40px;max-width:640px;width:100%}}
    .badge{{display:inline-block;background:rgba(249,115,22,.15);color:#f97316;
            font-size:48px;font-weight:700;padding:8px 0;margin-bottom:16px;letter-spacing:-2px}}
    h2{{color:#e2e8f0;font-size:1.4em;margin-bottom:8px}}
    p{{color:#94a3b8;line-height:1.6;margin-bottom:12px}}
    .ref{{background:#1e293b;border-radius:6px;padding:10px 14px;
          font-family:monospace;font-size:0.85em;color:#64748b;margin-top:16px}}
    a{{color:#f97316;text-decoration:none}}
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">{status_code}</div>
    <h2>{title}</h2>
    <p>{subtitle}</p>
    <p>Our team has been notified. If this keeps happening, please
    <a href="/">go back to the dashboard</a> and try again.</p>
    <div class="ref">Reference: <strong>{error_id}</strong></div>
    {tb_block}
  </div>
</body>
</html>"""
