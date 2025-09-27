"""
Test cases for new settings configuration and workflow-to-model mapping features
"""

from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings

from django_workflow_engine.models import WorkFlow, WorkflowConfiguration
from django_workflow_engine.services import (
    get_auto_start_workflow_for_object,
    get_available_workflows_for_selection,
    get_workflows_for_model,
    get_workflows_for_object,
    is_model_enabled_for_workflows,
)
from django_workflow_engine.settings import (
    get_auto_start_workflows,
    get_enabled_models,
    get_workflow_model_mappings,
    get_workflow_settings,
    is_model_workflow_enabled,
    validate_workflow_settings,
)
from sandbox.testapp.models import WorkflowTestModel

from .factories import UserFactory, WorkFlowFactory, WorkflowTestModelFactory


class WorkflowSettingsTest(TestCase):
    """Test workflow settings configuration"""

    @override_settings(DJANGO_WORKFLOW_ENGINE={})
    def test_get_workflow_settings_empty(self):
        """Test getting workflow settings when none configured"""
        settings = get_workflow_settings()
        self.assertEqual(settings, {})

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "ENABLED_MODELS": ["testapp.WorkflowTestModel", "myapp.PurchaseRequest"],
            "DEFAULT_STATUS_FIELD": "status",
            "MODEL_WORKFLOW_MAPPINGS": {
                "testapp.WorkflowTestModel": ["test_workflow", "emergency_workflow"]
            },
        }
    )
    def test_get_workflow_settings_configured(self):
        """Test getting workflow settings when configured"""
        settings = get_workflow_settings()
        self.assertIn("ENABLED_MODELS", settings)
        self.assertEqual(len(settings["ENABLED_MODELS"]), 2)

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={"ENABLED_MODELS": ["testapp.WorkflowTestModel"]}
    )
    def test_get_enabled_models(self):
        """Test getting enabled models list"""
        models = get_enabled_models()
        self.assertEqual(models, ["testapp.WorkflowTestModel"])

    @override_settings(DJANGO_WORKFLOW_ENGINE={})
    def test_get_enabled_models_empty(self):
        """Test getting enabled models when none configured"""
        models = get_enabled_models()
        self.assertEqual(models, [])

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "MODEL_WORKFLOW_MAPPINGS": {
                "testapp.WorkflowTestModel": ["workflow1", "workflow2"]
            }
        }
    )
    def test_get_workflow_model_mappings(self):
        """Test getting workflow model mappings"""
        mappings = get_workflow_model_mappings()
        self.assertIn("testapp.WorkflowTestModel", mappings)
        self.assertEqual(
            mappings["testapp.WorkflowTestModel"], ["workflow1", "workflow2"]
        )

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "AUTO_START_WORKFLOWS": {
                "testapp.WorkflowTestModel": {
                    "workflow_slug": "auto_workflow",
                    "conditions": {"amount__gte": 1000},
                }
            }
        }
    )
    def test_get_auto_start_workflows(self):
        """Test getting auto start workflows configuration"""
        auto_start = get_auto_start_workflows()
        self.assertIn("testapp.WorkflowTestModel", auto_start)
        self.assertEqual(
            auto_start["testapp.WorkflowTestModel"]["workflow_slug"], "auto_workflow"
        )

    @override_settings(DJANGO_WORKFLOW_ENGINE={})
    def test_is_model_workflow_enabled_no_config(self):
        """Test model workflow enabled check when no specific config"""
        # When no specific models configured, all models should be enabled
        self.assertTrue(is_model_workflow_enabled(WorkflowTestModel))

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={"ENABLED_MODELS": ["testapp.WorkflowTestModel"]}
    )
    def test_is_model_workflow_enabled_with_config(self):
        """Test model workflow enabled check with specific config"""
        self.assertTrue(is_model_workflow_enabled(WorkflowTestModel))

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={"ENABLED_MODELS": ["otherapp.OtherModel"]}
    )
    def test_is_model_workflow_disabled_with_config(self):
        """Test model workflow disabled when not in config"""
        self.assertFalse(is_model_workflow_enabled(WorkflowTestModel))


class WorkflowServicesTest(TestCase):
    """Test new workflow services functions"""

    def setUp(self):
        """Set up test data"""
        self.workflow1 = WorkFlowFactory(name_en="Test Workflow 1")
        self.workflow2 = WorkFlowFactory(name_en="Test Workflow 2")
        # Manually set slug-like identifiers for testing
        self.workflow1.slug_identifier = "test_workflow_1"
        self.workflow1.save()
        self.workflow2.slug_identifier = "test_workflow_2"
        self.workflow2.save()
        self.user = UserFactory()

    @override_settings(DJANGO_WORKFLOW_ENGINE={})
    def test_get_workflows_for_model_no_config(self):
        """Test getting workflows for model when no specific mapping"""
        workflows = get_workflows_for_model(WorkflowTestModel)
        # Should return all active workflows when no specific mapping
        self.assertEqual(len(workflows), 2)

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "ENABLED_MODELS": ["testapp.WorkflowTestModel"],
            "MODEL_WORKFLOW_MAPPINGS": {
                "testapp.WorkflowTestModel": ["Test Workflow 1"]
            },
        }
    )
    def test_get_workflows_for_model_with_mapping(self):
        """Test getting workflows for model with specific mapping"""
        workflows = get_workflows_for_model(WorkflowTestModel)
        self.assertEqual(len(workflows), 1)
        self.assertEqual(workflows[0].name_en, "Test Workflow 1")

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={"ENABLED_MODELS": ["otherapp.OtherModel"]}
    )
    def test_get_workflows_for_model_disabled(self):
        """Test getting workflows for disabled model"""
        workflows = get_workflows_for_model(WorkflowTestModel)
        self.assertEqual(len(workflows), 0)

    def test_get_workflows_for_object(self):
        """Test getting workflows for object instance"""
        obj = WorkflowTestModelFactory()
        workflows = get_workflows_for_object(obj)
        # Should return same as get_workflows_for_model
        self.assertEqual(len(workflows), 2)

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "ENABLED_MODELS": ["testapp.WorkflowTestModel"],
            "AUTO_START_WORKFLOWS": {
                "testapp.WorkflowTestModel": {"workflow_name": "Test Workflow 1"}
            },
        }
    )
    def test_get_auto_start_workflow_for_object(self):
        """Test getting auto-start workflow for object"""
        obj = WorkflowTestModelFactory()
        workflow = get_auto_start_workflow_for_object(obj)
        self.assertEqual(workflow.name_en, "Test Workflow 1")

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "ENABLED_MODELS": ["testapp.WorkflowTestModel"],
            "AUTO_START_WORKFLOWS": {
                "testapp.WorkflowTestModel": {
                    "workflow_name": "Test Workflow 1",
                    "conditions": {"amount__gte": 1000},
                }
            },
        }
    )
    def test_get_auto_start_workflow_for_object_with_conditions_met(self):
        """Test auto-start workflow with conditions met"""
        obj = WorkflowTestModelFactory(amount=2000)  # Meets condition
        workflow = get_auto_start_workflow_for_object(obj)
        self.assertEqual(workflow.name_en, "Test Workflow 1")

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "ENABLED_MODELS": ["testapp.WorkflowTestModel"],
            "AUTO_START_WORKFLOWS": {
                "testapp.WorkflowTestModel": {
                    "workflow_name": "Test Workflow 1",
                    "conditions": {"amount__gte": 1000},
                }
            },
        }
    )
    def test_get_auto_start_workflow_for_object_with_conditions_not_met(self):
        """Test auto-start workflow with conditions not met"""
        obj = WorkflowTestModelFactory(amount=500)  # Does not meet condition
        workflow = get_auto_start_workflow_for_object(obj)
        self.assertIsNone(workflow)

    def test_get_auto_start_workflow_for_object_no_config(self):
        """Test auto-start workflow when no config"""
        obj = WorkflowTestModelFactory()
        workflow = get_auto_start_workflow_for_object(obj)
        self.assertIsNone(workflow)

    def test_is_model_enabled_for_workflows_alias(self):
        """Test the alias function for model enabled check"""
        result = is_model_enabled_for_workflows(WorkflowTestModel)
        self.assertTrue(result)  # Default should be True when no config

    def test_get_available_workflows_for_selection(self):
        """Test getting workflows formatted for UI selection"""
        workflows = get_available_workflows_for_selection(WorkflowTestModel)
        self.assertEqual(len(workflows), 2)

        # Check format
        workflow_dict = workflows[0]
        self.assertIn("id", workflow_dict)
        self.assertIn("name", workflow_dict)
        self.assertIn("name_ar", workflow_dict)
        self.assertIn("description", workflow_dict)
        self.assertIn("slug", workflow_dict)
        self.assertIn("pipeline_count", workflow_dict)
        self.assertIn("is_active", workflow_dict)


class WorkflowSettingsValidationTest(TestCase):
    """Test workflow settings validation"""

    def test_validate_workflow_settings_valid(self):
        """Test validation with valid settings"""
        with override_settings(
            DJANGO_WORKFLOW_ENGINE={
                "ENABLED_MODELS": ["app.Model1", "app.Model2"],
                "MODEL_WORKFLOW_MAPPINGS": {"app.Model1": ["workflow1"]},
                "AUTO_START_WORKFLOWS": {"app.Model1": {"workflow_slug": "workflow1"}},
            }
        ):
            # Should not raise any exception
            validate_workflow_settings()

    def test_validate_workflow_settings_invalid_enabled_models_type(self):
        """Test validation with invalid enabled models type"""
        with override_settings(DJANGO_WORKFLOW_ENGINE={"ENABLED_MODELS": "not_a_list"}):
            with self.assertRaises(Exception):  # ImproperlyConfigured
                validate_workflow_settings()

    def test_validate_workflow_settings_invalid_model_string(self):
        """Test validation with invalid model string format"""
        with override_settings(
            DJANGO_WORKFLOW_ENGINE={"ENABLED_MODELS": ["invalid_format"]}
        ):
            with self.assertRaises(Exception):  # ImproperlyConfigured
                validate_workflow_settings()

    def test_validate_workflow_settings_invalid_mappings_type(self):
        """Test validation with invalid mappings type"""
        with override_settings(
            DJANGO_WORKFLOW_ENGINE={"MODEL_WORKFLOW_MAPPINGS": "not_a_dict"}
        ):
            with self.assertRaises(Exception):  # ImproperlyConfigured
                validate_workflow_settings()

    def test_validate_workflow_settings_invalid_auto_start_type(self):
        """Test validation with invalid auto start type"""
        with override_settings(
            DJANGO_WORKFLOW_ENGINE={"AUTO_START_WORKFLOWS": "not_a_dict"}
        ):
            with self.assertRaises(Exception):  # ImproperlyConfigured
                validate_workflow_settings()


# Add missing import
import django.conf
