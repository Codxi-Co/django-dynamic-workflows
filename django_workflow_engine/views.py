"""API views for django_workflow_engine."""

import logging
from typing import Any, Dict

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import WorkflowAttachment, WorkflowConfiguration
from .serializers import WorkflowApprovalSerializer, WorkflowAttachmentSerializer
from .services import (
    attach_workflow_to_object,
    get_workflow_attachment,
    is_model_workflow_enabled,
    start_workflow_for_object,
)

logger = logging.getLogger(__name__)


class WorkflowAttachmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing WorkflowAttachment instances."""

    queryset = WorkflowAttachment.objects.all()
    serializer_class = WorkflowAttachmentSerializer

    def get_queryset(self):
        """Filter queryset based on query parameters."""
        queryset = super().get_queryset()

        # Filter by content type
        content_type = self.request.query_params.get("content_type")
        if content_type:
            try:
                app_label, model_name = content_type.split(".")
                ct = ContentType.objects.get(app_label=app_label, model=model_name)
                queryset = queryset.filter(content_type=ct)
            except (ValueError, ContentType.DoesNotExist):
                pass

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by workflow
        workflow_id = self.request.query_params.get("workflow_id")
        if workflow_id:
            queryset = queryset.filter(workflow_id=workflow_id)

        return queryset

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Perform approval action on workflow attachment."""
        attachment = self.get_object()

        if not attachment.target:
            return Response(
                {"error": "Target object not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Initialize serializer with target object
        serializer = WorkflowApprovalSerializer(
            data=request.data,
            object_instance=attachment.target,
            context={"request": request},
        )

        if serializer.is_valid():
            try:
                result = serializer.save()
                return Response(
                    {
                        "message": "Workflow action processed successfully",
                        "action": serializer.validated_data["action"],
                        "object_id": attachment.object_id,
                    }
                )
            except Exception as e:
                logger.error(f"Error processing workflow action: {str(e)}")
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        """Get workflow progress information."""
        attachment = self.get_object()
        return Response(attachment.get_progress_info())

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Start workflow for the attached object."""
        attachment = self.get_object()

        if attachment.status != "not_started":
            return Response(
                {"error": f"Workflow already started (status: {attachment.status})"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not attachment.target:
            return Response(
                {"error": "Target object not found"}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            updated_attachment = start_workflow_for_object(
                attachment.target, user=request.user
            )
            return Response(
                {
                    "message": "Workflow started successfully",
                    "status": updated_attachment.status,
                    "current_stage": (
                        updated_attachment.current_stage.name_en
                        if updated_attachment.current_stage
                        else None
                    ),
                }
            )
        except Exception as e:
            logger.error(f"Error starting workflow: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class WorkflowMixin:
    """
    Mixin to add workflow functionality to any ViewSet.

    Usage:
        class TicketViewSet(WorkflowMixin, ModelViewSet):
            queryset = Ticket.objects.all()
            serializer_class = TicketSerializer
    """

    @action(detail=True, methods=["post"])
    def attach_workflow(self, request, pk=None):
        """Attach a workflow to the object."""
        obj = self.get_object()

        # Check if model is enabled for workflows
        if not is_model_workflow_enabled(obj.__class__):
            return Response(
                {"error": "Workflow functionality is not enabled for this model"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        workflow_id = request.data.get("workflow_id")
        auto_start = request.data.get("auto_start", True)
        metadata = request.data.get("metadata", {})

        if not workflow_id:
            return Response(
                {"error": "workflow_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from .models import WorkFlow

            workflow = WorkFlow.objects.get(pk=workflow_id)

            attachment = attach_workflow_to_object(
                obj=obj,
                workflow=workflow,
                user=request.user,
                auto_start=auto_start,
                metadata=metadata,
            )

            return Response(
                {
                    "message": "Workflow attached successfully",
                    "attachment_id": attachment.id,
                    "status": attachment.status,
                }
            )

        except WorkFlow.DoesNotExist:
            return Response(
                {"error": "Workflow not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error attaching workflow: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"])
    def workflow_status(self, request, pk=None):
        """Get workflow status for the object."""
        obj = self.get_object()
        attachment = get_workflow_attachment(obj)

        if not attachment:
            return Response(
                {"message": "No workflow attached to this object"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(attachment.get_progress_info())

    @action(detail=True, methods=["post"])
    def workflow_action(self, request, pk=None):
        """Perform a workflow action (approve, reject, delegate, resubmit)."""
        obj = self.get_object()
        attachment = get_workflow_attachment(obj)

        if not attachment:
            return Response(
                {"error": "No workflow attached to this object"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Use WorkflowApprovalSerializer for validation and processing
        serializer = WorkflowApprovalSerializer(
            data=request.data, object_instance=obj, context={"request": request}
        )

        if serializer.is_valid():
            try:
                result = serializer.save()
                return Response(
                    {
                        "message": "Workflow action processed successfully",
                        "action": serializer.validated_data["action"],
                        "object_id": obj.pk,
                    }
                )
            except Exception as e:
                logger.error(f"Error processing workflow action: {str(e)}")
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def start_workflow(self, request, pk=None):
        """Start workflow for the object."""
        obj = self.get_object()
        attachment = get_workflow_attachment(obj)

        if not attachment:
            return Response(
                {"error": "No workflow attached to this object"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if attachment.status != "not_started":
            return Response(
                {"error": f"Workflow already started (status: {attachment.status})"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            updated_attachment = start_workflow_for_object(obj, user=request.user)
            return Response(
                {
                    "message": "Workflow started successfully",
                    "status": updated_attachment.status,
                    "current_stage": (
                        updated_attachment.current_stage.name_en
                        if updated_attachment.current_stage
                        else None
                    ),
                }
            )
        except Exception as e:
            logger.error(f"Error starting workflow: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# Example of how to use the mixin in a real ViewSet
class ExampleTicketViewSet(WorkflowMixin, viewsets.ModelViewSet):
    """
    Example ViewSet showing how to integrate workflow functionality.

    This would be in your main app, not in the workflow engine package.
    """

    # queryset = Ticket.objects.all()
    # serializer_class = TicketSerializer

    def get_queryset(self):
        """Override to add workflow-related prefetching."""
        return (
            super()
            .get_queryset()
            .prefetch_related(
                "workflowattachment_set__workflow",
                "workflowattachment_set__current_stage",
                "workflowattachment_set__current_pipeline",
            )
        )

    def get_serializer_context(self):
        """Add workflow context to serializer."""
        context = super().get_serializer_context()
        context["include_workflow"] = True
        return context
