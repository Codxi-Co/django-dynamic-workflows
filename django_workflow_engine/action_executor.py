"""Action executor for workflow events."""

import logging
from typing import Dict, Optional

from django.conf import settings
from django.utils.module_loading import import_string

from .action_management import get_effective_actions

logger = logging.getLogger(__name__)


def execute_workflow_actions(
    action_type: str, workflow_attachment, **context
) -> Dict[str, int]:
    """
    Execute all effective actions for a workflow event.

    This function:
    1. Gets effective actions using inheritance (Stage -> Pipeline -> Workflow)
    2. Imports and executes each action's handler function
    3. Passes action parameters and context to handlers
    4. Returns execution statistics

    Args:
        action_type: Type of action (from ActionType choices)
        workflow_attachment: WorkflowAttachment instance
        **context: Additional context to pass to handlers (user, stage, reason, etc.)

    Returns:
        Dict with execution statistics:
        {
            'executed': int,  # Number of actions executed
            'succeeded': int,  # Number of successful executions
            'failed': int,    # Number of failed executions
            'skipped': int    # Number of skipped actions
        }

    Example:
        from .choices import ActionType

        execute_workflow_actions(
            action_type=ActionType.AFTER_APPROVE,
            workflow_attachment=attachment,
            user=approver,
            stage=current_stage
        )
    """
    # Check if email notifications are disabled
    if getattr(settings, "WORKFLOW_DISABLE_EMAILS", False):
        logger.info("Workflow emails disabled via WORKFLOW_DISABLE_EMAILS setting")
        return {"executed": 0, "succeeded": 0, "failed": 0, "skipped": 0}

    if not workflow_attachment:
        logger.error("No workflow_attachment provided to execute_workflow_actions")
        return {"executed": 0, "succeeded": 0, "failed": 0, "skipped": 0}

    # Get workflow, pipeline, and stage from attachment or context
    workflow = workflow_attachment.workflow
    pipeline = workflow_attachment.current_pipeline
    stage = context.get("stage") or workflow_attachment.current_stage

    # Get effective actions using inheritance
    actions = get_effective_actions(
        action_type=action_type,
        workflow=workflow,
        pipeline=pipeline,
        stage=stage,
    )

    if not actions:
        logger.debug(
            f"No actions found for {action_type} - "
            f"workflow: {workflow.id if workflow else None}, "
            f"pipeline: {pipeline.id if pipeline else None}, "
            f"stage: {stage.id if stage else None}"
        )
        return {"executed": 0, "succeeded": 0, "failed": 0, "skipped": 0}

    logger.info(
        f"Executing {len(actions)} action(s) for {action_type} - "
        f"workflow: {workflow.name_en if workflow else 'N/A'}"
    )

    # Execute each action
    executed = 0
    succeeded = 0
    failed = 0
    skipped = 0

    for action in actions:
        # Skip inactive actions
        if not action.is_active:
            action_label = f"DB:{action.id}" if action.id else "settings/default"
            logger.debug(f"Skipping inactive action {action_label}")
            skipped += 1
            continue

        try:
            # Determine action source for logging
            if action.id:
                action_source = f"DB action {action.id}"
            else:
                action_source = "settings/default action"

            # Import the handler function
            handler_function = import_string(action.function_path)

            # Get action parameters
            action_parameters = action.parameters or {}

            # Execute the handler
            logger.info(
                f"Executing {action_source} - {action.function_path} for {action_type}"
            )

            result = handler_function(
                workflow_attachment=workflow_attachment,
                action_parameters=action_parameters,
                **context,
            )

            executed += 1

            if result:
                succeeded += 1
                logger.info(f"{action_source} executed successfully")
            else:
                failed += 1
                logger.warning(f"{action_source} execution returned False")

        except ImportError as e:
            action_label = (
                f"action {action.id}" if action.id else "settings/default action"
            )
            logger.error(
                f"Failed to import handler function '{action.function_path}' "
                f"for {action_label}: {e}"
            )
            failed += 1
            executed += 1

        except Exception as e:
            action_label = (
                f"action {action.id}" if action.id else "settings/default action"
            )
            logger.error(
                f"Failed to execute {action_label} ({action.function_path}): {e}",
                exc_info=True,
            )
            failed += 1
            executed += 1

    logger.info(
        f"Action execution completed for {action_type} - "
        f"Executed: {executed}, Succeeded: {succeeded}, Failed: {failed}, Skipped: {skipped}"
    )

    return {
        "executed": executed,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
    }


def execute_custom_action(
    workflow_attachment,
    function_path: str,
    parameters: Optional[Dict] = None,
    **context,
) -> bool:
    """
    Execute a single custom action by function path.

    Useful for executing one-off actions outside of the standard action types.

    Args:
        workflow_attachment: WorkflowAttachment instance
        function_path: Dotted path to handler function
        parameters: Action parameters to pass to handler
        **context: Additional context

    Returns:
        bool: True if action executed successfully

    Example:
        execute_custom_action(
            workflow_attachment=attachment,
            function_path='myapp.actions.send_custom_email',
            parameters={'template': 'custom_template', 'recipients': ['admin']},
            user=current_user
        )
    """
    if not workflow_attachment:
        logger.error("No workflow_attachment provided to execute_custom_action")
        return False

    try:
        # Import the handler function
        handler_function = import_string(function_path)

        # Execute the handler
        logger.info(f"Executing custom action: {function_path}")

        result = handler_function(
            workflow_attachment=workflow_attachment,
            action_parameters=parameters or {},
            **context,
        )

        if result:
            logger.info(f"Custom action {function_path} executed successfully")
            return True
        else:
            logger.warning(f"Custom action {function_path} execution returned False")
            return False

    except ImportError as e:
        logger.error(f"Failed to import handler function '{function_path}': {e}")
        return False

    except Exception as e:
        logger.error(
            f"Failed to execute custom action {function_path}: {e}", exc_info=True
        )
        return False
