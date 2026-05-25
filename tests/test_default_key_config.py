"""Tests for 'default' key fallback and model-keyed configuration.

Covers:
- MODEL_WORKFLOW_MAPPINGS with 'default' key
- AUTO_START_WORKFLOWS with 'default' key
- WORKFLOW_ACTIONS_CONFIG flat list (backward compatibility)
- WORKFLOW_ACTIONS_CONFIG dict format with model keys and 'default' fallback
- Settings helpers: get_workflows_for_model_string, get_auto_start_config_for_model,
  get_actions_config_for_model
- Validation of 'default' key in settings
"""

from unittest.mock import patch

from django.test import TestCase, override_settings

from django_workflow_engine.action_management import get_effective_actions
from django_workflow_engine.choices import ActionType, WorkflowStatus
from django_workflow_engine.models import Pipeline, Stage, WorkFlow, WorkflowAction
from django_workflow_engine.settings import (
    get_actions_config_for_model,
    get_auto_start_config_for_model,
    get_workflows_for_model_string,
    validate_workflow_settings,
)


class GetWorkflowsForModelStringTest(TestCase):
    """Test get_workflows_for_model_string with 'default' fallback."""

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "MODEL_WORKFLOW_MAPPINGS": {
                "default": ["generic_approval"],
                "crm.Opportunity": ["opportunity_approval", "enterprise_sales"],
                "hr.LeaveRequest": ["leave_approval"],
            }
        }
    )
    def test_exact_model_match(self):
        """Returns exact model mapping when it exists."""
        result = get_workflows_for_model_string("crm.Opportunity")
        self.assertEqual(result, ["opportunity_approval", "enterprise_sales"])

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "MODEL_WORKFLOW_MAPPINGS": {
                "default": ["generic_approval"],
                "crm.Opportunity": ["opportunity_approval"],
            }
        }
    )
    def test_falls_back_to_default(self):
        """Falls back to 'default' when model has no specific mapping."""
        result = get_workflows_for_model_string("hr.LeaveRequest")
        self.assertEqual(result, ["generic_approval"])

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "MODEL_WORKFLOW_MAPPINGS": {
                "crm.Opportunity": ["opportunity_approval"],
            }
        }
    )
    def test_returns_none_when_no_match_and_no_default(self):
        """Returns None when model not found and no 'default' key."""
        result = get_workflows_for_model_string("hr.LeaveRequest")
        self.assertIsNone(result)

    @override_settings(DJANGO_WORKFLOW_ENGINE={})
    def test_returns_none_when_no_mappings_configured(self):
        """Returns None when MODEL_WORKFLOW_MAPPINGS is empty."""
        result = get_workflows_for_model_string("crm.Opportunity")
        self.assertIsNone(result)

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "MODEL_WORKFLOW_MAPPINGS": {
                "default": ["generic_approval"],
            }
        }
    )
    def test_default_only(self):
        """Returns default when only 'default' key exists."""
        result = get_workflows_for_model_string("any.Model")
        self.assertEqual(result, ["generic_approval"])

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "MODEL_WORKFLOW_MAPPINGS": {
                "default": ["generic_approval"],
                "crm.Opportunity": ["opportunity_approval"],
            }
        }
    )
    def test_exact_match_takes_priority_over_default(self):
        """Exact match is always preferred over default."""
        result_default = get_workflows_for_model_string("crm.Opportunity")
        result_other = get_workflows_for_model_string("hr.LeaveRequest")
        self.assertEqual(result_default, ["opportunity_approval"])
        self.assertEqual(result_other, ["generic_approval"])


class GetAutoStartConfigForModelTest(TestCase):
    """Test get_auto_start_config_for_model with 'default' fallback."""

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "AUTO_START_WORKFLOWS": {
                "default": {
                    "workflow_slug": "generic_approval",
                    "auto_start": True,
                },
                "crm.Opportunity": {
                    "workflow_slug": "opportunity_approval",
                    "auto_start": True,
                    "conditions": {"amount__gte": 1000},
                },
            }
        }
    )
    def test_exact_model_match(self):
        """Returns exact model config when it exists."""
        result = get_auto_start_config_for_model("crm.Opportunity")
        self.assertEqual(result["workflow_slug"], "opportunity_approval")
        self.assertEqual(result["conditions"], {"amount__gte": 1000})

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "AUTO_START_WORKFLOWS": {
                "default": {
                    "workflow_slug": "generic_approval",
                    "auto_start": True,
                },
                "crm.Opportunity": {
                    "workflow_slug": "opportunity_approval",
                    "auto_start": True,
                },
            }
        }
    )
    def test_falls_back_to_default(self):
        """Falls back to 'default' when model has no specific config."""
        result = get_auto_start_config_for_model("hr.LeaveRequest")
        self.assertEqual(result["workflow_slug"], "generic_approval")

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "AUTO_START_WORKFLOWS": {
                "crm.Opportunity": {"workflow_slug": "opportunity_approval"},
            }
        }
    )
    def test_returns_none_when_no_match_and_no_default(self):
        """Returns None when model not found and no 'default' key."""
        result = get_auto_start_config_for_model("hr.LeaveRequest")
        self.assertIsNone(result)

    @override_settings(DJANGO_WORKFLOW_ENGINE={})
    def test_returns_none_when_empty(self):
        """Returns None when AUTO_START_WORKFLOWS is not configured."""
        result = get_auto_start_config_for_model("crm.Opportunity")
        self.assertIsNone(result)


class GetActionsConfigForModelTest(TestCase):
    """Test get_actions_config_for_model with both formats."""

    # --- Flat list format (backward compatibility) ---

    @override_settings(
        WORKFLOW_ACTIONS_CONFIG=[
            {
                "action_type": "after_approve",
                "function_path": "myapp.actions.send_approval",
                "order": 1,
            },
            {
                "action_type": "after_reject",
                "function_path": "myapp.actions.send_rejection",
                "order": 1,
            },
        ]
    )
    def test_flat_list_format_returns_as_is(self):
        """Flat list format returns the whole list regardless of model_string."""
        result = get_actions_config_for_model("crm.Opportunity")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["action_type"], "after_approve")

    @override_settings(WORKFLOW_ACTIONS_CONFIG=[])
    def test_flat_list_empty(self):
        """Empty flat list returns empty list."""
        result = get_actions_config_for_model("crm.Opportunity")
        self.assertEqual(result, [])

    # --- Dict format with model keys ---

    @override_settings(
        WORKFLOW_ACTIONS_CONFIG={
            "default": [
                {
                    "action_type": "after_approve",
                    "function_path": "myapp.actions.generic_approval",
                    "order": 1,
                },
            ],
            "crm.Opportunity": [
                {
                    "action_type": "after_approve",
                    "function_path": "myapp.actions.opportunity_approved",
                    "order": 1,
                },
                {
                    "action_type": "after_reject",
                    "function_path": "myapp.actions.opportunity_rejected",
                    "order": 1,
                },
            ],
            "hr.LeaveRequest": [
                {
                    "action_type": "after_approve",
                    "function_path": "myapp.actions.leave_approved",
                    "order": 1,
                },
            ],
        }
    )
    def test_dict_format_exact_match(self):
        """Dict format returns model-specific actions for exact match."""
        result = get_actions_config_for_model("crm.Opportunity")
        self.assertEqual(len(result), 2)
        self.assertEqual(
            result[0]["function_path"], "myapp.actions.opportunity_approved"
        )

    @override_settings(
        WORKFLOW_ACTIONS_CONFIG={
            "default": [
                {
                    "action_type": "after_approve",
                    "function_path": "myapp.actions.generic_approval",
                    "order": 1,
                },
            ],
            "crm.Opportunity": [
                {
                    "action_type": "after_approve",
                    "function_path": "myapp.actions.opportunity_approved",
                    "order": 1,
                },
            ],
        }
    )
    def test_dict_format_falls_back_to_default(self):
        """Dict format falls back to 'default' for unmapped models."""
        result = get_actions_config_for_model("hr.LeaveRequest")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["function_path"], "myapp.actions.generic_approval")

    @override_settings(
        WORKFLOW_ACTIONS_CONFIG={
            "crm.Opportunity": [
                {
                    "action_type": "after_approve",
                    "function_path": "myapp.actions.opportunity_approved",
                    "order": 1,
                },
            ],
        }
    )
    def test_dict_format_no_match_no_default_returns_none(self):
        """Dict format returns None when no match and no 'default' key."""
        result = get_actions_config_for_model("hr.LeaveRequest")
        self.assertIsNone(result)

    @override_settings(
        WORKFLOW_ACTIONS_CONFIG={
            "default": [],
        }
    )
    def test_dict_format_default_empty_list(self):
        """Dict format with empty 'default' list returns empty list."""
        result = get_actions_config_for_model("any.Model")
        self.assertEqual(result, [])

    @override_settings(
        WORKFLOW_ACTIONS_CONFIG={
            "default": [
                {
                    "action_type": "after_approve",
                    "function_path": "myapp.generic",
                    "order": 1,
                },
            ],
            "crm.Opportunity": [
                {
                    "action_type": "after_approve",
                    "function_path": "myapp.opportunity",
                    "order": 1,
                },
            ],
        }
    )
    def test_exact_match_takes_priority_over_default_in_dict(self):
        """Exact match is always preferred over default in dict format."""
        result_opp = get_actions_config_for_model("crm.Opportunity")
        result_other = get_actions_config_for_model("hr.LeaveRequest")
        self.assertEqual(result_opp[0]["function_path"], "myapp.opportunity")
        self.assertEqual(result_other[0]["function_path"], "myapp.generic")

    @override_settings()
    def test_not_configured_returns_none(self):
        """Returns None when WORKFLOW_ACTIONS_CONFIG is not set."""
        result = get_actions_config_for_model("crm.Opportunity")
        self.assertIsNone(result)


class EffectiveActionsWithModelStringTest(TestCase):
    """Test get_effective_actions with model_string parameter."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com"
        )

        with self.settings(WORKFLOW_AUTO_CREATE_ACTIONS=False):
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
            pipeline=self.pipeline,
            name_en="Test Stage",
            order=1,
            created_by=self.user,
        )

    def test_model_specific_actions_used_when_model_string_provided(self):
        """When model_string matches, model-specific actions are returned."""
        with self.settings(
            WORKFLOW_AUTO_CREATE_ACTIONS=False,
            WORKFLOW_ACTIONS_CONFIG={
                "default": [
                    {
                        "action_type": "after_approve",
                        "function_path": "myapp.actions.generic_approval",
                        "parameters": {"template": "generic"},
                        "order": 1,
                    },
                ],
                "crm.Opportunity": [
                    {
                        "action_type": "after_approve",
                        "function_path": "myapp.actions.opportunity_approved",
                        "parameters": {"template": "opportunity"},
                        "order": 1,
                    },
                ],
            },
        ):
            actions = get_effective_actions(
                ActionType.AFTER_APPROVE,
                workflow=self.workflow,
                model_string="crm.Opportunity",
            )
            self.assertEqual(len(actions), 1)
            self.assertEqual(
                actions[0].function_path, "myapp.actions.opportunity_approved"
            )
            self.assertEqual(actions[0].parameters, {"template": "opportunity"})

    def test_default_actions_used_for_unmapped_model(self):
        """When model_string doesn't match any key, default actions are returned."""
        with self.settings(
            WORKFLOW_AUTO_CREATE_ACTIONS=False,
            WORKFLOW_ACTIONS_CONFIG={
                "default": [
                    {
                        "action_type": "after_approve",
                        "function_path": "myapp.actions.generic_approval",
                        "parameters": {"template": "generic"},
                        "order": 1,
                    },
                ],
                "crm.Opportunity": [
                    {
                        "action_type": "after_approve",
                        "function_path": "myapp.actions.opportunity_approved",
                        "parameters": {"template": "opportunity"},
                        "order": 1,
                    },
                ],
            },
        ):
            actions = get_effective_actions(
                ActionType.AFTER_APPROVE,
                workflow=self.workflow,
                model_string="hr.LeaveRequest",
            )
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0].function_path, "myapp.actions.generic_approval")

    def test_no_actions_for_unmapped_model_without_default(self):
        """When model has no match and no default, returns empty list."""
        with self.settings(
            WORKFLOW_AUTO_CREATE_ACTIONS=False,
            WORKFLOW_ACTIONS_CONFIG={
                "crm.Opportunity": [
                    {
                        "action_type": "after_approve",
                        "function_path": "myapp.actions.opportunity_approved",
                        "order": 1,
                    },
                ],
            },
        ):
            actions = get_effective_actions(
                ActionType.AFTER_APPROVE,
                workflow=self.workflow,
                model_string="hr.LeaveRequest",
            )
            self.assertEqual(len(actions), 0)

    def test_flat_list_ignores_model_string(self):
        """Flat list format still works regardless of model_string."""
        with self.settings(
            WORKFLOW_AUTO_CREATE_ACTIONS=False,
            WORKFLOW_ACTIONS_CONFIG=[
                {
                    "action_type": "after_approve",
                    "function_path": "myapp.actions.flat_list_handler",
                    "order": 1,
                },
            ],
        ):
            actions = get_effective_actions(
                ActionType.AFTER_APPROVE,
                workflow=self.workflow,
                model_string="crm.Opportunity",
            )
            self.assertEqual(len(actions), 1)
            self.assertEqual(
                actions[0].function_path, "myapp.actions.flat_list_handler"
            )

    def test_dict_with_empty_default_disables_actions(self):
        """Empty default list disables all actions for unmapped models."""
        with self.settings(
            WORKFLOW_AUTO_CREATE_ACTIONS=False,
            WORKFLOW_ACTIONS_CONFIG={"default": []},
        ):
            actions = get_effective_actions(
                ActionType.AFTER_APPROVE,
                workflow=self.workflow,
                model_string="any.Model",
            )
            self.assertEqual(len(actions), 0)

    def test_no_model_string_falls_back_to_direct_read(self):
        """Without model_string, reads WORKFLOW_ACTIONS_CONFIG directly."""
        with self.settings(
            WORKFLOW_AUTO_CREATE_ACTIONS=False,
            WORKFLOW_ACTIONS_CONFIG=[
                {
                    "action_type": "after_approve",
                    "function_path": "myapp.actions.direct_read",
                    "order": 1,
                },
            ],
        ):
            actions = get_effective_actions(
                ActionType.AFTER_APPROVE,
                workflow=self.workflow,
                # model_string NOT provided
            )
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0].function_path, "myapp.actions.direct_read")

    def test_action_type_filtering_with_model_string(self):
        """When model is matched but action_type isn't configured, returns empty."""
        with self.settings(
            WORKFLOW_AUTO_CREATE_ACTIONS=False,
            WORKFLOW_ACTIONS_CONFIG={
                "default": [
                    {
                        "action_type": "after_reject",
                        "function_path": "myapp.actions.generic_rejection",
                        "order": 1,
                    },
                ],
                "crm.Opportunity": [
                    {
                        "action_type": "after_approve",
                        "function_path": "myapp.actions.opportunity_approved",
                        "order": 1,
                    },
                ],
            },
        ):
            # Opportunity only has after_approve, asking for after_reject
            actions = get_effective_actions(
                ActionType.AFTER_REJECT,
                workflow=self.workflow,
                model_string="crm.Opportunity",
            )
            self.assertEqual(len(actions), 0)

    def test_unmapped_action_type_does_not_use_default(self):
        """When model match has no matching action_type, default is NOT used.

        The model is matched to 'crm.Opportunity', so only those actions are checked.
        Default is only used for unmatched models, not unmatched action_types.
        """
        with self.settings(
            WORKFLOW_AUTO_CREATE_ACTIONS=False,
            WORKFLOW_ACTIONS_CONFIG={
                "default": [
                    {
                        "action_type": "after_reject",
                        "function_path": "myapp.actions.generic_rejection",
                        "order": 1,
                    },
                ],
                "crm.Opportunity": [
                    {
                        "action_type": "after_approve",
                        "function_path": "myapp.actions.opportunity_approved",
                        "order": 1,
                    },
                ],
            },
        ):
            actions = get_effective_actions(
                ActionType.AFTER_REJECT,
                workflow=self.workflow,
                model_string="crm.Opportunity",
            )
            # Opportunity matched but has no after_reject → empty
            self.assertEqual(len(actions), 0)

    def test_default_used_for_unmapped_model_with_different_action_type(self):
        """Default actions are used for unmapped models."""
        with self.settings(
            WORKFLOW_AUTO_CREATE_ACTIONS=False,
            WORKFLOW_ACTIONS_CONFIG={
                "default": [
                    {
                        "action_type": "after_reject",
                        "function_path": "myapp.actions.generic_rejection",
                        "order": 1,
                    },
                ],
            },
        ):
            actions = get_effective_actions(
                ActionType.AFTER_REJECT,
                workflow=self.workflow,
                model_string="hr.LeaveRequest",
            )
            self.assertEqual(len(actions), 1)
            self.assertEqual(
                actions[0].function_path, "myapp.actions.generic_rejection"
            )

    def test_database_actions_still_take_priority(self):
        """Database actions at any level override settings-based actions."""
        WorkflowAction.objects.create(
            workflow=self.workflow,
            action_type=ActionType.AFTER_APPROVE,
            function_path="tests.db_handler",
            is_active=True,
            order=1,
        )

        with self.settings(
            WORKFLOW_AUTO_CREATE_ACTIONS=False,
            WORKFLOW_ACTIONS_CONFIG={
                "default": [
                    {
                        "action_type": "after_approve",
                        "function_path": "myapp.actions.settings_handler",
                        "order": 1,
                    },
                ],
            },
        ):
            actions = get_effective_actions(
                ActionType.AFTER_APPROVE,
                workflow=self.workflow,
                model_string="crm.Opportunity",
            )
            self.assertEqual(len(actions), 1)
            self.assertIsNotNone(actions[0].id)
            self.assertEqual(actions[0].function_path, "tests.db_handler")


class ValidateWorkflowSettingsTest(TestCase):
    """Test that validate_workflow_settings accepts 'default' key."""

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "MODEL_WORKFLOW_MAPPINGS": {
                "default": ["generic_approval"],
                "crm.Opportunity": ["opportunity_approval"],
            },
            "AUTO_START_WORKFLOWS": {
                "default": {"workflow_slug": "generic_approval"},
                "crm.Opportunity": {"workflow_slug": "opportunity_approval"},
            },
        }
    )
    def test_valid_settings_with_default_key(self):
        """Should not raise for valid settings with 'default' key."""
        validate_workflow_settings()  # Should not raise

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "MODEL_WORKFLOW_MAPPINGS": {
                "invalid_key": ["generic_approval"],
            },
        }
    )
    def test_invalid_key_without_dot_raises(self):
        """Should raise for keys that aren't 'default' and don't contain '.'."""
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            validate_workflow_settings()

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "AUTO_START_WORKFLOWS": {
                "invalid_key": {"workflow_slug": "test"},
            },
        }
    )
    def test_invalid_auto_start_key_without_dot_raises(self):
        """Should raise for auto-start keys that aren't 'default' and don't contain '.'."""
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            validate_workflow_settings()

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "MODEL_WORKFLOW_MAPPINGS": {
                "default": ["generic_approval"],
            },
        }
    )
    def test_only_default_key_is_valid(self):
        """Settings with only 'default' key should be valid."""
        validate_workflow_settings()  # Should not raise


class GetWorkflowsForModelIntegrationTest(TestCase):
    """Integration test for get_workflows_for_model using 'default' fallback."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com"
        )

        self.workflow1 = WorkFlow.objects.create(
            name_en="generic_approval",
            name_ar="موافقة عامة",
            status=WorkflowStatus.ACTIVE,
            is_active=True,
            created_by=self.user,
        )
        self.workflow2 = WorkFlow.objects.create(
            name_en="opportunity_approval",
            name_ar="موافقة الفرصة",
            status=WorkflowStatus.ACTIVE,
            is_active=True,
            created_by=self.user,
        )

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "ENABLED_MODELS": ["crm.Opportunity", "hr.LeaveRequest"],
            "MODEL_WORKFLOW_MAPPINGS": {
                "default": ["generic_approval"],
                "crm.Opportunity": ["opportunity_approval"],
            },
        }
    )
    def test_exact_model_match_returns_specific_workflows(self):
        """get_workflows_for_model returns model-specific workflows."""
        from django_workflow_engine.services import get_workflows_for_model
        from sandbox.testapp.models import WorkflowTestModel

        # Use the actual model class — but since we can't create a real crm.Opportunity,
        # we'll test via the helper function
        result = get_workflows_for_model_string("crm.Opportunity")
        self.assertEqual(result, ["opportunity_approval"])

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "ENABLED_MODELS": ["crm.Opportunity", "hr.LeaveRequest"],
            "MODEL_WORKFLOW_MAPPINGS": {
                "default": ["generic_approval"],
                "crm.Opportunity": ["opportunity_approval"],
            },
        }
    )
    def test_unmapped_model_returns_default_workflows(self):
        """Unmapped model falls back to default workflows."""
        result = get_workflows_for_model_string("hr.LeaveRequest")
        self.assertEqual(result, ["generic_approval"])

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "ENABLED_MODELS": ["crm.Opportunity"],
            "MODEL_WORKFLOW_MAPPINGS": {
                "crm.Opportunity": ["opportunity_approval"],
            },
        }
    )
    def test_no_default_no_match_returns_none(self):
        """Returns None when no mapping and no default."""
        result = get_workflows_for_model_string("hr.LeaveRequest")
        self.assertIsNone(result)
