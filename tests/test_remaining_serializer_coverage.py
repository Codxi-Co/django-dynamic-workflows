"""Focused validation and helper coverage for serializer branches."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from approval_workflow.choices import ApprovalStatus, RoleSelectionStrategy
from rest_framework import serializers

from django_workflow_engine.choices import ActionType, ApprovalTypes, WorkflowStrategy
from django_workflow_engine.serializers import (
    GenericForeignKeyField,
    PipelineSerializer,
    StageDetailSerializer,
    StageSerializer,
    StatusActionSerializer,
    WorkflowApprovalSerializer,
    WorkFlowSerializer,
)
from tests.factories import UserFactory

User = get_user_model()


class RemainingSerializerCoverageTest(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.instance = SimpleNamespace(
            pk=1,
            created_by=self.user,
            _meta=SimpleNamespace(label="tests.Target"),
        )

    def test_generic_foreign_key_field(self):
        field = GenericForeignKeyField()
        self.assertIsNone(field.to_representation(None))
        represented = field.to_representation(self.instance)
        self.assertEqual(represented["id"], 1)
        with self.assertRaises(serializers.ValidationError):
            field.to_internal_value({})

    def test_workflow_approval_action_validation_failures(self):
        serializer = WorkflowApprovalSerializer()
        with self.assertRaises(serializers.ValidationError):
            serializer.validate_action(ApprovalStatus.APPROVED)

        serializer.instance = self.instance
        with patch(
            "django_workflow_engine.serializers.get_workflow_attachment",
            return_value=None,
        ):
            with self.assertRaises(serializers.ValidationError):
                serializer.validate_action(ApprovalStatus.APPROVED)

        attachment = SimpleNamespace(
            status="in_progress",
            workflow=SimpleNamespace(id=2),
        )
        with (
            patch(
                "django_workflow_engine.serializers.get_workflow_attachment",
                return_value=attachment,
            ),
            patch(
                "django_workflow_engine.serializers.get_current_approval_for_object",
                return_value=None,
            ),
        ):
            with self.assertRaises(serializers.ValidationError):
                serializer.validate_action(ApprovalStatus.APPROVED)

    def test_workflow_approval_specific_validation_helpers(self):
        serializer = WorkflowApprovalSerializer(instance=self.instance)
        for method, attrs in [
            (serializer._validate_rejection, {}),
            (serializer._validate_resubmission, {}),
        ]:
            with self.assertRaises(serializers.ValidationError):
                method(attrs)

        with self.assertRaises(serializers.ValidationError):
            serializer._validate_delegation({"user_id": 999999})
        serializer._validate_delegation({})

        attachment = SimpleNamespace(current_stage=object())
        approval = SimpleNamespace(
            id=1,
            form=SimpleNamespace(id=2),
        )
        with (
            patch(
                "django_workflow_engine.serializers.get_workflow_attachment",
                return_value=attachment,
            ),
            patch(
                "django_workflow_engine.serializers.get_current_approval_for_object",
                return_value=[approval],
            ),
        ):
            with self.assertRaises(serializers.ValidationError):
                serializer._validate_approval({})

        serializer.context["request"] = SimpleNamespace(user=self.user)
        with self.assertRaises(serializers.ValidationError):
            serializer.validate({"action": ApprovalStatus.REJECTED, "reason": ""})

        workflow_attachment = SimpleNamespace(workflow=SimpleNamespace(id=1))
        wrong_stage = SimpleNamespace(
            pipeline=SimpleNamespace(workflow=SimpleNamespace(id=2))
        )
        with (
            patch(
                "django_workflow_engine.serializers.get_workflow_attachment",
                return_value=workflow_attachment,
            ),
            patch(
                "django_workflow_engine.serializers.Stage.objects.get",
                return_value=wrong_stage,
            ),
        ):
            with self.assertRaises(serializers.ValidationError):
                serializer._validate_resubmission({"reason": "retry", "stage_id": 3})
        with (
            patch(
                "django_workflow_engine.serializers.get_workflow_attachment",
                return_value=workflow_attachment,
            ),
            patch(
                "django_workflow_engine.serializers.Stage.objects.get",
                side_effect=__import__(
                    "django_workflow_engine.models", fromlist=["Stage"]
                ).Stage.DoesNotExist,
            ),
        ):
            with self.assertRaises(serializers.ValidationError):
                serializer._validate_resubmission({"reason": "retry", "stage_id": 999})

    def test_workflow_approval_save_and_helper_error_paths(self):
        serializer = WorkflowApprovalSerializer()
        with self.assertRaises(ValueError):
            serializer.save()

        serializer = WorkflowApprovalSerializer(instance=self.instance)
        with self.assertRaises(ValueError):
            serializer._get_delegation_user({"user_id": 999999})

        self.assertEqual(serializer._enrich_form_data({}, None), {})
        approval = SimpleNamespace(
            id=1,
            form=SimpleNamespace(
                id=2,
                form_info=[{"field_name": "name", "field_type": "TEXT"}],
            ),
        )
        with (
            patch(
                "django_workflow_engine.utils.flatten_form_info",
                return_value=[{"field_name": "name"}],
            ),
            patch(
                "django_workflow_engine.utils.enrich_answers",
                return_value=[{"field_name": "name", "answer": "A"}],
            ),
        ):
            enriched = serializer._enrich_form_data({"name": "A"}, approval)
        self.assertEqual(enriched[0]["answer"], "A")

        with patch(
            "django_workflow_engine.serializers.get_workflow_attachment",
            return_value=None,
        ):
            self.assertIsNone(
                serializer._update_workflow_attachment(ApprovalStatus.APPROVED)
            )
        attachment = SimpleNamespace(
            workflow=SimpleNamespace(strategy=WorkflowStrategy.STATUS_GRAPH)
        )
        with patch(
            "django_workflow_engine.serializers.get_workflow_attachment",
            return_value=attachment,
        ):
            self.assertIsNone(
                serializer._update_workflow_attachment(ApprovalStatus.APPROVED)
            )

    def test_status_action_validation_failures_and_success(self):
        serializer = StatusActionSerializer()
        with self.assertRaises(serializers.ValidationError):
            serializer.validate({})
        with self.assertRaises(serializers.ValidationError):
            serializer.validate(
                {
                    "status_node": object(),
                    "action_type": ActionType.AFTER_TRANSITION,
                }
            )
        with self.assertRaises(serializers.ValidationError):
            serializer.validate(
                {
                    "transition": object(),
                    "action_type": ActionType.ON_STATUS_ENTER,
                }
            )
        result = serializer.validate(
            {
                "transition": object(),
                "action_type": ActionType.AFTER_TRANSITION,
            }
        )
        self.assertIsNone(result["workflow"])

    def test_stage_detail_approval_display_branches(self):
        stage = SimpleNamespace(
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "role_selection_strategy": RoleSelectionStrategy.ANYONE,
                    },
                    {
                        "approval_type": ApprovalTypes.USER,
                        "role_selection_strategy": RoleSelectionStrategy.CONSENSUS,
                    },
                    {
                        "approval_type": ApprovalTypes.SELF,
                        "role_selection_strategy": RoleSelectionStrategy.ROUND_ROBIN,
                    },
                    {
                        "approval_type": "custom",
                        "role_selection_strategy": "custom",
                    },
                ]
            }
        )
        serializer = StageDetailSerializer()
        self.assertTrue(serializer.get_has_approvals(stage))
        result = serializer.get_approval_configuration(stage)
        self.assertEqual(result["total_approvals"], 4)

    def test_pipeline_and_workflow_strategy_validation(self):
        pipeline_serializer = PipelineSerializer()
        workflow_only = SimpleNamespace(strategy=WorkflowStrategy.WORKFLOW_ONLY)
        with self.assertRaises(serializers.ValidationError):
            pipeline_serializer.validate({"workflow": workflow_only})

        pipeline_only = SimpleNamespace(strategy=WorkflowStrategy.WORKFLOW_PIPELINE)
        with self.assertRaises(serializers.ValidationError):
            pipeline_serializer.validate(
                {"workflow": pipeline_only, "number_of_stages": 1}
            )
        with self.assertRaises(serializers.ValidationError):
            pipeline_serializer.validate({"workflow": pipeline_only})

        workflow_serializer = WorkFlowSerializer()
        with self.assertRaises(serializers.ValidationError):
            workflow_serializer.validate(
                {
                    "strategy": WorkflowStrategy.WORKFLOW_ONLY,
                    "pipelines": [{}],
                }
            )
        with self.assertRaises(serializers.ValidationError):
            workflow_serializer.validate(
                {
                    "strategy": WorkflowStrategy.WORKFLOW_PIPELINE,
                    "pipelines": [{"stages": []}],
                }
            )
        with self.assertRaises(serializers.ValidationError):
            workflow_serializer.validate(
                {
                    "strategy": WorkflowStrategy.WORKFLOW_PIPELINE,
                    "pipelines": [{}],
                }
            )
        with self.assertRaises(serializers.ValidationError):
            workflow_serializer.validate(
                {
                    "strategy": WorkflowStrategy.WORKFLOW_ONLY,
                    "workflow_info": {"approvals": []},
                }
            )

    def test_stage_validation_and_stage_info_errors(self):
        serializer = StageSerializer()
        with self.assertRaises(serializers.ValidationError):
            serializer.validate({})

        view = SimpleNamespace(kwargs={"pipeline": 999999})
        serializer = StageSerializer(context={"view": view})
        with self.assertRaises(serializers.ValidationError):
            serializer.validate({})

        for value in [
            [],
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
        ]:
            with self.subTest(value=value):
                with self.assertRaises(serializers.ValidationError):
                    serializer.validate_stage_info(value)

    def test_pipeline_create_with_stages_and_actions(self):
        serializer = PipelineSerializer()
        pipeline = SimpleNamespace(id=5)
        with (
            patch(
                "django_workflow_engine.serializers.Pipeline.objects.create",
                return_value=pipeline,
            ),
            patch(
                "django_workflow_engine.serializers.Stage.objects.create"
            ) as create_stage,
            patch(
                "django_workflow_engine.action_management.create_custom_workflow_actions"
            ) as create_actions,
        ):
            created = serializer.create(
                {
                    "name_en": "Pipeline",
                    "number_of_stages": 2,
                    "actions": [{"action_type": "after_approve"}],
                }
            )
        self.assertIs(created, pipeline)
        self.assertEqual(create_stage.call_count, 2)
        create_actions.assert_called_once()

    def test_resubmission_step_preparation_paths(self):
        serializer = WorkflowApprovalSerializer(
            instance=self.instance,
            context={"request": SimpleNamespace(user=self.user)},
        )
        stage = SimpleNamespace(id=5)
        manager = MagicMock()
        manager.get.return_value = stage
        with (
            patch(
                "django_workflow_engine.serializers.Stage.objects.select_related",
                return_value=manager,
            ),
            patch(
                "django_workflow_engine.serializers.get_current_approval_for_object",
                return_value=[],
            ),
        ):
            with self.assertRaises(ValueError):
                serializer._prepare_resubmission_steps({"stage_id": 5})

        builder = MagicMock()
        builder.build_steps.return_value = [{"step": 4}]
        with (
            patch(
                "django_workflow_engine.serializers.Stage.objects.select_related",
                return_value=manager,
            ),
            patch(
                "django_workflow_engine.serializers.get_current_approval_for_object",
                return_value=[SimpleNamespace(step_number=3)],
            ),
            patch(
                "django_workflow_engine.handlers.ApprovalStepBuilder",
                return_value=builder,
            ),
        ):
            steps = serializer._prepare_resubmission_steps({"stage_id": 5})
        self.assertEqual(steps[0]["extra_fields"]["resubmission_stage_id"], 5)

        manager.get.side_effect = __import__(
            "django_workflow_engine.models", fromlist=["Stage"]
        ).Stage.DoesNotExist
        with patch(
            "django_workflow_engine.serializers.Stage.objects.select_related",
            return_value=manager,
        ):
            with self.assertRaises(ValueError):
                serializer._prepare_resubmission_steps({"stage_id": 999})

        serializer.instance = SimpleNamespace(
            pk=2,
            created_by=self.user.pk,
            _meta=SimpleNamespace(label="tests.Target"),
        )
        manager.get.side_effect = None
        manager.get.return_value = stage
        with (
            patch(
                "django_workflow_engine.serializers.Stage.objects.select_related",
                return_value=manager,
            ),
            patch(
                "django_workflow_engine.serializers.get_current_approval_for_object",
                return_value=SimpleNamespace(step_number=1),
            ),
            patch(
                "django_workflow_engine.handlers.ApprovalStepBuilder",
                return_value=builder,
            ),
        ):
            serializer._prepare_resubmission_steps({"stage_id": 5})

        serializer.instance = SimpleNamespace(
            pk=3,
            _meta=SimpleNamespace(label="tests.Target"),
        )
        with (
            patch(
                "django_workflow_engine.serializers.Stage.objects.select_related",
                return_value=manager,
            ),
            patch(
                "django_workflow_engine.serializers.get_current_approval_for_object",
                return_value=SimpleNamespace(step_number=2),
            ),
            patch(
                "django_workflow_engine.handlers.ApprovalStepBuilder",
                return_value=builder,
            ),
        ):
            serializer._prepare_resubmission_steps({"stage_id": 5})

    def test_assigned_approval_display(self):
        serializer = StageDetailSerializer()
        result = serializer.get_approval_configuration(
            SimpleNamespace(
                stage_info={"approvals": [{"approval_type": ApprovalTypes.ASSIGNED}]}
            )
        )
        self.assertEqual(
            result["approvals"][0]["approval_type_display"], "Assigned User Approval"
        )

    def test_save_enriches_form_from_iterable_approval(self):
        serializer = WorkflowApprovalSerializer(
            instance=self.instance,
            context={"request": SimpleNamespace(user=self.user)},
        )
        serializer._validated_data = {
            "action": ApprovalStatus.APPROVED,
            "form_data": {"name": "A"},
        }
        attachment = SimpleNamespace(
            workflow=SimpleNamespace(id=1),
            current_stage=object(),
        )
        with (
            patch(
                "django_workflow_engine.serializers.get_workflow_attachment",
                return_value=attachment,
            ),
            patch(
                "django_workflow_engine.serializers.get_current_approval_for_object",
                return_value=[SimpleNamespace(form=None)],
            ),
            patch.object(
                serializer,
                "_enrich_form_data",
                return_value=[{"answer": "A"}],
            ),
            patch.object(serializer, "_update_workflow_attachment"),
            patch("django_workflow_engine.serializers.advance_flow"),
            patch(
                "django_workflow_engine.strategy_handlers.get_workflow_location",
                return_value="Location",
            ),
        ):
            self.assertIs(serializer.save(), self.instance)

    def test_workflow_and_stage_create_update_remaining_paths(self):
        workflow = SimpleNamespace(id=3, save=MagicMock())
        workflow_serializer = WorkFlowSerializer(
            context={
                "request": SimpleNamespace(user=self.user),
                "company": self.user,
            }
        )
        with (
            patch(
                "django_workflow_engine.serializers.create_workflow",
                return_value=workflow,
            ),
            patch(
                "django_workflow_engine.action_management.create_default_workflow_actions"
            ),
        ):
            created = workflow_serializer.create(
                {
                    "name_en": "Workflow",
                    "name_ar": "Workflow",
                    "description": "Description",
                }
            )
        self.assertIs(created, workflow)

        stage_serializer = StageSerializer()
        pipeline = SimpleNamespace(
            workflow=SimpleNamespace(strategy=WorkflowStrategy.WORKFLOW_ONLY)
        )
        with self.assertRaises(serializers.ValidationError):
            stage_serializer.validate({"pipeline": pipeline})
        pipeline.workflow.strategy = WorkflowStrategy.WORKFLOW_PIPELINE
        with self.assertRaises(serializers.ValidationError):
            stage_serializer.validate({"pipeline": pipeline})

        stage = MagicMock(id=4)
        with (
            patch(
                "rest_framework.serializers.ModelSerializer.create",
                return_value=stage,
            ),
            patch(
                "django_workflow_engine.action_management.create_custom_workflow_actions"
            ) as create_actions,
        ):
            created = stage_serializer.create(
                {
                    "name_en": "Stage",
                    "actions": [{"action_type": "after_approve"}],
                }
            )
        self.assertIs(created, stage)
        create_actions.assert_called_once()

        stage.is_active = True
        stage.stage_info = {"approvals": [{}]}
        stage.pipeline.workflow = MagicMock()
        with (
            patch(
                "django_workflow_engine.serializers.WorkflowAction.objects.filter"
            ) as actions,
            patch(
                "django_workflow_engine.action_management.create_custom_workflow_actions"
            ),
            patch(
                "rest_framework.serializers.ModelSerializer.update",
                return_value=stage,
            ),
        ):
            updated = stage_serializer.update(
                stage,
                {
                    "actions": [{"action_type": "after_approve"}],
                    "stage_info": {"approvals": []},
                },
            )
        actions.return_value.delete.assert_called_once()
        self.assertIs(updated, stage)
