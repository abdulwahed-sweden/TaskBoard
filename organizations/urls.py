from django.urls import path

from . import views

app_name = "organizations"
urlpatterns = [
    path("switch/", views.SwitchOrganizationView.as_view(), name="switch"),
    path("projects/", views.ProjectListView.as_view(), name="Project_list"),
    path(
        "projects/create/",
        views.ProjectCreateView.as_view(),
        name="Project_create",
    ),
    path(
        "projects/<int:pk>/",
        views.ProjectDetailView.as_view(),
        name="Project_detail",
    ),
]
