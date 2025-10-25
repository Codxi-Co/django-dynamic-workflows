"""Default action handlers for workflow events."""

import logging
from typing import Dict, List, Optional

from .notifications import get_workflow_email_context, send_bulk_workflow_emails
from .recipient_resolver import resolve_recipients

logger = logging.getLogger(__name__)


def send_approval_notification(
    workflow_attachment, action_parameters: Dict, **context
) -> bool:
    """
    Send approval notification email.

    Called when a workflow approval is granted.

    Args:
        workflow_attachment: WorkflowAttachment instance
        action_parameters: Action configuration (template, recipients, subject)
        **context: Additional context (user, stage, etc.)

    Returns:
        bool: True if emails sent successfully

    Example action_parameters:
        {
            'template': 'workflow_approved',
            'recipients': ['creator', 'workflow_starter'],
            'subject': 'Workflow Approved'
        }
    """
    template = action_parameters.get("template", "workflow_approved")
    recipients = action_parameters.get("recipients", ["creator"])
    subject = action_parameters.get("subject", "Workflow Approved")

    # Resolve recipients to email addresses
    email_addresses = resolve_recipients(
        recipient_types=recipients, workflow_attachment=workflow_attachment, **context
    )

    if not email_addresses:
        logger.warning("No recipients to send approval notification")
        return False

    # Build email context
    # Extract stage and user to avoid duplication when unpacking **context
    stage = context.get("stage")
    user = context.get("user")

    # Create context copy without stage and user to avoid duplicate kwargs
    context_without_duplicates = {
        k: v for k, v in context.items() if k not in ["stage", "user"]
    }

    email_context = get_workflow_email_context(
        workflow_attachment=workflow_attachment,
        stage=stage,
        user=user,
        subject=subject,
        action_type="approval",
        **context_without_duplicates,
    )

    # Send emails
    result = send_bulk_workflow_emails(
        name=template,
        recipients=list(email_addresses),
        context=email_context,
        deduplicate=False,  # Already deduplicated
    )

    logger.info(
        f"Approval notification sent - Sent: {result['sent']}, Failed: {result['failed']}"
    )

    return result["sent"] > 0


def send_rejection_notification(
    workflow_attachment, action_parameters: Dict, **context
) -> bool:
    """
    Send rejection notification email.

    Called when a workflow approval is rejected.

    Args:
        workflow_attachment: WorkflowAttachment instance
        action_parameters: Action configuration (template, recipients, subject)
        **context: Additional context (user, stage, reason, etc.)

    Returns:
        bool: True if emails sent successfully

    Example action_parameters:
        {
            'template': 'workflow_rejected',
            'recipients': ['creator'],
            'subject': 'Workflow Rejected'
        }
    """
    template = action_parameters.get("template", "workflow_rejected")
    recipients = action_parameters.get("recipients", ["creator"])
    subject = action_parameters.get("subject", "Workflow Rejected")

    # Resolve recipients to email addresses
    email_addresses = resolve_recipients(
        recipient_types=recipients, workflow_attachment=workflow_attachment, **context
    )

    if not email_addresses:
        logger.warning("No recipients to send rejection notification")
        return False

    # Build email context
    # Extract stage and user to avoid duplication when unpacking **context
    stage = context.get("stage")
    user = context.get("user")

    # Create context copy without stage and user to avoid duplicate kwargs
    context_without_duplicates = {
        k: v for k, v in context.items() if k not in ["stage", "user"]
    }

    email_context = get_workflow_email_context(
        workflow_attachment=workflow_attachment,
        stage=stage,
        user=user,
        subject=subject,
        action_type="rejection",
        rejection_reason=context.get("reason", "No reason provided"),
        **context_without_duplicates,
    )

    # Send emails
    result = send_bulk_workflow_emails(
        name=template,
        recipients=list(email_addresses),
        context=email_context,
        deduplicate=False,  # Already deduplicated
    )

    logger.info(
        f"Rejection notification sent - Sent: {result['sent']}, Failed: {result['failed']}"
    )

    return result["sent"] > 0


def send_resubmission_notification(
    workflow_attachment, action_parameters: Dict, **context
) -> bool:
    """
    Send resubmission notification email.

    Called when a workflow requires resubmission.

    Args:
        workflow_attachment: WorkflowAttachment instance
        action_parameters: Action configuration (template, recipients, subject)
        **context: Additional context (user, stage, resubmission_stage, comments, etc.)

    Returns:
        bool: True if emails sent successfully

    Example action_parameters:
        {
            'template': 'workflow_resubmission_required',
            'recipients': ['creator', 'current_approver'],
            'subject': 'Resubmission Required'
        }
    """
    template = action_parameters.get("template", "workflow_resubmission_required")
    recipients = action_parameters.get("recipients", ["creator", "current_approver"])
    subject = action_parameters.get("subject", "Resubmission Required")

    # Resolve recipients to email addresses
    email_addresses = resolve_recipients(
        recipient_types=recipients, workflow_attachment=workflow_attachment, **context
    )

    if not email_addresses:
        logger.warning("No recipients to send resubmission notification")
        return False

    # Build email context
    # Extract stage and user to avoid duplication when unpacking **context
    stage = context.get("stage")
    user = context.get("user")
    resubmission_stage = context.get("resubmission_stage")

    # Create context copy without stage and user to avoid duplicate kwargs
    context_without_duplicates = {
        k: v for k, v in context.items() if k not in ["stage", "user"]
    }

    email_context = get_workflow_email_context(
        workflow_attachment=workflow_attachment,
        stage=stage,
        user=user,
        subject=subject,
        action_type="resubmission",
        resubmission_stage=resubmission_stage.name_en if resubmission_stage else "N/A",
        resubmission_comments=context.get("comments", ""),
        **context_without_duplicates,
    )

    # Send emails
    result = send_bulk_workflow_emails(
        name=template,
        recipients=list(email_addresses),
        context=email_context,
        deduplicate=False,  # Already deduplicated
    )

    logger.info(
        f"Resubmission notification sent - Sent: {result['sent']}, Failed: {result['failed']}"
    )

    return result["sent"] > 0


def send_delegation_notification(
    workflow_attachment, action_parameters: Dict, **context
) -> bool:
    """
    Send delegation notification email.

    Called when a workflow approval is delegated to another user.

    Args:
        workflow_attachment: WorkflowAttachment instance
        action_parameters: Action configuration (template, recipients, subject)
        **context: Additional context (user, delegated_to, delegation_reason, etc.)

    Returns:
        bool: True if emails sent successfully

    Example action_parameters:
        {
            'template': 'workflow_delegated',
            'recipients': ['delegated_to', 'creator'],
            'subject': 'Workflow Delegated'
        }
    """
    template = action_parameters.get("template", "workflow_delegated")
    recipients = action_parameters.get("recipients", ["delegated_to", "creator"])
    subject = action_parameters.get("subject", "Workflow Delegated")

    # Resolve recipients to email addresses
    email_addresses = resolve_recipients(
        recipient_types=recipients, workflow_attachment=workflow_attachment, **context
    )

    if not email_addresses:
        logger.warning("No recipients to send delegation notification")
        return False

    # Build email context
    # Extract stage and user to avoid duplication when unpacking **context
    stage = context.get("stage")
    user = context.get("user")
    delegated_to = context.get("delegated_to")
    delegated_by = user

    # Create context copy without stage and user to avoid duplicate kwargs
    context_without_duplicates = {
        k: v for k, v in context.items() if k not in ["stage", "user"]
    }

    email_context = get_workflow_email_context(
        workflow_attachment=workflow_attachment,
        stage=stage,
        user=user,
        subject=subject,
        action_type="delegation",
        delegated_by=(
            getattr(delegated_by, "get_full_name", lambda: delegated_by.username)()
            if delegated_by and hasattr(delegated_by, "get_full_name")
            else "Unknown"
        ),
        delegation_reason=context.get("delegation_reason", ""),
        **context_without_duplicates,
    )

    # Send emails
    result = send_bulk_workflow_emails(
        name=template,
        recipients=list(email_addresses),
        context=email_context,
        deduplicate=False,  # Already deduplicated
    )

    logger.info(
        f"Delegation notification sent - Sent: {result['sent']}, Failed: {result['failed']}"
    )

    return result["sent"] > 0


def send_stage_move_notification(
    workflow_attachment, action_parameters: Dict, **context
) -> bool:
    """
    Send stage progression notification email.

    Called when a workflow moves to a new stage.

    Args:
        workflow_attachment: WorkflowAttachment instance
        action_parameters: Action configuration (template, recipients, subject)
        **context: Additional context (user, stage, previous_stage, etc.)

    Returns:
        bool: True if emails sent successfully

    Example action_parameters:
        {
            'template': 'workflow_action_required',
            'recipients': ['creator', 'current_approver'],
            'subject': 'Workflow Progressed to Next Stage'
        }
    """
    template = action_parameters.get("template", "workflow_action_required")
    recipients = action_parameters.get("recipients", ["creator", "current_approver"])
    subject = action_parameters.get("subject", "Workflow Progressed to Next Stage")

    # Resolve recipients to email addresses
    email_addresses = resolve_recipients(
        recipient_types=recipients, workflow_attachment=workflow_attachment, **context
    )

    if not email_addresses:
        logger.warning("No recipients to send stage move notification")
        return False

    # Build email context
    # Extract stage and user to avoid duplication when unpacking **context
    current_stage = context.get("stage") or workflow_attachment.current_stage
    user = context.get("user")
    previous_stage = context.get("previous_stage")

    # Create context copy without stage and user to avoid duplicate kwargs
    context_without_duplicates = {
        k: v for k, v in context.items() if k not in ["stage", "user"]
    }

    email_context = get_workflow_email_context(
        workflow_attachment=workflow_attachment,
        stage=current_stage,
        user=user,
        subject=subject,
        action_type="stage_move",
        previous_stage_name=previous_stage.name_en if previous_stage else "N/A",
        action_description=f"Workflow moved to stage: {current_stage.name_en if current_stage else 'N/A'}",
        **context_without_duplicates,
    )

    # Send emails
    result = send_bulk_workflow_emails(
        name=template,
        recipients=list(email_addresses),
        context=email_context,
        deduplicate=False,  # Already deduplicated
    )

    logger.info(
        f"Stage move notification sent - Sent: {result['sent']}, Failed: {result['failed']}"
    )

    return result["sent"] > 0
