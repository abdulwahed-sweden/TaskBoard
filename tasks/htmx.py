
from django.views import generic
from django.urls import reverse_lazy
from django.shortcuts import HttpResponse
from django.template.response import TemplateResponse

from . import models
from . import forms

class HTMXTaskListView(generic.ListView):
    model = models.Task
    form_class = forms.TaskForm
    
    def get(self, request, *args, **kwargs):
        super().get(request, *args, **kwargs)
        context = {
            "model_id": self.model._meta.verbose_name_raw,
            "objects": self.get_queryset()
        }
        return TemplateResponse(request,'htmx/list.html', context)


class HTMXTaskCreateView(generic.CreateView):
    model = models.Task
    form_class = forms.TaskForm
    
    def get(self, request, *args, **kwargs):
        super().get(request, *args, **kwargs)
        context = {
            "create_url": self.model.get_htmx_create_url(),
            "form": self.get_form()
        }
        return TemplateResponse(request, 'htmx/form.html', context)

    def form_valid(self, form):
        super().form_valid(form)
        context = {
            "model_id": self.model._meta.verbose_name_raw,
            "object": self.object,
            "form": form
        }
        return TemplateResponse(self.request, 'htmx/create.html', context)

    def form_invalid(self, form):
        super().form_invalid(form)
        context = {
            "create_url": self.model.get_htmx_create_url(),
            "form": self.get_form()
        }
        return TemplateResponse(self.request, 'htmx/form.html', context)


class HTMXTaskDeleteView(generic.DeleteView):
    model = models.Task
    success_url = reverse_lazy("tasks:Task_htmx_list")
    
    def form_valid(self, form):
        super().form_valid(form)
        return HttpResponse()

