"""Action executor for workflow events."""

import logging
from typing import Dict, Optional

from django.conf import settings
from django.utils.module_loading import import_string

from .action_management import get_effective_actions
from .action_registry import ActionExecutionError, ActionNotRegisteredError, registry

logger = logging.getLogger(__name__)


def _execute_action_securely(
    function_path: str,
    workflow_attachment,
    action_parameters: Dict,
    context: Dict,
    action_source: str,
    action_type: str,
) -> bool:
    """
    Attempt to execute an action using the secure registry.

    This function tries multiple strategies to execute an action securely:
    1. Direct action name match in registry
    2. Last component of function_path match (for legacy compatibility)

    Args:
        function_path: Function path or action name
        workflow_attachment: WorkflowAttachment instance
        action_parameters: Parameters for the action
        context: Additional context
        action_source: Source description for logging
        action_type: Type of action for logging

    Returns:
        True if action executed successfully, False otherwise

    Raises:
        ActionNotRegisteredError: If action is not in registry
        ActionExecutionError: If action execution fails
    """
    # Strategy 1: Try direct action name
    if registry.is_registered(function_path):
        logger.info(
            f"Executing {action_source} - {function_path} for {action_type} (secure registry)"
        )
        return registry.execute_action(
            action_name=function_path,
            workflow_attachment=workflow_attachment,
            action_parameters=action_parameters,
            **context,
        )

    # Strategy 2: Try last component of function_path (legacy compatibility)
    action_name = function_path.split(".")[-1]
    if registry.is_registered(action_name):
        logger.info(
            f"Executing {action_source} - {action_name} for {action_type} "
            f"(secure registry - resolved from {function_path})"
        )
        return registry.execute_action(
            action_name=action_name,
            workflow_attachment=workflow_attachment,
            action_parameters=action_parameters,
            **context,
        )

    # Not found in registry - let caller fall back to legacy import
    raise ActionNotRegisteredError(
        f"Action '{function_path}' not found in secure registry. "
        f"Checked direct name and extracted action name '{action_name}'."
    )


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

            # Get action parameters
            action_parameters = action.parameters or {}

            # Try to execute using secure registry first
            result = _execute_action_securely(
                action.function_path,
                workflow_attachment,
                action_parameters,
                context,
                action_source,
                action_type,
            )

            executed += 1

            if result:
                succeeded += 1
                logger.info(f"{action_source} executed successfully")
            else:
                failed += 1
                logger.warning(f"{action_source} execution returned False")

        except ActionNotRegisteredError as e:
            # This is expected for legacy function paths that aren't registered
            action_label = (
                f"action {action.id}" if action.id else "settings/default action"
            )
            logger.warning(
                f"Action not in registry, attempting legacy import for {action_label}: {e}"
            )
            # Fall through to legacy import (handled below)
            try:
                # Legacy import path (for backward compatibility)
                handler_function = import_string(action.function_path)

                # Execute the handler
                logger.info(
                    f"Executing {action_source} - {action.function_path} for {action_type} (legacy)"
                )

                result = handler_function(
                    workflow_attachment=workflow_attachment,
                    action_parameters=action_parameters,
                    **context,
                )

                executed += 1

                if result:
                    succeeded += 1
                    logger.info(f"{action_source} (legacy) executed successfully")
                else:
                    failed += 1
                    logger.warning(f"{action_source} (legacy) execution returned False")

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
    Execute a single custom action by function path or action name.

    This function first tries to use the secure action registry. If the action
    is not registered, it falls back to legacy dynamic import for backward
    compatibility (logged with a warning).

    Args:
        workflow_attachment: WorkflowAttachment instance
        function_path: Action name (registered) or dotted path to handler function (legacy)
        parameters: Action parameters to pass to handler
        **context: Additional context

    Returns:
        bool: True if action executed successfully

    Example:
        # Using registered action name (recommended)
        execute_custom_action(
            workflow_attachment=attachment,
            function_path='send_custom_email',
            parameters={'template': 'custom_template', 'recipients': ['admin']},
            user=current_user
        )

        # Legacy function path (still works but not recommended)
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

    # Try secure registry first
    try:
        logger.info(f"Attempting to execute custom action: {function_path}")

        result = _execute_action_securely(
            function_path=function_path,
            workflow_attachment=workflow_attachment,
            action_parameters=parameters or {},
            context=context,
            action_source="custom action",
            action_type="custom",
        )

        if result:
            logger.info(
                f"Custom action {function_path} executed successfully via registry"
            )
            return True
        else:
            logger.warning(f"Custom action {function_path} execution returned False")
            return False

    except ActionNotRegisteredError:
        # Fall back to legacy import for backward compatibility
        logger.warning(
            f"Action '{function_path}' not in secure registry. "
            f"Falling back to legacy dynamic import (not recommended for security)."
        )

        try:
            # Import the handler function
            handler_function = import_string(function_path)

            # Execute the handler
            logger.info(f"Executing custom action via legacy import: {function_path}")

            result = handler_function(
                workflow_attachment=workflow_attachment,
                action_parameters=parameters or {},
                **context,
            )

            if result:
                logger.info(
                    f"Custom action {function_path} executed successfully (legacy)"
                )
                return True
            else:
                logger.warning(
                    f"Custom action {function_path} execution returned False (legacy)"
                )
                return False

        except ImportError as e:
            logger.error(f"Failed to import handler function '{function_path}': {e}")
            return False

        except Exception as e:
            logger.error(
                f"Failed to execute custom action {function_path}: {e}", exc_info=True
            )
            return False

    except Exception as e:
        logger.error(
            f"Failed to execute custom action {function_path}: {e}", exc_info=True
        )
        return False
