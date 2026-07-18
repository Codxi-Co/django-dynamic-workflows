"""Django Workflow Engine Package.

A comprehensive Django package for implementing dynamic multi-step workflows with approval flows.
Combines workflow management (Pipeline, Stage) with approval workflow functionality.
"""

__version__ = "1.9.0"
__author__ = "Mohamed Ibrahim"
__email__ = "info@codxi.com"

default_app_config = "django_workflow_engine.apps.WorkflowEngineConfig"


def _patch_role_selection_strategy_compat():
    """Expose newer role strategy constants when older dependency lacks them."""
    try:
        from approval_workflow.choices import RoleSelectionStrategy
    except Exception:
        return

    for name, value in {
        "QUORUM": "quorum",
        "MAJORITY": "majority",
        "PERCENTAGE": "percentage",
        "HIERARCHY_UP": "hierarchy_up",
        "HIERARCHY_CHAIN": "hierarchy_chain",
    }.items():
        if not hasattr(RoleSelectionStrategy, name):
            setattr(RoleSelectionStrategy, name, value)


_patch_role_selection_strategy_compat()
