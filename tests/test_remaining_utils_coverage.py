"""Focused coverage for role, approval-step, and form utility branches."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from approval_workflow.choices import RoleSelectionStrategy

from django_workflow_engine.choices import WorkflowStrategy
from django_workflow_engine.utils import (
    _build_anyone_steps,
    _build_consensus_steps,
    _build_hierarchy_steps,
    _build_majority_steps,
    _build_percentage_steps,
    _build_quorum_steps,
    _build_role_strategy_steps,
    build_approval_steps,
    build_approval_steps_from_config,
    enrich_answers,
    flatten_form_info,
    get_next_workflow_stage,
    get_users_from_role,
    get_workflow_first_stage,
    get_workflow_location_string,
)
from tests.factories import UserFactory


def discover_role_users(role):
    return role.discovered


class RemainingUtilsCoverageTest(TestCase):
    def setUp(self):
        self.creator = UserFactory()
        self.users = [UserFactory(), UserFactory(), UserFactory()]
        self.role = SimpleNamespace(id=7)
        self.stage = SimpleNamespace(
            id=9,
            name_en="Review",
            quorum_count=2,
            quorum_total=3,
            percentage_required=Decimal("50"),
            hierarchy_base_user=None,
            hierarchy_levels=2,
        )

    @override_settings(
        WORKFLOW_ROLE_USERS_FUNCTION=(
            "tests.test_remaining_utils_coverage.discover_role_users"
        )
    )
    def test_role_user_discovery_all_relationship_patterns(self):
        role = SimpleNamespace(discovered=self.users)
        self.assertEqual(get_users_from_role(role), self.users)

        with override_settings(WORKFLOW_ROLE_USERS_FUNCTION="missing.path.function"):
            role = SimpleNamespace(users=MagicMock())
            role.users.all.return_value = self.users
            self.assertEqual(get_users_from_role(role), self.users)

        role = SimpleNamespace(users=MagicMock(), user_set=MagicMock())
        role.users.all.side_effect = RuntimeError("users failed")
        role.user_set.all.return_value = self.users
        self.assertEqual(get_users_from_role(role), self.users)
        role.user_set.all.side_effect = RuntimeError("user set failed")
        self.assertEqual(get_users_from_role(role), [])

        profiles = [SimpleNamespace(user=self.users[0]), SimpleNamespace()]
        role = SimpleNamespace(userprofile_set=MagicMock())
        role.userprofile_set.all.return_value = profiles
        self.assertEqual(get_users_from_role(role), [self.users[0]])
        role.userprofile_set.all.side_effect = RuntimeError("profiles failed")
        self.assertEqual(get_users_from_role(role), [])

        role = SimpleNamespace(profile_set=MagicMock())
        role.profile_set.all.return_value = [
            SimpleNamespace(user=self.users[0]),
            self.users[1],
        ]
        self.assertEqual(get_users_from_role(role), self.users[:2])

        role.profile_set.all.side_effect = RuntimeError("profile failed")
        self.assertEqual(get_users_from_role(role), [])

    def test_role_strategy_builders_with_users_and_fallbacks(self):
        with patch(
            "django_workflow_engine.utils.get_users_from_role",
            return_value=[],
        ):
            self.assertEqual(
                _build_quorum_steps(self.stage, self.role, self.creator, 1)[0][
                    "assigned_to"
                ],
                self.creator,
            )
            self.assertEqual(
                _build_majority_steps(self.stage, self.role, self.creator, 1)[0][
                    "assigned_to"
                ],
                self.creator,
            )
            self.assertEqual(
                _build_percentage_steps(self.stage, self.role, self.creator, 1)[0][
                    "assigned_to"
                ],
                self.creator,
            )
            self.assertEqual(
                _build_hierarchy_steps(
                    self.stage,
                    self.role,
                    RoleSelectionStrategy.HIERARCHY_UP,
                    self.creator,
                    1,
                )[0]["assigned_to"],
                self.creator,
            )
            self.assertEqual(
                _build_consensus_steps(self.stage, self.role, self.creator, 1)[0][
                    "assigned_to"
                ],
                self.creator,
            )

        with patch(
            "django_workflow_engine.utils.get_users_from_role",
            return_value=self.users,
        ):
            self.assertEqual(
                len(_build_quorum_steps(self.stage, self.role, self.creator, 2)),
                3,
            )
            self.assertEqual(
                len(_build_majority_steps(self.stage, self.role, self.creator, 2)),
                3,
            )
            self.assertEqual(
                len(_build_percentage_steps(self.stage, self.role, self.creator, 2)),
                3,
            )
            self.assertEqual(
                len(
                    _build_hierarchy_steps(
                        self.stage,
                        self.role,
                        RoleSelectionStrategy.HIERARCHY_UP,
                        self.creator,
                        2,
                    )
                ),
                2,
            )
            self.assertEqual(
                len(
                    _build_hierarchy_steps(
                        self.stage,
                        self.role,
                        RoleSelectionStrategy.HIERARCHY_CHAIN,
                        self.creator,
                        2,
                    )
                ),
                3,
            )
            self.assertEqual(
                len(_build_consensus_steps(self.stage, self.role, self.creator, 2)),
                3,
            )

        self.stage.percentage_required = None
        with patch(
            "django_workflow_engine.utils._build_majority_steps",
            return_value=["majority"],
        ):
            self.assertEqual(
                _build_percentage_steps(self.stage, self.role, self.creator, 1),
                ["majority"],
            )

        anyone = _build_anyone_steps(self.stage, self.role, self.creator, 4)
        self.assertIs(anyone[0]["assigned_role"], self.role)

    def test_role_strategy_router_all_paths(self):
        strategies = [
            ("QUORUM", "_build_quorum_steps"),
            ("MAJORITY", "_build_majority_steps"),
            ("PERCENTAGE", "_build_percentage_steps"),
        ]
        for constant, builder in strategies:
            value = getattr(RoleSelectionStrategy, constant)
            with patch(
                f"django_workflow_engine.utils.{builder}",
                return_value=[constant],
            ):
                self.assertEqual(
                    _build_role_strategy_steps(
                        self.stage,
                        self.role,
                        value,
                        self.creator,
                        1,
                    ),
                    [constant],
                )

        standard = _build_role_strategy_steps(
            self.stage,
            self.role,
            RoleSelectionStrategy.ANYONE,
            self.creator,
            1,
        )
        self.assertIs(standard[0]["assigned_role"], self.role)

    def test_build_approval_steps_strategy_and_lookup_errors(self):
        stage = SimpleNamespace(
            id=1,
            name_en="Stage",
            pipeline=None,
        )
        self.assertEqual(build_approval_steps(stage, self.creator), [])

        workflow = SimpleNamespace(
            strategy=WorkflowStrategy.WORKFLOW_PIPELINE,
            workflow_info={},
        )
        pipeline = SimpleNamespace(
            workflow=workflow,
            pipeline_info={"approvals": []},
        )
        stage.pipeline = pipeline
        steps = build_approval_steps(stage, self.creator)
        self.assertEqual(steps[0]["assigned_to"], self.creator)

        workflow.strategy = WorkflowStrategy.WORKFLOW_ONLY
        workflow.workflow_info = {"approvals": [{"approval_type": "self-approved"}]}
        self.assertEqual(len(build_approval_steps(stage, self.creator)), 1)

        workflow.strategy = 999
        self.assertEqual(len(build_approval_steps(stage, self.creator)), 1)

        workflow.strategy = WorkflowStrategy.WORKFLOW_PIPELINE
        pipeline.pipeline_info = {
            "approvals": [
                {
                    "approval_type": "user",
                    "approval_user": {"val": self.users[0].pk},
                    "required_form": {"val": 99},
                    "step_approval_type": "invalid",
                },
                {
                    "approval_type": "role",
                    "user_role": 88,
                },
            ]
        }
        with (
            patch(
                "django_workflow_engine.utils.User.objects.filter",
                return_value=self.users,
            ),
            patch(
                "django.apps.apps.get_model",
                side_effect=RuntimeError("model missing"),
            ),
        ):
            steps = build_approval_steps(stage, self.creator)
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[1]["assigned_to"], self.creator)

        form = SimpleNamespace(id=99)
        form_model = MagicMock()
        form_model.objects.filter.return_value = [form]
        pipeline.pipeline_info = {
            "approvals": [
                {
                    "approval_type": "self-approved",
                    "required_form": 99,
                }
            ]
        }
        with patch("django.apps.apps.get_model", return_value=form_model):
            steps = build_approval_steps(stage, self.creator)
        self.assertIs(steps[0]["form"], form)

    def test_navigation_config_forms_and_file_enrichment(self):
        self.assertIsNone(get_next_workflow_stage(None))

        next_stage = object()
        current_pipeline = SimpleNamespace(
            order=1,
            workflow=SimpleNamespace(pipelines=MagicMock()),
            stages=MagicMock(),
        )
        current_pipeline.stages.filter.return_value.order_by.return_value.first.return_value = (
            next_stage
        )
        current = SimpleNamespace(order=1, pipeline=current_pipeline)
        self.assertIs(get_next_workflow_stage(current), next_stage)

        current_pipeline.stages.filter.return_value.order_by.return_value.first.return_value = (
            None
        )
        next_pipeline = SimpleNamespace(stages=MagicMock())
        next_pipeline.stages.order_by.return_value.first.return_value = next_stage
        current_pipeline.workflow.pipelines.filter.return_value.order_by.return_value.first.return_value = (
            next_pipeline
        )
        self.assertIs(get_next_workflow_stage(current), next_stage)

        current_pipeline.workflow.pipelines.filter.return_value.order_by.return_value.first.return_value = (
            None
        )
        self.assertIsNone(get_next_workflow_stage(current))

        workflow = SimpleNamespace(pipelines=MagicMock())
        pipeline = SimpleNamespace(stages=MagicMock())
        stage = object()
        workflow.pipelines.order_by.return_value.first.return_value = pipeline
        pipeline.stages.order_by.return_value.first.return_value = stage
        self.assertIs(get_workflow_first_stage(workflow), stage)
        workflow.pipelines.order_by.return_value.first.return_value = None
        self.assertIsNone(get_workflow_first_stage(workflow))

        approvals = [
            {"approval_type": "user", "approval_user": 999999},
            {"approval_type": "role", "user_role": 1},
            {
                "approval_type": "self-approved",
                "required_form": {"val": 2},
                "step_approval_type": "invalid",
            },
        ]

        def get_model(app_label, model_name=None, **kwargs):
            if model_name is None and app_label == "testapp.MockUser":
                return type(self.creator)
            raise RuntimeError("missing model")

        with patch(
            "django.apps.apps.get_model",
            side_effect=get_model,
        ):
            steps = build_approval_steps_from_config(
                approvals,
                self.creator,
                {"source": "test"},
            )
        self.assertEqual(len(steps), 3)
        self.assertEqual(build_approval_steps_from_config([], self.creator), [])

        form = SimpleNamespace(id=2)
        form_model = MagicMock()
        form_model.objects.get.return_value = form

        def valid_get_model(app_label, model_name=None, **kwargs):
            if model_name is None and app_label == "testapp.MockUser":
                return type(self.creator)
            return form_model

        with patch(
            "django.apps.apps.get_model",
            side_effect=valid_get_model,
        ):
            steps = build_approval_steps_from_config(
                [
                    {
                        "approval_type": "self-approved",
                        "required_form": 2,
                        "step_approval_type": "approve",
                    }
                ],
                self.creator,
            )
        self.assertIs(steps[0]["form"], form)
        self.assertEqual(steps[0]["approval_type"], "approve")

        fields = [
            {
                "field_name": "priority",
                "field_type": "SELECT",
                "extra_info": ["Low", "High"],
            }
        ]
        self.assertEqual(flatten_form_info(fields, {}), fields)

        upload = SimpleUploadedFile("evidence.txt", b"evidence")
        form_info = [{"field_name": "file", "field_type": "FILE"}]
        with self.assertLogs("django_workflow_engine.utils", level="WARNING"):
            enriched = enrich_answers(
                form_info,
                {"file": upload},
                save_files=True,
            )
        self.assertIs(enriched[0]["answer"], upload)

        request = MagicMock()
        request.build_absolute_uri.side_effect = lambda url: f"https://test{url}"
        with (
            patch(
                "django_workflow_engine.utils.default_storage.save",
                return_value="workflows/1/evidence.txt",
            ),
            patch(
                "django_workflow_engine.utils.default_storage.url",
                return_value="/media/evidence.txt",
            ),
        ):
            enriched = enrich_answers(
                form_info,
                {"file": upload},
                object_id=1,
                request=request,
                save_files=True,
            )
        self.assertEqual(
            enriched[0]["answer"],
            "https://test/media/evidence.txt",
        )

        with patch(
            "django_workflow_engine.strategy_handlers.get_workflow_location",
            return_value="Location",
        ):
            self.assertEqual(get_workflow_location_string(object()), "Location")
