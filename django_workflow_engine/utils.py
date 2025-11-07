"""Utility functions for the django_workflow_engine package.

This module provides helper functions for workflow management.
Approval flow utilities are provided by the django-approval-workflow package.
"""

import logging
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Model

from approval_workflow.choices import ApprovalType, RoleSelectionStrategy

from .choices import ApprovalTypes, WorkflowStrategy
from .constants import ERROR_MESSAGES

logger = logging.getLogger(__name__)
User = get_user_model()


def get_user_for_approval(
    obj: Model, user: Optional[User] = None, attachment=None
) -> Optional[User]:
    """Get user for approval with proper fallback logic.

    This utility function implements a consistent fallback strategy for finding
    a user to use for approval step creation. It tries multiple sources in order:
    1. Provided user parameter
    2. obj.created_by
    3. obj.started_by
    4. attachment.started_by

    Args:
        obj: The model instance being processed
        user: Optional user to use (highest priority)
        attachment: Optional WorkflowAttachment instance for additional fallback

    Returns:
        User instance or None if no user found

    Example:
        >>> approval_user = get_user_for_approval(purchase_request, user=current_user)
        >>> if approval_user:
        ...     steps = build_approval_steps(stage, approval_user)
    """
    if user:
        return user

    if hasattr(obj, "created_by") and obj.created_by:
        return obj.created_by

    if hasattr(obj, "started_by") and obj.started_by:
        return obj.started_by

    if attachment and hasattr(attachment, "started_by") and attachment.started_by:
        return attachment.started_by

    logger.warning(
        ERROR_MESSAGES["no_user_for_approval"].format(
            obj_label=obj._meta.label, obj_pk=obj.pk
        )
    )
    return None


def get_workflow_stage_approvers(stage, created_by_user: User) -> List[Dict[str, Any]]:
    """Get approvers configuration for a workflow stage.

    Args:
        stage: The Stage instance
        created_by_user: The user who created the workflow item

    Returns:
        List of approver configurations
    """
    if not hasattr(stage, "stage_info") or not stage.stage_info:
        # Default to self-approval by creator
        return [
            {
                "approval_user": created_by_user,
                "approval_type": ApprovalTypes.SELF,
            }
        ]

    approvals = stage.stage_info.get("approvals", [])
    if not approvals:
        # Default to self-approval by creator
        return [
            {
                "approval_user": created_by_user,
                "approval_type": ApprovalTypes.SELF,
            }
        ]

    return approvals


def build_approval_steps(
    stage, created_by_user: Optional[User], start_step: int = 1
) -> List[Dict[str, Any]]:
    """Build approval steps for a workflow with strategy-aware approval extraction.

    This function handles all 3 workflow strategies:
    - Strategy 1 (Workflow Only): Approvals from workflow.workflow_info
    - Strategy 2 (Workflow→Pipeline): Approvals from pipeline.pipeline_info
    - Strategy 3 (Workflow→Pipeline→Stage): Approvals from stage.stage_info (default)

    Args:
        stage: The Stage instance (used for strategy 3 and to access workflow/pipeline)
        created_by_user: The user who created the workflow item (can be None)
        start_step: The starting step number (default: 1). Use this to continue
                   numbering from a specific point, e.g., after resubmission or
                   when extending an existing flow.

    Returns:
        List of approval step configurations

    Raises:
        ValueError: If created_by_user is None and required for approval steps

    Example:
        # Start from step 1 (default)
        steps = build_approval_steps(stage, user)

        # Continue from step 10 (e.g., after resubmission)
        steps = build_approval_steps(stage, user, start_step=10)
    """
    if not created_by_user:
        logger.error(
            f"No user provided for building approval steps for stage {stage.id} ({stage.name_en}). "
            "This will cause issues with user-based approvals."
        )
        # Return empty list instead of proceeding with None user
        # This prevents cascading errors in approval flow creation
        return []

    # Get workflow to determine strategy
    workflow = stage.pipeline.workflow if stage and stage.pipeline else None
    if not workflow:
        logger.error(f"No workflow found for stage {stage.id} ({stage.name_en})")
        return []

    strategy = workflow.strategy

    # Extract approvals based on strategy
    if strategy == WorkflowStrategy.WORKFLOW_PIPELINE_STAGE:
        # Strategy 1: Get approvals from stage.stage_info (full hierarchy - default behavior)
        approvals = get_workflow_stage_approvers(stage, created_by_user)
        logger.debug(
            f"Using Strategy 1 (Workflow→Pipeline→Stage) - Found {len(approvals)} approvals in stage.stage_info"
        )
    elif strategy == WorkflowStrategy.WORKFLOW_PIPELINE:
        # Strategy 2: Get approvals from pipeline.pipeline_info (no stages)
        pipeline = stage.pipeline
        pipeline_info = pipeline.pipeline_info or {}
        approvals = pipeline_info.get("approvals", [])
        logger.debug(
            f"Using Strategy 2 (Workflow→Pipeline) - Found {len(approvals)} approvals in pipeline.pipeline_info"
        )
    elif strategy == WorkflowStrategy.WORKFLOW_ONLY:
        # Strategy 3: Get approvals from workflow.workflow_info (no pipelines/stages)
        workflow_info = workflow.workflow_info or {}
        approvals = workflow_info.get("approvals", [])
        logger.debug(
            f"Using Strategy 3 (Workflow Only) - Found {len(approvals)} approvals in workflow.workflow_info"
        )
    else:
        logger.error(f"Unknown workflow strategy: {strategy}")
        approvals = []

    # If no approvals found, default to self-approval
    if not approvals:
        logger.warning(
            f"No approvals found for stage {stage.id} using strategy {strategy}, "
            f"defaulting to self-approval"
        )
        approvals = [
            {
                "approval_user": created_by_user,
                "approval_type": ApprovalTypes.SELF,
            }
        ]
    steps = []

    # Batch fetch all users, roles, and forms to avoid N+1 queries
    user_ids = []
    role_ids = []
    form_ids = []

    for approval_data in approvals:
        approval_type = approval_data.get("approval_type", ApprovalTypes.SELF)

        # Collect user IDs
        if approval_type in (
            ApprovalTypes.SELF,
            ApprovalTypes.USER,
        ) or approval_data.get("approval_user"):
            approval_user = approval_data.get("approval_user")
            if isinstance(approval_user, int):
                user_ids.append(approval_user)
            elif isinstance(approval_user, dict) and "val" in approval_user:
                user_ids.append(approval_user["val"])

        # Collect role IDs
        if approval_type == ApprovalTypes.ROLE and approval_data.get("user_role"):
            role_ids.append(approval_data["user_role"])

        # Collect form IDs
        if approval_data.get("required_form"):
            form_id = approval_data["required_form"]
            if isinstance(form_id, dict) and "val" in form_id:
                form_ids.append(form_id["val"])
            else:
                form_ids.append(form_id)

    # Batch fetch all users
    users_map = {}
    if user_ids:
        users_map = {user.id: user for user in User.objects.filter(id__in=user_ids)}

    # Batch fetch all roles
    roles_map = {}
    if role_ids:
        try:
            from django.apps import apps

            role_model_path = getattr(settings, "APPROVAL_ROLE_MODEL", "common.Role")
            app_label, model_name = role_model_path.split(".")
            RoleModel = apps.get_model(app_label, model_name)
            roles_map = {
                role.id: role for role in RoleModel.objects.filter(id__in=role_ids)
            }
        except Exception as e:
            logger.error(f"Error fetching roles: {e}")

    # Batch fetch all forms
    forms_map = {}
    if form_ids:
        try:
            from django.apps import apps

            form_model_path = getattr(
                settings, "APPROVAL_DYNAMIC_FORM_MODEL", "common.DynamicForm"
            )
            app_label, model_name = form_model_path.split(".")
            FormModel = apps.get_model(app_label, model_name)
            forms_map = {
                form.id: form for form in FormModel.objects.filter(id__in=form_ids)
            }
        except Exception as e:
            logger.error(f"Error fetching forms: {e}")

    # Build steps using cached data
    # Use start_step to continue numbering from a specific point
    for i, approval_data in enumerate(approvals, start=start_step):
        step = {
            "step": i,
            "extra_fields": {"stage_id": stage.id},
        }

        approval_type = approval_data.get("approval_type", ApprovalTypes.SELF)

        if approval_type in (
            ApprovalTypes.SELF,
            ApprovalTypes.USER,
        ) or approval_data.get("approval_user"):
            # User-specific approval
            approval_user = approval_data.get("approval_user", created_by_user)
            if isinstance(approval_user, int):
                approval_user = users_map.get(approval_user, created_by_user)
            elif isinstance(approval_user, dict) and "val" in approval_user:
                user_id = approval_user["val"]
                approval_user = users_map.get(user_id, created_by_user)
            step["assigned_to"] = approval_user

        elif approval_type == ApprovalTypes.ROLE and approval_data.get("user_role"):
            # Role-based approval
            role_id = approval_data["user_role"]
            role = roles_map.get(role_id)
            if role:
                step["assigned_role"] = role
                role_selection_strategy = approval_data.get("role_selection_strategy")
                step["role_selection_strategy"] = (
                    role_selection_strategy
                    if role_selection_strategy is not None
                    else RoleSelectionStrategy.ANYONE
                )
            else:
                logger.error(
                    f"Role with ID {role_id} not found, falling back to self-approval"
                )
                step["assigned_to"] = created_by_user

        # Add form if specified
        if approval_data.get("required_form"):
            form_id = approval_data["required_form"]
            if isinstance(form_id, dict) and "val" in form_id:
                form_id = form_id["val"]

            form = forms_map.get(form_id)
            if form:
                step["form"] = form
            else:
                logger.error(f"Form with ID {form_id} not found")

        # Add step_approval_type (APPROVE, SUBMIT, CHECK_IN_VERIFY, MOVE)
        # This determines the behavior of the approval step
        step_approval_type = approval_data.get("step_approval_type")
        if step_approval_type:
            # Validate it's a valid ApprovalType
            valid_step_types = [choice[0] for choice in ApprovalType.choices]
            if step_approval_type in valid_step_types:
                step["approval_type"] = step_approval_type
            else:
                logger.warning(
                    f"Invalid step_approval_type '{step_approval_type}', defaulting to APPROVE"
                )
                step["approval_type"] = ApprovalType.APPROVE
        else:
            # Default to APPROVE if not specified
            step["approval_type"] = ApprovalType.APPROVE

        steps.append(step)

    return steps


def get_next_workflow_stage(current_stage) -> Optional:
    """Get the next stage in the workflow progression.

    Args:
        current_stage: The current Stage instance

    Returns:
        Next Stage instance or None if at the end
    """
    if not current_stage:
        return None

    workflow = current_stage.pipeline.workflow
    current_pipeline = current_stage.pipeline

    # Try to get next stage in current pipeline
    next_stage = (
        current_pipeline.stages.filter(order__gt=current_stage.order)
        .order_by("order")
        .first()
    )

    if next_stage:
        return next_stage

    # Move to first stage of next pipeline
    next_pipeline = (
        workflow.pipelines.filter(order__gt=current_pipeline.order)
        .order_by("order")
        .first()
    )

    if next_pipeline:
        return next_pipeline.stages.order_by("order").first()

    return None


def build_approval_steps_from_config(
    approvals: List[Dict[str, Any]],
    approval_user: Optional[User],
    extra_fields: Dict[str, Any] = None,
    start_step: int = 1,
) -> List[Dict[str, Any]]:
    """Build approval steps from approval configuration (for strategies 2 and 3).

    This helper function extracts the common logic for building approval steps
    from pipeline_info or workflow_info configurations.

    Args:
        approvals: List of approval configurations
        approval_user: Default user to use if none specified
        extra_fields: Extra fields to add to each step
        start_step: Starting step number (default: 1)

    Returns:
        List of approval step configurations
    """
    from django.apps import apps
    from django.conf import settings
    from django.contrib.auth import get_user_model

    from approval_workflow.choices import ApprovalType as ApprovalFlowType
    from approval_workflow.choices import RoleSelectionStrategy

    if not approvals:
        return []

    steps = []
    UserModel = get_user_model()

    for i, approval_data in enumerate(approvals, start=start_step):
        step = {
            "step": i,
            "extra_fields": extra_fields.copy() if extra_fields else {},
        }

        approval_type = approval_data.get("approval_type", "self-approved")

        # Handle user-based approvals
        if approval_type in ("self-approved", "user") or approval_data.get(
            "approval_user"
        ):
            approval_user_data = approval_data.get("approval_user", approval_user)
            if isinstance(approval_user_data, int):
                try:
                    step["assigned_to"] = UserModel.objects.get(id=approval_user_data)
                except UserModel.DoesNotExist:
                    step["assigned_to"] = approval_user
            else:
                step["assigned_to"] = approval_user

        # Handle role-based approvals
        elif approval_type == "role" and approval_data.get("user_role"):
            try:
                role_model_path = getattr(
                    settings, "APPROVAL_ROLE_MODEL", "common.Role"
                )
                app_label, model_name = role_model_path.split(".")
                RoleModel = apps.get_model(app_label, model_name)
                role = RoleModel.objects.get(id=approval_data["user_role"])
                step["assigned_role"] = role
                step["role_selection_strategy"] = approval_data.get(
                    "role_selection_strategy", RoleSelectionStrategy.ANYONE
                )
            except Exception as e:
                logger.error(f"Error fetching role: {e}")
                step["assigned_to"] = approval_user

        # Handle step approval type (APPROVE, SUBMIT, CHECK_IN_VERIFY, MOVE)
        step_approval_type = approval_data.get("step_approval_type")
        if step_approval_type:
            valid_types = [choice[0] for choice in ApprovalFlowType.choices]
            if step_approval_type in valid_types:
                step["approval_type"] = step_approval_type
            else:
                step["approval_type"] = ApprovalFlowType.APPROVE
        else:
            step["approval_type"] = ApprovalFlowType.APPROVE

        steps.append(step)

    return steps


def get_workflow_location_string(attachment) -> str:
    """Get human-readable location string based on workflow strategy.

    Returns a location string like:
    - Strategy 1: "stage: Stage Name"
    - Strategy 2: "pipeline: Pipeline Name"
    - Strategy 3: "workflow: Workflow Name"

    Args:
        attachment: WorkflowAttachment instance

    Returns:
        Location string describing current position in workflow
    """
    from .choices import WorkflowStrategy

    if not attachment:
        return "unknown"

    strategy = attachment.workflow.strategy

    if strategy == WorkflowStrategy.WORKFLOW_PIPELINE_STAGE:
        return f"stage: {attachment.current_stage.name_en if attachment.current_stage else 'None'}"
    elif strategy == WorkflowStrategy.WORKFLOW_PIPELINE:
        return f"pipeline: {attachment.current_pipeline.name_en if attachment.current_pipeline else 'None'}"
    else:  # WorkflowStrategy.WORKFLOW_ONLY
        return f"workflow: {attachment.workflow.name_en}"


def get_workflow_first_stage(workflow) -> Optional:
    """Get the first stage of a workflow.

    Args:
        workflow: The WorkFlow instance

    Returns:
        First Stage instance or None
    """
    first_pipeline = workflow.pipelines.order_by("order").first()
    if first_pipeline:
        return first_pipeline.stages.order_by("order").first()
    return None


def flatten_form_info(form_info: List[Dict], submitted_data: dict) -> List[Dict]:
    """
    Recursively flatten form_info structure based on submitted answers.

    This function handles nested/conditional forms where certain choices
    trigger additional form fields to be displayed. It flattens the structure
    based on what was actually submitted.

    Args:
        form_info: The form field specifications (can contain nested forms)
        submitted_data: The submitted form data

    Returns:
        Flattened list of all field specifications that apply based on submitted data

    Example:
        form_info = [
            {
                "field_name": "department",
                "field_type": "DROP_DOWN",
                "extra_info": {
                    "choice_form": {
                        "choice": "IT",
                        "form": {
                            "field_name": "it_budget",
                            "field_type": "NUMBER"
                        }
                    }
                }
            }
        ]
        submitted_data = {"department": "IT", "it_budget": 50000}
        # Returns both department and it_budget fields flattened
    """
    flat_fields = []

    for field in form_info:
        flat_fields.append(field)
        ftype = field.get("field_type")
        extra_info = field.get("extra_info", {})

        # Normalize in case extra_info is a list (e.g., ["Low", "High"])
        if isinstance(extra_info, list):
            continue

        choice_form = extra_info.get("choice_form")
        if not choice_form:
            continue

        trigger_choice = choice_form.get("choice")
        submitted_value = submitted_data.get(field["field_name"])

        # Normalize trigger_choice and submitted_value to strings for comparison
        # This handles cases where choice is int (1) but submitted value is string ("1")
        trigger_choice_str = str(trigger_choice) if trigger_choice is not None else None

        # Determine if the conditional form should be triggered
        should_trigger = False
        if ftype in ("MULTI_CHOICE", "CHECKBOX"):
            # For multi-choice, submitted_value is a list
            if submitted_value:
                # Normalize submitted values to strings for comparison
                submitted_values_str = [str(v) for v in (submitted_value or [])]
                should_trigger = trigger_choice_str in submitted_values_str
        elif ftype == "DROP_DOWN":
            # For dropdown, submitted_value is a single value
            submitted_value_str = (
                str(submitted_value) if submitted_value is not None else None
            )
            should_trigger = trigger_choice_str == submitted_value_str

        if should_trigger:
            subform = choice_form.get("form")
            if subform:
                # Recursively flatten nested forms
                flat_fields.extend(flatten_form_info([subform], submitted_data))

    return flat_fields


def enrich_answers(
    form_info: List[Dict],
    answers: dict,
    *,
    request=None,
    object_id: int = None,
    save_files: bool = True,
) -> List[Dict]:
    """
    Enrich form answers by combining field specifications with submitted values.

    This function takes the form field definitions and the submitted answers,
    and creates an enriched structure where each field spec includes the
    submitted answer. It also handles file uploads by saving them and
    converting to URLs.

    Args:
        form_info: List of form field specifications
        answers: Dictionary of submitted answers {field_name: value}
        request: Django request object (needed for building absolute URLs)
        object_id: ID of the object these answers are for (used in file paths)
        save_files: Whether to save uploaded files (default: True)

    Returns:
        List of enriched field specs with 'answer' key added to each

    Example:
        form_info = [
            {"field_name": "name", "field_type": "TEXT"},
            {"field_name": "budget", "field_type": "NUMBER"}
        ]
        answers = {"name": "Project Alpha", "budget": 50000}

        # Returns:
        # [
        #     {"field_name": "name", "field_type": "TEXT", "answer": "Project Alpha"},
        #     {"field_name": "budget", "field_type": "NUMBER", "answer": 50000}
        # ]
    """
    enriched = []

    for spec in form_info or []:
        fname = spec["field_name"]
        if fname not in answers:
            continue

        answer = answers[fname]

        # If this is a file, save and generate full URL
        if (
            save_files
            and spec.get("field_type") in ("FILE", "UPLOAD")
            and isinstance(answer, UploadedFile)
        ):
            if object_id and request:
                path = default_storage.save(
                    f"workflows/{object_id}/{answer.name}", answer
                )
                relative_url = default_storage.url(path)
                answer = request.build_absolute_uri(relative_url)
            else:
                logger.warning(
                    f"Cannot save file for field '{fname}' - missing object_id or request"
                )

        enriched.append({**spec, "answer": answer})

    return enriched
