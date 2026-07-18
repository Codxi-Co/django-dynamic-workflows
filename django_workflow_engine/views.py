"""API views for django_workflow_engine."""

import logging
from typing import Any, Dict

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from approval_workflow.choices import RoleSelectionStrategy
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .choices import ApprovalTypes, TransitionRejectBehavior
from .models import (
    ModelStatus,
    ModelStatusConfiguration,
    Status,
    StatusAttachment,
    StatusHistory,
    StatusTransition,
    WorkFlow,
    WorkflowAction,
    WorkflowAttachment,
    WorkflowConfiguration,
    WorkflowStatusNode,
    validate_approval_configuration_payload,
)
from .serializers import (
    ModelStatusConfigurationSerializer,
    ModelStatusSerializer,
    PerformTransitionSerializer,
    RejectTransitionSerializer,
    SetStatusSerializer,
    StatusActionSerializer,
    StatusAttachmentSerializer,
    StatusHistorySerializer,
    StatusSerializer,
    StatusTransitionSerializer,
    WorkflowApprovalSerializer,
    WorkflowAttachmentSerializer,
    WorkFlowDetailSerializer,
    WorkFlowListSerializer,
    WorkflowStatusNodeSerializer,
)
from .services import (
    approve_pending_transition,
    attach_workflow_to_object,
    get_available_transitions,
    get_current_status,
    get_status_attachment,
    get_workflow_attachment,
    is_model_workflow_enabled,
    perform_transition,
    reject_pending_transition,
    set_status,
    start_workflow_for_object,
)
from .settings import get_status_api_viewset_mixins
from .status_services import (
    action_option,
    create_status_flow_design,
    get_status_flow_design,
)

logger = logging.getLogger(__name__)
StatusAPIConfiguredMixins = get_status_api_viewset_mixins()


class StatusAuditViewSetMixin:
    """Default audit field handling for status API viewsets."""

    def perform_create(self, serializer):
        save_kwargs = {}
        model = serializer.Meta.model
        if hasattr(model, "created_by") and self.request.user.is_authenticated:
            save_kwargs["created_by"] = self.request.user
        if hasattr(model, "modified_by") and self.request.user.is_authenticated:
            save_kwargs["modified_by"] = self.request.user
        serializer.save(**save_kwargs)

    def perform_update(self, serializer):
        save_kwargs = {}
        model = serializer.Meta.model
        if hasattr(model, "modified_by") and self.request.user.is_authenticated:
            save_kwargs["modified_by"] = self.request.user
        serializer.save(**save_kwargs)


StatusAPIViewSetBase = type(
    "StatusAPIViewSetBase",
    (*StatusAPIConfiguredMixins, StatusAuditViewSetMixin, viewsets.ModelViewSet),
    {},
)


def _content_type_from_model_string(model_string):
    """Resolve app_label.model path used in status URLs."""
    try:
        app_label, model_name = model_string.split(".", 1)
    except ValueError:
        return None

    try:
        return ContentType.objects.get(app_label=app_label, model=model_name.lower())
    except ContentType.DoesNotExist:
        return None


def _status_option(status_obj, model_status=None):
    """Shape status data for frontend dropdowns."""
    return {
        "id": status_obj.id,
        "key": status_obj.key,
        "label": status_obj.name_en,
        "label_en": status_obj.name_en,
        "label_ar": status_obj.name_ar,
        "category": status_obj.category,
        "color": status_obj.color,
        "icon": status_obj.icon,
        "metadata": status_obj.metadata,
        "is_initial": model_status.is_initial if model_status else False,
        "is_terminal": model_status.is_terminal if model_status else False,
        "order": model_status.order if model_status else 0,
    }


class StatusModelOptionsView(APIView):
    """Return status dropdown data and attached workflow status data for a model."""

    def get(self, request, model):
        content_type = _content_type_from_model_string(model)
        if not content_type:
            return Response(
                {"error": "Invalid model. Use app_label.model_name"},
                status=status.HTTP_404_NOT_FOUND,
            )

        config = (
            ModelStatusConfiguration.objects.filter(content_type=content_type)
            .prefetch_related("model_statuses__status")
            .first()
        )
        workflow_id = request.query_params.get("workflow_id")
        workflow = None
        if workflow_id:
            workflow = WorkFlow.objects.filter(pk=workflow_id).first()
        elif config:
            workflow_config = WorkflowConfiguration.objects.filter(
                content_type=content_type
            ).first()
            workflow = workflow_config.default_workflow if workflow_config else None

        company_id = request.query_params.get("company_id") or (
            workflow.company_id if workflow else None
        )
        company_filter = Q()
        if company_id:
            company_filter = Q(status__company__isnull=True) | Q(
                status__company_id=company_id
            )
        model_statuses = []
        if config:
            model_statuses = list(
                config.model_statuses.select_related("status")
                .filter(company_filter, is_active=True, status__is_active=True)
                .order_by("order", "id")
            )

        status_options = [
            _status_option(model_status.status, model_status)
            for model_status in model_statuses
        ]

        scoped_statuses = Status.objects.filter(
            content_type=content_type, is_active=True
        )
        if company_id:
            scoped_statuses = scoped_statuses.filter(
                Q(company__isnull=True) | Q(company_id=company_id)
            )
        configured_ids = {item["id"] for item in status_options}
        for status_obj in scoped_statuses.order_by("key", "id"):
            if status_obj.id not in configured_ids:
                status_options.append(_status_option(status_obj))

        workflow_statuses = []
        if workflow:
            workflow_statuses = [
                {
                    "id": node.id,
                    "status_id": node.status_id,
                    "key": node.status.key,
                    "label": node.status.name_en,
                    "label_en": node.status.name_en,
                    "label_ar": node.status.name_ar,
                    "category": node.status.category,
                    "color": node.status.color,
                    "metadata": node.metadata,
                    "is_initial": node.is_initial,
                    "is_terminal": node.is_terminal,
                    "order": node.order,
                }
                for node in workflow.status_nodes.select_related("status")
                .filter(is_active=True)
                .order_by("order", "id")
            ]

        return Response(
            {
                "model": f"{content_type.app_label}.{content_type.model}",
                "content_type": content_type.id,
                "configuration_id": config.id if config else None,
                "statuses": status_options,
                "workflow": (
                    {
                        "id": workflow.id,
                        "name_en": workflow.name_en,
                        "name_ar": workflow.name_ar,
                    }
                    if workflow
                    else None
                ),
                "workflow_statuses": workflow_statuses,
            }
        )


class StatusTransitionDiagramView(APIView):
    """Return status nodes and transition edges for a model/workflow diagram."""

    def get(self, request, model):
        content_type = _content_type_from_model_string(model)
        if not content_type:
            return Response(
                {"error": "Invalid model. Use app_label.model_name"},
                status=status.HTTP_404_NOT_FOUND,
            )

        workflow = None
        workflow_id = request.query_params.get("workflow_id")
        if workflow_id:
            workflow = WorkFlow.objects.filter(pk=workflow_id).first()
        else:
            workflow_config = WorkflowConfiguration.objects.filter(
                content_type=content_type
            ).first()
            workflow = workflow_config.default_workflow if workflow_config else None

        if not workflow:
            return Response(
                {
                    "model": f"{content_type.app_label}.{content_type.model}",
                    "content_type": content_type.id,
                    "workflow": None,
                    "nodes": [],
                    "edges": [],
                }
            )

        nodes = [
            {
                "id": node.id,
                "status_id": node.status_id,
                "key": node.status.key,
                "label": node.status.name_en,
                "label_en": node.status.name_en,
                "label_ar": node.status.name_ar,
                "category": node.status.category,
                "color": node.status.color,
                "metadata": {**node.status.metadata, **node.metadata},
                "is_initial": node.is_initial,
                "is_terminal": node.is_terminal,
                "order": node.order,
                "actions": [
                    action_option(action)
                    for action in node.actions.filter(is_active=True).order_by(
                        "order", "id"
                    )
                ],
            }
            for node in workflow.status_nodes.select_related("status")
            .filter(is_active=True)
            .order_by("order", "id")
        ]
        edges = [
            {
                "id": transition.id,
                "key": transition.key,
                "label": transition.name_en,
                "label_en": transition.name_en,
                "label_ar": transition.name_ar,
                "source": transition.from_status_id,
                "target": transition.to_status_id,
                "from_status_id": transition.from_status.status_id,
                "to_status_id": transition.to_status.status_id,
                "approvals": (transition.approval_config or {}).get("approvals", []),
                "reject_behavior": transition.reject_behavior,
                "reject_to_status_id": (
                    transition.reject_to_status.status_id
                    if transition.reject_to_status
                    else None
                ),
                "metadata": transition.metadata,
                "actions": [
                    action_option(action)
                    for action in transition.actions.filter(is_active=True).order_by(
                        "order", "id"
                    )
                ],
            }
            for transition in workflow.status_transitions.select_related(
                "from_status__status", "to_status__status", "reject_to_status__status"
            )
            .filter(is_active=True)
            .order_by("order", "id")
        ]

        return Response(
            {
                "model": f"{content_type.app_label}.{content_type.model}",
                "content_type": content_type.id,
                "workflow": {
                    "id": workflow.id,
                    "name_en": workflow.name_en,
                    "name_ar": workflow.name_ar,
                },
                "nodes": nodes,
                "edges": edges,
                "diagram": {"nodes": nodes, "edges": edges},
            }
        )


def _status_full_flow_response(content_type, workflow=None):
    """Build the complete status/workflow design payload for one model."""
    config = (
        ModelStatusConfiguration.objects.filter(content_type=content_type)
        .select_related("default_status")
        .prefetch_related("model_statuses__status")
        .first()
    )
    if not workflow:
        workflow_config = WorkflowConfiguration.objects.filter(
            content_type=content_type
        ).first()
        workflow = workflow_config.default_workflow if workflow_config else None

    statuses = []
    if config:
        statuses = [
            _status_option(model_status.status, model_status)
            for model_status in config.model_statuses.select_related("status")
            .filter(is_active=True)
            .order_by("order", "id")
        ]

    nodes = []
    transitions = []
    if workflow:
        nodes = [
            {
                "id": node.id,
                "status_id": node.status_id,
                "code": node.status.key,
                "label": node.status.name_en,
                "label_en": node.status.name_en,
                "label_ar": node.status.name_ar,
                "category": node.status.category,
                "color": node.status.color,
                "icon": node.status.icon,
                "metadata": {**node.status.metadata, **node.metadata},
                "is_initial": node.is_initial,
                "is_terminal": node.is_terminal,
                "order": node.order,
            }
            for node in workflow.status_nodes.select_related("status")
            .filter(is_active=True)
            .order_by("order", "id")
        ]
        transitions = [
            {
                "id": transition.id,
                "code": transition.key,
                "label": transition.name_en,
                "label_en": transition.name_en,
                "label_ar": transition.name_ar,
                "from": transition.from_status.status.key,
                "to": transition.to_status.status.key,
                "source": transition.from_status_id,
                "target": transition.to_status_id,
                "approvals": (transition.approval_config or {}).get("approvals", []),
                "reject_behavior": transition.reject_behavior,
                "reject_to": (
                    transition.reject_to_status.status.key
                    if transition.reject_to_status
                    else None
                ),
                "permission_codename": transition.permission_codename,
                "metadata": transition.metadata,
                "order": transition.order,
                "is_active": transition.is_active,
            }
            for transition in workflow.status_transitions.select_related(
                "from_status__status", "to_status__status", "reject_to_status__status"
            )
            .filter(is_active=True)
            .order_by("order", "id")
        ]

    return {
        "model": f"{content_type.app_label}.{content_type.model}",
        "content_type": content_type.id,
        "configuration": (
            {
                "id": config.id,
                "status_field": config.status_field,
                "default_status": config.default_status_id,
                "auto_create_attachment": config.auto_create_attachment,
                "allow_direct_change": config.allow_direct_change,
                "is_enabled": config.is_enabled,
            }
            if config
            else None
        ),
        "workflow": (
            {
                "id": workflow.id,
                "name_en": workflow.name_en,
                "name_ar": workflow.name_ar,
                "description": workflow.description,
                "status": workflow.status,
                "strategy": workflow.strategy,
                "is_active": workflow.is_active,
            }
            if workflow
            else None
        ),
        "statuses": statuses,
        "nodes": nodes,
        "transitions": transitions,
        "diagram": {"nodes": nodes, "edges": transitions},
    }


class StatusFlowDesignView(APIView):
    """Create or retrieve a full status workflow design for a model."""

    def get(self, request, model):
        workflow = None
        workflow_id = request.query_params.get("workflow_id")
        if workflow_id:
            workflow = WorkFlow.objects.filter(pk=workflow_id).first()
            if not workflow:
                return Response(
                    {"error": "workflow_id is invalid"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        try:
            result = get_status_flow_design(model, workflow=workflow)
        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(result)

    def post(self, request):
        try:
            result = create_status_flow_design(request.data, user=request.user)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)


class StatusEnabledModelsView(APIView):
    """Return model choices that have status configuration enabled."""

    def get(self, request):
        configurations = (
            ModelStatusConfiguration.objects.select_related(
                "content_type", "default_status"
            )
            .prefetch_related("model_statuses")
            .filter(is_enabled=True)
            .order_by("content_type__app_label", "content_type__model")
        )

        return Response(
            [
                {
                    "content_type": configuration.content_type_id,
                    "model": (
                        f"{configuration.content_type.app_label}."
                        f"{configuration.content_type.model}"
                    ),
                    "app_label": configuration.content_type.app_label,
                    "model_name": configuration.content_type.model,
                    "label": configuration.content_type.name,
                    "configuration_id": configuration.id,
                    "status_field": configuration.status_field,
                    "default_status": configuration.default_status_id,
                    "statuses_count": configuration.model_statuses.filter(
                        is_active=True
                    ).count(),
                }
                for configuration in configurations
            ]
        )


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
            instance=attachment.target,
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

    @action(detail=True, methods=["get"])
    def transitions(self, request, pk=None):
        """Get available status transitions for the attached object."""
        attachment = self.get_object()
        if not attachment.target:
            return Response(
                {"error": "Target object not found"}, status=status.HTTP_404_NOT_FOUND
            )
        transitions = get_available_transitions(attachment.target, user=request.user)
        return Response(StatusTransitionSerializer(transitions, many=True).data)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        """Perform a status transition for the attached object."""
        attachment = self.get_object()
        if not attachment.target:
            return Response(
                {"error": "Target object not found"}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = PerformTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            status_attachment = perform_transition(
                attachment.target,
                serializer.validated_data["transition_key"],
                user=request.user,
                reason=serializer.validated_data.get("reason", ""),
                metadata=serializer.validated_data.get("metadata", {}),
            )
            attachment.refresh_from_db()
            return Response(
                {
                    "message": "Transition processed successfully",
                    "attachment": WorkflowAttachmentSerializer(attachment).data,
                    "status": (
                        StatusAttachmentSerializer(status_attachment).data
                        if status_attachment
                        else None
                    ),
                }
            )
        except Exception as e:
            logger.error(f"Error performing status transition: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def approve_transition(self, request, pk=None):
        """Submit an approval through the configured approval workflow."""
        attachment = self.get_object()
        if not attachment.target:
            return Response(
                {"error": "Target object not found"}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = WorkflowApprovalSerializer(
            data={
                "action": "approved",
                "reason": request.data.get("reason", ""),
                "form_data": request.data.get("form_data", {}),
            },
            instance=attachment.target,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        try:
            serializer.save()
            attachment.refresh_from_db()
            status_attachment = get_status_attachment(attachment.target)
            return Response(
                {
                    "message": "Transition approval processed",
                    "attachment": WorkflowAttachmentSerializer(attachment).data,
                    "status": StatusAttachmentSerializer(status_attachment).data,
                }
            )
        except Exception as e:
            logger.error(f"Error approving status transition: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def reject_transition(self, request, pk=None):
        """Submit rejection through the configured approval workflow."""
        attachment = self.get_object()
        if not attachment.target:
            return Response(
                {"error": "Target object not found"}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = RejectTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        metadata = serializer.validated_data.get("metadata", {})
        if serializer.validated_data.get("evidence"):
            metadata = {
                **metadata,
                "evidence": serializer.validated_data["evidence"],
            }
        reject_to_status = None
        reject_to_status_id = serializer.validated_data.get("reject_to_status_id")
        if reject_to_status_id:
            try:
                reject_to_status = Status.objects.get(pk=reject_to_status_id)
            except Status.DoesNotExist:
                return Response(
                    {"error": "reject_to_status_id is invalid"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        attachment.metadata = {
            **(attachment.metadata or {}),
            "_status_transition_rejection": {
                "metadata": metadata,
                "reject_to_status_id": (
                    reject_to_status.id if reject_to_status else None
                ),
            },
        }
        attachment.save(update_fields=["metadata", "modified_at"])
        approval_serializer = WorkflowApprovalSerializer(
            data={
                "action": "rejected",
                "reason": serializer.validated_data.get("reason", ""),
            },
            instance=attachment.target,
            context={"request": request},
        )
        approval_serializer.is_valid(raise_exception=True)
        try:
            approval_serializer.save()
            attachment.refresh_from_db()
            status_attachment = get_status_attachment(attachment.target)
            return Response(
                {
                    "message": "Pending transition rejected",
                    "attachment": WorkflowAttachmentSerializer(attachment).data,
                    "status": (
                        StatusAttachmentSerializer(status_attachment).data
                        if status_attachment
                        else None
                    ),
                }
            )
        except Exception as e:
            logger.error(f"Error rejecting status transition: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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


class StatusViewSet(StatusAPIViewSetBase):
    """ViewSet for creating and managing reusable business statuses."""

    queryset = Status.objects.all()
    serializer_class = StatusSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        company_id = self.request.query_params.get("company_id")
        if company_id:
            queryset = queryset.filter(company_id=company_id)
        model = self.request.query_params.get("model")
        if model:
            content_type_obj = _content_type_from_model_string(model)
            if content_type_obj:
                queryset = queryset.filter(content_type=content_type_obj)
        content_type = self.request.query_params.get("content_type")
        if content_type:
            if content_type.isdigit():
                queryset = queryset.filter(content_type_id=content_type)
            else:
                content_type_obj = _content_type_from_model_string(content_type)
                if content_type_obj:
                    queryset = queryset.filter(content_type=content_type_obj)
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")
        return queryset


class ModelStatusConfigurationViewSet(StatusAPIViewSetBase):
    """ViewSet for configuring which statuses a model can use."""

    queryset = ModelStatusConfiguration.objects.prefetch_related(
        "model_statuses__status"
    )
    serializer_class = ModelStatusConfigurationSerializer


class ModelStatusViewSet(StatusAPIViewSetBase):
    """ViewSet for attaching statuses to a model status configuration."""

    queryset = ModelStatus.objects.select_related("configuration", "status")
    serializer_class = ModelStatusSerializer


class WorkflowStatusNodeViewSet(StatusAPIViewSetBase):
    """ViewSet for workflow-specific status nodes."""

    queryset = WorkflowStatusNode.objects.select_related("workflow", "status")
    serializer_class = WorkflowStatusNodeSerializer


class StatusTransitionViewSet(StatusAPIViewSetBase):
    """ViewSet for configuring status graph transitions."""

    queryset = StatusTransition.objects.select_related(
        "workflow", "from_status__status", "to_status__status", "reject_to_status"
    )
    serializer_class = StatusTransitionSerializer


class StatusActionViewSet(StatusAPIViewSetBase):
    """Manage actions attached to workflow status nodes and transitions."""

    queryset = WorkflowAction.objects.select_related(
        "status_node", "status_node__status", "transition"
    )
    serializer_class = StatusActionSerializer

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .filter(Q(status_node__isnull=False) | Q(transition__isnull=False))
        )
        status_node = self.request.query_params.get("status_node")
        transition = self.request.query_params.get("transition")
        workflow = self.request.query_params.get("workflow")
        action_type = self.request.query_params.get("action_type")
        if status_node:
            queryset = queryset.filter(status_node_id=status_node)
        if transition:
            queryset = queryset.filter(transition_id=transition)
        if workflow:
            queryset = queryset.filter(
                Q(status_node__workflow_id=workflow)
                | Q(transition__workflow_id=workflow)
            )
        if action_type:
            queryset = queryset.filter(action_type=action_type)
        return queryset.order_by("status_node_id", "transition_id", "order", "id")


class StatusAttachmentViewSet(StatusAPIViewSetBase):
    """ViewSet for current status attachments on arbitrary objects."""

    queryset = StatusAttachment.objects.select_related("status", "content_type")
    serializer_class = StatusAttachmentSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        content_type = self.request.query_params.get("content_type")
        if content_type:
            try:
                app_label, model_name = content_type.split(".")
                ct = ContentType.objects.get(app_label=app_label, model=model_name)
                queryset = queryset.filter(content_type=ct)
            except (ValueError, ContentType.DoesNotExist):
                pass
        return queryset

    @action(detail=True, methods=["post"])
    def set_status(self, request, pk=None):
        """Set this object's status directly, when allowed by configuration."""
        attachment = self.get_object()
        if not attachment.target:
            return Response(
                {"error": "Target object not found"}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = SetStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            target_status = Status.objects.get(
                pk=serializer.validated_data["status_id"]
            )
        except Status.DoesNotExist:
            return Response(
                {"error": "status_id is invalid"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            updated = set_status(
                attachment.target,
                target_status,
                user=request.user,
                reason=serializer.validated_data.get("reason", ""),
                metadata=serializer.validated_data.get("metadata", {}),
            )
            return Response(StatusAttachmentSerializer(updated).data)
        except Exception as e:
            logger.error(f"Error setting status: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StatusHistoryViewSet(StatusAPIViewSetBase):
    """Read-only status history API."""

    queryset = StatusHistory.objects.select_related(
        "from_status", "to_status", "workflow", "transition", "content_type"
    )
    serializer_class = StatusHistorySerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        model = self.request.query_params.get("model") or self.request.query_params.get(
            "content_type"
        )
        if model:
            content_type = _content_type_from_model_string(model)
            if content_type:
                queryset = queryset.filter(content_type=content_type)
        object_id = self.request.query_params.get("object_id")
        if object_id:
            queryset = queryset.filter(object_id=str(object_id))
        workflow = self.request.query_params.get("workflow")
        if workflow:
            queryset = queryset.filter(workflow_id=workflow)
        transition = self.request.query_params.get("transition")
        if transition:
            queryset = queryset.filter(transition_id=transition)
        company_id = self.request.query_params.get("company_id")
        if company_id:
            queryset = queryset.filter(to_status__company_id=company_id)
        return queryset


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
            data=request.data, instance=obj, context={"request": request}
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
                    ApprovalTypes.ASSIGNED: 0,
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
                ApprovalTypes.ASSIGNED: 0,
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
