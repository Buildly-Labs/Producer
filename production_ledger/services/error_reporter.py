"""
GitHub Issues reporter for ProducerForge error reporting.

Reads GITHUB_TOKEN and GITHUB_REPO from Django settings (sourced from env).
All HTTP calls use the stdlib so no extra dependencies are needed.

Typical env vars (.env / DigitalOcean App Platform secrets):
    GITHUB_TOKEN=ghp_...          Personal-access or fine-grained token
                                   Scopes needed: repo (issues: write)
    GITHUB_REPO=buildly-inc/producer   "owner/repo"
"""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

_GITHUB_API = 'https://api.github.com'
_UA = 'ProducerForge-ErrorReporter/1.0'


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_error_issue(error_id: str, error_data: dict, user_note: str = '') -> dict:
    """
    Create a GitHub issue for *error_data* and return::

        {issue_number, issue_url, issue_title}

    Raises ``RuntimeError`` if GITHUB_TOKEN / GITHUB_REPO are not configured
    or if the API call fails.
    """
    token, repo = _require_config()

    title = _issue_title(error_id, error_data)
    body  = _issue_body(error_id, error_data, user_note)
    labels = _issue_labels(error_data)

    result = _api_post(
        token,
        f'/repos/{repo}/issues',
        {'title': title, 'body': body, 'labels': labels},
    )

    logger.info(
        'GitHub issue created for forge-error %s: #%s %s',
        error_id, result['number'], result['html_url'],
    )
    return {
        'issue_number': result['number'],
        'issue_url':    result['html_url'],
        'issue_title':  result['title'],
    }


def close_issue(issue_number: int, comment: str = '') -> None:
    """
    Close a GitHub issue (called from the developer dismiss endpoint).
    Silently logs and returns on failure — never raises so a dismiss
    action can't crash the UI.
    """
    try:
        token, repo = _require_config()
        if comment:
            _api_post(token, f'/repos/{repo}/issues/{issue_number}/comments', {'body': comment})
        _api_patch(token, f'/repos/{repo}/issues/{issue_number}', {'state': 'closed'})
        logger.info('GitHub issue #%s closed', issue_number)
    except Exception as exc:
        logger.warning('Failed to close GitHub issue #%s: %s', issue_number, exc)


def list_open_error_issues(label: str = 'auto-reported') -> list[dict]:
    """
    Return open issues tagged with *label* — for the developer dashboard.
    Returns [] on any failure.
    """
    try:
        token, repo = _require_config()
        data = _api_get(token, f'/repos/{repo}/issues?state=open&labels={label}&per_page=50')
        return [
            {
                'number':    i['number'],
                'title':     i['title'],
                'url':       i['html_url'],
                'created_at': i['created_at'],
                'labels':    [lb['name'] for lb in i.get('labels', [])],
            }
            for i in data
        ]
    except Exception as exc:
        logger.warning('list_open_error_issues failed: %s', exc)
        return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_config() -> tuple[str, str]:
    token = getattr(settings, 'GITHUB_TOKEN', '')
    repo  = getattr(settings, 'GITHUB_REPO', '')
    if not token or not repo:
        raise RuntimeError(
            'GITHUB_TOKEN and GITHUB_REPO must be set to report issues. '
            'Add them as environment variables and restart the server.'
        )
    return token, repo


def _api_request(method: str, token: str, path: str, payload: dict | None = None) -> object:
    url = f'{_GITHUB_API}{path}'
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(  # noqa: S310
        url,
        data=data,
        method=method,
        headers={
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github+json',
            'Content-Type': 'application/json',
            'User-Agent': _UA,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'GitHub API {method} {path} → {exc.code}: {body[:300]}') from exc


def _api_post(token, path, payload):
    return _api_request('POST', token, path, payload)


def _api_patch(token, path, payload):
    return _api_request('PATCH', token, path, payload)


def _api_get(token, path):
    return _api_request('GET', token, path)


# ---------------------------------------------------------------------------
# Issue formatting
# ---------------------------------------------------------------------------

def _issue_title(error_id: str, data: dict) -> str:
    status   = data.get('status', 500)
    exc_type = data.get('exception_type') or ''
    # Strip query string for cleaner titles
    url_path = (data.get('url') or '').split('?')[0]
    if exc_type:
        return f'[Auto] {status} {exc_type} at {url_path} [{error_id}]'
    return f'[Auto] HTTP {status} at {url_path} [{error_id}]'


def _issue_body(error_id: str, data: dict, user_note: str) -> str:
    lines = [
        '## Automatic Error Report',
        '',
        f'**Error ID:** `{error_id}`',
        f'**Status:** {data.get("status", "?")}',
        f'**URL:** `{data.get("url", "")}`',
        f'**Method:** {data.get("method", "")}',
        f'**User:** {data.get("user", "anonymous")}',
        f'**Timestamp:** {data.get("timestamp", "")}',
        '',
    ]
    if data.get('exception_type'):
        lines += [
            '### Exception',
            f'`{data["exception_type"]}`: {data.get("exception_message", "")}',
            '',
        ]
    if user_note:
        lines += ['### User Note', user_note, '']
    if data.get('traceback'):
        lines += [
            '### Traceback',
            '```',
            data['traceback'],
            '```',
            '',
        ]
    lines += [
        '---',
        '_Created automatically by ProducerForge. '
        'Comment `/dismiss` or `/wontfix` to close without action, '
        'or `/resolve` after the fix is merged._',
    ]
    return '\n'.join(lines)


def _issue_labels(data: dict) -> list[str]:
    labels = ['bug', 'auto-reported']
    status = data.get('status', 500)
    tag = {502: 'gateway-error', 503: 'service-unavailable', 504: 'timeout', 500: 'server-error'}
    if status in tag:
        labels.append(tag[status])
    return labels
