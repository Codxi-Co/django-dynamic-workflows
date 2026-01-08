"""Action management for workflow events."""

import logging
from typing import Dict, List, Optional

from .choices import ActionType
from .models import Pipeline, Stage, WorkFlow, WorkflowAction

logger = logging.getLogger(__name__)


def create_custom_workflow_actions(
    actions_data: List[Dict],
    workflow: Optional[WorkFlow] = None,
    pipeline: Optional[Pipeline] = None,
    stage: Optional[Stage] = None,
) -> List[WorkflowAction]:
    """
    Create custom workflow actions from provided data.

    Args:
        actions_data: List of action configuration dictionaries
        workflow: Optional workflow instance
        pipeline: Optional pipeline instance
        stage: Optional stage instance

    Returns:
        List of created WorkflowAction instances

    Example:
        actions_data = [
            {
                'action_type': 'after_approve',
                'function_path': 'myapp.actions.send_custom_approval',
                'parameters': {
                    'template': 'custom_approved',
                    'recipients': ['creator', 'manager@example.com']
                },
                'order': 1,
                'is_active': True
            }
        ]
        actions = create_custom_workflow_actions(actions_data, workflow=my_workflow)
    """
    created_actions = []

    # Determine scope
    if stage:
        scope_kwargs = {"stage": stage, "workflow": None, "pipeline": None}
        scope_name = f"stage {stage.name_en}"
    elif pipeline:
        scope_kwargs = {"pipeline": pipeline, "workflow": None, "stage": None}
        scope_name = f"pipeline {pipeline.name_en}"
    elif workflow:
        scope_kwargs = {"workflow": workflow, "pipeline": None, "stage": None}
        scope_name = f"workflow {workflow.name_en}"
    else:
        logger.error("No scope provided for creating custom actions")
        return []

    for action_data in actions_data:
        try:
            action = WorkflowAction.objects.create(
                **scope_kwargs,
                action_type=action_data.get("action_type"),
                function_path=action_data.get("function_path"),
                is_active=action_data.get("is_active", True),
                parameters=action_data.get("parameters", {}),
                order=action_data.get("order", 1),
            )
            created_actions.append(action)
            logger.info(
                f"Created custom action {action_data.get('action_type')} for {scope_name}"
            )
        except Exception as e:
            logger.error(
                f"Failed to create custom action {action_data.get('action_type')} "
                f"for {scope_name}: {e}"
            )

    logger.info(f"Created {len(created_actions)} custom actions for {scope_name}")
    return created_actions


def create_default_workflow_actions(
    workflow: WorkFlow,
    pipeline: Optional[Pipeline] = None,
    stage: Optional[Stage] = None,
    force: bool = False,
) -> List[WorkflowAction]:
    """
    DEPRECATED: Create placeholder action configurations (does not send emails).

    WARNING: As of v1.5.5, the package no longer sends emails. The action handlers
    referenced by this function are stubs that log warnings.

    To actually send emails, you must:
    1. Create your own action handlers in your application
    2. Update the function_path to point to your handlers
    3. Or use create_custom_workflow_actions() with your own function paths

    This function creates WorkflowAction records but they won't send emails unless
    you implement your own handlers.

    Args:
        workflow: Workflow instance
        pipeline: Optional pipeline for pipeline-level actions
        stage: Optional stage for stage-level actions
        force: If True, create actions even if some already exist

    Returns:
        List of created WorkflowAction instances (with stub handlers)

    Better Alternative:
        # Use create_custom_workflow_actions with YOUR handlers
        from django_workflow_engine.action_management import create_custom_workflow_actions

        actions_data = [{
            'action_type': 'after_approve',
            'function_path': 'myapp.actions.send_approval_email',  # Your handler
            'parameters': {'template': 'approval'},
            'order': 1,
        }]
        create_custom_workflow_actions(actions_data, workflow=workflow)
    """
    created_actions = []

    # Determine scope
    if stage:
        scope_kwargs = {"stage": stage, "workflow": None, "pipeline": None}
        scope_name = f"stage {stage.name_en}"
    elif pipeline:
        scope_kwargs = {"pipeline": pipeline, "workflow": None, "stage": None}
        scope_name = f"pipeline {pipeline.name_en}"
    else:
        scope_kwargs = {"workflow": workflow, "pipeline": None, "stage": None}
        scope_name = f"workflow {workflow.name_en}"

    # Check if actions already exist
    if not force:
        existing_actions = WorkflowAction.objects.filter(**scope_kwargs)
        if existing_actions.exists():
            logger.info(
                f"Default actions already exist for {scope_name}, skipping creation"
            )
            return list(existing_actions)

    # Define default actions with their configurations
    default_actions_config = [
        {
            "action_type": ActionType.AFTER_APPROVE,
            "function_path": "django_workflow_engine.action_handlers.send_approval_notification",
            "order": 1,
            "parameters": {
                "template": "workflow_approved",
                "recipients": ["creator"],
                "subject": "Workflow Approved",
            },
        },
        {
            "action_type": ActionType.AFTER_REJECT,
            "function_path": "django_workflow_engine.action_handlers.send_rejection_notification",
            "order": 1,
            "parameters": {
                "template": "workflow_rejected",
                "recipients": ["creator"],
                "subject": "Workflow Rejected",
            },
        },
        {
            "action_type": ActionType.AFTER_RESUBMISSION,
            "function_path": "django_workflow_engine.action_handlers.send_resubmission_notification",
            "order": 1,
            "parameters": {
                "template": "workflow_resubmission_required",
                "recipients": ["creator", "current_approver"],
                "subject": "Resubmission Required",
            },
        },
        {
            "action_type": ActionType.AFTER_DELEGATE,
            "function_path": "django_workflow_engine.action_handlers.send_delegation_notification",
            "order": 1,
            "parameters": {
                "template": "workflow_delegated",
                "recipients": ["delegated_to", "creator"],
                "subject": "Workflow Delegated",
            },
        },
        {
            "action_type": ActionType.AFTER_MOVE_STAGE,
            "function_path": "django_workflow_engine.action_handlers.send_stage_move_notification",
            "order": 1,
            "parameters": {
                "template": "workflow_action_required",
                "recipients": ["creator"],
                "subject": "Workflow Progressed to Next Stage",
            },
        },
    ]

    # Create actions
    for config in default_actions_config:
        try:
            action = WorkflowAction.objects.create(
                **scope_kwargs,
                action_type=config["action_type"],
                function_path=config["function_path"],
                is_active=True,
                parameters=config["parameters"],
                order=config["order"],
            )
            created_actions.append(action)
            logger.info(
                f"Created default action {config['action_type']} for {scope_name}"
            )
        except Exception as e:
            logger.error(
                f"Failed to create default action {config['action_type']} for {scope_name}: {e}"
            )

    logger.info(f"Created {len(created_actions)} default actions for {scope_name}")
    return created_actions


def clone_workflow_actions(
    source_workflow: WorkFlow,
    target_workflow: WorkFlow,
    pipeline_mapping: Optional[dict] = None,
) -> dict:
    """
    Clone workflow actions from source to target workflow.

    This clones actions at all levels:
    - Workflow-level actions
    - Pipeline-level actions (mapped to new pipelines)
    - Stage-level actions (mapped to new stages)

    Args:
        source_workflow: Source workflow to clone from
        target_workflow: Target workflow to clone to
        pipeline_mapping: Optional dict mapping source pipeline IDs to target pipeline instances

    Returns:
        Dict with counts of cloned actions at each level

    Example:
        result = clone_workflow_actions(old_workflow, new_workflow, pipeline_map)
        # Returns: {'workflow': 5, 'pipeline': 10, 'stage': 15}
    """
    cloned_counts = {"workflow": 0, "pipeline": 0, "stage": 0}

    # Clone workflow-level actions
    workflow_actions = WorkflowAction.objects.filter(
        workflow=source_workflow, pipeline__isnull=True, stage__isnull=True
    )

    for action in workflow_actions:
        try:
            WorkflowAction.objects.create(
                workflow=target_workflow,
                pipeline=None,
                stage=None,
                action_type=action.action_type,
                function_path=action.function_path,
                is_active=action.is_active,
                parameters=action.parameters.copy() if action.parameters else {},
                order=action.order,
            )
            cloned_counts["workflow"] += 1
        except Exception as e:
            logger.error(f"Failed to clone workflow action {action.id}: {e}")

    # Clone pipeline and stage actions if mapping provided
    if pipeline_mapping:
        for source_pipeline_id, pipeline_data in pipeline_mapping.items():
            target_pipeline = pipeline_data.get("created_pipeline")
            if not target_pipeline:
                continue

            # Clone pipeline-level actions
            pipeline_actions = WorkflowAction.objects.filter(
                pipeline_id=source_pipeline_id, stage__isnull=True
            )

            for action in pipeline_actions:
                try:
                    WorkflowAction.objects.create(
                        workflow=None,
                        pipeline=target_pipeline,
                        stage=None,
                        action_type=action.action_type,
                        function_path=action.function_path,
                        is_active=action.is_active,
                        parameters=(
                            action.parameters.copy() if action.parameters else {}
                        ),
                        order=action.order,
                    )
                    cloned_counts["pipeline"] += 1
                except Exception as e:
                    logger.error(f"Failed to clone pipeline action {action.id}: {e}")

            # Clone stage-level actions
            source_stages = pipeline_data.get("stages", [])
            target_stages = target_pipeline.stages.all()

            # Create stage mapping based on order
            stage_mapping = {}
            for idx, source_stage in enumerate(source_stages):
                if idx < len(target_stages):
                    stage_mapping[source_stage.id] = target_stages[idx]

            for source_stage_id, target_stage in stage_mapping.items():
                stage_actions = WorkflowAction.objects.filter(stage_id=source_stage_id)

                for action in stage_actions:
                    try:
                        WorkflowAction.objects.create(
                            workflow=None,
                            pipeline=None,
                            stage=target_stage,
                            action_type=action.action_type,
                            function_path=action.function_path,
                            is_active=action.is_active,
                            parameters=(
                                action.parameters.copy() if action.parameters else {}
                            ),
                            order=action.order,
                        )
                        cloned_counts["stage"] += 1
                    except Exception as e:
                        logger.error(f"Failed to clone stage action {action.id}: {e}")

    logger.info(
        f"Cloned actions - Workflow: {cloned_counts['workflow']}, "
        f"Pipeline: {cloned_counts['pipeline']}, Stage: {cloned_counts['stage']}"
    )

    return cloned_counts


def get_effective_actions(
    action_type: str,
    workflow: WorkFlow,
    pipeline: Optional[Pipeline] = None,
    stage: Optional[Stage] = None,
) -> List[WorkflowAction]:
    """
    Get effective actions for a given event using priority system.

    Priority order:
    1. Database actions (custom): Stage -> Pipeline -> Workflow
    2. Settings-based actions: WORKFLOW_ACTIONS_CONFIG
    3. Default actions: Built-in email notifications

    Args:
        action_type: Type of action (from ActionType choices)
        workflow: Workflow instance
        pipeline: Optional pipeline instance
        stage: Optional stage instance

    Returns:
        List of WorkflowAction instances to execute

    Example:
        actions = get_effective_actions(
            ActionType.AFTER_APPROVE,
            workflow=my_workflow,
            stage=current_stage
        )
    """
    from django.conf import settings

    # Priority 1: Try database actions with inheritance (Stage -> Pipeline -> Workflow)
    # Try stage-level first
    if stage:
        stage_actions = WorkflowAction.objects.filter(
            stage=stage, action_type=action_type, is_active=True
        ).order_by("order")

        if stage_actions.exists():
            logger.debug(
                f"Found {stage_actions.count()} stage-level DB actions for {action_type}"
            )
            return list(stage_actions)

    # Try pipeline-level
    if pipeline:
        pipeline_actions = WorkflowAction.objects.filter(
            pipeline=pipeline,
            stage__isnull=True,
            action_type=action_type,
            is_active=True,
        ).order_by("order")

        if pipeline_actions.exists():
            logger.debug(
                f"Found {pipeline_actions.count()} pipeline-level DB actions for {action_type}"
            )
            return list(pipeline_actions)

    # Try workflow-level
    workflow_actions = WorkflowAction.objects.filter(
        workflow=workflow,
        pipeline__isnull=True,
        stage__isnull=True,
        action_type=action_type,
        is_active=True,
    ).order_by("order")

    if workflow_actions.exists():
        logger.debug(
            f"Found {workflow_actions.count()} workflow-level DB actions for {action_type}"
        )
        return list(workflow_actions)

    # Priority 2: Check settings for configured actions
    settings_actions_config = getattr(settings, "WORKFLOW_ACTIONS_CONFIG", None)

    # Check if WORKFLOW_ACTIONS_CONFIG is explicitly set (even if empty)
    # - None/not set → use defaults (Priority 3)
    # - [] (empty list) → disable all actions (return empty)
    # - [...] (has items) → use only configured actions
    if settings_actions_config is not None:
        # WORKFLOW_ACTIONS_CONFIG is explicitly configured
        # Empty list means "disable all actions"
        if not settings_actions_config:
            logger.debug(
                f"WORKFLOW_ACTIONS_CONFIG is empty - all actions disabled for {action_type}"
            )
            return []

        # Filter actions by action_type
        matching_configs = [
            config
            for config in settings_actions_config
            if config.get("action_type") == action_type
        ]

        if matching_configs:
            logger.debug(
                f"Found {len(matching_configs)} settings-based actions for {action_type}"
            )
            # Convert settings config to WorkflowAction-like objects
            settings_actions = []
            for config in sorted(matching_configs, key=lambda x: x.get("order", 1)):
                # Create a mock WorkflowAction object with the config data
                action = WorkflowAction(
                    workflow=workflow,
                    action_type=config.get("action_type"),
                    function_path=config.get("function_path"),
                    parameters=config.get("parameters", {}),
                    order=config.get("order", 1),
                    is_active=True,
                )
                settings_actions.append(action)
            return settings_actions
        else:
            # WORKFLOW_ACTIONS_CONFIG has actions but action_type not included
            # This means user explicitly doesn't want any action for this type
            logger.debug(
                f"WORKFLOW_ACTIONS_CONFIG is set but {action_type} not configured - "
                "no action will be performed"
            )
            return []

    # No actions configured - return empty list (do not use default actions)
    logger.debug(
        f"No actions found for {action_type} - no action will be executed. "
        "To configure actions, use WorkflowAction model or WORKFLOW_ACTIONS_CONFIG setting."
    )
    return []
