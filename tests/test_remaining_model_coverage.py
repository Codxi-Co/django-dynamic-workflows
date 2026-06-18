"""Focused branch coverage for model validation and calculated properties."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from approval_workflow.choices import ApprovalType

from django_workflow_engine.choices import ApprovalTypes, WorkflowStrategy
from django_workflow_engine.models import (
    CompanyBaseWithNamedModelWithClone,
    Pipeline,
    Stage,
    StatusAttachment,
    StatusHistory,
    WorkFlow,
    WorkflowAction,
    WorkflowAttachment,
    validate_approval_configuration_payload,
)


class ApprovalPayloadValidationCoverageTest(SimpleTestCase):
    def test_all_invalid_approval_payload_shapes(self):
        payloads = [
            None,
            {"approvals": "invalid"},
            {"approvals": ["invalid"]},
            {"approvals": [{"approval_type": "invalid"}]},
            {"approvals": [{"approval_type": ApprovalTypes.ROLE}]},
            {
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "user_role": 1,
                        "role_selection_strategy": "invalid",
                    }
                ]
            },
            {"approvals": [{"approval_type": ApprovalTypes.USER}]},
            {
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.SELF,
                        "step_approval_type": "invalid",
                    }
                ]
            },
            {
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.SELF,
                        "step_approval_type": ApprovalType.SUBMIT,
                    }
                ]
            },
            {
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.SELF,
                        "step_approval_type": ApprovalType.MOVE,
                        "required_form": 1,
                    }
                ]
            },
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    validate_approval_configuration_payload(payload)

        with self.assertRaises(ValidationError):
            validate_approval_configuration_payload(
                {"approvals": []},
                require_approvals=True,
            )

        self.assertTrue(
            validate_approval_configuration_payload(
                {"approvals": [{"approval_type": ApprovalTypes.SELF}]}
            )
        )


class CalculatedModelCoverageTest(TestCase):
    def test_clone_uses_default_arguments(self):
        workflow = WorkFlow(name_en="Original", name_ar="Original")
        workflow.pk = 3
        with patch.object(WorkFlow, "save"):
            cloned = CompanyBaseWithNamedModelWithClone.clone(workflow)
        self.assertIsInstance(cloned, WorkFlow)
        self.assertEqual(cloned.cloned_from, workflow)

    def test_validate_completeness_remaining_strategy_paths(self):
        empty_manager = MagicMock()
        empty_manager.prefetch_related.return_value.all.return_value = []
        workflow = SimpleNamespace(
            strategy=WorkflowStrategy.WORKFLOW_PIPELINE,
            pipelines=empty_manager,
        )
        valid, message = WorkFlow.validate_completeness(workflow)
        self.assertFalse(valid)
        self.assertIn("at least one pipeline", message)

        pipeline = SimpleNamespace(
            name_en="Pipeline",
            pipeline_info={},
            stages=MagicMock(),
        )
        manager = MagicMock()
        manager.prefetch_related.return_value.all.return_value = [pipeline]
        workflow.pipelines = manager
        valid, message = WorkFlow.validate_completeness(workflow)
        self.assertFalse(valid)
        self.assertIn("must have approvals", message)

        pipeline.pipeline_info = {"approvals": [{}]}
        pipeline.stages.all.return_value = [object()]
        valid, message = WorkFlow.validate_completeness(workflow)
        self.assertFalse(valid)
        self.assertIn("cannot have stages", message)

        workflow.strategy = WorkflowStrategy.WORKFLOW_ONLY
        workflow.workflow_info = {}
        valid, message = WorkFlow.validate_completeness(workflow)
        self.assertFalse(valid)
        self.assertIn("must have approvals", message)

        workflow.workflow_info = {"approvals": [{}]}
        workflow.pipelines.all.return_value.exists.return_value = True
        valid, message = WorkFlow.validate_completeness(workflow)
        self.assertFalse(valid)
        self.assertIn("cannot have pipelines", message)

        workflow.pipelines.all.return_value.exists.return_value = False
        valid, message = WorkFlow.validate_completeness(workflow)
        self.assertTrue(valid)
        self.assertIn("complete and valid", message)

        workflow.strategy = WorkflowStrategy.STATUS_GRAPH
        workflow.status_nodes = MagicMock()
        workflow.status_transitions = MagicMock()
        workflow.status_nodes.filter.return_value = []
        valid, message = WorkFlow.validate_completeness(workflow)
        self.assertFalse(valid)
        self.assertIn("at least one status", message)

        workflow.status_nodes.filter.return_value = [
            SimpleNamespace(is_initial=True),
            SimpleNamespace(is_initial=True),
        ]
        valid, message = WorkFlow.validate_completeness(workflow)
        self.assertFalse(valid)
        self.assertIn("exactly one initial", message)

        transition = MagicMock()
        transition.clean.side_effect = ValidationError("invalid transition")
        workflow.status_nodes.filter.return_value = [
            SimpleNamespace(is_initial=True),
        ]
        workflow.status_transitions.filter.return_value = [transition]
        valid, message = WorkFlow.validate_completeness(workflow)
        self.assertFalse(valid)
        self.assertIn("invalid transition", message)

        workflow.strategy = 999
        valid, message = WorkFlow.validate_completeness(workflow)
        self.assertFalse(valid)
        self.assertIn("Unknown strategy", message)

    def test_stage_approval_validation_early_returns(self):
        stage = Stage(name_en="Review")
        invalid = [
            "not-a-dict",
            {},
            {"approval_type": "invalid"},
            {"approval_type": ApprovalTypes.ROLE},
            {"approval_type": ApprovalTypes.USER},
            {
                "approval_type": ApprovalTypes.SELF,
                "step_approval_type": "invalid",
            },
        ]
        for approval in invalid:
            with self.subTest(approval=approval):
                self.assertFalse(stage._validate_approval_config(approval))

    def test_pipeline_department_name_fallbacks(self):
        pipeline = SimpleNamespace(department=None)
        self.assertIsNone(Pipeline.department_name.fget(pipeline))

        pipeline.department = SimpleNamespace(name="Support")
        self.assertEqual(Pipeline.department_name.fget(pipeline), "Support")

        class StringOnly:
            def __str__(self):
                return "Fallback"

        pipeline.department = StringOnly()
        self.assertEqual(Pipeline.department_name.fget(pipeline), "Fallback")

    def test_attachment_progress_strategy_and_cache_paths(self):
        workflow_only = SimpleNamespace(strategy=WorkflowStrategy.WORKFLOW_ONLY)

        class Attachment(SimpleNamespace):
            def _calculate_pipeline_progress(self):
                return WorkflowAttachment._calculate_pipeline_progress(self)

            def _calculate_stage_progress(self):
                return WorkflowAttachment._calculate_stage_progress(self)

        attachment = Attachment(
            status="in_progress",
            current_stage=SimpleNamespace(id=2),
            current_pipeline=None,
            workflow=workflow_only,
        )
        self.assertEqual(WorkflowAttachment.progress_percentage.fget(attachment), 50)

        first = SimpleNamespace(id=1)
        second = SimpleNamespace(id=2)
        pipeline_workflow = SimpleNamespace(
            strategy=WorkflowStrategy.WORKFLOW_PIPELINE,
            _prefetched_objects_cache={"pipelines": [first, second]},
        )
        attachment.workflow = pipeline_workflow
        attachment.current_pipeline = second
        self.assertEqual(WorkflowAttachment.progress_percentage.fget(attachment), 100)

        attachment.current_pipeline = SimpleNamespace(id=99)
        self.assertEqual(
            WorkflowAttachment._calculate_pipeline_progress(attachment),
            0,
        )

        empty_workflow = SimpleNamespace(
            _prefetched_objects_cache={"pipelines": []},
            pipelines=MagicMock(),
        )
        empty_workflow.pipelines.all.return_value.order_by.return_value = []
        attachment.workflow = empty_workflow
        self.assertEqual(
            WorkflowAttachment._calculate_pipeline_progress(attachment),
            0,
        )

    def test_stage_progress_prefetch_and_query_fallbacks(self):
        current = SimpleNamespace(id=2)
        stage_one = SimpleNamespace(id=1)
        stage_two = current
        prefetched_pipeline = SimpleNamespace(
            _prefetched_objects_cache={"stages": [stage_one, stage_two]}
        )
        workflow = SimpleNamespace(
            _prefetched_objects_cache={"pipelines": [prefetched_pipeline]}
        )
        attachment = SimpleNamespace(workflow=workflow, current_stage=current)
        self.assertEqual(
            WorkflowAttachment._calculate_stage_progress(attachment),
            100,
        )

        pipeline = SimpleNamespace(stages=MagicMock())
        pipeline.stages.all.return_value.order_by.return_value = []
        workflow = SimpleNamespace(pipelines=MagicMock())
        workflow.pipelines.all.return_value.order_by.return_value = [pipeline]
        attachment.workflow = workflow
        self.assertEqual(
            WorkflowAttachment._calculate_stage_progress(attachment),
            0,
        )

        pipeline = SimpleNamespace(
            _prefetched_objects_cache={"stages": None},
            stages=MagicMock(),
        )
        pipeline.stages.all.return_value.order_by.return_value = []
        workflow = SimpleNamespace(
            _prefetched_objects_cache={"pipelines": None},
            pipelines=MagicMock(),
        )
        workflow.pipelines.all.return_value.order_by.return_value = [pipeline]
        attachment.workflow = workflow
        self.assertEqual(
            WorkflowAttachment._calculate_stage_progress(attachment),
            0,
        )

        workflow = SimpleNamespace(pipelines=MagicMock())
        workflow.pipelines.all.return_value.order_by.return_value = []
        attachment.workflow = workflow
        self.assertEqual(
            WorkflowAttachment._calculate_pipeline_progress(attachment),
            0,
        )

    def test_next_stage_strategy_early_paths(self):
        attachment = SimpleNamespace(
            workflow=SimpleNamespace(strategy=WorkflowStrategy.WORKFLOW_ONLY),
        )
        self.assertIsNone(WorkflowAttachment.next_stage.fget(attachment))

        first_pipeline = SimpleNamespace()
        manager = MagicMock()
        manager.order_by.return_value.first.return_value = first_pipeline
        attachment = SimpleNamespace(
            workflow=SimpleNamespace(
                strategy=WorkflowStrategy.WORKFLOW_PIPELINE,
                pipelines=manager,
            ),
            current_pipeline=None,
        )
        self.assertIs(
            WorkflowAttachment.next_stage.fget(attachment),
            first_pipeline,
        )

        attachment.current_pipeline = SimpleNamespace(order=3)
        manager.filter.return_value.order_by.return_value.first.return_value = None
        self.assertIsNone(WorkflowAttachment.next_stage.fget(attachment))

        attachment = SimpleNamespace(
            id=4,
            workflow=SimpleNamespace(
                strategy=WorkflowStrategy.WORKFLOW_PIPELINE_STAGE,
                pipelines=MagicMock(),
            ),
            current_stage=SimpleNamespace(
                order=1,
                pipeline=None,
            ),
            current_pipeline=None,
        )
        self.assertIsNone(WorkflowAttachment.next_stage.fget(attachment))

    def test_workflow_action_scope_strings_and_objects(self):
        action = WorkflowAction(action_type="before_approve", function_path="test")
        self.assertEqual(action.scope_level, "default")
        self.assertIsNone(action.scope_object)
        with self.assertRaises(ValidationError):
            action.clean()

        scopes = [
            ("stage", SimpleNamespace(name_en="Stage")),
            ("pipeline", SimpleNamespace(name_en="Pipeline")),
            ("workflow", SimpleNamespace(name_en="Workflow")),
            ("transition", SimpleNamespace(name_en="Transition")),
            (
                "status_node",
                SimpleNamespace(status=SimpleNamespace(name_en="Status")),
            ),
        ]
        for field, value in scopes:
            values = {
                "stage": None,
                "pipeline": None,
                "workflow": None,
                "transition": None,
                "status_node": None,
            }
            values[field] = value
            action = SimpleNamespace(
                **values,
                function_path="test",
                get_action_type_display=lambda: "Before approve",
            )
            self.assertEqual(WorkflowAction.scope_level.fget(action), field)
            self.assertIs(WorkflowAction.scope_object.fget(action), value)
            self.assertIn(
                value.name_en if field != "status_node" else "Status",
                WorkflowAction.__str__(action),
            )

    def test_attachment_and_history_string_representations(self):
        content_type = SimpleNamespace(model="ticket")
        status = SimpleNamespace(__str__=lambda self: "New")
        workflow = SimpleNamespace(name_en="Support")
        attachment = SimpleNamespace(
            workflow=workflow,
            content_type=content_type,
            object_id="1",
        )
        self.assertIn(
            "Support",
            WorkflowAttachment.__str__(attachment),
        )

        status_attachment = SimpleNamespace(
            content_type=content_type,
            object_id="1",
            status=status,
        )
        self.assertIn(
            "ticket(1)",
            StatusAttachment.__str__(status_attachment),
        )

        history = SimpleNamespace(
            content_type=content_type,
            object_id="1",
            from_status=None,
            to_status=status,
        )
        self.assertIn("ticket(1)", StatusHistory.__str__(history))

    def test_workflow_save_and_clone_action_errors_are_logged(self):
        workflow = WorkFlow(name_en="Workflow", name_ar="Workflow")
        with (
            patch(
                "django_workflow_engine.action_management.create_default_workflow_actions",
                side_effect=RuntimeError("actions failed"),
            ),
            patch.object(
                WorkFlow.__mro__[1],
                "save",
                autospec=True,
            ),
        ):
            workflow.save()

        source = WorkFlow(name_en="Source", name_ar="Source")
        source.pk = 9
        target = WorkFlow(name_en="Target", name_ar="Target")
        target.pk = 10
        with (
            patch.object(WorkFlow.__mro__[1], "clone", return_value=target),
            patch(
                "django_workflow_engine.action_management.clone_workflow_actions",
                side_effect=RuntimeError("clone actions failed"),
            ),
        ):
            self.assertIs(source.clone(), target)

    def test_attachment_save_corrects_mismatched_pipeline(self):
        expected_pipeline = Pipeline(name_en="Expected", name_ar="Expected")
        expected_pipeline.pk = 1
        wrong_pipeline = Pipeline(name_en="Wrong", name_ar="Wrong")
        wrong_pipeline.pk = 2
        stage = Stage(
            name_en="Stage",
            name_ar="Stage",
            pipeline=expected_pipeline,
        )
        stage.pk = 3
        attachment = WorkflowAttachment(
            current_stage=stage,
            current_pipeline=wrong_pipeline,
        )

        with patch("django.db.models.Model.save"):
            attachment.save()

        self.assertIs(attachment.current_pipeline, expected_pipeline)
