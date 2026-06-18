"""Tests for company-specific default status workflow provisioning."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from django_workflow_engine.models import (
    ModelStatus,
    ModelStatusConfiguration,
    Status,
    WorkFlow,
    WorkflowAttachment,
    WorkflowConfiguration,
)
from django_workflow_engine.services import register_model_for_statuses
from django_workflow_engine.settings import validate_workflow_settings
from django_workflow_engine.status_services import (
    _build_default_workflow_design,
    attach_default_status_workflow,
    auto_generate_default_flow,
    create_status_flow_design,
    ensure_default_status_workflows_for_company,
    get_company_default_status_workflow,
    get_or_create_default_status_workflow,
    get_or_create_default_status_workflow_for_object,
    get_status_flow_design,
)
from sandbox.testapp.models import WorkflowTestModel

User = get_user_model()


def ticket_default_flow(company, model, user=None):
    return {
        "status_field": "status",
        "default_status": "new",
        "terminal_statuses": ["closed"],
        "workflow": {
            "name_en": f"Ticket Workflow - {company.username}",
            "name_ar": f"Ticket Workflow - {company.username}",
        },
        "statuses": [
            {
                "code": "new",
                "key": "new",
                "name_en": "New",
                "name_ar": "New",
                "category": "open",
            },
            {
                "code": "closed",
                "key": "closed",
                "name_en": "Closed",
                "name_ar": "Closed",
                "category": "done",
                "is_terminal": True,
            },
        ],
        "transitions": [
            {
                "code": "close",
                "name_en": "Close",
                "from": "new",
                "to": "closed",
            }
        ],
    }


DEFAULT_SETTINGS = {
    "DEFAULT_STATUS_WORKFLOWS": {
        "testapp.WorkflowTestModel": {
            "status_field": "status",
            "allow_direct_change": False,
            "default_status": "new",
            "terminal_statuses": ["closed"],
            "workflow": {
                "name_en": "Default Ticket Workflow",
                "name_ar": "Default Ticket Workflow",
            },
            "statuses": [
                {
                    "code": "new",
                    "name_en": "New",
                    "name_ar": "New",
                    "category": "open",
                },
                {
                    "code": "closed",
                    "name_en": "Closed",
                    "name_ar": "Closed",
                    "category": "done",
                    "is_terminal": True,
                },
            ],
            "transitions": [
                {
                    "code": "close",
                    "name_en": "Close",
                    "from": "new",
                    "to": "closed",
                }
            ],
            "company_field": "created_by",
            "auto_start": True,
        }
    }
}


@override_settings(DJANGO_WORKFLOW_ENGINE=DEFAULT_SETTINGS)
class DefaultStatusWorkflowProvisioningTest(TestCase):
    def setUp(self):
        self.company_one = User.objects.create_user(username="company-one")
        self.company_two = User.objects.create_user(username="company-two")

    def test_company_provisioning_is_idempotent_and_company_scoped(self):
        first = ensure_default_status_workflows_for_company(
            self.company_one, user=self.company_one
        )
        repeated = ensure_default_status_workflows_for_company(
            self.company_one, user=self.company_one
        )
        second = ensure_default_status_workflows_for_company(
            self.company_two, user=self.company_two
        )

        model = "testapp.WorkflowTestModel"
        self.assertEqual(first[model].id, repeated[model].id)
        self.assertNotEqual(first[model].id, second[model].id)
        self.assertEqual(first[model].company, self.company_one)
        self.assertEqual(second[model].company, self.company_two)
        self.assertEqual(
            WorkFlow.objects.filter(
                workflow_info__default_status_workflow=True
            ).count(),
            2,
        )
        self.assertEqual(
            Status.objects.filter(key="new")
            .values_list("company_id", flat=True)
            .count(),
            2,
        )

        config = ModelStatusConfiguration.objects.get(
            content_type=ContentType.objects.get_for_model(WorkflowTestModel)
        )
        self.assertEqual(ModelStatus.objects.filter(configuration=config).count(), 4)
        first_design = get_status_flow_design(
            "testapp.WorkflowTestModel", workflow=first[model]
        )
        second_design = get_status_flow_design(
            "testapp.WorkflowTestModel", workflow=second[model]
        )
        self.assertEqual(len(first_design["statuses"]), 2)
        self.assertEqual(len(second_design["statuses"]), 2)
        self.assertFalse(
            {item["id"] for item in first_design["statuses"]}
            & {item["id"] for item in second_design["statuses"]}
        )

    def test_get_or_create_and_lookup_default_workflow(self):
        workflow = get_or_create_default_status_workflow(
            model="testapp.WorkflowTestModel",
            company=self.company_one,
            user=self.company_one,
        )

        self.assertEqual(
            get_company_default_status_workflow(
                "testapp.WorkflowTestModel", self.company_one
            ),
            workflow,
        )

    def test_auto_generate_default_flow_uses_settings_and_is_idempotent(self):
        first = auto_generate_default_flow(self.company_one.pk)
        repeated = auto_generate_default_flow(self.company_one.pk)

        model = "testapp.WorkflowTestModel"
        self.assertEqual(first[model].pk, repeated[model].pk)
        self.assertEqual(first[model].company, self.company_one)
        self.assertEqual(first[model].created_by, self.company_one)

    def test_auto_generate_default_flow_accepts_configured_model_label(self):
        generated = auto_generate_default_flow(
            self.company_one.pk,
            flow="testapp.WorkflowTestModel",
        )

        self.assertEqual(
            generated["testapp.WorkflowTestModel"].company,
            self.company_one,
        )

    def test_auto_generate_default_flow_accepts_explicit_design(self):
        flow = ticket_default_flow(
            company=self.company_one,
            model="testapp.WorkflowTestModel",
        )
        flow["model"] = "testapp.WorkflowTestModel"
        flow["key"] = "explicit"

        first = auto_generate_default_flow(self.company_one.pk, flow=flow)
        repeated = auto_generate_default_flow(self.company_one.pk, flow=flow)

        workflow = first["testapp.WorkflowTestModel"]
        self.assertEqual(workflow.pk, repeated["testapp.WorkflowTestModel"].pk)
        self.assertEqual(
            workflow.workflow_info["default_status_key"],
            "explicit",
        )

    def test_auto_generate_default_flow_rejects_invalid_inputs(self):
        with self.assertRaisesMessage(ValueError, "does not exist"):
            auto_generate_default_flow(999999)

        with self.assertRaisesMessage(ValueError, "flow must be"):
            auto_generate_default_flow(self.company_one.pk, flow=[])

        with self.assertRaisesMessage(ValueError, "must be a dictionary"):
            auto_generate_default_flow(
                self.company_one.pk,
                flow={"testapp.WorkflowTestModel": []},
            )

    def test_auto_generate_default_flow_accepts_model_mapping(self):
        flow = ticket_default_flow(self.company_one, "testapp.WorkflowTestModel")
        generated = auto_generate_default_flow(
            self.company_one.pk,
            flow={"testapp.WorkflowTestModel": flow},
        )

        self.assertEqual(
            generated["testapp.WorkflowTestModel"].company,
            self.company_one,
        )

    def test_default_design_wrapper_and_validation_errors(self):
        wrapped = _build_default_workflow_design(
            model="testapp.WorkflowTestModel",
            company=self.company_one,
            configuration={"design": ticket_default_flow(self.company_one, "")},
        )
        self.assertEqual(wrapped["model"], "testapp.WorkflowTestModel")

        with override_settings(DJANGO_WORKFLOW_ENGINE={}):
            with self.assertRaisesMessage(ValueError, "No default"):
                _build_default_workflow_design(
                    model="testapp.WorkflowTestModel",
                    company=self.company_one,
                    configuration={},
                )

        with patch(
            "django_workflow_engine.status_services.import_string",
            return_value=lambda **kwargs: [],
        ):
            with self.assertRaisesMessage(ValueError, "must be a dictionary"):
                _build_default_workflow_design(
                    model="testapp.WorkflowTestModel",
                    company=self.company_one,
                    configuration={"factory": "tests.invalid"},
                )

    @override_settings(DJANGO_WORKFLOW_ENGINE={})
    def test_missing_default_configuration_helpers_raise(self):
        with self.assertRaisesMessage(ValueError, "No default"):
            get_or_create_default_status_workflow(
                model="testapp.WorkflowTestModel",
                company=self.company_one,
            )

        ticket = WorkflowTestModel.objects.create(
            name="Unconfigured",
            created_by=self.company_one,
        )
        with self.assertRaisesMessage(ValueError, "No default"):
            get_or_create_default_status_workflow_for_object(ticket)

    def test_status_and_transition_action_creation_failures_raise(self):
        status_design = ticket_default_flow(
            self.company_one,
            "testapp.WorkflowTestModel",
        )
        status_design["model"] = "testapp.WorkflowTestModel"
        status_design["statuses"][0]["actions"] = [
            {"function_path": "tests.actions.status"}
        ]
        with patch(
            "django_workflow_engine.status_services.create_custom_workflow_actions",
            return_value=[],
        ):
            with self.assertRaisesMessage(ValueError, "status 'new'"):
                create_status_flow_design(status_design, user=self.company_one)

        transition_design = ticket_default_flow(
            self.company_one,
            "testapp.WorkflowTestModel",
        )
        transition_design["model"] = "testapp.WorkflowTestModel"
        transition_design["transitions"][0]["actions"] = [
            {"function_path": "tests.actions.transition"}
        ]
        with patch(
            "django_workflow_engine.status_services.create_custom_workflow_actions",
            return_value=[],
        ):
            with self.assertRaisesMessage(ValueError, "transition 'close'"):
                create_status_flow_design(transition_design, user=self.company_one)

    def test_existing_configuration_backfills_created_by(self):
        content_type = ContentType.objects.get_for_model(WorkflowTestModel)
        configuration = ModelStatusConfiguration.objects.create(
            content_type=content_type,
            status_field="status",
        )
        design = ticket_default_flow(
            self.company_one,
            "testapp.WorkflowTestModel",
        )
        design.update(
            {
                "model": "testapp.WorkflowTestModel",
                "merge_model_statuses": True,
                "register_default_workflow": False,
            }
        )

        create_status_flow_design(design, user=self.company_one)

        configuration.refresh_from_db()
        self.assertEqual(configuration.created_by, self.company_one)

    def test_lazy_object_provisioning_and_attachment(self):
        ticket = WorkflowTestModel.objects.create(
            name="Lazy default ticket",
            created_by=self.company_one,
        )

        workflow = get_or_create_default_status_workflow_for_object(
            ticket, user=self.company_one
        )
        attachment = attach_default_status_workflow(ticket, user=self.company_one)

        self.assertEqual(workflow.company, self.company_one)
        self.assertEqual(attachment.workflow.cloned_from, workflow)
        self.assertEqual(attachment.current_status.key, "new")
        self.assertTrue(
            WorkflowAttachment.objects.filter(
                object_id=str(ticket.pk),
                current_status__key="new",
            ).exists()
        )

    def test_missing_company_field_is_rejected(self):
        ticket = WorkflowTestModel.objects.create(name="No company")

        with self.assertRaisesMessage(ValueError, "Could not resolve company"):
            get_or_create_default_status_workflow_for_object(ticket)


class RegisterModelDefaultWorkflowTest(TestCase):
    def test_register_model_for_statuses_can_register_default_workflow(self):
        company = User.objects.create_user(username="single-company")
        status = Status.objects.create(
            company=company,
            key="new",
            name_en="New",
            name_ar="New",
        )
        workflow = WorkFlow.objects.create(
            company=company,
            name_en="Default Ticket Workflow",
            name_ar="Default Ticket Workflow",
        )

        register_model_for_statuses(
            WorkflowTestModel,
            statuses=[status],
            default_status=status,
            default_workflow=workflow,
            auto_start_workflow=True,
            status_field="status",
        )

        workflow_config = WorkflowConfiguration.objects.get(
            content_type=ContentType.objects.get_for_model(WorkflowTestModel)
        )
        self.assertEqual(workflow_config.default_workflow, workflow)
        self.assertTrue(workflow_config.auto_start_workflow)

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "DEFAULT_STATUS_WORKFLOWS": {"support.Ticket": {"company_field": "company"}}
        }
    )
    def test_default_workflow_setting_requires_flow_definition(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "full flow design"):
            validate_workflow_settings()

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "DEFAULT_STATUS_WORKFLOWS": {
                "testapp.WorkflowTestModel": {
                    "factory": (
                        "tests.test_default_status_workflow_provisioning."
                        "ticket_default_flow"
                    )
                }
            }
        }
    )
    def test_factory_configuration_remains_supported(self):
        company = User.objects.create_user(username="factory-company")

        generated = auto_generate_default_flow(company.pk)

        self.assertEqual(
            generated["testapp.WorkflowTestModel"].company,
            company,
        )
