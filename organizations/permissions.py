"""Role-based permission helpers, usable as plain predicates or as a CBV mixin.

The active-org scoping of task views lands in Phase 2; these helpers exist now
so that work has a single, tested place to ask "may this user act in this org?".
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from .models import Membership, role_rank


def has_role(user, organization, min_role):
    """True if ``user`` belongs to ``organization`` with at least ``min_role``.

    Anonymous users and non-members are always False.
    """
    if organization is None or not user or not user.is_authenticated:
        return False
    membership = (
        Membership.objects.filter(user=user, organization=organization)
        .only("role")
        .first()
    )
    if membership is None:
        return False
    return role_rank(membership.role) >= role_rank(min_role)


class RequireRoleMixin(LoginRequiredMixin):
    """CBV mixin that requires the logged-in user to hold at least
    ``required_role`` in the organization returned by ``get_organization``.

    Subclasses set ``required_role`` and implement ``get_organization(self)``.
    Anonymous users are redirected to login (via ``LoginRequiredMixin``);
    authenticated users without the role get a 403.
    """

    required_role = Membership.Role.MEMBER

    def get_organization(self):
        raise NotImplementedError(
            "RequireRoleMixin subclasses must implement get_organization()"
        )

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not has_role(
            request.user, self.get_organization(), self.required_role
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
