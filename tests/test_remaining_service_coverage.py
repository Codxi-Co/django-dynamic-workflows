"""Focused coverage for remaining workflow service fallback contracts."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from django_workflow_engine.choices import (
    ActionFailurePolicy,
    ActionType,
    WorkflowAttachmentStatus,
    WorkflowStrategy,
)
from django_workflow_engine.models import (
    ModelStatusConfiguration,
    StatusAttachment,
    WorkflowAttachment,
    WorkflowConfiguration,
)
from django_workflow_engine.services import (
    _complete_transition,
    _execute_configured_actions,
    _run_status_entry_actions,
    _sync_object_status_field,
    _validate_status_allowed_for_object,
    approve_pending_transition,
    attach_workflow_to_object,
    complete_workflow,
    execute_action_function,
    execute_workflow_actions,
    get_auto_start_workflow_for_object,
    get_available_statuses,
    get_available_transitions,
    get_status_attachment,
    get_workflow_attachment,
    get_workflow_progress,
    is_model_workflow_enabled,
    move_to_next_stage,
    perform_transition,
    register_model_for_workflow,
    reject_pending_transition,
    reject_workflow_stage,
    set_pipeline_department,
    set_status,
    start_workflow_for_object,
    trigger_workflow_event,
    update_object_status,
)
from sandbox.testapp.models import WorkflowTestModel
from tests.factories import UserFactory, WorkFlowFactory, WorkflowTestModelFactory

User = get_user_model()


class RemainingServiceCoverageTest(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.obj = WorkflowTestModelFactory(created_by=self.user)

    @override_settings(DJANGO_WORKFLOW_ENGINE={})
    def test_department_and_missing_status_configuration_paths(self):
        pipeline = SimpleNamespace(id=1)
        self.assertIsNone(set_pipeline_department(pipeline, 2))

        with override_settings(DJANGO_WORKFLOW_ENGINE={"DEPARTMENT_MODEL": "invalid"}):
            self.assertIsNone(set_pipeline_department(pipeline, 2))

        self.assertEqual(get_available_statuses(WorkflowTestModel), [])
        self.assertIsNone(get_status_attachment(self.obj))
        self.assertIsNone(get_workflow_attachment(self.obj))
        self.assertFalse(is_model_workflow_enabled(WorkflowTestModel))

    def test_progress_and_status_validation_fallbacks(self):
        progress = get_workflow_progress(WorkFlowFactory(), self.obj)
        self.assertEqual(progress["progress_percentage"], 0)

        inactive = SimpleNamespace(is_active=False)
        with self.assertRaises(ValueError):
            _validate_status_allowed_for_object(self.obj, inactive, None)

        active = SimpleNamespace(is_active=True, company_id=2)
        _validate_status_allowed_for_object(self.obj, active, None)
        config = SimpleNamespace()
        with self.assertRaises(ValueError):
            _validate_status_allowed_for_object(
                self.obj,
                active,
                config,
                company=1,
            )
        active.company_id = None
        with patch(
            "django_workflow_engine.services.ModelStatus.objects.filter"
        ) as model_statuses:
            model_statuses.return_value.exists.return_value = False
            with self.assertRaises(ValueError):
                _validate_status_allowed_for_object(
                    self.obj,
                    active,
                    config,
                )

    def test_sync_status_field_early_paths_and_relation_value(self):
        _sync_object_status_field(self.obj, object(), None)
        config = SimpleNamespace(status_field="")
        _sync_object_status_field(self.obj, object(), config)
        config.status_field = "missing"
        _sync_object_status_field(self.obj, object(), config)

        field = SimpleNamespace(remote_field=object())
        obj = MagicMock()
        obj._meta.get_field.return_value = field
        obj.status = None
        config.status_field = "status"
        status = object()
        _sync_object_status_field(obj, status, config)
        self.assertIs(obj.status, status)

    def test_set_status_workflow_enforcement_errors(self):
        status = SimpleNamespace(is_active=True, company_id=None)
        config = SimpleNamespace(allow_direct_change=False)
        with patch(
            "django_workflow_engine.services._get_model_status_config",
            return_value=config,
        ):
            with self.assertRaises(ValueError):
                set_status(self.obj, status)

        config.allow_direct_change = True
        attachment = SimpleNamespace(
            workflow=SimpleNamespace(strategy=WorkflowStrategy.STATUS_GRAPH)
        )
        with (
            patch(
                "django_workflow_engine.services._get_model_status_config",
                return_value=config,
            ),
            patch(
                "django_workflow_engine.services.get_workflow_attachment",
                return_value=attachment,
            ),
        ):
            with self.assertRaises(ValueError):
                set_status(self.obj, status)

    def test_attach_existing_attachment_update_path(self):
        workflow = WorkFlowFactory()
        existing = MagicMock(metadata={})
        with (
            patch(
                "django_workflow_engine.services.WorkflowAttachment.objects.get_or_create",
                return_value=(existing, False),
            ),
            patch("django_workflow_engine.services.log_workflow_action"),
        ):
            result = attach_workflow_to_object(
                self.obj,
                workflow,
                user=self.user,
                disable_clone=True,
            )
        self.assertIs(result, existing)
        existing.save.assert_called()

    def test_start_workflow_missing_and_strategy_requirements(self):
        with self.assertRaises(ValueError):
            start_workflow_for_object(self.obj, self.user)

        attachment = MagicMock(status=WorkflowAttachmentStatus.NOT_STARTED)
        workflow = MagicMock(
            strategy=WorkflowStrategy.WORKFLOW_PIPELINE_STAGE,
            name_en="Workflow",
        )
        attachment.workflow = workflow
        manager = MagicMock()
        manager.get.return_value = attachment
        workflow.pipelines.order_by.return_value.first.return_value = None
        with patch(
            "django_workflow_engine.services.WorkflowAttachment.objects.select_related",
            return_value=manager,
        ):
            with self.assertRaises(ValueError):
                start_workflow_for_object(self.obj, self.user)

        pipeline = MagicMock(name_en="Pipeline")
        workflow.pipelines.order_by.return_value.first.return_value = pipeline
        pipeline.stages.order_by.return_value.first.return_value = None
        with patch(
            "django_workflow_engine.services.WorkflowAttachment.objects.select_related",
            return_value=manager,
        ):
            with self.assertRaises(ValueError):
                start_workflow_for_object(self.obj, self.user)

        workflow.strategy = WorkflowStrategy.WORKFLOW_PIPELINE
        workflow.pipelines.order_by.return_value.first.return_value = None
        with patch(
            "django_workflow_engine.services.WorkflowAttachment.objects.select_related",
            return_value=manager,
        ):
            with self.assertRaises(ValueError):
                start_workflow_for_object(self.obj, self.user)

        workflow.strategy = WorkflowStrategy.STATUS_GRAPH
        workflow.status_nodes.filter.return_value.first.return_value = None
        with patch(
            "django_workflow_engine.services.WorkflowAttachment.objects.select_related",
            return_value=manager,
        ):
            with self.assertRaises(ValueError):
                start_workflow_for_object(self.obj, self.user)

    def test_move_reject_complete_missing_attachment_paths(self):
        with self.assertRaises(ValueError):
            move_to_next_stage(self.obj, self.user)
        with self.assertRaises(ValueError):
            reject_workflow_stage(self.obj, SimpleNamespace(name_en="Stage"))
        with self.assertRaises(ValueError):
            complete_workflow(self.obj, self.user)

        attachment = MagicMock(
            status=WorkflowAttachmentStatus.IN_PROGRESS,
            workflow=SimpleNamespace(strategy=WorkflowStrategy.WORKFLOW_ONLY),
        )
        with (
            patch(
                "django_workflow_engine.services.WorkflowAttachment.objects.get",
                return_value=attachment,
            ),
            patch(
                "django_workflow_engine.services.complete_workflow",
                return_value=attachment,
            ) as complete,
        ):
            self.assertIs(move_to_next_stage(self.obj, self.user), attachment)
        complete.assert_called_once()

    def test_update_object_status_all_configuration_paths(self):
        self.assertFalse(update_object_status(self.obj, "closed"))

        configuration = WorkflowConfiguration.objects.create(
            content_type=__import__(
                "django.contrib.contenttypes.models",
                fromlist=["ContentType"],
            ).ContentType.objects.get_for_model(WorkflowTestModel),
            status_field="",
        )
        self.assertFalse(update_object_status(self.obj, "closed"))
        configuration.status_field = "missing"
        configuration.save()
        self.assertFalse(update_object_status(self.obj, "closed"))
        configuration.status_field = "status"
        configuration.save()
        self.assertTrue(update_object_status(self.obj, "closed"))
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.status, "closed")

    def test_registration_update_and_optimized_attachment_lookup(self):
        workflow = WorkFlowFactory()
        first = register_model_for_workflow(
            WorkflowTestModel,
            default_workflow=workflow,
        )
        second = register_model_for_workflow(
            WorkflowTestModel,
            auto_start=True,
            status_field="status",
        )
        self.assertEqual(first.pk, second.pk)
        self.assertTrue(second.auto_start_workflow)

        attachment = WorkflowAttachment.objects.create(
            workflow=workflow,
            content_type=first.content_type,
            object_id=str(self.obj.pk),
        )
        self.assertEqual(
            get_workflow_attachment(self.obj, optimize_for_progress=True),
            attachment,
        )

    def test_transition_and_action_fallback_paths(self):
        self.assertEqual(get_available_transitions(self.obj, self.user), [])
        workflow = SimpleNamespace(status_nodes=MagicMock())
        workflow.status_nodes.filter.return_value.first.return_value = None
        self.assertEqual(
            _run_status_entry_actions(
                SimpleNamespace(workflow=workflow),
                object(),
            ),
            [],
        )

        skip = SimpleNamespace(
            condition_function="tests.condition",
            parameters={},
            function_path="tests.action",
            failure_policy=ActionFailurePolicy.CONTINUE,
            id=1,
        )
        with patch(
            "django_workflow_engine.services.import_string",
            return_value=lambda **kwargs: False,
        ):
            self.assertEqual(_execute_configured_actions([skip], {}), [])

        failing = SimpleNamespace(
            condition_function="",
            parameters={},
            function_path="tests.action",
            failure_policy=ActionFailurePolicy.STOP,
            id=2,
        )
        with patch(
            "django_workflow_engine.services.execute_action_function",
            side_effect=RuntimeError("failed"),
        ):
            self.assertEqual(_execute_configured_actions([failing], {}), [])

    def test_transition_missing_attachment_and_pending_paths(self):
        transition = SimpleNamespace()
        with self.assertRaises(ValueError):
            _complete_transition(self.obj, transition)
        with self.assertRaises(ValueError):
            perform_transition(self.obj, "missing", self.user)
        with self.assertRaises(ValueError):
            approve_pending_transition(self.obj, self.user)
        with self.assertRaises(ValueError):
            reject_pending_transition(self.obj, self.user)

    def test_action_execution_registry_legacy_and_event_errors(self):
        registry = MagicMock()
        registry.is_registered.side_effect = lambda name: name in {
            "direct",
            "resolved",
        }
        registry.execute_action.return_value = True
        with patch(
            "django_workflow_engine.action_registry.registry",
            registry,
        ):
            self.assertTrue(execute_action_function("direct", {}))
            self.assertTrue(execute_action_function("path.resolved", {}))

        action = SimpleNamespace(function_path="tests.action", parameters={})
        with (
            patch(
                "django_workflow_engine.services.get_actions_for_event",
                return_value=[action],
            ),
            patch(
                "django_workflow_engine.services.execute_action_function",
                side_effect=RuntimeError("failed"),
            ),
        ):
            self.assertEqual(
                execute_workflow_actions(object(), "event", {}),
                [None],
            )

        attachment = SimpleNamespace(
            target=SimpleNamespace(
                pk=1,
                _meta=SimpleNamespace(label="tests.Target"),
            ),
            workflow=SimpleNamespace(),
            current_stage=None,
            current_pipeline=None,
        )
        with (
            patch(
                "django_workflow_engine.services.execute_workflow_actions",
                return_value=[],
            ),
            patch(
                "django_workflow_engine.action_executor.execute_workflow_actions",
                side_effect=RuntimeError("email failed"),
            ),
        ):
            self.assertEqual(trigger_workflow_event(attachment, "event"), [])

    def test_auto_start_configuration_condition_paths(self):
        with patch(
            "django_workflow_engine.services.is_model_enabled_in_settings",
            return_value=False,
        ):
            self.assertIsNone(get_auto_start_workflow_for_object(self.obj))

        configurations = [
            {},
            {"conditions": {}, "workflow_name": None},
            {
                "workflow_name": "Workflow",
                "conditions": {"missing": 1},
            },
            {
                "workflow_name": "Workflow",
                "conditions": {"amount__unsupported": 1},
            },
            {
                "workflow_name": "Workflow",
                "conditions": {"amount__gte": 999999},
            },
        ]
        for configuration in configurations:
            with self.subTest(configuration=configuration):
                with (
                    patch(
                        "django_workflow_engine.services.is_model_enabled_in_settings",
                        return_value=True,
                    ),
                    patch(
                        "django_workflow_engine.services.get_auto_start_config_for_model",
                        return_value=configuration,
                    ),
                ):
                    self.assertIsNone(get_auto_start_workflow_for_object(self.obj))

        lookups = {
            "amount": self.obj.amount,
            "amount__gte": self.obj.amount,
            "amount__lte": self.obj.amount,
            "amount__gt": self.obj.amount - 1,
            "amount__lt": self.obj.amount + 1,
            "amount__in": [self.obj.amount],
            "description__isnull": False,
        }
        for lookup, expected in lookups.items():
            with (
                patch(
                    "django_workflow_engine.services.is_model_enabled_in_settings",
                    return_value=True,
                ),
                patch(
                    "django_workflow_engine.services.get_auto_start_config_for_model",
                    return_value={
                        "workflow_name": "Missing",
                        "conditions": {lookup: expected},
                    },
                ),
            ):
                self.assertIsNone(get_auto_start_workflow_for_object(self.obj))
