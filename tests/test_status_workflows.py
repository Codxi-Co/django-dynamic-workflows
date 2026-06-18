"""Tests for business statuses and status-graph workflow transitions."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from approval_workflow.models import ApprovalFlow, ApprovalInstance

from django_workflow_engine.choices import (
    ApprovalTypes,
    StatusCategory,
    TransitionRejectBehavior,
    WorkflowAttachmentStatus,
    WorkflowStatus,
    WorkflowStrategy,
)
from django_workflow_engine.models import (
    Status,
    StatusAttachment,
    StatusHistory,
    StatusTransition,
    WorkFlow,
    WorkflowStatusNode,
)
from django_workflow_engine.services import (
    approve_pending_transition,
    attach_workflow_to_object,
    get_available_statuses,
    get_available_transitions,
    get_current_status,
    get_workflow_attachment,
    perform_transition,
    register_model_for_statuses,
    reject_pending_transition,
    set_status,
)
from sandbox.testapp.models import WorkflowTestModel

User = get_user_model()


class StatusWithoutWorkflowTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="status-user", email="status@example.com", password="pass"
        )
        self.todo = Status.objects.create(
            key="to_do", name_en="To Do", category=StatusCategory.OPEN
        )
        self.in_progress = Status.objects.create(
            key="in_progress",
            name_en="In Progress",
            category=StatusCategory.ACTIVE,
        )

    def test_model_can_use_statuses_without_workflow(self):
        register_model_for_statuses(
            WorkflowTestModel,
            statuses=[self.todo, self.in_progress],
            default_status=self.todo,
            status_field="status",
        )
        obj = WorkflowTestModel.objects.create(name="Ticket 1")

        status_attachment = set_status(
            obj, self.in_progress, user=self.user, reason="Started work"
        )
        obj.refresh_from_db()

        self.assertEqual(status_attachment.status, self.in_progress)
        self.assertEqual(get_current_status(obj), self.in_progress)
        self.assertEqual(obj.status, "in_progress")
        self.assertEqual(StatusAttachment.objects.count(), 1)
        self.assertEqual(StatusHistory.objects.count(), 1)
        self.assertEqual(StatusHistory.objects.first().from_status, None)
        self.assertEqual(
            list(get_available_statuses(WorkflowTestModel)),
            [self.todo, self.in_progress],
        )


class StatusGraphWorkflowTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="graph-user", email="graph@example.com", password="pass"
        )
        self.todo = Status.objects.create(
            key="to_do", name_en="To Do", category=StatusCategory.OPEN
        )
        self.in_progress = Status.objects.create(
            key="in_progress",
            name_en="In Progress",
            category=StatusCategory.ACTIVE,
        )
        self.resolved = Status.objects.create(
            key="resolved", name_en="Resolved", category=StatusCategory.DONE
        )
        register_model_for_statuses(
            WorkflowTestModel,
            statuses=[self.todo, self.in_progress, self.resolved],
            default_status=self.todo,
            status_field="status",
            allow_direct_change=True,
        )
        self.workflow = WorkFlow.objects.create(
            company=self.user,
            name_en="Ticket Status Workflow",
            name_ar="Ticket Status Workflow",
            status=WorkflowStatus.ACTIVE,
            strategy=WorkflowStrategy.STATUS_GRAPH,
        )
        self.todo_node = WorkflowStatusNode.objects.create(
            workflow=self.workflow,
            status=self.todo,
            is_initial=True,
            order=0,
        )
        self.progress_node = WorkflowStatusNode.objects.create(
            workflow=self.workflow,
            status=self.in_progress,
            order=1,
        )
        self.resolved_node = WorkflowStatusNode.objects.create(
            workflow=self.workflow,
            status=self.resolved,
            is_terminal=True,
            order=2,
        )
        self.start_transition = StatusTransition.objects.create(
            workflow=self.workflow,
            key="start_progress",
            name_en="Start Progress",
            from_status=self.todo_node,
            to_status=self.progress_node,
        )
        self.resolve_transition = StatusTransition.objects.create(
            workflow=self.workflow,
            key="resolve",
            name_en="Resolve",
            from_status=self.progress_node,
            to_status=self.resolved_node,
            requires_approval=True,
            approval_config={"approvals": [{"approval_type": ApprovalTypes.SELF}]},
            reject_behavior=TransitionRejectBehavior.STAY_CURRENT,
        )
        self.workflow.update_active_status()

    def test_status_graph_workflow_starts_at_initial_status_and_moves(self):
        obj = WorkflowTestModel.objects.create(name="Ticket 2")
        attachment = attach_workflow_to_object(
            obj,
            self.workflow,
            user=self.user,
            auto_start=True,
            disable_clone=True,
        )

        self.assertEqual(attachment.status, WorkflowAttachmentStatus.IN_PROGRESS)
        self.assertEqual(attachment.current_status, self.todo)
        self.assertEqual(get_current_status(obj), self.todo)
        self.assertEqual(
            list(get_available_transitions(obj, user=self.user)),
            [self.start_transition],
        )

        perform_transition(obj, "start_progress", user=self.user)
        attachment.refresh_from_db()
        obj.refresh_from_db()

        self.assertEqual(attachment.current_status, self.in_progress)
        self.assertEqual(get_current_status(obj), self.in_progress)
        self.assertEqual(obj.status, "in_progress")

    def test_required_approval_sets_pending_then_approval_completes_transition(self):
        obj = WorkflowTestModel.objects.create(name="Ticket 3")
        attach_workflow_to_object(
            obj,
            self.workflow,
            user=self.user,
            auto_start=True,
            disable_clone=True,
        )
        perform_transition(obj, "start_progress", user=self.user)

        perform_transition(obj, "resolve", user=self.user)
        attachment = get_workflow_attachment(obj)
        self.assertEqual(attachment.pending_transition, self.resolve_transition)
        self.assertEqual(attachment.current_status, self.in_progress)
        approval_flow = ApprovalFlow.objects.get(object_id=str(obj.pk))
        approval_instance = ApprovalInstance.objects.get(flow=approval_flow)
        self.assertEqual(
            approval_instance.extra_fields["status_transition_id"],
            self.resolve_transition.id,
        )
        self.assertEqual(
            approval_instance.extra_fields["status_transition_key"],
            "resolve",
        )

        approve_pending_transition(obj, user=self.user, reason="QA passed")
        attachment.refresh_from_db()

        self.assertEqual(attachment.pending_transition, None)
        self.assertEqual(attachment.current_status, self.resolved)
        self.assertEqual(attachment.status, WorkflowAttachmentStatus.COMPLETED)
        self.assertEqual(get_current_status(obj), self.resolved)

    def test_rejected_pending_transition_keeps_current_status(self):
        obj = WorkflowTestModel.objects.create(name="Ticket 4")
        attach_workflow_to_object(
            obj,
            self.workflow,
            user=self.user,
            auto_start=True,
            disable_clone=True,
        )
        perform_transition(obj, "start_progress", user=self.user)
        perform_transition(obj, "resolve", user=self.user)

        reject_pending_transition(obj, user=self.user, reason="Needs changes")
        attachment = get_workflow_attachment(obj)

        self.assertEqual(attachment.pending_transition, None)
        self.assertEqual(attachment.current_status, self.in_progress)
        self.assertEqual(get_current_status(obj), self.in_progress)
        self.assertEqual(
            StatusHistory.objects.filter(
                transition=self.resolve_transition,
                metadata__reject_behavior=TransitionRejectBehavior.STAY_CURRENT,
            ).count(),
            1,
        )
