
from django import forms
from . import models


class TaskForm(forms.ModelForm):
    class Meta:
        model = models.Task
        fields = [
            "title",
            "notes",
            "is_done",
            "due_date",
        ]
