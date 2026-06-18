"""Status API URL configuration for django_workflow_engine."""

from django.urls import include, path

from rest_framework.routers import DefaultRouter

from .views import (
    ModelStatusConfigurationViewSet,
    ModelStatusViewSet,
    StatusActionViewSet,
    StatusAttachmentViewSet,
    StatusEnabledModelsView,
    StatusFlowDesignView,
    StatusHistoryViewSet,
    StatusModelOptionsView,
    StatusTransitionDiagramView,
    StatusTransitionViewSet,
    StatusViewSet,
    WorkflowStatusNodeViewSet,
)

router = DefaultRouter()
router.register(r"statuses", StatusViewSet, basename="status")
router.register(
    r"model-configurations",
    ModelStatusConfigurationViewSet,
    basename="model-status-configuration",
)
router.register(r"model-statuses", ModelStatusViewSet, basename="model-status")
router.register(
    r"workflow-statuses", WorkflowStatusNodeViewSet, basename="workflow-status"
)
router.register(r"transitions", StatusTransitionViewSet, basename="status-transition")
router.register(r"actions", StatusActionViewSet, basename="status-action")
router.register(r"attachments", StatusAttachmentViewSet, basename="status-attachment")

urlpatterns = [
    path("", StatusViewSet.as_view({"get": "list", "post": "create"}), name="status"),
    path(
        "<int:pk>/",
        StatusViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="status-detail",
    ),
    path("models/", StatusEnabledModelsView.as_view(), name="status-models"),
    path("flow/", StatusFlowDesignView.as_view(), name="status-flow"),
    path(
        "flow/<str:model>/",
        StatusFlowDesignView.as_view(),
        name="status-flow-detail",
    ),
    path(
        "options/<str:model>/", StatusModelOptionsView.as_view(), name="status-options"
    ),
    path(
        "transitions/<str:model>/",
        StatusTransitionDiagramView.as_view(),
        name="status-transition-diagram",
    ),
    # Backwards-compatible typo alias, because the requested path used "history".
    path(
        "history/", StatusHistoryViewSet.as_view({"get": "list"}), name="status-history"
    ),
    path("", include(router.urls)),
]
