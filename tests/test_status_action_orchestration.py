"""End-to-end orchestration tests for developer-owned workflow actions."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from rest_framework.test import APIClient

from django_workflow_engine.choices import (
    ActionFailurePolicy,
    ActionType,
    ApprovalTypes,
    StatusCategory,
)
from django_workflow_engine.models import Status, WorkflowAction, WorkflowStatusNode
from django_workflow_engine.services import (
    attach_workflow_to_object,
    get_current_status,
    perform_transition,
    reject_pending_transition,
    set_status,
)
from django_workflow_engine.status_services import create_status_flow_design
from sandbox.testapp.models import WorkflowTestModel

User = get_user_model()
ACTION_CALLS = []


def record_project_action(**context):
    """Represent a project notification, SLA, task, or scheduling integration."""
    ACTION_CALLS.append(
        {
            "event": context.get("event"),
            "status": getattr(context.get("status"), "key", None),
            "transition": getattr(context.get("transition"), "key", None),
            "metadata": context.get("metadata", {}),
            "parameters": {
                key: value
                for key, value in context.items()
                if key
                in {
                    "team",
                    "delay_days",
                    "sla_operation",
                    "notification",
                    "task_type",
                    "escalation_level",
                }
            },
        }
    )
    return True


def action_condition(**context):
    return context.get("metadata", {}).get("run_action", False)


def failing_action(**context):
    raise RuntimeError("project action failed")


def validate_survey_submission(**context):
    return bool(context["metadata"].get("survey_submitted"))


def validate_check_in(**context):
    return bool(context["metadata"].get("latitude")) and bool(
        context["metadata"].get("longitude")
    )


def validate_escalation_level(**context):
    return context["metadata"].get("escalation_level", 0) <= 3


class StatusActionOrchestrationBase(TestCase):
    def setUp(self):
        ACTION_CALLS.clear()
        self.user = User.objects.create_user(
            username="orchestration-user",
            email="orchestration@example.com",
            password="pass",
        )

    def create_flow(self, statuses, transitions, default_status=None):
        return create_status_flow_design(
            {
                "model": "testapp.workflowtestmodel",
                "company": self.user.id,
                "status_field": "status",
                "allow_direct_change": False,
                "default_status": default_status or statuses[0]["code"],
                "statuses": statuses,
                "transitions": transitions,
            },
            user=self.user,
        )

    def attach(self, flow, name="Ticket"):
        ticket = WorkflowTestModel.objects.create(name=name, created_by=self.user)
        workflow = WorkflowStatusNode.objects.get(
            workflow_id=flow["workflow"]["id"], is_initial=True
        ).workflow
        attach_workflow_to_object(
            ticket,
            workflow,
            user=self.user,
            auto_start=True,
            disable_clone=True,
        )
        return ticket

    @staticmethod
    def action(event, **parameters):
        return {
            "function_path": (
                "tests.test_status_action_orchestration.record_project_action"
            ),
            "parameters": {"event": event, **parameters},
        }


class FullDesignActionContractTest(StatusActionOrchestrationBase):
    def test_full_design_creates_and_returns_status_and_transition_actions(self):
        flow = self.create_flow(
            statuses=[
                {
                    "code": "new",
                    "name_en": "New",
                    "category": StatusCategory.OPEN,
                    "actions": [self.action("initial_notification")],
                },
                {
                    "code": "assigned",
                    "name_en": "Assigned",
                    "category": StatusCategory.ACTIVE,
                },
            ],
            transitions=[
                {
                    "code": "assign",
                    "name_en": "Assign",
                    "from": "new",
                    "to": "assigned",
                    "actions": [
                        {
                            **self.action("notify_assignee", notification="assigned"),
                            "action_type": ActionType.AFTER_TRANSITION,
                            "condition_function": (
                                "tests.test_status_action_orchestration.action_condition"
                            ),
                            "failure_policy": ActionFailurePolicy.STOP,
                        }
                    ],
                }
            ],
        )

        self.assertEqual(
            flow["nodes"][0]["actions"][0]["function_path"],
            "tests.test_status_action_orchestration.record_project_action",
        )
        transition_action = flow["transitions"][0]["actions"][0]
        self.assertEqual(transition_action["action_type"], ActionType.AFTER_TRANSITION)
        self.assertEqual(
            transition_action["condition_function"],
            "tests.test_status_action_orchestration.action_condition",
        )
        self.assertEqual(transition_action["failure_policy"], ActionFailurePolicy.STOP)

    def test_status_graph_clone_preserves_nodes_transitions_and_actions(self):
        flow = self.create_flow(
            statuses=[
                {
                    "code": "new",
                    "name_en": "New",
                    "actions": [self.action("entered_new")],
                },
                {"code": "done", "name_en": "Done"},
            ],
            transitions=[
                {
                    "code": "finish",
                    "name_en": "Finish",
                    "from": "new",
                    "to": "done",
                    "actions": [
                        {
                            **self.action("finished"),
                            "condition_function": (
                                "tests.test_status_action_orchestration.action_condition"
                            ),
                            "failure_policy": ActionFailurePolicy.RAISE,
                        }
                    ],
                }
            ],
        )
        workflow = WorkflowStatusNode.objects.get(
            workflow_id=flow["workflow"]["id"], is_initial=True
        ).workflow

        clone = workflow.clone()

        self.assertEqual(clone.status_nodes.count(), 2)
        cloned_transition = clone.status_transitions.get(key="finish")
        cloned_action = cloned_transition.actions.get()
        self.assertEqual(
            cloned_action.condition_function,
            "tests.test_status_action_orchestration.action_condition",
        )
        self.assertEqual(cloned_action.failure_policy, ActionFailurePolicy.RAISE)

    @override_settings(ROOT_URLCONF="django_workflow_engine.urls")
    def test_actions_api_accepts_transition_scope(self):
        flow = self.create_flow(
            statuses=[
                {"code": "new", "name_en": "New"},
                {"code": "assigned", "name_en": "Assigned"},
            ],
            transitions=[
                {
                    "code": "assign",
                    "name_en": "Assign",
                    "from": "new",
                    "to": "assigned",
                }
            ],
        )
        client = APIClient()
        client.force_authenticate(self.user)
        transition_id = flow["transitions"][0]["id"]

        response = client.post(
            "/status/actions/",
            {
                "transition": transition_id,
                "action_type": ActionType.AFTER_TRANSITION,
                "function_path": (
                    "tests.test_status_action_orchestration.record_project_action"
                ),
                "failure_policy": ActionFailurePolicy.RAISE,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["transition"], transition_id)
        self.assertEqual(
            client.get(f"/status/actions/?transition={transition_id}").data[0][
                "failure_policy"
            ],
            ActionFailurePolicy.RAISE,
        )


class ActionLifecycleBehaviorTest(StatusActionOrchestrationBase):
    def test_initial_direct_and_rejection_entries_run_status_actions(self):
        flow = self.create_flow(
            statuses=[
                {
                    "code": "new",
                    "name_en": "New",
                    "actions": [self.action("entered_new")],
                },
                {
                    "code": "review",
                    "name_en": "Review",
                    "actions": [self.action("entered_review")],
                },
                {
                    "code": "rejected",
                    "name_en": "Rejected",
                    "is_terminal": True,
                    "actions": [self.action("entered_rejected")],
                },
            ],
            transitions=[
                {
                    "code": "review",
                    "name_en": "Review",
                    "from": "new",
                    "to": "review",
                    "approvals": [{"approval_type": ApprovalTypes.SELF}],
                    "reject_behavior": "move_to_specific_status",
                    "reject_to": "rejected",
                }
            ],
        )
        ticket = self.attach(flow)
        self.assertEqual([call["event"] for call in ACTION_CALLS], ["entered_new"])

        review_status = Status.objects.get(key="review")
        set_status(
            ticket,
            review_status,
            user=self.user,
            workflow=WorkflowStatusNode.objects.get(
                workflow_id=flow["workflow"]["id"], status=review_status
            ).workflow,
            enforce_workflow=False,
        )
        self.assertEqual(ACTION_CALLS[-1]["event"], "entered_review")

        new_status = Status.objects.get(key="new")
        set_status(
            ticket,
            new_status,
            user=self.user,
            workflow=WorkflowStatusNode.objects.get(
                workflow_id=flow["workflow"]["id"], status=new_status
            ).workflow,
            enforce_workflow=False,
        )
        perform_transition(ticket, "review", user=self.user)
        reject_pending_transition(ticket, user=self.user, reason="Invalid request")
        self.assertEqual(ACTION_CALLS[-1]["event"], "entered_rejected")

    def test_conditions_and_failure_policies_control_order(self):
        flow = self.create_flow(
            statuses=[
                {"code": "new", "name_en": "New"},
                {"code": "done", "name_en": "Done"},
            ],
            transitions=[
                {
                    "code": "finish",
                    "name_en": "Finish",
                    "from": "new",
                    "to": "done",
                    "actions": [
                        {
                            "action_type": ActionType.BEFORE_TRANSITION,
                            "function_path": (
                                "tests.test_status_action_orchestration.record_project_action"
                            ),
                            "condition_function": (
                                "tests.test_status_action_orchestration.action_condition"
                            ),
                            "parameters": {"event": "conditional"},
                            "order": 1,
                        },
                        {
                            "action_type": ActionType.BEFORE_TRANSITION,
                            "function_path": (
                                "tests.test_status_action_orchestration.failing_action"
                            ),
                            "failure_policy": ActionFailurePolicy.STOP,
                            "order": 2,
                        },
                        {
                            **self.action("must_not_run"),
                            "action_type": ActionType.BEFORE_TRANSITION,
                            "order": 3,
                        },
                    ],
                }
            ],
        )
        ticket = self.attach(flow)

        perform_transition(
            ticket,
            "finish",
            user=self.user,
            metadata={"run_action": True},
        )

        self.assertEqual([call["event"] for call in ACTION_CALLS], ["conditional"])
        self.assertEqual(get_current_status(ticket).key, "done")

    def test_raise_failure_policy_rolls_back_transition(self):
        flow = self.create_flow(
            statuses=[
                {"code": "new", "name_en": "New"},
                {"code": "done", "name_en": "Done"},
            ],
            transitions=[
                {
                    "code": "finish",
                    "name_en": "Finish",
                    "from": "new",
                    "to": "done",
                    "actions": [
                        {
                            "action_type": ActionType.BEFORE_TRANSITION,
                            "function_path": (
                                "tests.test_status_action_orchestration.failing_action"
                            ),
                            "failure_policy": ActionFailurePolicy.RAISE,
                        }
                    ],
                }
            ],
        )
        ticket = self.attach(flow)

        with self.assertRaisesMessage(Exception, "project action failed"):
            perform_transition(ticket, "finish", user=self.user)

        self.assertEqual(get_current_status(ticket).key, "new")


class SupportWorkflowBusinessTest(StatusActionOrchestrationBase):
    def test_standard_support_actions_are_delegated_to_project_functions(self):
        flow = self.create_flow(
            statuses=[
                {"code": "new", "name_en": "New"},
                {"code": "assigned", "name_en": "Assigned"},
                {"code": "in_progress", "name_en": "In Progress"},
                {"code": "pending_customer", "name_en": "Pending Customer"},
                {
                    "code": "resolved",
                    "name_en": "Resolved",
                    "actions": [
                        self.action(
                            "schedule_auto_close",
                            delay_days=2,
                            task_type="close_if_still_resolved",
                        )
                    ],
                },
                {"code": "closed", "name_en": "Closed", "is_terminal": True},
            ],
            transitions=[
                {
                    "code": "assign",
                    "name_en": "Assign",
                    "from": "new",
                    "to": "assigned",
                    "actions": [
                        self.action("notify_assigned_user", notification="assigned"),
                        self.action("start_sla", sla_operation="start"),
                    ],
                },
                {
                    "code": "start",
                    "name_en": "Start",
                    "from": "assigned",
                    "to": "in_progress",
                },
                {
                    "code": "request_customer",
                    "name_en": "Request Customer Information",
                    "from": "in_progress",
                    "to": "pending_customer",
                    "actions": [
                        self.action("email_customer", notification="request_info"),
                        self.action("pause_sla", sla_operation="pause"),
                    ],
                },
                {
                    "code": "resume",
                    "name_en": "Resume",
                    "from": "pending_customer",
                    "to": "in_progress",
                    "actions": [
                        self.action(
                            "notify_engineer", notification="customer_response"
                        ),
                        self.action("resume_sla", sla_operation="resume"),
                    ],
                },
                {
                    "code": "resolve",
                    "name_en": "Resolve",
                    "from": "in_progress",
                    "to": "resolved",
                    "actions": [
                        self.action("send_survey", notification="survey"),
                        self.action("stop_sla", sla_operation="stop"),
                    ],
                },
                {
                    "code": "close",
                    "name_en": "Close",
                    "from": "resolved",
                    "to": "closed",
                    "metadata": {
                        "required_metadata_keys": ["survey_submitted"],
                        "validation_function": (
                            "tests.test_status_action_orchestration."
                            "validate_survey_submission"
                        ),
                    },
                },
            ],
        )
        ticket = self.attach(flow)

        perform_transition(ticket, "assign", user=self.user)
        perform_transition(ticket, "start", user=self.user)
        perform_transition(ticket, "request_customer", user=self.user)
        perform_transition(ticket, "resume", user=self.user)
        perform_transition(ticket, "resolve", user=self.user)

        self.assertEqual(
            [call["event"] for call in ACTION_CALLS],
            [
                "notify_assigned_user",
                "start_sla",
                "email_customer",
                "pause_sla",
                "notify_engineer",
                "resume_sla",
                "send_survey",
                "stop_sla",
                "schedule_auto_close",
            ],
        )
        self.assertEqual(ACTION_CALLS[-1]["parameters"]["delay_days"], 2)

        with self.assertRaisesMessage(ValueError, "survey_submitted"):
            perform_transition(ticket, "close", user=self.user)
        perform_transition(
            ticket,
            "close",
            user=self.user,
            metadata={"survey_submitted": True},
        )
        self.assertEqual(get_current_status(ticket).key, "closed")


class EscalationWorkflowBusinessTest(StatusActionOrchestrationBase):
    def test_l1_l2_l3_escalation_uses_actions_and_custom_level_validation(self):
        escalation_actions = [
            self.action("reassign_next_team", team="next"),
            self.action("notify_team_leader", notification="escalation"),
            self.action("log_escalation"),
            self.action("calculate_team_sla", sla_operation="calculate"),
        ]
        flow = self.create_flow(
            statuses=[
                {"code": "new", "name_en": "New"},
                {"code": "l1", "name_en": "Level 1 Support"},
                {"code": "l2", "name_en": "Level 2 Support"},
                {"code": "l3", "name_en": "Level 3 Support"},
                {"code": "resolved", "name_en": "Resolved"},
                {"code": "closed", "name_en": "Closed", "is_terminal": True},
            ],
            transitions=[
                {
                    "code": "assign_l1",
                    "name_en": "Assign L1",
                    "from": "new",
                    "to": "l1",
                    "actions": [self.action("assign_l1_team", team="l1")],
                },
                {
                    "code": "escalate_l2",
                    "name_en": "Escalate L2",
                    "from": "l1",
                    "to": "l2",
                    "metadata": {
                        "required_metadata_keys": ["escalation_level"],
                        "validation_function": (
                            "tests.test_status_action_orchestration."
                            "validate_escalation_level"
                        ),
                    },
                    "actions": escalation_actions,
                },
                {
                    "code": "escalate_l3",
                    "name_en": "Escalate L3",
                    "from": "l2",
                    "to": "l3",
                    "metadata": {
                        "required_metadata_keys": ["escalation_level"],
                        "validation_function": (
                            "tests.test_status_action_orchestration."
                            "validate_escalation_level"
                        ),
                    },
                    "actions": escalation_actions,
                },
                {
                    "code": "resolve",
                    "name_en": "Resolve",
                    "from": "l3",
                    "to": "resolved",
                },
                {
                    "code": "close",
                    "name_en": "Close",
                    "from": "resolved",
                    "to": "closed",
                },
            ],
        )
        ticket = self.attach(flow)
        perform_transition(ticket, "assign_l1", user=self.user)

        with self.assertRaisesMessage(ValueError, "failed custom validation"):
            perform_transition(
                ticket,
                "escalate_l2",
                user=self.user,
                metadata={"escalation_level": 4},
            )

        perform_transition(
            ticket,
            "escalate_l2",
            user=self.user,
            metadata={"escalation_level": 2},
        )
        perform_transition(
            ticket,
            "escalate_l3",
            user=self.user,
            metadata={"escalation_level": 3},
        )

        self.assertEqual(
            [call["event"] for call in ACTION_CALLS],
            [
                "assign_l1_team",
                "reassign_next_team",
                "notify_team_leader",
                "log_escalation",
                "calculate_team_sla",
                "reassign_next_team",
                "notify_team_leader",
                "log_escalation",
                "calculate_team_sla",
            ],
        )
        self.assertEqual(get_current_status(ticket).name_en, "Level 3 Support")


class VisitWorkflowBusinessTest(StatusActionOrchestrationBase):
    def test_visit_actions_and_location_validator(self):
        flow = self.create_flow(
            statuses=[
                {"code": "new", "name_en": "New"},
                {"code": "assigned", "name_en": "Assigned"},
                {
                    "code": "visit_scheduled",
                    "name_en": "Site Visit Scheduled",
                    "actions": [
                        self.action(
                            "send_appointment_notification",
                            notification="appointment",
                        )
                    ],
                },
                {"code": "on_site", "name_en": "On Site"},
                {"code": "pending_parts", "name_en": "Pending Parts"},
                {"code": "resolved", "name_en": "Resolved", "is_terminal": True},
            ],
            transitions=[
                {
                    "code": "assign",
                    "name_en": "Assign",
                    "from": "new",
                    "to": "assigned",
                },
                {
                    "code": "schedule_visit",
                    "name_en": "Schedule Visit",
                    "from": "assigned",
                    "to": "visit_scheduled",
                    "actions": [
                        self.action("notify_user", notification="visit"),
                        self.action("create_visit_task", task_type="site_visit"),
                    ],
                },
                {
                    "code": "check_in",
                    "name_en": "Check In",
                    "from": "visit_scheduled",
                    "to": "on_site",
                    "metadata": {
                        "required_metadata_keys": ["latitude", "longitude"],
                        "validation_function": (
                            "tests.test_status_action_orchestration.validate_check_in"
                        ),
                    },
                    "actions": [self.action("record_location")],
                },
                {
                    "code": "request_parts",
                    "name_en": "Request Parts",
                    "from": "on_site",
                    "to": "pending_parts",
                    "actions": [
                        self.action("request_parts", task_type="parts_request")
                    ],
                },
                {
                    "code": "parts_received",
                    "name_en": "Parts Received",
                    "from": "pending_parts",
                    "to": "on_site",
                },
                {
                    "code": "resolve",
                    "name_en": "Resolve",
                    "from": "on_site",
                    "to": "resolved",
                },
            ],
        )
        ticket = self.attach(flow)
        perform_transition(ticket, "assign", user=self.user)
        perform_transition(ticket, "schedule_visit", user=self.user)

        self.assertEqual(
            [call["event"] for call in ACTION_CALLS],
            [
                "notify_user",
                "create_visit_task",
                "send_appointment_notification",
            ],
        )
        with self.assertRaisesMessage(ValueError, "longitude"):
            perform_transition(
                ticket,
                "check_in",
                user=self.user,
                metadata={"latitude": 24.7136},
            )
        perform_transition(
            ticket,
            "check_in",
            user=self.user,
            metadata={"latitude": 24.7136, "longitude": 46.6753},
        )
        perform_transition(ticket, "request_parts", user=self.user)
        perform_transition(ticket, "parts_received", user=self.user)
        perform_transition(ticket, "resolve", user=self.user)

        self.assertEqual(ACTION_CALLS[-2]["event"], "record_location")
        self.assertEqual(ACTION_CALLS[-1]["event"], "request_parts")
        self.assertEqual(get_current_status(ticket).key, "resolved")
