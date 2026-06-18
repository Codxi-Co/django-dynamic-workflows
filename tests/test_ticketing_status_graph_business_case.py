"""Ticketing business case for status-graph workflows."""

from django.contrib.auth import get_user_model
from django.test import TestCase

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
    StatusTransition,
    WorkFlow,
    WorkflowStatusNode,
)
from django_workflow_engine.services import (
    approve_pending_transition,
    attach_workflow_to_object,
    get_current_status,
    get_workflow_attachment,
    perform_transition,
    register_model_for_statuses,
    reject_pending_transition,
)
from sandbox.testapp.models import WorkflowTestModel

User = get_user_model()


class TicketingStatusGraphBusinessCaseTest(TestCase):
    """Ticketing flow with PM triage, hold/resume, approvals, and rejection evidence."""

    def setUp(self):
        self.pm = User.objects.create_user(
            username="pm", email="pm@example.com", password="pass"
        )
        self.developer = User.objects.create_user(
            username="developer", email="developer@example.com", password="pass"
        )

        # The named business-visible statuses.
        self.new = self._status("new", "New", StatusCategory.OPEN)
        self.in_progress = self._status(
            "in_progress", "In Progress", StatusCategory.ACTIVE
        )
        self.on_hold = self._status("on_hold", "On Hold", StatusCategory.PAUSED)
        self.resolved = self._status("resolved", "Resolved", StatusCategory.DONE)
        self.closed = self._status("closed", "Closed", StatusCategory.DONE)
        self.duplicated = self._status(
            "duplicated", "Duplicated", StatusCategory.CANCELLED
        )
        self.rejected = self._status("rejected", "Rejected", StatusCategory.CANCELLED)

        # Internal intake status: ticket is not visible as New until PM approves it.
        self.pending_pm_review = self._status(
            "pending_pm_review", "Pending PM Review", StatusCategory.OPEN
        )

        register_model_for_statuses(
            WorkflowTestModel,
            statuses=[
                self.pending_pm_review,
                self.new,
                self.in_progress,
                self.on_hold,
                self.resolved,
                self.closed,
                self.duplicated,
                self.rejected,
            ],
            default_status=self.pending_pm_review,
            status_field="status",
        )

        self.workflow = WorkFlow.objects.create(
            company=self.pm,
            name_en="Ticketing Status Workflow",
            name_ar="Ticketing Status Workflow",
            status=WorkflowStatus.ACTIVE,
            strategy=WorkflowStrategy.STATUS_GRAPH,
        )

        self.nodes = {
            "pending_pm_review": self._node(self.pending_pm_review, is_initial=True),
            "new": self._node(self.new),
            "in_progress": self._node(self.in_progress),
            "on_hold": self._node(self.on_hold),
            "resolved": self._node(self.resolved),
            "closed": self._node(self.closed, is_terminal=True),
            "duplicated": self._node(self.duplicated, is_terminal=True),
            "rejected": self._node(self.rejected, is_terminal=True),
        }

        self._transition(
            "pm_confirm_valid",
            "PM Confirm Valid",
            "pending_pm_review",
            "new",
            requires_approval=True,
            approval_config={"approvals": [{"approval_type": ApprovalTypes.SELF}]},
            reject_behavior=TransitionRejectBehavior.MOVE_TO_STATUS,
            reject_to_status="rejected",
            metadata={
                "allowed_reject_status_keys": ["duplicated", "rejected"],
                "internal_visibility_gate": True,
            },
        )
        self._transition(
            "start_progress",
            "Start Progress",
            "new",
            "in_progress",
            metadata={"required_metadata_keys": ["assignee_id"]},
        )
        self._transition(
            "put_on_hold",
            "Put On Hold",
            "in_progress",
            "on_hold",
            requires_approval=True,
            approval_config={"approvals": [{"approval_type": ApprovalTypes.SELF}]},
            metadata={"required_metadata_keys": ["customer_requirement"]},
        )
        self._transition(
            "resume_from_hold",
            "Resume From Hold",
            "on_hold",
            "in_progress",
            requires_approval=True,
            approval_config={"approvals": [{"approval_type": ApprovalTypes.SELF}]},
            metadata={"required_metadata_keys": ["customer_response"]},
        )
        self._transition(
            "resolve",
            "Resolve",
            "in_progress",
            "resolved",
            requires_approval=True,
            approval_config={"approvals": [{"approval_type": ApprovalTypes.SELF}]},
            reject_behavior=TransitionRejectBehavior.MOVE_TO_STATUS,
            reject_to_status="in_progress",
        )
        self._transition("reopen", "Reopen", "resolved", "in_progress")
        self._transition(
            "close",
            "Close",
            "resolved",
            "closed",
            requires_approval=True,
            approval_config={"approvals": [{"approval_type": ApprovalTypes.SELF}]},
            reject_behavior=TransitionRejectBehavior.MOVE_TO_STATUS,
            reject_to_status="in_progress",
        )

        self.workflow.update_active_status()

    def _status(self, key, name, category):
        return Status.objects.create(key=key, name_en=name, category=category)

    def _node(self, status, is_initial=False, is_terminal=False):
        return WorkflowStatusNode.objects.create(
            workflow=self.workflow,
            status=status,
            is_initial=is_initial,
            is_terminal=is_terminal,
        )

    def _transition(
        self,
        key,
        name,
        from_key,
        to_key,
        requires_approval=False,
        approval_config=None,
        reject_behavior=TransitionRejectBehavior.STAY_CURRENT,
        reject_to_status=None,
        metadata=None,
    ):
        return StatusTransition.objects.create(
            workflow=self.workflow,
            key=key,
            name_en=name,
            from_status=self.nodes[from_key],
            to_status=self.nodes[to_key],
            requires_approval=requires_approval,
            approval_config=approval_config or {},
            reject_behavior=reject_behavior,
            reject_to_status=(
                self.nodes[reject_to_status] if reject_to_status else None
            ),
            metadata=metadata or {},
        )

    def _ticket(self, name="Ticket"):
        ticket = WorkflowTestModel.objects.create(name=name)
        attach_workflow_to_object(
            ticket,
            self.workflow,
            user=self.pm,
            auto_start=True,
            disable_clone=True,
        )
        return ticket

    def test_ticket_is_not_new_until_pm_approval(self):
        ticket = self._ticket("PM validation")

        self.assertEqual(get_current_status(ticket), self.pending_pm_review)

        perform_transition(ticket, "pm_confirm_valid", user=self.pm)
        attachment = get_workflow_attachment(ticket)
        self.assertEqual(attachment.pending_transition.key, "pm_confirm_valid")
        self.assertEqual(get_current_status(ticket), self.pending_pm_review)

        approve_pending_transition(ticket, user=self.pm, reason="Valid customer issue")

        self.assertEqual(get_current_status(ticket), self.new)

    def test_pm_rejection_can_mark_ticket_duplicated_with_evidence(self):
        ticket = self._ticket("Duplicate triage")
        perform_transition(ticket, "pm_confirm_valid", user=self.pm)

        with self.assertRaisesMessage(
            ValueError, "Transition rejection requires a reason or evidence"
        ):
            reject_pending_transition(ticket, user=self.pm)

        reject_pending_transition(
            ticket,
            user=self.pm,
            reason="Already reported in ticket #100",
            metadata={"evidence": "duplicate-ticket-100"},
            reject_to_status=self.duplicated,
        )

        attachment = get_workflow_attachment(ticket)
        self.assertEqual(get_current_status(ticket), self.duplicated)
        self.assertEqual(attachment.pending_transition, None)

    def test_new_to_in_progress_requires_assignment(self):
        ticket = self._ticket("Assignment")
        perform_transition(ticket, "pm_confirm_valid", user=self.pm)
        approve_pending_transition(ticket, user=self.pm, reason="Valid")

        with self.assertRaisesMessage(ValueError, "assignee_id"):
            perform_transition(ticket, "start_progress", user=self.developer)

        perform_transition(
            ticket,
            "start_progress",
            user=self.developer,
            metadata={"assignee_id": self.developer.id},
        )

        self.assertEqual(get_current_status(ticket), self.in_progress)

    def test_hold_and_resume_require_customer_context(self):
        ticket = self._ticket("Hold and resume")
        perform_transition(ticket, "pm_confirm_valid", user=self.pm)
        approve_pending_transition(ticket, user=self.pm, reason="Valid")
        perform_transition(
            ticket,
            "start_progress",
            user=self.developer,
            metadata={"assignee_id": self.developer.id},
        )

        with self.assertRaisesMessage(ValueError, "customer_requirement"):
            perform_transition(ticket, "put_on_hold", user=self.developer)

        perform_transition(
            ticket,
            "put_on_hold",
            user=self.developer,
            metadata={
                "customer_requirement": "Need production error screenshot or logs"
            },
        )
        self.assertEqual(get_current_status(ticket), self.in_progress)
        self.assertEqual(
            get_workflow_attachment(ticket).pending_transition.key, "put_on_hold"
        )
        approve_pending_transition(
            ticket, user=self.pm, reason="Customer requirement is clear"
        )
        self.assertEqual(get_current_status(ticket), self.on_hold)

        with self.assertRaisesMessage(ValueError, "customer_response"):
            perform_transition(ticket, "resume_from_hold", user=self.developer)

        perform_transition(
            ticket,
            "resume_from_hold",
            user=self.developer,
            metadata={"customer_response": "Customer attached requested logs"},
        )
        self.assertEqual(get_current_status(ticket), self.on_hold)
        self.assertEqual(
            get_workflow_attachment(ticket).pending_transition.key, "resume_from_hold"
        )
        approve_pending_transition(
            ticket, user=self.pm, reason="Customer response is sufficient"
        )
        self.assertEqual(get_current_status(ticket), self.in_progress)

    def test_resolve_close_and_reopen_approval_logic(self):
        ticket = self._ticket("Resolve close reopen")
        perform_transition(ticket, "pm_confirm_valid", user=self.pm)
        approve_pending_transition(ticket, user=self.pm, reason="Valid")
        perform_transition(
            ticket,
            "start_progress",
            user=self.developer,
            metadata={"assignee_id": self.developer.id},
        )

        perform_transition(ticket, "resolve", user=self.developer)
        self.assertEqual(
            get_workflow_attachment(ticket).pending_transition.key, "resolve"
        )
        approve_pending_transition(ticket, user=self.pm, reason="QA approved")
        self.assertEqual(get_current_status(ticket), self.resolved)

        perform_transition(ticket, "reopen", user=self.pm, reason="Issue reproduced")
        self.assertEqual(get_current_status(ticket), self.in_progress)

        perform_transition(ticket, "resolve", user=self.developer)
        approve_pending_transition(ticket, user=self.pm, reason="QA approved again")
        perform_transition(ticket, "close", user=self.pm)

        reject_pending_transition(
            ticket,
            user=self.pm,
            reason="Customer rejected closure",
            metadata={"evidence": "customer-email-thread"},
        )
        self.assertEqual(get_current_status(ticket), self.in_progress)

        perform_transition(ticket, "resolve", user=self.developer)
        approve_pending_transition(ticket, user=self.pm, reason="QA approved final fix")
        perform_transition(ticket, "close", user=self.pm)
        approve_pending_transition(ticket, user=self.pm, reason="Customer accepted")

        attachment = get_workflow_attachment(ticket)
        self.assertEqual(get_current_status(ticket), self.closed)
        self.assertEqual(attachment.status, WorkflowAttachmentStatus.COMPLETED)
