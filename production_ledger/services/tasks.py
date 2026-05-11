"""
Background task runner with timeout watchdog and status tracking.

Usage
-----
from production_ledger.services.tasks import run_background_task
from production_ledger.models import BackgroundTask

task = run_background_task(
    task_type=BackgroundTask.TASK_TRANSCRIPTION,
    label='Transcribe Episode 42',
    fn=my_function,
    episode=episode_obj,
    created_by=request.user,
    timeout=300,          # seconds (default 600)
    # any extra keyword args are forwarded to fn:
    asset_pk=asset.pk,
    user=request.user,
)
# task.pk can be stored / returned to the frontend for polling
"""
import logging
import threading

from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 600  # 10 minutes


def run_background_task(
    task_type: str,
    label: str,
    fn,
    *,
    episode=None,
    organization_uuid=None,
    created_by=None,
    timeout: int = DEFAULT_TIMEOUT,
    **fn_kwargs,
):
    """
    Create a BackgroundTask record, spawn a daemon watchdog thread, and return
    the task immediately.

    The watchdog thread:
      1. Marks the task as *running*.
      2. Runs ``fn(**fn_kwargs)`` in a child thread.
      3. Waits up to *timeout* seconds for the child.
      4. Marks the task completed / failed / timeout and writes any error.

    The calling view gets the task object back synchronously so it can return
    the task.pk to the browser for polling.
    """
    # Import here to avoid circular imports at module load time.
    from ..models import BackgroundTask  # noqa: PLC0415

    org_uuid = organization_uuid or (
        episode.organization_uuid if episode is not None else None
    )

    task = BackgroundTask.objects.create(
        task_type=task_type,
        label=label,
        status=BackgroundTask.STATUS_PENDING,
        episode=episode,
        organization_uuid=org_uuid,
        created_by=created_by,
    )

    def _watchdog(task_pk: str):
        import django  # noqa: PLC0415
        import django.db  # noqa: PLC0415

        # Re-fetch the task record — we're in a new thread.
        from ..models import BackgroundTask as _BT  # noqa: PLC0415

        try:
            task_obj = _BT.objects.get(pk=task_pk)
        except _BT.DoesNotExist:
            logger.error("BackgroundTask %s disappeared before watchdog started", task_pk)
            return

        task_obj.status = _BT.STATUS_RUNNING
        task_obj.started_at = timezone.now()
        task_obj.save(update_fields=["status", "started_at"])
        logger.info("BackgroundTask %s (%s) started", task_pk, task_obj.label)

        exc_holder: list = []

        def _worker():
            try:
                fn(**fn_kwargs)
            except Exception as exc:  # noqa: BLE001
                exc_holder.append(exc)
                logger.exception(
                    "BackgroundTask %s (%s) raised an exception",
                    task_pk,
                    task_obj.label,
                )
            finally:
                try:
                    django.db.connections.close_all()
                except Exception:  # noqa: BLE001
                    pass

        worker = threading.Thread(target=_worker, daemon=True)
        worker.start()
        worker.join(timeout=timeout)

        # Re-fetch to pick up any status changes written by fn itself.
        try:
            task_obj = _BT.objects.get(pk=task_pk)
        except _BT.DoesNotExist:
            return

        if task_obj.is_terminal:
            # fn() already marked it done (e.g., it updates ingestion_status
            # on a MediaAsset and we can consider the task done separately).
            logger.info("BackgroundTask %s already in terminal state %s", task_pk, task_obj.status)
            return

        now = timezone.now()
        if worker.is_alive():
            task_obj.status = _BT.STATUS_TIMEOUT
            task_obj.completed_at = now
            task_obj.error_message = (
                f"Task timed out after {timeout} seconds without completing. "
                "It may still be running in the background, but no result was recorded."
            )
            logger.warning("BackgroundTask %s timed out after %ds", task_pk, timeout)
        elif exc_holder:
            exc = exc_holder[0]
            task_obj.status = _BT.STATUS_FAILED
            task_obj.completed_at = now
            task_obj.error_message = _format_error(exc)
            logger.error("BackgroundTask %s failed: %s", task_pk, task_obj.error_message)
        else:
            task_obj.status = _BT.STATUS_COMPLETED
            task_obj.completed_at = now
            logger.info("BackgroundTask %s completed in %ds", task_pk,
                        (now - task_obj.started_at).seconds if task_obj.started_at else 0)

        task_obj.save(update_fields=["status", "completed_at", "error_message"])

        try:
            django.db.connections.close_all()
        except Exception:  # noqa: BLE001
            pass

    watchdog = threading.Thread(
        target=_watchdog,
        args=(str(task.pk),),
        daemon=True,
        name=f"forge-task-{task.pk}",
    )
    watchdog.start()
    return task


def _format_error(exc: Exception) -> str:
    """Return a user-friendly error string from an exception."""
    name = type(exc).__name__
    msg = str(exc).strip()

    # Provide helpful hints for common failure modes.
    hints = {
        "RuntimeError": None,
        "OpenAIError": "Check that your OpenAI API key is configured in Settings → API Keys.",
        "AuthenticationError": "API key is invalid or expired. Update it in Settings → API Keys.",
        "RateLimitError": "AI provider rate limit hit. Try again in a few minutes.",
        "APIConnectionError": "Could not reach the AI provider. Check your network connection.",
        "ImportError": "A required package is not installed on this server.",
        "FileNotFoundError": "A required file was not found (check storage/ffmpeg config).",
    }
    hint = hints.get(name)
    base = f"{name}: {msg}" if msg else name
    return f"{base}\n\nHint: {hint}" if hint else base
