"""Utility functions for the django_workflow_engine package.

This module provides helper functions for workflow management.
Approval flow utilities are provided by the django-approval-workflow package.
"""

import logging
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.contrib.auth import get_user_model

from approval_workflow.choices import RoleSelectionStrategy

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
                "approval_type": "self",
            }
        ]

    approvals = stage.stage_info.get("approvals", [])
    if not approvals:
        # Default to self-approval by creator
        return [
            {
                "approval_user": created_by_user,
                "approval_type": "self",
            }
        ]

    return approvals


def build_approval_steps(stage, created_by_user: User) -> List[Dict[str, Any]]:
    """Build approval steps for a workflow stage.

    Args:
        stage: The Stage instance
        created_by_user: The user who created the workflow item

    Returns:
        List of approval step configurations
    """
    approvals = get_workflow_stage_approvers(stage, created_by_user)
    steps = []

    for i, approval_data in enumerate(approvals, start=1):
        step = {
            "step": i,
            "extra_fields": {"stage_id": stage.id},
            "assigned_to": None,
            "role_selection_strategy": "",
        }

        approval_type = approval_data.get("approval_type", "self")

        if approval_type == "self" or approval_data.get("approval_user"):
            # User-specific approval
            approval_user = approval_data.get("approval_user", created_by_user)
            step["assigned_to"] = approval_user

        elif approval_type == "role" and approval_data.get("user_role"):
            # Role-based approval
            try:
                from django.apps import apps

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
                logger.error(f"Error setting up role-based approval: {e}")
                # Fallback to self-approval
                step["assigned_to"] = created_by_user

        # Add form if specified
        if approval_data.get("required_form"):
            try:
                from django.apps import apps

                form_model_path = getattr(
                    settings, "APPROVAL_DYNAMIC_FORM_MODEL", "common.DynamicForm"
                )
                app_label, model_name = form_model_path.split(".")
                FormModel = apps.get_model(app_label, model_name)

                form_id = approval_data["required_form"]
                if isinstance(form_id, dict) and "val" in form_id:
                    form_id = form_id["val"]

                form = FormModel.objects.get(id=form_id)
                step["form"] = form
            except Exception as e:
                logger.error(f"Error setting up form for approval step: {e}")

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
