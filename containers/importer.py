"""CSV/XLSX import for the container operations domain.

Reuses the pure parsing core of the existing task importer (``parse_upload`` and
``map_row`` — both generic and side-effect free) and adds one importer per
entity: a field catalog, a row validator that resolves foreign keys by natural
key, duplicate detection, and a committer. Like ``tasks/importer.py`` nothing
touches the database until :meth:`EntityImporter.commit`.
"""

import datetime
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _

# Reuse the generic parsing primitives from the existing importer.
from tasks.importer import ImportError, map_row, parse_upload  # noqa: F401

from .models import Container, Customer, ServiceRequest, ServiceType, Site
from .services import set_container_pin


def _iso_date(value):
    """Parse an ISO date string; raise ValueError on a bad value."""
    datetime.date.fromisoformat(value)  # validates
    return value


class EntityImporter:
    """Base importer: generic auto-mapping, preview and commit; subclasses
    declare ``fields`` and implement ``clean_row`` / ``is_duplicate`` / ``build``."""

    key = ""
    label = ""
    # (target, label, required)
    fields = []

    def __init__(self, organization):
        self.organization = organization

    def target_fields(self):
        return list(self.fields)

    def auto_mapping(self, headers):
        lookup = {h.lower().strip(): h for h in headers}
        mapping = {}
        for name, label, _required in self.fields:
            for key in (name, str(label)):
                match = lookup.get(key.lower())
                if match:
                    mapping[name] = match
                    break
        return mapping

    # --- per-entity hooks ---------------------------------------------------

    def clean_row(self, mapped):
        """Return ``(data, errors)``; no database writes."""
        raise NotImplementedError

    def is_duplicate(self, data):
        return False

    def build(self, data):
        raise NotImplementedError

    # --- shared helpers -----------------------------------------------------

    def _customer(self, mapped, data, errors, required=True):
        number = (mapped.get("customer_number") or "").strip()
        if not number:
            if required:
                errors["customer_number"] = _("Required.")
            return None
        customer = Customer.objects.filter(
            organization=self.organization, customer_number=number
        ).first()
        if customer is None:
            errors["customer_number"] = _("No customer with number '%(n)s'.") % {"n": number}
        else:
            data["customer"] = customer
        return customer

    # --- pipeline -----------------------------------------------------------

    def preview(self, rows, mapping):
        results = []
        for index, row in enumerate(rows, start=1):
            mapped = map_row(row, mapping)
            data, errors = self.clean_row(mapped)
            duplicate = bool(data) and not errors and self.is_duplicate(data)
            results.append(
                {
                    "row_number": index,
                    "values": mapped,
                    "errors": errors,
                    "duplicate": duplicate,
                    "valid": not errors and not duplicate,
                    "_data": data,
                }
            )
        return results

    def commit(self, rows, mapping):
        created = 0
        skipped = []
        for result in self.preview(rows, mapping):
            if result["valid"]:
                self.build(result["_data"])
                created += 1
                continue
            errors = dict(result["errors"])
            if result["duplicate"]:
                errors.setdefault("__all__", str(_("Already exists; skipped.")))
            skipped.append({"row_number": result["row_number"], "errors": errors})
        return {"created": created, "skipped": skipped}


class CustomerImporter(EntityImporter):
    key = "customers"
    label = _("Customers")
    fields = [
        ("name", _("Name"), True),
        ("customer_number", _("Customer number"), True),
        ("org_number", _("Org number"), False),
        ("email", _("Email"), False),
        ("phone", _("Phone"), False),
        ("billing_address", _("Billing address"), False),
        ("notes", _("Notes"), False),
    ]

    def clean_row(self, mapped):
        errors, data = {}, {}
        name = (mapped.get("name") or "").strip()
        if name:
            data["name"] = name
        else:
            errors["name"] = _("Required.")
        number = (mapped.get("customer_number") or "").strip()
        if number:
            data["customer_number"] = number
        else:
            errors["customer_number"] = _("Required.")
        email = (mapped.get("email") or "").strip()
        if email:
            try:
                validate_email(email)
                data["email"] = email
            except ValidationError:
                errors["email"] = _("Enter a valid email.")
        for opt in ("org_number", "phone", "billing_address", "notes"):
            if mapped.get(opt):
                data[opt] = mapped[opt].strip()
        return data, errors

    def is_duplicate(self, data):
        return Customer.objects.filter(
            organization=self.organization,
            customer_number=data.get("customer_number", ""),
        ).exists()

    def build(self, data):
        return Customer.objects.create(organization=self.organization, **data)


class SiteImporter(EntityImporter):
    key = "sites"
    label = _("Sites")
    fields = [
        ("customer_number", _("Customer number"), True),
        ("street", _("Street"), True),
        ("postal_code", _("Postal code"), False),
        ("city", _("City"), False),
        ("label", _("Label"), False),
        ("municipality", _("Municipality"), False),
        ("access_notes", _("Access notes"), False),
    ]

    def clean_row(self, mapped):
        errors, data = {}, {}
        self._customer(mapped, data, errors)
        street = (mapped.get("street") or "").strip()
        if street:
            data["street"] = street
        else:
            errors["street"] = _("Required.")
        for opt in ("postal_code", "city", "label", "municipality", "access_notes"):
            if mapped.get(opt):
                data[opt] = mapped[opt].strip()
        return data, errors

    def is_duplicate(self, data):
        return Site.objects.filter(
            organization=self.organization,
            customer=data.get("customer"),
            street=data.get("street", ""),
            postal_code=data.get("postal_code", ""),
        ).exists()

    def build(self, data):
        return Site.objects.create(organization=self.organization, **data)


class ContainerImporter(EntityImporter):
    key = "containers"
    label = _("Containers")
    fields = [
        ("customer_number", _("Customer number"), True),
        ("container_type", _("Container type"), True),
        ("site_label", _("Site label"), False),
        ("size", _("Size"), False),
        ("serial_number", _("Serial number"), False),
        ("waste_category", _("Waste category"), False),
        ("qr_uid", _("QR UID"), False),
        ("pin", _("PIN"), False),
    ]

    def clean_row(self, mapped):
        errors, data = {}, {}
        customer = self._customer(mapped, data, errors)

        container_type = (mapped.get("container_type") or "").strip()
        if not container_type:
            errors["container_type"] = _("Required.")
        elif container_type not in Container.ContainerType.values:
            errors["container_type"] = _("Unknown container type.")
        else:
            data["container_type"] = container_type

        waste = (mapped.get("waste_category") or "").strip()
        if waste:
            if waste in Container.WasteCategory.values:
                data["waste_category"] = waste
            else:
                errors["waste_category"] = _("Unknown waste category.")

        site_label = (mapped.get("site_label") or "").strip()
        if site_label and customer is not None:
            site = Site.objects.filter(
                organization=self.organization, customer=customer, label=site_label
            ).first()
            if site is None:
                errors["site_label"] = _("No site with label '%(l)s'.") % {"l": site_label}
            else:
                data["site"] = site

        for opt in ("size", "serial_number"):
            if mapped.get(opt):
                data[opt] = mapped[opt].strip()
        qr = (mapped.get("qr_uid") or "").strip()
        if qr:
            data["qr_uid"] = qr
        pin = (mapped.get("pin") or "").strip()
        if pin:
            data["_pin"] = pin
        return data, errors

    def is_duplicate(self, data):
        serial = data.get("serial_number")
        if serial and Container.objects.filter(
            organization=self.organization, serial_number=serial
        ).exists():
            return True
        qr = data.get("qr_uid")
        if qr and Container.objects.filter(qr_uid=qr).exists():
            return True
        return False

    def build(self, data):
        pin = data.pop("_pin", None)
        container = Container.objects.create(organization=self.organization, **data)
        if pin:
            set_container_pin(container, pin)
        return container


class ServiceRequestImporter(EntityImporter):
    key = "requests"
    label = _("Service requests")
    fields = [
        ("customer_number", _("Customer number"), True),
        ("service_type_code", _("Service type"), True),
        ("reference", _("Reference"), False),
        ("site_label", _("Site label"), False),
        ("container_qr_uid", _("Container QR UID"), False),
        ("requested_date", _("Requested date"), False),
        ("priority", _("Priority"), False),
        ("contact_name", _("Contact name"), False),
        ("contact_phone", _("Contact phone"), False),
        ("notes", _("Notes"), False),
    ]

    def clean_row(self, mapped):
        errors, data = {}, {}
        customer = self._customer(mapped, data, errors)

        code = (mapped.get("service_type_code") or "").strip()
        if not code:
            errors["service_type_code"] = _("Required.")
        else:
            service_type = ServiceType.objects.filter(
                organization=self.organization, code=code
            ).first()
            if service_type is None:
                errors["service_type_code"] = _("No service type '%(c)s'.") % {"c": code}
            else:
                data["service_type"] = service_type

        reference = (mapped.get("reference") or "").strip()
        if reference:
            data["reference"] = reference

        site_label = (mapped.get("site_label") or "").strip()
        if site_label and customer is not None:
            site = Site.objects.filter(
                organization=self.organization, customer=customer, label=site_label
            ).first()
            if site is None:
                errors["site_label"] = _("No site with label '%(l)s'.") % {"l": site_label}
            else:
                data["site"] = site

        qr = (mapped.get("container_qr_uid") or "").strip()
        if qr:
            container = Container.objects.filter(
                organization=self.organization, qr_uid=qr
            ).first()
            if container is None:
                errors["container_qr_uid"] = _("No container '%(q)s'.") % {"q": qr}
            else:
                data["container"] = container

        requested = (mapped.get("requested_date") or "").strip()
        if requested:
            try:
                data["requested_date"] = _iso_date(requested)
            except ValueError:
                errors["requested_date"] = _("Enter a date (YYYY-MM-DD).")

        priority = (mapped.get("priority") or "").strip()
        if priority:
            if priority in ServiceRequest.Priority.values:
                data["priority"] = priority
            else:
                errors["priority"] = _("Unknown priority.")

        for opt in ("contact_name", "contact_phone", "notes"):
            if mapped.get(opt):
                data[opt] = mapped[opt].strip()
        return data, errors

    def is_duplicate(self, data):
        reference = data.get("reference")
        if not reference:
            return False
        return ServiceRequest.objects.filter(
            organization=self.organization, reference=reference
        ).exists()

    def build(self, data):
        data.setdefault("reference", f"IMP-{uuid.uuid4().hex[:10].upper()}")
        return ServiceRequest.objects.create(
            organization=self.organization,
            source=ServiceRequest.Source.IMPORT,
            status=ServiceRequest.Status.NEW,
            **data,
        )


IMPORTERS = {
    cls.key: cls
    for cls in (CustomerImporter, SiteImporter, ContainerImporter, ServiceRequestImporter)
}
