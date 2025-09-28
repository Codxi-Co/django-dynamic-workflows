"""Custom hook handler for approval steps and workflow events."""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .models import ApprovalInstance

logger = logging.getLogger(__name__)


class BaseApprovalHandler:
    """Base class for custom approval hook logic.

    You can extend this per model or service to implement custom
    business logic for approval workflow events.
    """

    def before_approve(self, instance: "ApprovalInstance") -> None:
        """Called before a step is approved.

        This method is triggered before the approval action is processed,
        allowing for pre-approval validation, logging, or setup. Use this
        for actions that should occur before the approval state changes, such as:
        - Pre-approval validation
        - Logging approval attempts
        - Setting up resources needed for approval
        - Sending pre-approval notifications

        Args:
            instance: The approval instance about to be approved
        """
        logger.debug(
            "Base approval handler - before_approve called - Flow ID: %s, Step: %s",
            instance.flow.id,
            instance.step_number,
        )

    def after_approve(self, instance: "ApprovalInstance") -> None:
        """Called after a step is approved.

        Args:
            instance: The approval instance that was approved
        """
        logger.debug(
            "Base approval handler - after_approve called - Flow ID: %s, Step: %s",
            instance.flow.id,
            instance.step_number,
        )

    def on_final_approve(self, instance: "ApprovalInstance") -> None:
        """Called when the final step is approved.

        Args:
            instance: The final approval instance that was approved
        """
        logger.debug(
            "Base approval handler - on_final_approve called - Flow ID: %s, Step: %s",
            instance.flow.id,
            instance.step_number,
        )

    def before_reject(self, instance: "ApprovalInstance") -> None:
        """Called before a step is rejected.

        This method is triggered before the rejection action is processed,
        allowing for pre-rejection validation, logging, or setup. Use this
        for actions that should occur before the rejection state changes, such as:
        - Pre-rejection validation
        - Logging rejection attempts
        - Backing up data before rejection
        - Sending pre-rejection notifications

        Args:
            instance: The approval instance about to be rejected
        """
        logger.debug(
            "Base approval handler - before_reject called - Flow ID: %s, Step: %s",
            instance.flow.id,
            instance.step_number,
        )

    def after_reject(self, instance: "ApprovalInstance") -> None:
        """Called after a step is rejected.

        Args:
            instance: The approval instance that was rejected
        """
        logger.debug(
            "Base approval handler - after_reject called - Flow ID: %s, Step: %s",
            instance.flow.id,
            instance.step_number,
        )

    def after_resubmission(self, instance: "ApprovalInstance") -> None:
        """Called after resubmission is requested.

        Args:
            instance: The approval instance for resubmission
        """
        logger.debug(
            "Base approval handler - after_resubmission called - Flow ID: %s, Step: %s",
            instance.flow.id,
            instance.step_number,
        )

    def after_delegate(self, instance: "ApprovalInstance") -> None:
        """Called after delegation occurs.

        Args:
            instance: The approval instance that was delegated
        """
        logger.debug(
            "Base approval handler - after_delegate called - Flow ID: %s, Step: %s",
            instance.flow.id,
            instance.step_number,
        )


def get_handler_for_instance(
    instance: "ApprovalInstance",
) -> Optional[BaseApprovalHandler]:
    """Get the appropriate handler for an approval instance.

    This function allows for dynamic handler resolution based on the
    target object type or other criteria.

    Args:
        instance: The approval instance to get a handler for

    Returns:
        Handler instance or None if no specific handler is found
    """
    target_object = instance.flow.target

    if not target_object:
        return None

    # Check if this object has a WorkflowAttachment (generic workflow support)
    from .services import get_workflow_attachment

    attachment = get_workflow_attachment(target_object)

    if attachment:
        # Object is using workflow engine - return generic workflow handler
        return WorkflowApprovalHandler(target_object)

    # Try to get a specific handler for this object type
    handler_name = f"{target_object._meta.app_label}.{target_object._meta.model_name}"

    # Legacy support for specific handlers
    if (
        hasattr(target_object, "_meta")
        and target_object._meta.model_name == "opportunity"
    ):
        # Return opportunity-specific handler if available
        try:
            from django.apps import apps

            if apps.is_installed("crm"):
                from crm.approval import OpportunityApprovalHandler

                return OpportunityApprovalHandler(target_object)
        except ImportError:
            logger.debug(f"No specific handler found for {handler_name}")

    logger.debug(f"No handler found for {handler_name}")
    return None


class ApprovalStepBuilder:
    """Helper class for building approval steps from stage configurations."""

    def __init__(self, stage, created_by_user):
        """Initialize the builder.

        Args:
            stage: The Stage instance
            created_by_user: The user who created the workflow item
        """
        self.stage = stage
        self.created_by_user = created_by_user

    def build_steps(self) -> List[Dict[str, Any]]:
        """Build approval steps for the stage.

        Returns:
            List of approval step configurations
        """
        from .utils import build_approval_steps

        return build_approval_steps(self.stage, self.created_by_user)


class WorkflowApprovalHandler(BaseApprovalHandler):
    """
    Generic approval handler that integrates with workflow progression.

    This handler should be used for objects that have WorkflowAttachment
    to automatically progress through workflow stages when approvals are completed.
    """

    def __init__(self, instance=None):
        super().__init__()
        self.instance = instance

    def on_final_approve(self, approval_instance):
        """Called when the final approval for current stage is completed."""
        try:
            logger.info(f"Final approval completed for {self.instance}")

            # Trigger approve actions before moving to next stage
            from .choices import ActionType
            from .services import get_workflow_attachment, trigger_workflow_event

            attachment = get_workflow_attachment(self.instance)
            if attachment:
                trigger_workflow_event(
                    attachment,
                    ActionType.AFTER_APPROVE,
                    approval_instance=approval_instance,
                    user=getattr(approval_instance, "action_user", None),
                )

            # Move to next workflow stage
            from .services import move_to_next_stage

            attachment = move_to_next_stage(self.instance)

            logger.info(
                f"Workflow progressed - Object: {self.instance._meta.label}({self.instance.pk}), "
                f"Status: {attachment.status}"
            )

        except Exception as e:
            logger.error(f"Error progressing workflow after final approval: {str(e)}")

    def after_approve(self, approval_instance):
        """Called after each individual approval (not necessarily final)."""
        logger.debug(f"Approval step completed for {self.instance}")
        # Individual approvals don't trigger workflow progression
        # Only final approval (on_final_approve) does

    def after_reject(self, approval_instance):
        """Called when approval is rejected."""
        try:
            logger.info(f"Approval rejected for {self.instance}")

            # Trigger reject actions first
            from .choices import ActionType
            from .services import get_workflow_attachment, trigger_workflow_event

            attachment = get_workflow_attachment(self.instance)
            if attachment:
                trigger_workflow_event(
                    attachment,
                    ActionType.AFTER_REJECT,
                    approval_instance=approval_instance,
                    reason=getattr(approval_instance, "comment", ""),
                    user=getattr(approval_instance, "action_user", None),
                )

            # Update workflow attachment status
            if attachment:
                from .services import reject_workflow_stage

                reject_workflow_stage(
                    obj=self.instance,
                    stage=attachment.current_stage,
                    reason=getattr(approval_instance, "comment", ""),
                )

        except Exception as e:
            logger.error(f"Error handling workflow rejection: {str(e)}")

    def after_resubmission(self, approval_instance):
        """Called when resubmission is requested."""
        try:
            logger.info(f"Resubmission requested for {self.instance}")

            # Trigger resubmission actions
            from .choices import ActionType
            from .services import get_workflow_attachment, trigger_workflow_event

            attachment = get_workflow_attachment(self.instance)

            if attachment:
                # Look for resubmission_stage_id in approval instance extra_fields
                extra_fields = getattr(approval_instance, "extra_fields", {})
                resubmission_stage_id = extra_fields.get("resubmission_stage_id")
                target_stage = None

                if resubmission_stage_id:
                    try:
                        from .models import Stage

                        target_stage = Stage.objects.get(pk=resubmission_stage_id)

                        # Update attachment to point to resubmission stage
                        attachment.current_stage = target_stage
                        attachment.current_pipeline = target_stage.pipeline
                        attachment.save()
                    except Stage.DoesNotExist:
                        logger.error(
                            f"Resubmission stage {resubmission_stage_id} not found"
                        )

                # Trigger resubmission actions
                trigger_workflow_event(
                    attachment,
                    ActionType.AFTER_RESUBMISSION,
                    approval_instance=approval_instance,
                    target_stage=target_stage,
                    reason=getattr(approval_instance, "comment", ""),
                    user=getattr(approval_instance, "action_user", None),
                )

            logger.info(
                f"Workflow resubmission - moved to stage: {target_stage.name_en}"
            )

        except Exception as e:
            logger.error(f"Error handling workflow resubmission: {str(e)}")

    def after_delegate(self, approval_instance):
        """Called when delegation occurs."""
        try:
            logger.info(f"Delegation occurred for {self.instance}")

            # Trigger delegation actions
            from .choices import ActionType
            from .services import get_workflow_attachment, trigger_workflow_event

            attachment = get_workflow_attachment(self.instance)

            if attachment:
                # Get delegate user from approval instance
                delegate_user = getattr(approval_instance, "assigned_to", None)

                # Trigger delegation actions
                trigger_workflow_event(
                    attachment,
                    ActionType.AFTER_DELEGATE,
                    approval_instance=approval_instance,
                    delegate_user=delegate_user,
                    reason=getattr(approval_instance, "comment", ""),
                    user=getattr(approval_instance, "action_user", None),
                )

            logger.info(
                f"Workflow delegation completed - delegated to: {delegate_user}"
            )

        except Exception as e:
            logger.error(f"Error handling workflow delegation: {str(e)}")


def get_workflow_handler_for_object(obj):
    """Get the workflow handler for an object.

    Args:
        obj: The object to get a handler for

    Returns:
        WorkflowApprovalHandler instance or None
    """
    from .services import get_workflow_attachment

    attachment = get_workflow_attachment(obj)
    if attachment:
        return WorkflowApprovalHandler(obj)
    return None


class WorkflowProgressManager:
    """
    Manages workflow attachment and integration with approval flows.

    Note: This class focuses on workflow management, not approval progression.
    Approval progression is handled automatically by WorkflowApprovalHandler.
    """

    def __init__(self, obj, workflow_handler=None):
        """Initialize the progress manager.

        Args:
            obj: The object progressing through the workflow
            workflow_handler: Optional workflow handler
        """
        self.obj = obj
        self.workflow_handler = workflow_handler or get_workflow_handler_for_object(obj)

    def attach_and_start_workflow(self, workflow, user=None, metadata=None):
        """Attach and start a workflow for the object.

        Args:
            workflow: The WorkFlow instance to attach and start
            user: The user starting the workflow
            metadata: Additional metadata for the attachment

        Returns:
            WorkflowAttachment instance
        """
        from .services import attach_workflow_to_object

        # Attach workflow with auto-start
        attachment = attach_workflow_to_object(
            obj=self.obj,
            workflow=workflow,
            user=user,
            auto_start=True,
            metadata=metadata or {},
        )

        logger.info(
            f"Workflow attached and started - Object: {self.obj._meta.label}({self.obj.pk}), "
            f"Workflow: {workflow.name_en}"
        )

        return attachment

    def get_current_status(self):
        """Get current workflow status for the object."""
        from .services import get_workflow_attachment

        attachment = get_workflow_attachment(self.obj)
        if not attachment:
            return None

        return {
            "workflow": attachment.workflow.name_en,
            "status": attachment.status,
            "current_stage": (
                attachment.current_stage.name_en if attachment.current_stage else None
            ),
            "current_pipeline": (
                attachment.current_pipeline.name_en
                if attachment.current_pipeline
                else None
            ),
            "progress_percentage": attachment.progress_percentage,
            "started_at": attachment.started_at,
            "completed_at": attachment.completed_at,
        }
