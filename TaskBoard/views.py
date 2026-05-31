from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.urls import reverse_lazy
from django.views import generic

from organizations.services import create_personal_organization
from tasks.models import Task


class SignUpView(generic.CreateView):
    """Self-service registration using Django's built-in user form."""

    form_class = UserCreationForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("login")

    def form_valid(self, form):
        """Create the user, then give them a personal organization to own."""
        response = super().form_valid(form)
        create_personal_organization(self.object)
        return response


class ProfileView(LoginRequiredMixin, generic.UpdateView):
    """Show and edit the logged-in user's account, plus their tasks."""

    model = User
    fields = ["first_name", "last_name", "email"]
    template_name = "registration/profile.html"
    success_url = reverse_lazy("profile")

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tasks"] = Task.objects.filter(owner=self.request.user)
        return context
