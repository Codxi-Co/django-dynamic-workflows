"""Recipient resolution for workflow email notifications."""

import logging
from typing import List, Optional, Set, Union

from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


def resolve_recipients(
    recipient_types: List[Union[str, User, int]], workflow_attachment, **context
) -> Set[str]:
    """
    Resolve recipient types to actual email addresses.

    Supported types:
    - 'creator': Object creator (from attached_object.created_by)
    - 'current_approver': Current approval step approver(s)
    - 'delegated_to': User delegated to (from context)
    - 'workflow_starter': User who started workflow
    - User object: Direct user object
    - int: User ID
    - str (email): Direct email address

    Args:
        recipient_types: List of recipient types or direct values
        workflow_attachment: WorkflowAttachment instance
        **context: Additional context (delegated_to, user, etc.)

    Returns:
        Set of unique email addresses

    Example:
        emails = resolve_recipients(
            recipient_types=['creator', 'current_approver', 'user@example.com'],
            workflow_attachment=attachment,
            delegated_to=user_obj
        )
    """
    recipients = set()

    if not workflow_attachment:
        logger.warning("No workflow_attachment provided to resolve_recipients")
        return recipients

    attached_object = workflow_attachment.target

    for recipient_type in recipient_types:
        # Handle direct email strings
        if isinstance(recipient_type, str):
            # Check if it's an email address
            if "@" in recipient_type:
                recipients.add(recipient_type)
                continue

            # Handle recipient type strings
            if recipient_type == "creator":
                email = _resolve_creator(attached_object)
                if email:
                    recipients.add(email)

            elif recipient_type == "current_approver":
                emails = _resolve_current_approvers(attached_object)
                recipients.update(emails)

            elif recipient_type == "delegated_to":
                email = _resolve_delegated_to(context)
                if email:
                    recipients.add(email)

            elif recipient_type == "workflow_starter":
                email = _resolve_workflow_starter(workflow_attachment)
                if email:
                    recipients.add(email)

            else:
                logger.warning(f"Unknown recipient type: {recipient_type}")

        # Handle User objects
        elif hasattr(recipient_type, "email"):
            email = getattr(recipient_type, "email", None)
            if email:
                recipients.add(email)
            else:
                logger.warning(f"User object {recipient_type} has no email")

        # Handle User IDs
        elif isinstance(recipient_type, int):
            email = _resolve_user_id(recipient_type)
            if email:
                recipients.add(email)

    logger.debug(
        f"Resolved {len(recipients)} unique recipients from {len(recipient_types)} inputs"
    )
    return recipients


def _resolve_creator(attached_object) -> Optional[str]:
    """Resolve creator email from attached object."""
    if not attached_object:
        return None

    if hasattr(attached_object, "created_by"):
        creator = attached_object.created_by
        if creator and hasattr(creator, "email"):
            return creator.email

    logger.debug("No creator found for attached object")
    return None


def _resolve_current_approvers(attached_object) -> Set[str]:
    """Resolve current approver emails from approval workflow."""
    emails = set()

    if not attached_object:
        return emails

    try:
        from approval_workflow.services import get_current_approval_for_object

        approvals = get_current_approval_for_object(attached_object)

        if not approvals:
            logger.debug("No current approvals found for object")
            return emails

        # approvals can be a single object or a list
        if not isinstance(approvals, list):
            approvals = [approvals]

        for approval in approvals:
            if hasattr(approval, "user") and approval.user:
                if hasattr(approval.user, "email"):
                    email = approval.user.email
                    if email:
                        emails.add(email)
                    else:
                        logger.warning(f"Approver user {approval.user} has no email")

            # Handle role-based approvals (multiple users)
            if hasattr(approval, "role") and approval.role:
                role = approval.role
                if hasattr(role, "users"):
                    for user in role.users.all():
                        if hasattr(user, "email") and user.email:
                            emails.add(user.email)

    except ImportError:
        logger.error(
            "approval_workflow package not installed, cannot resolve current approvers"
        )
    except Exception as e:
        logger.error(f"Error resolving current approvers: {e}")

    return emails


def _resolve_delegated_to(context: dict) -> Optional[str]:
    """Resolve delegated_to email from context."""
    delegated_to = context.get("delegated_to")

    if not delegated_to:
        return None

    # Handle User object
    if hasattr(delegated_to, "email"):
        return delegated_to.email

    # Handle User ID
    if isinstance(delegated_to, int):
        return _resolve_user_id(delegated_to)

    return None


def _resolve_workflow_starter(workflow_attachment) -> Optional[str]:
    """Resolve workflow starter email from workflow attachment."""
    if not workflow_attachment:
        return None

    if hasattr(workflow_attachment, "started_by"):
        starter = workflow_attachment.started_by
        if starter and hasattr(starter, "email"):
            return starter.email

    logger.debug("No workflow starter found")
    return None


def _resolve_user_id(user_id: int) -> Optional[str]:
    """Resolve user email from user ID."""
    try:
        user = User.objects.get(pk=user_id)
        if hasattr(user, "email"):
            return user.email
        else:
            logger.warning(f"User {user_id} has no email attribute")
    except User.DoesNotExist:
        logger.warning(f"User with ID {user_id} not found")

    return None
