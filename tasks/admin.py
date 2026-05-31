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
        "status",
        "due_date",
        "owner",
    ]
    readonly_fields = [
        "created",
        "last_updated",
    ]


class CommentAdmin(admin.ModelAdmin):
    list_display = ["task", "author", "created"]
    search_fields = ["body", "task__title"]
    readonly_fields = ["created"]


class ActivityAdmin(admin.ModelAdmin):
    list_display = ["task", "actor", "action", "created"]
    list_filter = ["action"]
    readonly_fields = ["task", "actor", "action", "description", "detail", "created"]

    def has_add_permission(self, request):
        return False  # activity is append-only, recorded by the app

    def has_change_permission(self, request, obj=None):
        return False


class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "notify_on_assignment",
        "notify_on_comment",
        "notify_on_status_change",
    ]
    search_fields = ["user__username"]


admin.site.register(models.Task, TaskAdmin)
admin.site.register(models.Comment, CommentAdmin)
admin.site.register(models.Activity, ActivityAdmin)
admin.site.register(models.NotificationPreference, NotificationPreferenceAdmin)

