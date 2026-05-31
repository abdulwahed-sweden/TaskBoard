
from django.urls import path, include
from rest_framework import routers

from . import api
from . import views


router = routers.DefaultRouter()
router.register("Task", api.TaskViewSet, basename="task")
router.register("Project", api.ProjectViewSet, basename="project")

app_name = "tasks"
urlpatterns = (
    path("api/v1/", include(router.urls)),
    path("Task/", views.TaskListView.as_view(), name="Task_list"),
    path("Task/create/", views.TaskCreateView.as_view(), name="Task_create"),
    path("Task/detail/<int:pk>/", views.TaskDetailView.as_view(), name="Task_detail"),
    path("Task/update/<int:pk>/", views.TaskUpdateView.as_view(), name="Task_update"),
    path("Task/delete/<int:pk>/", views.TaskDeleteView.as_view(), name="Task_delete"),
    path("Task/<int:pk>/comment/", views.AddCommentView.as_view(), name="Task_comment"),
    path("import/", views.TaskImportView.as_view(), name="import"),
    path("import/map/", views.TaskImportMapView.as_view(), name="import_map"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path(
        "views/save/",
        views.SavedViewCreateView.as_view(),
        name="savedview_create",
    ),
    path(
        "views/<int:pk>/delete/",
        views.SavedViewDeleteView.as_view(),
        name="savedview_delete",
    ),
)
