"""Authorization helpers for status transition actors."""

import logging
from typing import Any, Dict, Iterable, List

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.module_loading import import_string

from .settings import get_transition_actor_settings
from .utils import get_users_from_role

logger = logging.getLogger(__name__)
User = get_user_model()


TRANSITION_ACTOR_OWNER = "owner"
TRANSITION_ACTOR_CREATOR = "creator"
TRANSITION_ACTOR_ASSIGNED_USER = "assigned_user"
TRANSITION_ACTOR_TEAM_MEMBER = "team_member"
TRANSITION_ACTOR_TEAM_LEAD = "team_lead"
TRANSITION_ACTOR_DEPARTMENT_MEMBER = "department_member"
TRANSITION_ACTOR_SPECIFIC_ROLE = "specific_role"
TRANSITION_ACTOR_SPECIFIC_USER = "specific_user"
TRANSITION_ACTOR_ASSIGNMENT_HISTORY_USER = "assignment_history_user"
TRANSITION_ACTOR_OWNER_MANAGER = "owner_manager"
TRANSITION_ACTOR_CREATOR_MANAGER = "creator_manager"
TRANSITION_ACTOR_ASSIGNED_USER_MANAGER = "assigned_user_manager"
TRANSITION_ACTOR_CUSTOM_FUNCTION = "custom_function"


def can_user_perform_transition(user, obj, transition) -> bool:
    """Return whether user is allowed by transition.metadata.allowed_actors."""
    actor_rules = get_transition_actor_rules(transition)
    if not actor_rules:
        return True
    if not user or getattr(user, "is_anonymous", False):
        return False

    return any(transition_actor_rule_matches(user, obj, rule) for rule in actor_rules)


def explain_transition_actor_denial(transition) -> str:
    """Return a concise error message for denied transition actor checks."""
    actor_rules = get_transition_actor_rules(transition)
    if not actor_rules:
        return "User is not allowed to perform this transition"
    labels = [
        rule if isinstance(rule, str) else str(rule.get("type", rule))
        for rule in actor_rules
    ]
    return (
        "User is not allowed to perform this transition. "
        f"Allowed actors: {', '.join(labels)}"
    )


def get_transition_actor_rules(transition) -> List[Any]:
    """Read allowed actor rules from transition metadata."""
    metadata = transition.metadata or {}
    return (
        metadata.get("allowed_actors")
        or metadata.get("allowed_transition_actors")
        or []
    )


def transition_actor_rule_matches(user, obj, rule) -> bool:
    """Evaluate one allowed actor rule."""
    rule_config = _normalize_actor_rule(rule)
    actor_type = rule_config.get("type")
    if not actor_type:
        return False

    if actor_type in (TRANSITION_ACTOR_OWNER, TRANSITION_ACTOR_CREATOR):
        return _same_user(user, _get_owner(obj, rule_config))

    if actor_type == TRANSITION_ACTOR_ASSIGNED_USER:
        return _same_user(user, _get_assigned_user(obj, rule_config))

    if actor_type == TRANSITION_ACTOR_TEAM_MEMBER:
        return _user_in(user, _get_team_users(obj, rule_config))

    if actor_type == TRANSITION_ACTOR_TEAM_LEAD:
        return _same_user(user, _get_team_lead(obj, rule_config))

    if actor_type == TRANSITION_ACTOR_DEPARTMENT_MEMBER:
        return _user_in(user, _get_department_users(obj, rule_config))

    if actor_type == TRANSITION_ACTOR_SPECIFIC_ROLE:
        return _user_in(user, _get_specific_role_users(rule_config))

    if actor_type == TRANSITION_ACTOR_SPECIFIC_USER:
        return _same_user(user, _get_specific_user(rule_config))

    if actor_type == TRANSITION_ACTOR_ASSIGNMENT_HISTORY_USER:
        return _user_in(user, _get_assignment_history_users(obj, rule_config))

    if actor_type in (
        TRANSITION_ACTOR_OWNER_MANAGER,
        TRANSITION_ACTOR_CREATOR_MANAGER,
    ):
        return _user_in(
            user,
            _get_manager_candidates(_get_owner(obj, rule_config), rule_config, obj=obj),
        )

    if actor_type == TRANSITION_ACTOR_ASSIGNED_USER_MANAGER:
        return _user_in(
            user,
            _get_manager_candidates(
                _get_assigned_user(obj, rule_config), rule_config, obj=obj
            ),
        )

    if actor_type == TRANSITION_ACTOR_CUSTOM_FUNCTION:
        return _evaluate_custom_function(user, obj, rule_config)

    logger.warning("Unknown transition actor type: %s", actor_type)
    return False


def _normalize_actor_rule(rule) -> Dict[str, Any]:
    if isinstance(rule, str):
        return {"type": rule}
    if isinstance(rule, dict):
        return rule
    return {}


def _transition_actor_settings(obj=None) -> Dict[str, Any]:
    return get_transition_actor_settings(obj) or {}


def _get_owner(obj, rule_config):
    field_name = rule_config.get("field") or _transition_actor_settings(obj).get(
        "OWNER_FIELD", "created_by"
    )
    return _get_attr_path(obj, field_name)


def _get_assigned_user(obj, rule_config):
    function_path = rule_config.get("function") or _transition_actor_settings(obj).get(
        "ASSIGNED_USER_FUNCTION"
    )
    if function_path:
        return _call_resolver(
            function_path, obj, actor_type=TRANSITION_ACTOR_ASSIGNED_USER
        )
    field_name = rule_config.get("field") or _transition_actor_settings(obj).get(
        "ASSIGNED_USER_FIELD", "assigned_to"
    )
    return _get_attr_path(obj, field_name)


def _get_team_users(obj, rule_config):
    function_path = rule_config.get("function") or _transition_actor_settings(obj).get(
        "TEAM_USERS_FUNCTION"
    )
    if function_path:
        return _call_resolver(
            function_path, obj, actor_type=TRANSITION_ACTOR_TEAM_MEMBER
        )
    field_name = rule_config.get("field") or _transition_actor_settings(obj).get(
        "TEAM_USERS_FIELD", "team"
    )
    team_value = _get_attr_path(obj, field_name)
    users_field = rule_config.get("users_field") or _transition_actor_settings(obj).get(
        "TEAM_USERS_RELATION", "users"
    )
    return _resolve_related_users(team_value, users_field=users_field)


def _get_team_lead(obj, rule_config):
    function_path = rule_config.get("function") or _transition_actor_settings(obj).get(
        "TEAM_LEAD_FUNCTION"
    )
    if function_path:
        return _call_resolver(function_path, obj, actor_type=TRANSITION_ACTOR_TEAM_LEAD)
    field_name = rule_config.get("field") or _transition_actor_settings(obj).get(
        "TEAM_LEAD_FIELD", "team.lead"
    )
    return _get_attr_path(obj, field_name)


def _get_department_users(obj, rule_config):
    function_path = rule_config.get("function") or _transition_actor_settings(obj).get(
        "DEPARTMENT_USERS_FUNCTION"
    )
    if function_path:
        return _call_resolver(
            function_path, obj, actor_type=TRANSITION_ACTOR_DEPARTMENT_MEMBER
        )
    field_name = rule_config.get("field") or _transition_actor_settings(obj).get(
        "DEPARTMENT_FIELD", "department"
    )
    department = _get_attr_path(obj, field_name)
    users_field = rule_config.get("users_field") or _transition_actor_settings(obj).get(
        "DEPARTMENT_USERS_RELATION", "users"
    )
    return _resolve_related_users(department, users_field=users_field)


def _get_assignment_history_users(obj, rule_config):
    function_path = rule_config.get("function") or _transition_actor_settings(obj).get(
        "ASSIGNMENT_HISTORY_USERS_FUNCTION"
    )
    if function_path:
        return _call_resolver(
            function_path, obj, actor_type=TRANSITION_ACTOR_ASSIGNMENT_HISTORY_USER
        )
    field_name = rule_config.get("field") or _transition_actor_settings(obj).get(
        "ASSIGNMENT_HISTORY_FIELD", "assignment_history"
    )
    history = _get_attr_path(obj, field_name)
    users_field = rule_config.get("users_field") or _transition_actor_settings(obj).get(
        "ASSIGNMENT_HISTORY_USER_FIELD", "user"
    )
    return _resolve_related_users(history, users_field=users_field)


def _get_specific_role_users(rule_config):
    role = rule_config.get("role") or rule_config.get("user_role")
    if role is None:
        return []
    if isinstance(role, int):
        role = _get_role_model().objects.get(id=role)
    return get_users_from_role(role)


def _get_specific_user(rule_config):
    user_value = (
        rule_config.get("user")
        or rule_config.get("user_id")
        or rule_config.get("approval_user")
    )
    if isinstance(user_value, dict):
        user_value = user_value.get("val") or user_value.get("id")
    if isinstance(user_value, int):
        try:
            return User.objects.get(id=user_value)
        except User.DoesNotExist:
            return None
    return user_value


def _get_role_model():
    role_model_path = getattr(settings, "APPROVAL_ROLE_MODEL", "auth.Group")
    app_label, model_name = role_model_path.split(".")
    return apps.get_model(app_label, model_name)


def _get_manager_candidates(base_user, rule_config, obj=None):
    if not base_user:
        return []
    chain = _get_manager_chain(base_user, rule_config, obj=obj)
    levels = _get_manager_levels(rule_config)
    if levels:
        return [chain[level - 1] for level in levels if 0 < level <= len(chain)]
    return chain[:1]


def _get_manager_chain(base_user, rule_config, obj=None):
    actor_settings = _transition_actor_settings(obj)
    manager_field = rule_config.get("manager_field") or actor_settings.get(
        "MANAGER_FIELD", "manager"
    )
    max_depth = int(
        rule_config.get("max_depth") or actor_settings.get("MANAGER_MAX_DEPTH", 10)
    )
    chain = []
    current = base_user
    seen_ids = set()
    for _ in range(max_depth):
        manager = _get_attr_path(current, manager_field)
        if not manager or not getattr(manager, "id", None):
            break
        if manager.id in seen_ids:
            break
        chain.append(manager)
        seen_ids.add(manager.id)
        current = manager
    return chain


def _get_manager_levels(rule_config):
    levels = (
        rule_config.get("manager_levels")
        or rule_config.get("levels")
        or rule_config.get("level")
    )
    if levels is None:
        return None
    if isinstance(levels, int):
        return [levels]
    if isinstance(levels, str):
        return [int(levels)]
    return [int(level) for level in levels]


def _evaluate_custom_function(user, obj, rule_config):
    function_path = (
        rule_config.get("function")
        or rule_config.get("function_path")
        or rule_config.get("resolver")
    )
    if not function_path:
        return False
    result = _call_resolver(
        function_path,
        obj,
        user=user,
        rule=rule_config,
    )
    if isinstance(result, bool):
        return result
    return _user_in(user, result)


def _call_resolver(function_path, obj, **kwargs):
    resolver = import_string(function_path)
    try:
        return resolver(obj=obj, **kwargs)
    except TypeError:
        if kwargs:
            return resolver(obj)
        raise


def _get_attr_path(obj, path):
    if not obj or not path:
        return None
    current = obj
    for part in str(path).split("."):
        current = getattr(current, part, None)
        if callable(current):
            current = current()
        if current is None:
            return None
    return current


def _resolve_related_users(value, users_field="user"):
    if value is None:
        return []
    if _is_user(value):
        return [value]
    if isinstance(value, (list, tuple, set)):
        users = []
        for item in value:
            users.extend(_resolve_related_users(item, users_field=users_field))
        return users
    if hasattr(value, "all"):
        return _resolve_related_users(list(value.all()), users_field=users_field)
    related = getattr(value, users_field, None)
    if related is not None:
        return _resolve_related_users(related, users_field="user")
    return []


def _same_user(user, candidate) -> bool:
    if not user or not candidate:
        return False
    return getattr(user, "id", None) == getattr(candidate, "id", None)


def _user_in(user, candidates: Iterable) -> bool:
    if not user or not candidates:
        return False
    user_id = getattr(user, "id", None)
    return any(getattr(candidate, "id", None) == user_id for candidate in candidates)


def _is_user(value) -> bool:
    return getattr(value, "id", None) is not None and hasattr(value, "is_authenticated")
