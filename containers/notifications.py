"""Email notifications for service-request status transitions.

The recipient is the request's customer (``customer.email``). Sending is
best-effort — failures are logged, never raised into the request path — and a
``NotificationLog`` row is recorded for every attempt with a recipient. Dev uses
the console email backend (see ``settings.py``); tests use ``mailoutbox``.

Only notable, customer-facing target statuses notify; intermediate operational
moves (assigned, in_progress) do not. Driver notifications belong with the
assignment flow and are intentionally not handled here yet.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import NotificationLog, ServiceRequest

logger = logging.getLogger(__name__)

# Target statuses worth telling the customer about.
CUSTOMER_NOTIFY_STATUSES = frozenset(
    {
        ServiceRequest.Status.VERIFIED,
        ServiceRequest.Status.SCHEDULED,
        ServiceRequest.Status.COMPLETED,
        ServiceRequest.Status.CANCELLED,
        ServiceRequest.Status.REJECTED,
        ServiceRequest.Status.INVOICED,
    }
)


def notify_transition(service_request, to_status):
    """Email the customer about a notable status change. Best-effort: returns the
    created ``NotificationLog`` (or ``None`` when there is nothing to send) and
    never raises."""
    if to_status not in CUSTOMER_NOTIFY_STATUSES:
        return None
    recipient = (service_request.customer.email or "").strip()
    if not recipient:
        return None

    operator = service_request.organization.name
    status_label = service_request.get_status_display()
    subject = f"[{operator}] {service_request.reference} — {status_label}"
    body = (
        f"Your service request {service_request.reference} is now "
        f'"{status_label}".\n\n{operator}'
    )

    sent = False
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
        sent = True
    except OSError:
        logger.exception(
            "Failed to send transition notification for %s", service_request.reference
        )

    return NotificationLog.objects.create(
        service_request=service_request,
        to_status=to_status,
        recipient=recipient,
        sent=sent,
    )


def _driver_email(driver):
    """The driver's contact email: their own, else the linked login user's."""
    if driver.email:
        return driver.email
    if driver.user_id and driver.user.email:
        return driver.user.email
    return ""


def notify_assignment(assignment):
    """Best-effort email to the driver assigned to a request. Logged against the
    request with the ``assigned`` status. Never raises; returns the
    ``NotificationLog`` or ``None`` when there is no recipient."""
    recipient = (_driver_email(assignment.driver) or "").strip()
    if not recipient:
        return None

    sr = assignment.service_request
    operator = sr.organization.name
    when = assignment.scheduled_date or sr.scheduled_date
    subject = f"[{operator}] Assigned: {sr.reference}"
    body = (
        f"You have been assigned service request {sr.reference}"
        + (f" for {when}" if when else "")
        + f".\n\n{operator}"
    )

    sent = False
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
        sent = True
    except OSError:
        logger.exception(
            "Failed to send assignment notification for %s", sr.reference
        )

    return NotificationLog.objects.create(
        service_request=sr,
        to_status=ServiceRequest.Status.ASSIGNED,
        recipient=recipient,
        sent=sent,
    )
