from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from django_workflow_engine.assignment import (
    _call_resolver,
    _coerce_user,
    _query_value,
    _resolve_from_spec,
    _resolve_path,
    resolve_assigned_user,
)
from django_workflow_engine.choices import ApprovalTypes
from django_workflow_engine.models import validate_approval_configuration_payload
from django_workflow_engine.settings import (
    get_assignment_resolvers,
    validate_workflow_settings,
)
from django_workflow_engine.utils import (
    build_approval_steps,
    build_approval_steps_from_config,
)
from sandbox.testapp.models import WorkflowTestModel


def resolve_target_assignee(obj, approval):
    assert approval["approval_type"] == ApprovalTypes.ASSIGNED
    assert approval["marker"] == "called"
    return obj.created_by


def resolve_with_kwargs(**kwargs):
    return kwargs["obj"].created_by


class AssignmentResolutionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.User = User
        self.creator = User.objects.create_user(username="assignment-creator")
        self.assignee = User.objects.create_user(username="assignment-assignee")
        self.target = WorkflowTestModel.objects.create(
            name="Target", created_by=self.assignee
        )

    def test_assigned_approval_resolves_a_configured_object_field(self):
        with override_settings(
            DJANGO_WORKFLOW_ENGINE={
                "ASSIGNMENT_RESOLVERS": {
                    "testapp.WorkflowTestModel": {"field": "created_by"}
                }
            }
        ):
            steps = build_approval_steps_from_config(
                [{"approval_type": "assigned"}], self.creator, obj=self.target
            )

        self.assertEqual(steps[0]["assigned_to"], self.assignee)

        workflow = SimpleNamespace(strategy=1)
        stage = SimpleNamespace(
            id=10,
            name_en="Assigned",
            pipeline=SimpleNamespace(workflow=workflow),
            stage_info={"approvals": [{"approval_type": "assigned"}]},
        )
        with override_settings(
            DJANGO_WORKFLOW_ENGINE={
                "ASSIGNMENT_RESOLVERS": {
                    "testapp.WorkflowTestModel": {"field": "created_by"}
                }
            }
        ):
            steps = build_approval_steps(stage, self.creator, obj=self.target)
        self.assertEqual(steps[0]["assigned_to"], self.assignee)

    def test_assigned_approval_resolves_an_assignment_model_query(self):
        assignment = Mock(user=self.assignee)
        queryset = Mock()
        queryset.first.return_value = assignment
        assignment_model = Mock()
        assignment_model.objects.filter.return_value = queryset
        with override_settings(
            DJANGO_WORKFLOW_ENGINE={
                "ASSIGNMENT_RESOLVERS": {
                    "testapp.WorkflowTestModel": {
                        "model": "assignments.Assignment",
                        "query": {
                            "target": "$object",
                            "is_active": True,
                        },
                        "user_field": "user",
                    }
                }
            }
        ):
            with patch(
                "django_workflow_engine.assignment.apps.get_model",
                side_effect=lambda model, **kwargs: (
                    assignment_model if model == "assignments.Assignment" else self.User
                ),
            ):
                user = resolve_assigned_user(
                    self.target, {"approval_type": "assigned"}, self.creator
                )

        self.assertEqual(user, self.assignee)
        assignment_model.objects.filter.assert_called_once_with(
            target=self.target, is_active=True
        )

    def test_inline_assignment_function_is_called(self):
        user = resolve_assigned_user(
            self.target,
            {
                "approval_type": "assigned",
                "assign_function": "tests.test_assignment.resolve_target_assignee",
                "marker": "called",
            },
            self.creator,
        )
        self.assertEqual(user, self.assignee)

    def test_assigned_is_a_valid_approval_type(self):
        self.assertTrue(
            validate_approval_configuration_payload(
                {"approvals": [{"approval_type": ApprovalTypes.ASSIGNED}]},
                require_approvals=True,
            )
        )

    def test_legacy_self_approval_remains_supported(self):
        steps = build_approval_steps_from_config(
            [{"approval_type": "self-approved"}], self.creator, obj=self.target
        )
        self.assertEqual(steps[0]["assigned_to"], self.creator)

    def test_path_and_user_coercion_helpers(self):
        self.assertIsNone(_resolve_path(None, "anything"))
        self.assertEqual(
            _resolve_path(SimpleNamespace(value=lambda: "called"), "value"),
            "called",
        )

        class FakeManager:
            def all(self):
                return FakeQuerySet()

        class FakeQuerySet:
            def first(self):
                return "first"

        with (
            patch("django_workflow_engine.assignment.Manager", FakeManager),
            patch("django_workflow_engine.assignment.QuerySet", FakeQuerySet),
        ):
            self.assertEqual(
                _resolve_path(SimpleNamespace(items=FakeManager()), "items"), "first"
            )

        self.assertIsNone(_coerce_user(None))
        self.assertEqual(_coerce_user(self.assignee), self.assignee)
        self.assertEqual(_coerce_user(self.assignee.pk), self.assignee)
        self.assertEqual(_coerce_user(str(self.assignee.pk)), self.assignee)
        self.assertEqual(
            _coerce_user(SimpleNamespace(user=self.assignee)), self.assignee
        )
        self.assertEqual(
            _coerce_user(SimpleNamespace(is_authenticated=True)),
            SimpleNamespace(is_authenticated=True),
        )
        self.assertIsNone(_coerce_user(object()))

    def test_function_and_query_helpers(self):
        self.assertEqual(
            _call_resolver(
                "tests.test_assignment.resolve_with_kwargs", self.target, {}
            ),
            self.assignee,
        )
        self.assertEqual(_query_value(3, self.target, {}), 3)
        self.assertIs(_query_value("$object", self.target, {}), self.target)
        self.assertEqual(_query_value("$object.pk", self.target, {}), self.target.pk)
        self.assertEqual(_query_value("$approval.key", self.target, {"key": 9}), 9)
        with self.assertRaises(ImproperlyConfigured):
            _query_value("$unknown", self.target, {})

    def test_resolver_spec_validation_and_variants(self):
        self.assertEqual(
            _resolve_from_spec("created_by", self.target, {}), self.assignee
        )
        self.assertEqual(
            _resolve_from_spec(
                {"function": "tests.test_assignment.resolve_target_assignee"},
                self.target,
                {"approval_type": ApprovalTypes.ASSIGNED, "marker": "called"},
            ),
            self.assignee,
        )
        for invalid in ([], {}):
            with self.subTest(spec=invalid):
                with self.assertRaises(ImproperlyConfigured):
                    _resolve_from_spec(invalid, self.target, {})
        with patch(
            "django_workflow_engine.assignment.apps.get_model",
            side_effect=LookupError,
        ):
            with self.assertRaises(ImproperlyConfigured):
                _resolve_from_spec({"model": "bad.Model"}, self.target, {})

    def test_assignment_model_ordering_and_resolution_failures(self):
        assignment = SimpleNamespace(user=self.assignee)
        queryset = Mock()
        queryset.order_by.return_value = queryset
        queryset.first.return_value = assignment
        model = Mock()
        model.objects.filter.return_value = queryset
        with patch(
            "django_workflow_engine.assignment.apps.get_model", return_value=model
        ):
            self.assertEqual(
                _resolve_from_spec(
                    {
                        "model": "assignments.Assignment",
                        "query": {"target_id": "$object.pk"},
                        "order_by": ["-id"],
                    },
                    self.target,
                    {},
                ),
                self.assignee,
            )
        queryset.order_by.assert_called_once_with("-id")

        with self.assertRaises(ValueError):
            resolve_assigned_user(None, {})
        with override_settings(DJANGO_WORKFLOW_ENGINE={}):
            with self.assertRaises(ImproperlyConfigured):
                resolve_assigned_user(self.target, {})
            conventional = SimpleNamespace(
                assigned_to=None,
                assignee=self.assignee,
                _meta=SimpleNamespace(label="tests.Target"),
                pk=1,
            )
            self.assertEqual(resolve_assigned_user(conventional, {}), self.assignee)
        with override_settings(
            DJANGO_WORKFLOW_ENGINE={
                "ASSIGNMENT_RESOLVERS": {
                    "testapp.WorkflowTestModel": {"field": "description"}
                }
            }
        ):
            with self.assertRaises(ValueError):
                resolve_assigned_user(self.target, {})

    def test_assignment_setting_resolution_and_validation(self):
        with override_settings(DJANGO_WORKFLOW_ENGINE={}):
            self.assertEqual(get_assignment_resolvers(), {})
        configuration = {
            "ASSIGNMENT_RESOLVERS": {
                "default": {"field": "assigned_to"},
                "TESTAPP.WORKFLOWTESTMODEL": {"field": "created_by"},
            }
        }
        with override_settings(DJANGO_WORKFLOW_ENGINE=configuration):
            self.assertEqual(
                get_assignment_resolvers("testapp.WorkflowTestModel"),
                {"field": "created_by"},
            )
            self.assertEqual(
                get_assignment_resolvers("other.Model"),
                {"field": "assigned_to"},
            )
            validate_workflow_settings()

        invalid_settings = [
            {"ASSIGNMENT_RESOLVERS": []},
            {"ASSIGNMENT_RESOLVERS": {"invalid": {}}},
            {"ASSIGNMENT_RESOLVERS": {"default": "assigned_to"}},
        ]
        for setting in invalid_settings:
            with self.subTest(setting=setting):
                with override_settings(DJANGO_WORKFLOW_ENGINE=setting):
                    with self.assertRaises(ImproperlyConfigured):
                        validate_workflow_settings()
