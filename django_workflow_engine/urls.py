"""URL configuration for django_workflow_engine."""

from django.urls import include, path

from rest_framework.routers import DefaultRouter

from .views import WorkflowAttachmentViewSet

# Create router for viewsets
router = DefaultRouter()
router.register(
    r"attachments", WorkflowAttachmentViewSet, basename="workflow-attachment"
)

app_name = "django_workflow_engine"

urlpatterns = [
    path("api/workflow/", include(router.urls)),
]

# Individual URL patterns for non-viewset views (if needed)
# urlpatterns += [
#     path('api/workflow/validate/', SomeValidationView.as_view(), name='workflow-validate'),
# ]
