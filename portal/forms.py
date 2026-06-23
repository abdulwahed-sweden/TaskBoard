from django import forms
from django.utils import timezone

from containers.models import ServiceType


class PinForm(forms.Form):
    pin = forms.CharField(
        max_length=12,
        label="PIN",
        widget=forms.PasswordInput(
            attrs={"inputmode": "numeric", "autocomplete": "off"}
        ),
    )


class QRServiceRequestForm(forms.Form):
    """Public service-request form. The container (hence organization, customer
    and site) is supplied by the view from the scanned QR code — never by the
    client — so this form only collects the service, date and contact details."""

    service_type = forms.ModelChoiceField(
        queryset=ServiceType.objects.none(), label="Service"
    )
    requested_date = forms.DateField(
        label="Preferred date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    contact_name = forms.CharField(max_length=120, label="Your name")
    contact_phone = forms.CharField(max_length=40, label="Phone")
    notes = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Notes"
    )
    # Honeypot: hidden, must stay empty. Bots that fill every field are rejected.
    website = forms.CharField(required=False, widget=forms.HiddenInput, label="")

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service_type"].queryset = ServiceType.objects.filter(
            organization=organization, is_active=True
        )

    def clean_requested_date(self):
        requested = self.cleaned_data["requested_date"]
        if requested < timezone.localdate():
            raise forms.ValidationError("Choose today or a future date.")
        return requested

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("website"):
            raise forms.ValidationError("Submission could not be processed.")
        return cleaned
