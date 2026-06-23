"""Container operations domain models (first slice).

These are net-new, first-class models for the container booking / operations
product. They live alongside — and do not modify — the existing ``tasks`` and
``organizations`` apps. Tenancy is inherited from the existing
``organizations.Organization``: every tenant-owned model carries an
``organization`` FK so the existing role/scoping helpers apply unchanged.

This slice defines fields and relationships only. Behaviour reused from the
configurable engine (custom-field / status-workflow validation, transition
rules, the QR portal, importer, and API) lands in later, separately approved
phases.
"""

import uuid

from django.db import models


def generate_qr_uid():
    """Opaque, unguessable identifier used as the public QR target for a
    container (never the database primary key)."""
    return uuid.uuid4().hex


class Customer(models.Model):
    """A company or person served by the operating company (tenant)."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="customers",
    )
    name = models.CharField(max_length=120)
    # Human-facing account number, unique within the operating company.
    customer_number = models.CharField(max_length=40)
    org_number = models.CharField(max_length=40, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=40, blank=True, default="")
    billing_address = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "customer_number"],
                name="unique_customer_number_per_organization",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "name"]),
        ]

    def __str__(self):
        return self.name


class Site(models.Model):
    """A physical address belonging to a customer where containers are placed
    and services are performed."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="sites",
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="sites"
    )
    label = models.CharField(max_length=120, blank=True, default="")
    street = models.CharField(max_length=255)
    postal_code = models.CharField(max_length=16, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")
    municipality = models.CharField(max_length=120, blank=True, default="")
    access_notes = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["city", "street"]
        indexes = [
            models.Index(fields=["organization", "customer"]),
        ]

    def __str__(self):
        return self.label or self.street


class Container(models.Model):
    """A physical waste container placed at a site. The ``qr_uid`` is the opaque
    target encoded in the container's QR code for the (later) customer portal."""

    class ContainerType(models.TextChoices):
        SKIP = "skip", "Skip"
        ROLLOFF = "rolloff", "Roll-off"
        WHEELIE = "wheelie", "Wheelie bin"
        RECYCLING = "recycling", "Recycling"
        HAZMAT = "hazmat", "Hazardous"

    class WasteCategory(models.TextChoices):
        HOUSEHOLD = "household", "Household"
        CONSTRUCTION = "construction", "Construction"
        ELECTRICAL = "electrical", "Electrical"
        ASBESTOS = "asbestos", "Asbestos"
        MIXED = "mixed", "Mixed"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        REMOVED = "removed", "Removed"
        MAINTENANCE = "maintenance", "Maintenance"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="containers",
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="containers"
    )
    site = models.ForeignKey(
        Site,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="containers",
    )
    # Opaque public identifier for the QR code; unguessable, never the pk.
    qr_uid = models.CharField(
        max_length=32, unique=True, default=generate_qr_uid, editable=False
    )
    # Hashed PIN for the customer portal (set in a later phase); never plaintext.
    pin_hash = models.CharField(max_length=128, blank=True, default="")
    container_type = models.CharField(
        max_length=40, choices=ContainerType.choices
    )
    size = models.CharField(max_length=40, blank=True, default="")
    serial_number = models.CharField(max_length=80, blank=True, default="")
    waste_category = models.CharField(
        max_length=40, choices=WasteCategory.choices, blank=True, default=""
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    placed_at = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["site"]),
        ]

    def __str__(self):
        label = self.get_container_type_display()
        return f"{label} {self.size}".strip()


class Driver(models.Model):
    """A driver / field worker who performs assignments for the operating
    company. Optionally linked to a login user."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="drivers",
    )
    user = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=40, blank=True, default="")
    license_class = models.CharField(max_length=40, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["organization", "is_active"]),
        ]

    def __str__(self):
        return self.name


class ServiceType(models.Model):
    """A kind of service the operating company offers (emptying, replacement,
    rental, construction/electrical/asbestos waste, quote request, ...).

    ``project_type`` is an optional link to the existing configurable engine so
    a later phase can attach a custom-field schema and status workflow without
    modifying ``ProjectType`` itself.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="service_types",
    )
    # Optional engine link; PROTECT so a type in use is never silently dropped.
    project_type = models.ForeignKey(
        "organizations.ProjectType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=40, blank=True, default="")
    requires_pin = models.BooleanField(default=True)
    default_sla_days = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_service_type_code_per_organization",
            )
        ]

    def __str__(self):
        return self.name


class ServiceRequest(models.Model):
    """A request for a service against a customer/site/container — the new,
    purpose-built operational work item (parallel to, not a rename of,
    ``tasks.Task``).

    ``status`` and ``custom_fields`` are plain fields in this slice; validation
    against the configurable engine and transition rules arrive in a later
    approved phase.
    """

    class Source(models.TextChoices):
        QR = "qr", "QR portal"
        PORTAL = "portal", "Portal"
        PHONE = "phone", "Phone"
        IMPORT = "import", "Import"
        API = "api", "API"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"

    class Status(models.TextChoices):
        NEW = "new", "New"
        VERIFIED = "verified", "Verified"
        SCHEDULED = "scheduled", "Scheduled"
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        REJECTED = "rejected", "Rejected"
        INVOICE_READY = "invoice_ready", "Invoice ready"
        INVOICED = "invoiced", "Invoiced"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="service_requests",
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="service_requests"
    )
    site = models.ForeignKey(
        Site,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_requests",
    )
    container = models.ForeignKey(
        Container,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_requests",
    )
    service_type = models.ForeignKey(
        ServiceType, on_delete=models.PROTECT, related_name="service_requests"
    )
    # Human-facing reference, unique within the operating company.
    reference = models.CharField(max_length=40)
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.PORTAL
    )
    # Operational lifecycle status; transitions are governed by
    # containers/workflow.py (the role-aware transition layer).
    status = models.CharField(
        max_length=60, choices=Status.choices, default=Status.NEW, blank=True
    )
    priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.NORMAL
    )
    owner = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    requested_date = models.DateField(null=True, blank=True)
    scheduled_date = models.DateField(null=True, blank=True)
    # Captured for portal submissions made by people who are not login users.
    contact_name = models.CharField(max_length=120, blank=True, default="")
    contact_phone = models.CharField(max_length=40, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    custom_fields = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True, editable=False)
    updated = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        ordering = ["-created"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "reference"],
                name="unique_service_request_reference_per_organization",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "scheduled_date"]),
            models.Index(fields=["customer"]),
            models.Index(fields=["container"]),
        ]

    def __str__(self):
        return self.reference


class Assignment(models.Model):
    """Allocation of a service request to a driver for execution on a date."""

    class Status(models.TextChoices):
        ASSIGNED = "assigned", "Assigned"
        EN_ROUTE = "en_route", "En route"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    service_request = models.ForeignKey(
        ServiceRequest, on_delete=models.CASCADE, related_name="assignments"
    )
    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE, related_name="assignments"
    )
    scheduled_date = models.DateField(null=True, blank=True)
    sequence = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ASSIGNED
    )
    notes = models.TextField(blank=True, default="")
    created = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["sequence", "id"]
        indexes = [
            models.Index(fields=["driver", "scheduled_date"]),
            models.Index(fields=["service_request"]),
        ]

    def __str__(self):
        return f"{self.service_request} → {self.driver}"


class ServiceRequestActivity(models.Model):
    """Append-only record of a service request lifecycle event.

    Written only by the service layer (e.g. status transitions) where the acting
    user is known; there are no edit/delete paths. Mirrors ``tasks.Activity``
    and is scoped to its organization through ``service_request``.
    """

    class Action(models.TextChoices):
        CREATED = "created", "Created"
        STATUS_CHANGED = "status_changed", "Status changed"

    service_request = models.ForeignKey(
        ServiceRequest, on_delete=models.CASCADE, related_name="activities"
    )
    actor = models.ForeignKey(
        "auth.User", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    description = models.CharField(max_length=255)
    detail = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["-created", "-id"]
        verbose_name_plural = "service request activities"

    def __str__(self):
        return self.description


# Module-level aliases for the per-model "status" choice sets. They give
# drf-spectacular a stable, importable target for ENUM_NAME_OVERRIDES so the
# generated OpenAPI enums get distinct, non-colliding names (import_string can
# resolve a module attribute but not a nested TextChoices class).
CONTAINER_STATUS_CHOICES = Container.Status.choices
SERVICE_REQUEST_STATUS_CHOICES = ServiceRequest.Status.choices
ASSIGNMENT_STATUS_CHOICES = Assignment.Status.choices
