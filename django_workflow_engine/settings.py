"""
Django Workflow Engine Settings Configuration
"""

from typing import Optional

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def get_workflow_settings():
    """Get workflow engine settings with defaults"""
    return getattr(settings, "DJANGO_WORKFLOW_ENGINE", {})


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
