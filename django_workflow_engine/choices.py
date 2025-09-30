"""
Choice enums for workflow engine and approval workflow statuses and actions.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

# Import approval-related choices from the approval_workflow package
from approval_workflow.choices import ApprovalStatus, RoleSelectionStrategy


class WorkflowStatus(models.TextChoices):
    """Status choices for workflows."""

    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    DRAFT = "draft", "Draft"


class ApprovalTypes(models.TextChoices):
    """Types of approval configurations."""

    SELF = "self-approved", _("Self Approved")
    ROLE = "role", _("Role")
    USER = "user", _("User")
    TEAM_HEAD = "team_head", _("Team Head")
    DEPARTMENT_HEAD = "department_head", _("Department Head")


class WorkflowAttachmentStatus(models.TextChoices):
    """Status choices for workflow attachments."""

    NOT_STARTED = "not_started", "Not Started"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class ActionType(models.TextChoices):
    """Types of actions that can be triggered in workflows."""

    AFTER_APPROVE = "after_approve", "After Approval"
    AFTER_REJECT = "after_reject", "After Rejection"
    AFTER_RESUBMISSION = "after_resubmission", "After Resubmission"
    AFTER_DELEGATE = "after_delegate", "After Delegation"
    AFTER_MOVE_STAGE = "after_move_stage", "After Move Stage"
    AFTER_MOVE_PIPELINE = "after_move_pipeline", "After Move Pipeline"
    ON_WORKFLOW_START = "on_workflow_start", "On Workflow Start"
    ON_WORKFLOW_COMPLETE = "on_workflow_complete", "On Workflow Complete"


# Default action functions mapping
DEFAULT_ACTIONS = {
    ActionType.AFTER_APPROVE: "default_send_email_after_approve",
    ActionType.AFTER_REJECT: "default_send_email_after_reject",
    ActionType.AFTER_RESUBMISSION: "default_send_email_after_resubmission",
    ActionType.AFTER_DELEGATE: "default_send_email_after_delegate",
    ActionType.AFTER_MOVE_STAGE: "default_send_email_after_move_stage",
    ActionType.AFTER_MOVE_PIPELINE: "default_send_email_after_move_pipeline",
    ActionType.ON_WORKFLOW_START: "default_send_email_on_workflow_start",
    ActionType.ON_WORKFLOW_COMPLETE: "default_send_email_on_workflow_complete",
}
