"""
Cleanup utilities for workflow data to reduce database usage.

Cleans up cloned WorkflowAction records from completed workflows while
preserving WorkflowAttachment records for history/audit purposes.
"""

import logging
from datetime import timedelta
from typing import Dict, Optional

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from .choices import WorkflowAttachmentStatus
from .models import WorkFlow, WorkflowAction, WorkflowAttachment

logger = logging.getLogger(__name__)


def cleanup_completed_workflow_actions(
    older_than_days: Optional[int] = None,
    status_filter: Optional[list] = None,
    dry_run: bool = False,
) -> Dict[str, int]:
    """
    Clean up cloned WorkflowAction records from completed workflows.

    This removes WorkflowAction records that belong to CLONED workflows whose
    attachments have reached a final state (completed or rejected).

    IMPORTANT:
    - WorkflowAttachment records are KEPT for history/audit purposes
    - Only cloned WorkflowAction records are deleted
    - Original template WorkflowAction records are preserved

    Args:
        older_than_days: Only clean actions from workflows completed more than X days ago.
                        If None, cleans all completed workflows immediately.
        status_filter: List of statuses to check. Defaults to ['completed', 'rejected'].
        dry_run: If True, count records but don't actually delete them.

    Returns:
        Dict with cleanup statistics:
        {
            'actions_deleted': int,  # Cloned WorkflowAction records deleted
            'workflows_processed': int,  # Number of cloned workflows processed
            'dry_run': bool
        }

    Example:
        # Clean up actions from workflows completed more than 30 days ago
        result = cleanup_completed_workflow_actions(older_than_days=30)

        # Dry run to see what would be deleted
        result = cleanup_completed_workflow_actions(
            older_than_days=7,
            dry_run=True
        )
        print(f"Would delete {result['actions_deleted']} cloned actions")
    """
    if status_filter is None:
        status_filter = [
            WorkflowAttachmentStatus.COMPLETED,
            WorkflowAttachmentStatus.REJECTED,
        ]

    # Build query for completed attachments
    query = Q(status__in=status_filter)

    if older_than_days is not None:
        cutoff_date = timezone.now() - timedelta(days=older_than_days)
        query &= Q(modified_at__lt=cutoff_date)

    # Get completed attachments
    completed_attachments = WorkflowAttachment.objects.filter(query).select_related(
        "workflow"
    )

    # Find cloned workflows (is_hidden=True or cloned_from is not None)
    cloned_workflow_ids = set()
    for attachment in completed_attachments:
        workflow = attachment.workflow
        if workflow and (workflow.is_hidden or workflow.cloned_from_id is not None):
            cloned_workflow_ids.add(workflow.id)

    # Get actions belonging to these cloned workflows
    actions_to_delete = WorkflowAction.objects.filter(
        Q(workflow_id__in=cloned_workflow_ids)
        | Q(pipeline__workflow_id__in=cloned_workflow_ids)
        | Q(stage__pipeline__workflow_id__in=cloned_workflow_ids)
    )

    actions_count = actions_to_delete.count()
    workflows_count = len(cloned_workflow_ids)

    logger.info(
        f"{'[DRY RUN] Would delete' if dry_run else 'Deleting'} "
        f"{actions_count} cloned actions from {workflows_count} completed workflows"
    )

    if dry_run:
        return {
            "actions_deleted": actions_count,
            "workflows_processed": workflows_count,
            "dry_run": True,
        }

    # Perform deletion in transaction
    with transaction.atomic():
        deleted_count, deleted_objects = actions_to_delete.delete()

        logger.info(
            f"Successfully deleted {deleted_count} cloned workflow actions "
            f"from {workflows_count} workflows"
        )

        return {
            "actions_deleted": deleted_objects.get(
                "django_workflow_engine.WorkflowAction", 0
            ),
            "workflows_processed": workflows_count,
            "dry_run": False,
        }


def cleanup_orphaned_workflow_actions(dry_run: bool = False) -> Dict[str, int]:
    """
    Clean up orphaned workflow actions with no associated workflow/pipeline/stage.

    This should rarely be needed, but can occur if workflow templates are deleted
    improperly or if there's a data integrity issue.

    Args:
        dry_run: If True, count records but don't actually delete them.

    Returns:
        Dict with cleanup statistics:
        {
            'actions_deleted': int,
            'dry_run': bool
        }

    Example:
        # Check for orphaned actions
        result = cleanup_orphaned_workflow_actions(dry_run=True)
        if result['actions_deleted'] > 0:
            print(f"Found {result['actions_deleted']} orphaned actions")

            # Clean them up
            cleanup_orphaned_workflow_actions()
    """
    # Find actions with no workflow, pipeline, or stage
    orphaned_actions = WorkflowAction.objects.filter(
        workflow__isnull=True, pipeline__isnull=True, stage__isnull=True
    )

    count = orphaned_actions.count()

    logger.info(
        f"{'[DRY RUN] Would delete' if dry_run else 'Deleting'} {count} orphaned workflow actions"
    )

    if dry_run:
        return {"actions_deleted": count, "dry_run": True}

    with transaction.atomic():
        deleted_count, _ = orphaned_actions.delete()

        logger.info(f"Successfully deleted {deleted_count} orphaned workflow actions")

        return {"actions_deleted": deleted_count, "dry_run": False}


def get_cleanup_statistics() -> Dict:
    """
    Get statistics about workflow data that could be cleaned up.

    Returns:
        Dict with statistics:
        {
            'total_attachments': int,
            'completed_attachments': int,
            'rejected_attachments': int,
            'in_progress_attachments': int,
            'cloned_workflows': {
                'total': int,
                'with_completed_attachments': int,
            },
            'cloned_actions': {
                'total': int,
                'from_completed_workflows': int,
            },
            'cleanable_by_age': {
                'older_than_30_days': int,  # Actions count
                'older_than_90_days': int,
                'older_than_365_days': int
            },
            'total_actions': int,
            'orphaned_actions': int
        }

    Example:
        stats = get_cleanup_statistics()
        print(f"Cloned actions to clean: {stats['cloned_actions']['from_completed_workflows']}")
    """
    now = timezone.now()

    # Attachment statistics (kept for history - NOT deleted)
    total_attachments = WorkflowAttachment.objects.count()
    completed_attachments = WorkflowAttachment.objects.filter(
        status=WorkflowAttachmentStatus.COMPLETED
    ).count()
    rejected_attachments = WorkflowAttachment.objects.filter(
        status=WorkflowAttachmentStatus.REJECTED
    ).count()
    in_progress_attachments = WorkflowAttachment.objects.filter(
        status=WorkflowAttachmentStatus.IN_PROGRESS
    ).count()

    # Cloned workflow statistics
    cloned_workflows_total = WorkFlow.objects.filter(
        Q(is_hidden=True) | Q(cloned_from__isnull=False)
    ).count()

    # Cloned workflows with completed attachments
    final_statuses = [
        WorkflowAttachmentStatus.COMPLETED,
        WorkflowAttachmentStatus.REJECTED,
    ]

    completed_cloned_workflow_ids = set(
        WorkflowAttachment.objects.filter(status__in=final_statuses)
        .filter(Q(workflow__is_hidden=True) | Q(workflow__cloned_from__isnull=False))
        .values_list("workflow_id", flat=True)
        .distinct()
    )

    # Actions from cloned workflows
    cloned_actions_total = WorkflowAction.objects.filter(
        Q(workflow__is_hidden=True)
        | Q(workflow__cloned_from__isnull=False)
        | Q(pipeline__workflow__is_hidden=True)
        | Q(pipeline__workflow__cloned_from__isnull=False)
        | Q(stage__pipeline__workflow__is_hidden=True)
        | Q(stage__pipeline__workflow__cloned_from__isnull=False)
    ).count()

    # Actions from completed cloned workflows (cleanable)
    cloned_actions_from_completed = WorkflowAction.objects.filter(
        Q(workflow_id__in=completed_cloned_workflow_ids)
        | Q(pipeline__workflow_id__in=completed_cloned_workflow_ids)
        | Q(stage__pipeline__workflow_id__in=completed_cloned_workflow_ids)
    ).count()

    # Age-based statistics for cleanable actions
    def get_cleanable_actions_by_age(days):
        cutoff = now - timedelta(days=days)
        attachment_ids = set(
            WorkflowAttachment.objects.filter(
                status__in=final_statuses, modified_at__lt=cutoff
            )
            .filter(
                Q(workflow__is_hidden=True) | Q(workflow__cloned_from__isnull=False)
            )
            .values_list("workflow_id", flat=True)
            .distinct()
        )
        return WorkflowAction.objects.filter(
            Q(workflow_id__in=attachment_ids)
            | Q(pipeline__workflow_id__in=attachment_ids)
            | Q(stage__pipeline__workflow_id__in=attachment_ids)
        ).count()

    older_than_30 = get_cleanable_actions_by_age(30)
    older_than_90 = get_cleanable_actions_by_age(90)
    older_than_365 = get_cleanable_actions_by_age(365)

    # All actions
    total_actions = WorkflowAction.objects.count()
    orphaned_actions = WorkflowAction.objects.filter(
        workflow__isnull=True, pipeline__isnull=True, stage__isnull=True
    ).count()

    return {
        "total_attachments": total_attachments,
        "completed_attachments": completed_attachments,
        "rejected_attachments": rejected_attachments,
        "in_progress_attachments": in_progress_attachments,
        "cloned_workflows": {
            "total": cloned_workflows_total,
            "with_completed_attachments": len(completed_cloned_workflow_ids),
        },
        "cloned_actions": {
            "total": cloned_actions_total,
            "from_completed_workflows": cloned_actions_from_completed,
        },
        "cleanable_by_age": {
            "older_than_30_days": older_than_30,
            "older_than_90_days": older_than_90,
            "older_than_365_days": older_than_365,
        },
        "total_actions": total_actions,
        "orphaned_actions": orphaned_actions,
    }
