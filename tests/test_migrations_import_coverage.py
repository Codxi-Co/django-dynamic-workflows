"""Import migration modules so coverage accounts for their declarations."""

import importlib

from django.test import SimpleTestCase


class MigrationImportCoverageTest(SimpleTestCase):
    def test_workflow_engine_migrations_import(self):
        migration_modules = [
            "0001_initial",
            "0002_alter_workflow_options_and_more",
            "0003_add_is_hidden_to_workflow",
            "0004_add_status_values_to_workflowconfiguration",
            "0005_add_workflow_strategy_system",
            "0006_fix_workflow_strategy_values",
            "0007_add_enhanced_role_strategies",
            "0008_status_workflows",
        ]

        for module_name in migration_modules:
            with self.subTest(module=module_name):
                module = importlib.import_module(
                    f"django_workflow_engine.migrations.{module_name}"
                )
                self.assertTrue(hasattr(module, "Migration"))
