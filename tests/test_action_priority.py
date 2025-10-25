"""Tests for 3-tier action priority system and timing fixes."""

from unittest.mock import MagicMock, Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from django_workflow_engine.action_management import get_effective_actions
from django_workflow_engine.choices import ActionType, WorkflowStatus
from django_workflow_engine.models import Pipeline, Stage, WorkFlow, WorkflowAction
from django_workflow_engine.services import (
    attach_workflow_to_object,
    start_workflow_for_object,
)

User = get_user_model()


@override_settings(WORKFLOW_AUTO_CREATE_ACTIONS=False)
class ActionPrioritySystemTest(TestCase):
    """Test 3-tier action priority system: Database > Settings > Default."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com"
        )

        # Create workflow
        self.workflow = WorkFlow.objects.create(
            name_en="Test Workflow",
            name_ar="سير عمل الاختبار",
            status=WorkflowStatus.ACTIVE,
            is_active=True,
            is_hidden=False,
            created_by=self.user,
        )

        # Create pipeline
        self.pipeline = Pipeline.objects.create(
            workflow=self.workflow,
            name_en="Test Pipeline",
            name_ar="خط أنابيب الاختبار",
            order=1,
            created_by=self.user,
        )

        # Create stage
        self.stage = Stage.objects.create(
            pipeline=self.pipeline,
            name_en="Test Stage",
            name_ar="مرحلة الاختبار",
            order=1,
            created_by=self.user,
        )

    def test_priority_1_stage_level_database_actions(self):
        """Test that stage-level database actions have highest priority."""
        # Create stage-level action
        stage_action = WorkflowAction.objects.create(
            stage=self.stage,
            action_type=ActionType.AFTER_APPROVE,
            function_path="tests.stage_handler",
            is_active=True,
            order=1,
        )

        # Create pipeline and workflow actions (should be ignored)
        WorkflowAction.objects.create(
            pipeline=self.pipeline,
            stage=None,
            action_type=ActionType.AFTER_APPROVE,
            function_path="tests.pipeline_handler",
            is_active=True,
            order=1,
        )
        WorkflowAction.objects.create(
            workflow=self.workflow,
            pipeline=None,
            stage=None,
            action_type=ActionType.AFTER_APPROVE,
            function_path="tests.workflow_handler",
            is_active=True,
            order=1,
        )

        # Get effective actions
        actions = get_effective_actions(
            ActionType.AFTER_APPROVE,
            workflow=self.workflow,
            pipeline=self.pipeline,
            stage=self.stage,
        )

        # Should only return stage action
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].id, stage_action.id)
        self.assertEqual(actions[0].function_path, "tests.stage_handler")

    def test_priority_1_pipeline_level_database_actions(self):
        """Test that pipeline-level actions used when no stage actions."""
        # Create pipeline-level action (no stage actions)
        pipeline_action = WorkflowAction.objects.create(
            pipeline=self.pipeline,
            stage=None,
            action_type=ActionType.AFTER_APPROVE,
            function_path="tests.pipeline_handler",
            is_active=True,
            order=1,
        )

        # Create workflow action (should be ignored)
        WorkflowAction.objects.create(
            workflow=self.workflow,
            pipeline=None,
            stage=None,
            action_type=ActionType.AFTER_APPROVE,
            function_path="tests.workflow_handler",
            is_active=True,
            order=1,
        )

        # Get effective actions
        actions = get_effective_actions(
            ActionType.AFTER_APPROVE,
            workflow=self.workflow,
            pipeline=self.pipeline,
            stage=self.stage,
        )

        # Should only return pipeline action
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].id, pipeline_action.id)
        self.assertEqual(actions[0].function_path, "tests.pipeline_handler")

    def test_priority_1_workflow_level_database_actions(self):
        """Test that workflow-level actions used when no stage/pipeline actions."""
        # Create workflow-level action (no stage/pipeline actions)
        workflow_action = WorkflowAction.objects.create(
            workflow=self.workflow,
            pipeline=None,
            stage=None,
            action_type=ActionType.AFTER_APPROVE,
            function_path="tests.workflow_handler",
            is_active=True,
            order=1,
        )

        # Get effective actions
        actions = get_effective_actions(
            ActionType.AFTER_APPROVE,
            workflow=self.workflow,
            pipeline=self.pipeline,
            stage=self.stage,
        )

        # Should only return workflow action
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].id, workflow_action.id)
        self.assertEqual(actions[0].function_path, "tests.workflow_handler")

    @override_settings(
        WORKFLOW_ACTIONS_CONFIG=[
            {
                "action_type": ActionType.AFTER_APPROVE,
                "function_path": "tests.settings_handler",
                "order": 1,
                "parameters": {"source": "settings"},
            }
        ]
    )
    def test_priority_2_settings_based_actions(self):
        """Test that settings actions used when no database actions."""
        # No database actions created

        # Get effective actions
        actions = get_effective_actions(
            ActionType.AFTER_APPROVE,
            workflow=self.workflow,
            pipeline=self.pipeline,
            stage=self.stage,
        )

        # Should return settings action
        self.assertEqual(len(actions), 1)
        self.assertIsNone(actions[0].id)  # Not saved to DB
        self.assertEqual(actions[0].function_path, "tests.settings_handler")
        self.assertEqual(actions[0].parameters, {"source": "settings"})

    @override_settings(
        WORKFLOW_ACTIONS_CONFIG=[
            {
                "action_type": ActionType.AFTER_APPROVE,
                "function_path": "tests.settings_handler_1",
                "order": 1,
                "parameters": {"priority": 1},
            },
            {
                "action_type": ActionType.AFTER_APPROVE,
                "function_path": "tests.settings_handler_2",
                "order": 2,
                "parameters": {"priority": 2},
            },
        ]
    )
    def test_priority_2_settings_actions_with_order(self):
        """Test that settings actions respect order parameter."""
        # Get effective actions
        actions = get_effective_actions(
            ActionType.AFTER_APPROVE,
            workflow=self.workflow,
            pipeline=self.pipeline,
            stage=self.stage,
        )

        # Should return both settings actions in order
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0].function_path, "tests.settings_handler_1")
        self.assertEqual(actions[0].order, 1)
        self.assertEqual(actions[1].function_path, "tests.settings_handler_2")
        self.assertEqual(actions[1].order, 2)

    def test_priority_3_default_actions_fallback(self):
        """Test that default actions used when no database or settings actions."""
        # No database actions, no settings actions

        # Get effective actions for AFTER_APPROVE (has default)
        actions = get_effective_actions(
            ActionType.AFTER_APPROVE,
            workflow=self.workflow,
            pipeline=self.pipeline,
            stage=self.stage,
        )

        # Should return default action
        self.assertEqual(len(actions), 1)
        self.assertIsNone(actions[0].id)  # Not saved to DB
        self.assertEqual(
            actions[0].function_path,
            "django_workflow_engine.action_handlers.send_approval_notification",
        )

    def test_priority_no_mixing_database_and_settings(self):
        """Test that database actions prevent settings actions from running."""
        # Create database action
        WorkflowAction.objects.create(
            workflow=self.workflow,
            pipeline=None,
            stage=None,
            action_type=ActionType.AFTER_APPROVE,
            function_path="tests.db_handler",
            is_active=True,
            order=1,
        )

        with self.settings(
            WORKFLOW_ACTIONS_CONFIG=[
                {
                    "action_type": ActionType.AFTER_APPROVE,
                    "function_path": "tests.settings_handler",
                    "order": 1,
                }
            ]
        ):
            # Get effective actions
            actions = get_effective_actions(
                ActionType.AFTER_APPROVE,
                workflow=self.workflow,
                pipeline=self.pipeline,
                stage=self.stage,
            )

            # Should only return database action, not settings action
            self.assertEqual(len(actions), 1)
            self.assertIsNotNone(actions[0].id)  # Has DB ID
            self.assertEqual(actions[0].function_path, "tests.db_handler")

    def test_no_actions_for_unknown_action_type(self):
        """Test that no actions returned for action types without any config."""
        # Custom action type that has no default
        custom_action_type = "custom_action"

        # Get effective actions
        actions = get_effective_actions(
            custom_action_type,
            workflow=self.workflow,
            pipeline=self.pipeline,
            stage=self.stage,
        )

        # Should return empty list
        self.assertEqual(len(actions), 0)

    def test_multiple_database_actions_same_level(self):
        """Test multiple actions at same level are all returned in order."""
        # Create multiple workflow-level actions
        action1 = WorkflowAction.objects.create(
            workflow=self.workflow,
            action_type=ActionType.AFTER_APPROVE,
            function_path="tests.handler_1",
            is_active=True,
            order=2,
        )
        action2 = WorkflowAction.objects.create(
            workflow=self.workflow,
            action_type=ActionType.AFTER_APPROVE,
            function_path="tests.handler_2",
            is_active=True,
            order=1,
        )

        # Get effective actions
        actions = get_effective_actions(
            ActionType.AFTER_APPROVE,
            workflow=self.workflow,
            pipeline=self.pipeline,
            stage=self.stage,
        )

        # Should return both actions in order
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0].id, action2.id)  # Order 1 first
        self.assertEqual(actions[1].id, action1.id)  # Order 2 second


@override_settings(WORKFLOW_AUTO_CREATE_ACTIONS=False)
class WorkflowStartTimingTest(TestCase):
    """Test ON_WORKFLOW_START timing fix - runs after approval setup."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="password"
        )

        # Create workflow with proper structure
        self.workflow = WorkFlow.objects.create(
            name_en="Test Workflow",
            name_ar="سير عمل الاختبار",
            status=WorkflowStatus.ACTIVE,
            is_active=True,
            is_hidden=False,
            created_by=self.user,
            company=self.user,  # Required for workflow
        )

        self.pipeline = Pipeline.objects.create(
            workflow=self.workflow,
            name_en="Test Pipeline",
            name_ar="خط أنابيب الاختبار",
            order=1,
            created_by=self.user,
        )

        self.stage = Stage.objects.create(
            pipeline=self.pipeline,
            name_en="Test Stage",
            name_ar="مرحلة الاختبار",
            order=1,
            created_by=self.user,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": self.user.id}]
            },
        )

        # Update workflow active status
        self.workflow.update_active_status()

    @patch("django_workflow_engine.services.trigger_workflow_event")
    @patch("approval_workflow.services.start_flow")
    @patch("django_workflow_engine.utils.build_approval_steps")
    def test_on_workflow_start_runs_after_approval_setup(
        self, mock_build_steps, mock_start_flow, mock_trigger_event
    ):
        """Test that ON_WORKFLOW_START is triggered after start_flow completes."""
        # Mock approval steps
        mock_build_steps.return_value = [
            {"approver": self.user, "order": 1, "approval_type": "approve"}
        ]
        mock_start_flow.return_value = None
        mock_trigger_event.return_value = []

        # Attach and start workflow
        attachment = attach_workflow_to_object(
            self.user, self.workflow, self.user, auto_start=False
        )
        start_workflow_for_object(self.user, self.user)

        # Verify both start_flow and trigger_event were called
        self.assertEqual(mock_start_flow.call_count, 1)
        self.assertEqual(mock_trigger_event.call_count, 1)

        # Verify start_flow was called (means approval cycle was set up)
        self.assertTrue(mock_start_flow.called)

        # Verify trigger_workflow_event was called with ON_WORKFLOW_START
        self.assertTrue(mock_trigger_event.called)
        trigger_call_args = mock_trigger_event.call_args[0]  # Positional args
        trigger_call_kwargs = mock_trigger_event.call_args[1]  # Keyword args

        # Second positional arg should be action_type
        self.assertEqual(trigger_call_args[1], ActionType.ON_WORKFLOW_START)

        # Should have initial_stage and user in kwargs
        self.assertIn("initial_stage", trigger_call_kwargs)
        self.assertIn("user", trigger_call_kwargs)

    @patch("django_workflow_engine.services.trigger_workflow_event")
    @patch("approval_workflow.services.start_flow")
    @patch("django_workflow_engine.utils.build_approval_steps")
    def test_on_workflow_start_has_approval_context(
        self, mock_build_steps, mock_start_flow, mock_trigger_event
    ):
        """Test that ON_WORKFLOW_START receives approval context."""
        # Mock approval steps
        mock_build_steps.return_value = [
            {"approver": self.user, "order": 1, "approval_type": "approve"}
        ]
        mock_trigger_event.return_value = []

        # Attach and start workflow
        attachment = attach_workflow_to_object(
            self.user, self.workflow, self.user, auto_start=False
        )
        start_workflow_for_object(self.user, self.user)

        # Verify trigger_workflow_event was called with correct context
        self.assertTrue(mock_trigger_event.called)
        trigger_call_kwargs = mock_trigger_event.call_args[1]

        # Should have initial_stage and user in context
        self.assertIn("initial_stage", trigger_call_kwargs)
        self.assertIn("user", trigger_call_kwargs)

        # initial_stage should be a Stage instance (cloned from original)
        self.assertIsInstance(trigger_call_kwargs["initial_stage"], Stage)
        self.assertIn("Test Stage", trigger_call_kwargs["initial_stage"].name_en)


@override_settings(WORKFLOW_AUTO_CREATE_ACTIONS=False)
class ActionLoggingTest(TestCase):
    """Test improved logging for action source identification."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com"
        )

        self.workflow = WorkFlow.objects.create(
            name_en="Test Workflow",
            name_ar="سير عمل الاختبار",
            status=WorkflowStatus.ACTIVE,
            is_active=True,
            created_by=self.user,
        )

    def test_database_action_has_id(self):
        """Test that database actions have an ID for logging."""
        action = WorkflowAction.objects.create(
            workflow=self.workflow,
            action_type=ActionType.AFTER_APPROVE,
            function_path="tests.handler",
            is_active=True,
            order=1,
        )

        # Database action should have ID
        self.assertIsNotNone(action.id)

    @override_settings(
        WORKFLOW_ACTIONS_CONFIG=[
            {
                "action_type": ActionType.AFTER_APPROVE,
                "function_path": "tests.handler",
                "order": 1,
            }
        ]
    )
    def test_settings_action_has_no_id(self):
        """Test that settings actions have no ID (not saved to DB)."""
        actions = get_effective_actions(
            ActionType.AFTER_APPROVE, workflow=self.workflow
        )

        # Settings action should not have ID
        self.assertEqual(len(actions), 1)
        self.assertIsNone(actions[0].id)

    def test_default_action_has_no_id(self):
        """Test that default actions have no ID (not saved to DB)."""
        actions = get_effective_actions(
            ActionType.AFTER_APPROVE, workflow=self.workflow
        )

        # Default action should not have ID
        self.assertEqual(len(actions), 1)
        self.assertIsNone(actions[0].id)


@override_settings(WORKFLOW_AUTO_CREATE_ACTIONS=False)
class ActionPriorityEdgeCasesTest(TestCase):
    """Test edge cases for action priority system."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com"
        )

        self.workflow = WorkFlow.objects.create(
            name_en="Test Workflow",
            name_ar="سير عمل الاختبار",
            status=WorkflowStatus.ACTIVE,
            is_active=True,
            created_by=self.user,
        )

        self.pipeline = Pipeline.objects.create(
            workflow=self.workflow,
            name_en="Test Pipeline",
            order=1,
            created_by=self.user,
        )

        self.stage = Stage.objects.create(
            pipeline=self.pipeline, name_en="Test Stage", order=1, created_by=self.user
        )

    def test_inactive_database_actions_are_skipped(self):
        """Test that inactive database actions are not returned."""
        # Create inactive database action
        WorkflowAction.objects.create(
            workflow=self.workflow,
            action_type=ActionType.AFTER_APPROVE,
            function_path="tests.handler",
            is_active=False,  # Inactive
            order=1,
        )

        with self.settings(
            WORKFLOW_ACTIONS_CONFIG=[
                {
                    "action_type": ActionType.AFTER_APPROVE,
                    "function_path": "tests.settings_handler",
                    "order": 1,
                }
            ]
        ):
            # Get effective actions
            actions = get_effective_actions(
                ActionType.AFTER_APPROVE, workflow=self.workflow
            )

            # Should fall through to settings action since DB action is inactive
            self.assertEqual(len(actions), 1)
            self.assertIsNone(actions[0].id)
            self.assertEqual(actions[0].function_path, "tests.settings_handler")

    @override_settings(WORKFLOW_ACTIONS_CONFIG=None)
    def test_none_settings_config_uses_default(self):
        """Test that None settings config falls through to defaults."""
        # Get effective actions with None config
        actions = get_effective_actions(
            ActionType.AFTER_APPROVE, workflow=self.workflow
        )

        # Should return default action
        self.assertEqual(len(actions), 1)
        self.assertEqual(
            actions[0].function_path,
            "django_workflow_engine.action_handlers.send_approval_notification",
        )

    @override_settings(WORKFLOW_ACTIONS_CONFIG=[])
    def test_empty_settings_config_uses_default(self):
        """Test that empty settings config falls through to defaults."""
        # Get effective actions with empty config
        actions = get_effective_actions(
            ActionType.AFTER_APPROVE, workflow=self.workflow
        )

        # Should return default action
        self.assertEqual(len(actions), 1)
        self.assertEqual(
            actions[0].function_path,
            "django_workflow_engine.action_handlers.send_approval_notification",
        )

    @override_settings(
        WORKFLOW_ACTIONS_CONFIG=[
            {
                "action_type": ActionType.AFTER_REJECT,  # Different action type
                "function_path": "tests.handler",
                "order": 1,
            }
        ]
    )
    def test_settings_config_filters_by_action_type(self):
        """Test that settings config correctly filters by action type."""
        # Get actions for AFTER_APPROVE (config has AFTER_REJECT)
        actions = get_effective_actions(
            ActionType.AFTER_APPROVE, workflow=self.workflow
        )

        # Should return default action for AFTER_APPROVE
        self.assertEqual(len(actions), 1)
        self.assertEqual(
            actions[0].function_path,
            "django_workflow_engine.action_handlers.send_approval_notification",
        )
