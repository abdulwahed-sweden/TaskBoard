from django.apps import AppConfig


class ContainersConfig(AppConfig):
    name = 'containers'

    def ready(self):
        from . import signals  # noqa: F401  (registers the assignment signal)
