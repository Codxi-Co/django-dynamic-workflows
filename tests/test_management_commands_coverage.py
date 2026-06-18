"""Coverage for package management commands."""

import argparse
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase


class CleanupWorkflowsCommandTest(SimpleTestCase):
    def _stats(self, orphaned_actions=0, completed_actions=0):
        return {
            "total_attachments": 10,
            "completed_attachments": 4,
            "rejected_attachments": 1,
            "in_progress_attachments": 5,
            "cloned_workflows": {
                "total": 3,
                "with_completed_attachments": 2,
            },
            "cloned_actions": {
                "total": 12,
                "from_completed_workflows": completed_actions,
            },
            "cleanable_by_age": {
                "older_than_30_days": 2,
                "older_than_90_days": 1,
                "older_than_365_days": 0,
            },
            "total_actions": 20,
            "orphaned_actions": orphaned_actions,
        }

    def test_cleanup_command_argument_registration_and_percent(self):
        from django_workflow_engine.management.commands.cleanup_workflows import Command

        parser = argparse.ArgumentParser()
        command = Command()
        command.add_arguments(parser)
        options = parser.parse_args(
            [
                "--days",
                "30",
                "--dry-run",
                "--include-orphaned-actions",
                "--status",
                "completed",
            ]
        )

        self.assertEqual(options.days, 30)
        self.assertTrue(options.dry_run)
        self.assertTrue(options.include_orphaned_actions)
        self.assertEqual(options.status, ["completed"])
        self.assertEqual(command._percent(0, 0), "0%")
        self.assertEqual(command._percent(1, 4), "25.0%")

    def test_cleanup_command_stats_paths(self):
        out = StringIO()
        with patch(
            "django_workflow_engine.management.commands.cleanup_workflows.get_cleanup_statistics",
            return_value=self._stats(orphaned_actions=0, completed_actions=0),
        ):
            call_command("cleanup_workflows", "--stats", stdout=out)
        self.assertIn("No cloned actions to clean up", out.getvalue())

        out = StringIO()
        with patch(
            "django_workflow_engine.management.commands.cleanup_workflows.get_cleanup_statistics",
            return_value=self._stats(orphaned_actions=2, completed_actions=101),
        ):
            call_command("cleanup_workflows", "--stats", stdout=out)
        output = out.getvalue()
        self.assertIn("Consider running", output)
        self.assertIn("Clean up orphaned actions", output)

    def test_cleanup_command_dry_run_and_orphaned_paths(self):
        out = StringIO()
        with (
            patch(
                "django_workflow_engine.management.commands.cleanup_workflows.cleanup_completed_workflow_actions",
                return_value={"actions_deleted": 3, "workflows_processed": 2},
            ) as completed,
            patch(
                "django_workflow_engine.management.commands.cleanup_workflows.cleanup_orphaned_workflow_actions",
                return_value={"actions_deleted": 4},
            ) as orphaned,
        ):
            call_command(
                "cleanup_workflows",
                "--dry-run",
                "--days",
                "30",
                "--include-orphaned-actions",
                stdout=out,
            )

        self.assertEqual(completed.call_args.kwargs["older_than_days"], 30)
        self.assertTrue(completed.call_args.kwargs["dry_run"])
        orphaned.assert_called_once_with(dry_run=True)
        output = out.getvalue()
        self.assertIn("DRY RUN", output)
        self.assertIn("Would delete 3", output)
        self.assertIn("Would delete 4 orphaned", output)

    def test_cleanup_command_real_delete_and_noop_paths(self):
        out = StringIO()
        with (
            patch(
                "django_workflow_engine.management.commands.cleanup_workflows.cleanup_completed_workflow_actions",
                return_value={"actions_deleted": 3, "workflows_processed": 2},
            ),
            patch(
                "django_workflow_engine.management.commands.cleanup_workflows.cleanup_orphaned_workflow_actions",
                return_value={"actions_deleted": 0},
            ),
        ):
            call_command("cleanup_workflows", "--include-orphaned-actions", stdout=out)

        output = out.getvalue()
        self.assertIn("CLEANUP MODE", output)
        self.assertIn("Deleted 3", output)
        self.assertIn("No orphaned actions", output)
        self.assertIn("Cleanup complete", output)

        out = StringIO()
        with patch(
            "django_workflow_engine.management.commands.cleanup_workflows.cleanup_completed_workflow_actions",
            return_value={"actions_deleted": 0, "workflows_processed": 0},
        ):
            call_command("cleanup_workflows", stdout=out)
        self.assertIn("No cloned workflow actions", out.getvalue())


class CompileMessagesCommandTest(SimpleTestCase):
    def test_compilemessages_argument_registration(self):
        from django_workflow_engine.management.commands.compilemessages import Command

        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        options = parser.parse_args(["--locale", "en", "-l", "ar"])
        self.assertEqual(options.locale, ["en", "ar"])

    def test_compilemessages_success_warning_error_and_missing_file(self):
        out = StringIO()

        def exists(path):
            if path.endswith("en/LC_MESSAGES/django.po"):
                return True
            if path.endswith("en/LC_MESSAGES/django.mo"):
                return True
            if path.endswith("ar/LC_MESSAGES/django.po"):
                return True
            if path.endswith("ar/LC_MESSAGES/django.mo"):
                return False
            return False

        with (
            patch(
                "django_workflow_engine.management.commands.compilemessages.os.path.exists",
                side_effect=exists,
            ),
            patch(
                "django_workflow_engine.management.commands.compilemessages.call_command"
            ) as compile_call,
        ):
            call_command(
                "compilemessages", "--locale", "en", "--locale", "ar", stdout=out
            )

        self.assertEqual(compile_call.call_count, 2)
        output = out.getvalue()
        self.assertIn("Successfully compiled en", output)
        self.assertIn("not found after compilation", output)

        out = StringIO()
        with patch(
            "django_workflow_engine.management.commands.compilemessages.os.path.exists",
            return_value=False,
        ):
            call_command("compilemessages", "--locale", "fr", stdout=out)
        self.assertIn("No translation file found", out.getvalue())

        out = StringIO()
        with (
            patch(
                "django_workflow_engine.management.commands.compilemessages.os.path.exists",
                return_value=True,
            ),
            patch(
                "django_workflow_engine.management.commands.compilemessages.call_command",
                side_effect=RuntimeError("compile failed"),
            ),
        ):
            call_command("compilemessages", "--locale", "en", stdout=out)
        self.assertIn("Error compiling en messages", out.getvalue())


class SetupWorkflowsCommandTest(TestCase):
    def test_setup_workflows_argument_registration(self):
        from django_workflow_engine.management.commands.setup_workflows import Command

        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        options = parser.parse_args(
            ["--company-id", "1", "--user-id", "2", "--department-id", "3"]
        )
        self.assertEqual(options.company_id, 1)
        self.assertEqual(options.user_id, 2)
        self.assertEqual(options.department_id, 3)

    def test_setup_workflows_success_and_error_paths(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(username="setup-user", password="pass")
        company = SimpleNamespace(id=10)
        department = SimpleNamespace(id=20)
        pipeline = SimpleNamespace(
            name_en="Pipeline",
            stages=SimpleNamespace(count=Mock(return_value=2)),
        )
        workflow = SimpleNamespace(
            id=30,
            name_en="Created Flow",
            pipelines=SimpleNamespace(all=Mock(return_value=[pipeline])),
        )

        def get_model(app_label, model_name):
            if app_label == "companies":
                return SimpleNamespace(
                    objects=SimpleNamespace(get=Mock(return_value=company))
                )
            if app_label == "common":
                return SimpleNamespace(
                    objects=SimpleNamespace(get=Mock(return_value=department))
                )
            raise LookupError(app_label, model_name)

        out = StringIO()
        with (
            patch(
                "django.apps.apps.get_model",
                side_effect=get_model,
                create=True,
            ),
            patch(
                "django_workflow_engine.management.commands.setup_workflows.User.objects.get",
                return_value=user,
            ),
            patch(
                "django_workflow_engine.management.commands.setup_workflows.create_workflow",
                return_value=workflow,
            ) as create_workflow,
        ):
            call_command(
                "setup_workflows",
                "--company-id",
                "10",
                "--user-id",
                str(user.id),
                "--department-id",
                "20",
                stdout=out,
            )

        self.assertEqual(create_workflow.call_count, 2)
        self.assertIn("Successfully created 2 sample workflows", out.getvalue())

        with patch(
            "django.apps.apps.get_model",
            side_effect=RuntimeError("lookup failed"),
            create=True,
        ):
            with self.assertRaises(RuntimeError):
                call_command(
                    "setup_workflows",
                    "--company-id",
                    "10",
                    "--user-id",
                    str(user.id),
                    "--department-id",
                    "20",
                    stdout=StringIO(),
                )
