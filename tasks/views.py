
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.views import generic
from django.urls import reverse_lazy

from organizations.models import Membership
from organizations.permissions import has_role
from organizations.views import ActiveOrganizationMixin

from . import models
from . import forms


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
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        project_id = self.request.GET.get("project")
        if project_id:
            initial["project"] = project_id
        return initial

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class TaskDetailView(OrgScopedTaskMixin, generic.DetailView):
    model = models.Task


class TaskUpdateView(TaskWriteRoleMixin, generic.UpdateView):
    model = models.Task
    form_class = forms.TaskForm
    pk_url_kwarg = "pk"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Allow moving the task between projects within its own organization.
        kwargs["projects"] = self.object.project.organization.projects.all()
        return kwargs


class TaskDeleteView(TaskWriteRoleMixin, generic.DeleteView):
    model = models.Task
    success_url = reverse_lazy("tasks:Task_list")
