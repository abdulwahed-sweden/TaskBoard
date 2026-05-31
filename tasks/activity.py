"""Recording task lifecycle events into the append-only Activity log.

Called from the app's write paths (web views and the API viewset) where the
acting user is known. Admin/raw ORM saves deliberately don't call these, so the
log reflects user actions.
"""

from .models import Activity


def snapshot(task):
    """Capture the fields whose changes we track, before a save."""
    return {"status": task.status, "owner_id": task.owner_id}


def _actor_name(user):
    return user.get_username() if user is not None else "Someone"


def log_created(task, actor):
    Activity.objects.create(
        task=task,
        actor=actor,
        action=Activity.Action.CREATED,
        description=f"{_actor_name(actor)} created this task.",
    )


def log_changes(task, actor, previous):
    """Emit the most specific activity for what changed between ``previous``
    (from :func:`snapshot`) and the now-saved ``task``."""
    actor_name = _actor_name(actor)
    logged = False

    if previous.get("status") != task.status:
        Activity.objects.create(
            task=task,
            actor=actor,
            action=Activity.Action.STATUS_CHANGED,
            description=(
                f"{actor_name} changed status to "
                f"{task.status_label or '(none)'}."
            ),
            detail={"from": previous.get("status", ""), "to": task.status},
        )
        logged = True

    if previous.get("owner_id") != task.owner_id:
        assignee = task.owner.get_username() if task.owner_id else None
        Activity.objects.create(
            task=task,
            actor=actor,
            action=Activity.Action.ASSIGNED,
            description=(
                f"{actor_name} assigned this task to {assignee}."
                if assignee
                else f"{actor_name} unassigned this task."
            ),
            detail={"to": assignee},
        )
        logged = True

    if not logged:
        Activity.objects.create(
            task=task,
            actor=actor,
            action=Activity.Action.UPDATED,
            description=f"{actor_name} updated this task.",
        )
