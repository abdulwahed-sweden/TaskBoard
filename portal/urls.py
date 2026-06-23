from django.urls import path

from . import views

app_name = "portal"
urlpatterns = [
    path("<str:qr_uid>/", views.landing, name="landing"),
    path("<str:qr_uid>/verify/", views.verify_pin, name="verify"),
    path("<str:qr_uid>/request/", views.request_service, name="request"),
    path("<str:qr_uid>/done/<str:reference>/", views.done, name="done"),
]
