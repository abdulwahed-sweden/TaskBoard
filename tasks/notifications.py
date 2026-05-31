"""Email notifications for task events, gated by per-user preferences.

The recipient is always the task's assignee (``task.owner``); the actor (the
user who performed the action) is never notified about their own action. Sending
is best-effort — failures are logged, never raised into the request path. Dev
uses the console email backend (see ``settings.py``); tests use ``mailoutbox``.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import NotificationPreference

logger = logging.getLogger(__name__)


def _preference(user):
    preference, _ = NotificationPreference.objects.get_or_create(user=user)
    return preference


def _send(recipient, actor, pref_attr, subject, body):
    """Send one notification unless it should be suppressed: no recipient, the
    recipient is the actor, the recipient has no email, or their preference for
    this event is off."""
    if recipient is None or recipient == actor or not recipient.email:
        return
    if not getattr(_preference(recipient), pref_attr):
        return
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient.email],
            fail_silently=False,
        )
    except OSError:
        logger.exception("Failed to send notification email to %s", recipient.email)


def _actor_name(actor):
    return actor.get_username() if actor is not None else "Someone"


def _task_line(task):
    return f'"{task.title}" ({task.get_absolute_url()})'


def notify_assignment(task, actor):
    _send(
        task.owner,
        actor,
        "notify_on_assignment",
        f"You were assigned: {task.title}",
        f"{_actor_name(actor)} assigned you the task {_task_line(task)}.",
    )


def notify_status_change(task, actor):
    _send(
        task.owner,
        actor,
        "notify_on_status_change",
        f"Status changed: {task.title}",
        f"{_actor_name(actor)} set the status of {_task_line(task)} "
        f"to {task.status_label or task.status}.",
    )


def notify_comment(task, actor):
    _send(
        task.owner,
        actor,
        "notify_on_comment",
        f"New comment: {task.title}",
        f"{_actor_name(actor)} commented on {_task_line(task)}.",
    )


# -- entry points used by the write paths ------------------------------------

def on_task_created(task, actor):
    if task.owner_id:
        notify_assignment(task, actor)


def on_task_updated(task, actor, previous):
    """``previous`` is the snapshot taken before the save (see tasks/activity.py
    ``snapshot``): {"status", "owner_id"}."""
    if previous.get("owner_id") != task.owner_id:
        notify_assignment(task, actor)
    if previous.get("status") != task.status:
        notify_status_change(task, actor)
