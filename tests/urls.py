"""Test URLs for django-workflow-engine."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/approval/", include("approval_workflow.urls")),
    path("api/workflow/", include("django_workflow_engine.urls")),
]
