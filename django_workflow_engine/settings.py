"""
Django Workflow Engine Settings Configuration
"""

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

    Example in settings.py:
        DJANGO_WORKFLOW_ENGINE = {
            'MODEL_WORKFLOW_MAPPINGS': {
                'myapp.PurchaseRequest': ['purchase_approval', 'emergency_approval'],
                'crm.Opportunity': ['sales_process', 'enterprise_sales'],
                'support.Ticket': ['standard_support', 'escalation_process'],
                'hr.LeaveRequest': ['leave_approval']
            }
        }
    """
    workflow_settings = get_workflow_settings()
    return workflow_settings.get("MODEL_WORKFLOW_MAPPINGS", {})


def get_auto_start_workflows():
    """
    Get models that should auto-start workflows when created

    Returns:
        dict: Model strings mapped to their auto-start configuration

    Example in settings.py:
        DJANGO_WORKFLOW_ENGINE = {
            'AUTO_START_WORKFLOWS': {
                'myapp.PurchaseRequest': {
                    'workflow_slug': 'purchase_approval',
                    'conditions': {
                        'amount__gte': 1000  # Only auto-start for amounts >= 1000
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

    # Validate auto start workflows
    auto_start = workflow_settings.get("AUTO_START_WORKFLOWS", {})
    if auto_start and not isinstance(auto_start, dict):
        raise ImproperlyConfigured(
            "DJANGO_WORKFLOW_ENGINE['AUTO_START_WORKFLOWS'] must be a dict"
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
        # 'app_label.ModelName': ['workflow_slug1', 'workflow_slug2']
    },
    "AUTO_START_WORKFLOWS": {
        # Models that auto-start workflows when created
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
