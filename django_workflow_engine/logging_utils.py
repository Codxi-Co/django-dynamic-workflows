"""Logging utilities for the django workflow engine.

Provides structured logging functions for monitoring workflow operations,
performance tracking, and debugging in both Arabic and English contexts.
"""

import logging
from typing import Any, Dict, Optional

from django.utils import timezone


class WorkflowLogger:
    """Centralized workflow logging with structured data."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def log_action(self, action: str, level: str = "info", **kwargs):
        """Log workflow action with structured data.

        Args:
            action: Action being performed (in English)
            level: Log level (info, warning, error, debug)
            **kwargs: Additional structured data
        """
        log_data = {"action": action, "timestamp": timezone.now().isoformat(), **kwargs}

        getattr(self.logger, level)(f"WORKFLOW: {action}", extra=log_data)

    def log_workflow_created(
        self, workflow_id: int, user_id: int, name_en: str, name_ar: str
    ):
        """Log workflow creation."""
        self.log_action(
            "workflow_created",
            workflow_id=workflow_id,
            user_id=user_id,
            name_en=name_en,
            name_ar=name_ar,
        )

    def log_workflow_attached(
        self, workflow_id: int, object_type: str, object_id: str, user_id: int = None
    ):
        """Log workflow attachment to object."""
        self.log_action(
            "workflow_attached",
            workflow_id=workflow_id,
            object_type=object_type,
            object_id=object_id,
            user_id=user_id,
        )

    def log_workflow_started(
        self, workflow_id: int, object_type: str, object_id: str, user_id: int = None
    ):
        """Log workflow start."""
        self.log_action(
            "workflow_started",
            workflow_id=workflow_id,
            object_type=object_type,
            object_id=object_id,
            user_id=user_id,
        )

    def log_stage_moved(
        self,
        workflow_id: int,
        from_stage: str,
        to_stage: str,
        object_id: str,
        user_id: int = None,
    ):
        """Log stage transition."""
        self.log_action(
            "stage_moved",
            workflow_id=workflow_id,
            from_stage=from_stage,
            to_stage=to_stage,
            object_id=object_id,
            user_id=user_id,
        )

    def log_workflow_completed(
        self,
        workflow_id: int,
        object_id: str,
        user_id: int = None,
        duration_seconds: float = None,
    ):
        """Log workflow completion."""
        self.log_action(
            "workflow_completed",
            workflow_id=workflow_id,
            object_id=object_id,
            user_id=user_id,
            duration_seconds=duration_seconds,
        )

    def log_workflow_rejected(
        self,
        workflow_id: int,
        stage: str,
        reason: str,
        object_id: str,
        user_id: int = None,
    ):
        """Log workflow rejection."""
        self.log_action(
            "workflow_rejected",
            level="warning",
            workflow_id=workflow_id,
            stage=stage,
            reason=reason,
            object_id=object_id,
            user_id=user_id,
        )

    def log_approval_action(
        self, action: str, workflow_id: int, stage: str, user_id: int = None, **kwargs
    ):
        """Log approval actions (approve, reject, delegate, resubmit)."""
        self.log_action(
            f"approval_{action}",
            workflow_id=workflow_id,
            stage=stage,
            user_id=user_id,
            **kwargs,
        )

    def log_error(self, error_type: str, message: str, **kwargs):
        """Log workflow errors."""
        self.log_action(
            f"error_{error_type}", level="error", error_message=message, **kwargs
        )

    def log_performance(self, operation: str, duration_ms: float, **kwargs):
        """Log performance metrics."""
        self.log_action(
            f"performance_{operation}", level="debug", duration_ms=duration_ms, **kwargs
        )


# Global logger instances
services_logger = WorkflowLogger("django_workflow_engine.services")
models_logger = WorkflowLogger("django_workflow_engine.models")
serializers_logger = WorkflowLogger("django_workflow_engine.serializers")
handlers_logger = WorkflowLogger("django_workflow_engine.handlers")


def log_model_operation(
    model_name: str,
    operation: str,
    object_id: str = None,
    user_id: int = None,
    **kwargs,
):
    """Log model operations (create, update, delete)."""
    models_logger.log_action(
        f"{model_name}_{operation}", object_id=object_id, user_id=user_id, **kwargs
    )


def log_serializer_validation(
    serializer_name: str, is_valid: bool, errors: Dict = None, user_id: int = None
):
    """Log serializer validation results."""
    level = "info" if is_valid else "warning"
    serializers_logger.log_action(
        f"{serializer_name}_validation",
        level=level,
        is_valid=is_valid,
        errors=errors,
        user_id=user_id,
    )


def log_api_request(
    endpoint: str,
    method: str,
    user_id: int = None,
    response_status: int = None,
    duration_ms: float = None,
):
    """Log API requests for workflow endpoints."""
    api_logger = WorkflowLogger("django_workflow_engine.api")
    api_logger.log_action(
        "api_request",
        endpoint=endpoint,
        method=method,
        user_id=user_id,
        response_status=response_status,
        duration_ms=duration_ms,
    )
