"""Resolve approval-step assignees from workflow objects and project settings."""

import inspect
from typing import Any, Dict, Optional

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Manager, QuerySet
from django.utils.module_loading import import_string

from .settings import get_assignment_resolvers


def _resolve_path(value: Any, path: str) -> Any:
    for part in path.split("."):
        if value is None:
            return None
        value = getattr(value, part, None)
        if callable(value) and not isinstance(value, (Manager, QuerySet)):
            value = value()
    if isinstance(value, Manager):
        value = value.all()
    if isinstance(value, QuerySet):
        value = value.first()
    return value


def _coerce_user(value: Any) -> Any:
    if value is None:
        return None
    User = get_user_model()
    if isinstance(value, User):
        return value
    if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        return User.objects.filter(pk=value).first()
    if hasattr(value, "user"):
        return value.user
    return value if getattr(value, "is_authenticated", False) else None


def _call_resolver(path: str, obj: Any, approval: Dict[str, Any]):
    resolver = import_string(path)
    parameters = inspect.signature(resolver).parameters
    kwargs = {
        "obj": obj,
        "approval": approval,
    }
    if any(p.kind == p.VAR_KEYWORD for p in parameters.values()):
        return resolver(**kwargs)
    return resolver(
        **{key: value for key, value in kwargs.items() if key in parameters}
    )


def _query_value(value: Any, obj: Any, approval: Dict[str, Any]):
    if not isinstance(value, str) or not value.startswith("$"):
        return value
    expression = value[1:]
    if expression == "object":
        return obj
    if expression.startswith("object."):
        return _resolve_path(obj, expression[7:])
    if expression.startswith("approval."):
        return approval.get(expression[9:])
    raise ImproperlyConfigured(f"Unknown assignment query expression: {value}")


def _resolve_from_spec(spec, obj, approval):
    if isinstance(spec, str):
        spec = {"field": spec}
    if not isinstance(spec, dict):
        raise ImproperlyConfigured("Assignment resolver must be a string or dict")
    if spec.get("function"):
        return _call_resolver(spec["function"], obj, approval)
    if spec.get("field"):
        return _resolve_path(obj, spec["field"])
    if spec.get("model"):
        try:
            model = apps.get_model(spec["model"])
        except (LookupError, ValueError) as exc:
            raise ImproperlyConfigured(
                f"Invalid assignment model '{spec['model']}'"
            ) from exc
        query = {
            key: _query_value(value, obj, approval)
            for key, value in (spec.get("query") or {}).items()
        }
        queryset = model.objects.filter(**query)
        if spec.get("order_by"):
            order_by = spec["order_by"]
            queryset = queryset.order_by(
                *([order_by] if isinstance(order_by, str) else order_by)
            )
        assignment = queryset.first()
        return _resolve_path(assignment, spec.get("user_field", "user"))
    raise ImproperlyConfigured("Assignment resolver requires field, model, or function")


def resolve_assigned_user(
    obj: Any,
    approval: Dict[str, Any],
    default_user: Optional[Any] = None,
):
    """Resolve the concrete user for an ``ApprovalTypes.ASSIGNED`` step.

    Resolution can be declared inline with ``assign_function`` or per target
    model in ``DJANGO_WORKFLOW_ENGINE['ASSIGNMENT_RESOLVERS']``.
    """
    if not obj:
        raise ValueError("approval_type 'assigned' requires the workflow target object")

    inline_function = approval.get("assign_function")
    if inline_function:
        user = _call_resolver(inline_function, obj, approval)
    else:
        spec = get_assignment_resolvers(obj)
        if not spec:
            for field in ("assigned_to", "assignee", "assigned_user"):
                user = _coerce_user(_resolve_path(obj, field))
                if user:
                    return user
            raise ImproperlyConfigured(
                f"No assignment resolver configured for {obj._meta.label}"
            )
        user = _resolve_from_spec(spec, obj, approval)

    user = _coerce_user(user)
    if not user:
        raise ValueError(
            "Assignment resolver returned no user for " f"{obj._meta.label}({obj.pk})"
        )
    return user
