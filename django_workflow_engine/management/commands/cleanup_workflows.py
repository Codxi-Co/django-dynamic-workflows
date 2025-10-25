"""
Django management command to clean up cloned workflow actions from completed workflows.

IMPORTANT: WorkflowAttachment records are KEPT for history/audit purposes.
Only cloned WorkflowAction records from completed workflows are deleted.

Usage:
    python manage.py cleanup_workflows --days=30
    python manage.py cleanup_workflows --dry-run
    python manage.py cleanup_workflows --stats
"""

from django.core.management.base import BaseCommand, CommandError

from django_workflow_engine.cleanup import (
    cleanup_completed_workflow_actions,
    cleanup_orphaned_workflow_actions,
    get_cleanup_statistics,
)


class Command(BaseCommand):
    help = "Clean up cloned workflow actions from completed workflows (keeps attachments for history)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Only clean actions from workflows completed more than X days ago (default: clean all)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )
        parser.add_argument(
            "--stats",
            action="store_true",
            help="Show cleanup statistics without performing cleanup",
        )
        parser.add_argument(
            "--include-orphaned-actions",
            action="store_true",
            help="Also clean up orphaned workflow actions",
        )
        parser.add_argument(
            "--status",
            nargs="+",
            default=["completed", "rejected"],
            help="Workflow status filter (default: completed rejected)",
        )

    def handle(self, *args, **options):
        # Show statistics if requested
        if options["stats"]:
            self.show_statistics()
            return

        days = options["days"]
        dry_run = options["dry_run"]
        status_filter = options["status"]
        include_orphaned = options["include_orphaned_actions"]

        # Show what we're about to do
        if dry_run:
            self.stdout.write(
                self.style.WARNING("=== DRY RUN MODE - No data will be deleted ===\n")
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "=== CLEANUP MODE - Data will be permanently deleted ===\n"
                )
            )

        # Cleanup cloned workflow actions
        self.stdout.write(f"Cleaning up cloned workflow actions...")
        self.stdout.write(f"  Status filter: {', '.join(status_filter)}")
        if days is not None:
            self.stdout.write(f"  Age filter: Older than {days} days")
        else:
            self.stdout.write(f"  Age filter: All (no age limit)")

        self.stdout.write(
            self.style.WARNING(
                "  NOTE: WorkflowAttachment records are KEPT for history"
            )
        )

        result = cleanup_completed_workflow_actions(
            older_than_days=days, status_filter=status_filter, dry_run=dry_run
        )

        if result["actions_deleted"] > 0:
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f"\nWould delete {result['actions_deleted']} cloned workflow actions"
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        f"From {result['workflows_processed']} completed workflows"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n✓ Deleted {result['actions_deleted']} cloned workflow actions"
                    )
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ From {result['workflows_processed']} completed workflows"
                    )
                )
        else:
            self.stdout.write(
                self.style.SUCCESS("\n✓ No cloned workflow actions to clean up")
            )

        # Cleanup orphaned actions if requested
        if include_orphaned:
            self.stdout.write(f"\nCleaning up orphaned workflow actions...")

            result = cleanup_orphaned_workflow_actions(dry_run=dry_run)

            if result["actions_deleted"] > 0:
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Would delete {result['actions_deleted']} orphaned actions"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Deleted {result['actions_deleted']} orphaned actions"
                        )
                    )
            else:
                self.stdout.write(
                    self.style.SUCCESS("✓ No orphaned actions to clean up")
                )

        # Final message
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    "\n✓ Dry run complete. Run without --dry-run to actually delete data."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("\n✓ Cleanup complete!"))

    def show_statistics(self):
        """Display cleanup statistics."""
        self.stdout.write(self.style.SUCCESS("=== Workflow Cleanup Statistics ===\n"))

        stats = get_cleanup_statistics()

        # Attachments (kept for history)
        self.stdout.write(
            self.style.HTTP_INFO("Workflow Attachments (KEPT for history/audit):")
        )
        self.stdout.write(f"  Total: {stats['total_attachments']}")
        self.stdout.write(
            f"  Completed: {stats['completed_attachments']} "
            f"({self._percent(stats['completed_attachments'], stats['total_attachments'])})"
        )
        self.stdout.write(
            f"  Rejected: {stats['rejected_attachments']} "
            f"({self._percent(stats['rejected_attachments'], stats['total_attachments'])})"
        )
        self.stdout.write(
            f"  In Progress: {stats['in_progress_attachments']} "
            f"({self._percent(stats['in_progress_attachments'], stats['total_attachments'])})"
        )

        # Cloned workflows
        self.stdout.write(self.style.HTTP_INFO("\nCloned Workflows:"))
        self.stdout.write(
            f"  Total cloned workflows: {stats['cloned_workflows']['total']}"
        )
        self.stdout.write(
            f"  With completed attachments: {stats['cloned_workflows']['with_completed_attachments']}"
        )

        # Cloned actions (cleanable)
        self.stdout.write(
            self.style.HTTP_INFO("\nCloned Workflow Actions (Cleanable):")
        )
        self.stdout.write(f"  Total cloned actions: {stats['cloned_actions']['total']}")
        self.stdout.write(
            self.style.WARNING(
                f"  From completed workflows: {stats['cloned_actions']['from_completed_workflows']}"
            )
        )

        # Age-based cleanable actions
        self.stdout.write(self.style.HTTP_INFO("\nCleanable Actions by Age:"))
        self.stdout.write(
            f"  Older than 30 days: {stats['cleanable_by_age']['older_than_30_days']}"
        )
        self.stdout.write(
            f"  Older than 90 days: {stats['cleanable_by_age']['older_than_90_days']}"
        )
        self.stdout.write(
            f"  Older than 365 days: {stats['cleanable_by_age']['older_than_365_days']}"
        )

        # All actions
        self.stdout.write(self.style.HTTP_INFO("\nAll Workflow Actions:"))
        self.stdout.write(f"  Total: {stats['total_actions']}")
        if stats["orphaned_actions"] > 0:
            self.stdout.write(
                self.style.WARNING(f"  Orphaned: {stats['orphaned_actions']}")
            )
        else:
            self.stdout.write(f"  Orphaned: {stats['orphaned_actions']}")

        # Recommendations
        self.stdout.write(self.style.SUCCESS("\nRecommendations:"))
        if stats["cloned_actions"]["from_completed_workflows"] > 100:
            self.stdout.write(
                f"  → Consider running: python manage.py cleanup_workflows --days=30"
            )
        if stats["orphaned_actions"] > 0:
            self.stdout.write(
                f"  → Clean up orphaned actions: python manage.py cleanup_workflows --include-orphaned-actions"
            )
        if (
            stats["cloned_actions"]["from_completed_workflows"] == 0
            and stats["orphaned_actions"] == 0
        ):
            self.stdout.write("  ✓ No cloned actions to clean up!")

    def _percent(self, part, total):
        """Calculate percentage."""
        if total == 0:
            return "0%"
        return f"{(part / total * 100):.1f}%"
