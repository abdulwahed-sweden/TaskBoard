from django.urls import include, path
from rest_framework import routers

from . import api

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
)
