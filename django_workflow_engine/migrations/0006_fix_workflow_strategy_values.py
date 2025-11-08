# Generated migration to fix incorrect strategy values from 0005

from django.db import migrations


def fix_workflow_strategies(apps, schema_editor):
    """Fix workflows that were incorrectly set to strategy=3.

    The migration 0005 incorrectly set default=3 thinking it was
    WORKFLOW_PIPELINE_STAGE, but 3 is actually WORKFLOW_ONLY.

    This data migration fixes existing workflows by:
    - Setting strategy=1 (WORKFLOW_PIPELINE_STAGE) for workflows that have pipelines/stages
    - Leaving strategy=3 for workflows that genuinely have no pipelines
    """
    WorkFlow = apps.get_model("django_workflow_engine", "WorkFlow")
    Pipeline = apps.get_model("django_workflow_engine", "Pipeline")

    for workflow in WorkFlow.objects.all():
        # If workflow has pipelines, it should be strategy 1 or 2, not 3
        if workflow.pipelines.exists():
            # Check if any pipeline has stages
            has_stages = any(
                pipeline.stages.exists() for pipeline in workflow.pipelines.all()
            )

            if has_stages:
                # Has pipelines and stages -> Strategy 1 (WORKFLOW_PIPELINE_STAGE)
                workflow.strategy = 1
            else:
                # Has pipelines but no stages -> Strategy 2 (WORKFLOW_PIPELINE)
                workflow.strategy = 2

            workflow.save(update_fields=["strategy"])
            print(
                f"Fixed workflow {workflow.id} ('{workflow.name_en}') - set strategy to {workflow.strategy}"
            )
        else:
            # No pipelines -> Strategy 3 (WORKFLOW_ONLY) is correct
            # Only update if it's not already set to 3
            if workflow.strategy != 3:
                workflow.strategy = 3
                workflow.save(update_fields=["strategy"])
                print(
                    f"Fixed workflow {workflow.id} ('{workflow.name_en}') - set strategy to 3 (no pipelines)"
                )


def reverse_fix(apps, schema_editor):
    """Reverse migration - set all workflows back to strategy=3 (the old incorrect default)"""
    WorkFlow = apps.get_model("django_workflow_engine", "WorkFlow")
    WorkFlow.objects.all().update(strategy=3)


class Migration(migrations.Migration):

    dependencies = [
        ("django_workflow_engine", "0005_add_workflow_strategy_system"),
    ]

    operations = [
        migrations.RunPython(fix_workflow_strategies, reverse_fix),
    ]
