
from django.views import generic
from django.urls import reverse_lazy

from . import models
from . import forms


class TaskListView(generic.ListView):
    model = models.Task


class TaskCreateView(generic.CreateView):
    model = models.Task
    form_class = forms.TaskForm


class TaskDetailView(generic.DetailView):
    model = models.Task


class TaskUpdateView(generic.UpdateView):
    model = models.Task
    form_class = forms.TaskForm
    pk_url_kwarg = "pk"


class TaskDeleteView(generic.DeleteView):
    model = models.Task
    success_url = reverse_lazy("tasks:Task_list")

