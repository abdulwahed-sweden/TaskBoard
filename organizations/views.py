from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from .sessions import set_active_organization, user_organizations


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
