"""Default action functions for workflow events.

These functions are called automatically when no custom actions are configured
for specific workflow events. They provide basic email notifications to
creators and approvers.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def default_send_email_after_approve(**context) -> bool:
    """Send an email notification after approval.

    Args:
        **context: Context including attachment, obj, current_stage, etc.

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        attachment = context.get("attachment")
        obj = context.get("obj")
        current_stage = context.get("current_stage")
        approver = context.get("user")

        if not all([attachment, obj, current_stage]):
            logger.warning("Missing required context for after_approve email")
            return False

        # Get email recipients (creator and approvers)
        recipients = []

        # Add creator email
        if (
            hasattr(obj, "created_by")
            and obj.created_by
            and hasattr(obj.created_by, "email")
        ):
            recipients.append(obj.created_by.email)

        # Add workflow starter email
        if attachment.started_by and hasattr(attachment.started_by, "email"):
            recipients.append(attachment.started_by.email)

        # Remove duplicates
        recipients = list(set(filter(None, recipients)))

        if not recipients:
            logger.warning(f"No email recipients found for {obj._meta.label}({obj.pk})")
            return False

        # Prepare email content
        subject = f"Approval Completed - {current_stage.name_en}"
        message = f"""
        The approval for {obj._meta.verbose_name} has been completed.

        Stage: {current_stage.name_en}
        Approver: {approver.get_full_name() if approver else 'System'}
        Object: {str(obj)}

        The workflow will continue to the next stage.
        """

        # Send email (implementation depends on your email backend)
        return _send_email(recipients, subject, message, context)

    except Exception as e:
        logger.error(f"Error sending after_approve email: {str(e)}")
        return False


def default_send_email_after_reject(**context) -> bool:
    """Send email notification after rejection.

    Args:
        **context: Context including attachment, obj, current_stage, etc.

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        attachment = context.get("attachment")
        obj = context.get("obj")
        current_stage = context.get("current_stage")
        reason = context.get("reason", "No reason provided")
        rejector = context.get("user")

        if not all([attachment, obj, current_stage]):
            logger.warning("Missing required context for after_reject email")
            return False

        # Get email recipients
        recipients = []

        # Add creator email
        if (
            hasattr(obj, "created_by")
            and obj.created_by
            and hasattr(obj.created_by, "email")
        ):
            recipients.append(obj.created_by.email)

        # Add workflow starter email
        if attachment.started_by and hasattr(attachment.started_by, "email"):
            recipients.append(attachment.started_by.email)

        recipients = list(set(filter(None, recipients)))

        if not recipients:
            logger.warning(f"No email recipients found for {obj._meta.label}({obj.pk})")
            return False

        # Prepare email content
        subject = f"Workflow Rejected - {current_stage.name_en}"
        message = f"""
        The workflow for {obj._meta.verbose_name} has been rejected.

        Stage: {current_stage.name_en}
        Rejector: {rejector.get_full_name() if rejector else 'System'}
        Reason: {reason}
        Object: {str(obj)}

        Please review and resubmit if necessary.
        """

        return _send_email(recipients, subject, message, context)

    except Exception as e:
        logger.error(f"Error sending after_reject email: {str(e)}")
        return False


def default_send_email_after_resubmission(**context) -> bool:
    """Send email notification after resubmission request.

    Args:
        **context: Context including attachment, obj, target_stage, etc.

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        attachment = context.get("attachment")
        obj = context.get("obj")
        target_stage = context.get("target_stage")
        reason = context.get("reason", "No reason provided")
        requester = context.get("user")

        if not all([attachment, obj]):
            logger.warning("Missing required context for after_resubmission email")
            return False

        # Get email recipients
        recipients = []

        if (
            hasattr(obj, "created_by")
            and obj.created_by
            and hasattr(obj.created_by, "email")
        ):
            recipients.append(obj.created_by.email)

        if attachment.started_by and hasattr(attachment.started_by, "email"):
            recipients.append(attachment.started_by.email)

        recipients = list(set(filter(None, recipients)))

        if not recipients:
            logger.warning(f"No email recipients found for {obj._meta.label}({obj.pk})")
            return False

        # Prepare email content
        subject = f"Resubmission Requested - {obj._meta.verbose_name}"
        message = f"""
        A resubmission has been requested for {obj._meta.verbose_name}.

        Target Stage: {target_stage.name_en if target_stage else 'Previous stage'}
        Requester: {requester.get_full_name() if requester else 'System'}
        Reason: {reason}
        Object: {str(obj)}

        Please review and make necessary changes before resubmitting.
        """

        return _send_email(recipients, subject, message, context)

    except Exception as e:
        logger.error(f"Error sending after_resubmission email: {str(e)}")
        return False


def default_send_email_after_delegate(**context) -> bool:
    """Send email notification after delegation.

    Args:
        **context: Context including attachment, obj, delegate_to, etc.

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        attachment = context.get("attachment")
        obj = context.get("obj")
        current_stage = context.get("current_stage")
        delegate_to = context.get("delegate_to")
        delegator = context.get("user")
        reason = context.get("reason", "No reason provided")

        if not all([attachment, obj, current_stage, delegate_to]):
            logger.warning("Missing required context for after_delegate email")
            return False

        # Send email to delegate
        if hasattr(delegate_to, "email") and delegate_to.email:
            subject = f"Approval Delegated - {current_stage.name_en}"
            message = f"""
            An approval has been delegated to you.

            Stage: {current_stage.name_en}
            Delegator: {delegator.get_full_name() if delegator else 'System'}
            Reason: {reason}
            Object: {str(obj)}

            Please review and approve or reject as appropriate.
            """

            return _send_email([delegate_to.email], subject, message, context)

        return False

    except Exception as e:
        logger.error(f"Error sending after_delegate email: {str(e)}")
        return False


def default_send_email_after_move_stage(**context) -> bool:
    """Send email notification after moving to a new stage.

    Args:
        **context: Context including attachment, obj, from_stage, to_stage, etc.

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        attachment = context.get("attachment")
        obj = context.get("obj")
        from_stage = context.get("from_stage")
        to_stage = context.get("to_stage")

        if not all([attachment, obj, to_stage]):
            logger.warning("Missing required context for after_move_stage email")
            return False

        # Get email recipients
        recipients = []

        if (
            hasattr(obj, "created_by")
            and obj.created_by
            and hasattr(obj.created_by, "email")
        ):
            recipients.append(obj.created_by.email)

        if attachment.started_by and hasattr(attachment.started_by, "email"):
            recipients.append(attachment.started_by.email)

        recipients = list(set(filter(None, recipients)))

        if not recipients:
            logger.warning(f"No email recipients found for {obj._meta.label}({obj.pk})")
            return False

        # Prepare email content
        subject = f"Workflow Progress - Moved to {to_stage.name_en}"
        message = f"""
        The workflow has progressed to a new stage.

        From: {from_stage.name_en if from_stage else 'Start'}
        To: {to_stage.name_en}
        Object: {str(obj)}

        The workflow is now awaiting approval at the new stage.
        """

        return _send_email(recipients, subject, message, context)

    except Exception as e:
        logger.error(f"Error sending after_move_stage email: {str(e)}")
        return False


def default_send_email_after_move_pipeline(**context) -> bool:
    """Send email notification after moving to a new pipeline.

    Args:
        **context: Context including attachment, obj, from_pipeline, to_pipeline, etc.

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        attachment = context.get("attachment")
        obj = context.get("obj")
        from_pipeline = context.get("from_pipeline")
        to_pipeline = context.get("to_pipeline")

        if not all([attachment, obj, to_pipeline]):
            logger.warning("Missing required context for after_move_pipeline email")
            return False

        # Get email recipients
        recipients = []

        if (
            hasattr(obj, "created_by")
            and obj.created_by
            and hasattr(obj.created_by, "email")
        ):
            recipients.append(obj.created_by.email)

        if attachment.started_by and hasattr(attachment.started_by, "email"):
            recipients.append(attachment.started_by.email)

        recipients = list(set(filter(None, recipients)))

        if not recipients:
            logger.warning(f"No email recipients found for {obj._meta.label}({obj.pk})")
            return False

        # Prepare email content
        subject = f"Workflow Progress - Moved to {to_pipeline.name_en} Pipeline"
        message = f"""
        The workflow has moved to a new pipeline.

        From: {from_pipeline.name_en if from_pipeline else 'Previous pipeline'}
        To: {to_pipeline.name_en}
        Object: {str(obj)}

        The workflow will continue in the new pipeline.
        """

        return _send_email(recipients, subject, message, context)

    except Exception as e:
        logger.error(f"Error sending after_move_pipeline email: {str(e)}")
        return False


def default_send_email_on_workflow_start(**context) -> bool:
    """Send email notification when workflow starts.

    Args:
        **context: Context including attachment, obj, workflow, initial_stage, etc.

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        attachment = context.get("attachment")
        obj = context.get("obj")
        workflow = context.get("workflow")
        initial_stage = context.get("initial_stage")

        if not all([attachment, obj, workflow]):
            logger.warning("Missing required context for on_workflow_start email")
            return False

        # Get email recipients
        recipients = []

        if (
            hasattr(obj, "created_by")
            and obj.created_by
            and hasattr(obj.created_by, "email")
        ):
            recipients.append(obj.created_by.email)

        if attachment.started_by and hasattr(attachment.started_by, "email"):
            recipients.append(attachment.started_by.email)

        recipients = list(set(filter(None, recipients)))

        if not recipients:
            logger.warning(f"No email recipients found for {obj._meta.label}({obj.pk})")
            return False

        # Prepare email content
        subject = f"Workflow Started - {workflow.name_en}"
        message = f"""
        A workflow has been started for {obj._meta.verbose_name}.

        Workflow: {workflow.name_en}
        Initial Stage: {initial_stage.name_en if initial_stage else 'N/A'}
        Object: {str(obj)}

        The approval process has begun.
        """

        return _send_email(recipients, subject, message, context)

    except Exception as e:
        logger.error(f"Error sending on_workflow_start email: {str(e)}")
        return False


def default_send_email_on_workflow_complete(**context) -> bool:
    """Send email notification when workflow completes.

    Args:
        **context: Context including attachment, obj, workflow, etc.

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        attachment = context.get("attachment")
        obj = context.get("obj")
        workflow = context.get("workflow")

        if not all([attachment, obj, workflow]):
            logger.warning("Missing required context for on_workflow_complete email")
            return False

        # Get email recipients
        recipients = []

        if (
            hasattr(obj, "created_by")
            and obj.created_by
            and hasattr(obj.created_by, "email")
        ):
            recipients.append(obj.created_by.email)

        if attachment.started_by and hasattr(attachment.started_by, "email"):
            recipients.append(attachment.started_by.email)

        recipients = list(set(filter(None, recipients)))

        if not recipients:
            logger.warning(f"No email recipients found for {obj._meta.label}({obj.pk})")
            return False

        # Prepare email content
        subject = f"Workflow Completed - {workflow.name_en}"
        message = f"""
        The workflow has been completed successfully.

        Workflow: {workflow.name_en}
        Object: {str(obj)}
        Completed at: {attachment.completed_at}

        All approvals have been obtained and the process is complete.
        """

        return _send_email(recipients, subject, message, context)

    except Exception as e:
        logger.error(f"Error sending on_workflow_complete email: {str(e)}")
        return False


def _send_email(
    recipients: list, subject: str, message: str, context: Dict[str, Any]
) -> bool:
    """Send email using Django's email backend.

    Args:
        recipients: List of email addresses
        subject: Email subject
        message: Email message body
        context: Additional context (not used in basic implementation)

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        from django.conf import settings
        from django.core.mail import send_mail

        # Get sender email from settings
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")

        # Send email
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipients,
            fail_silently=False,
        )

        logger.info(f"Email sent successfully to {recipients}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {recipients}: {str(e)}")
        return False
