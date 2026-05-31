
from django import forms
from . import models


class TaskForm(forms.ModelForm):
    class Meta:
        model = models.Task
        fields = [
            "project",
            "title",
            "notes",
            "is_done",
            "due_date",
        ]

    def __init__(self, *args, projects=None, **kwargs):
        """``projects`` limits the selectable projects to those the user may
        file a task into (set by the view from the active organization)."""
        super().__init__(*args, **kwargs)
        if projects is not None:
            self.fields["project"].queryset = projects
