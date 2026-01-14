"""
Example workflow actions module.

This module demonstrates best practices for creating workflow actions
using the secure action registry.

Copy this module to your app and customize it for your needs.
"""

import logging
from typing import Any, Dict

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone, translation

from django_workflow_engine.action_registry import register_action

logger = logging.getLogger(__name__)
User = get_user_model()


# ============================================================================
# Email Actions
# ============================================================================


@register_action(
    name="send_approval_email",
    category="email",
    description="Send email notification when workflow is approved",
)
def send_approval_email(
    workflow_attachment, action_parameters: Dict[str, Any], **context
) -> bool:
    """
    Send approval email notification to relevant parties.

    Action Parameters:
        - recipients (list): List of email addresses or recipient keys:
                             - "creator": Object creator
                             - "manager": Manager email from settings
                             - "admin": Admin emails from settings
        - subject (str, optional): Email subject (default: "Workflow Approved")
        - template (str, optional): Email template path
        - include_details (bool): Include workflow details (default: True)

    Context:
        - user: User who approved the workflow
        - stage: Current stage (if applicable)

    Returns:
        bool: True if email sent successfully

    Example:
        {
            "recipients": ["creator", "manager@example.com"],
            "subject": "Purchase Order Approved",
            "template": "emails/po_approved.html"
        }
    """
    try:
        # Get recipients
        recipients = action_parameters.get("recipients", [])
        if not recipients:
            logger.warning("No recipients specified for send_approval_email")
            return False

        # Resolve recipient keys to actual email addresses
        email_list = _resolve_recipients(recipients, workflow_attachment)
        if not email_list:
            logger.error("No valid email addresses resolved")
            return False

        # Prepare email content
        subject = action_parameters.get("subject") or _get_default_subject(
            "approval", workflow_attachment
        )
        message = _prepare_email_message(
            workflow_attachment, action_parameters, context
        )

        # Send email
        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"),
            recipient_list=email_list,
            fail_silently=False,
        )

        logger.info(
            f"Approval email sent to {len(email_list)} recipients "
            f"for workflow {workflow_attachment.workflow.id}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to send approval email: {e}", exc_info=True)
        return False


@register_action(
    name="send_rejection_email",
    category="email",
    description="Send email notification when workflow is rejected",
)
def send_rejection_email(
    workflow_attachment, action_parameters: Dict[str, Any], **context
) -> bool:
    """
    Send rejection email notification.

    Action Parameters:
        - recipients (list): List of email addresses
        - include_reason (bool): Include rejection reason (default: True)

    Returns:
        bool: True if successful
    """
    try:
        recipients = action_parameters.get("recipients", [])
        if not recipients:
            logger.warning("No recipients specified for send_rejection_email")
            return False

        email_list = _resolve_recipients(recipients, workflow_attachment)
        reason = context.get("reason", "No reason provided")

        subject = action_parameters.get("subject") or _get_default_subject(
            "rejection", workflow_attachment
        )

        message = render_to_string(
            "emails/workflow_rejection.txt",
            {
                "workflow": workflow_attachment.workflow,
                "object": workflow_attachment.target,
                "reason": reason,
                "user": context.get("user"),
            },
        )

        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"),
            recipient_list=email_list,
            fail_silently=False,
        )

        logger.info(
            f"Rejection email sent for workflow {workflow_attachment.workflow.id}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to send rejection email: {e}", exc_info=True)
        return False


# ============================================================================
# Notification Actions
# ============================================================================


@register_action(
    name="send_notification",
    category="notification",
    description="Send in-app notification to users",
)
def send_notification(
    workflow_attachment, action_parameters: Dict[str, Any], **context
) -> bool:
    """
    Send in-app notification to specified users.

    Action Parameters:
        - recipients (list): List of user IDs or keys:
                             - "creator": Object creator
                             - "approvers": Current approval users
        - message (str): Notification message
        - notification_type (str): Type of notification (default: "info")

    Returns:
        bool: True if successful
    """
    try:
        # This is a placeholder - implement based on your notification system
        recipients = action_parameters.get("recipients", ["creator"])
        message = action_parameters.get("message", "Workflow action completed")
        notification_type = action_parameters.get("notification_type", "info")

        # Resolve recipients to User objects
        users = _resolve_user_recipients(recipients, workflow_attachment)

        # Send notifications (implement your notification logic here)
        for user in users:
            logger.info(
                f"Notification sent to user {user.id}: {message} "
                f"(type: {notification_type})"
            )

        return True

    except Exception as e:
        logger.error(f"Failed to send notification: {e}", exc_info=True)
        return False


# ============================================================================
# Status Update Actions
# ============================================================================


@register_action(
    name="update_object_status",
    category="status_update",
    description="Update target object's status field",
)
def update_object_status(
    workflow_attachment, action_parameters: Dict[str, Any], **context
) -> bool:
    """
    Update the status field of the target object.

    Action Parameters:
        - status (str): New status value (required)
        - status_field (str): Name of status field (default: "status")
        - save (bool): Save the object (default: True)

    Returns:
        bool: True if successful
    """
    try:
        obj = workflow_attachment.target
        if not obj:
            logger.error("No target object found for status update")
            return False

        status = action_parameters.get("status")
        if not status:
            logger.error("Status parameter is required")
            return False

        status_field = action_parameters.get("status_field", "status")

        if not hasattr(obj, status_field):
            logger.error(
                f"Object {obj._meta.label}({obj.pk}) does not have field '{status_field}'"
            )
            return False

        # Update status
        setattr(obj, status_field, status)

        # Add audit fields if available
        if hasattr(obj, "updated_at"):
            obj.updated_at = timezone.now()

        if action_parameters.get("save", True):
            obj.save()
            logger.info(
                f"Updated {obj._meta.label}({obj.pk}).{status_field} to '{status}'"
            )

        return True

    except Exception as e:
        logger.error(f"Failed to update object status: {e}", exc_info=True)
        return False


@register_action(
    name="mark_object_approved",
    category="status_update",
    description="Mark object as approved with timestamp",
)
def mark_object_approved(
    workflow_attachment, action_parameters: Dict[str, Any], **context
) -> bool:
    """
    Mark object as approved with user and timestamp.

    Action Parameters:
        - approved_by_field (str): Field for approver (default: "approved_by")
        - approved_at_field (str): Field for timestamp (default: "approved_at")

    Returns:
        bool: True if successful
    """
    try:
        obj = workflow_attachment.target
        if not obj:
            logger.error("No target object found")
            return False

        approved_by_field = action_parameters.get("approved_by_field", "approved_by")
        approved_at_field = action_parameters.get("approved_at_field", "approved_at")

        # Set approver
        if hasattr(obj, approved_by_field):
            setattr(obj, approved_by_field, context.get("user"))

        # Set timestamp
        if hasattr(obj, approved_at_field):
            setattr(obj, approved_at_field, timezone.now())

        # Save if fields exist
        if hasattr(obj, approved_by_field) or hasattr(obj, approved_at_field):
            obj.save()
            logger.info(
                f"Marked {obj._meta.label}({obj.pk}) as approved "
                f"by {context.get('user')}"
            )

        return True

    except Exception as e:
        logger.error(f"Failed to mark object as approved: {e}", exc_info=True)
        return False


# ============================================================================
# Logging Actions
# ============================================================================


@register_action(
    name="log_workflow_event",
    category="logging",
    description="Log workflow event with details",
)
def log_workflow_event(
    workflow_attachment, action_parameters: Dict[str, Any], **context
) -> bool:
    """
    Log a workflow event with detailed information.

    Action Parameters:
        - event_type (str): Type of event (e.g., "approved", "rejected")
        - message (str, optional): Custom log message
        - log_level (str): Log level (default: "info")

    Returns:
        bool: True if successful
    """
    try:
        event_type = action_parameters.get("event_type", "workflow_event")
        message = action_parameters.get(
            "message",
            f"Workflow {event_type} for {workflow_attachment.workflow.name_en}",
        )
        log_level = action_parameters.get("log_level", "info").lower()

        log_func = getattr(logger, log_level, logger.info)

        log_func(
            f"{message} - "
            f"Workflow: {workflow_attachment.workflow.id}, "
            f"Object: {workflow_attachment.target}, "
            f"User: {context.get('user')}, "
            f"Status: {workflow_attachment.status}"
        )

        return True

    except Exception as e:
        logger.error(f"Failed to log workflow event: {e}", exc_info=True)
        return False


# ============================================================================
# Custom Business Logic Actions
# ============================================================================


@register_action(
    name="update_inventory",
    category="business_logic",
    description="Update inventory based on workflow object",
)
def update_inventory(
    workflow_attachment, action_parameters: Dict[str, Any], **context
) -> bool:
    """
    Example: Update inventory when purchase order is approved.

    This is a placeholder - implement your business logic here.

    Action Parameters:
        - verify_stock (bool): Verify stock before update (default: True)

    Returns:
        bool: True if successful
    """
    try:
        obj = workflow_attachment.target
        if not obj:
            logger.error("No target object for inventory update")
            return False

        # Example: Check if object has items
        if not hasattr(obj, "items"):
            logger.warning(
                f"Object {obj._meta.label}({obj.pk}) has no 'items' attribute"
            )
            return False

        # Implement your inventory logic here
        logger.info(
            f"Would update inventory for {obj._meta.label}({obj.pk}) "
            f"with {len(obj.items)} items"
        )

        return True

    except Exception as e:
        logger.error(f"Failed to update inventory: {e}", exc_info=True)
        return False


# ============================================================================
# Helper Functions
# ============================================================================


def _resolve_recipients(recipients, workflow_attachment) -> list:
    """
    Resolve recipient keys to actual email addresses.

    Supported keys:
        - "creator": Email of object creator
        - "manager": Email from settings.WORKFLOW_MANAGER_EMAIL
        - "admin": Emails from settings.ADMINS
        - Other values are treated as email addresses
    """
    emails = []
    obj = workflow_attachment.target

    for recipient in recipients:
        if recipient == "creator":
            if hasattr(obj, "created_by"):
                creator = obj.created_by
                if hasattr(creator, "email"):
                    emails.append(creator.email)

        elif recipient == "manager":
            manager_email = getattr(settings, "WORKFLOW_MANAGER_EMAIL", None)
            if manager_email:
                emails.append(manager_email)

        elif recipient == "admin":
            admin_emails = [email for name, email in getattr(settings, "ADMINS", [])]
            emails.extend(admin_emails)

        else:
            # Assume it's an email address
            if "@" in str(recipient):
                emails.append(str(recipient))

    return list(set(emails))  # Remove duplicates


def _resolve_user_recipients(recipients, workflow_attachment) -> list:
    """
    Resolve recipient keys to User objects.

    Supported keys:
        - "creator": Object creator
        - "approvers": Current approval users
        - Other values are treated as user IDs
    """
    users = []
    obj = workflow_attachment.target

    for recipient in recipients:
        if recipient == "creator":
            if hasattr(obj, "created_by"):
                users.append(obj.created_by)

        elif recipient == "approvers":
            # Get current approval users
            from approval_workflow.services import get_current_approval_for_object

            approvals = get_current_approval_for_object(obj)
            for approval in approvals:
                if hasattr(approval, "assigned_to") and approval.assigned_to:
                    users.append(approval.assigned_to)

        else:
            # Assume it's a user ID
            try:
                user = User.objects.get(pk=int(recipient))
                users.append(user)
            except (User.DoesNotExist, ValueError, TypeError):
                logger.warning(f"Could not resolve user recipient: {recipient}")

    return list(set(users))  # Remove duplicates


def _get_default_subject(event_type, workflow_attachment) -> str:
    """Get default email subject based on event type."""
    # Get user's language
    obj = workflow_attachment.target
    user_language = "en"

    if hasattr(obj, "created_by") and hasattr(obj.created_by, "language"):
        user_language = obj.created_by.language

    # Activate translation
    with translation.override(user_language):
        if event_type == "approval":
            # Translators: Email subject when workflow is approved
            return translation.gettext("Workflow Approved - {workflow_name}").format(
                workflow_name=workflow_attachment.workflow.name_en
            )
        elif event_type == "rejection":
            # Translators: Email subject when workflow is rejected
            return translation.gettext("Workflow Rejected - {workflow_name}").format(
                workflow_name=workflow_attachment.workflow.name_en
            )
        else:
            # Translators: Generic email subject for workflow events
            return translation.gettext("Workflow Update - {workflow_name}").format(
                workflow_name=workflow_attachment.workflow.name_en
            )


def _prepare_email_message(
    workflow_attachment, action_parameters: Dict[str, Any], context: Dict[str, Any]
) -> str:
    """Prepare email message content."""
    include_details = action_parameters.get("include_details", True)
    template = action_parameters.get("template")

    if template:
        # Use custom template
        return render_to_string(
            template,
            {
                "workflow": workflow_attachment.workflow,
                "attachment": workflow_attachment,
                "object": workflow_attachment.target,
                "user": context.get("user"),
            },
        )

    # Use default plain text format
    lines = [
        f"Workflow: {workflow_attachment.workflow.name_en}",
        f"Status: {workflow_attachment.status}",
        f"Object: {workflow_attachment.target}",
    ]

    if include_details:
        if workflow_attachment.current_stage:
            lines.append(f"Current Stage: {workflow_attachment.current_stage.name_en}")

        user = context.get("user")
        if user:
            lines.append(f"Action by: {user}")

    return "\n".join(lines)
