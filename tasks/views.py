
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import generic
from django.urls import reverse_lazy

from . import models
from . import forms


class OwnedTasksMixin(LoginRequiredMixin):
    """Restrict task access to those owned by the logged-in user."""

    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)


class TaskListView(OwnedTasksMixin, generic.ListView):
    model = models.Task


class TaskCreateView(LoginRequiredMixin, generic.CreateView):
    model = models.Task
    form_class = forms.TaskForm

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class TaskDetailView(OwnedTasksMixin, generic.DetailView):
    model = models.Task


class TaskUpdateView(OwnedTasksMixin, generic.UpdateView):
    model = models.Task
    form_class = forms.TaskForm
    pk_url_kwarg = "pk"


class TaskDeleteView(OwnedTasksMixin, generic.DeleteView):
    model = models.Task
    success_url = reverse_lazy("tasks:Task_list")
