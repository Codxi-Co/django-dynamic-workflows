"""
Choice enums for workflow engine and approval workflow statuses and actions.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class WorkflowStatus(models.TextChoices):
    """Status choices for workflows."""

    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    DRAFT = "draft", "Draft"


class WorkflowStrategy(models.IntegerChoices):
    """Workflow hierarchy strategies for approval management.

    Strategy 1: Full hierarchy (workflow → pipeline → stage) with approvals at stage level
    Strategy 2: Two-level (workflow → pipeline) with approvals at pipeline level, NO stages allowed
    Strategy 3: Single-level (workflow only) with approvals at workflow level, NO pipelines or stages allowed
    """

    WORKFLOW_PIPELINE_STAGE = 1, _(
        "Workflow → Pipeline → Stage - Approvals at stage level"
    )
    WORKFLOW_PIPELINE = 2, _(
        "Workflow → Pipeline - Approvals at pipeline level (no stages)"
    )
    WORKFLOW_ONLY = 3, _(
        "Workflow Only - Approvals at workflow level (no pipelines/stages)"
    )
    STATUS_GRAPH = 4, _("Status Graph - Transitions between workflow statuses")


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
    BEFORE_TRANSITION = "before_transition", "Before Status Transition"
    AFTER_TRANSITION = "after_transition", "After Status Transition"
    ON_TRANSITION_APPROVAL_REQUESTED = (
        "on_transition_approval_requested",
        "On Transition Approval Requested",
    )
    ON_TRANSITION_APPROVED = "on_transition_approved", "On Transition Approved"
    ON_TRANSITION_REJECTED = "on_transition_rejected", "On Transition Rejected"
    ON_STATUS_ENTER = "on_status_enter", "On Status Enter"


class ActionFailurePolicy(models.TextChoices):
    """How workflow execution proceeds when a custom action raises an error."""

    CONTINUE = "continue", _("Continue")
    STOP = "stop", _("Stop Remaining Actions")
    RAISE = "raise", _("Raise Error")


class StatusCategory(models.TextChoices):
    """Business category for reusable statuses."""

    OPEN = "open", _("Open")
    ACTIVE = "active", _("Active")
    PAUSED = "paused", _("Paused")
    DONE = "done", _("Done")
    CANCELLED = "cancelled", _("Cancelled")
    OTHER = "other", _("Other")


class TransitionRejectBehavior(models.TextChoices):
    """What happens when a transition approval is rejected."""

    STAY_CURRENT = "stay_current_status", _("Stay in Current Status")
    MOVE_TO_STATUS = "move_to_specific_status", _("Move to Specific Status")
    REQUEST_CHANGES = "request_changes", _("Request Changes")
    CANCEL_WORKFLOW = "cancel_workflow", _("Cancel Workflow")


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
