"""Public, PIN-gated customer portal reached by scanning a container's QR code.

Security model:
- Unknown or inactive containers 404 (qr_uid is opaque and unguessable).
- No container details are shown before a correct PIN is entered.
- A correct PIN stores a signed, time-boxed verification in the session; the
  request form is unreachable without it.
- Organization, customer and site are always derived server-side from the
  scanned container — never accepted from the client.
- PIN verification and submission are rate limited (see portal/ratelimit.py).
"""

import uuid

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from containers.models import Container, ServiceRequest
from containers.services import check_container_pin

from .forms import PinForm, QRServiceRequestForm
from .ratelimit import client_ip, too_many

# Verification lifetime and rate-limit budgets.
VERIFY_MAX_AGE = 900                         # 15 minutes
PIN_LIMIT, PIN_WINDOW = 5, 900               # per IP, per container
PIN_GLOBAL_LIMIT = 50                         # per container (all IPs), same window
SUBMIT_LIMIT, SUBMIT_WINDOW = 3, 3600         # per IP, per container

_signer = TimestampSigner(salt="portal.pin-verification")
_SESSION_KEY = "portal_verified"


# --- verification session helpers -------------------------------------------

def _mark_verified(request, qr_uid):
    verified = request.session.get(_SESSION_KEY, {})
    verified[qr_uid] = _signer.sign(qr_uid)
    request.session[_SESSION_KEY] = verified


def _is_verified(request, qr_uid):
    token = request.session.get(_SESSION_KEY, {}).get(qr_uid)
    if not token:
        return False
    try:
        _signer.unsign(token, max_age=VERIFY_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


def _clear_verified(request, qr_uid):
    verified = request.session.get(_SESSION_KEY, {})
    if verified.pop(qr_uid, None) is not None:
        request.session[_SESSION_KEY] = verified


# --- container lookup & safe projection -------------------------------------

def _get_active_container(qr_uid):
    return get_object_or_404(
        Container, qr_uid=qr_uid, status=Container.Status.ACTIVE
    )


def _safe_info(container):
    """Only the fields safe to show a member of the public after PIN entry."""
    site = container.site
    return {
        "operator_name": container.organization.name,
        "container_type": container.get_container_type_display(),
        "size": container.size,
        "site_label": site.label if site else "",
        "site_city": site.city if site else "",
    }


# --- views -------------------------------------------------------------------

def landing(request, qr_uid):
    _get_active_container(qr_uid)  # 404s unknown/inactive before anything else
    if _is_verified(request, qr_uid):
        return redirect("portal:request", qr_uid=qr_uid)
    return render(request, "portal/landing.html", {"form": PinForm(), "qr_uid": qr_uid})


@require_POST
def verify_pin(request, qr_uid):
    container = _get_active_container(qr_uid)
    ip = client_ip(request)
    if too_many(f"portal:pin:{qr_uid}:{ip}", PIN_LIMIT, PIN_WINDOW) or too_many(
        f"portal:pin:{qr_uid}", PIN_GLOBAL_LIMIT, PIN_WINDOW
    ):
        return render(
            request,
            "portal/landing.html",
            {"form": PinForm(), "qr_uid": qr_uid, "locked": True},
            status=429,
        )

    form = PinForm(request.POST)
    if form.is_valid() and check_container_pin(container, form.cleaned_data["pin"]):
        _mark_verified(request, qr_uid)
        return redirect("portal:request", qr_uid=qr_uid)

    form.add_error("pin", "Incorrect PIN.")
    return render(request, "portal/landing.html", {"form": form, "qr_uid": qr_uid})


def request_service(request, qr_uid):
    container = _get_active_container(qr_uid)
    if not _is_verified(request, qr_uid):
        return redirect("portal:landing", qr_uid=qr_uid)

    if request.method == "POST":
        ip = client_ip(request)
        if too_many(f"portal:submit:{qr_uid}:{ip}", SUBMIT_LIMIT, SUBMIT_WINDOW):
            form = QRServiceRequestForm(organization=container.organization)
            return render(
                request,
                "portal/request.html",
                {"form": form, "qr_uid": qr_uid, "info": _safe_info(container), "locked": True},
                status=429,
            )
        form = QRServiceRequestForm(request.POST, organization=container.organization)
        if form.is_valid():
            service_request = _create_request(container, form)
            _clear_verified(request, qr_uid)  # one submission per verification
            return redirect(
                "portal:done", qr_uid=qr_uid, reference=service_request.reference
            )
    else:
        form = QRServiceRequestForm(organization=container.organization)

    return render(
        request,
        "portal/request.html",
        {"form": form, "qr_uid": qr_uid, "info": _safe_info(container)},
    )


def done(request, qr_uid, reference):
    return render(request, "portal/done.html", {"reference": reference})


def _create_request(container, form):
    reference = f"QR-{uuid.uuid4().hex[:10].upper()}"
    return ServiceRequest.objects.create(
        organization=container.organization,
        customer=container.customer,
        site=container.site,
        container=container,
        service_type=form.cleaned_data["service_type"],
        reference=reference,
        source=ServiceRequest.Source.QR,
        status=ServiceRequest.Status.NEW,
        requested_date=form.cleaned_data["requested_date"],
        contact_name=form.cleaned_data["contact_name"],
        contact_phone=form.cleaned_data["contact_phone"],
        notes=form.cleaned_data.get("notes", ""),
    )
