# Generated manually for django_workflow_engine

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_workflow_engine", "0003_add_is_hidden_to_workflow"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowconfiguration",
            name="completion_status_value",
            field=models.CharField(
                blank=True,
                help_text="Value to set in the status_field when workflow completes successfully (e.g., 'completed', 'won', 'closed')",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="workflowconfiguration",
            name="rejection_status_value",
            field=models.CharField(
                blank=True,
                help_text="Value to set in the status_field when workflow is rejected (e.g., 'rejected', 'cancelled', 'lost')",
                max_length=100,
            ),
        ),
    ]
