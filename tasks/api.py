
from rest_framework import viewsets, permissions

from . import serializers
from . import models


class TaskViewSet(viewsets.ModelViewSet):
    """ViewSet for the Task class"""

    queryset = models.Task.objects.all()
    serializer_class = serializers.TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

