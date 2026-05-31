from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View, generic

from .models import Membership, Project
from .permissions import has_role
from .sessions import (
    get_active_organization,
    set_active_organization,
    user_organizations,
)


class SwitchOrganizationView(LoginRequiredMixin, View):
    """POST an ``organization`` id to make it the session's active org.

    Only orgs the user belongs to can be selected; anything else 404s rather
    than leaking another tenant. GET is not allowed.
    """

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        organization = get_object_or_404(
            user_organizations(request.user),
            pk=request.POST.get("organization"),
        )
        set_active_organization(request, organization)
        return HttpResponseRedirect(self._redirect_target(request))

    def _redirect_target(self, request):
        candidate = request.POST.get("next") or request.META.get("HTTP_REFERER", "")
        if candidate and url_has_allowed_host_and_scheme(
            candidate,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return candidate
        return reverse("tasks:Task_list")


class ActiveOrganizationMixin(LoginRequiredMixin):
    """Resolves ``self.active_organization`` for the request and, when
    ``required_role`` is set, requires the user to hold at least that role in it
    (otherwise 403). Anonymous users are handled by ``LoginRequiredMixin``."""

    required_role = None

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.active_organization = get_active_organization(request)
            if self.required_role is not None and not has_role(
                request.user, self.active_organization, self.required_role
            ):
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class ProjectListView(ActiveOrganizationMixin, generic.ListView):
    """Projects in the active organization."""

    model = Project
    context_object_name = "projects"

    def get_queryset(self):
        if not self.active_organization:
            return Project.objects.none()
        return self.active_organization.projects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_create"] = has_role(
            self.request.user, self.active_organization, Membership.Role.MEMBER
        )
        return context


class ProjectDetailView(LoginRequiredMixin, generic.DetailView):
    """A project and its tasks. Scoped to projects in the user's orgs, so a
    project in another org 404s rather than leaking."""

    model = Project
    context_object_name = "project"

    def get_queryset(self):
        return Project.objects.filter(organization__members=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tasks"] = self.object.tasks.all()
        context["can_write"] = has_role(
            self.request.user,
            self.object.organization,
            Membership.Role.MEMBER,
        )
        return context


class ProjectCreateView(ActiveOrganizationMixin, generic.CreateView):
    """Create a project in the active org (members and above)."""

    model = Project
    fields = ["name", "description"]
    required_role = Membership.Role.MEMBER

    def form_valid(self, form):
        form.instance.organization = self.active_organization
        return super().form_valid(form)
