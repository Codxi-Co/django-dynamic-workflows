"""
Signal handlers for django_workflow_engine.

Handles automatic cleanup of cloned WorkflowAction records when workflows complete.
WorkflowAttachment records are ALWAYS kept for history/audit purposes.
"""

import logging

from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from .choices import WorkflowAttachmentStatus
from .models import WorkflowAction, WorkflowAttachment

logger = logging.getLogger(__name__)


@receiver(post_save, sender=WorkflowAttachment)
def auto_cleanup_completed_workflow_actions(sender, instance, created, **kwargs):
    """
    Automatically clean up cloned WorkflowAction records when a workflow completes.

    This signal triggers when a WorkflowAttachment is saved with COMPLETED or REJECTED status.
    It deletes the cloned WorkflowAction records associated with that workflow while
    preserving the WorkflowAttachment for history/audit purposes.

    Args:
        sender: The WorkflowAttachment model class
        instance: The WorkflowAttachment instance that was saved
        created: Boolean indicating if this is a new instance
        **kwargs: Additional keyword arguments
    """
    # Only clean up when status is COMPLETED or REJECTED
    if instance.status not in [
        WorkflowAttachmentStatus.COMPLETED,
        WorkflowAttachmentStatus.REJECTED,
    ]:
        return

    # Only clean up cloned workflows (is_hidden=True or cloned_from is not None)
    workflow = instance.workflow
    if not workflow or (not workflow.is_hidden and workflow.cloned_from_id is None):
        return

    # Find all actions belonging to this cloned workflow
    actions_to_delete = WorkflowAction.objects.filter(
        Q(workflow_id=workflow.id)
        | Q(pipeline__workflow_id=workflow.id)
        | Q(stage__pipeline__workflow_id=workflow.id)
    )

    actions_count = actions_to_delete.count()

    if actions_count > 0:
        try:
            with transaction.atomic():
                deleted_count, deleted_objects = actions_to_delete.delete()

                logger.info(
                    f"Auto-cleanup: Deleted {deleted_objects.get('django_workflow_engine.WorkflowAction', 0)} "
                    f"cloned actions from workflow {workflow.id} (status: {instance.status})"
                )
        except Exception as e:
            logger.error(
                f"Error during auto-cleanup of workflow {workflow.id}: {e}",
                exc_info=True,
            )
