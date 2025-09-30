"""Serializers for django_workflow_engine."""

import logging
from typing import Any, Dict, List, Optional, Union

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from approval_workflow.choices import ApprovalStatus, RoleSelectionStrategy
from approval_workflow.models import ApprovalInstance
from approval_workflow.services import advance_flow, get_current_approval_for_object
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .choices import ApprovalTypes
from .logging_utils import log_serializer_validation, serializers_logger
from .models import Pipeline, Stage, WorkFlow, WorkflowAttachment
from .services import create_workflow, get_workflow_attachment

logger = logging.getLogger(__name__)


class GenericForeignKeyField(serializers.Field):
    """Custom field for handling GenericForeignKey serialization."""

    def to_representation(self, value):
        """Return a representation of the generic foreign key object."""
        if value is None:
            return None
        return {"id": value.pk, "type": value._meta.label, "name": str(value)}

    def to_internal_value(self, data):
        """Convert the input data to internal value."""
        # This would be used for write operations
        # For now, we'll make it read-only
        raise serializers.ValidationError("This field is read-only.")


class WorkflowApprovalSerializer(serializers.Serializer):
    """
    Generic serializer for approving/rejecting workflow stages.

    Handles approve, reject, delegate, and resubmission actions for any object
    attached to a workflow through WorkflowAttachment.

    Usage:
        serializer = WorkflowApprovalSerializer(
            instance=my_object,  # The object with attached workflow
            data={'action': 'approved', 'form_data': {...}},
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()

    Note: The 'instance' parameter is required and represents the object
    that has the workflow attached to it (not the WorkflowAttachment itself).
    """

    action = serializers.ChoiceField(
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.APPROVED,
        help_text=_("Action to perform on the workflow stage"),
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text=_("Reason for rejection, delegation, or resubmission"),
    )
    form_data = serializers.JSONField(
        required=False,
        default=dict,
        help_text=_("Form data for approval (if required by stage)"),
    )
    user_id = serializers.IntegerField(
        required=False,
        help_text=_("User ID for delegation (required for delegation action)"),
    )
    stage_id = serializers.IntegerField(
        required=False,
        help_text=_("Stage ID for resubmission (required for resubmission action)"),
    )

    def validate_action(self, value):
        """Validate the action is appropriate for current workflow state."""
        if not self.instance:
            raise serializers.ValidationError(
                _(
                    "Object instance is required for workflow approval. "
                    "Use: WorkflowApprovalSerializer(instance=my_object, data={...})"
                )
            )

        attachment = get_workflow_attachment(self.instance)
        if not attachment:
            raise serializers.ValidationError(_("No workflow attached to this object"))

        if attachment.status != "in_progress":
            raise serializers.ValidationError(
                _("Workflow is not in progress (current status: {status})").format(
                    status=attachment.status
                )
            )

        # Check if there are current approval instances
        current_approval = get_current_approval_for_object(self.instance)
        if not current_approval:
            raise serializers.ValidationError(
                _("No current approval step found for this object")
            )

        # Log validation
        serializers_logger.log_action(
            "workflow_approval_validation",
            approval_action=value,
            object_type=self.instance._meta.label,
            object_id=str(self.instance.pk),
        )

        return value

    def validate(self, attrs):
        """Validate action-specific requirements."""
        action = attrs.get("action")
        user = self.context.get("request").user if self.context.get("request") else None

        try:
            if action == ApprovalStatus.REJECTED:
                self._validate_rejection(attrs)
            elif action == ApprovalStatus.NEEDS_RESUBMISSION:
                self._validate_resubmission(attrs)
            elif action == ApprovalStatus.DELEGATED:
                self._validate_delegation(attrs)
            elif action == ApprovalStatus.APPROVED:
                self._validate_approval(attrs)

            # Log successful validation
            log_serializer_validation(
                serializer_name="WorkflowApprovalSerializer",
                is_valid=True,
                user_id=user.id if user else None,
            )

            return attrs

        except serializers.ValidationError as e:
            # Log validation errors
            log_serializer_validation(
                serializer_name="WorkflowApprovalSerializer",
                is_valid=False,
                errors=e.detail,
                user_id=user.id if user else None,
            )
            raise

    def _validate_rejection(self, attrs):
        """Validate rejection requirements."""
        if not attrs.get("reason"):
            raise serializers.ValidationError(
                {"reason": _("Reason is required for rejection")}
            )

    def _validate_resubmission(self, attrs):
        """Validate resubmission requirements."""
        if not attrs.get("reason"):
            raise serializers.ValidationError(
                {"reason": "Reason is required for resubmission"}
            )

        # stage_id is optional - if not provided, resubmission goes to current stage
        stage_id = attrs.get("stage_id")
        if stage_id:
            # Validate stage exists and belongs to current workflow
            try:
                attachment = get_workflow_attachment(self.instance)
                stage = Stage.objects.get(pk=stage_id)

                # Check if stage belongs to current workflow
                if stage.pipeline.workflow.id != attachment.workflow.id:
                    raise serializers.ValidationError(
                        {"stage_id": "Stage does not belong to current workflow"}
                    )

            except Stage.DoesNotExist:
                raise serializers.ValidationError({"stage_id": "Invalid stage ID"})

    def _validate_delegation(self, attrs):
        """Validate delegation requirements."""
        # user_id is optional for delegation - if not provided, the approval workflow
        # will handle the delegation logic internally
        user_id = attrs.get("user_id")
        if user_id:
            # Validate user exists only if user_id is provided
            from django.contrib.auth import get_user_model

            User = get_user_model()

            try:
                User.objects.get(pk=user_id)
            except User.DoesNotExist:
                raise serializers.ValidationError({"user_id": "Invalid user ID"})

    def _validate_approval(self, attrs):
        """Validate approval requirements."""
        # Check if current stage requires form data
        attachment = get_workflow_attachment(self.instance)
        if attachment and attachment.current_stage:
            current_approval = get_current_approval_for_object(self.instance)

            # Handle both single instance and list/queryset
            if hasattr(current_approval, "__iter__") and not isinstance(
                current_approval, (str, bytes)
            ):
                current_approval = (
                    list(current_approval)[0] if current_approval else None
                )

            if current_approval and current_approval.form:
                # Form is required - validate form_data is provided
                form_data = attrs.get("form_data", {})
                if not form_data:
                    raise serializers.ValidationError(
                        {"form_data": "Form data is required for this approval step"}
                    )

    def save(self, **kwargs):
        """Process the workflow approval action."""
        if not self.instance:
            raise ValueError("Object instance is required for workflow approval")

        validated_data = self.validated_data
        action = validated_data["action"]
        user = self.context.get("request").user if self.context.get("request") else None

        # Log the approval action attempt
        attachment = get_workflow_attachment(self.instance)
        serializers_logger.log_approval_action(
            action=action.value if hasattr(action, "value") else str(action),
            workflow_id=attachment.workflow.id if attachment else None,
            stage=(
                attachment.current_stage.name_en
                if attachment and attachment.current_stage
                else "unknown"
            ),
            user_id=user.id if user else None,
            object_type=self.instance._meta.label,
            object_id=str(self.instance.pk),
        )

        try:
            with transaction.atomic():
                # Prepare resubmission steps if needed
                resubmission_steps = None
                if action == ApprovalStatus.NEEDS_RESUBMISSION:
                    resubmission_steps = self._prepare_resubmission_steps(
                        validated_data
                    )

                # Prepare delegation user if needed
                delegate_to_user = None
                if action == ApprovalStatus.DELEGATED:
                    delegate_to_user = self._get_delegation_user(validated_data)

                # Use approval_workflow's advance_flow to handle the action
                advance_flow(
                    instance=self.instance,
                    action=action,
                    user=user,
                    comment=validated_data.get("reason", ""),
                    form_data=validated_data.get("form_data"),
                    delegate_to=delegate_to_user,
                    resubmission_steps=resubmission_steps,
                )

                # Update workflow attachment status if needed
                self._update_workflow_attachment(action, user)

                return self.instance

        except Exception as e:
            logger.error(f"Error processing workflow approval action: {str(e)}")
            raise serializers.ValidationError(
                {"error": f"Failed to process approval action: {str(e)}"}
            )

    def _prepare_resubmission_steps(self, validated_data):
        """Prepare resubmission steps for the specified stage."""
        stage_id = validated_data["stage_id"]

        try:
            stage = Stage.objects.select_related("pipeline__workflow").get(pk=stage_id)

            # Get current approval flow
            current_approval = get_current_approval_for_object(self.instance)
            if hasattr(current_approval, "__iter__") and not isinstance(
                current_approval, (str, bytes)
            ):
                current_approval = (
                    list(current_approval)[0] if current_approval else None
                )

            if not current_approval:
                raise ValueError("No current approval found for resubmission")

            # Build resubmission steps using workflow handler pattern
            from django.contrib.auth import get_user_model

            from .handlers import ApprovalStepBuilder

            User = get_user_model()
            created_by = getattr(self.instance, "created_by", None)
            if not created_by:
                # Fallback to request user
                created_by = (
                    self.context.get("request").user
                    if self.context.get("request")
                    else None
                )

            if created_by and not isinstance(created_by, User):
                created_by = User.objects.get(pk=created_by)

            builder = ApprovalStepBuilder(stage, created_by)
            resubmission_steps = builder.build_steps()

            # Add resubmission stage_id to each step's extra_fields
            for step in resubmission_steps:
                if "extra_fields" not in step:
                    step["extra_fields"] = {}
                step["extra_fields"]["resubmission_stage_id"] = stage_id

            return resubmission_steps

        except Stage.DoesNotExist:
            raise ValueError(f"Stage with ID {stage_id} not found")
        except Exception as e:
            raise ValueError(f"Error preparing resubmission steps: {str(e)}")

    def _get_delegation_user(self, validated_data):
        """Get the user for delegation."""
        user_id = validated_data["user_id"]

        from django.contrib.auth import get_user_model

        User = get_user_model()

        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise ValueError(f"User with ID {user_id} not found")

    def _update_workflow_attachment(self, action, user=None):
        """Update workflow attachment status based on action."""
        attachment = get_workflow_attachment(self.instance)
        if not attachment:
            return

        if action == ApprovalStatus.REJECTED:
            attachment.status = "rejected"
            attachment.save()

            # Call workflow hooks
            from .choices import ActionType
            from .services import trigger_workflow_event

            trigger_workflow_event(
                attachment,
                ActionType.AFTER_REJECT,
                target_object=self.instance,
                stage=attachment.current_stage,
                user=user,
            )

        # Note: Approval progression to next stage is handled by the approval workflow
        # through handlers (on_final_approve, etc.) - no automatic progression here


class WorkflowAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for WorkflowAttachment model."""

    progress_info = serializers.SerializerMethodField()
    target_object_repr = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowAttachment
        fields = [
            "id",
            "workflow",
            "content_type",
            "object_id",
            "current_stage",
            "current_pipeline",
            "status",
            "started_at",
            "completed_at",
            "started_by",
            "progress_info",
            "target_object_repr",
            "metadata",
        ]
        read_only_fields = [
            "content_type",
            "object_id",
            "started_at",
            "completed_at",
            "progress_info",
            "target_object_repr",
        ]

    @extend_schema_field(serializers.DictField)
    def get_progress_info(self, obj):
        """Get detailed progress information."""
        return obj.get_progress_info()

    @extend_schema_field(serializers.CharField)
    def get_target_object_repr(self, obj):
        """Get string representation of target object."""
        return str(obj.target) if obj.target else None


class StageDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for Stage model with approval configuration."""

    approvals_count = serializers.SerializerMethodField()
    has_approvals = serializers.SerializerMethodField()
    approval_configuration = serializers.SerializerMethodField()

    class Meta:
        model = Stage
        fields = [
            "id",
            "name_en",
            "name_ar",
            "order",
            "is_active",
            "stage_info",
            "approvals_count",
            "has_approvals",
            "approval_configuration",
            "created_at",
            "modified_at",
        ]

    @extend_schema_field(serializers.IntegerField)
    def get_approvals_count(self, obj):
        """Get number of approval configurations in this stage."""
        approvals = obj.stage_info.get("approvals", [])
        return len(approvals)

    @extend_schema_field(serializers.BooleanField)
    def get_has_approvals(self, obj):
        """Check if stage has any approval configurations."""
        approvals = obj.stage_info.get("approvals", [])
        return len(approvals) > 0

    @extend_schema_field(serializers.DictField)
    def get_approval_configuration(self, obj):
        """Get detailed approval configuration for this stage."""
        approvals = obj.stage_info.get("approvals", [])

        # Enrich approval data with readable information
        enriched_approvals = []
        for approval in approvals:
            enriched_approval = approval.copy()

            # Add human-readable approval type
            approval_type = approval.get("approval_type", "")
            if approval_type == ApprovalTypes.ROLE:
                enriched_approval["approval_type_display"] = "Role-based Approval"
            elif approval_type == ApprovalTypes.USER:
                enriched_approval["approval_type_display"] = "User-specific Approval"
            elif approval_type == ApprovalTypes.SELF:
                enriched_approval["approval_type_display"] = "Self Approval"
            else:
                enriched_approval["approval_type_display"] = approval_type

            # Add human-readable role selection strategy
            strategy = approval.get("role_selection_strategy", "")
            if strategy == RoleSelectionStrategy.ANYONE:
                enriched_approval["strategy_display"] = "Any user with role can approve"
            elif strategy == RoleSelectionStrategy.CONSENSUS:
                enriched_approval["strategy_display"] = (
                    "All users with role must approve"
                )
            elif strategy == RoleSelectionStrategy.ROUND_ROBIN:
                enriched_approval["strategy_display"] = (
                    "Rotate approval among role users"
                )
            else:
                enriched_approval["strategy_display"] = strategy

            enriched_approvals.append(enriched_approval)

        return {
            "approvals": enriched_approvals,
            "color": obj.stage_info.get("color", "#3498db"),
            "total_approvals": len(enriched_approvals),
        }


class PipelineDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for Pipeline model with stages."""

    stages = StageDetailSerializer(many=True, read_only=True)
    stages_count = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()

    department = GenericForeignKeyField(read_only=True)

    class Meta:
        model = Pipeline
        fields = [
            "id",
            "name_en",
            "name_ar",
            "order",
            "department",
            "department_name",
            "stages",
            "stages_count",
            "created_at",
            "modified_at",
        ]

    @extend_schema_field(serializers.IntegerField)
    def get_stages_count(self, obj):
        """Get number of stages in this pipeline."""
        return obj.stages.count()

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_department_name(self, obj):
        """Get department name if available."""
        return obj.department_name


class WorkFlowDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for WorkFlow model with pipelines and stages."""

    pipelines = PipelineDetailSerializer(many=True, read_only=True)
    pipelines_count = serializers.SerializerMethodField()
    total_stages_count = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    workflow_summary = serializers.SerializerMethodField()

    class Meta:
        model = WorkFlow
        fields = [
            "id",
            "name_en",
            "name_ar",
            "company",
            "company_name",
            "is_active",
            "description",
            "pipelines",
            "pipelines_count",
            "total_stages_count",
            "workflow_summary",
            "created_at",
            "modified_at",
        ]

    @extend_schema_field(serializers.IntegerField)
    def get_pipelines_count(self, obj):
        """Get number of pipelines in this workflow."""
        return obj.pipelines.count()

    @extend_schema_field(serializers.IntegerField)
    def get_total_stages_count(self, obj):
        """Get total number of stages across all pipelines."""
        return sum(pipeline.stages.count() for pipeline in obj.pipelines.all())

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_company_name(self, obj):
        """Get company name if available."""
        return obj.company.username if obj.company else None

    @extend_schema_field(serializers.DictField)
    def get_workflow_summary(self, obj):
        """Get workflow summary information."""
        pipelines = obj.pipelines.prefetch_related("stages").all()

        summary = {
            "total_pipelines": len(pipelines),
            "total_stages": 0,
            "total_approvals": 0,
            "pipeline_breakdown": [],
        }

        for pipeline in pipelines:
            stages = pipeline.stages.all()
            pipeline_approvals = 0

            for stage in stages:
                approvals = stage.stage_info.get("approvals", [])
                pipeline_approvals += len(approvals)
                summary["total_approvals"] += len(approvals)

            summary["total_stages"] += len(stages)
            summary["pipeline_breakdown"].append(
                {
                    "pipeline_name": pipeline.name_en,
                    "pipeline_order": pipeline.order,
                    "stages_count": len(stages),
                    "approvals_count": pipeline_approvals,
                }
            )

        return summary


class WorkFlowListSerializer(serializers.ModelSerializer):
    """Simplified serializer for WorkFlow list view."""

    pipelines_count = serializers.SerializerMethodField()
    total_stages_count = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()

    class Meta:
        model = WorkFlow
        fields = [
            "id",
            "name_en",
            "name_ar",
            "company",
            "company_name",
            "is_active",
            "description",
            "pipelines_count",
            "total_stages_count",
            "created_at",
            "modified_at",
        ]

    @extend_schema_field(serializers.IntegerField)
    def get_pipelines_count(self, obj):
        """Get number of pipelines in this workflow."""
        return obj.pipelines.count()

    @extend_schema_field(serializers.IntegerField)
    def get_total_stages_count(self, obj):
        """Get total number of stages across all pipelines."""
        return sum(pipeline.stages.count() for pipeline in obj.pipelines.all())

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_company_name(self, obj):
        """Get company name if available."""
        return obj.company.username if obj.company else None


class PipelineSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating Pipeline with auto-generated stages.

    Note: Override fields in your implementation as needed.
    created_by is automatically set from request context.
    """

    number_of_stages = serializers.IntegerField(
        write_only=True,
        required=False,
        min_value=1,
        help_text=_("Number of stages to auto-create for this pipeline"),
    )

    class Meta:
        model = Pipeline
        fields = "__all__"
        read_only_fields = [
            "id",
            "created_by",
            "modified_by",
            "created_at",
            "modified_at",
            "workflow",
        ]
        extra_kwargs = {
            "company": {"required": False},
            "workflow": {"required": False},  # Set by parent WorkFlowSerializer
        }

    def create(self, validated_data):
        """Create pipeline with auto-generated stages."""
        number_of_stages = validated_data.pop("number_of_stages", 0)
        pipeline = Pipeline.objects.create(**validated_data)

        # Auto-create stages if number_of_stages is provided
        if number_of_stages > 0:
            for i in range(1, number_of_stages + 1):
                Stage.objects.create(
                    pipeline=pipeline,
                    name_en=f"Stage {i}",
                    name_ar=f"المرحلة {i}",
                    order=i,
                    stage_info={"approvals": [], "color": "#3498db"},
                )

        return pipeline


class WorkFlowSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating WorkFlow with nested pipelines.

    Note: Override fields in your implementation as needed.
    created_by is automatically set from request context.
    company is automatically set from context if not provided.
    """

    pipelines = PipelineSerializer(many=True, required=False)

    class Meta:
        model = WorkFlow
        fields = "__all__"
        read_only_fields = [
            "id",
            "created_by",
            "modified_by",
            "created_at",
            "modified_at",
            "is_active",
        ]
        extra_kwargs = {
            "company": {"required": False},
        }

    def create(self, validated_data):
        """Create workflow with nested pipelines and stages using service function."""
        pipelines_data = validated_data.pop("pipelines", [])

        # Get company from context if not provided
        company = validated_data.pop("company", None)
        if not company:
            company = self.context.get("company_user")

        # Get created_by from request
        request = self.context.get("request")
        created_by = request.user if request else company

        # Get other workflow fields
        name_en = validated_data.pop("name_en")
        name_ar = validated_data.pop("name_ar", name_en)
        description = validated_data.pop("description", "")
        is_active = validated_data.pop("is_active", True)

        # Use the existing create_workflow service function
        workflow = create_workflow(
            company=company,
            name_en=name_en,
            name_ar=name_ar,
            created_by=created_by,
            pipelines_data=pipelines_data,
        )

        # Update additional fields if provided
        if description:
            workflow.description = description
        if is_active is not None:
            workflow.is_active = is_active
        workflow.save()

        return workflow

    def to_representation(self, instance):
        """Return detailed representation after creation."""
        return {
            "id": instance.id,
            "name_en": instance.name_en,
            "name_ar": instance.name_ar,
            "company": instance.company_id,
            "is_active": instance.is_active,
            "description": instance.description,
            "pipelines_count": instance.pipelines.count(),
            "total_stages_count": sum(
                pipeline.stages.count() for pipeline in instance.pipelines.all()
            ),
        }


class StageSerializer(serializers.ModelSerializer):
    """Serializer for updating Stage configurations including approvals.

    Note: Override fields in your implementation as needed.
    is_active is auto-managed based on approval configuration.
    """

    stage_info = serializers.JSONField(required=False)

    class Meta:
        model = Stage
        fields = "__all__"
        read_only_fields = [
            "id",
            "created_by",
            "modified_by",
            "created_at",
            "modified_at",
            "is_active",
            "pipeline",
        ]
        extra_kwargs = {
            "company": {"required": False},
            "pipeline": {"required": False},  # Set by parent PipelineSerializer
        }

    def validate(self, attrs):
        """Validate pipeline is provided either from URL or body."""
        # If updating existing instance, pipeline is already set
        if self.instance:
            return attrs

        # For create operations, check pipeline from context (URL) or body
        pipeline = attrs.get("pipeline")

        # Check if pipeline is in context (from URL kwargs)
        if not pipeline and self.context.get("view"):
            view = self.context["view"]
            pipeline_id = view.kwargs.get("pipeline") or view.kwargs.get("pipeline_pk")
            if pipeline_id:
                try:
                    from .models import Pipeline

                    pipeline = Pipeline.objects.get(id=pipeline_id)
                    attrs["pipeline"] = pipeline
                except Pipeline.DoesNotExist:
                    raise serializers.ValidationError(
                        {"pipeline": f"Pipeline with id {pipeline_id} does not exist"}
                    )

        # If still no pipeline, it's required
        if not pipeline:
            raise serializers.ValidationError(
                {
                    "pipeline": "Pipeline is required. Provide it in the request body or URL."
                }
            )

        return attrs

    def validate_stage_info(self, value):
        """Validate stage_info structure."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("stage_info must be a dictionary")

        # Validate approvals structure if present
        approvals = value.get("approvals", [])
        if not isinstance(approvals, list):
            raise serializers.ValidationError("approvals must be a list")

        # Normalize approval_type to lowercase for case-insensitive comparison
        valid_approval_types = [
            ApprovalTypes.ROLE.lower(),
            ApprovalTypes.USER.lower(),
            ApprovalTypes.SELF.lower(),
        ]

        for approval in approvals:
            if not isinstance(approval, dict):
                raise serializers.ValidationError("Each approval must be a dictionary")

            approval_type = approval.get("approval_type", "").lower()

            # Normalize to lowercase in the data
            if approval_type:
                approval["approval_type"] = approval_type

            if approval_type not in valid_approval_types:
                raise serializers.ValidationError(
                    f"Invalid approval_type: {approval.get('approval_type')}. "
                    f"Must be one of: role, user, self (case-insensitive)"
                )

            # Validate role-based approval
            if approval_type == ApprovalTypes.ROLE.lower():
                if "user_role" not in approval:
                    raise serializers.ValidationError(
                        "user_role is required for ROLE approval type"
                    )
                strategy = approval.get("role_selection_strategy", "").lower()

                # Normalize strategy to lowercase
                if strategy:
                    approval["role_selection_strategy"] = strategy

                # Valid strategies from approval_workflow
                valid_strategies = [
                    "anyone",
                    "consensus",
                    "round_robin",
                    "random",
                    "supervisor",
                ]
                if strategy and strategy not in valid_strategies:
                    raise serializers.ValidationError(
                        f"Invalid strategy: {approval.get('role_selection_strategy')}. "
                        f"Must be one of: {', '.join(valid_strategies)} (case-insensitive)"
                    )

            # Validate user-based approval
            elif approval_type == ApprovalTypes.USER.lower():
                if "approval_user" not in approval:
                    raise serializers.ValidationError(
                        "approval_user is required for USER approval type"
                    )

        return value

    def update(self, instance, validated_data):
        """Update stage with new configuration and auto-activate/deactivate."""
        stage_info = validated_data.get("stage_info")
        old_is_active = instance.is_active

        if stage_info:
            # Merge with existing stage_info
            existing_info = instance.stage_info or {}
            existing_info.update(stage_info)
            validated_data["stage_info"] = existing_info

            # Auto-activate/deactivate based on approvals
            approvals = existing_info.get("approvals", [])
            if approvals:
                # Has approvals - activate if not already active
                if not old_is_active:
                    validated_data["is_active"] = True
                    serializers_logger.log_action(
                        "stage_auto_activated",
                        stage_id=instance.id,
                        stage_name=instance.name_en,
                        reason="approvals_configured",
                    )
            else:
                # No approvals - deactivate if currently active
                if old_is_active:
                    validated_data["is_active"] = False
                    serializers_logger.log_action(
                        "stage_auto_deactivated",
                        stage_id=instance.id,
                        stage_name=instance.name_en,
                        reason="no_approvals_configured",
                    )

        updated_instance = super().update(instance, validated_data)

        # Trigger workflow status update
        if updated_instance.pipeline and updated_instance.pipeline.workflow:
            updated_instance.pipeline.workflow.update_active_status()

        return updated_instance
