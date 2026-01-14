"""Secure action registry for workflow actions.

This module provides a secure, whitelist-based registry for workflow action handlers.
It replaces the unsafe dynamic function execution with a controlled registration system.

Usage:
    from django_workflow_engine.action_registry import registry

    # Register an action handler
    @registry.register(name="send_approval_email")
    def send_approval_email(workflow_attachment, action_parameters, **context):
        # Your action logic here
        return True

    # Execute an action safely
    registry.execute_action(
        action_name="send_approval_email",
        workflow_attachment=attachment,
        action_parameters={...},
        user=user
    )
"""

import inspect
import logging
from typing import Any, Callable, Dict, List, Optional

from django.core.exceptions import ImproperlyConfigured, ValidationError

logger = logging.getLogger(__name__)


class WorkflowActionError(Exception):
    """Base exception for workflow action errors."""

    pass


class ActionNotRegisteredError(WorkflowActionError):
    """Raised when attempting to execute an unregistered action."""

    pass


class ActionExecutionError(WorkflowActionError):
    """Raised when an action fails during execution."""

    pass


class DuplicateActionError(WorkflowActionError):
    """Raised when attempting to register a duplicate action."""

    pass


class WorkflowActionRegistry:
    """
    Secure registry for workflow action handlers.

    This registry provides a whitelist-based approach to action execution,
    replacing unsafe dynamic imports with a controlled registration system.

    Features:
    - Whitelist-based: Only registered actions can be executed
    - Signature validation: Ensures actions have correct parameters
    - Execution tracking: Logs all action executions
    - Error handling: Provides clear error messages
    """

    def __init__(self):
        """Initialize the registry with empty actions dict."""
        self._actions: Dict[str, Callable] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: str,
        allow_override: bool = False,
        description: str = "",
        category: str = "general",
    ) -> Callable:
        """
        Register a workflow action handler.

        Args:
            name: Unique name for this action (used for execution)
            allow_override: Allow re-registering an existing action
            description: Human-readable description of the action
            category: Category for grouping actions (e.g., 'email', 'notification')

        Returns:
            Decorator function to register the action handler

        Raises:
            DuplicateActionError: If action already exists and allow_override=False
            ValueError: If action name is invalid

        Example:
            @registry.register(name="send_approval_email", category="email")
            def send_approval_email(workflow_attachment, action_parameters, **context):
                send_mail(...)
                return True
        """
        if not name or not isinstance(name, str):
            raise ValueError("Action name must be a non-empty string")

        # Validate action name format (alphanumeric, underscores, hyphens)
        if not name.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                f"Invalid action name '{name}'. "
                "Use only alphanumeric characters, underscores, and hyphens."
            )

        def decorator(func: Callable) -> Callable:
            """Decorator to register the action function."""
            # Check if action already exists
            if name in self._actions and not allow_override:
                raise DuplicateActionError(
                    f"Action '{name}' is already registered. "
                    f"Use allow_override=True to replace it."
                )

            # Validate function signature
            self._validate_function_signature(func, name)

            # Register the action
            self._actions[name] = func
            self._metadata[name] = {
                "description": description,
                "category": category,
                "module": func.__module__,
                "function_name": func.__name__,
                "docstring": inspect.getdoc(func) or "",
            }

            logger.info(
                f"Registered workflow action '{name}' in category '{category}' "
                f"(module: {func.__module__})"
            )

            return func

        return decorator

    def _validate_function_signature(self, func: Callable, action_name: str) -> None:
        """
        Validate that the function has an acceptable signature.

        Args:
            func: Function to validate
            action_name: Name of the action (for error messages)

        Raises:
            ValueError: If function signature is invalid
        """
        try:
            sig = inspect.signature(func)
            params = sig.parameters

            # Check for required parameters
            # Actions should at least accept workflow_attachment and **kwargs
            has_workflow_attachment = "workflow_attachment" in params
            has_kwargs = any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
            )

            if not has_workflow_attachment and not has_kwargs:
                raise ValueError(
                    f"Action '{action_name}' must accept 'workflow_attachment' parameter "
                    f"or have **kwargs to accept dynamic context"
                )

        except Exception as e:
            raise ValueError(
                f"Could not validate signature for action '{action_name}': {e}"
            )

    def execute_action(
        self,
        action_name: str,
        workflow_attachment: Any,
        action_parameters: Optional[Dict[str, Any]] = None,
        **context,
    ) -> Any:
        """
        Execute a registered workflow action.

        Args:
            action_name: Name of the registered action
            workflow_attachment: WorkflowAttachment instance
            action_parameters: Optional parameters for the action
            **context: Additional context (user, stage, reason, etc.)

        Returns:
            Result from the action handler

        Raises:
            ActionNotRegisteredError: If action is not registered
            ActionExecutionError: If action execution fails

        Example:
            result = registry.execute_action(
                action_name="send_approval_email",
                workflow_attachment=attachment,
                action_parameters={"recipients": ["user@example.com"]},
                user=request.user
            )
        """
        # Check if action is registered
        if action_name not in self._actions:
            available = ", ".join(self.list_actions())
            raise ActionNotRegisteredError(
                f"Action '{action_name}' is not registered. "
                f"Available actions: {available or 'None'}"
            )

        # Get the action handler
        handler = self._actions[action_name]
        metadata = self._metadata[action_name]

        # Prepare parameters
        params = {
            "workflow_attachment": workflow_attachment,
            "action_parameters": action_parameters or {},
            **context,
        }

        # Execute the action
        logger.info(
            f"Executing action '{action_name}' (category: {metadata['category']}) "
            f"for workflow {workflow_attachment.workflow.id}"
        )

        try:
            result = handler(**params)

            logger.info(
                f"Action '{action_name}' executed successfully "
                f"(result: {result}, workflow: {workflow_attachment.workflow.id})"
            )

            return result

        except Exception as e:
            logger.error(
                f"Action '{action_name}' execution failed: {e}",
                exc_info=True,
                extra={
                    "action_name": action_name,
                    "workflow_id": workflow_attachment.workflow.id,
                },
            )
            raise ActionExecutionError(
                f"Execution of action '{action_name}' failed: {e}"
            ) from e

    def is_registered(self, action_name: str) -> bool:
        """Check if an action is registered."""
        return action_name in self._actions

    def get_action(self, action_name: str) -> Optional[Callable]:
        """
        Get an action handler by name.

        Returns None if action is not registered (safe alternative to execute_action).
        """
        return self._actions.get(action_name)

    def list_actions(self, category: Optional[str] = None) -> List[str]:
        """
        List all registered action names.

        Args:
            category: Optional filter by category

        Returns:
            List of action names
        """
        if category:
            return [
                name
                for name, meta in self._metadata.items()
                if meta.get("category") == category
            ]
        return list(self._actions.keys())

    def list_actions_by_category(self) -> Dict[str, List[str]]:
        """
        List all actions grouped by category.

        Returns:
            Dictionary mapping categories to lists of action names
        """
        categories: Dict[str, List[str]] = {}
        for name, meta in self._metadata.items():
            cat = meta.get("category", "general")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(name)
        return categories

    def get_action_metadata(self, action_name: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a registered action."""
        return self._metadata.get(action_name)

    def unregister(self, action_name: str) -> None:
        """
        Unregister an action.

        Raises:
            ActionNotRegisteredError: If action is not registered
        """
        if action_name not in self._actions:
            raise ActionNotRegisteredError(f"Action '{action_name}' is not registered")

        del self._actions[action_name]
        del self._metadata[action_name]

        logger.info(f"Unregistered action '{action_name}'")

    def clear(self) -> None:
        """Clear all registered actions (useful for testing)."""
        self._actions.clear()
        self._metadata.clear()
        logger.info("Cleared all registered actions")

    def validate_action_config(self, function_path: str) -> bool:
        """
        Validate an action configuration string.

        This is used to validate legacy function_path strings.
        Returns True if the path maps to a registered action.

        Args:
            function_path: Legacy path string (e.g., 'myapp.actions.send_email')

        Returns:
            True if valid, False otherwise
        """
        # Check if it's a direct action name
        if function_path in self._actions:
            return True

        # For legacy paths, check if the last component matches an action
        # This supports backward compatibility
        action_name = function_path.split(".")[-1]
        return action_name in self._actions


# Global registry instance
registry = WorkflowActionRegistry()


def register_action(
    name: str,
    allow_override: bool = False,
    description: str = "",
    category: str = "general",
) -> Callable:
    """
    Convenience decorator for registering actions.

    Usage:
        from django_workflow_engine.action_registry import register_action

        @register_action(name="send_email", category="notification")
        def send_email_handler(workflow_attachment, action_parameters, **context):
            return True
    """
    return registry.register(
        name=name,
        allow_override=allow_override,
        description=description,
        category=category,
    )


def execute_action(
    action_name: str,
    workflow_attachment: Any,
    action_parameters: Optional[Dict[str, Any]] = None,
    **context,
) -> Any:
    """
    Convenience function for executing registered actions.

    Usage:
        from django_workflow_engine.action_registry import execute_action

        result = execute_action(
            action_name="send_email",
            workflow_attachment=attachment,
            user=request.user
        )
    """
    return registry.execute_action(
        action_name=action_name,
        workflow_attachment=workflow_attachment,
        action_parameters=action_parameters,
        **context,
    )
