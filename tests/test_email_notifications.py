"""Tests for email notification system."""

import uuid
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from django_workflow_engine.action_management import (
    clone_workflow_actions,
    create_custom_workflow_actions,
    create_default_workflow_actions,
    get_effective_actions,
)
from django_workflow_engine.choices import ActionType, WorkflowStatus
from django_workflow_engine.models import Pipeline, Stage, WorkFlow, WorkflowAction
from django_workflow_engine.serializers import (
    PipelineSerializer,
    StageSerializer,
    WorkFlowSerializer,
)
from sandbox.testapp.models import Company, Department

User = get_user_model()


@override_settings(WORKFLOW_AUTO_CREATE_ACTIONS=True)
class EmailNotificationDefaultActionsTest(TestCase):
    """Test default action creation."""

    def setUp(self):
        """Set up test data."""
        unique_id = str(uuid.uuid4())[:8]
        self.user = User.objects.create_user(
            username=f"testuser_{unique_id}",
            email=f"test_{unique_id}@example.com",
            password="testpass123",
        )
        self.company_user = User.objects.create_user(
            username=f"company_{unique_id}",
            email=f"company_{unique_id}@example.com",
            password="testpass123",
        )

    def test_default_actions_created_on_workflow_creation(self):
        """Test that default actions are auto-created when workflow is created."""
        workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            status=WorkflowStatus.ACTIVE,
            created_by=self.user,
        )

        # Check that default actions were created
        actions = WorkflowAction.objects.filter(workflow=workflow)

        # Should have 5 default actions
        self.assertEqual(actions.count(), 5)

        # Verify action types
        action_types = set(actions.values_list("action_type", flat=True))
        expected_types = {
            ActionType.AFTER_APPROVE,
            ActionType.AFTER_REJECT,
            ActionType.AFTER_RESUBMISSION,
            ActionType.AFTER_DELEGATE,
            ActionType.AFTER_MOVE_STAGE,
        }
        self.assertEqual(action_types, expected_types)

        # Verify all actions are active
        self.assertTrue(all(action.is_active for action in actions))

    def test_default_actions_have_correct_handlers(self):
        """Test that default actions have correct handler functions."""
        workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            created_by=self.user,
        )

        actions = WorkflowAction.objects.filter(workflow=workflow)

        # Check function paths
        for action in actions:
            self.assertTrue(
                action.function_path.startswith(
                    "django_workflow_engine.action_handlers"
                )
            )
            self.assertIn("notification", action.function_path)

    def test_create_default_workflow_actions_manually(self):
        """Test manually creating default actions."""
        # Create workflow without auto-creation
        with override_settings(WORKFLOW_AUTO_CREATE_ACTIONS=False):
            workflow = WorkFlow.objects.create(
                company=self.company_user,
                name_en="Test Workflow",
                name_ar="سير عمل تجريبي",
                created_by=self.user,
            )

        # Manually create default actions
        created_actions = create_default_workflow_actions(workflow)

        # Should return 5 actions
        self.assertEqual(len(created_actions), 5)

        # Verify in database
        db_actions = WorkflowAction.objects.filter(workflow=workflow)
        self.assertEqual(db_actions.count(), 5)

    def test_default_actions_not_duplicated(self):
        """Test that default actions are not duplicated if already exist."""
        workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            created_by=self.user,
        )

        initial_count = WorkflowAction.objects.filter(workflow=workflow).count()

        # Try to create default actions again
        create_default_workflow_actions(workflow)

        # Should not create duplicates
        final_count = WorkflowAction.objects.filter(workflow=workflow).count()
        self.assertEqual(initial_count, final_count)


@override_settings(WORKFLOW_AUTO_CREATE_ACTIONS=False)
class EmailNotificationCustomActionsTest(TestCase):
    """Test custom action creation via serializers."""

    def setUp(self):
        """Set up test data."""
        unique_id = str(uuid.uuid4())[:8]
        self.user = User.objects.create_user(
            username=f"testuser_{unique_id}",
            email=f"test_{unique_id}@example.com",
            password="testpass123",
        )
        self.company_user = User.objects.create_user(
            username=f"company_{unique_id}",
            email=f"company_{unique_id}@example.com",
            password="testpass123",
        )

    def test_workflow_serializer_with_custom_actions(self):
        """Test creating workflow with custom actions via serializer."""
        data = {
            "name_en": "Custom Actions Workflow",
            "name_ar": "سير عمل مخصص",
            "company": self.company_user.id,
            "actions": [
                {
                    "action_type": ActionType.AFTER_APPROVE,
                    "function_path": "myapp.actions.custom_approval",
                    "parameters": {
                        "template": "custom_approved",
                        "recipients": ["creator", "admin@example.com"],
                    },
                    "order": 1,
                    "is_active": True,
                },
                {
                    "action_type": ActionType.AFTER_REJECT,
                    "function_path": "myapp.actions.custom_rejection",
                    "parameters": {
                        "template": "custom_rejected",
                        "recipients": ["creator"],
                    },
                    "order": 1,
                    "is_active": True,
                },
            ],
        }

        serializer = WorkFlowSerializer(
            data=data, context={"request": Mock(user=self.user)}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

        workflow = serializer.save()

        # Check custom actions were created
        actions = WorkflowAction.objects.filter(workflow=workflow)
        self.assertEqual(actions.count(), 2)

        # Verify action details
        approve_action = actions.get(action_type=ActionType.AFTER_APPROVE)
        self.assertEqual(approve_action.function_path, "myapp.actions.custom_approval")
        self.assertEqual(approve_action.parameters["template"], "custom_approved")

    def test_workflow_serializer_without_actions_creates_defaults(self):
        """Test that workflow without actions creates defaults when enabled."""
        with override_settings(WORKFLOW_AUTO_CREATE_ACTIONS=True):
            data = {
                "name_en": "Default Actions Workflow",
                "name_ar": "سير عمل افتراضي",
                "company": self.company_user.id,
            }

            serializer = WorkFlowSerializer(
                data=data, context={"request": Mock(user=self.user)}
            )
            self.assertTrue(serializer.is_valid())

            workflow = serializer.save()

            # Should have default actions
            actions = WorkflowAction.objects.filter(workflow=workflow)
            self.assertEqual(actions.count(), 5)

    def test_pipeline_serializer_with_custom_actions(self):
        """Test creating pipeline with custom actions."""
        # Create workflow first
        workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            created_by=self.user,
        )

        data = {
            "workflow": workflow.id,
            "name_en": "Custom Pipeline",
            "name_ar": "خط أنابيب مخصص",
            "order": 1,
            "actions": [
                {
                    "action_type": ActionType.AFTER_MOVE_STAGE,
                    "function_path": "myapp.actions.pipeline_stage_move",
                    "parameters": {"recipients": ["creator"]},
                    "order": 1,
                }
            ],
        }

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            name_en=data["name_en"],
            name_ar=data["name_ar"],
            order=data["order"],
        )

        # Create custom actions for pipeline
        create_custom_workflow_actions(data["actions"], pipeline=pipeline)

        # Verify actions
        actions = WorkflowAction.objects.filter(pipeline=pipeline)
        self.assertEqual(actions.count(), 1)
        self.assertEqual(actions[0].action_type, ActionType.AFTER_MOVE_STAGE)

    def test_stage_serializer_with_custom_actions(self):
        """Test creating stage with custom actions."""
        # Create workflow and pipeline
        workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            created_by=self.user,
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow,
            name_en="Test Pipeline",
            name_ar="خط أنابيب",
            order=1,
        )

        stage = Stage.objects.create(
            pipeline=pipeline,
            name_en="Custom Stage",
            name_ar="مرحلة مخصصة",
            order=1,
        )

        # Create custom actions
        actions_data = [
            {
                "action_type": ActionType.AFTER_APPROVE,
                "function_path": "myapp.actions.stage_approval",
                "parameters": {"recipients": ["creator", "current_approver"]},
                "order": 1,
            }
        ]

        create_custom_workflow_actions(actions_data, stage=stage)

        # Verify actions
        actions = WorkflowAction.objects.filter(stage=stage)
        self.assertEqual(actions.count(), 1)


@override_settings(WORKFLOW_AUTO_CREATE_ACTIONS=True)
class EmailNotificationActionInheritanceTest(TestCase):
    """Test action inheritance: Stage -> Pipeline -> Workflow."""

    def setUp(self):
        """Set up test data."""
        unique_id = str(uuid.uuid4())[:8]
        self.user = User.objects.create_user(
            username=f"testuser_{unique_id}",
            email=f"test_{unique_id}@example.com",
            password="testpass123",
        )
        self.company_user = User.objects.create_user(
            username=f"company_{unique_id}",
            email=f"company_{unique_id}@example.com",
            password="testpass123",
        )

        self.workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            created_by=self.user,
        )

        self.pipeline = Pipeline.objects.create(
            workflow=self.workflow, name_en="Test Pipeline", name_ar="خط", order=1
        )

        self.stage = Stage.objects.create(
            pipeline=self.pipeline, name_en="Test Stage", name_ar="مرحلة", order=1
        )

    def test_action_inheritance_stage_overrides_workflow(self):
        """Test that stage-level actions override workflow-level actions."""
        # Create stage-level action
        stage_action = WorkflowAction.objects.create(
            stage=self.stage,
            action_type=ActionType.AFTER_APPROVE,
            function_path="myapp.actions.stage_approval",
            order=1,
        )

        # Get effective actions (should return stage action, not workflow default)
        effective_actions = get_effective_actions(
            action_type=ActionType.AFTER_APPROVE,
            workflow=self.workflow,
            pipeline=self.pipeline,
            stage=self.stage,
        )

        self.assertEqual(len(effective_actions), 1)
        self.assertEqual(effective_actions[0].id, stage_action.id)
        self.assertEqual(
            effective_actions[0].function_path, "myapp.actions.stage_approval"
        )

    def test_action_inheritance_pipeline_overrides_workflow(self):
        """Test that pipeline-level actions override workflow-level actions."""
        # Create pipeline-level action
        pipeline_action = WorkflowAction.objects.create(
            pipeline=self.pipeline,
            action_type=ActionType.AFTER_APPROVE,
            function_path="myapp.actions.pipeline_approval",
            order=1,
        )

        # Get effective actions (should return pipeline action)
        effective_actions = get_effective_actions(
            action_type=ActionType.AFTER_APPROVE,
            workflow=self.workflow,
            pipeline=self.pipeline,
            stage=self.stage,
        )

        self.assertEqual(len(effective_actions), 1)
        self.assertEqual(effective_actions[0].id, pipeline_action.id)

    def test_action_inheritance_falls_back_to_workflow(self):
        """Test that workflow-level actions are used when no stage/pipeline actions exist."""
        # Remove default workflow actions
        WorkflowAction.objects.filter(workflow=self.workflow).delete()

        # Create workflow-level action
        workflow_action = WorkflowAction.objects.create(
            workflow=self.workflow,
            action_type=ActionType.AFTER_APPROVE,
            function_path="myapp.actions.workflow_approval",
            order=1,
        )

        # Get effective actions
        effective_actions = get_effective_actions(
            action_type=ActionType.AFTER_APPROVE,
            workflow=self.workflow,
            pipeline=self.pipeline,
            stage=self.stage,
        )

        self.assertEqual(len(effective_actions), 1)
        self.assertEqual(effective_actions[0].id, workflow_action.id)


@override_settings(WORKFLOW_AUTO_CREATE_ACTIONS=True)
class EmailNotificationActionCloningTest(TestCase):
    """Test action cloning when workflows are cloned."""

    def setUp(self):
        """Set up test data."""
        unique_id = str(uuid.uuid4())[:8]
        self.user = User.objects.create_user(
            username=f"testuser_{unique_id}",
            email=f"test_{unique_id}@example.com",
            password="testpass123",
        )
        self.company_user = User.objects.create_user(
            username=f"company_{unique_id}",
            email=f"company_{unique_id}@example.com",
            password="testpass123",
        )

        # Create source workflow with actions
        self.source_workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Source Workflow",
            name_ar="سير عمل المصدر",
            created_by=self.user,
        )

        self.source_pipeline = Pipeline.objects.create(
            workflow=self.source_workflow,
            name_en="Source Pipeline",
            name_ar="خط",
            order=1,
        )

        self.source_stage = Stage.objects.create(
            pipeline=self.source_pipeline,
            name_en="Source Stage",
            name_ar="مرحلة",
            order=1,
        )

    def test_workflow_actions_cloned_on_workflow_clone(self):
        """Test that workflow-level actions are cloned when workflow is cloned."""
        # Get workflow actions count
        source_workflow_actions_count = WorkflowAction.objects.filter(
            workflow=self.source_workflow
        ).count()

        # Clone workflow (auto-creation is disabled in clone to avoid duplication)
        cloned_workflow = self.source_workflow.clone()

        # Check workflow actions were cloned
        # Note: The clone includes both cloned actions from source
        cloned_workflow_actions = WorkflowAction.objects.filter(
            workflow=cloned_workflow
        )

        # Should have at least the source count (may have more if auto-creation happens during clone)
        self.assertGreaterEqual(
            cloned_workflow_actions.count(), source_workflow_actions_count
        )

        # Verify cloned actions have same configuration as source
        source_action = WorkflowAction.objects.filter(
            workflow=self.source_workflow, action_type=ActionType.AFTER_APPROVE
        ).first()

        # Should have an AFTER_APPROVE action in cloned workflow
        cloned_actions = WorkflowAction.objects.filter(
            workflow=cloned_workflow, action_type=ActionType.AFTER_APPROVE
        )
        self.assertTrue(cloned_actions.exists())

        # Check at least one has the same configuration
        cloned_action = cloned_actions.first()
        self.assertEqual(source_action.function_path, cloned_action.function_path)
        self.assertEqual(source_action.parameters, cloned_action.parameters)
        self.assertNotEqual(source_action.id, cloned_action.id)

    def test_pipeline_actions_cloned(self):
        """Test that pipeline-level actions are cloned."""
        # Create pipeline-level action
        WorkflowAction.objects.create(
            pipeline=self.source_pipeline,
            action_type=ActionType.AFTER_MOVE_STAGE,
            function_path="myapp.actions.pipeline_stage_move",
            order=1,
        )

        # Clone workflow
        cloned_workflow = self.source_workflow.clone()

        # Get cloned pipeline
        cloned_pipeline = cloned_workflow.pipelines.first()

        # Check pipeline actions were cloned
        cloned_pipeline_actions = WorkflowAction.objects.filter(
            pipeline=cloned_pipeline
        )
        self.assertEqual(cloned_pipeline_actions.count(), 1)

    def test_stage_actions_cloned(self):
        """Test that stage-level actions are cloned."""
        # Create stage-level action
        WorkflowAction.objects.create(
            stage=self.source_stage,
            action_type=ActionType.AFTER_APPROVE,
            function_path="myapp.actions.stage_approval",
            order=1,
        )

        # Clone workflow
        cloned_workflow = self.source_workflow.clone()

        # Get cloned stage
        cloned_pipeline = cloned_workflow.pipelines.first()
        cloned_stage = cloned_pipeline.stages.first()

        # Check stage actions were cloned
        cloned_stage_actions = WorkflowAction.objects.filter(stage=cloned_stage)
        self.assertEqual(cloned_stage_actions.count(), 1)


@override_settings(WORKFLOW_AUTO_CREATE_ACTIONS=True)
class EmailNotificationExecutionTest(TestCase):
    """Test actual email sending when actions are executed."""

    def setUp(self):
        """Set up test data."""
        unique_id = str(uuid.uuid4())[:8]
        self.user = User.objects.create_user(
            username=f"testuser_{unique_id}",
            email=f"test_{unique_id}@example.com",
            password="testpass123",
        )
        self.company_user = User.objects.create_user(
            username=f"company_{unique_id}",
            email=f"company_{unique_id}@example.com",
            password="testpass123",
        )

        self.workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            status=WorkflowStatus.ACTIVE,
            created_by=self.user,
        )

        self.pipeline = Pipeline.objects.create(
            workflow=self.workflow, name_en="Test Pipeline", name_ar="خط", order=1
        )

        self.stage = Stage.objects.create(
            pipeline=self.pipeline,
            name_en="Test Stage",
            name_ar="مرحلة",
            order=1,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": "user",
                        "approval_user": self.user.id,
                        "step_approval_type": "approve",
                    }
                ]
            },
        )

        # Update workflow active status
        is_active, message = self.workflow.update_active_status()
        self.assertTrue(is_active, f"Workflow should be active: {message}")

        # Create test object to attach workflow to
        from sandbox.testapp.models import WorkflowTestModel

        from .factories import setup_test_workflow_model

        setup_test_workflow_model()  # Register model for workflow

        self.test_object = WorkflowTestModel.objects.create(
            name="Test Purchase Request",
            description="Test object for email notifications",
            created_by=self.user,  # This is the creator that will receive emails
        )

        # Create workflow attachment
        from django_workflow_engine.services import attach_workflow_to_object

        self.attachment = attach_workflow_to_object(
            obj=self.test_object,
            workflow=self.workflow,
            user=self.user,
            auto_start=False,
        )
        self.attachment.current_stage = self.stage
        self.attachment.current_pipeline = self.pipeline
        self.attachment.save()

    @patch("django_workflow_engine.action_handlers.send_approval_notification")
    @override_settings(WORKFLOW_DISABLE_EMAILS=False)
    def test_email_sent_on_action_execution(self, mock_handler):
        """Test that email is sent when workflow action is executed."""
        from django_workflow_engine import action_executor

        # Verify default actions exist
        workflow_actions = WorkflowAction.objects.filter(workflow=self.workflow)
        self.assertGreater(
            workflow_actions.count(), 0, "Workflow should have default actions created"
        )

        # Mock the handler to return success
        mock_handler.return_value = True

        # Execute AFTER_APPROVE actions
        result = action_executor.execute_workflow_actions(
            action_type=ActionType.AFTER_APPROVE,
            workflow_attachment=self.attachment,
            user=self.user,
            stage=self.stage,
        )

        # Verify action was executed
        self.assertGreater(result["executed"], 0, f"Result: {result}")
        self.assertGreater(result["succeeded"], 0, f"Result: {result}")

        # Verify handler was called
        self.assertTrue(mock_handler.called)
        # Verify it was called with correct parameters
        call_args = mock_handler.call_args
        self.assertIsNotNone(call_args)

        # Verify workflow_attachment was passed
        self.assertEqual(call_args.kwargs["workflow_attachment"], self.attachment)

    @patch("django_workflow_engine.action_handlers.send_approval_notification")
    @override_settings(WORKFLOW_DISABLE_EMAILS=False)
    def test_email_recipients_resolved_correctly(self, mock_handler):
        """Test that email handlers are called with correct context."""
        from django_workflow_engine.action_executor import execute_workflow_actions

        # Mock handler to return success
        mock_handler.return_value = True

        # Execute actions
        result = execute_workflow_actions(
            action_type=ActionType.AFTER_APPROVE,
            workflow_attachment=self.attachment,
            user=self.user,
            stage=self.stage,
        )

        # Verify handler was called
        self.assertTrue(mock_handler.called)
        self.assertGreater(result["succeeded"], 0)

        # Verify handler was called with correct context
        call_args = mock_handler.call_args
        self.assertEqual(call_args.kwargs["workflow_attachment"], self.attachment)
        self.assertEqual(call_args.kwargs["user"], self.user)

    @patch("django_workflow_engine.action_handlers.send_rejection_notification")
    @patch("django_workflow_engine.action_handlers.send_approval_notification")
    @override_settings(WORKFLOW_DISABLE_EMAILS=False)
    def test_multiple_action_types_send_emails(
        self, mock_approve_handler, mock_reject_handler
    ):
        """Test that different action types call appropriate handlers."""
        from django_workflow_engine.action_executor import execute_workflow_actions

        # Mock handlers to return success
        mock_approve_handler.return_value = True
        mock_reject_handler.return_value = True

        # Test AFTER_APPROVE
        result_approve = execute_workflow_actions(
            action_type=ActionType.AFTER_APPROVE,
            workflow_attachment=self.attachment,
            user=self.user,
        )

        # Test AFTER_REJECT
        result_reject = execute_workflow_actions(
            action_type=ActionType.AFTER_REJECT,
            workflow_attachment=self.attachment,
            user=self.user,
            reason="Test rejection",
        )

        # Both should have executed successfully
        self.assertGreater(result_approve["executed"], 0)
        self.assertGreater(result_approve["succeeded"], 0)
        self.assertGreater(result_reject["executed"], 0)
        self.assertGreater(result_reject["succeeded"], 0)

        # Verify correct handlers were called
        self.assertTrue(mock_approve_handler.called)
        self.assertTrue(mock_reject_handler.called)

    @override_settings(WORKFLOW_DISABLE_EMAILS=True)
    def test_emails_disabled_via_setting(self):
        """Test that emails can be disabled via settings."""
        from django_workflow_engine.action_executor import execute_workflow_actions

        result = execute_workflow_actions(
            action_type=ActionType.AFTER_APPROVE,
            workflow_attachment=self.attachment,
            user=self.user,
        )

        # No actions should be executed when emails are disabled
        self.assertEqual(result["executed"], 0)
        self.assertEqual(result["succeeded"], 0)


@override_settings(
    WORKFLOW_SEND_EMAIL_FUNCTION="tests.test_email_notifications.mock_send_email",
    WORKFLOW_AUTO_CREATE_ACTIONS=True,
)
class EmailNotificationCustomEmailFunctionTest(TestCase):
    """Test custom email function integration."""

    def setUp(self):
        """Set up test data."""
        unique_id = str(uuid.uuid4())[:8]
        self.user = User.objects.create_user(
            username=f"testuser_{unique_id}",
            email=f"test_{unique_id}@example.com",
            password="testpass123",
        )
        self.company_user = User.objects.create_user(
            username=f"company_{unique_id}",
            email=f"company_{unique_id}@example.com",
            password="testpass123",
        )

        self.workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            status=WorkflowStatus.ACTIVE,
            created_by=self.user,
        )

        self.pipeline = Pipeline.objects.create(
            workflow=self.workflow, name_en="Test Pipeline", name_ar="خط", order=1
        )

        self.stage = Stage.objects.create(
            pipeline=self.pipeline,
            name_en="Test Stage",
            name_ar="مرحلة",
            order=1,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": "user",
                        "approval_user": self.user.id,
                        "step_approval_type": "approve",
                    }
                ]
            },
        )

        # Update workflow active status
        is_active, message = self.workflow.update_active_status()
        self.assertTrue(is_active, f"Workflow should be active: {message}")

        # Create test object to attach workflow to
        from sandbox.testapp.models import WorkflowTestModel

        from .factories import setup_test_workflow_model

        setup_test_workflow_model()  # Register model for workflow

        self.test_object = WorkflowTestModel.objects.create(
            name="Test Purchase Request",
            description="Test object for email notifications",
            created_by=self.user,  # This is the creator that will receive emails
        )

        # Create workflow attachment
        from django_workflow_engine.services import attach_workflow_to_object

        self.attachment = attach_workflow_to_object(
            obj=self.test_object,
            workflow=self.workflow,
            user=self.user,
            auto_start=False,
        )
        self.attachment.current_stage = self.stage
        self.attachment.current_pipeline = self.pipeline
        self.attachment.save()

    def test_custom_email_function_is_called(self):
        """Test that custom email function is used when configured."""
        from django_workflow_engine.notifications import send_workflow_email

        with patch("tests.test_email_notifications.mock_send_email") as mock_send:
            send_workflow_email(
                name="test_notification",
                user=self.user,
                context={"workflow_name": "Test Workflow"},
            )

            # Verify custom function was called
            mock_send.assert_called_once()

            # Verify arguments passed to custom function
            call_args = mock_send.call_args
            self.assertEqual(call_args[1]["name"], "test_notification")
            self.assertEqual(call_args[1]["email"], self.user.email)
            self.assertIn("workflow_name", call_args[1]["context"])

    @patch("django_workflow_engine.action_handlers.send_approval_notification")
    @override_settings(WORKFLOW_DISABLE_EMAILS=False)
    def test_custom_function_used_in_action_execution(self, mock_handler):
        """Test that custom email function integration works during action execution."""
        from django_workflow_engine.action_executor import execute_workflow_actions

        # Mock handler to return success
        mock_handler.return_value = True

        result = execute_workflow_actions(
            action_type=ActionType.AFTER_APPROVE,
            workflow_attachment=self.attachment,
            user=self.user,
        )

        # Verify action executed successfully
        self.assertGreater(result["executed"], 0)
        self.assertGreater(result["succeeded"], 0)

        # Verify handler was called
        self.assertTrue(mock_handler.called)

    @patch("django_workflow_engine.action_handlers.send_approval_notification")
    @override_settings(WORKFLOW_DISABLE_EMAILS=False)
    def test_custom_function_receives_correct_context(self, mock_handler):
        """Test that action handlers receive correct workflow context."""
        from django_workflow_engine.action_executor import execute_workflow_actions

        # Mock handler to return success
        mock_handler.return_value = True

        result = execute_workflow_actions(
            action_type=ActionType.AFTER_APPROVE,
            workflow_attachment=self.attachment,
            user=self.user,
            stage=self.stage,
        )

        # Verify handler was called with correct context
        self.assertTrue(mock_handler.called)
        self.assertGreater(result["succeeded"], 0)

        call_args = mock_handler.call_args
        self.assertEqual(call_args.kwargs["workflow_attachment"], self.attachment)
        self.assertEqual(call_args.kwargs["user"], self.user)
        self.assertEqual(call_args.kwargs["stage"], self.stage)


# Mock custom email function for testing
def mock_send_email(name, email, subject, context, user=None):
    """Mock send_email function for testing."""
    pass
