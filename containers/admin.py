from django import forms
from django.contrib import admin
from django.contrib.auth.hashers import make_password

from . import models


class CustomerAdmin(admin.ModelAdmin):
    list_display = ["name", "customer_number", "organization", "email", "phone", "is_active"]
    list_filter = ["organization", "is_active"]
    search_fields = ["name", "customer_number", "org_number", "email"]
    autocomplete_fields = ["organization"]
    readonly_fields = ["created"]


class SiteAdmin(admin.ModelAdmin):
    list_display = ["__str__", "customer", "city", "postal_code", "organization", "is_active"]
    list_filter = ["organization", "is_active", "city"]
    search_fields = ["label", "street", "city", "postal_code", "customer__name"]
    autocomplete_fields = ["organization", "customer"]
    readonly_fields = ["created"]


class ContainerAdminForm(forms.ModelForm):
    new_pin = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Set or replace the customer portal PIN. Leave blank to keep the current one.",
    )

    class Meta:
        model = models.Container
        exclude = ["pin_hash"]  # never edit/display the hash directly

    def save(self, commit=True):
        instance = super().save(commit=False)
        raw = self.cleaned_data.get("new_pin")
        if raw:
            instance.pin_hash = make_password(raw)
        if commit:
            instance.save()
        return instance


class ContainerAdmin(admin.ModelAdmin):
    form = ContainerAdminForm
    list_display = ["__str__", "container_type", "size", "customer", "site", "status", "pin_set", "organization"]
    list_filter = ["organization", "container_type", "waste_category", "status"]
    search_fields = ["serial_number", "qr_uid", "customer__name"]
    autocomplete_fields = ["organization", "customer", "site"]
    # qr_uid is auto-generated and immutable; the PIN is set via the form's
    # write-only new_pin field and stored hashed.
    readonly_fields = ["qr_uid", "created"]

    @admin.display(boolean=True, description="PIN set")
    def pin_set(self, obj):
        return bool(obj.pin_hash)


class DriverAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "user", "organization", "is_active"]
    list_filter = ["organization", "is_active"]
    search_fields = ["name", "phone"]
    autocomplete_fields = ["organization", "user"]
    readonly_fields = ["created"]


class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "category", "organization", "requires_pin", "is_active"]
    list_filter = ["organization", "category", "requires_pin", "is_active"]
    search_fields = ["name", "code"]
    autocomplete_fields = ["organization", "project_type"]
    readonly_fields = ["created"]


class AssignmentInline(admin.TabularInline):
    model = models.Assignment
    extra = 0
    autocomplete_fields = ["driver"]
    readonly_fields = ["created"]


class ServiceRequestActivityInline(admin.TabularInline):
    model = models.ServiceRequestActivity
    extra = 0
    can_delete = False
    readonly_fields = ["actor", "action", "description", "detail", "created"]

    def has_add_permission(self, request, obj=None):
        return False  # activity is append-only, recorded by the service layer


class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ["reference", "customer", "service_type", "status", "priority", "requested_date", "scheduled_date", "organization"]
    list_filter = ["organization", "status", "priority", "source", "service_type"]
    search_fields = ["reference", "customer__name", "contact_name"]
    autocomplete_fields = ["organization", "customer", "site", "container", "service_type", "owner"]
    readonly_fields = ["created", "updated"]
    inlines = [AssignmentInline, ServiceRequestActivityInline]


class AssignmentAdmin(admin.ModelAdmin):
    list_display = ["service_request", "driver", "scheduled_date", "sequence", "status", "organization"]
    list_filter = ["organization", "status"]
    search_fields = ["service_request__reference", "driver__name"]
    autocomplete_fields = ["organization", "service_request", "driver"]
    readonly_fields = ["created"]


class ServiceRequestActivityAdmin(admin.ModelAdmin):
    list_display = ["service_request", "actor", "action", "created"]
    list_filter = ["action"]
    search_fields = ["service_request__reference"]
    readonly_fields = ["service_request", "actor", "action", "description", "detail", "created"]

    def has_add_permission(self, request):
        return False  # append-only, recorded by the service layer

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(models.Customer, CustomerAdmin)
admin.site.register(models.Site, SiteAdmin)
admin.site.register(models.Container, ContainerAdmin)
admin.site.register(models.Driver, DriverAdmin)
admin.site.register(models.ServiceType, ServiceTypeAdmin)
admin.site.register(models.ServiceRequest, ServiceRequestAdmin)
admin.site.register(models.Assignment, AssignmentAdmin)
admin.site.register(models.ServiceRequestActivity, ServiceRequestActivityAdmin)
