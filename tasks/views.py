
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import urlencode
from django.views import generic

from organizations.models import Membership, Project
from organizations.permissions import has_role
from organizations.views import ActiveOrganizationMixin

from . import models
from . import forms
from . import importer
from . import notifications
from .activity import log_changes, log_created, snapshot

IMPORT_SESSION_KEY = "task_import"


def task_filters_from_request(request):
    """Canonical task-list filters (status / is_done / q), omitting blanks.

    Reads POST data on a POST (the "save view" form) and query params otherwise
    (the list and saved-view links), so every caller agrees on the filter shape.
    ``project`` is handled separately.
    """
    data = request.POST if request.method == "POST" else request.GET
    filters = {}
    status = data.get("status", "").strip()
    if status:
        filters["status"] = status
    is_done = data.get("is_done", "").strip().lower()
    if is_done in ("true", "false"):
        filters["is_done"] = is_done
    q = data.get("q", "").strip()
    if q:
        filters["q"] = q
    return filters


def apply_task_filters(queryset, filters):
    """Narrow ``queryset`` by a canonical filter dict (see above)."""
    if "status" in filters:
        queryset = queryset.filter(status=filters["status"])
    if "is_done" in filters:
        queryset = queryset.filter(is_done=filters["is_done"] == "true")
    if "q" in filters:
        term = filters["q"]
        queryset = queryset.filter(
            Q(title__icontains=term) | Q(notes__icontains=term)
        )
    return queryset


class OrgScopedTaskMixin(LoginRequiredMixin):
    """Read boundary: only tasks in projects within orgs the user belongs to.

    A task in another org is invisible (404 on detail/update/delete) rather
    than leaking. Replaces the old owner-scoping.
    """

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(project__organization__members=self.request.user)
        )


class TaskWriteRoleMixin(OrgScopedTaskMixin):
    """Org-scoped (read) plus a write gate: the user must hold at least
    ``member`` in the task's organization. Viewers can open the detail page but
    get a 403 on update/delete."""

    def get_object(self, queryset=None):
        task = super().get_object(queryset)
        if not has_role(
            self.request.user, task.project.organization, Membership.Role.MEMBER
        ):
            raise PermissionDenied
        return task


class TaskListView(ActiveOrganizationMixin, generic.ListView):
    """Tasks across the active organization, filterable by `?project=`,
    `?status=`, `?is_done=`, and `?q=` (search) — all within the org scope."""

    model = models.Task

    def get_queryset(self):
        if not self.active_organization:
            return models.Task.objects.none()
        queryset = models.Task.objects.filter(
            project__organization=self.active_organization
        )
        project_id = self.request.GET.get("project")
        if project_id:
            # Already constrained to the active org, so a foreign id just
            # yields an empty list rather than leaking.
            queryset = queryset.filter(project_id=project_id)
        return apply_task_filters(queryset, task_filters_from_request(self.request))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org = self.active_organization
        projects = org.projects.all() if org else []
        context["projects"] = projects
        selected_project_id = self.request.GET.get("project") or ""
        context["selected_project"] = selected_project_id
        context["filters"] = task_filters_from_request(self.request)
        context["can_write"] = has_role(
            self.request.user, org, Membership.Role.MEMBER
        )
        # Distinct statuses present in the org, for the filter dropdown.
        context["status_options"] = sorted(
            models.Task.objects.filter(project__organization=org)
            .exclude(status="")
            .values_list("status", flat=True)
            .distinct()
        ) if org else []
        # Saved views only make sense in a single-project context.
        selected_project = None
        if selected_project_id and org:
            selected_project = org.projects.filter(pk=selected_project_id).first()
        context["selected_project_obj"] = selected_project
        context["saved_views"] = (
            selected_project.saved_views.all() if selected_project else []
        )
        # Hidden-input pairs so the "save view" form carries the current filters.
        context["current_filters"] = task_filters_from_request(self.request)
        return context


class TaskCreateView(ActiveOrganizationMixin, generic.CreateView):
    model = models.Task
    form_class = forms.TaskForm
    required_role = Membership.Role.MEMBER

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["projects"] = self.active_organization.projects.all()
        kwargs["assignees"] = self.active_organization.members.all()
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        project_id = self.request.GET.get("project")
        if project_id:
            initial["project"] = project_id
        initial["owner"] = self.request.user.pk
        return initial

    def form_valid(self, form):
        # Default the assignee to the creator only if left unset.
        if not form.instance.owner_id:
            form.instance.owner = self.request.user
        response = super().form_valid(form)
        log_created(self.object, self.request.user)
        notifications.on_task_created(self.object, self.request.user)
        return response


class TaskDetailView(OrgScopedTaskMixin, generic.DetailView):
    model = models.Task

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["comments"] = self.object.comments.select_related("author")
        context["activities"] = self.object.activities.select_related("actor")
        context["comment_form"] = forms.CommentForm()
        context["can_comment"] = has_role(
            self.request.user,
            self.object.project.organization,
            Membership.Role.MEMBER,
        )
        return context


class TaskUpdateView(TaskWriteRoleMixin, generic.UpdateView):
    model = models.Task
    form_class = forms.TaskForm
    pk_url_kwarg = "pk"

    def get_object(self, queryset=None):
        task = super().get_object(queryset)
        self._previous = snapshot(task)  # before the form mutates it
        return task

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        organization = self.object.project.organization
        # Allow moving the task between projects within its own organization.
        kwargs["projects"] = organization.projects.all()
        kwargs["assignees"] = organization.members.all()
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        log_changes(self.object, self.request.user, self._previous)
        notifications.on_task_updated(self.object, self.request.user, self._previous)
        return response


class TaskDeleteView(TaskWriteRoleMixin, generic.DeleteView):
    model = models.Task
    success_url = reverse_lazy("tasks:Task_list")


class AddCommentView(LoginRequiredMixin, generic.View):
    """Post a comment on a task. Org-scoped (foreign task 404s) and requires
    ``member`` (viewers are read-only)."""

    http_method_names = ["post"]

    def post(self, request, pk):
        task = get_object_or_404(
            models.Task.objects.filter(
                project__organization__members=request.user
            ),
            pk=pk,
        )
        if not has_role(
            request.user, task.project.organization, Membership.Role.MEMBER
        ):
            raise PermissionDenied
        form = forms.CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.task = task
            comment.author = request.user
            comment.save()
            notifications.notify_comment(task, request.user)
        return redirect(task.get_absolute_url())


class TaskImportView(ActiveOrganizationMixin, generic.View):
    """Step 1: upload a CSV/XLSX file for a chosen active-org project. Members+
    only (via ``required_role``)."""

    required_role = Membership.Role.MEMBER
    template_name = "tasks/import_start.html"
    http_method_names = ["get", "post"]

    def _projects(self):
        return self.active_organization.projects.all()

    def get(self, request):
        return render(request, self.template_name, {"projects": self._projects()})

    def post(self, request):
        project = get_object_or_404(
            self._projects(), pk=request.POST.get("project")
        )
        upload = request.FILES.get("file")
        if not upload:
            return render(
                request,
                self.template_name,
                {"projects": self._projects(), "error": "Choose a file to upload."},
            )
        try:
            headers, rows = importer.parse_upload(upload, upload.name)
        except importer.ImportError as exc:
            return render(
                request,
                self.template_name,
                {"projects": self._projects(), "error": str(exc)},
            )
        request.session[IMPORT_SESSION_KEY] = {
            "project_id": project.pk,
            "headers": headers,
            "rows": rows,
        }
        return redirect("tasks:import_map")


class TaskImportMapView(ActiveOrganizationMixin, generic.View):
    """Step 2: map columns, preview validation, then commit. State lives in the
    session from step 1; the project is re-scoped to the active org each time."""

    required_role = Membership.Role.MEMBER
    template_name = "tasks/import_map.html"
    http_method_names = ["get", "post"]

    def _session_project(self, request):
        data = request.session.get(IMPORT_SESSION_KEY)
        if not data:
            return None, None
        project = get_object_or_404(
            self.active_organization.projects.all(), pk=data["project_id"]
        )
        return data, project

    def get(self, request):
        data, project = self._session_project(request)
        if not data:
            return redirect("tasks:import")
        mapping = importer.auto_mapping(project, data["headers"])
        return render(
            request, self.template_name, self._context(project, data, mapping, None)
        )

    def post(self, request):
        data, project = self._session_project(request)
        if not data:
            return redirect("tasks:import")
        mapping = self._mapping_from_post(request, project)

        if request.POST.get("action") == "commit":
            result = importer.commit(
                project, data["rows"], mapping, request.user
            )
            del request.session[IMPORT_SESSION_KEY]
            return render(
                request,
                "tasks/import_result.html",
                {"project": project, "result": result},
            )

        rows_preview = importer.preview(project, data["rows"], mapping)
        return render(
            request,
            self.template_name,
            self._context(project, data, mapping, rows_preview),
        )

    def _mapping_from_post(self, request, project):
        mapping = {}
        for name, _label, _required in importer.target_fields(project):
            source = request.POST.get(f"map_{name}", "")
            if source:
                mapping[name] = source
        return mapping

    def _context(self, project, data, mapping, preview):
        target_fields = importer.target_fields(project)
        fields = [
            {
                "name": name,
                "label": label,
                "required": required,
                "source": mapping.get(name, ""),
            }
            for name, label, required in target_fields
        ]
        # Reshape the preview into per-field cells aligned with ``fields`` so the
        # template can render a simple nested loop (no dynamic dict lookups).
        preview_rows = None
        valid_count = None
        if preview is not None:
            preview_rows = [
                {
                    "row_number": row["row_number"],
                    "valid": row["valid"],
                    "cells": [
                        {
                            "value": row["values"].get(name, ""),
                            "error": row["errors"].get(name, ""),
                        }
                        for name, _label, _required in target_fields
                    ],
                }
                for row in preview
            ]
            valid_count = sum(1 for row in preview if row["valid"])
        return {
            "project": project,
            "headers": data["headers"],
            "fields": fields,
            "preview_rows": preview_rows,
            "valid_count": valid_count,
        }


class NotificationPreferencesView(LoginRequiredMixin, generic.UpdateView):
    """Edit the current user's email notification preferences."""

    form_class = forms.NotificationPreferenceForm
    template_name = "tasks/notification_preferences.html"
    success_url = reverse_lazy("notification_preferences")

    def get_object(self, queryset=None):
        preference, _ = models.NotificationPreference.objects.get_or_create(
            user=self.request.user
        )
        return preference


class SavedViewCreateView(LoginRequiredMixin, generic.View):
    """Save the current task-list filters as a named, project-shared view.
    Org-scoped (foreign project 404s) and requires `member`+."""

    http_method_names = ["post"]

    def post(self, request):
        project = get_object_or_404(
            Project.objects.filter(organization__members=request.user),
            pk=request.POST.get("project"),
        )
        if not has_role(request.user, project.organization, Membership.Role.MEMBER):
            raise PermissionDenied
        name = request.POST.get("name", "").strip()
        if name:
            models.SavedView.objects.update_or_create(
                project=project,
                name=name,
                defaults={
                    "created_by": request.user,
                    "filters": task_filters_from_request(request),
                },
            )
        params = {"project": project.pk}
        params.update(task_filters_from_request(request))
        return redirect(f"{reverse('tasks:Task_list')}?{urlencode(params)}")


class SavedViewDeleteView(LoginRequiredMixin, generic.View):
    """Delete a saved view (member+ in its project's org)."""

    http_method_names = ["post"]

    def post(self, request, pk):
        saved_view = get_object_or_404(
            models.SavedView.objects.filter(
                project__organization__members=request.user
            ),
            pk=pk,
        )
        if not has_role(
            request.user, saved_view.project.organization, Membership.Role.MEMBER
        ):
            raise PermissionDenied
        project_id = saved_view.project_id
        saved_view.delete()
        return redirect(
            f"{reverse('tasks:Task_list')}?{urlencode({'project': project_id})}"
        )


class DashboardView(ActiveOrganizationMixin, generic.TemplateView):
    """At-a-glance overview of the active organization's work."""

    template_name = "tasks/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org = self.active_organization
        context["organization"] = org
        if org is None:
            return context
        tasks = models.Task.objects.filter(project__organization=org)
        context["total"] = tasks.count()
        context["open_count"] = tasks.filter(is_done=False).count()
        context["done_count"] = tasks.filter(is_done=True).count()
        context["overdue_count"] = tasks.filter(
            is_done=False, due_date__lt=timezone.localdate()
        ).count()
        context["status_counts"] = list(
            tasks.values("status")
            .annotate(count=Count("id"))
            .order_by("-count", "status")
        )
        context["recent_activity"] = (
            models.Activity.objects.filter(task__project__organization=org)
            .select_related("task", "actor")[:10]
        )
        return context
