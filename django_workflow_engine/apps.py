"""Django app configuration for workflow engine."""

from django.apps import AppConfig


class WorkflowEngineConfig(AppConfig):
    """Configuration for the workflow engine Django app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "django_workflow_engine"
    verbose_name = "Django Workflow Engine"

    def ready(self):
        """Perform app initialization."""
        # Import signals or other setup code here if needed
        pass
