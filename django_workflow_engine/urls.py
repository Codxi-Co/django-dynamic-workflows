"""URL configuration for django_workflow_engine."""

from django.urls import include, path

from rest_framework.routers import DefaultRouter

from .views import WorkflowAttachmentViewSet, WorkFlowViewSet

# Create router for viewsets
router = DefaultRouter()
router.register(
    r"attachments", WorkflowAttachmentViewSet, basename="workflow-attachment"
)
router.register(r"workflows", WorkFlowViewSet, basename="workflow")

app_name = "django_workflow_engine"

urlpatterns = [
    path("", include(router.urls)),
]

# Individual URL patterns for non-viewset views (if needed)
# urlpatterns += [
#     path('api/workflow/validate/', SomeValidationView.as_view(), name='workflow-validate'),
# ]
