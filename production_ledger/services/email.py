"""
Email service for ProducerForge transactional emails via MailerSend (django-anymail).

All functions accept model instances and a request (for building absolute URIs)
or an explicit base_url string.  They fail silently with a logged error rather
than crashing the request — email delivery should never block the user action.
"""

import logging
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def _send(subject: str, html_body: str, to_email: str) -> bool:
    """Low-level send wrapper — returns True on success, logs and returns False on failure."""
    try:
        send_mail(
            subject=subject,
            message=strip_tags(html_body),
            html_message=html_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Failed to send email to %s (subject: %s)", to_email, subject)
        return False


# ---------------------------------------------------------------------------
# INVITATION EMAIL
# ---------------------------------------------------------------------------

def send_invitation_email(invitation, invite_url: str) -> bool:
    """
    Send an invitation to join ProducerForge.

    Args:
        invitation: Invitation model instance
        invite_url: Absolute URL to the AcceptInviteView (with token)
    """
    inviter_name = (
        invitation.invited_by.get_full_name() or invitation.invited_by.username
        if invitation.invited_by else 'The ProducerForge team'
    )
    html = render_to_string('production_ledger/emails/invitation.html', {
        'invitation': invitation,
        'invite_url': invite_url,
        'inviter_name': inviter_name,
    })
    return _send(
        subject=f"You've been invited to ProducerForge",
        html_body=html,
        to_email=invitation.email,
    )


# ---------------------------------------------------------------------------
# ACCESS REQUEST EMAILS
# ---------------------------------------------------------------------------

def send_access_request_received(access_request, admin_emails: list[str]) -> bool:
    """
    Notify admins that a new access request has been submitted.

    Args:
        access_request: AccessRequest model instance
        admin_emails: List of admin email addresses to notify
    """
    if not admin_emails:
        return True

    html = render_to_string('production_ledger/emails/access_request_received.html', {
        'access_request': access_request,
    })
    success = True
    for email in admin_emails:
        ok = _send(
            subject=f"New access request from {access_request.name}",
            html_body=html,
            to_email=email,
        )
        success = success and ok
    return success


def send_access_approved(invitation, invite_url: str) -> bool:
    """
    Notify the requester that their access request was approved and send the invite link.

    Args:
        invitation: Invitation created when the access request was approved
        invite_url: Absolute URL to the AcceptInviteView (with token)
    """
    html = render_to_string('production_ledger/emails/access_approved.html', {
        'invitation': invitation,
        'invite_url': invite_url,
    })
    return _send(
        subject="Your ProducerForge access request has been approved",
        html_body=html,
        to_email=invitation.email,
    )


def send_access_declined(access_request) -> bool:
    """
    Notify the requester that their access request was declined.

    Args:
        access_request: AccessRequest model instance
    """
    html = render_to_string('production_ledger/emails/access_declined.html', {
        'access_request': access_request,
    })
    return _send(
        subject="Update on your ProducerForge access request",
        html_body=html,
        to_email=access_request.email,
    )
