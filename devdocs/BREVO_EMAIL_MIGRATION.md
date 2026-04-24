# Brevo Email Migration - Producer

## Overview

The Producer app has been migrated from MailerSend to Brevo (formerly SendinBlue) for all transactional email sending.

## Changes Made

### 1. Django Settings Updated ✅

**File**: `Producer/logic_service/settings/docker.py`

**Before (MailerSend):**
```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.mailersend.net'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('MAILERSEND_SMTP_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('MAILERSEND_SMTP_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'ProducerForge <noreply@firstcityfoundry.com>')
```

**After (Brevo):**
```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('BREVO_SMTP_HOST', 'smtp-relay.brevo.com')
EMAIL_PORT = int(os.getenv('BREVO_SMTP_PORT', '587'))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('BREVO_SMTP_LOGIN', '')
EMAIL_HOST_PASSWORD = os.getenv('BREVO_SMTP_KEY', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'ProducerForge <hello@firstcityfoundry.com>')
```

### 2. Environment Variables Updated ✅

**File**: `.env.example`

Added `DEFAULT_FROM_EMAIL` to the email configuration section:

```bash
# ── Email (Brevo SMTP) ──────────────────────────────────────
BREVO_SMTP_KEY=your-brevo-smtp-key
BREVO_SMTP_LOGIN=your-smtp-login@smtp-brevo.com
BREVO_SMTP_HOST=smtp-relay.brevo.com
BREVO_SMTP_PORT=587
FROM_EMAIL=hello@firstcityfoundry.com
FROM_NAME=First City Foundry
REPLY_TO_EMAIL=hello@firstcityfoundry.com
DEFAULT_FROM_EMAIL=ProducerForge <hello@firstcityfoundry.com>
```

## Required Environment Variables

The following environment variables must be set in your `.env` file:

| Variable | Description | Example |
|----------|-------------|---------|
| `BREVO_SMTP_HOST` | Brevo SMTP server | `smtp-relay.brevo.com` |
| `BREVO_SMTP_PORT` | SMTP port | `587` |
| `BREVO_SMTP_LOGIN` | Your Brevo SMTP login | `96af72001@smtp-brevo.com` |
| `BREVO_SMTP_KEY` | Your Brevo SMTP API key | `xsmtpsib-...` |
| `DEFAULT_FROM_EMAIL` | Default sender address (must be verified in Brevo) | `ProducerForge <hello@firstcityfoundry.com>` |

## How to Get Brevo SMTP Credentials

1. **Login to Brevo Dashboard**: https://app.brevo.com/
2. **Navigate to**: Settings → SMTP & API
3. **Copy**:
   - SMTP Server: `smtp-relay.brevo.com`
   - Port: `587`
   - Login: Your unique SMTP login (looks like `96af72001@smtp-brevo.com`)
   - SMTP Key: Generate a new SMTP key or use existing one

## Verified Sender Addresses

**Important**: The `DEFAULT_FROM_EMAIL` address must be verified in your Brevo account.

To verify a sender address in Brevo:
1. Go to **Settings → Senders & IP**
2. Click **Add a new sender**
3. Enter email address and complete verification process
4. Wait for domain verification email

**Currently Verified**:
- `hello@firstcityfoundry.com` ✅

## Email Service Module

**File**: `Producer/production_ledger/services/email.py`

This module handles all transactional emails:
- `send_invitation_email()` - User invitations to join ProducerForge
- `send_access_request_received()` - Notify admins of new access requests
- `send_access_approved()` - Notify users their access was approved
- `send_access_declined()` - Notify users their access was declined

All emails use the `DEFAULT_FROM_EMAIL` sender address configured in settings.

## Testing Email Configuration

### Test in Django Shell

```bash
cd Producer
python manage.py shell
```

```python
from django.core.mail import send_mail
from django.conf import settings

# Check current settings
print(f"EMAIL_HOST: {settings.EMAIL_HOST}")
print(f"EMAIL_PORT: {settings.EMAIL_PORT}")
print(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
print(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")

# Send test email
send_mail(
    subject='Test Email from ProducerForge',
    message='This is a test email.',
    from_email=settings.DEFAULT_FROM_EMAIL,
    recipient_list=['your-email@example.com'],
    fail_silently=False,
)
```

### Test via Producer Interface

1. Navigate to `/producer/request-access/`
2. Submit an access request
3. Check if admin notification email is sent
4. Check Brevo dashboard for delivery confirmation

## Docker Configuration

The main `docker-compose.yml` automatically passes all environment variables from `.env` to the container:

```yaml
services:
  buildly:
    env_file:
      - .env
```

No additional Docker configuration needed.

## Troubleshooting

### Error: "The from.email domain must be verified"

**Cause**: The sender email address is not verified in Brevo.

**Solution**:
1. Verify the domain in Brevo dashboard
2. Update `DEFAULT_FROM_EMAIL` in `.env` to use a verified address
3. Restart the application

### Error: "SMTPAuthenticationError"

**Cause**: Invalid SMTP credentials.

**Solution**:
1. Check `BREVO_SMTP_LOGIN` and `BREVO_SMTP_KEY` are correct
2. Generate new SMTP key in Brevo dashboard if needed
3. Update `.env` and restart

### Error: "Connection refused"

**Cause**: Firewall blocking SMTP port or incorrect host.

**Solution**:
1. Verify `BREVO_SMTP_HOST=smtp-relay.brevo.com`
2. Verify `BREVO_SMTP_PORT=587`
3. Check firewall allows outbound connections on port 587

### Emails Not Sending

**Debug Steps**:
1. Check Django logs for errors
2. Check Brevo dashboard → Statistics → Email Activity
3. Verify sender email is verified in Brevo
4. Test SMTP connection with telnet:
   ```bash
   telnet smtp-relay.brevo.com 587
   ```

## Brevo vs MailerSend Comparison

| Feature | MailerSend | Brevo |
|---------|------------|-------|
| SMTP Host | `smtp.mailersend.net` | `smtp-relay.brevo.com` |
| Port | 587 | 587 |
| TLS | Yes | Yes |
| Free Tier | 12,000/month | 300/day |
| Authentication | API Key | Login + SMTP Key |
| Sender Verification | Required | Required |

## Migration Checklist

- [x] Update Django settings to use Brevo SMTP
- [x] Update environment variable names
- [x] Document Brevo credentials in .env.example
- [x] Update from email address to verified domain
- [x] Test email sending in development
- [ ] Test email sending in production
- [ ] Monitor Brevo dashboard for delivery rates
- [ ] Update any documentation referencing MailerSend

## Rollback Plan

If you need to switch back to MailerSend:

1. **Update settings**:
```python
EMAIL_HOST = 'smtp.mailersend.net'
EMAIL_HOST_USER = os.getenv('MAILERSEND_SMTP_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('MAILERSEND_SMTP_PASSWORD', '')
```

2. **Update .env**:
```bash
MAILERSEND_SMTP_USER=your-mailersend-user
MAILERSEND_SMTP_PASSWORD=your-mailersend-password
```

3. **Restart application**

## Additional Resources

- **Brevo Documentation**: https://developers.brevo.com/docs
- **Brevo SMTP Guide**: https://help.brevo.com/hc/en-us/articles/209462765
- **Django Email Backend**: https://docs.djangoproject.com/en/5.1/topics/email/

## Support

**Brevo Support**:
- Email: support@brevo.com
- Dashboard: https://app.brevo.com/

**Internal Support**:
- Check `Producer/devdocs/` for additional documentation
- Review email service code in `production_ledger/services/email.py`

---

**Status**: ✅ COMPLETE
**Migration Date**: 2025-01-15
**Version**: 1.0.0
**Impact**: All transactional emails now use Brevo
