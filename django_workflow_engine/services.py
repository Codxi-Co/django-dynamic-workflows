"""Workflow management services.

This module provides services for managing workflows, pipelines, and stages.
Approval flow functionality is handled by the django-approval-workflow package.
"""

import logging
from typing import Any, Dict, List, Optional, Type

from django.contrib.auth import get_user_model
from django.db.models import Model
from django.utils import timezone

from approval_workflow.models import ApprovalFlow

from .choices import DEFAULT_ACTIONS, ActionType, WorkflowAttachmentStatus
from .models import (
    Pipeline,
    Stage,
    WorkFlow,
    WorkflowAction,
    WorkflowAttachment,
    WorkflowConfiguration,
)
from .settings import (
    get_auto_start_workflows,
    get_default_workflow_status_field,
    get_workflow_model_mappings,
)
from .settings import is_model_workflow_enabled as is_model_enabled_in_settings

logger = logging.getLogger(__name__)

User = get_user_model()


def log_workflow_action(
    action: str,
    workflow_id: int = None,
    user_id: int = None,
    object_type: str = None,
    object_id: str = None,
    **kwargs,
):
    """Log workflow actions with structured data for monitoring and debugging."""
    logger.info(
        f"WORKFLOW_ACTION: {action}",
        extra={
            "action": action,
            "workflow_id": workflow_id,
            "user_id": user_id,
            "object_type": object_type,
            "object_id": object_id,
            "timestamp": timezone.now().isoformat(),
            **kwargs,
        },
    )


# Workflow management services


def create_workflow(
    company,
    name_en: str,
    name_ar: str,
    created_by: User,
    pipelines_data: List[Dict[str, Any]],
) -> WorkFlow:
    """Create a new workflow with pipelines and stages.

    Args:
        company: Company instance
        name_en: English name
        name_ar: Arabic name
        created_by: User creating the workflow
        pipelines_data: List of pipeline configurations

    Returns:
        The created WorkFlow instance
    """
    workflow = WorkFlow.objects.create(
        company=company, name_en=name_en, name_ar=name_ar, created_by=created_by
    )

    log_workflow_action(
        action="workflow_created",
        workflow_id=workflow.id,
        user_id=created_by.id,
        company_id=company.id,
        pipeline_count=len(pipelines_data),
    )

    for pipeline_data in pipelines_data:
        create_pipeline(workflow, pipeline_data, created_by)

    logger.info(
        "Workflow created - ID: %s, Name: %s, Pipelines: %d",
        workflow.id,
        name_en,
        len(pipelines_data),
    )

    return workflow


def create_pipeline(
    workflow: WorkFlow, pipeline_data: Dict[str, Any], created_by: User
) -> Pipeline:
    """Create a pipeline within a workflow.

    Args:
        workflow: The WorkFlow to attach the pipeline to
        pipeline_data: Pipeline configuration
        created_by: User creating the pipeline

    Returns:
        The created Pipeline instance
    """
    pipeline = Pipeline.objects.create(
        workflow=workflow,
        company=workflow.company,
        name_en=pipeline_data["name_en"],
        name_ar=pipeline_data["name_ar"],
        department_id=pipeline_data["department_id"],
        created_by=created_by,
        order=pipeline_data.get("order", 0),
    )

    # Create stages for the pipeline
    number_of_stages = pipeline_data.get("number_of_stages", 1)
    for i in range(number_of_stages):
        Stage.objects.create(
            pipeline=pipeline,
            company=workflow.company,
            name_en=f"Stage {i + 1}",
            name_ar=f"المرحلة {i + 1}",
            created_by=created_by,
            order=i,
        )

    logger.info(
        "Pipeline created - ID: %s, Workflow: %s, Stages: %d",
        pipeline.id,
        workflow.name_en,
        number_of_stages,
    )

    return pipeline


def get_workflow_progress(workflow: WorkFlow, obj: Model) -> Dict[str, Any]:
    """Get the progress of an object through a workflow.

    Args:
        workflow: The WorkFlow to check progress for
        obj: The object progressing through the workflow

    Returns:
        Dictionary containing progress information
    """
    try:
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(obj)

        attachment = WorkflowAttachment.objects.get(
            content_type=content_type, object_id=str(obj.pk)
        )

        return attachment.get_progress_info()
    except WorkflowAttachment.DoesNotExist:
        return {
            "current_stage": None,
            "current_pipeline": None,
            "status": WorkflowAttachmentStatus.NOT_STARTED,
            "progress_percentage": 0,
            "started_at": None,
            "completed_at": None,
            "next_stage": None,
        }


# Workflow Attachment Services


def attach_workflow_to_object(
    obj: Model,
    workflow: WorkFlow,
    user: User = None,
    auto_start: bool = True,
    metadata: Dict[str, Any] = None,
) -> WorkflowAttachment:
    """Attach a workflow to any model instance.

    Args:
        obj: The model instance to attach workflow to
        workflow: The WorkFlow to attach
        user: User who is attaching the workflow
        auto_start: Whether to automatically start the workflow
        metadata: Additional metadata to store

    Returns:
        WorkflowAttachment instance
    """
    from django.contrib.contenttypes.models import ContentType
    from django.utils import timezone

    if not workflow.is_active:
        raise ValueError(
            f"Workflow '{workflow.name_en}' is not active and cannot be attached"
        )

    content_type = ContentType.objects.get_for_model(obj)

    # Create or get existing attachment
    attachment, created = WorkflowAttachment.objects.get_or_create(
        content_type=content_type,
        object_id=str(obj.pk),
        defaults={
            "workflow": workflow,
            "metadata": metadata or {},
            "started_by": user,
        },
    )

    if not created:
        # Update existing attachment
        attachment.workflow = workflow
        attachment.metadata.update(metadata or {})
        attachment.save()

    log_workflow_action(
        action="workflow_attached" if created else "workflow_updated",
        workflow_id=workflow.id,
        user_id=user.id if user else None,
        object_type=content_type.model,
        object_id=str(obj.pk),
        auto_start=auto_start,
    )

    logger.info(
        f"Workflow '{workflow.name_en}' {'attached' if created else 'updated'} to {obj._meta.label}({obj.pk})"
    )

    # Auto-start if requested
    if auto_start and attachment.status == WorkflowAttachmentStatus.NOT_STARTED:
        start_workflow_for_object(obj, user)

    return attachment


def start_workflow_for_object(obj: Model, user: User = None) -> WorkflowAttachment:
    """Start workflow execution for an object.

    Args:
        obj: The model instance to start workflow for
        user: User who is starting the workflow

    Returns:
        Updated WorkflowAttachment instance
    """
    from django.contrib.contenttypes.models import ContentType
    from django.utils import timezone

    content_type = ContentType.objects.get_for_model(obj)

    try:
        attachment = WorkflowAttachment.objects.get(
            content_type=content_type, object_id=str(obj.pk)
        )
    except WorkflowAttachment.DoesNotExist:
        raise ValueError(f"No workflow attached to {obj._meta.label}({obj.pk})")

    if attachment.status != WorkflowAttachmentStatus.NOT_STARTED:
        raise ValueError(f"Workflow already started (status: {attachment.status})")

    # Get first stage
    first_pipeline = attachment.workflow.pipelines.order_by("order").first()
    if not first_pipeline:
        raise ValueError(f"Workflow '{attachment.workflow.name_en}' has no pipelines")

    first_stage = first_pipeline.stages.order_by("order").first()
    if not first_stage:
        raise ValueError(f"Pipeline '{first_pipeline.name_en}' has no stages")

    # Update attachment
    attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
    attachment.current_stage = first_stage
    attachment.current_pipeline = first_pipeline
    attachment.started_at = timezone.now()
    attachment.started_by = user
    attachment.save()

    # Trigger workflow start actions
    trigger_workflow_event(
        attachment, ActionType.ON_WORKFLOW_START, initial_stage=first_stage, user=user
    )

    # Start approval flow for first stage
    from approval_workflow.services import start_flow

    from .utils import build_approval_steps

    steps = build_approval_steps(first_stage, user or obj.created_by)
    if steps:
        start_flow(obj, steps)

    logger.info(
        f"Workflow started for {obj._meta.label}({obj.pk}) at stage '{first_stage.name_en}'"
    )

    return attachment


def move_to_next_stage(obj: Model, user: User = None) -> WorkflowAttachment:
    """Move object to the next stage in workflow.

    Note: This method should only be called internally by approval handlers
    (on_final_approve), not directly by API endpoints.

    Args:
        obj: The model instance to move
        user: User performing the move

    Returns:
        Updated WorkflowAttachment instance
    """
    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.get_for_model(obj)

    try:
        attachment = WorkflowAttachment.objects.get(
            content_type=content_type, object_id=str(obj.pk)
        )
    except WorkflowAttachment.DoesNotExist:
        raise ValueError(f"No workflow attached to {obj._meta.label}({obj.pk})")

    if attachment.status != WorkflowAttachmentStatus.IN_PROGRESS:
        raise ValueError(f"Workflow not in progress (status: {attachment.status})")

    current_stage = attachment.current_stage
    next_stage = attachment.next_stage

    if not next_stage:
        # Workflow complete
        return complete_workflow(obj, user)

    # Check if moving to new pipeline
    current_pipeline = attachment.current_pipeline
    next_pipeline = next_stage.pipeline
    pipeline_changed = current_pipeline.id != next_pipeline.id

    # Update attachment
    old_stage = attachment.current_stage
    old_pipeline = attachment.current_pipeline

    attachment.current_stage = next_stage
    attachment.current_pipeline = next_pipeline
    attachment.save()

    # Trigger workflow actions
    if pipeline_changed:
        # Trigger pipeline move actions
        trigger_workflow_event(
            attachment,
            ActionType.AFTER_MOVE_PIPELINE,
            from_pipeline=old_pipeline,
            to_pipeline=next_pipeline,
            user=user,
        )

    # Trigger stage move actions
    trigger_workflow_event(
        attachment,
        ActionType.AFTER_MOVE_STAGE,
        from_stage=old_stage,
        to_stage=next_stage,
        user=user,
    )

    # Start approval flow for next stage
    from approval_workflow.services import start_flow

    from .utils import build_approval_steps

    steps = build_approval_steps(next_stage, user or obj.created_by)
    if steps:
        start_flow(obj, steps)

    logger.info(
        f"Moved {obj._meta.label}({obj.pk}) from stage '{old_stage.name_en}' to '{next_stage.name_en}'"
    )

    return attachment


def reject_workflow_stage(
    obj: Model, stage, user: User = None, reason: str = None
) -> WorkflowAttachment:
    """Reject workflow at current stage.

    Args:
        obj: The model instance
        stage: The stage being rejected
        user: User performing the rejection
        reason: Rejection reason

    Returns:
        Updated WorkflowAttachment instance
    """
    from django.contrib.contenttypes.models import ContentType
    from django.utils import timezone

    content_type = ContentType.objects.get_for_model(obj)

    try:
        attachment = WorkflowAttachment.objects.get(
            content_type=content_type, object_id=str(obj.pk)
        )
    except WorkflowAttachment.DoesNotExist:
        raise ValueError(f"No workflow attached to {obj._meta.label}({obj.pk})")

    # Update attachment status
    attachment.status = WorkflowAttachmentStatus.REJECTED
    attachment.completed_at = timezone.now()
    if reason:
        attachment.metadata["rejection_reason"] = reason
        attachment.metadata["rejected_by"] = user.username if user else "system"
    attachment.save()

    # Trigger reject actions
    trigger_workflow_event(
        attachment, ActionType.AFTER_REJECT, stage=stage, reason=reason, user=user
    )

    logger.info(
        f"Workflow rejected for {obj._meta.label}({obj.pk}) at stage '{stage.name_en}'"
    )

    return attachment


def complete_workflow(obj: Model, user: User = None) -> WorkflowAttachment:
    """Complete workflow for an object.

    Args:
        obj: The model instance
        user: User completing the workflow

    Returns:
        Updated WorkflowAttachment instance
    """
    from django.contrib.contenttypes.models import ContentType
    from django.utils import timezone

    content_type = ContentType.objects.get_for_model(obj)

    try:
        attachment = WorkflowAttachment.objects.get(
            content_type=content_type, object_id=str(obj.pk)
        )
    except WorkflowAttachment.DoesNotExist:
        raise ValueError(f"No workflow attached to {obj._meta.label}({obj.pk})")

    # Update attachment
    attachment.status = WorkflowAttachmentStatus.COMPLETED
    attachment.completed_at = timezone.now()
    attachment.save()

    # Trigger workflow complete actions
    trigger_workflow_event(attachment, ActionType.ON_WORKFLOW_COMPLETE, user=user)

    logger.info(f"Workflow completed for {obj._meta.label}({obj.pk})")

    return attachment


def register_model_for_workflow(
    model_class: Type[Model],
    auto_start: bool = False,
    default_workflow: WorkFlow = None,
    status_field: str = None,
    stage_field: str = None,
    pre_start_hook: str = None,
    post_complete_hook: str = None,
) -> WorkflowConfiguration:
    """Register a model to support workflow functionality.

    Args:
        model_class: The Django model class to register
        auto_start: Whether to auto-start workflows for new instances
        default_workflow: Default workflow to use
        status_field: Field name to update with workflow status
        stage_field: Field name to update with current stage
        pre_start_hook: Hook called before workflow starts
        post_complete_hook: Hook called after workflow completes

    Returns:
        WorkflowConfiguration instance
    """
    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.get_for_model(model_class)

    config, created = WorkflowConfiguration.objects.get_or_create(
        content_type=content_type,
        defaults={
            "auto_start_workflow": auto_start,
            "default_workflow": default_workflow,
            "status_field": status_field or "",
            "stage_field": stage_field or "",
            "pre_start_hook": pre_start_hook or "",
            "post_complete_hook": post_complete_hook or "",
        },
    )

    if not created:
        # Update existing config
        config.auto_start_workflow = auto_start
        config.default_workflow = default_workflow
        config.status_field = status_field or config.status_field
        config.stage_field = stage_field or config.stage_field
        config.pre_start_hook = pre_start_hook or config.pre_start_hook
        config.post_complete_hook = post_complete_hook or config.post_complete_hook
        config.save()

    logger.info(
        f"Model {model_class._meta.label} {'registered' if created else 'updated'} for workflow functionality"
    )

    return config


def get_workflow_attachment(obj: Model) -> Optional[WorkflowAttachment]:
    """Get workflow attachment for an object.

    Args:
        obj: The model instance

    Returns:
        WorkflowAttachment instance or None
    """
    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.get_for_model(obj)

    try:
        return WorkflowAttachment.objects.get(
            content_type=content_type, object_id=str(obj.pk)
        )
    except WorkflowAttachment.DoesNotExist:
        return None


def is_model_workflow_enabled(model_class: Type[Model]) -> bool:
    """Check if a model is enabled for workflow functionality.

    Args:
        model_class: The Django model class

    Returns:
        True if enabled, False otherwise
    """
    from django.contrib.contenttypes.models import ContentType

    try:
        content_type = ContentType.objects.get_for_model(model_class)
        config = WorkflowConfiguration.objects.get(content_type=content_type)
        return config.is_enabled
    except WorkflowConfiguration.DoesNotExist:
        return False


# Action execution services


def get_actions_for_event(
    attachment: WorkflowAttachment, action_type: str
) -> List[WorkflowAction]:
    """Get all actions for a specific event type using inheritance system.

    Priority order: Stage -> Pipeline -> Workflow -> Default

    Args:
        attachment: The WorkflowAttachment instance
        action_type: The ActionType to get actions for

    Returns:
        List of WorkflowAction instances ordered by priority and execution order
    """
    actions = []

    # Stage-level actions (highest priority)
    if attachment.current_stage:
        stage_actions = WorkflowAction.objects.filter(
            stage=attachment.current_stage, action_type=action_type, is_active=True
        ).order_by("order")
        actions.extend(stage_actions)

    # Pipeline-level actions (if no stage actions found)
    if not actions and attachment.current_pipeline:
        pipeline_actions = WorkflowAction.objects.filter(
            pipeline=attachment.current_pipeline,
            action_type=action_type,
            is_active=True,
        ).order_by("order")
        actions.extend(pipeline_actions)

    # Workflow-level actions (if no pipeline actions found)
    if not actions and attachment.workflow:
        workflow_actions = WorkflowAction.objects.filter(
            workflow=attachment.workflow, action_type=action_type, is_active=True
        ).order_by("order")
        actions.extend(workflow_actions)

    # Default actions (if no workflow actions found)
    if not actions and action_type in DEFAULT_ACTIONS:
        # Create a virtual action for the default function
        default_function = DEFAULT_ACTIONS[action_type]

        # Check if there's already a default action configured
        try:
            default_action = WorkflowAction(
                action_type=action_type,
                function_path=f"django_workflow_engine.default_actions.{default_function}",
                is_active=True,
                parameters={},
                order=0,
            )
            actions.append(default_action)
        except Exception as e:
            logger.warning(f"Error creating default action for {action_type}: {str(e)}")

    return actions


def execute_action_function(
    function_path: str, context: Dict[str, Any], parameters: Dict[str, Any] = None
) -> Any:
    """Execute an action function by its path.

    Args:
        function_path: Python path to the function (e.g., 'myapp.actions.send_email')
        context: Context data to pass to the function
        parameters: Additional parameters from WorkflowAction.parameters

    Returns:
        Function result or None if execution failed
    """
    import importlib

    try:
        # Parse the function path
        module_path, function_name = function_path.rsplit(".", 1)

        # Import the module
        module = importlib.import_module(module_path)

        # Get the function
        function = getattr(module, function_name)

        # Prepare arguments
        kwargs = context.copy()
        if parameters:
            kwargs.update(parameters)

        # Execute the function
        result = function(**kwargs)

        logger.info(f"Successfully executed action function: {function_path}")
        return result

    except ImportError as e:
        logger.error(
            f"Failed to import module for action function {function_path}: {str(e)}"
        )
        return None
    except AttributeError as e:
        logger.error(
            f"Function {function_name} not found in module {module_path}: {str(e)}"
        )
        return None
    except Exception as e:
        logger.error(f"Error executing action function {function_path}: {str(e)}")
        return None


def execute_workflow_actions(
    attachment: WorkflowAttachment, action_type: str, context: Dict[str, Any]
) -> List[Any]:
    """Execute all actions for a workflow event.

    Args:
        attachment: The WorkflowAttachment instance
        action_type: The ActionType to execute actions for
        context: Context data to pass to action functions

    Returns:
        List of action results
    """
    actions = get_actions_for_event(attachment, action_type)
    results = []

    for action in actions:
        try:
            result = execute_action_function(
                function_path=action.function_path,
                context=context,
                parameters=action.parameters,
            )
            results.append(result)

        except Exception as e:
            logger.error(
                f"Failed to execute action {action.function_path} for {action_type}: {str(e)}"
            )
            results.append(None)

    return results


def trigger_workflow_event(
    attachment: WorkflowAttachment, action_type: str, **context_kwargs
) -> List[Any]:
    """Trigger a workflow event and execute associated actions.

    Args:
        attachment: The WorkflowAttachment instance
        action_type: The ActionType to trigger
        **context_kwargs: Additional context data

    Returns:
        List of action results
    """
    # Build context
    context = {
        "attachment": attachment,
        "obj": attachment.target,
        "workflow": attachment.workflow,
        "current_stage": attachment.current_stage,
        "current_pipeline": attachment.current_pipeline,
        "action_type": action_type,
        **context_kwargs,
    }

    logger.info(
        f"Triggering workflow event {action_type} for {attachment.target._meta.label}({attachment.target.pk})"
    )

    return execute_workflow_actions(attachment, action_type, context)


# New functions for workflow-to-model mapping and settings integration


def get_workflows_for_model(model_class: Type[Model]) -> List[WorkFlow]:
    """
    Get all available workflows for a specific model class.

    Args:
        model_class: Django model class

    Returns:
        List of WorkFlow instances available for this model

    Example:
        workflows = get_workflows_for_model(PurchaseRequest)
        for workflow in workflows:
            print(f"Available workflow: {workflow.name_en}")
    """
    # Check if model is enabled for workflows
    if not is_model_enabled_in_settings(model_class):
        logger.warning(
            f"Model {model_class._meta.label} is not enabled for workflows. "
            "Add it to DJANGO_WORKFLOW_ENGINE['ENABLED_MODELS'] in settings."
        )
        return []

    model_string = f"{model_class._meta.app_label}.{model_class.__name__}"
    mappings = get_workflow_model_mappings()

    # If specific mappings exist, filter by them
    if model_string in mappings:
        workflow_names = mappings[model_string]
        workflows = WorkFlow.objects.filter(
            name_en__in=workflow_names, is_active=True
        ).order_by("name_en")

        log_workflow_action(
            action="get_workflows_for_model",
            object_type=model_string,
            workflow_count=len(workflows),
            workflow_names=workflow_names,
        )

        return list(workflows)

    # If no specific mappings, return all active workflows
    # (This maintains backward compatibility)
    workflows = WorkFlow.objects.filter(is_active=True).order_by("name_en")

    log_workflow_action(
        action="get_workflows_for_model",
        object_type=model_string,
        workflow_count=len(workflows),
        note="No specific mappings configured, returning all active workflows",
    )

    return list(workflows)


def get_workflows_for_object(obj: Model) -> List[WorkFlow]:
    """
    Get all available workflows for a specific object instance.

    Args:
        obj: Django model instance

    Returns:
        List of WorkFlow instances available for this object

    Example:
        purchase_request = PurchaseRequest.objects.get(id=1)
        workflows = get_workflows_for_object(purchase_request)
        for workflow in workflows:
            print(f"Available workflow: {workflow.name_en}")
    """
    return get_workflows_for_model(obj.__class__)


def get_auto_start_workflow_for_object(obj: Model) -> Optional[WorkFlow]:
    """
    Get the auto-start workflow for an object if configured.

    Args:
        obj: Django model instance

    Returns:
        WorkFlow instance if auto-start is configured, None otherwise

    Example:
        purchase_request = PurchaseRequest.objects.create(...)
        auto_workflow = get_auto_start_workflow_for_object(purchase_request)
        if auto_workflow:
            attach_workflow_to_object(purchase_request, auto_workflow, user, auto_start=True)
    """
    if not is_model_enabled_in_settings(obj.__class__):
        return None

    model_string = f"{obj._meta.app_label}.{obj.__class__.__name__}"
    auto_start_config = get_auto_start_workflows()

    if model_string not in auto_start_config:
        return None

    config = auto_start_config[model_string]
    workflow_name = config.get("workflow_name")
    conditions = config.get("conditions", {})

    if not workflow_name:
        logger.warning(
            f"Auto-start configuration for {model_string} missing 'workflow_name'"
        )
        return None

    # Check conditions if specified
    if conditions:
        for field_lookup, expected_value in conditions.items():
            # Handle Django field lookups (e.g., 'amount__gte': 1000)
            field_parts = field_lookup.split("__")
            field_name = field_parts[0]
            lookup_type = field_parts[1] if len(field_parts) > 1 else "exact"

            if not hasattr(obj, field_name):
                logger.warning(
                    f"Field '{field_name}' not found on {model_string} for auto-start condition"
                )
                continue

            field_value = getattr(obj, field_name)

            # Apply lookup type
            condition_met = False
            if lookup_type == "exact":
                condition_met = field_value == expected_value
            elif lookup_type == "gte":
                condition_met = field_value >= expected_value
            elif lookup_type == "lte":
                condition_met = field_value <= expected_value
            elif lookup_type == "gt":
                condition_met = field_value > expected_value
            elif lookup_type == "lt":
                condition_met = field_value < expected_value
            elif lookup_type == "in":
                condition_met = field_value in expected_value
            elif lookup_type == "isnull":
                condition_met = (field_value is None) == expected_value
            else:
                logger.warning(
                    f"Unsupported lookup type '{lookup_type}' in auto-start condition"
                )
                continue

            if not condition_met:
                log_workflow_action(
                    action="auto_start_condition_not_met",
                    object_type=model_string,
                    object_id=str(obj.pk),
                    condition=field_lookup,
                    expected=expected_value,
                    actual=field_value,
                )
                return None

    # Get the workflow
    try:
        workflow = WorkFlow.objects.get(name_en=workflow_name, is_active=True)

        log_workflow_action(
            action="auto_start_workflow_found",
            object_type=model_string,
            object_id=str(obj.pk),
            workflow_id=workflow.id,
            workflow_name=workflow_name,
        )

        return workflow

    except WorkFlow.DoesNotExist:
        logger.error(
            f"Auto-start workflow '{workflow_name}' not found for {model_string}"
        )
        return None


def is_model_enabled_for_workflows(model_class: Type[Model]) -> bool:
    """
    Check if a model is enabled for workflow functionality.
    Alias for is_model_workflow_enabled for better naming consistency.

    Args:
        model_class: Django model class

    Returns:
        bool: True if model is enabled for workflows
    """
    return is_model_enabled_in_settings(model_class)


def get_available_workflows_for_selection(
    model_class: Type[Model],
) -> List[Dict[str, Any]]:
    """
    Get workflows formatted for UI selection (forms, API responses, etc).

    Args:
        model_class: Django model class

    Returns:
        List of workflow dictionaries with id, name, and description

    Example:
        workflows = get_available_workflows_for_selection(PurchaseRequest)
        # Returns: [
        #     {'id': 1, 'name': 'Purchase Approval', 'description': '...', 'slug': 'purchase_approval'},
        #     {'id': 2, 'name': 'Emergency Approval', 'description': '...', 'slug': 'emergency_approval'}
        # ]
    """
    workflows = get_workflows_for_model(model_class)

    return [
        {
            "id": workflow.id,
            "name": workflow.name_en,
            "name_ar": workflow.name_ar,
            "description": getattr(workflow, "description", ""),
            "slug": workflow.name_en.lower().replace(" ", "_"),
            "pipeline_count": workflow.pipelines.count(),
            "is_active": workflow.is_active,
        }
        for workflow in workflows
    ]
