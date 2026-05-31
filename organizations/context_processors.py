"""Expose the active org and the user's orgs to every template (for the nav
switcher). Registered in ``TEMPLATES['OPTIONS']['context_processors']``."""

from .sessions import get_active_organization, user_organizations


def organizations(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    return {
        "active_organization": get_active_organization(request),
        "user_organizations": user_organizations(user),
    }
