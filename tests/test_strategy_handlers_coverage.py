"""Focused coverage for workflow strategy handlers."""

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from django_workflow_engine.choices import (
    WorkflowAttachmentStatus,
    WorkflowStatus,
    WorkflowStrategy,
)
from django_workflow_engine.models import Pipeline, Stage, WorkFlow, WorkflowAttachment
from django_workflow_engine.strategy_handlers import (
    StrategyHandler,
    WorkflowOnlyHandler,
    WorkflowPipelineHandler,
    WorkflowPipelineStageHandler,
    get_strategy_handler,
    get_workflow_location,
)
from sandbox.testapp.models import WorkflowTestModel

User = get_user_model()


class StrategyHandlersCoverageTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="strategy-user", password="pass")
        self.obj = WorkflowTestModel.objects.create(name="Strategy Target")
        self.content_type = ContentType.objects.get_for_model(self.obj)

    def _workflow(self, strategy):
        return WorkFlow.objects.create(
            name_en=f"Workflow {strategy}",
            name_ar=f"Workflow {strategy}",
            status=WorkflowStatus.ACTIVE,
            strategy=strategy,
            company=self.user,
        )

    def _attachment(self, workflow, **kwargs):
        target = WorkflowTestModel.objects.create(name=f"Strategy Target {workflow.id}")
        defaults = {
            "workflow": workflow,
            "content_type": self.content_type,
            "object_id": str(target.pk),
            "status": WorkflowAttachmentStatus.IN_PROGRESS,
        }
        defaults.update(kwargs)
        return WorkflowAttachment.objects.create(**defaults)

    def test_base_strategy_handler_methods_raise_not_implemented(self):
        workflow = self._workflow(WorkflowStrategy.WORKFLOW_ONLY)
        attachment = self._attachment(workflow)
        handler = StrategyHandler(attachment)

        for method_name in [
            "get_initial_position",
            "get_next_position",
            "calculate_progress",
            "validate_position",
            "build_approval_steps",
        ]:
            with self.subTest(method=method_name):
                with self.assertRaises(NotImplementedError):
                    if method_name == "build_approval_steps":
                        getattr(handler, method_name)(self.user)
                    else:
                        getattr(handler, method_name)()

    def test_pipeline_stage_handler_positions_progress_and_approvals(self):
        workflow = self._workflow(WorkflowStrategy.WORKFLOW_PIPELINE_STAGE)
        first_pipeline = Pipeline.objects.create(
            workflow=workflow, name_en="P1", order=1
        )
        second_pipeline = Pipeline.objects.create(
            workflow=workflow, name_en="P2", order=2
        )
        stage1 = Stage.objects.create(pipeline=first_pipeline, name_en="S1", order=1)
        stage2 = Stage.objects.create(pipeline=first_pipeline, name_en="S2", order=2)
        stage3 = Stage.objects.create(pipeline=second_pipeline, name_en="S3", order=1)
        attachment = self._attachment(
            workflow, current_pipeline=first_pipeline, current_stage=stage1
        )
        handler = WorkflowPipelineStageHandler(attachment)

        self.assertEqual(handler.get_initial_position(), (first_pipeline, stage1))
        self.assertEqual(handler.get_next_position(), stage2)
        self.assertEqual(handler.calculate_progress(), 33)
        self.assertTrue(handler.validate_position())

        attachment.current_stage = stage2
        attachment.current_pipeline = first_pipeline
        self.assertEqual(handler.get_next_position(), stage3)

        attachment.current_stage = stage3
        attachment.current_pipeline = second_pipeline
        self.assertEqual(handler.get_next_position(), None)

        attachment.current_stage = None
        self.assertEqual(handler.get_next_position(), stage1)
        self.assertFalse(handler.validate_position())
        self.assertEqual(handler.build_approval_steps(self.user), [])

        attachment.current_stage = stage1
        with patch(
            "django_workflow_engine.utils.build_approval_steps",
            return_value=[{"step": 1}],
        ) as builder:
            self.assertEqual(
                handler.build_approval_steps(self.user, start_step=5), [{"step": 1}]
            )
        builder.assert_called_once_with(stage1, self.user, 5)

        workflow._prefetched_objects_cache = {"pipelines": [first_pipeline]}
        first_pipeline._prefetched_objects_cache = {"stages": [stage1, stage2]}
        self.assertEqual(list(handler._get_pipelines()), [first_pipeline])
        self.assertEqual(list(handler._get_stages(first_pipeline)), [stage1, stage2])

    def test_pipeline_stage_handler_initial_position_errors_and_empty_progress(self):
        workflow = self._workflow(WorkflowStrategy.WORKFLOW_PIPELINE_STAGE)
        attachment = self._attachment(workflow)
        handler = WorkflowPipelineStageHandler(attachment)

        with self.assertRaisesMessage(ValueError, "at least one pipeline"):
            handler.get_initial_position()
        self.assertEqual(handler.get_next_position(), None)
        self.assertEqual(handler.calculate_progress(), 0)

        pipeline = Pipeline.objects.create(workflow=workflow, name_en="Empty", order=1)
        with self.assertRaisesMessage(ValueError, "at least one stage"):
            handler.get_initial_position()
        self.assertEqual(handler._get_stages(pipeline).count(), 0)

    def test_pipeline_handler_positions_progress_and_approvals(self):
        workflow = self._workflow(WorkflowStrategy.WORKFLOW_PIPELINE)
        first_pipeline = Pipeline.objects.create(
            workflow=workflow,
            name_en="P1",
            order=1,
            pipeline_info={"approvals": [{"approval_type": "self"}]},
        )
        second_pipeline = Pipeline.objects.create(
            workflow=workflow, name_en="P2", order=2
        )
        attachment = self._attachment(workflow, current_pipeline=first_pipeline)
        handler = WorkflowPipelineHandler(attachment)

        self.assertEqual(handler.get_initial_position(), (first_pipeline, None))
        self.assertEqual(handler.get_next_position(), second_pipeline)
        self.assertEqual(handler.calculate_progress(), 50)
        self.assertTrue(handler.validate_position())

        attachment.current_pipeline = second_pipeline
        self.assertEqual(handler.get_next_position(), None)

        attachment.current_pipeline = None
        self.assertEqual(handler.get_next_position(), first_pipeline)
        self.assertEqual(handler.calculate_progress(), 0)
        self.assertFalse(handler.validate_position())
        self.assertEqual(handler.build_approval_steps(self.user), [])

        attachment.current_pipeline = first_pipeline
        with patch(
            "django_workflow_engine.utils.build_approval_steps_from_config",
            return_value=[{"step": 2}],
        ) as builder:
            self.assertEqual(
                handler.build_approval_steps(self.user, start_step=3), [{"step": 2}]
            )
        builder.assert_called_once()
        self.assertEqual(
            builder.call_args.kwargs["extra_fields"], {"pipeline_id": first_pipeline.id}
        )

        workflow._prefetched_objects_cache = {
            "pipelines": [first_pipeline, second_pipeline]
        }
        self.assertEqual(
            list(handler._get_pipelines()), [first_pipeline, second_pipeline]
        )

    def test_pipeline_handler_initial_position_error_and_empty_progress(self):
        workflow = self._workflow(WorkflowStrategy.WORKFLOW_PIPELINE)
        attachment = self._attachment(workflow)
        handler = WorkflowPipelineHandler(attachment)

        with self.assertRaisesMessage(ValueError, "at least one pipeline"):
            handler.get_initial_position()
        self.assertEqual(handler.calculate_progress(), 0)

    def test_workflow_only_handler_and_factory_locations(self):
        workflow = self._workflow(WorkflowStrategy.WORKFLOW_ONLY)
        workflow.workflow_info = {"approvals": [{"approval_type": "self"}]}
        workflow.save(update_fields=["workflow_info"])
        attachment = self._attachment(workflow)
        handler = WorkflowOnlyHandler(attachment)

        self.assertEqual(handler.get_initial_position(), (None, None))
        self.assertEqual(handler.get_next_position(), None)
        self.assertEqual(handler.calculate_progress(), 50)
        self.assertTrue(handler.validate_position())
        self.assertEqual(
            get_strategy_handler(attachment).__class__, WorkflowOnlyHandler
        )
        self.assertEqual(get_workflow_location(attachment), "Workflow 'Workflow 3'")

        with patch(
            "django_workflow_engine.utils.build_approval_steps_from_config",
            return_value=[{"step": 1}],
        ) as builder:
            self.assertEqual(
                handler.build_approval_steps(self.user, start_step=9), [{"step": 1}]
            )
        self.assertEqual(
            builder.call_args.kwargs["extra_fields"], {"workflow_id": workflow.id}
        )

        attachment.status = WorkflowAttachmentStatus.COMPLETED
        attachment.current_pipeline = Pipeline.objects.create(
            workflow=workflow, name_en="Invalid"
        )
        self.assertEqual(handler.calculate_progress(), 0)
        self.assertFalse(handler.validate_position())

    def test_get_strategy_handler_variants_and_location_fallbacks(self):
        stage_workflow = self._workflow(WorkflowStrategy.WORKFLOW_PIPELINE_STAGE)
        pipeline = Pipeline.objects.create(
            workflow=stage_workflow, name_en="Pipe", order=1
        )
        stage = Stage.objects.create(pipeline=pipeline, name_en="Stage", order=1)
        stage_attachment = self._attachment(
            stage_workflow, current_pipeline=pipeline, current_stage=stage
        )
        self.assertIsInstance(
            get_strategy_handler(stage_attachment), WorkflowPipelineStageHandler
        )
        self.assertEqual(
            get_workflow_location(stage_attachment),
            "Stage 'Stage' in pipeline 'Pipe'",
        )

        stage_attachment.current_stage = None
        self.assertEqual(get_workflow_location(stage_attachment), "No stage")

        pipeline_workflow = self._workflow(WorkflowStrategy.WORKFLOW_PIPELINE)
        pipeline = Pipeline.objects.create(
            workflow=pipeline_workflow, name_en="Only Pipe"
        )
        pipeline_attachment = self._attachment(
            pipeline_workflow, current_pipeline=pipeline
        )
        self.assertIsInstance(
            get_strategy_handler(pipeline_attachment), WorkflowPipelineHandler
        )
        self.assertEqual(
            get_workflow_location(pipeline_attachment), "Pipeline 'Only Pipe'"
        )

        pipeline_attachment.current_pipeline = None
        self.assertEqual(get_workflow_location(pipeline_attachment), "No pipeline")

        mock_strategy_attachment = SimpleMockAttachment(strategy=Mock())
        self.assertIsInstance(
            get_strategy_handler(mock_strategy_attachment), WorkflowPipelineStageHandler
        )

        unknown_attachment = SimpleMockAttachment(strategy=99)
        with self.assertRaisesMessage(ValueError, "Unknown workflow strategy"):
            get_strategy_handler(unknown_attachment)
        self.assertEqual(get_workflow_location(unknown_attachment), "Unknown location")


class SimpleMockAttachment:
    def __init__(self, strategy):
        self.workflow = SimpleMockWorkflow(strategy)
        self.current_pipeline = None
        self.current_stage = None


class SimpleMockWorkflow:
    def __init__(self, strategy):
        self.strategy = strategy
        self.name_en = "Mock Workflow"
