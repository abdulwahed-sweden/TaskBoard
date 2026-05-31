from django.urls import path

from . import views

app_name = "organizations"
urlpatterns = [
    path("switch/", views.SwitchOrganizationView.as_view(), name="switch"),
]
