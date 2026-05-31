from django.contrib import admin
from django import forms

from . import models


class TaskAdminForm(forms.ModelForm):

    class Meta:
        model = models.Task
        fields = "__all__"


class TaskAdmin(admin.ModelAdmin):
    form = TaskAdminForm
    list_display = [
        "created",
        "last_updated",
        "title",
        "notes",
        "is_done",
        "due_date",
        "owner",
    ]
    readonly_fields = [
        "created",
        "last_updated",
    ]


admin.site.register(models.Task, TaskAdmin)

