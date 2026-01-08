"""Example action handler stubs for workflow events.

IMPORTANT: This package does NOT send emails. These are example handlers that you
should copy to your own application and customize with your email implementation.

To use workflow actions:
1. Copy these function signatures to your app (e.g., myapp/workflow_actions.py)
2. Implement your own email sending logic
3. Configure actions to point to your functions:
   - Via WorkflowAction model: function_path='myapp.workflow_actions.send_approval_notification'
   - Via settings: WORKFLOW_ACTIONS_CONFIG with your function paths
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


def send_approval_notification(
    workflow_attachment, action_parameters: Dict, **context
) -> bool:
    """
    Example: Send approval notification email.

    IMPORTANT: This is a stub. Implement your own version in your application.

    Args:
        workflow_attachment: WorkflowAttachment instance
        action_parameters: Action configuration (template, recipients, subject)
        **context: Additional context (user, stage, etc.)

    Returns:
        bool: True if handled successfully

    Example implementation in your app:
        def send_approval_notification(workflow_attachment, action_parameters, **context):
            from django.core.mail import send_mail

            # Your email logic here
            send_mail(
                subject='Workflow Approved',
                message=f'Your workflow has been approved',
                from_email='noreply@example.com',
                recipient_list=[workflow_attachment.target.created_by.email],
            )
            return True
    """
    logger.warning(
        "send_approval_notification called but not implemented. "
        "Please implement your own email handler in your application code."
    )
    return False


def send_rejection_notification(
    workflow_attachment, action_parameters: Dict, **context
) -> bool:
    """
    Example: Send rejection notification email.

    IMPORTANT: This is a stub. Implement your own version in your application.

    Args:
        workflow_attachment: WorkflowAttachment instance
        action_parameters: Action configuration
        **context: Additional context (user, stage, reason, etc.)

    Returns:
        bool: True if handled successfully
    """
    logger.warning(
        "send_rejection_notification called but not implemented. "
        "Please implement your own email handler in your application code."
    )
    return False


def send_resubmission_notification(
    workflow_attachment, action_parameters: Dict, **context
) -> bool:
    """
    Example: Send resubmission notification email.

    IMPORTANT: This is a stub. Implement your own version in your application.

    Args:
        workflow_attachment: WorkflowAttachment instance
        action_parameters: Action configuration
        **context: Additional context (user, stage, resubmission_stage, comments, etc.)

    Returns:
        bool: True if handled successfully
    """
    logger.warning(
        "send_resubmission_notification called but not implemented. "
        "Please implement your own email handler in your application code."
    )
    return False


def send_delegation_notification(
    workflow_attachment, action_parameters: Dict, **context
) -> bool:
    """
    Example: Send delegation notification email.

    IMPORTANT: This is a stub. Implement your own version in your application.

    Args:
        workflow_attachment: WorkflowAttachment instance
        action_parameters: Action configuration
        **context: Additional context (user, delegated_to, delegation_reason, etc.)

    Returns:
        bool: True if handled successfully
    """
    logger.warning(
        "send_delegation_notification called but not implemented. "
        "Please implement your own email handler in your application code."
    )
    return False


def send_stage_move_notification(
    workflow_attachment, action_parameters: Dict, **context
) -> bool:
    """
    Example: Send stage progression notification email.

    IMPORTANT: This is a stub. Implement your own version in your application.

    Args:
        workflow_attachment: WorkflowAttachment instance
        action_parameters: Action configuration
        **context: Additional context (user, stage, previous_stage, etc.)

    Returns:
        bool: True if handled successfully
    """
    logger.warning(
        "send_stage_move_notification called but not implemented. "
        "Please implement your own email handler in your application code."
    )
    return False
