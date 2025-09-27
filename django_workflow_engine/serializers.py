"""Serializers for django_workflow_engine."""

import logging
from typing import Any, Dict, List, Optional, Union

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from approval_workflow.choices import ApprovalStatus
from approval_workflow.models import ApprovalInstance
from approval_workflow.services import advance_flow, get_current_approval_for_object
from rest_framework import serializers

from .logging_utils import log_serializer_validation, serializers_logger
from .models import Stage, WorkflowAttachment
from .services import get_workflow_attachment

logger = logging.getLogger(__name__)


class WorkflowApprovalSerializer(serializers.Serializer):
    """
    Generic serializer for approving/rejecting workflow stages.

    Handles approve, reject, delegate, and resubmission actions for any object
    attached to a workflow through WorkflowAttachment.
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

    def __init__(self, *args, **kwargs):
        """Initialize serializer with object instance."""
        self.object_instance = kwargs.pop("object_instance", None)
        super().__init__(*args, **kwargs)

    def validate_action(self, value):
        """Validate the action is appropriate for current workflow state."""
        if not self.object_instance:
            raise serializers.ValidationError(
                _("Object instance is required for workflow approval")
            )

        attachment = get_workflow_attachment(self.object_instance)
        if not attachment:
            raise serializers.ValidationError(_("No workflow attached to this object"))

        if attachment.status != "in_progress":
            raise serializers.ValidationError(
                _("Workflow is not in progress (current status: {status})").format(
                    status=attachment.status
                )
            )

        # Check if there are current approval instances
        current_approval = get_current_approval_for_object(self.object_instance)
        if not current_approval:
            raise serializers.ValidationError(
                _("No current approval step found for this object")
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
                attachment = get_workflow_attachment(self.object_instance)
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
        attachment = get_workflow_attachment(self.object_instance)
        if attachment and attachment.current_stage:
            current_approval = get_current_approval_for_object(self.object_instance)

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
        if not self.object_instance:
            raise ValueError("Object instance is required for workflow approval")

        validated_data = self.validated_data
        action = validated_data["action"]
        user = self.context.get("request").user if self.context.get("request") else None

        # Log the approval action attempt
        attachment = get_workflow_attachment(self.object_instance)
        serializers_logger.log_approval_action(
            action=action.value if hasattr(action, "value") else str(action),
            workflow_id=attachment.workflow.id if attachment else None,
            stage=(
                attachment.current_stage.name_en
                if attachment and attachment.current_stage
                else "unknown"
            ),
            user_id=user.id if user else None,
            object_type=self.object_instance._meta.label,
            object_id=str(self.object_instance.pk),
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
                    instance=self.object_instance,
                    action=action,
                    user=user,
                    comment=validated_data.get("reason", ""),
                    form_data=validated_data.get("form_data"),
                    delegate_to=delegate_to_user,
                    resubmission_steps=resubmission_steps,
                )

                # Update workflow attachment status if needed
                self._update_workflow_attachment(action)

                return self.object_instance

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
            current_approval = get_current_approval_for_object(self.object_instance)
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
            created_by = getattr(self.object_instance, "created_by", None)
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

    def _update_workflow_attachment(self, action):
        """Update workflow attachment status based on action."""
        attachment = get_workflow_attachment(self.object_instance)
        if not attachment:
            return

        if action == ApprovalStatus.REJECTED:
            attachment.status = "rejected"
            attachment.save()

            # Call workflow hooks
            from .services import _call_workflow_hook

            _call_workflow_hook(
                attachment,
                "after_reject_stage",
                self.object_instance,
                attachment.current_stage,
                attachment,
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

    def get_progress_info(self, obj):
        """Get detailed progress information."""
        return obj.get_progress_info()

    def get_target_object_repr(self, obj):
        """Get string representation of target object."""
        return str(obj.target) if obj.target else None
