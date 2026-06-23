"""Server-rendered operations UI for the container operations domain.

Read-first: dashboard, service-request triage (list + detail + status
transitions), and reference lists for customers, containers and drivers. All
views are login-required and organization-scoped through the existing
``ActiveOrganizationMixin`` / membership helpers; creating and editing records is
done via the admin or the REST API for now.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View, generic

from organizations.models import Membership
from organizations.permissions import has_role
from organizations.views import ActiveOrganizationMixin

from . import workflow
from .importer import IMPORTERS, ImportError as ImportParseError, parse_upload
from .models import Container, Customer, Driver, ServiceRequest
from .services import transition_service_request

IMPORT_SESSION_KEY = "containers_import"

OPEN_EXCLUDED = [
    ServiceRequest.Status.COMPLETED,
    ServiceRequest.Status.CANCELLED,
    ServiceRequest.Status.REJECTED,
    ServiceRequest.Status.INVOICED,
]


def _role_in(user, organization):
    if organization is None:
        return None
    membership = (
        Membership.objects.filter(user=user, organization=organization)
        .only("role")
        .first()
    )
    return membership.role if membership else None


class DashboardView(ActiveOrganizationMixin, generic.TemplateView):
    template_name = "containers/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org = self.active_organization
        requests = (
            ServiceRequest.objects.filter(organization=org)
            if org
            else ServiceRequest.objects.none()
        )
        Status = ServiceRequest.Status
        context.update(
            {
                "total": requests.count(),
                "open_count": requests.exclude(status__in=OPEN_EXCLUDED).count(),
                "new_count": requests.filter(status=Status.NEW).count(),
                "scheduled_today": requests.filter(
                    scheduled_date=timezone.localdate()
                ).count(),
                "unassigned": requests.filter(
                    status=Status.SCHEDULED, assignments__isnull=True
                ).count(),
                "by_status": list(
                    requests.values("status").annotate(n=Count("id")).order_by("status")
                ),
                "recent": requests.select_related("customer", "service_type")[:8],
                "customer_count": (
                    Customer.objects.filter(organization=org).count() if org else 0
                ),
                "container_count": (
                    Container.objects.filter(organization=org).count() if org else 0
                ),
            }
        )
        return context


class ServiceRequestListView(ActiveOrganizationMixin, generic.ListView):
    template_name = "containers/servicerequest_list.html"
    context_object_name = "requests"
    paginate_by = 25

    def get_queryset(self):
        org = self.active_organization
        if not org:
            return ServiceRequest.objects.none()
        qs = ServiceRequest.objects.filter(organization=org).select_related(
            "customer", "service_type"
        )
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        priority = self.request.GET.get("priority")
        if priority:
            qs = qs.filter(priority=priority)
        query = self.request.GET.get("q")
        if query:
            qs = qs.filter(reference__icontains=query) | qs.filter(
                contact_name__icontains=query
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = ServiceRequest.Status.choices
        context["priority_choices"] = ServiceRequest.Priority.choices
        context["current"] = {
            "status": self.request.GET.get("status", ""),
            "priority": self.request.GET.get("priority", ""),
            "q": self.request.GET.get("q", ""),
        }
        return context


class ServiceRequestDetailView(LoginRequiredMixin, generic.DetailView):
    template_name = "containers/servicerequest_detail.html"
    context_object_name = "service_request"

    def get_queryset(self):
        return ServiceRequest.objects.filter(
            organization__members=self.request.user
        ).select_related("customer", "site", "container", "service_type", "owner")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sr = self.object
        role = _role_in(self.request.user, sr.organization)
        targets = workflow.allowed_transitions(role, sr.status)
        context["transitions"] = [
            {
                "to_status": target,
                "label": ServiceRequest.Status(target).label,
                "requires_note": workflow.requires_note(sr.status, target),
            }
            for target in targets
        ]
        context["activities"] = sr.activities.all()[:50]
        context["can_write"] = has_role(
            self.request.user, sr.organization, Membership.Role.MEMBER
        )
        return context


class ServiceRequestTransitionView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        sr = get_object_or_404(
            ServiceRequest.objects.filter(organization__members=request.user), pk=pk
        )
        try:
            transition_service_request(
                sr,
                request.POST.get("to_status", ""),
                user=request.user,
                note=request.POST.get("note", ""),
            )
            messages.success(request, _("Status updated."))
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return redirect("containers:servicerequest_detail", pk=pk)


class CustomerListView(ActiveOrganizationMixin, generic.ListView):
    template_name = "containers/customer_list.html"
    context_object_name = "customers"
    paginate_by = 25

    def get_queryset(self):
        org = self.active_organization
        if not org:
            return Customer.objects.none()
        return Customer.objects.filter(organization=org)


class CustomerDetailView(LoginRequiredMixin, generic.DetailView):
    template_name = "containers/customer_detail.html"
    context_object_name = "customer"

    def get_queryset(self):
        return Customer.objects.filter(organization__members=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sites"] = self.object.sites.all()
        context["containers"] = self.object.containers.all()
        context["requests"] = self.object.service_requests.all()[:25]
        return context


class ContainerListView(ActiveOrganizationMixin, generic.ListView):
    template_name = "containers/container_list.html"
    context_object_name = "containers"
    paginate_by = 25

    def get_queryset(self):
        org = self.active_organization
        if not org:
            return Container.objects.none()
        return Container.objects.filter(organization=org).select_related(
            "customer", "site"
        )


class DriverListView(ActiveOrganizationMixin, generic.ListView):
    template_name = "containers/driver_list.html"
    context_object_name = "drivers"
    paginate_by = 25

    def get_queryset(self):
        org = self.active_organization
        if not org:
            return Driver.objects.none()
        return Driver.objects.filter(organization=org)


class ImportView(ActiveOrganizationMixin, generic.View):
    """Upload a CSV/XLSX, preview validated rows, then commit. Members and above;
    the heavy lifting is in containers/importer.py — this is the web wrapper."""

    required_role = Membership.Role.MEMBER
    template_name = "containers/import.html"

    def get(self, request):
        payload = request.session.get(IMPORT_SESSION_KEY)
        preview = entity = None
        if payload:
            entity = payload["entity"]
            importer = IMPORTERS[entity](self.active_organization)
            preview = importer.preview(payload["rows"], payload["mapping"])
        return self._render(request, preview, entity)

    def post(self, request):
        action = request.POST.get("action")
        if action == "confirm":
            return self._confirm(request)
        if action == "cancel":
            request.session.pop(IMPORT_SESSION_KEY, None)
            return redirect("containers:import")
        return self._upload(request)

    def _upload(self, request):
        entity = request.POST.get("entity")
        upload = request.FILES.get("file")
        if entity not in IMPORTERS or not upload:
            messages.error(request, _("Choose a type and a file."))
            return redirect("containers:import")
        try:
            headers, rows = parse_upload(upload, upload.name)
        except ImportParseError as exc:
            messages.error(request, str(exc))
            return redirect("containers:import")
        importer = IMPORTERS[entity](self.active_organization)
        request.session[IMPORT_SESSION_KEY] = {
            "entity": entity,
            "rows": rows,
            "mapping": importer.auto_mapping(headers),
        }
        return redirect("containers:import")

    def _confirm(self, request):
        payload = request.session.pop(IMPORT_SESSION_KEY, None)
        if not payload:
            messages.error(request, _("Nothing to import."))
            return redirect("containers:import")
        importer = IMPORTERS[payload["entity"]](self.active_organization)
        result = importer.commit(payload["rows"], payload["mapping"])
        messages.success(request, _("Imported %(n)s row(s).") % {"n": result["created"]})
        if result["skipped"]:
            messages.warning(
                request, _("Skipped %(n)s row(s).") % {"n": len(result["skipped"])}
            )
        return redirect("containers:import")

    def _render(self, request, preview, entity):
        return render(
            request,
            self.template_name,
            {
                "entities": [(cls.key, cls.label) for cls in IMPORTERS.values()],
                "preview": preview,
                "entity": entity,
                "valid_count": (
                    sum(1 for r in preview if r["valid"]) if preview else 0
                ),
            },
        )
