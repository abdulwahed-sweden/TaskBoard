"""Helpers for the per-session "active organization".

The active org is stored as an id in ``request.session`` and always validated
against the user's current memberships before use, so a stale or tampered id
can never leak another org.
"""

from .models import Organization

SESSION_KEY = "active_organization_id"


def user_organizations(user):
    """Organizations the user is a member of (empty queryset if anonymous)."""
    if not user or not user.is_authenticated:
        return Organization.objects.none()
    return user.organizations.all()


def set_active_organization(request, organization):
    """Mark ``organization`` active for this session."""
    request.session[SESSION_KEY] = organization.pk


def get_active_organization(request):
    """Return the request's active organization, or ``None``.

    Reads the session id and confirms the user is still a member; otherwise
    falls back to their first organization and writes that back to the session.
    """
    orgs = user_organizations(request.user)
    active_id = request.session.get(SESSION_KEY)
    if active_id is not None:
        organization = orgs.filter(pk=active_id).first()
        if organization is not None:
            return organization
    # No valid selection: fall back to the first membership, if any.
    organization = orgs.first()
    if organization is not None:
        set_active_organization(request, organization)
    elif SESSION_KEY in request.session:
        del request.session[SESSION_KEY]
    return organization
