"""Tests for enhanced role strategies and strategy-agnostic approval builders."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from approval_workflow.choices import RoleSelectionStrategy

from django_workflow_engine.choices import ApprovalTypes, WorkflowStatus
from django_workflow_engine.models import Pipeline, Stage, WorkFlow
from django_workflow_engine.utils import (
    build_approval_steps,
    build_approval_steps_from_config,
)

User = get_user_model()


class EnhancedRoleStrategiesTest(TestCase):
    """Validate enhanced role strategy handling across builders."""

    def setUp(self):
        self.creator = User.objects.create_user(
            username="creator",
            email="creator@example.com",
            password="testpass123",
        )
        self.company_user = User.objects.create_user(
            username="company",
            email="company@example.com",
            password="testpass123",
        )
        self.workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Role Strategy Workflow",
            name_ar="Role Strategy Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=self.creator,
        )
        self.pipeline = Pipeline.objects.create(
            workflow=self.workflow,
            company=self.company_user,
            name_en="Pipeline",
            name_ar="Pipeline",
            created_by=self.creator,
            order=0,
        )

    def _create_stage(self, approvals, **fields):
        defaults = {
            "pipeline": self.pipeline,
            "company": self.company_user,
            "name_en": "Stage",
            "name_ar": "Stage",
            "created_by": self.creator,
            "order": 0,
            "is_active": True,
            "stage_info": {"approvals": approvals},
        }
        defaults.update(fields)
        return Stage.objects.create(**defaults)

    def _create_group_with_users(self, count):
        group = Group.objects.create(name=f"group-{count}")
        users = []
        for i in range(count):
            user = User.objects.create_user(
                username=f"roleuser{i}",
                email=f"roleuser{i}@example.com",
                password="testpass123",
            )
            users.append(user)
            group.user_set.add(user)
        return group, users

    def test_quorum_strategy_builds_parallel_steps(self):
        role, users = self._create_group_with_users(3)
        stage = self._create_stage(
            approvals=[
                {
                    "approval_type": ApprovalTypes.ROLE,
                    "user_role": role.id,
                    "role_selection_strategy": RoleSelectionStrategy.QUORUM,
                }
            ],
            quorum_count=2,
            quorum_total=3,
        )

        with self.settings(APPROVAL_ROLE_MODEL="auth.Group"):
            steps = build_approval_steps(stage, self.creator)

        self.assertEqual(len(steps), len(users))
        for step in steps:
            self.assertIn("assigned_to", step)
            self.assertEqual(step["extra_fields"]["quorum_count"], 2)
            self.assertEqual(step["extra_fields"]["quorum_total"], 3)
            self.assertEqual(
                step["extra_fields"]["parallel_group"], f"quorum_{stage.id}"
            )
            self.assertTrue(step["extra_fields"]["parallel_required"])

    def test_percentage_strategy_calculates_required_count(self):
        role, users = self._create_group_with_users(5)
        stage = self._create_stage(
            approvals=[
                {
                    "approval_type": ApprovalTypes.ROLE,
                    "user_role": role.id,
                    "role_selection_strategy": RoleSelectionStrategy.PERCENTAGE,
                }
            ],
            percentage_required=Decimal("60.0"),
        )

        with self.settings(APPROVAL_ROLE_MODEL="auth.Group"):
            steps = build_approval_steps(stage, self.creator)

        self.assertEqual(len(steps), len(users))
        for step in steps:
            self.assertEqual(step["extra_fields"]["quorum_total"], len(users))
            self.assertEqual(step["extra_fields"]["quorum_count"], 4)

    def test_pipeline_config_preserves_role_strategy(self):
        role, _users = self._create_group_with_users(2)
        approvals = [
            {
                "approval_type": ApprovalTypes.ROLE,
                "user_role": role.id,
                "role_selection_strategy": RoleSelectionStrategy.QUORUM,
            }
        ]

        with self.settings(APPROVAL_ROLE_MODEL="auth.Group"):
            steps = build_approval_steps_from_config(
                approvals=approvals,
                approval_user=self.creator,
                extra_fields={"pipeline_id": self.pipeline.id},
            )

        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertEqual(step["assigned_role"], role)
        self.assertEqual(step["role_selection_strategy"], RoleSelectionStrategy.QUORUM)
        self.assertEqual(step["extra_fields"]["pipeline_id"], self.pipeline.id)

    def test_workflow_config_mixed_user_and_role(self):
        role, _users = self._create_group_with_users(1)
        approvals = [
            {
                "approval_type": ApprovalTypes.USER,
                "approval_user": self.creator.id,
            },
            {
                "approval_type": ApprovalTypes.ROLE,
                "user_role": role.id,
                "role_selection_strategy": RoleSelectionStrategy.ANYONE,
            },
        ]

        with self.settings(APPROVAL_ROLE_MODEL="auth.Group"):
            steps = build_approval_steps_from_config(
                approvals=approvals,
                approval_user=self.creator,
                extra_fields={"workflow_id": self.workflow.id},
            )

        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]["assigned_to"], self.creator)
        self.assertEqual(steps[1]["assigned_role"], role)
        self.assertEqual(steps[1]["extra_fields"]["workflow_id"], self.workflow.id)
