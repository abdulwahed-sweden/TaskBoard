
"""
TaskBoard URL Configuration

The 'urlpatterns' list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import TemplateView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.authtoken.views import obtain_auth_token

from tasks.views import NotificationPreferencesView

from . import views

# Brand the admin to match the TaskBoard app (see templates/admin/base_site.html).
admin.site.site_header = 'TaskBoard administration'
admin.site.site_title = 'TaskBoard admin'
admin.site.index_title = 'Administration'

urlpatterns = [
    path('', TemplateView.as_view(template_name='index.html'), name='index'),
    path('accounts/signup/', views.SignUpView.as_view(), name='signup'),
    path('accounts/profile/', views.ProfileView.as_view(), name='profile'),
    path(
        'accounts/notifications/',
        NotificationPreferencesView.as_view(),
        name='notification_preferences',
    ),
    # Override the default reset view to send a styled HTML email (with the
    # existing plain-text template as the multipart fallback).
    path(
        'accounts/password_reset/',
        auth_views.PasswordResetView.as_view(
            html_email_template_name='registration/password_reset_email_html.html',
        ),
        name='password_reset',
    ),
    path('accounts/', include('django.contrib.auth.urls')),
    path('organizations/', include('organizations.urls')),
    path('tasks/', include('tasks.urls')),
    # API auth + documentation
    path('api/token/', obtain_auth_token, name='api_token'),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path(
        'api/docs/',
        SpectacularSwaggerView.as_view(url_name='schema'),
        name='swagger-ui',
    ),
    path(
        'api/redoc/',
        SpectacularRedocView.as_view(url_name='schema'),
        name='redoc',
    ),
    path('admin/', admin.site.urls),
]
