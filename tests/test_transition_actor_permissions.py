"""Tests for status transition actor authorization rules."""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings

from django_workflow_engine.choices import (
    StatusCategory,
    WorkflowStatus,
    WorkflowStrategy,
)
from django_workflow_engine.models import (
    Status,
    StatusTransition,
    WorkFlow,
    WorkflowStatusNode,
)
from django_workflow_engine.services import (
    attach_workflow_to_object,
    get_available_transitions,
    perform_transition,
    register_model_for_statuses,
)
from django_workflow_engine.status_permissions import (
    _call_resolver,
    can_user_perform_transition,
    explain_transition_actor_denial,
    transition_actor_rule_matches,
)
from sandbox.testapp.models import WorkflowTestModel

User = get_user_model()


def get_assigned_user(obj):
    return obj.assigned_to


def get_ticket_assigned_user(obj, actor_type=None):
    assert obj._meta.label == "support.Ticket"
    assert actor_type == "assigned_user"
    return obj.ticket_engineer


def get_team_users(obj):
    return obj.team_users


def get_team_lead(obj):
    return obj.team_lead


def get_department_users(obj):
    return obj.department_users


def get_assignment_history_users(obj):
    return obj.assignment_history_users


def can_custom_transition(obj, user, rule):
    return user == obj.custom_allowed_user and rule["type"] == "custom_function"


def custom_transition_users(obj):
    return [obj.custom_allowed_user]


def invalid_custom_transition(obj, user, rule):
    return None


def broken_resolver():
    return True


class RelatedList:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class TransitionActorPermissionsTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@example.com", password="pass"
        )
        self.assignee = User.objects.create_user(
            username="assignee", email="assignee@example.com", password="pass"
        )
        self.team_member = User.objects.create_user(
            username="team-member", email="team@example.com", password="pass"
        )
        self.team_lead = User.objects.create_user(
            username="team-lead", email="lead@example.com", password="pass"
        )
        self.department_user = User.objects.create_user(
            username="department-user", email="dept@example.com", password="pass"
        )
        self.history_user = User.objects.create_user(
            username="history-user", email="history@example.com", password="pass"
        )
        self.specific_user = User.objects.create_user(
            username="specific-user", email="specific@example.com", password="pass"
        )
        self.custom_user = User.objects.create_user(
            username="custom-user", email="custom@example.com", password="pass"
        )
        self.first_manager = User.objects.create_user(
            username="first-manager", email="m1@example.com", password="pass"
        )
        self.second_manager = User.objects.create_user(
            username="second-manager", email="m2@example.com", password="pass"
        )
        self.third_manager = User.objects.create_user(
            username="third-manager", email="m3@example.com", password="pass"
        )
        self.other = User.objects.create_user(
            username="other", email="other@example.com", password="pass"
        )

        self.owner.manager = self.first_manager
        self.first_manager.manager = self.second_manager
        self.second_manager.manager = self.third_manager
        self.assignee.manager = self.first_manager

        self.obj = SimpleNamespace(
            created_by=self.owner,
            assigned_to=self.assignee,
            team_users=[self.team_member],
            team_lead=self.team_lead,
            department_users=[self.department_user],
            assignment_history_users=[self.history_user],
            custom_allowed_user=self.custom_user,
        )
        self.transition = SimpleNamespace(metadata={})

    def assertActorAllowedOnly(self, rule, allowed_user):
        self.transition.metadata = {"allowed_actors": [rule]}
        self.assertTrue(
            can_user_perform_transition(allowed_user, self.obj, self.transition)
        )
        self.assertFalse(
            can_user_perform_transition(self.other, self.obj, self.transition)
        )

    def test_empty_allowed_actors_keeps_transition_open(self):
        self.transition.metadata = {}
        self.assertTrue(
            can_user_perform_transition(self.other, self.obj, self.transition)
        )
        self.assertTrue(can_user_perform_transition(None, self.obj, self.transition))

    def test_actor_rules_reject_missing_user_and_invalid_rules(self):
        self.transition.metadata = {"allowed_actors": ["creator"]}
        self.assertFalse(can_user_perform_transition(None, self.obj, self.transition))
        self.assertFalse(transition_actor_rule_matches(self.owner, self.obj, None))
        self.assertFalse(
            transition_actor_rule_matches(self.owner, self.obj, {"type": "unknown"})
        )

    def test_owner_creator_and_assigned_user_rules(self):
        self.assertActorAllowedOnly("owner", self.owner)
        self.assertActorAllowedOnly("creator", self.owner)
        self.assertActorAllowedOnly("assigned_user", self.assignee)

    def test_actor_denial_message_includes_configured_rules(self):
        self.transition.metadata = {}
        self.assertEqual(
            explain_transition_actor_denial(self.transition),
            "User is not allowed to perform this transition",
        )

        self.transition.metadata = {
            "allowed_transition_actors": [
                "creator",
                {"type": "specific_user", "user": self.specific_user.id},
            ]
        }
        self.assertIn("creator", explain_transition_actor_denial(self.transition))
        self.assertIn("specific_user", explain_transition_actor_denial(self.transition))

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "TRANSITION_ACTORS": {
                "ASSIGNED_USER_FUNCTION": (
                    "tests.test_transition_actor_permissions.get_assigned_user"
                ),
                "TEAM_USERS_FUNCTION": (
                    "tests.test_transition_actor_permissions.get_team_users"
                ),
                "TEAM_LEAD_FUNCTION": (
                    "tests.test_transition_actor_permissions.get_team_lead"
                ),
                "DEPARTMENT_USERS_FUNCTION": (
                    "tests.test_transition_actor_permissions.get_department_users"
                ),
                "ASSIGNMENT_HISTORY_USERS_FUNCTION": (
                    "tests.test_transition_actor_permissions.get_assignment_history_users"
                ),
            }
        }
    )
    def test_configured_assignment_team_department_and_history_rules(self):
        self.assertActorAllowedOnly("assigned_user", self.assignee)
        self.assertActorAllowedOnly("team_member", self.team_member)
        self.assertActorAllowedOnly("team_lead", self.team_lead)
        self.assertActorAllowedOnly("department_member", self.department_user)
        self.assertActorAllowedOnly("assignment_history_user", self.history_user)

    @override_settings(
        DJANGO_WORKFLOW_ENGINE={
            "TRANSITION_ACTORS": {
                "default": {
                    "OWNER_FIELD": "created_by",
                    "MANAGER_FIELD": "manager",
                },
                "support.Ticket": {
                    "ASSIGNED_USER_FUNCTION": (
                        "tests.test_transition_actor_permissions."
                        "get_ticket_assigned_user"
                    )
                },
                "tasks.Task": {
                    "OWNER_FIELD": "requested_by",
                    "ASSIGNED_USER_FIELD": "assignee",
                },
            }
        }
    )
    def test_actor_fields_and_functions_are_resolved_per_model(self):
        ticket = SimpleNamespace(
            _meta=SimpleNamespace(app_label="support", label="support.Ticket"),
            created_by=self.owner,
            ticket_engineer=self.assignee,
        )
        task = SimpleNamespace(
            _meta=SimpleNamespace(app_label="tasks", label="tasks.Task"),
            requested_by=self.team_lead,
            assignee=self.team_member,
        )

        self.assertTrue(
            transition_actor_rule_matches(
                self.assignee, ticket, {"type": "assigned_user"}
            )
        )
        self.assertTrue(
            transition_actor_rule_matches(
                self.team_member, task, {"type": "assigned_user"}
            )
        )
        self.assertTrue(
            transition_actor_rule_matches(self.team_lead, task, {"type": "owner"})
        )
        self.assertFalse(
            transition_actor_rule_matches(
                self.assignee, task, {"type": "assigned_user"}
            )
        )

    def test_field_based_team_department_and_history_rules(self):
        self.obj.team = SimpleNamespace(users=RelatedList([self.team_member]))
        self.obj.team_with_lead = SimpleNamespace(lead=lambda: self.team_lead)
        self.obj.department = SimpleNamespace(users=[self.department_user])
        self.obj.assignment_history = [
            SimpleNamespace(user=self.history_user),
            SimpleNamespace(user=None),
        ]

        self.assertActorAllowedOnly("team_member", self.team_member)
        self.assertActorAllowedOnly(
            {"type": "team_lead", "field": "team_with_lead.lead"},
            self.team_lead,
        )
        self.assertActorAllowedOnly("department_member", self.department_user)
        self.assertActorAllowedOnly("assignment_history_user", self.history_user)

    def test_specific_user_rule(self):
        self.assertActorAllowedOnly(
            {"type": "specific_user", "user": self.specific_user.id},
            self.specific_user,
        )
        self.assertActorAllowedOnly(
            {"type": "specific_user", "approval_user": {"val": self.specific_user.id}},
            self.specific_user,
        )
        self.assertActorAllowedOnly(
            {"type": "specific_user", "approval_user": {"id": self.specific_user.id}},
            self.specific_user,
        )
        self.assertFalse(
            transition_actor_rule_matches(
                self.specific_user,
                self.obj,
                {"type": "specific_user", "user": 999999},
            )
        )
        self.assertFalse(
            transition_actor_rule_matches(
                self.specific_user,
                self.obj,
                {"type": "specific_user"},
            )
        )

    @override_settings(APPROVAL_ROLE_MODEL="auth.Group")
    def test_specific_role_rule_uses_current_role_strategy_payload(self):
        group = Group.objects.create(name="support-role")
        group.user_set.add(self.team_member)

        self.assertActorAllowedOnly(
            {
                "type": "specific_role",
                "user_role": group.id,
                "role_selection_strategy": "round_robin",
            },
            self.team_member,
        )
        self.assertFalse(
            transition_actor_rule_matches(
                self.team_member, self.obj, {"type": "specific_role"}
            )
        )

    def test_owner_manager_and_assigned_user_manager_levels(self):
        self.assertActorAllowedOnly("owner_manager", self.first_manager)
        self.assertActorAllowedOnly(
            {"type": "owner_manager", "manager_levels": [2]},
            self.second_manager,
        )
        self.assertActorAllowedOnly(
            {"type": "owner_manager", "levels": [1, 3]},
            self.third_manager,
        )
        self.assertActorAllowedOnly(
            {"type": "assigned_user_manager", "level": 1},
            self.first_manager,
        )
        self.assertActorAllowedOnly(
            {"type": "assigned_user_manager", "levels": 2},
            self.second_manager,
        )
        self.assertActorAllowedOnly(
            {"type": "creator_manager", "manager_levels": "2"},
            self.second_manager,
        )
        self.assertFalse(
            transition_actor_rule_matches(
                self.first_manager,
                SimpleNamespace(created_by=None),
                {"type": "owner_manager"},
            )
        )
        self.third_manager.manager = self.first_manager
        self.assertFalse(
            transition_actor_rule_matches(
                self.other,
                self.obj,
                {
                    "type": "owner_manager",
                    "manager_levels": [4],
                    "max_depth": 5,
                },
            )
        )

    def test_custom_function_rule(self):
        self.assertActorAllowedOnly(
            {
                "type": "custom_function",
                "function": "tests.test_transition_actor_permissions.can_custom_transition",
            },
            self.custom_user,
        )
        self.assertActorAllowedOnly(
            {
                "type": "custom_function",
                "function_path": (
                    "tests.test_transition_actor_permissions.custom_transition_users"
                ),
            },
            self.custom_user,
        )
        self.assertFalse(
            transition_actor_rule_matches(
                self.custom_user, self.obj, {"type": "custom_function"}
            )
        )
        self.assertFalse(
            transition_actor_rule_matches(
                self.custom_user,
                self.obj,
                {
                    "type": "custom_function",
                    "resolver": (
                        "tests.test_transition_actor_permissions.invalid_custom_transition"
                    ),
                },
            )
        )

    def test_defensive_actor_helper_branches(self):
        with self.assertRaises(TypeError):
            _call_resolver(
                "tests.test_transition_actor_permissions.broken_resolver",
                self.obj,
            )
        self.assertFalse(
            transition_actor_rule_matches(
                self.owner,
                None,
                {"type": "creator"},
            )
        )
        self.assertFalse(
            transition_actor_rule_matches(
                self.team_member,
                SimpleNamespace(team=None),
                {"type": "team_member"},
            )
        )


@override_settings(ROOT_URLCONF="django_workflow_engine.urls")
class TransitionActorIntegrationTest(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(username="creator-api", password="pass")
        self.other = User.objects.create_user(username="other-api", password="pass")
        self.todo = Status.objects.create(
            key="todo", name_en="To Do", category=StatusCategory.OPEN
        )
        self.progress = Status.objects.create(
            key="progress", name_en="Progress", category=StatusCategory.ACTIVE
        )
        register_model_for_statuses(
            WorkflowTestModel,
            statuses=[self.todo, self.progress],
            default_status=self.todo,
            status_field="status",
        )
        self.workflow = WorkFlow.objects.create(
            company=self.creator,
            name_en="Actor Flow",
            status=WorkflowStatus.ACTIVE,
            strategy=WorkflowStrategy.STATUS_GRAPH,
        )
        self.todo_node = WorkflowStatusNode.objects.create(
            workflow=self.workflow,
            status=self.todo,
            is_initial=True,
        )
        self.progress_node = WorkflowStatusNode.objects.create(
            workflow=self.workflow,
            status=self.progress,
        )
        self.transition = StatusTransition.objects.create(
            workflow=self.workflow,
            key="start",
            name_en="Start",
            from_status=self.todo_node,
            to_status=self.progress_node,
            metadata={"allowed_actors": ["creator"]},
        )
        self.workflow.update_active_status()

    def test_available_transitions_and_perform_transition_respect_allowed_actors(self):
        ticket = WorkflowTestModel.objects.create(
            name="Actor Ticket", created_by=self.creator
        )
        attach_workflow_to_object(
            ticket,
            self.workflow,
            user=self.creator,
            auto_start=True,
            disable_clone=True,
        )

        self.assertEqual(get_available_transitions(ticket, user=self.other), [])
        self.assertEqual(
            list(get_available_transitions(ticket, user=self.creator)),
            [self.transition],
        )

        with self.assertRaisesMessage(ValueError, "not available"):
            perform_transition(ticket, "start", user=self.other)

        perform_transition(ticket, "start", user=self.creator)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "progress")
