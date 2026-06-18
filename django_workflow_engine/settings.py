"""
Django Workflow Engine Settings Configuration
"""

from typing import Optional

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string


def get_workflow_settings():
    """Get workflow engine settings with defaults"""
    return getattr(settings, "DJANGO_WORKFLOW_ENGINE", {})


def _import_setting(path, default=None):
    """Import a class/function from settings, returning default when not set."""
    if not path:
        return default
    try:
        return import_string(path)
    except ImportError as exc:
        raise ImproperlyConfigured(f"Could not import '{path}': {exc}") from exc


def get_status_api_viewset_mixins():
    """Return project-provided mixins for status API ViewSets."""
    workflow_settings = get_workflow_settings()
    mixins = workflow_settings.get("STATUS_API_VIEWSET_MIXINS", [])
    if isinstance(mixins, str):
        mixins = [mixins]
    return tuple(_import_setting(path) for path in mixins)


def get_status_base_serializer_class():
    """Return base serializer class for non-named status serializers."""
    from rest_framework import serializers

    workflow_settings = get_workflow_settings()
    return _import_setting(
        workflow_settings.get("STATUS_BASE_SERIALIZER"),
        serializers.ModelSerializer,
    )


def get_status_named_serializer_class():
    """Return base serializer class for named status serializers."""
    return _import_setting(
        get_workflow_settings().get("STATUS_NAMED_SERIALIZER"),
        get_status_base_serializer_class(),
    )


def get_enabled_models():
    """
    Get list of models enabled for workflow functionality

    Returns:
        list: List of model strings in 'app_label.ModelName' format

    Example in settings.py:
        DJANGO_WORKFLOW_ENGINE = {
            'ENABLED_MODELS': [
                'myapp.PurchaseRequest',
                'crm.Opportunity',
                'support.Ticket',
                'hr.LeaveRequest'
            ]
        }
    """
    workflow_settings = get_workflow_settings()
    return workflow_settings.get("ENABLED_MODELS", [])


def get_default_workflow_status_field():
    """Get default status field name for workflow models"""
    workflow_settings = get_workflow_settings()
    return workflow_settings.get("DEFAULT_STATUS_FIELD", "workflow_status")


def get_workflow_model_mappings():
    """
    Get workflow-to-model mappings configuration

    Returns:
        dict: Mapping of model strings to their allowed workflows

    Supports a 'default' key as fallback for models without a specific mapping.

    Example in settings.py:
        DJANGO_WORKFLOW_ENGINE = {
            'MODEL_WORKFLOW_MAPPINGS': {
                'default': ['generic_approval'],
                'myapp.PurchaseRequest': ['purchase_approval', 'emergency_approval'],
                'crm.Opportunity': ['sales_process', 'enterprise_sales'],
            }
        }
    """
    workflow_settings = get_workflow_settings()
    return workflow_settings.get("MODEL_WORKFLOW_MAPPINGS", {})


def get_workflows_for_model_string(model_string: str) -> Optional[list]:
    """
    Get configured workflow slugs for a model string, with 'default' fallback.

    Resolution order:
        1. Exact model match (e.g. 'crm.Opportunity')
        2. 'default' key if no exact match

    Args:
        model_string: Model string in 'app_label.ModelName' format

    Returns:
        list of workflow slug strings, or None if nothing configured
    """
    mappings = get_workflow_model_mappings()
    if model_string in mappings:
        return mappings[model_string]
    if "default" in mappings:
        return mappings["default"]
    return None


def get_auto_start_workflows():
    """
    Get models that should auto-start workflows when created

    Returns:
        dict: Model strings mapped to their auto-start configuration

    Supports a 'default' key as fallback for models without a specific config.

    Example in settings.py:
        DJANGO_WORKFLOW_ENGINE = {
            'AUTO_START_WORKFLOWS': {
                'default': {
                    'workflow_slug': 'generic_approval',
                    'auto_start': True,
                },
                'myapp.PurchaseRequest': {
                    'workflow_slug': 'purchase_approval',
                    'conditions': {
                        'amount__gte': 1000
                    }
                },
                'crm.Opportunity': {
                    'workflow_slug': 'sales_process'
                }
            }
        }
    """
    workflow_settings = get_workflow_settings()
    return workflow_settings.get("AUTO_START_WORKFLOWS", {})


def get_auto_start_config_for_model(model_string: str) -> Optional[dict]:
    """
    Get auto-start config for a model string, with 'default' fallback.

    Resolution order:
        1. Exact model match (e.g. 'crm.Opportunity')
        2. 'default' key if no exact match

    Args:
        model_string: Model string in 'app_label.ModelName' format

    Returns:
        dict with auto-start configuration, or None if nothing configured
    """
    auto_start = get_auto_start_workflows()
    if model_string in auto_start:
        return auto_start[model_string]
    if "default" in auto_start:
        return auto_start["default"]
    return None


def get_department_model_mapping():
    """
    Get department model mapping configuration

    Returns:
        str: Model string for department model or None for no mapping

    Example in settings.py:
        DJANGO_WORKFLOW_ENGINE = {
            'DEPARTMENT_MODEL': 'myapp.Department'  # Map to any model
        }

    This allows users to map the department GenericForeignKey to any model:
    - 'myapp.Department'
    - 'auth.Group'
    - 'companies.Division'
    - etc.
    """
    workflow_settings = get_workflow_settings()
    return workflow_settings.get("DEPARTMENT_MODEL", None)


def get_workflow_permissions():
    """
    Get workflow permissions configuration

    Returns:
        dict: Permission configuration for workflows

    Example in settings.py:
        DJANGO_WORKFLOW_ENGINE = {
            'PERMISSIONS': {
                'REQUIRE_PERMISSION_TO_START': True,
                'REQUIRE_PERMISSION_TO_APPROVE': True,
                'DEFAULT_PERMISSIONS': {
                    'can_start_workflow': 'workflow.start_workflow',
                    'can_approve': 'workflow.approve_workflow',
                    'can_reject': 'workflow.reject_workflow',
                    'can_delegate': 'workflow.delegate_workflow'
                }
            }
        }
    """
    workflow_settings = get_workflow_settings()
    return workflow_settings.get("PERMISSIONS", {})


def get_workflow_actions_config():
    """
    Get workflow actions configuration.

    Supports two formats:

    1. Flat list (backward compatible):
        WORKFLOW_ACTIONS_CONFIG = [
            {'action_type': 'after_approve', 'function_path': '...', ...}
        ]

    2. Dict keyed by model string with 'default' fallback:
        WORKFLOW_ACTIONS_CONFIG = {
            'default': [
                {'action_type': 'after_approve', 'function_path': '...', ...}
            ],
            'crm.Opportunity': [
                {'action_type': 'after_approve', 'function_path': 'myapp.actions.opportunity_approved', ...}
            ],
        }

    Returns:
        The raw config value (list or dict), or None if not set.
    """
    from django.conf import settings as django_settings

    return getattr(django_settings, "WORKFLOW_ACTIONS_CONFIG", None)


def get_transition_actor_settings(model_or_obj=None):
    """
    Get settings used to resolve who may perform status transitions.

    These settings intentionally describe where to find users on the target object,
    because every project names ownership, assignment, teams, and departments
    differently.
    """
    workflow_settings = get_workflow_settings()
    configuration = workflow_settings.get("TRANSITION_ACTORS", {})
    if not configuration or not model_or_obj:
        return configuration

    # Backward-compatible flat configuration.
    if any(str(key).isupper() for key in configuration):
        return configuration

    if isinstance(model_or_obj, str):
        model_string = model_or_obj
    else:
        if not hasattr(model_or_obj, "_meta"):
            return configuration.get("default", {})
        model_string = getattr(
            model_or_obj._meta,
            "label",
            f"{model_or_obj._meta.app_label}.{model_or_obj.__class__.__name__}",
        )

    resolved = dict(configuration.get("default") or {})
    model_config = configuration.get(model_string)
    if model_config is None:
        normalized = model_string.lower()
        model_config = next(
            (
                value
                for key, value in configuration.items()
                if key != "default" and key.lower() == normalized
            ),
            None,
        )
    if model_config:
        resolved.update(model_config)
    return resolved


def get_default_status_workflows():
    """Return model-specific default status workflow definitions."""
    return get_workflow_settings().get("DEFAULT_STATUS_WORKFLOWS", {})


def get_default_status_workflow_config(model_string: str) -> Optional[dict]:
    """Resolve a default status workflow config using exact/default fallback."""
    configurations = get_default_status_workflows()
    if model_string in configurations:
        return configurations[model_string]

    normalized = model_string.lower()
    for configured_model, configuration in configurations.items():
        if configured_model != "default" and configured_model.lower() == normalized:
            return configuration
    return configurations.get("default")


def get_actions_config_for_model(model_string: str) -> Optional[list]:
    """
    Resolve action config list for a model string.

    Handles both the old flat-list format and the new dict format with
    model-specific keys and 'default' fallback.

    Resolution order (for dict format):
        1. Exact model match (e.g. 'crm.Opportunity')
        2. 'default' key
        3. None (nothing configured)

    Args:
        model_string: Model string in 'app_label.ModelName' format

    Returns:
        list of action config dicts, or None if nothing configured
    """
    config = get_workflow_actions_config()

    if config is None:
        return None

    # Old flat-list format — return as-is
    if isinstance(config, list):
        return config

    # New dict format — resolve by model key
    if isinstance(config, dict):
        if model_string in config:
            return config[model_string]
        if "default" in config:
            return config["default"]
        return None

    return None


def is_model_workflow_enabled(model_class):
    """
    Check if a model class is enabled for workflow functionality

    Args:
        model_class: Django model class

    Returns:
        bool: True if model is enabled for workflows
    """
    model_string = f"{model_class._meta.app_label}.{model_class.__name__}"
    enabled_models = get_enabled_models()

    # If no specific models are configured, allow all models
    if not enabled_models:
        return True

    return model_string in enabled_models


def validate_workflow_settings():
    """
    Validate workflow settings configuration

    Raises:
        ImproperlyConfigured: If settings are invalid
    """
    workflow_settings = get_workflow_settings()

    # Validate enabled models format
    enabled_models = workflow_settings.get("ENABLED_MODELS", [])
    if enabled_models and not isinstance(enabled_models, list):
        raise ImproperlyConfigured(
            "DJANGO_WORKFLOW_ENGINE['ENABLED_MODELS'] must be a list"
        )

    for model_string in enabled_models:
        if not isinstance(model_string, str) or "." not in model_string:
            raise ImproperlyConfigured(
                f"Invalid model string '{model_string}' in ENABLED_MODELS. "
                "Format should be 'app_label.ModelName'"
            )

    # Validate model workflow mappings
    mappings = workflow_settings.get("MODEL_WORKFLOW_MAPPINGS", {})
    if mappings and not isinstance(mappings, dict):
        raise ImproperlyConfigured(
            "DJANGO_WORKFLOW_ENGINE['MODEL_WORKFLOW_MAPPINGS'] must be a dict"
        )
    for key in mappings:
        if key != "default" and ("." not in key or not isinstance(key, str)):
            raise ImproperlyConfigured(
                f"Invalid key '{key}' in MODEL_WORKFLOW_MAPPINGS. "
                "Format should be 'app_label.ModelName' or 'default'"
            )

    # Validate auto start workflows
    auto_start = workflow_settings.get("AUTO_START_WORKFLOWS", {})
    if auto_start and not isinstance(auto_start, dict):
        raise ImproperlyConfigured(
            "DJANGO_WORKFLOW_ENGINE['AUTO_START_WORKFLOWS'] must be a dict"
        )
    for key in auto_start:
        if key != "default" and ("." not in key or not isinstance(key, str)):
            raise ImproperlyConfigured(
                f"Invalid key '{key}' in AUTO_START_WORKFLOWS. "
                "Format should be 'app_label.ModelName' or 'default'"
            )

    default_status_workflows = workflow_settings.get("DEFAULT_STATUS_WORKFLOWS", {})
    if default_status_workflows and not isinstance(default_status_workflows, dict):
        raise ImproperlyConfigured(
            "DJANGO_WORKFLOW_ENGINE['DEFAULT_STATUS_WORKFLOWS'] must be a dict"
        )
    for key, configuration in default_status_workflows.items():
        if key != "default" and ("." not in key or not isinstance(key, str)):
            raise ImproperlyConfigured(
                f"Invalid key '{key}' in DEFAULT_STATUS_WORKFLOWS. "
                "Format should be 'app_label.ModelName' or 'default'"
            )
        if not isinstance(configuration, dict):
            raise ImproperlyConfigured(
                f"DEFAULT_STATUS_WORKFLOWS['{key}'] must be a dict"
            )
        has_direct_design = bool(configuration.get("statuses"))
        if (
            not configuration.get("factory")
            and not configuration.get("design")
            and not has_direct_design
        ):
            raise ImproperlyConfigured(
                f"DEFAULT_STATUS_WORKFLOWS['{key}'] requires a full flow design, "
                "'design', or 'factory'"
            )

    transition_actors = workflow_settings.get("TRANSITION_ACTORS", {})
    if transition_actors and not isinstance(transition_actors, dict):
        raise ImproperlyConfigured(
            "DJANGO_WORKFLOW_ENGINE['TRANSITION_ACTORS'] must be a dict"
        )
    if transition_actors and not any(str(key).isupper() for key in transition_actors):
        for key, configuration in transition_actors.items():
            if key != "default" and ("." not in key or not isinstance(key, str)):
                raise ImproperlyConfigured(
                    f"Invalid key '{key}' in TRANSITION_ACTORS. "
                    "Format should be 'app_label.ModelName' or 'default'"
                )
            if not isinstance(configuration, dict):
                raise ImproperlyConfigured(f"TRANSITION_ACTORS['{key}'] must be a dict")


# Default settings template for documentation
DEFAULT_SETTINGS = {
    "ENABLED_MODELS": [
        # List of models enabled for workflow functionality
        # Format: 'app_label.ModelName'
        # Example: 'myapp.PurchaseRequest'
    ],
    "DEFAULT_STATUS_FIELD": "workflow_status",
    "DEPARTMENT_MODEL": None,  # Set to 'app_label.ModelName' to map departments to a specific model
    "MODEL_WORKFLOW_MAPPINGS": {
        # Map models to their available workflows
        # 'default': ['generic_approval'],  # Fallback for models without specific mapping
        # 'app_label.ModelName': ['workflow_slug1', 'workflow_slug2']
    },
    "AUTO_START_WORKFLOWS": {
        # Models that auto-start workflows when created
        # 'default': {                          # Fallback for models without specific config
        #     'workflow_slug': 'generic_approval',
        #     'auto_start': True,
        # },
        # 'app_label.ModelName': {
        #     'workflow_slug': 'workflow_name',
        #     'conditions': {}  # Optional conditions
        # }
    },
    "DEFAULT_STATUS_WORKFLOWS": {
        # Create one company-owned status workflow per configured model.
        # 'support.Ticket': {
        #     'status_field': 'status',
        #     'allow_direct_change': False,
        #     'default_status': 'new',
        #     'terminal_statuses': ['closed'],
        #     'workflow': {
        #         'name_en': 'Standard Support Workflow',
        #         'name_ar': 'Standard Support Workflow',
        #     },
        #     'statuses': [
        #         {'code': 'new', 'name_en': 'New', 'name_ar': 'New'},
        #         {'code': 'closed', 'name_en': 'Closed', 'name_ar': 'Closed'},
        #     ],
        #     'transitions': [
        #         {'code': 'close', 'name_en': 'Close', 'from': 'new', 'to': 'closed'},
        #     ],
        #     'company_field': 'company',
        #     'auto_start': True,
        # }
    },
    "PERMISSIONS": {
        "REQUIRE_PERMISSION_TO_START": False,
        "REQUIRE_PERMISSION_TO_APPROVE": False,
        "DEFAULT_PERMISSIONS": {
            "can_start_workflow": "workflow.start_workflow",
            "can_approve": "workflow.approve_workflow",
            "can_reject": "workflow.reject_workflow",
            "can_delegate": "workflow.delegate_workflow",
        },
    },
    "TRANSITION_ACTORS": {
        # Model-specific field/function discovery for transition authorization.
        "default": {
            "OWNER_FIELD": "created_by",
            "MANAGER_FIELD": "manager",
        },
        # "support.Ticket": {
        #     "ASSIGNED_USER_FUNCTION": "support.workflow_actors.get_assigned_user",
        # },
        # "tasks.Task": {
        #     "ASSIGNED_USER_FIELD": "assignee",
        # },
    },
}

# WORKFLOW_ACTIONS_CONFIG is a separate top-level Django setting (not inside DJANGO_WORKFLOW_ENGINE).
#
# Supports two formats:
#
# 1) Flat list (backward compatible — applies to all models):
#    WORKFLOW_ACTIONS_CONFIG = [
#        {'action_type': 'after_approve', 'function_path': 'myapp.actions.send_approval', ...},
#    ]
#
# 2) Dict keyed by model string with 'default' fallback:
#    WORKFLOW_ACTIONS_CONFIG = {
#        'default': [
#            {'action_type': 'after_approve', 'function_path': 'myapp.actions.generic_approval', ...},
#        ],
#        'crm.Opportunity': [
#            {'action_type': 'after_approve', 'function_path': 'myapp.actions.opportunity_approved', ...},
#        ],
#    }
#
# Resolution order: exact model match → 'default' key → None (no actions).
