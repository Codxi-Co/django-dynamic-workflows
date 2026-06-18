"""Focused coverage for small production branches not reached by workflow tests."""

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.test import TestCase, override_settings
from django.test.client import RequestFactory

from django_workflow_engine import action_handlers, enhanced_logging
from django_workflow_engine.action_executor import (
    _execute_action_securely,
    execute_custom_action,
    execute_workflow_actions,
)
from django_workflow_engine.action_management import (
    clone_workflow_actions,
    create_custom_workflow_actions,
    create_default_workflow_actions,
)
from django_workflow_engine.action_registry import (
    ActionNotRegisteredError,
    WorkflowActionRegistry,
)
from django_workflow_engine.admin import (
    ModelStatusConfigurationAdmin,
    StatusAttachmentAdmin,
    StatusHistoryAdmin,
    WorkflowActionAdmin,
    WorkflowAttachmentAdmin,
    WorkflowConfigurationAdmin,
)
from django_workflow_engine.choices import WorkflowAttachmentStatus
from django_workflow_engine.cleanup import cleanup_orphaned_workflow_actions
from django_workflow_engine.constants import validate_json_size
from django_workflow_engine.example_actions import update_object_status
from django_workflow_engine.handlers import (
    WorkflowApprovalHandler,
    get_handler_for_instance,
)
from django_workflow_engine.management.commands.cleanup_workflows import (
    Command as CleanupCommand,
)
from django_workflow_engine.models import WorkflowAction
from django_workflow_engine.notifications import (
    get_workflow_email_context,
    send_bulk_workflow_emails,
    send_workflow_email,
)
from django_workflow_engine.recipient_resolver import _resolve_creator, _resolve_user_id
from django_workflow_engine.settings import (
    _import_setting,
    get_actions_config_for_model,
    get_default_status_workflow_config,
    get_default_workflow_status_field,
    get_status_api_viewset_mixins,
    get_transition_actor_settings,
    get_workflow_permissions,
    validate_workflow_settings,
)
from django_workflow_engine.signals import auto_cleanup_completed_workflow_actions
from django_workflow_engine.translation_utils import log_workflow_event
from tests.factories import WorkFlowFactory, WorkflowTestModelFactory

User = get_user_model()


def discover_test_handler(instance):
    return SimpleNamespace(instance=instance)


class SmallPureBranchCoverageTest(TestCase):
    def test_example_action_handlers_log_and_return_false(self):
        handlers = [
            action_handlers.send_approval_notification,
            action_handlers.send_rejection_notification,
            action_handlers.send_resubmission_notification,
            action_handlers.send_delegation_notification,
            action_handlers.send_stage_move_notification,
        ]

        with self.assertLogs(action_handlers.logger, level="WARNING") as captured:
            results = [handler(None, {}) for handler in handlers]

        self.assertEqual(results, [False] * len(handlers))
        self.assertEqual(len(captured.output), len(handlers))

    def test_validate_json_size_covers_raise_log_and_serialization_error(self):
        with self.assertRaises(ValidationError):
            validate_json_size(
                {"large": "value"},
                max_size=1,
                field_name="metadata",
                raise_error=True,
            )

        with self.assertLogs("django_workflow_engine.constants", level="WARNING"):
            self.assertFalse(
                validate_json_size(
                    {"large": "value"},
                    max_size=1,
                    field_name="metadata",
                    raise_error=False,
                )
            )

        with self.assertLogs("django_workflow_engine.constants", level="ERROR"):
            self.assertFalse(
                validate_json_size(
                    {"bad": object()},
                    max_size=100,
                    field_name="metadata",
                )
            )

    def test_registry_get_action_and_legacy_config_validation(self):
        registry = WorkflowActionRegistry()

        @registry.register("send_email")
        def send_email(*args, **kwargs):
            return True

        self.assertIs(registry.get_action("send_email"), send_email)
        self.assertTrue(registry.validate_action_config("send_email"))
        self.assertTrue(registry.validate_action_config("project.actions.send_email"))
        self.assertFalse(registry.validate_action_config("project.actions.missing"))

    def test_translation_event_uses_default_logger(self):
        with patch("django_workflow_engine.translation_utils.logger") as default_logger:
            log_workflow_event("created", {"workflow_id": 1, "name": "Test"})

        default_logger.info.assert_called_once()

    def test_recipient_fallback_branches(self):
        self.assertIsNone(_resolve_creator(SimpleNamespace()))

        with patch(
            "django_workflow_engine.recipient_resolver.User.objects.get",
            return_value=SimpleNamespace(),
        ):
            with self.assertLogs(
                "django_workflow_engine.recipient_resolver", level="WARNING"
            ):
                self.assertIsNone(_resolve_user_id(123))

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "STATUS_API_VIEWSET_MIXINS": "django.views.View",
            "PERMISSIONS": {"enabled": True},
            "DEFAULT_STATUS_WORKFLOWS": {
                "Support.Ticket": {"statuses": [{"code": "new"}]},
                "default": {"statuses": [{"code": "fallback"}]},
            },
            "TRANSITION_ACTORS": {
                "default": {"OWNER_FIELD": "created_by"},
                "Support.Ticket": {"ASSIGNED_USER_FIELD": "assigned_to"},
            },
        }
    )
    def test_settings_resolution_and_import_paths(self):
        self.assertEqual(len(get_status_api_viewset_mixins()), 1)
        self.assertEqual(get_workflow_permissions(), {"enabled": True})
        self.assertEqual(get_default_workflow_status_field(), "workflow_status")
        self.assertEqual(
            get_default_status_workflow_config("support.ticket")["statuses"][0]["code"],
            "new",
        )
        self.assertEqual(
            get_default_status_workflow_config("unknown.Model")["statuses"][0]["code"],
            "fallback",
        )
        self.assertEqual(
            get_transition_actor_settings(SimpleNamespace()),
            {"OWNER_FIELD": "created_by"},
        )
        self.assertEqual(
            get_transition_actor_settings("support.ticket"),
            {
                "OWNER_FIELD": "created_by",
                "ASSIGNED_USER_FIELD": "assigned_to",
            },
        )

        with self.assertRaisesMessage(Exception, "Could not import"):
            _import_setting("missing.module.Class")

        with override_settings(WORKFLOW_ACTIONS_CONFIG="invalid"):
            self.assertIsNone(get_actions_config_for_model("support.Ticket"))

    def test_invalid_status_and_actor_settings_are_rejected(self):
        invalid_settings = [
            {"DEFAULT_STATUS_WORKFLOWS": ["invalid"]},
            {"DEFAULT_STATUS_WORKFLOWS": {"invalid": {"statuses": [{}]}}},
            {"DEFAULT_STATUS_WORKFLOWS": {"app.Model": []}},
            {"TRANSITION_ACTORS": ["invalid"]},
            {"TRANSITION_ACTORS": {"invalid": {}}},
            {"TRANSITION_ACTORS": {"app.Model": []}},
        ]
        for configuration in invalid_settings:
            with self.subTest(configuration=configuration):
                with override_settings(DJANGO_WORKFLOW_ENGINE=configuration):
                    with self.assertRaises(Exception):
                        validate_workflow_settings()

    def test_secure_action_execution_direct_legacy_and_missing(self):
        registry = MagicMock()
        registry.is_registered.side_effect = lambda name: name in {
            "direct",
            "legacy",
        }
        registry.execute_action.return_value = True

        with patch("django_workflow_engine.action_executor.registry", registry):
            self.assertTrue(
                _execute_action_securely("direct", object(), {}, {}, "source", "type")
            )
            self.assertTrue(
                _execute_action_securely(
                    "project.actions.legacy",
                    object(),
                    {},
                    {},
                    "source",
                    "type",
                )
            )
            with self.assertRaises(ActionNotRegisteredError):
                _execute_action_securely(
                    "project.actions.missing",
                    object(),
                    {},
                    {},
                    "source",
                    "type",
                )

    def test_execute_workflow_actions_covers_all_result_paths(self):
        attachment = SimpleNamespace(
            workflow=SimpleNamespace(id=1, name_en="Workflow"),
            current_pipeline=SimpleNamespace(id=2),
            current_stage=SimpleNamespace(id=3),
            content_type=None,
        )
        actions = [
            SimpleNamespace(
                id=1,
                is_active=False,
                function_path="inactive",
                parameters={},
            ),
            SimpleNamespace(
                id=2, is_active=True, function_path="secure_true", parameters={}
            ),
            SimpleNamespace(
                id=None, is_active=True, function_path="secure_false", parameters={}
            ),
            SimpleNamespace(
                id=4, is_active=True, function_path="legacy_true", parameters={}
            ),
            SimpleNamespace(
                id=None, is_active=True, function_path="legacy_false", parameters={}
            ),
            SimpleNamespace(
                id=6, is_active=True, function_path="legacy_import", parameters={}
            ),
            SimpleNamespace(
                id=7, is_active=True, function_path="legacy_error", parameters={}
            ),
            SimpleNamespace(
                id=8, is_active=True, function_path="secure_error", parameters={}
            ),
        ]
        secure_results = [
            True,
            False,
            ActionNotRegisteredError(),
            ActionNotRegisteredError(),
            ActionNotRegisteredError(),
            ActionNotRegisteredError(),
            RuntimeError("secure failed"),
        ]

        def import_handler(path):
            if path == "legacy_true":
                return lambda **kwargs: True
            if path == "legacy_false":
                return lambda **kwargs: False
            if path == "legacy_import":
                raise ImportError("missing")
            return lambda **kwargs: (_ for _ in ()).throw(RuntimeError("failed"))

        with override_settings(WORKFLOW_DISABLE_EMAILS=False):
            with (
                patch(
                    "django_workflow_engine.action_executor.get_effective_actions",
                    return_value=actions,
                ),
                patch(
                    "django_workflow_engine.action_executor._execute_action_securely",
                    side_effect=secure_results,
                ),
                patch(
                    "django_workflow_engine.action_executor.import_string",
                    side_effect=import_handler,
                ),
            ):
                result = execute_workflow_actions("after_approve", attachment)

        self.assertEqual(
            result,
            {"executed": 7, "succeeded": 2, "failed": 5, "skipped": 1},
        )

    @override_settings(WORKFLOW_DISABLE_EMAILS=True)
    def test_execute_workflow_actions_disabled_and_missing_attachment(self):
        empty = {"executed": 0, "succeeded": 0, "failed": 0, "skipped": 0}
        self.assertEqual(execute_workflow_actions("event", object()), empty)

        with override_settings(WORKFLOW_DISABLE_EMAILS=False):
            self.assertEqual(execute_workflow_actions("event", None), empty)

    def test_execute_custom_action_covers_registry_and_legacy_paths(self):
        attachment = object()

        with patch(
            "django_workflow_engine.action_executor._execute_action_securely",
            return_value=True,
        ):
            self.assertTrue(execute_custom_action(attachment, "registered"))
        with patch(
            "django_workflow_engine.action_executor._execute_action_securely",
            return_value=False,
        ):
            self.assertFalse(execute_custom_action(attachment, "registered"))

        cases = [
            (lambda **kwargs: True, True),
            (lambda **kwargs: False, False),
            (ImportError("missing"), False),
            (lambda **kwargs: (_ for _ in ()).throw(RuntimeError("failed")), False),
        ]
        for imported, expected in cases:
            with self.subTest(imported=imported):
                with (
                    patch(
                        "django_workflow_engine.action_executor._execute_action_securely",
                        side_effect=ActionNotRegisteredError(),
                    ),
                    patch(
                        "django_workflow_engine.action_executor.import_string",
                        side_effect=(
                            imported if isinstance(imported, Exception) else None
                        ),
                        return_value=(
                            None if isinstance(imported, Exception) else imported
                        ),
                    ),
                ):
                    self.assertEqual(
                        execute_custom_action(attachment, "legacy.path"),
                        expected,
                    )

        with patch(
            "django_workflow_engine.action_executor._execute_action_securely",
            side_effect=RuntimeError("secure failed"),
        ):
            self.assertFalse(execute_custom_action(attachment, "registered"))
        self.assertFalse(execute_custom_action(None, "registered"))

    def test_action_management_error_and_scope_paths(self):
        self.assertEqual(create_custom_workflow_actions([{}]), [])

        workflow = SimpleNamespace(name_en="Workflow")
        pipeline = SimpleNamespace(name_en="Pipeline")
        stage = SimpleNamespace(name_en="Stage")
        with patch(
            "django_workflow_engine.action_management.WorkflowAction.objects.create",
            side_effect=RuntimeError("create failed"),
        ):
            self.assertEqual(
                create_custom_workflow_actions(
                    [{"action_type": "event"}],
                    workflow=workflow,
                ),
                [],
            )
            self.assertEqual(
                create_default_workflow_actions(
                    workflow,
                    pipeline=pipeline,
                    force=True,
                ),
                [],
            )
            self.assertEqual(
                create_default_workflow_actions(
                    workflow,
                    stage=stage,
                    force=True,
                ),
                [],
            )

    def test_clone_workflow_actions_handles_mapping_and_create_failures(self):
        source = SimpleNamespace()
        target = SimpleNamespace()
        action = SimpleNamespace(
            id=1,
            action_type="event",
            function_path="tests.action",
            condition_function="",
            failure_policy="continue",
            is_active=True,
            parameters={},
            order=1,
        )
        target_pipeline = SimpleNamespace(
            stages=SimpleNamespace(all=lambda: [SimpleNamespace()])
        )
        filters = [
            [action],
            [action],
            [action],
        ]

        with (
            patch(
                "django_workflow_engine.action_management.WorkflowAction.objects.filter",
                side_effect=filters,
            ),
            patch(
                "django_workflow_engine.action_management.WorkflowAction.objects.create",
                side_effect=RuntimeError("clone failed"),
            ),
        ):
            result = clone_workflow_actions(
                source,
                target,
                pipeline_mapping={
                    1: {"created_pipeline": None},
                    2: {
                        "created_pipeline": target_pipeline,
                        "stages": [SimpleNamespace(id=3)],
                    },
                },
            )

        self.assertEqual(result, {"workflow": 0, "pipeline": 0, "stage": 0})

    @override_settings(
        WORKFLOW_HANDLER_DISCOVERY_FUNCTION=(
            "tests.test_remaining_small_module_coverage.discover_test_handler"
        )
    )
    def test_custom_handler_discovery_success_and_failure(self):
        instance = SimpleNamespace(
            flow=SimpleNamespace(id=1, target=None),
        )
        handler = get_handler_for_instance(instance)
        self.assertIs(handler.instance, instance)

        with override_settings(
            WORKFLOW_HANDLER_DISCOVERY_FUNCTION="missing.module.function"
        ):
            self.assertIsNone(get_handler_for_instance(instance))

    def test_workflow_handler_aliases_and_exception_paths(self):
        target = SimpleNamespace(
            pk=1,
            _meta=SimpleNamespace(label="tests.Target"),
        )
        handler = WorkflowApprovalHandler(target)
        approval = SimpleNamespace(
            id=2,
            flow_id=3,
            action_user=self.user if hasattr(self, "user") else None,
            comment="reason",
            extra_fields={},
            assigned_to=None,
        )

        with patch.object(handler, "after_approve") as after_approve:
            handler.on_approve(approval)
            after_approve.assert_called_once_with(approval)

        with patch.object(handler, "after_resubmission") as after_resubmission:
            handler.on_resubmission(approval)
            after_resubmission.assert_called_once_with(approval)

        with (
            patch(
                "django_workflow_engine.services.get_workflow_attachment",
                return_value=None,
            ),
            patch(
                "django_workflow_engine.services.move_to_next_stage",
                side_effect=RuntimeError("move failed"),
            ),
        ):
            with self.assertRaisesMessage(RuntimeError, "move failed"):
                handler.on_final_approve(approval)

        with patch(
            "django_workflow_engine.services.get_workflow_attachment",
            return_value=None,
        ):
            handler.after_resubmission(approval)
            handler.after_delegate(approval)

    def test_status_rejection_resolves_explicit_reject_status(self):
        from django_workflow_engine.choices import WorkflowStrategy

        target = SimpleNamespace(pk=1, _meta=SimpleNamespace(label="tests.Target"))
        handler = WorkflowApprovalHandler(target)
        attachment = MagicMock()
        attachment.workflow.strategy = WorkflowStrategy.STATUS_GRAPH
        attachment.pending_transition_id = 9
        attachment.metadata = {
            "_status_transition_rejection": {
                "reject_to_status_id": 5,
                "metadata": {"evidence": "file"},
            }
        }
        approval = SimpleNamespace(
            id=2,
            flow_id=3,
            action_user=None,
            comment="reason",
        )
        reject_status = object()

        with (
            patch(
                "django_workflow_engine.services.get_workflow_attachment",
                return_value=attachment,
            ),
            patch(
                "django_workflow_engine.models.Status.objects.filter"
            ) as status_filter,
            patch(
                "django_workflow_engine.services.reject_pending_transition"
            ) as reject,
        ):
            status_filter.return_value.first.return_value = reject_status
            handler.after_reject(approval)

        reject.assert_called_once()
        self.assertIs(reject.call_args.kwargs["reject_to_status"], reject_status)

    def test_handler_rejection_exception_is_reraised(self):
        target = SimpleNamespace(pk=1, _meta=SimpleNamespace(label="tests.Target"))
        handler = WorkflowApprovalHandler(target)
        with patch(
            "django_workflow_engine.services.get_workflow_attachment",
            side_effect=RuntimeError("lookup failed"),
        ):
            with self.assertRaisesMessage(RuntimeError, "lookup failed"):
                handler.after_reject(SimpleNamespace())

    def test_enhanced_logging_all_levels_and_context_types(self):
        structured = enhanced_logging.StructuredLogger("tests.structured")
        model = SimpleNamespace(
            pk=4,
            _meta=SimpleNamespace(label="tests.Model"),
        )
        with patch.object(structured, "logger") as logger:
            structured.info("custom", none=None, enabled=True, model=model)
            structured.debug("custom", enabled=False)
            structured.warning("warning", value=1)
            structured.error("error", value="x")

        logger.info.assert_called_once()
        logger.debug.assert_called_once()
        logger.warning.assert_called_once()
        logger.error.assert_called_once()

        with patch.object(enhanced_logging.StructuredLogger, "info") as info:
            enhanced_logging.log_workflow_event("workflow_created", workflow_id=1)
            info.assert_called_once()

        user = SimpleNamespace(id=5, username="user")
        with patch.object(enhanced_logging, "log_workflow_event") as event:
            enhanced_logging.log_workflow_event_with_user(
                "stage_approved",
                user,
                stage=2,
            )
            self.assertEqual(event.call_args.kwargs["user_id"], 5)

        with patch.object(enhanced_logging.StructuredLogger, "error") as error:
            enhanced_logging.log_workflow_error(
                "action_failed",
                ValueError("failure"),
                action_id=3,
            )
            self.assertEqual(error.call_args.kwargs["error_type"], "ValueError")

    def test_admin_display_helpers_cover_all_scopes(self):
        target = SimpleNamespace(__str__=lambda self: "Target")
        content_type = SimpleNamespace(app_label="app", model="ticket")
        attachment_obj = SimpleNamespace(
            target=target,
            content_type=content_type,
            object_id="1",
        )
        with patch("django_workflow_engine.admin.reverse", return_value="/admin/1/"):
            rendered = WorkflowAttachmentAdmin.get_target_object(None, attachment_obj)
            self.assertIn("/admin/1/", rendered)
        with patch(
            "django_workflow_engine.admin.reverse",
            side_effect=RuntimeError("missing"),
        ):
            self.assertTrue(
                WorkflowAttachmentAdmin.get_target_object(None, attachment_obj)
            )
        self.assertEqual(
            WorkflowAttachmentAdmin.get_target_object(
                None,
                SimpleNamespace(target=None),
            ),
            "-",
        )

        named = SimpleNamespace(content_type=content_type)
        self.assertEqual(
            ModelStatusConfigurationAdmin.get_model_name(None, named),
            "app.ticket",
        )
        self.assertEqual(
            WorkflowConfigurationAdmin.get_model_name(None, named),
            "app.ticket",
        )
        self.assertEqual(
            StatusAttachmentAdmin.get_target_object(None, attachment_obj),
            str(target),
        )
        self.assertEqual(
            StatusHistoryAdmin.get_target_object(None, SimpleNamespace(target=None)),
            "-",
        )

        scopes = [
            SimpleNamespace(
                stage=SimpleNamespace(
                    name_en="Stage",
                    pipeline=SimpleNamespace(name_en="Pipeline"),
                ),
                pipeline=None,
                workflow=None,
                transition=None,
            ),
            SimpleNamespace(
                stage=None,
                pipeline=SimpleNamespace(
                    name_en="Pipeline",
                    workflow=SimpleNamespace(name_en="Workflow"),
                ),
                workflow=None,
                transition=None,
            ),
            SimpleNamespace(
                stage=None,
                pipeline=None,
                workflow=SimpleNamespace(name_en="Workflow"),
                transition=None,
            ),
            SimpleNamespace(
                stage=None,
                pipeline=None,
                workflow=None,
                transition=SimpleNamespace(name_en="Transition"),
            ),
            SimpleNamespace(
                stage=None,
                pipeline=None,
                workflow=None,
                transition=None,
            ),
        ]
        for scope in scopes:
            self.assertTrue(WorkflowActionAdmin.get_scope(None, scope))

    def test_migration_callable_branches(self):
        initial = importlib.import_module(
            "django_workflow_engine.migrations.0001_initial"
        )
        with patch.object(initial.django, "VERSION", (6, 0)):
            constraint = initial.create_check_constraint(
                "test_constraint",
                Q(pk=1),
            )
            self.assertEqual(constraint.name, "test_constraint")

        strategy = importlib.import_module(
            "django_workflow_engine.migrations.0006_fix_workflow_strategy_values"
        )
        with_stages = MagicMock(id=1, name_en="With stages", strategy=3)
        stage_pipeline = MagicMock()
        stage_pipeline.stages.exists.return_value = True
        with_stages.pipelines.exists.return_value = True
        with_stages.pipelines.all.return_value = [stage_pipeline]

        without_stages = MagicMock(id=2, name_en="No stages", strategy=3)
        empty_pipeline = MagicMock()
        empty_pipeline.stages.exists.return_value = False
        without_stages.pipelines.exists.return_value = True
        without_stages.pipelines.all.return_value = [empty_pipeline]

        without_pipelines = MagicMock(id=3, name_en="No pipelines", strategy=1)
        without_pipelines.pipelines.exists.return_value = False
        already_workflow_only = MagicMock(id=4, strategy=3)
        already_workflow_only.pipelines.exists.return_value = False

        workflow_model = MagicMock()
        workflow_model.objects.all.return_value = [
            with_stages,
            without_stages,
            without_pipelines,
            already_workflow_only,
        ]
        apps = MagicMock()
        apps.get_model.return_value = workflow_model

        strategy.fix_workflow_strategies(apps, None)
        self.assertEqual(with_stages.strategy, 1)
        self.assertEqual(without_stages.strategy, 2)
        self.assertEqual(without_pipelines.strategy, 3)

        queryset = MagicMock()
        workflow_model.objects.all.return_value = queryset
        strategy.reverse_fix(apps, None)
        queryset.update.assert_called_once_with(strategy=3)

    def test_package_compat_import_failure_is_ignored(self):
        package = importlib.import_module("django_workflow_engine")
        with patch.dict(sys.modules, {"approval_workflow.choices": None}):
            package._patch_role_selection_strategy_compat()

    def test_example_status_update_sets_updated_at(self):
        target = SimpleNamespace(
            pk=1,
            status="old",
            updated_at=None,
            _meta=SimpleNamespace(label="tests.Target"),
        )
        result = update_object_status(
            SimpleNamespace(target=target),
            {"status": "new", "save": False},
        )
        self.assertTrue(result)
        self.assertEqual(target.status, "new")
        self.assertIsNotNone(target.updated_at)

    def test_cleanup_command_reports_deleted_orphan_actions(self):
        command = CleanupCommand()
        command.stdout = MagicMock()
        command.style = MagicMock()
        command.style.SUCCESS.side_effect = lambda value: value
        with (
            patch(
                "django_workflow_engine.management.commands.cleanup_workflows."
                "cleanup_completed_workflow_actions",
                return_value={"actions_deleted": 0},
            ),
            patch(
                "django_workflow_engine.management.commands.cleanup_workflows."
                "cleanup_orphaned_workflow_actions",
                return_value={"actions_deleted": 2},
            ),
        ):
            command.handle(
                dry_run=False,
                days=30,
                status=["completed"],
                include_orphaned_actions=True,
                stats=False,
            )

        self.assertTrue(
            any(
                "Deleted 2 orphaned actions" in str(call)
                for call in command.stdout.write.call_args_list
            )
        )

    def test_workflow_action_admin_queryset_optimization(self):
        model_admin = WorkflowActionAdmin(WorkflowAction, admin.site)
        request = RequestFactory().get("/admin/")
        queryset = model_admin.get_queryset(request)
        self.assertEqual(queryset.model, WorkflowAction)


class SmallDatabaseBranchCoverageTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="small-coverage",
            email="small@example.com",
        )

    def test_orphan_cleanup_dry_run_and_delete(self):
        queryset = MagicMock()
        queryset.count.return_value = 1
        queryset.delete.return_value = (1, {})

        with patch(
            "django_workflow_engine.cleanup.WorkflowAction.objects.filter",
            return_value=queryset,
        ):
            dry_run = cleanup_orphaned_workflow_actions(dry_run=True)
            deleted = cleanup_orphaned_workflow_actions(dry_run=False)

        self.assertEqual(dry_run, {"actions_deleted": 1, "dry_run": True})
        self.assertEqual(deleted, {"actions_deleted": 1, "dry_run": False})

    @patch("django_workflow_engine.notifications.EmailMultiAlternatives")
    def test_notification_user_id_and_bulk_non_deduplicated_paths(self, email_class):
        email_class.return_value.send.return_value = 1
        self.assertTrue(
            send_workflow_email(
                name="workflow_approved",
                user=self.user.pk,
                context={"subject": "Subject"},
            )
        )
        self.assertFalse(
            send_workflow_email(
                name="workflow_approved",
                user=999999,
            )
        )

        with patch(
            "django_workflow_engine.notifications.send_workflow_email",
            return_value=True,
        ) as send_email:
            result = send_bulk_workflow_emails(
                "workflow_approved",
                [self.user.pk, self.user, "direct@example.com", 999999],
                context={"subject": "Subject"},
                deduplicate=False,
            )

        self.assertEqual(result["sent"], 3)
        self.assertEqual(send_email.call_count, 3)

    def test_build_email_context_includes_company_details(self):
        company = SimpleNamespace(name="Acme", logo="logo.png")
        attached_object = WorkflowTestModelFactory(created_by=self.user)
        attached_object.company = company
        attachment = __import__(
            "django_workflow_engine.models", fromlist=["WorkflowAttachment"]
        ).WorkflowAttachment.objects.create(
            workflow=WorkFlowFactory(),
            content_type=ContentType.objects.get_for_model(attached_object),
            object_id=str(attached_object.pk),
            started_by=self.user,
        )

        with patch.object(
            type(attached_object),
            "company",
            new_callable=PropertyMock,
            create=True,
            return_value=company,
        ):
            context = get_workflow_email_context(
                attachment,
                user=self.user,
            )

        self.assertEqual(context["company_name"], "Acme")
        self.assertEqual(context["company_logo"], "logo.png")
        self.assertEqual(context["actor_email"], self.user.email)
        self.assertTrue(
            context["object_link"].endswith(f"/workflowtestmodels/{attached_object.pk}")
        )

    def test_cleanup_signal_logs_delete_failure(self):
        workflow = SimpleNamespace(id=7, is_hidden=True, cloned_from_id=None)
        instance = SimpleNamespace(
            status=WorkflowAttachmentStatus.COMPLETED,
            workflow=workflow,
        )
        queryset = MagicMock()
        queryset.count.return_value = 1
        queryset.delete.side_effect = RuntimeError("delete failed")

        with patch(
            "django_workflow_engine.signals.WorkflowAction.objects.filter",
            return_value=queryset,
        ):
            with self.assertLogs(
                "django_workflow_engine.signals", level="ERROR"
            ) as captured:
                auto_cleanup_completed_workflow_actions(
                    sender=None,
                    instance=instance,
                    created=False,
                )

        self.assertIn("delete failed", captured.output[0])
