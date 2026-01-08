"""Deprecated: Default action functions (no longer used).

IMPORTANT: As of v1.5.5, this package does NOT send emails automatically.
These functions are kept for backward compatibility but do nothing except log warnings.

To implement email notifications:
1. Create your own action handlers in your application
2. Configure them via WorkflowAction model or WORKFLOW_ACTIONS_CONFIG setting
3. Use your own email sending logic (Django mail, SendGrid, etc.)

Example implementation in your app:
    # myapp/workflow_actions.py
    from django.core.mail import send_mail

    def send_approval_email(**context):
        attachment = context.get('attachment')
        obj = attachment.target

        send_mail(
            subject='Workflow Approved',
            message=f'Your {obj} has been approved',
            from_email='noreply@example.com',
            recipient_list=[obj.created_by.email],
        )
        return True
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def default_send_email_after_approve(**context) -> bool:
    """Deprecated: No longer sends emails.

    IMPORTANT: Implement your own version in your application.
    """
    logger.warning(
        "default_send_email_after_approve called but does nothing. "
        "Please implement your own email handler in your application code."
    )
    return False


def default_send_email_after_reject(**context) -> bool:
    """Deprecated: No longer sends emails.

    IMPORTANT: Implement your own version in your application.
    """
    logger.warning(
        "default_send_email_after_reject called but does nothing. "
        "Please implement your own email handler in your application code."
    )
    return False


def default_send_email_after_resubmission(**context) -> bool:
    """Deprecated: No longer sends emails.

    IMPORTANT: Implement your own version in your application.
    """
    logger.warning(
        "default_send_email_after_resubmission called but does nothing. "
        "Please implement your own email handler in your application code."
    )
    return False


def default_send_email_after_delegate(**context) -> bool:
    """Deprecated: No longer sends emails.

    IMPORTANT: Implement your own version in your application.
    """
    logger.warning(
        "default_send_email_after_delegate called but does nothing. "
        "Please implement your own email handler in your application code."
    )
    return False


def default_send_email_after_move_stage(**context) -> bool:
    """Deprecated: No longer sends emails.

    IMPORTANT: Implement your own version in your application.
    """
    logger.warning(
        "default_send_email_after_move_stage called but does nothing. "
        "Please implement your own email handler in your application code."
    )
    return False


def default_send_email_after_move_pipeline(**context) -> bool:
    """Deprecated: No longer sends emails.

    IMPORTANT: Implement your own version in your application.
    """
    logger.warning(
        "default_send_email_after_move_pipeline called but does nothing. "
        "Please implement your own email handler in your application code."
    )
    return False


def default_send_email_on_workflow_start(**context) -> bool:
    """Deprecated: No longer sends emails.

    IMPORTANT: Implement your own version in your application.
    """
    logger.warning(
        "default_send_email_on_workflow_start called but does nothing. "
        "Please implement your own email handler in your application code."
    )
    return False


def default_send_email_on_workflow_complete(**context) -> bool:
    """Deprecated: No longer sends emails.

    IMPORTANT: Implement your own version in your application.
    """
    logger.warning(
        "default_send_email_on_workflow_complete called but does nothing. "
        "Please implement your own email handler in your application code."
    )
    return False
