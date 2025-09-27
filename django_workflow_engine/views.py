"""API views for django_workflow_engine."""

import logging
from typing import Any, Dict

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from approval_workflow.choices import RoleSelectionStrategy
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .choices import ApprovalTypes
from .models import WorkFlow, WorkflowAttachment, WorkflowConfiguration
from .serializers import (
    WorkflowApprovalSerializer,
    WorkflowAttachmentSerializer,
    WorkFlowDetailSerializer,
    WorkFlowListSerializer,
)
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
            modified_attachment = start_workflow_for_object(
                attachment.target, user=request.user
            )
            return Response(
                {
                    "message": "Workflow started successfully",
                    "status": modified_attachment.status,
                    "current_stage": (
                        modified_attachment.current_stage.name_en
                        if modified_attachment.current_stage
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
            modified_attachment = start_workflow_for_object(obj, user=request.user)
            return Response(
                {
                    "message": "Workflow started successfully",
                    "status": modified_attachment.status,
                    "current_stage": (
                        modified_attachment.current_stage.name_en
                        if modified_attachment.current_stage
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


class WorkFlowViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing WorkFlow instances with detailed nested data."""

    def get_queryset(self):
        """Get queryset with optimized prefetching."""
        queryset = WorkFlow.objects.select_related("company").prefetch_related(
            "pipelines__stages",
        )

        # Filter by company if provided
        if hasattr(self, "request") and self.request:
            company_id = self.request.query_params.get("company_id")
            if company_id:
                queryset = queryset.filter(company_id=company_id)

            # Filter by active status
            is_active = self.request.query_params.get("is_active")
            if is_active is not None:
                queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset

    def get_serializer_class(self):
        """Use different serializers for list vs detail views."""
        if self.action == "retrieve":
            return WorkFlowDetailSerializer
        return WorkFlowListSerializer

    @action(detail=True, methods=["get"])
    def pipeline_structure(self, request, pk=None):
        """Get detailed pipeline and stage structure for a workflow."""
        workflow = self.get_object()

        # Build pipeline structure
        pipelines_data = []
        for pipeline in workflow.pipelines.all():
            stages_data = []
            for stage in pipeline.stages.all():
                approvals = stage.stage_info.get("approvals", [])

                # Count approvals by type
                approval_counts = {
                    ApprovalTypes.ROLE: 0,
                    ApprovalTypes.USER: 0,
                    ApprovalTypes.SELF: 0,
                }
                for approval in approvals:
                    approval_type = approval.get("approval_type", "")
                    if approval_type in approval_counts:
                        approval_counts[approval_type] += 1

                stages_data.append(
                    {
                        "id": stage.id,
                        "name_en": stage.name_en,
                        "name_ar": stage.name_ar,
                        "order": stage.order,
                        "is_active": stage.is_active,
                        "approvals_count": len(approvals),
                        "approval_types": approval_counts,
                        "color": stage.stage_info.get("color", "#3498db"),
                        "has_forms": any(
                            approval.get("required_form") for approval in approvals
                        ),
                    }
                )

            pipelines_data.append(
                {
                    "id": pipeline.id,
                    "name_en": pipeline.name_en,
                    "name_ar": pipeline.name_ar,
                    "order": pipeline.order,
                    "department": pipeline.department_name,
                    "stages": stages_data,
                    "stages_count": len(stages_data),
                }
            )

        return Response(
            {
                "workflow_id": workflow.id,
                "workflow_name": workflow.name_en,
                "pipelines": pipelines_data,
                "total_pipelines": len(pipelines_data),
                "total_stages": sum(len(p["stages"]) for p in pipelines_data),
            }
        )

    @action(detail=True, methods=["get"])
    def approval_summary(self, request, pk=None):
        """Get approval summary across all stages in the workflow."""
        workflow = self.get_object()

        # Collect approval statistics
        approval_stats = {
            "total_approvals": 0,
            "by_type": {
                ApprovalTypes.ROLE: 0,
                ApprovalTypes.USER: 0,
                ApprovalTypes.SELF: 0,
            },
            "by_strategy": {
                RoleSelectionStrategy.ANYONE: 0,
                RoleSelectionStrategy.CONSENSUS: 0,
                RoleSelectionStrategy.ROUND_ROBIN: 0,
            },
            "stages_with_forms": 0,
            "pipeline_breakdown": [],
        }

        for pipeline in workflow.pipelines.all():
            pipeline_stats = {
                "pipeline_name": pipeline.name_en,
                "pipeline_order": pipeline.order,
                "stages": [],
                "total_approvals": 0,
            }

            for stage in pipeline.stages.all():
                approvals = stage.stage_info.get("approvals", [])
                stage_approvals = len(approvals)
                pipeline_stats["total_approvals"] += stage_approvals
                approval_stats["total_approvals"] += stage_approvals

                # Count by type and strategy
                has_forms = False
                for approval in approvals:
                    approval_type = approval.get("approval_type", "")
                    if approval_type in approval_stats["by_type"]:
                        approval_stats["by_type"][approval_type] += 1

                    strategy = approval.get("role_selection_strategy", "")
                    if strategy in approval_stats["by_strategy"]:
                        approval_stats["by_strategy"][strategy] += 1

                    if approval.get("required_form"):
                        has_forms = True

                if has_forms:
                    approval_stats["stages_with_forms"] += 1

                pipeline_stats["stages"].append(
                    {
                        "stage_name": stage.name_en,
                        "stage_order": stage.order,
                        "approvals_count": stage_approvals,
                        "has_forms": has_forms,
                    }
                )

            approval_stats["pipeline_breakdown"].append(pipeline_stats)

        return Response(approval_stats)

    @action(detail=False, methods=["get"])
    def workflow_statistics(self, request):
        """Get overall statistics about all workflows."""
        queryset = self.get_queryset()

        total_workflows = queryset.count()
        active_workflows = queryset.filter(is_active=True).count()

        # Calculate pipeline and stage counts
        total_pipelines = 0
        total_stages = 0
        total_approvals = 0

        company_stats = {}

        for workflow in queryset:
            company_name = (
                workflow.company.username if workflow.company else "No Company"
            )
            if company_name not in company_stats:
                company_stats[company_name] = {
                    "workflows": 0,
                    "pipelines": 0,
                    "stages": 0,
                    "approvals": 0,
                }

            workflow_pipelines = workflow.pipelines.count()
            workflow_stages = sum(
                pipeline.stages.count() for pipeline in workflow.pipelines.all()
            )
            workflow_approvals = 0

            for pipeline in workflow.pipelines.all():
                for stage in pipeline.stages.all():
                    approvals = stage.stage_info.get("approvals", [])
                    workflow_approvals += len(approvals)

            total_pipelines += workflow_pipelines
            total_stages += workflow_stages
            total_approvals += workflow_approvals

            company_stats[company_name]["workflows"] += 1
            company_stats[company_name]["pipelines"] += workflow_pipelines
            company_stats[company_name]["stages"] += workflow_stages
            company_stats[company_name]["approvals"] += workflow_approvals

        return Response(
            {
                "overview": {
                    "total_workflows": total_workflows,
                    "active_workflows": active_workflows,
                    "inactive_workflows": total_workflows - active_workflows,
                    "total_pipelines": total_pipelines,
                    "total_stages": total_stages,
                    "total_approvals": total_approvals,
                    "avg_pipelines_per_workflow": (
                        round(total_pipelines / total_workflows, 2)
                        if total_workflows > 0
                        else 0
                    ),
                    "avg_stages_per_workflow": (
                        round(total_stages / total_workflows, 2)
                        if total_workflows > 0
                        else 0
                    ),
                },
                "by_company": company_stats,
            }
        )
