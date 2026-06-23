from django.urls import include, path
from rest_framework import routers

from . import api, views

router = routers.DefaultRouter()
router.register("customers", api.CustomerViewSet, basename="customer")
router.register("sites", api.SiteViewSet, basename="site")
router.register("containers", api.ContainerViewSet, basename="container")
router.register("drivers", api.DriverViewSet, basename="driver")
router.register("service-types", api.ServiceTypeViewSet, basename="servicetype")
router.register("service-requests", api.ServiceRequestViewSet, basename="servicerequest")
router.register("assignments", api.AssignmentViewSet, basename="assignment")

app_name = "containers"
urlpatterns = (
    path("api/v1/", include(router.urls)),
    # Operations UI (server-rendered, login-required, org-scoped).
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("requests/", views.ServiceRequestListView.as_view(), name="servicerequest_list"),
    path("requests/<int:pk>/", views.ServiceRequestDetailView.as_view(), name="servicerequest_detail"),
    path(
        "requests/<int:pk>/transition/",
        views.ServiceRequestTransitionView.as_view(),
        name="servicerequest_transition",
    ),
    path("customers/", views.CustomerListView.as_view(), name="customer_list"),
    path("customers/<int:pk>/", views.CustomerDetailView.as_view(), name="customer_detail"),
    path("units/", views.ContainerListView.as_view(), name="container_list"),
    path("drivers/", views.DriverListView.as_view(), name="driver_list"),
)
