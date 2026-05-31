
from django.urls import path, include
from rest_framework import routers

from . import api
from . import views


router = routers.DefaultRouter()
router.register("Task", api.TaskViewSet)

app_name = "tasks"
urlpatterns = (
    path("api/v1/", include(router.urls)),
    path("Task/", views.TaskListView.as_view(), name="Task_list"),
    path("Task/create/", views.TaskCreateView.as_view(), name="Task_create"),
    path("Task/detail/<int:pk>/", views.TaskDetailView.as_view(), name="Task_detail"),
    path("Task/update/<int:pk>/", views.TaskUpdateView.as_view(), name="Task_update"),
    path("Task/delete/<int:pk>/", views.TaskDeleteView.as_view(), name="Task_delete"),
)
