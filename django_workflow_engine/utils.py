"""Utility functions for the django_workflow_engine package.

This module provides helper functions for workflow management.
Approval flow utilities are provided by the django-approval-workflow package.
"""

import logging
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.contrib.auth import get_user_model

from approval_workflow.choices import RoleSelectionStrategy

from .choices import ApprovalTypes

logger = logging.getLogger(__name__)
User = get_user_model()


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


def build_approval_steps(stage, created_by_user: User) -> List[Dict[str, Any]]:
    """Build approval steps for a workflow stage with optimized batch queries.

    Args:
        stage: The Stage instance
        created_by_user: The user who created the workflow item

    Returns:
        List of approval step configurations
    """
    approvals = get_workflow_stage_approvers(stage, created_by_user)
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
    for i, approval_data in enumerate(approvals, start=1):
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
