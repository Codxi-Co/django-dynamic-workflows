"""Constants and configuration for django_workflow_engine.

This module contains reusable constants to avoid magic strings and values
throughout the codebase.
"""

from django.utils.translation import gettext_lazy as _

from approval_workflow.choices import RoleSelectionStrategy

from .choices import ApprovalTypes

# Default values
DEFAULT_STAGE_COLOR = "#3498db"
DEFAULT_STAGE_NAME_EN = "Stage"
DEFAULT_STAGE_NAME_AR = "المرحلة"
DEFAULT_PIPELINE_NAME_EN = "Pipeline"
DEFAULT_PIPELINE_NAME_AR = "خط الأنابيب"

# Approval type display names for UI/serialization
APPROVAL_TYPE_DISPLAY = {
    ApprovalTypes.ROLE: _("Role-based Approval"),
    ApprovalTypes.USER: _("User-specific Approval"),
    ApprovalTypes.SELF: _("Self Approval"),
    ApprovalTypes.TEAM_HEAD: _("Team Head Approval"),
    ApprovalTypes.DEPARTMENT_HEAD: _("Department Head Approval"),
}

# Role selection strategy display names for UI/serialization
ROLE_STRATEGY_DISPLAY = {
    RoleSelectionStrategy.ANYONE: _("Any user with role can approve"),
    RoleSelectionStrategy.CONSENSUS: _("All users with role must approve"),
    RoleSelectionStrategy.ROUND_ROBIN: _("Rotate approval among role users"),
}

# Error messages
ERROR_MESSAGES = {
    "no_workflow_attached": _(
        "No workflow attached to {obj_label}({obj_pk}). "
        "Use attach_workflow_to_object() to attach a workflow first."
    ),
    "workflow_not_in_progress": _(
        "Workflow is not in progress (status: {status}). "
        "Current status must be 'in_progress' to perform this action."
    ),
    "no_pipelines": _(
        "Workflow '{workflow_name}' has no pipelines. "
        "Add at least one pipeline with stages to use this workflow."
    ),
    "no_stages": _(
        "Pipeline '{pipeline_name}' has no stages. "
        "Add at least one stage with approvals to use this pipeline."
    ),
    "no_next_stage": _(
        "No next stage found, completing workflow for {obj_label}({obj_pk})"
    ),
    "no_current_pipeline": _(
        "No current pipeline found for attachment {attachment_id}, cannot determine next stage"
    ),
    "no_user_for_approval": _(
        "No user found for building approval steps for {obj_label}({obj_pk}), "
        "this may cause issues with approval flow"
    ),
    "workflow_already_started": _(
        "Workflow already started (status: {status}). "
        "Cannot start a workflow that is already in progress."
    ),
    "workflow_inactive": _(
        "Workflow '{workflow_name}' is not active and cannot be attached. "
        "Please activate the workflow before attaching it to objects."
    ),
}

# Logging messages
LOG_MESSAGES = {
    "workflow_created": _(
        "Workflow created - ID: {workflow_id}, Name: {name}, Pipelines: {pipeline_count}"
    ),
    "pipeline_created": _(
        "Pipeline created - ID: {pipeline_id}, Workflow: {workflow_name}, Stages: {stage_count}"
    ),
    "workflow_started": _(
        "Workflow started for {obj_label}({obj_pk}) at stage '{stage_name}'"
    ),
    "workflow_completed": _("Workflow completed for {obj_label}({obj_pk})"),
    "stage_moved": _(
        "Moved {obj_label}({obj_pk}) from stage '{from_stage}' to '{to_stage}'"
    ),
    "pipeline_changed": _("Pipeline changed from '{from_pipeline}' to '{to_pipeline}'"),
    "approval_flow_started": _(
        "Starting approval flow for stage '{stage_name}' with {step_count} steps"
    ),
    "no_approval_steps": _(
        "No approval steps generated for stage '{stage_name}', workflow may be stuck"
    ),
}

# Query optimization settings
BATCH_FETCH_SIZE = 100  # Maximum number of items to fetch in batch queries

# Cache settings
WORKFLOW_CACHE_TIMEOUT = 300  # 5 minutes in seconds
STAGE_CACHE_TIMEOUT = 300  # 5 minutes in seconds
