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

from .choices import ActionType, ApprovalTypes
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


class WorkflowActionInputSerializer(serializers.Serializer):
    """
    Serializer for workflow action input data.

    Used to define the structure of custom actions when creating workflows,
    pipelines, or stages. This makes the API documentation clearer in Swagger.

    Example:
        {
            "action_type": "after_approve",
            "function_path": "myapp.actions.send_custom_approval",
            "parameters": {
                "template": "custom_approved",
                "recipients": ["creator", "manager@example.com"]
            },
            "order": 1,
            "is_active": true
        }
    """

    action_type = serializers.ChoiceField(
        choices=ActionType,
        help_text=_("The type of action trigger"),
    )
    function_path = serializers.CharField(
        max_length=255,
        help_text=_(
            "Dotted path to the action handler function (e.g., 'myapp.actions.send_email')"
        ),
    )
    parameters = serializers.JSONField(
        required=False,
        default=dict,
        help_text=_(
            "Parameters to pass to the action handler (e.g., template, recipients, subject)"
        ),
    )
    order = serializers.IntegerField(
        required=False,
        default=1,
        help_text=_("Execution order when multiple actions exist for the same trigger"),
    )
    is_active = serializers.BooleanField(
        required=False,
        default=True,
        help_text=_("Whether this action is active and should be executed"),
    )


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
        logger.info(
            f"Validating approval action - "
            f"action: {value}, "
            f"object: {self.instance._meta.label if self.instance else 'None'}({self.instance.pk if self.instance else 'N/A'})"
        )

        if not self.instance:
            logger.error("Validation failed: No instance provided")
            raise serializers.ValidationError(
                _(
                    "Object instance is required for workflow approval. "
                    "Use: WorkflowApprovalSerializer(instance=my_object, data={...})"
                )
            )

        attachment = get_workflow_attachment(self.instance)
        if not attachment:
            logger.error(
                f"Validation failed: No workflow attached - "
                f"object: {self.instance._meta.label}({self.instance.pk})"
            )
            raise serializers.ValidationError(_("No workflow attached to this object"))

        if attachment.status != "in_progress":
            logger.warning(
                f"Validation failed: Workflow not in progress - "
                f"status: {attachment.status}, "
                f"workflow_id: {attachment.workflow.id}, "
                f"object: {self.instance._meta.label}({self.instance.pk})"
            )
            raise serializers.ValidationError(
                _("Workflow is not in progress (current status: {status})").format(
                    status=attachment.status
                )
            )

        # Check if there are current approval instances
        current_approval = get_current_approval_for_object(self.instance)
        if not current_approval:
            # Get location based on strategy
            from .utils import get_workflow_location_string

            location = get_workflow_location_string(attachment)

            logger.error(
                f"Validation failed: No current approval step - "
                f"workflow_id: {attachment.workflow.id}, "
                f"{location}, "
                f"object: {self.instance._meta.label}({self.instance.pk})"
            )
            raise serializers.ValidationError(
                _("No current approval step found for this object")
            )

        # Log successful validation with strategy-aware location
        from .utils import get_workflow_location_string

        location = get_workflow_location_string(attachment)

        logger.info(
            f"Action validation passed - "
            f"action: {value}, "
            f"workflow_id: {attachment.workflow.id}, "
            f"{location}, "
            f"object: {self.instance._meta.label}({self.instance.pk})"
        )
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

        logger.info(
            f"Starting comprehensive validation - "
            f"action: {action}, "
            f"user: {user.id if user else 'Anonymous'}, "
            f"has_reason: {bool(attrs.get('reason'))}, "
            f"has_form_data: {bool(attrs.get('form_data'))}"
        )

        try:
            if action == ApprovalStatus.REJECTED:
                logger.debug("Validating rejection requirements")
                self._validate_rejection(attrs)
            elif action == ApprovalStatus.NEEDS_RESUBMISSION:
                logger.debug("Validating resubmission requirements")
                self._validate_resubmission(attrs)
            elif action == ApprovalStatus.DELEGATED:
                logger.debug("Validating delegation requirements")
                self._validate_delegation(attrs)
            elif action == ApprovalStatus.APPROVED:
                logger.debug("Validating approval requirements")
                self._validate_approval(attrs)

            # Log successful validation
            logger.info(
                f"Comprehensive validation passed - "
                f"action: {action}, "
                f"user: {user.id if user else 'Anonymous'}"
            )
            log_serializer_validation(
                serializer_name="WorkflowApprovalSerializer",
                is_valid=True,
                user_id=user.id if user else None,
            )

            return attrs

        except serializers.ValidationError as e:
            # Log validation errors
            logger.error(
                f"Comprehensive validation failed - "
                f"action: {action}, "
                f"user: {user.id if user else 'Anonymous'}, "
                f"errors: {e.detail}"
            )
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
        logger.debug(
            f"Validating resubmission - stage_id: {attrs.get('stage_id')}, has_reason: {bool(attrs.get('reason'))}"
        )

        if not attrs.get("reason"):
            logger.warning("Resubmission validation failed: Missing reason")
            raise serializers.ValidationError(
                {"reason": _("Reason is required for resubmission")}
            )

        # stage_id is optional - if not provided, resubmission goes to current stage
        stage_id = attrs.get("stage_id")
        if stage_id:
            # Validate stage exists and belongs to current workflow
            try:
                attachment = get_workflow_attachment(self.instance)
                stage = Stage.objects.get(pk=stage_id)

                logger.debug(
                    f"Validating resubmission stage - "
                    f"stage_id: {stage_id}, "
                    f"stage_workflow: {stage.pipeline.workflow.id}, "
                    f"current_workflow: {attachment.workflow.id}"
                )

                # Check if stage belongs to current workflow
                if stage.pipeline.workflow.id != attachment.workflow.id:
                    logger.error(
                        f"Resubmission validation failed: Stage {stage_id} belongs to workflow {stage.pipeline.workflow.id}, "
                        f"but current workflow is {attachment.workflow.id}"
                    )
                    raise serializers.ValidationError(
                        {"stage_id": _("Stage does not belong to current workflow")}
                    )

                logger.debug(f"Resubmission validation passed for stage {stage_id}")

            except Stage.DoesNotExist:
                logger.error(
                    f"Resubmission validation failed: Stage {stage_id} does not exist"
                )
                raise serializers.ValidationError({"stage_id": _("Invalid stage ID")})

    def _validate_delegation(self, attrs):
        """Validate delegation requirements."""
        logger.debug(f"Validating delegation - user_id: {attrs.get('user_id')}")

        # user_id is optional for delegation - if not provided, the approval workflow
        # will handle the delegation logic internally
        user_id = attrs.get("user_id")
        if user_id:
            # Validate user exists only if user_id is provided
            from django.contrib.auth import get_user_model

            User = get_user_model()

            try:
                user = User.objects.get(pk=user_id)
                logger.debug(
                    f"Delegation user validated - user_id: {user_id}, username: {user.username if hasattr(user, 'username') else 'N/A'}"
                )
            except User.DoesNotExist:
                logger.error(
                    f"Delegation validation failed: User {user_id} does not exist"
                )
                raise serializers.ValidationError({"user_id": _("Invalid user ID")})
        else:
            logger.debug("No user_id provided for delegation - will use internal logic")

    def _validate_approval(self, attrs):
        """Validate approval requirements."""
        logger.debug("Validating approval requirements")

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
                logger.debug(
                    f"Approval requires form - "
                    f"approval_id: {current_approval.id}, "
                    f"form_id: {current_approval.form.id}"
                )

                # Form is required - validate form_data is provided
                form_data = attrs.get("form_data", {})
                if not form_data:
                    logger.error(
                        f"Approval validation failed: Form data required but not provided - "
                        f"approval_id: {current_approval.id}, "
                        f"form_id: {current_approval.form.id}"
                    )
                    raise serializers.ValidationError(
                        {"form_data": _("Form data is required for this approval step")}
                    )

                logger.debug(
                    f"Approval validation passed - form_data fields: {list(form_data.keys())}"
                )
            else:
                logger.debug("No form required for this approval")

    def save(self, **kwargs):
        """Process the workflow approval action."""
        logger.info("=== Starting workflow approval save ===")

        if not self.instance:
            logger.error("Save failed: No instance provided")
            raise ValueError(_("Object instance is required for workflow approval"))

        validated_data = self.validated_data
        action = validated_data["action"]
        user = self.context.get("request").user if self.context.get("request") else None

        # Log the approval action attempt
        attachment = get_workflow_attachment(self.instance)

        # Get location based on strategy
        from .utils import get_workflow_location_string

        location_str = (
            get_workflow_location_string(attachment) if attachment else "unknown"
        )

        logger.info(
            f"Processing approval action - "
            f"action: {action}, "
            f"user: {user.id if user else 'Anonymous'}, "
            f"workflow: {attachment.workflow.id if attachment else 'None'}, "
            f"location: {location_str}, "
            f"object: {self.instance._meta.label}({self.instance.pk})"
        )

        serializers_logger.log_approval_action(
            action=action.value if hasattr(action, "value") else str(action),
            workflow_id=attachment.workflow.id if attachment else None,
            stage=location_str,
            user_id=user.id if user else None,
            object_type=self.instance._meta.label,
            object_id=str(self.instance.pk),
        )

        try:
            with transaction.atomic():
                # Prepare resubmission steps if needed
                resubmission_steps = None
                if action == ApprovalStatus.NEEDS_RESUBMISSION:
                    logger.debug("Preparing resubmission steps")
                    resubmission_steps = self._prepare_resubmission_steps(
                        validated_data
                    )
                    logger.debug(
                        f"Resubmission steps prepared: {len(resubmission_steps)} steps"
                    )

                # Prepare delegation user if needed
                delegate_to_user = None
                if action == ApprovalStatus.DELEGATED:
                    logger.debug("Fetching delegation user")
                    delegate_to_user = self._get_delegation_user(validated_data)
                    logger.debug(
                        f"Delegation user fetched: {delegate_to_user.id if delegate_to_user else 'None'}"
                    )

                # Enrich form data with answer keys if form_data is provided
                form_data = validated_data.get("form_data")
                enriched_form_data = None
                if form_data and attachment and attachment.current_stage:
                    logger.debug("Enriching form data")
                    # Get current approval to access its form
                    current_approval = get_current_approval_for_object(self.instance)
                    if hasattr(current_approval, "__iter__") and not isinstance(
                        current_approval, (str, bytes)
                    ):
                        current_approval = (
                            list(current_approval)[0] if current_approval else None
                        )

                    enriched_form_data = self._enrich_form_data(
                        form_data, current_approval
                    )
                    logger.debug("Form data enrichment completed")

                # Use approval_workflow's advance_flow to handle the action
                logger.info(f"Calling advance_flow with action: {action}")
                advance_flow(
                    instance=self.instance,
                    action=action,
                    user=user,
                    comment=validated_data.get("reason", ""),
                    form_data=enriched_form_data or form_data,
                    delegate_to=delegate_to_user,
                    resubmission_steps=resubmission_steps,
                )
                logger.info("advance_flow completed successfully")

                # Update workflow attachment status if needed
                logger.debug("Updating workflow attachment")
                self._update_workflow_attachment(action, user)
                logger.debug("Workflow attachment updated")

                logger.info(
                    f"=== Workflow approval save completed successfully === "
                    f"action: {action}, object: {self.instance._meta.label}({self.instance.pk})"
                )

                return self.instance

        except Exception as e:
            logger.error(
                f"=== Error processing workflow approval action === "
                f"action: {action}, "
                f"user: {user.id if user else 'Anonymous'}, "
                f"error: {str(e)}"
            )
            raise serializers.ValidationError(
                {
                    "error": _("Failed to process approval action: {error}").format(
                        error=str(e)
                    )
                }
            )

    def _prepare_resubmission_steps(self, validated_data):
        """Prepare resubmission steps for the specified stage.

        IMPORTANT: Steps are numbered to continue from the current step.
        Example: If currently at step 5, new resubmission steps start from 6.
        This ensures step numbers are cumulative across the entire workflow,
        not restarting from 1 after resubmission.
        """
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

            # Calculate starting step number for resubmission
            # The approval_workflow package will:
            # 1. Mark current step as NEEDS_RESUBMISSION
            # 2. Delete all PENDING/CURRENT steps after the current step
            # 3. Create new steps starting from current_step + 1
            current_step_number = current_approval.step_number
            start_step = current_step_number + 1

            logger.info(
                f"Preparing resubmission steps - Current step: {current_step_number}, "
                f"New steps will start from: {start_step}"
            )

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
            # Pass start_step to continue numbering from current position
            resubmission_steps = builder.build_steps(start_step=start_step)

            # Add resubmission stage_id to each step's extra_fields
            for step in resubmission_steps:
                if "extra_fields" not in step:
                    step["extra_fields"] = {}
                step["extra_fields"]["resubmission_stage_id"] = stage_id

            logger.info(
                f"Resubmission steps prepared - Step numbers: "
                f"{[step['step'] for step in resubmission_steps]}"
            )

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

    def _enrich_form_data(self, form_data: dict, current_approval) -> list:
        """Enrich form data with field specifications and answer keys.

        This method flattens nested forms based on submitted data and enriches
        each field with its answer, creating a structure like:
        [
            {"field_name": "budget", "field_type": "NUMBER", "answer": 50000},
            {"field_name": "description", "field_type": "TEXT", "answer": "..."}
        ]

        Args:
            form_data: The submitted form data dictionary
            current_approval: The current ApprovalInstance with form

        Returns:
            List of enriched field specifications with answers
        """
        from .utils import enrich_answers, flatten_form_info

        # Get the form_info from the current approval's form
        # This ensures we use the form assigned to THIS specific approval step,
        # not the stage's form_info which may not match
        form_info = None
        if current_approval and current_approval.form:
            # Get form_info from the Form instance
            form_info = getattr(current_approval.form, "form_info", None)

        if not form_info or not form_data:
            logger.debug(
                f"No form_info to enrich - form_info: {bool(form_info)}, "
                f"form_data: {bool(form_data)}, "
                f"has_approval: {bool(current_approval)}, "
                f"has_form: {bool(current_approval.form if current_approval else False)}"
            )
            return form_data

        # Flatten nested forms based on submitted data
        flattened_form_info = flatten_form_info(form_info, form_data)

        # Enrich with answers
        request = self.context.get("request")
        object_id = getattr(self.instance, "pk", None)

        enriched = enrich_answers(
            flattened_form_info,
            form_data,
            request=request,
            object_id=object_id,
            save_files=True,
        )

        logger.info(
            f"Form data enriched - approval_id: {current_approval.id if current_approval else None}, "
            f"form_id: {current_approval.form.id if current_approval and current_approval.form else None}, "
            f"fields_count: {len(enriched)}"
        )

        return enriched

    def _update_workflow_attachment(self, action, user=None):
        """Update workflow attachment status based on action (strategy-aware)."""
        logger.debug(f"Updating workflow attachment for action: {action}")

        attachment = get_workflow_attachment(self.instance)
        if not attachment:
            logger.warning("No workflow attachment found - skipping update")
            return

        if action == ApprovalStatus.REJECTED:
            # Get location based on strategy for logging
            from .utils import get_workflow_location_string

            location_str = get_workflow_location_string(attachment)

            logger.info(
                f"Marking workflow as rejected - "
                f"workflow_id: {attachment.workflow.id}, "
                f"{location_str}, "
                f"object: {self.instance._meta.label}({self.instance.pk})"
            )

            attachment.status = "rejected"
            attachment.save()

            # Call workflow hooks
            from .choices import ActionType
            from .services import trigger_workflow_event

            logger.debug("Triggering AFTER_REJECT event")
            trigger_workflow_event(
                attachment,
                ActionType.AFTER_REJECT,
                target_object=self.instance,
                stage=attachment.current_stage,  # Will be None for strategies 2 and 3
                pipeline=attachment.current_pipeline,  # Will be None for strategy 3
                user=user,
            )

            logger.info(
                f"Workflow rejection completed - "
                f"workflow_id: {attachment.workflow.id}, "
                f"{location_str}"
            )

        # Note: Approval progression to next stage/pipeline is handled by the approval workflow
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
    """Serializer for creating/updating Pipeline with auto-generated stages and custom actions.

    Note: Override fields in your implementation as needed.
    created_by is automatically set from request context.

    Actions field format: Same as WorkFlowSerializer
    """

    number_of_stages = serializers.IntegerField(
        write_only=True,
        required=False,
        min_value=1,
        help_text=_("Number of stages to auto-create for this pipeline"),
    )
    actions = serializers.ListField(
        child=WorkflowActionInputSerializer(),
        required=False,
        write_only=True,
        help_text=_(
            "Custom actions for this pipeline. If not provided, workflow-level actions will be inherited."
        ),
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

    def validate(self, attrs):
        """Validate pipeline creation based on parent workflow strategy."""
        from .choices import WorkflowStrategy

        workflow = attrs.get("workflow")
        number_of_stages = attrs.get("number_of_stages", 0)

        # If workflow is provided, check its strategy
        if workflow:
            # Strategy 3 (Workflow Only): NO pipelines allowed at all
            if workflow.strategy == WorkflowStrategy.WORKFLOW_ONLY:
                raise serializers.ValidationError(
                    {
                        "workflow": "Cannot create pipelines for Strategy 3 (Workflow Only) workflows. Approvals must be at workflow level."
                    }
                )

            # Strategy 2 (Workflow→Pipeline): NO stages allowed
            if workflow.strategy == WorkflowStrategy.WORKFLOW_PIPELINE:
                if number_of_stages > 0:
                    raise serializers.ValidationError(
                        {
                            "number_of_stages": "Cannot create stages for Strategy 2 (Workflow→Pipeline) workflows. Approvals must be at pipeline level."
                        }
                    )
                # Check pipeline_info has approvals
                pipeline_info = attrs.get("pipeline_info", {})
                if not pipeline_info or not pipeline_info.get("approvals"):
                    raise serializers.ValidationError(
                        {
                            "pipeline_info": "Strategy 2 pipeline requires approvals in pipeline_info."
                        }
                    )

        return attrs

    def create(self, validated_data):
        """Create pipeline with auto-generated stages and custom actions."""
        number_of_stages = validated_data.pop("number_of_stages", 0)
        actions_data = validated_data.pop("actions", None)

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

        # Handle actions
        if actions_data:
            from .action_management import create_custom_workflow_actions

            create_custom_workflow_actions(actions_data, pipeline=pipeline)
            logger.info(
                f"Created {len(actions_data)} custom actions for pipeline {pipeline.id}"
            )

        return pipeline


class WorkFlowSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating WorkFlow with nested pipelines and custom actions.

    Note: Override fields in your implementation as needed.
    created_by is automatically set from request context.
    company is automatically set from context if not provided.

    Actions field format:
        actions = [
            {
                'action_type': 'after_approve',  # ActionType choice
                'function_path': 'myapp.actions.send_custom_email',
                'parameters': {
                    'template': 'custom_approved',
                    'recipients': ['creator', 'user@example.com']
                },
                'order': 1,
                'is_active': True
            }
        ]
    """

    pipelines = PipelineSerializer(many=True, required=False)
    actions = serializers.ListField(
        child=WorkflowActionInputSerializer(),
        required=False,
        write_only=True,
        help_text=_(
            "Custom actions for this workflow. If not provided, default actions will be created."
        ),
    )

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

    def validate(self, attrs):
        """Validate workflow creation based on strategy constraints.

        Note: This only validates pipelines IF they are provided in the request.
        Workflows can be created without nested pipelines and have them added later.
        """
        from .choices import WorkflowStrategy

        strategy = attrs.get("strategy", WorkflowStrategy.WORKFLOW_PIPELINE_STAGE)
        pipelines_data = attrs.get("pipelines", [])
        workflow_info = attrs.get("workflow_info", {})

        # Only validate if pipelines data is actually provided
        if pipelines_data:
            # Strategy 3 (Workflow Only): NO pipelines allowed if provided
            if strategy == WorkflowStrategy.WORKFLOW_ONLY:
                raise serializers.ValidationError(
                    {
                        "pipelines": "Strategy 3 (Workflow Only) cannot have pipelines. Approvals must be in workflow_info only."
                    }
                )

            # Strategy 2 (Workflow→Pipeline): NO stages allowed in pipelines
            elif strategy == WorkflowStrategy.WORKFLOW_PIPELINE:
                for i, pipeline_data in enumerate(pipelines_data):
                    # Check if pipeline has stages defined
                    if "stages" in pipeline_data or "number_of_stages" in pipeline_data:
                        raise serializers.ValidationError(
                            {
                                f"pipelines[{i}]": "Strategy 2 (Workflow→Pipeline) cannot have stages. Approvals must be in pipeline_info."
                            }
                        )
                    # Check if pipeline has pipeline_info with approvals
                    pipeline_info = pipeline_data.get("pipeline_info", {})
                    if not pipeline_info or not pipeline_info.get("approvals"):
                        raise serializers.ValidationError(
                            {
                                f"pipelines[{i}].pipeline_info": "Strategy 2 pipeline must have approvals in pipeline_info."
                            }
                        )

        # For Strategy 3, validate workflow_info if provided
        if strategy == WorkflowStrategy.WORKFLOW_ONLY and workflow_info:
            if not workflow_info.get("approvals"):
                raise serializers.ValidationError(
                    {
                        "workflow_info": "Strategy 3 (Workflow Only) requires approvals in workflow_info."
                    }
                )

        return attrs

    def create(self, validated_data):
        """Create workflow with nested pipelines, stages, and custom actions."""
        from django.conf import settings

        pipelines_data = validated_data.pop("pipelines", [])
        actions_data = validated_data.pop("actions", None)

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

        # Temporarily disable auto-creation of default actions
        # (we'll create custom or default actions manually)
        original_auto_create = getattr(settings, "WORKFLOW_AUTO_CREATE_ACTIONS", True)
        settings.WORKFLOW_AUTO_CREATE_ACTIONS = False

        try:
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
            workflow.save(update_fields=["description", "is_active"])

            # Handle actions
            if actions_data:
                # Create custom actions provided by user
                from .action_management import create_custom_workflow_actions

                create_custom_workflow_actions(actions_data, workflow=workflow)
                logger.info(
                    f"Created {len(actions_data)} custom actions for workflow {workflow.id}"
                )
            elif original_auto_create:
                # No custom actions provided, create defaults
                from .action_management import create_default_workflow_actions

                create_default_workflow_actions(workflow)
                logger.info(f"Created default actions for workflow {workflow.id}")

        finally:
            # Restore original setting
            settings.WORKFLOW_AUTO_CREATE_ACTIONS = original_auto_create

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
    """Serializer for updating Stage configurations including approvals and custom actions.

    Note: Override fields in your implementation as needed.
    is_active is auto-managed based on approval configuration.

    Actions field format: Same as WorkFlowSerializer
    """

    stage_info = serializers.JSONField(required=False)
    actions = serializers.ListField(
        child=WorkflowActionInputSerializer(),
        required=False,
        write_only=True,
        help_text=_(
            "Custom actions for this stage. If not provided, pipeline or workflow-level actions will be inherited."
        ),
    )

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
        """Validate pipeline is provided and check workflow strategy constraints."""
        from .choices import WorkflowStrategy

        # If updating existing instance, pipeline is already set
        if self.instance:
            pipeline = self.instance.pipeline
        else:
            # For create operations, check pipeline from context (URL) or body
            pipeline = attrs.get("pipeline")

            # Check if pipeline is in context (from URL kwargs)
            if not pipeline and self.context.get("view"):
                view = self.context["view"]
                pipeline_id = view.kwargs.get("pipeline") or view.kwargs.get(
                    "pipeline_pk"
                )
                if pipeline_id:
                    try:
                        from .models import Pipeline

                        pipeline = Pipeline.objects.get(id=pipeline_id)
                        attrs["pipeline"] = pipeline
                    except Pipeline.DoesNotExist:
                        raise serializers.ValidationError(
                            {
                                "pipeline": f"Pipeline with id {pipeline_id} does not exist"
                            }
                        )

            # If still no pipeline, it's required
            if not pipeline:
                raise serializers.ValidationError(
                    {
                        "pipeline": "Pipeline is required. Provide it in the request body or URL."
                    }
                )

        # Check workflow strategy - stages not allowed for Strategy 2 and 3
        if pipeline and pipeline.workflow:
            workflow = pipeline.workflow

            # Strategy 3 (Workflow Only): NO stages allowed
            if workflow.strategy == WorkflowStrategy.WORKFLOW_ONLY:
                raise serializers.ValidationError(
                    {
                        "pipeline": "Cannot create stages for Strategy 3 (Workflow Only) workflows. Approvals must be at workflow level only."
                    }
                )

            # Strategy 2 (Workflow→Pipeline): NO stages allowed
            if workflow.strategy == WorkflowStrategy.WORKFLOW_PIPELINE:
                raise serializers.ValidationError(
                    {
                        "pipeline": "Cannot create stages for Strategy 2 (Workflow→Pipeline) workflows. Approvals must be at pipeline level."
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
        valid_approval_types = [choice[0].lower() for choice in ApprovalTypes.choices]

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

                # Valid strategies from RoleSelectionStrategy choices
                valid_strategies = [
                    choice[0].lower() for choice in RoleSelectionStrategy.choices
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

            # Validate step_approval_type (APPROVE, SUBMIT, CHECK_IN_VERIFY, MOVE)
            step_approval_type = approval.get("step_approval_type")
            if step_approval_type:
                # Import ApprovalType from approval_workflow
                from approval_workflow.choices import ApprovalType

                valid_step_types = [
                    choice[0].lower() for choice in ApprovalType.choices
                ]
                step_type_lower = step_approval_type.lower()

                # Normalize to lowercase
                approval["step_approval_type"] = step_type_lower

                if step_type_lower not in valid_step_types:
                    raise serializers.ValidationError(
                        f"Invalid step_approval_type: {step_approval_type}. "
                        f"Must be one of: approve, submit, check_in_verify, move (case-insensitive)"
                    )

                # SUBMIT type must have a form
                if step_type_lower == ApprovalType.SUBMIT.lower():
                    if "required_form" not in approval or not approval["required_form"]:
                        raise serializers.ValidationError(
                            "SUBMIT step_approval_type requires a required_form to be specified"
                        )

                # MOVE type cannot have a form
                if step_type_lower == ApprovalType.MOVE.lower():
                    if approval.get("required_form"):
                        raise serializers.ValidationError(
                            "MOVE step_approval_type cannot have a required_form"
                        )

        return value

    def create(self, validated_data):
        """Create stage with custom actions."""
        actions_data = validated_data.pop("actions", None)

        # Create the stage
        stage = super().create(validated_data)

        # Handle actions
        if actions_data:
            from .action_management import create_custom_workflow_actions

            create_custom_workflow_actions(actions_data, stage=stage)
            logger.info(
                f"Created {len(actions_data)} custom actions for stage {stage.id}"
            )

        return stage

    def update(self, instance, validated_data):
        """Update stage with new configuration and auto-activate/deactivate."""
        actions_data = validated_data.pop("actions", None)
        stage_info = validated_data.get("stage_info")
        old_is_active = instance.is_active

        # Handle actions if provided
        if actions_data:
            from .action_management import create_custom_workflow_actions

            # Remove old stage actions before creating new ones
            from .models import WorkflowAction

            WorkflowAction.objects.filter(stage=instance).delete()

            # Create new actions
            create_custom_workflow_actions(actions_data, stage=instance)
            logger.info(
                f"Updated {len(actions_data)} custom actions for stage {instance.id}"
            )

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
