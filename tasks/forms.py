
from django import forms
from . import models
from django.contrib.auth.models import User

class TaskForm(forms.ModelForm):
    class Meta:
        model = models.Task
        fields = [
            "title",
            "notes",
            "is_done",
            "due_date",
            "owner",
        ]

    def __init__(self, *args, **kwargs):
        super(TaskForm, self).__init__(*args, **kwargs)
        self.fields["owner"].queryset = User.objects.all()
        # owner is nullable on the model; don't force it in the form.
        self.fields["owner"].required = False
