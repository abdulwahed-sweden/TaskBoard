"""Tenancy operations that change data, kept out of views and models so they
can be reused (e.g. by signup and the data migration)."""

import logging

from django.utils.text import slugify

from .models import Membership, Organization

logger = logging.getLogger(__name__)


def unique_org_slug(base, *, exists):
    """Return a unique slug derived from ``base``.

    ``exists(slug)`` is a callable returning whether a slug is already taken.
    Passing it in lets both live code and migrations (which must use historical
    models) share this logic.
    """
    root = slugify(base) or "org"
    candidate = root
    suffix = 2
    while exists(candidate):
        candidate = f"{root}-{suffix}"
        suffix += 1
    return candidate


def create_personal_organization(user):
    """Create a personal organization for ``user`` and make them its owner.

    Returns the created :class:`Organization`. Safe to call once per new user
    (e.g. on signup); the data migration mirrors this logic for existing users.
    """
    slug = unique_org_slug(
        user.get_username(),
        exists=lambda s: Organization.objects.filter(slug=s).exists(),
    )
    organization = Organization.objects.create(
        name=f"{user.get_username()}'s Organization",
        slug=slug,
    )
    Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.OWNER,
    )
    logger.info(
        "Created personal organization %s for user %s", slug, user.get_username()
    )
    return organization
