
from rest_framework import serializers
from . import models


class TaskSerializer(serializers.ModelSerializer):

    class Meta:
        model = models.Task
        fields = [
            "created",
            "last_updated",
            "title",
            "notes",
            "is_done",
            "due_date",
            "owner",
        ]

