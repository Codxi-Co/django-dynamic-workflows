"""Email notification service for workflow actions."""

import logging
from typing import Callable, Dict, List, Optional, Union

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)
User = get_user_model()


def get_custom_send_email_function() -> Optional[Callable]:
    """
    Get custom send_email function from settings if configured.

    Returns:
        Callable or None: Custom send_email function if configured, None otherwise

    Example in settings.py:
        WORKFLOW_SEND_EMAIL_FUNCTION = 'myapp.utils.send_email'
    """
    custom_function_path = getattr(settings, "WORKFLOW_SEND_EMAIL_FUNCTION", None)

    if custom_function_path:
        try:
            return import_string(custom_function_path)
        except (ImportError, AttributeError) as e:
            logger.error(
                f"Failed to import custom send_email function '{custom_function_path}': {e}"
            )

    return None


def send_workflow_email(
    name: str,
    email: Optional[str] = None,
    user: Optional[Union[User, int]] = None,
    context: Optional[Dict] = None,
    html_only: bool = True,
    from_email: str = None,
    bcc: Optional[List[str]] = None,
    template_name: str = None,
) -> bool:
    """
    Send email notification for workflow actions.

    Supports custom email sending function via settings.WORKFLOW_SEND_EMAIL_FUNCTION.
    Falls back to Django's EmailMultiAlternatives if no custom function is provided.

    Args:
        name: Email template name (without extension)
        email: Recipient email address
        user: User object or user ID
        context: Template context dictionary
        html_only: Whether to send HTML only (no plain text alternative)
        from_email: Sender email address
        bcc: List of BCC email addresses
        template_name: Optional custom template name

    Returns:
        bool: True if email was sent successfully, False otherwise

    Example:
        send_workflow_email(
            name='workflow_approval',
            user=approver,
            context={
                'workflow_name': 'Opportunity Approval',
                'requester_name': 'John Doe',
                'object_name': 'Q4 Sales Opportunity',
            }
        )

        # In settings.py, configure custom send_email function:
        WORKFLOW_SEND_EMAIL_FUNCTION = 'myapp.utils.send_email'

        # Custom function signature:
        def send_email(name, email, subject, context, user=None):
            # Your custom email sending logic
            pass
    """
    if not from_email:
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")

    # Get user email
    recipient_email = None
    user_obj = None

    if email:
        recipient_email = email
    elif user:
        if isinstance(user, int):
            try:
                user_obj = User.objects.get(pk=user)
                user = user_obj
            except User.DoesNotExist:
                logger.error(f"User with ID {user} not found for email notification")
                return False
        else:
            user_obj = user

        if hasattr(user, "email"):
            recipient_email = user.email
        else:
            logger.error(f"User {user} has no email address")
            return False

    if not recipient_email:
        logger.error("No recipient email provided")
        return False

    # Prepare context with defaults
    default_context = {
        "site_name": getattr(settings, "SITE_NAME", "Workflow System"),
        "company_name": getattr(settings, "COMPANY_NAME", "Your Company"),
        "company_logo": getattr(settings, "COMPANY_LOGO_URL", None),
        "frontend_url": getattr(settings, "FRONTEND_URL", "http://localhost:3000"),
        "support_email": getattr(
            settings, "SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL
        ),
    }

    if context:
        default_context.update(context)

    context = default_context

    # Prepare subject from context or template name
    subject = context.get(
        "subject", f"Workflow Notification: {name.replace('_', ' ').title()}"
    )

    # Check for custom send_email function
    custom_send_email = get_custom_send_email_function()

    if custom_send_email:
        try:
            # Use customer's custom send_email function
            # Signature: send_email(name, email, subject, context, user=None)
            custom_send_email(
                name=name,
                email=recipient_email,
                subject=subject,
                context=context,
                user=user_obj,
            )
            logger.info(
                f"Email '{name}' sent successfully to {recipient_email} using custom function"
            )
            return True
        except Exception as e:
            logger.error(
                f"Failed to send email '{name}' to {recipient_email} using custom function: {str(e)}"
            )
            return False

    # Fallback to default EmailMultiAlternatives
    # Determine template name
    if not template_name:
        template_name = f"django_workflow_engine/emails/{name}.html"

    try:
        # Render HTML content
        html_content = render_to_string(template_name, context)

        # Create email message
        if html_only:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=strip_tags(html_content),  # Plain text fallback
                from_email=from_email,
                to=[recipient_email],
                bcc=bcc or [],
            )
            msg.attach_alternative(html_content, "text/html")
        else:
            # Render plain text version
            plain_template = template_name.replace(".html", ".txt")
            try:
                plain_content = render_to_string(plain_template, context)
            except Exception:
                # If no plain text template, strip HTML
                plain_content = strip_tags(html_content)

            msg = EmailMultiAlternatives(
                subject=subject,
                body=plain_content,
                from_email=from_email,
                to=[recipient_email],
                bcc=bcc or [],
            )
            msg.attach_alternative(html_content, "text/html")

        # Send email
        msg.send(fail_silently=False)

        logger.info(
            f"Email '{name}' sent successfully to {recipient_email} using EmailMultiAlternatives"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to send email '{name}' to {recipient_email}: {str(e)}")
        return False


def send_bulk_workflow_emails(
    name: str,
    recipients: List[Union[str, User, int]],
    context: Optional[Dict] = None,
    html_only: bool = True,
    from_email: str = None,
    template_name: str = None,
    deduplicate: bool = True,
) -> Dict[str, int]:
    """
    Send email to multiple recipients with duplicate prevention.

    Args:
        name: Email template name
        recipients: List of email addresses, User objects, or user IDs
        context: Template context dictionary
        html_only: Whether to send HTML only
        from_email: Sender email address
        template_name: Optional custom template name
        deduplicate: Whether to remove duplicate email addresses

    Returns:
        Dict with 'sent' and 'failed' counts

    Example:
        result = send_bulk_workflow_emails(
            name='workflow_approval',
            recipients=[creator, approver1, approver2],
            context={'workflow_name': 'Approval Process'}
        )
        # Returns: {'sent': 2, 'failed': 0, 'skipped': 1}
    """
    if not recipients:
        logger.warning("No recipients provided for bulk email")
        return {"sent": 0, "failed": 0, "skipped": 0}

    # Collect unique email addresses
    email_addresses = set() if deduplicate else []
    user_map = {}  # Map email to user for context enrichment

    for recipient in recipients:
        if isinstance(recipient, str):
            # Direct email address
            if deduplicate:
                email_addresses.add(recipient)
            else:
                email_addresses.append(recipient)
        elif isinstance(recipient, int):
            # User ID
            try:
                user = User.objects.get(pk=recipient)
                email = getattr(user, "email", None)
                if email:
                    if deduplicate:
                        email_addresses.add(email)
                    else:
                        email_addresses.append(email)
                    user_map[email] = user
            except User.DoesNotExist:
                logger.warning(f"User with ID {recipient} not found")
        elif hasattr(recipient, "email"):
            # User object
            email = getattr(recipient, "email", None)
            if email:
                if deduplicate:
                    email_addresses.add(email)
                else:
                    email_addresses.append(email)
                user_map[email] = recipient

    # Send emails
    sent = 0
    failed = 0
    skipped = len(recipients) - len(email_addresses) if deduplicate else 0

    for email in email_addresses:
        # Enrich context with user-specific data if available
        email_context = context.copy() if context else {}
        if email in user_map:
            user = user_map[email]
            email_context["recipient_name"] = (
                getattr(user, "get_full_name", lambda: user.username)()
                if hasattr(user, "get_full_name")
                else getattr(user, "username", "User")
            )
            email_context["recipient_email"] = email

        success = send_workflow_email(
            name=name,
            email=email,
            context=email_context,
            html_only=html_only,
            from_email=from_email,
            template_name=template_name,
        )

        if success:
            sent += 1
        else:
            failed += 1

    logger.info(
        f"Bulk email '{name}' completed - Sent: {sent}, Failed: {failed}, Skipped: {skipped}"
    )

    return {"sent": sent, "failed": failed, "skipped": skipped}


def get_workflow_email_context(workflow_attachment, stage=None, user=None, **kwargs):
    """
    Build default email context from workflow attachment and related objects.

    Args:
        workflow_attachment: WorkflowAttachment instance
        stage: Optional Stage instance
        user: Optional User performing the action
        **kwargs: Additional context variables

    Returns:
        Dict: Email context dictionary
    """
    from .models import WorkflowAttachment

    if not isinstance(workflow_attachment, WorkflowAttachment):
        logger.error(
            "Invalid workflow_attachment provided to get_workflow_email_context"
        )
        return kwargs

    attached_object = workflow_attachment.target
    workflow = workflow_attachment.workflow

    context = {
        # Workflow information
        "workflow_name": workflow.name_en if workflow else "Workflow",
        "workflow_id": workflow.id if workflow else None,
        # Stage information
        "stage_name": (
            stage.name_en
            if stage
            else (
                workflow_attachment.current_stage.name_en
                if workflow_attachment.current_stage
                else "N/A"
            )
        ),
        "stage_id": (
            stage.id
            if stage
            else (
                workflow_attachment.current_stage.id
                if workflow_attachment.current_stage
                else None
            )
        ),
        # Object information
        "object_name": str(attached_object) if attached_object else "N/A",
        "object_type": (
            attached_object._meta.verbose_name if attached_object else "Object"
        ),
        "object_id": attached_object.pk if attached_object else None,
        # Creator information
        "requester_name": "Unknown",
        "requester_email": None,
        # Current user information
        "actor_name": "System",
        "actor_email": None,
        # Status
        "workflow_status": workflow_attachment.status,
        "started_at": workflow_attachment.started_at,
    }

    # Get creator information
    if attached_object and hasattr(attached_object, "created_by"):
        creator = attached_object.created_by
        if creator:
            context["requester_name"] = (
                getattr(creator, "get_full_name", lambda: creator.username)()
                if hasattr(creator, "get_full_name")
                else getattr(creator, "username", "Unknown")
            )
            context["requester_email"] = getattr(creator, "email", None)

    # Get actor information
    if user:
        context["actor_name"] = (
            getattr(user, "get_full_name", lambda: user.username)()
            if hasattr(user, "get_full_name")
            else getattr(user, "username", "User")
        )
        context["actor_email"] = getattr(user, "email", None)

    # Get company information
    if attached_object and hasattr(attached_object, "company"):
        company = attached_object.company
        if company:
            context["company_name"] = getattr(company, "name", "Your Company")
            context["company_logo"] = getattr(company, "logo", None)

    # Build object link
    if attached_object:
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
        model_name = attached_object._meta.model_name
        context["object_link"] = f"{frontend_url}/{model_name}s/{attached_object.pk}"

    # Merge with additional kwargs
    context.update(kwargs)

    return context
