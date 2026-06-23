"""Signal wiring for the containers app.

Driver-on-assigned notification: when an :class:`Assignment` is created (via the
admin, the API, or any future flow), email the assigned driver. A signal is used
here — rather than an explicit write-path hook like the task notifications — so
the driver is told regardless of how the assignment was created.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from . import notifications
from .models import Assignment


@receiver(post_save, sender=Assignment, dispatch_uid="containers_notify_assignment")
def _assignment_created(sender, instance, created, **kwargs):
    if created:
        notifications.notify_assignment(instance)
