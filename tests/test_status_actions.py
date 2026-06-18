"""Tests for actions attached to workflow status nodes."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from rest_framework.test import APIClient

from django_workflow_engine.choices import (
    ActionType,
    StatusCategory,
    WorkflowStatus,
    WorkflowStrategy,
)
from django_workflow_engine.models import (
    Status,
    StatusTransition,
    WorkFlow,
    WorkflowAction,
    WorkflowStatusNode,
)
from django_workflow_engine.services import (
    attach_workflow_to_object,
    perform_transition,
    register_model_for_statuses,
)
from django_workflow_engine.status_services import create_status_flow_design
from sandbox.testapp.models import WorkflowTestModel

User = get_user_model()

STATUS_ACTION_CALLS = []


def record_status_action(**kwargs):
    """Test action handler used by legacy action import."""
    STATUS_ACTION_CALLS.append(
        {
            "status": kwargs["status"].key,
            "status_node_id": kwargs["status_node"].id,
            "transition": kwargs["transition"].key,
            "previous_status": kwargs["previous_status"].key,
            "obj_id": kwargs["obj"].id,
            "attachment_id": kwargs["attachment"].id,
            "user_id": kwargs["user"].id,
            "sla_minutes": kwargs.get("sla_minutes"),
            "notify_user": kwargs.get("notify_user"),
            "order": kwargs.get("order"),
        }
    )
    return "executed"


class StatusActionExecutionTest(TestCase):
    def setUp(self):
        STATUS_ACTION_CALLS.clear()
        self.user = User.objects.create_user(
            username="status-action-user",
            email="status-action@example.com",
            password="pass",
        )
        self.todo = Status.objects.create(
            key="to_do", name_en="To Do", category=StatusCategory.OPEN
        )
        self.review = Status.objects.create(
            key="in_review", name_en="In Review", category=StatusCategory.ACTIVE
        )
        register_model_for_statuses(
            WorkflowTestModel,
            statuses=[self.todo, self.review],
            default_status=self.todo,
            status_field="status",
        )
        self.workflow = WorkFlow.objects.create(
            company=self.user,
            name_en="Task Status Workflow",
            name_ar="Task Status Workflow",
            status=WorkflowStatus.ACTIVE,
            strategy=WorkflowStrategy.STATUS_GRAPH,
        )
        self.todo_node = WorkflowStatusNode.objects.create(
            workflow=self.workflow,
            status=self.todo,
            is_initial=True,
            order=0,
        )
        self.review_node = WorkflowStatusNode.objects.create(
            workflow=self.workflow,
            status=self.review,
            order=1,
        )
        self.transition = StatusTransition.objects.create(
            workflow=self.workflow,
            key="send_to_review",
            name_en="Send To Review",
            from_status=self.todo_node,
            to_status=self.review_node,
        )
        self.workflow.update_active_status()

    def _attach_object(self):
        obj = WorkflowTestModel.objects.create(name="Review action task")
        attach_workflow_to_object(
            obj,
            self.workflow,
            user=self.user,
            auto_start=True,
            disable_clone=True,
        )
        return obj

    def test_entering_status_executes_status_actions(self):
        WorkflowAction.objects.create(
            status_node=self.review_node,
            action_type=ActionType.ON_STATUS_ENTER,
            function_path="tests.test_status_actions.record_status_action",
            parameters={"sla_minutes": 30, "notify_user": "qa@example.com"},
        )
        obj = self._attach_object()

        perform_transition(obj, "send_to_review", user=self.user)

        self.assertEqual(len(STATUS_ACTION_CALLS), 1)
        call = STATUS_ACTION_CALLS[0]
        self.assertEqual(call["status"], "in_review")
        self.assertEqual(call["status_node_id"], self.review_node.id)
        self.assertEqual(call["transition"], "send_to_review")
        self.assertEqual(call["previous_status"], "to_do")
        self.assertEqual(call["obj_id"], obj.id)
        self.assertEqual(call["user_id"], self.user.id)
        self.assertEqual(call["sla_minutes"], 30)
        self.assertEqual(call["notify_user"], "qa@example.com")

    def test_status_actions_respect_order_and_skip_inactive_actions(self):
        WorkflowAction.objects.create(
            status_node=self.review_node,
            action_type=ActionType.ON_STATUS_ENTER,
            function_path="tests.test_status_actions.record_status_action",
            parameters={"order": "second"},
            order=20,
        )
        WorkflowAction.objects.create(
            status_node=self.review_node,
            action_type=ActionType.ON_STATUS_ENTER,
            function_path="tests.test_status_actions.record_status_action",
            parameters={"order": "first"},
            order=10,
        )
        WorkflowAction.objects.create(
            status_node=self.review_node,
            action_type=ActionType.ON_STATUS_ENTER,
            function_path="tests.test_status_actions.record_status_action",
            parameters={"order": "inactive"},
            order=1,
            is_active=False,
        )
        obj = self._attach_object()

        perform_transition(obj, "send_to_review", user=self.user)

        self.assertEqual(
            [call["order"] for call in STATUS_ACTION_CALLS], ["first", "second"]
        )


@override_settings(ROOT_URLCONF="django_workflow_engine.urls")
class StatusActionAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="status-action-api-user",
            email="status-action-api@example.com",
            password="pass",
        )
        self.client.force_authenticate(self.user)
        self.status = Status.objects.create(
            key="review", name_en="Review", category=StatusCategory.ACTIVE
        )
        self.workflow = WorkFlow.objects.create(
            company=self.user,
            name_en="Action API Workflow",
            name_ar="Action API Workflow",
            status=WorkflowStatus.ACTIVE,
            strategy=WorkflowStrategy.STATUS_GRAPH,
        )
        self.node = WorkflowStatusNode.objects.create(
            workflow=self.workflow,
            status=self.status,
            is_initial=True,
        )

    def test_status_action_api_creates_and_lists_actions(self):
        response = self.client.post(
            "/status/actions/",
            {
                "status_node": self.node.id,
                "action_type": ActionType.ON_STATUS_ENTER,
                "function_path": "tests.test_status_actions.record_status_action",
                "parameters": {"sla_minutes": 45},
                "order": 5,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status_node"], self.node.id)
        self.assertEqual(response.data["action_type"], ActionType.ON_STATUS_ENTER)

        list_response = self.client.get(f"/status/actions/?status_node={self.node.id}")
        self.assertEqual(list_response.status_code, 200, list_response.data)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(list_response.data[0]["parameters"], {"sla_minutes": 45})

    def test_status_action_api_rejects_unsupported_action_type(self):
        response = self.client.post(
            "/status/actions/",
            {
                "status_node": self.node.id,
                "action_type": ActionType.AFTER_APPROVE,
                "function_path": "tests.test_status_actions.record_status_action",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("action_type", response.data)


class StatusActionFlowDesignTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="status-action-flow-user",
            email="status-action-flow@example.com",
            password="pass",
        )

    def test_flow_design_creates_status_enter_actions(self):
        result = create_status_flow_design(
            {
                "model": "testapp.workflowtestmodel",
                "company": self.user.id,
                "default_status": "new",
                "statuses": [
                    {
                        "code": "new",
                        "name_en": "New",
                        "name_ar": "جديد",
                        "category": StatusCategory.OPEN,
                    },
                    {
                        "code": "in_review",
                        "name_en": "In Review",
                        "name_ar": "قيد المراجعة",
                        "category": StatusCategory.ACTIVE,
                        "actions": [
                            {
                                "function_path": (
                                    "tests.test_status_actions.record_status_action"
                                ),
                                "parameters": {
                                    "sla_minutes": 30,
                                    "notify_user": "qa@example.com",
                                },
                            }
                        ],
                    },
                ],
                "transitions": [
                    {
                        "code": "send_to_review",
                        "name_en": "Send To Review",
                        "from": "new",
                        "to": "in_review",
                    }
                ],
            },
            user=self.user,
        )

        review_node = WorkflowStatusNode.objects.get(
            workflow_id=result["workflow"]["id"], status__key="in_review"
        )
        action = WorkflowAction.objects.get(status_node=review_node)
        self.assertEqual(action.action_type, ActionType.ON_STATUS_ENTER)
        self.assertEqual(action.parameters["sla_minutes"], 30)
        self.assertEqual(action.parameters["notify_user"], "qa@example.com")
