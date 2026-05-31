
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views import generic
from django.urls import reverse_lazy

from organizations.models import Membership
from organizations.permissions import has_role
from organizations.views import ActiveOrganizationMixin

from . import models
from . import forms
from . import importer
from .activity import log_changes, log_created, snapshot

IMPORT_SESSION_KEY = "task_import"


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
    """Tasks across the active organization, optionally filtered to one project
    via ``?project=<id>``."""

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
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        projects = (
            self.active_organization.projects.all()
            if self.active_organization
            else []
        )
        context["projects"] = projects
        context["selected_project"] = self.request.GET.get("project") or ""
        context["can_write"] = has_role(
            self.request.user, self.active_organization, Membership.Role.MEMBER
        )
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
