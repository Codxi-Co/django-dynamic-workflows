"""
Enhanced structured logging for django_workflow_engine.

This module provides emoji-based structured logging that matches the
django-approval-workflow package's logging format.

Features:
- Emoji indicators for quick log scanning
- Structured key-value format
- Event categorization
- Bilingual support (English/Arabic)
"""

import logging
from typing import Any, Dict, Optional

from django.utils import translation

# Event emoji indicators (matches approval-workflow package)
LOG_EMOJIS = {
    # Workflow lifecycle events
    "workflow_created": "✨",
    "workflow_started": "🚀",
    "workflow_completed": "🎉",
    "workflow_cancelled": "🛑",
    # Stage events
    "stage_entered": "📍",
    "stage_exited": "🚪",
    "stage_approved": "✅",
    "stage_rejected": "❌",
    # Role-based strategy events
    "activating_role_step": "🎯",
    "quorum_reached": "✅",
    "quorum_progress": "📊",
    "quorum_pending": "⏳",
    "hierarchy_escalate": "📈",
    # Action events
    "action_executed": "⚡",
    "action_failed": "💥",
    "action_skipped": "⏭️",
    # User events
    "user_approved": "👍",
    "user_rejected": "👎",
    "user_delegated": "🤝",
    "user_escalated": "⬆️",
    # System events
    "validation_passed": "✅",
    "validation_failed": "❌",
    "migration_applied": "🔄",
    "error": "⚠️",
    "warning": "⚡",
    "info": "ℹ️",
}

logger = logging.getLogger(__name__)


class StructuredLogger:
    """
    Structured logger with emoji indicators and key-value format.

    Matches the django-approval-workflow package logging format:

    [WORKFLOW_ENGINE] 🎯 EVENT | Key: value | Key: value

    Example:
        log_workflow_event(
            "workflow_created",
            workflow_id=123,
            object_type="PurchaseOrder",
            object_id=456
        )
        # Output: [WORKFLOW_ENGINE] ✨ WORKFLOW_CREATED | workflow_id: 123 | object_type: PurchaseOrder | object_id: 456
    """

    def __init__(self, module_name: str):
        """Initialize the structured logger.

        Args:
            module_name: Name of the module (usually __name__)
        """
        self.logger = logging.getLogger(module_name)
        self.prefix = "[WORKFLOW_ENGINE]"

    def _format_message(self, event_type: str, context: Dict[str, Any]) -> str:
        """Format log message with emoji and key-value pairs."""
        emoji = LOG_EMOJIS.get(event_type, "📌")

        # Format context as key=value pairs
        context_parts = []
        for key, value in context.items():
            if value is None:
                value_str = "None"
            elif isinstance(value, bool):
                value_str = "True" if value else "False"
            elif hasattr(value, "_meta"):  # Django model
                value_str = f"{value._meta.label}({value.pk})"
            else:
                value_str = str(value)

            context_parts.append(f"{key}: {value_str}")

        context_str = " | ".join(context_parts)

        return f"{self.prefix} {emoji} {event_type.upper()} | {context_str}"

    def info(self, event_type: str, **context):
        """Log info level event."""
        message = self._format_message(event_type, context)
        self.logger.info(message)

    def debug(self, event_type: str, **context):
        """Log debug level event."""
        message = self._format_message(event_type, context)
        self.logger.debug(message)

    def warning(self, event_type: str, **context):
        """Log warning level event."""
        message = self._format_message(event_type, context)
        self.logger.warning(message)

    def error(self, event_type: str, **context):
        """Log error level event."""
        message = self._format_message(event_type, context)
        self.logger.error(message)


# Convenience function for quick logging
def log_workflow_event(event_type: str, **context):
    """
    Log a workflow event with structured format.

    Args:
        event_type: Type of event (e.g., "workflow_created", "stage_approved")
        **context: Key-value pairs for the log message

    Example:
        log_workflow_event(
            "workflow_created",
            workflow_id=123,
            name="Test Workflow"
        )
        # Output: [WORKFLOW_ENGINE] ✨ WORKFLOW_CREATED | workflow_id: 123 | name: Test Workflow
    """
    event_logger = StructuredLogger(__name__)
    event_logger.info(event_type, **context)


def log_workflow_event_with_user(event_type: str, user, **context):
    """
    Log a workflow event including user information.

    Args:
        event_type: Type of event
        user: User object (can be None)
        **context: Additional key-value pairs

    Example:
        log_workflow_event_with_user(
            "stage_approved",
            user=request.user,
            stage_id=1,
            workflow_id=123
        )
    """
    if user:
        context["user_id"] = user.id
        context["username"] = getattr(user, "username", str(user))

    log_workflow_event(event_type, **context)


def log_workflow_error(event_type: str, error: Exception, **context):
    """
    Log a workflow error with exception details.

    Args:
        event_type: Type of error event
        error: Exception object
        **context: Additional context

    Example:
        try:
            ...
        except Exception as e:
            log_workflow_error("action_failed", e, action_id=123)
    """
    context["error_type"] = type(error).__name__
    context["error_message"] = str(error)[:100]  # Truncate long errors

    event_logger = StructuredLogger(__name__)
    event_logger.error(event_type, **context)


# Convenience instances for common modules
workflow_logger = StructuredLogger("django_workflow_engine.services")
handler_logger = StructuredLogger("django_workflow_engine.handlers")
action_logger = StructuredLogger("django_workflow_engine.action_executor")
strategy_logger = StructuredLogger("django_workflow_engine.strategy_handlers")
