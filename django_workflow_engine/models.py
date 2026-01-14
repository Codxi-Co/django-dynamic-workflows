"""Models for django_workflow_engine Django app.

Workflow management models (WorkFlow, Pipeline, Stage) for creating and managing
dynamic multistep workflows. Integrates with django-approval-workflow package
for approval flow functionality.
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from approval_workflow.choices import ApprovalType

from .choices import (
    ActionType,
    ApprovalTypes,
    WorkflowAttachmentStatus,
    WorkflowStatus,
    WorkflowStrategy,
)
from .constants import (
    ERROR_MESSAGES,
    MAX_METADATA_SIZE,
    MAX_PIPELINE_INFO_SIZE,
    MAX_STAGE_INFO_SIZE,
    MAX_WORKFLOW_INFO_SIZE,
    validate_json_size,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class BaseCompanyModel(models.Model):
    """Base model for company-scoped models."""

    # Optional company field - uses a User model for company association
    company = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_company",
        help_text=_("Company/Organization user that owns this workflow"),
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    modified_at = models.DateTimeField(auto_now=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_modified",
    )

    class Meta:
        abstract = True


class CompanyBaseWithNamedModel(BaseCompanyModel):
    """Base model with multi-language name support."""

    name_en = models.CharField(max_length=150, help_text=_("English name"))
    name_ar = models.CharField(max_length=150, help_text=_("Arabic name"))

    class Meta:
        abstract = True

    def __str__(self):
        return self.name_en or self.name_ar or f"ID: {self.pk}"


class CompanyBaseWithNamedModelWithClone(CompanyBaseWithNamedModel):
    """Base model with cloning capability."""

    cloned_from = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cloned_%(class)s",
        help_text=_("The original object this was cloned from"),
        verbose_name=_("Cloned From"),
    )

    class Meta:
        abstract = True

    def clone(self, modified_keys=None, overrides=None):
        """Clone this model instance with optional modifications."""
        if modified_keys is None:
            modified_keys = []
        if overrides is None:
            overrides = {}

        # Create a new instance
        new_instance = self.__class__()

        # Copy all field values
        for field in self._meta.fields:
            if not field.primary_key and field.name not in [
                "created_at",
                "modified_at",
                "cloned_from",  # Skip cloned_from during copying
            ]:
                value = getattr(self, field.name)
                if field.name in modified_keys:
                    if field.name in ["name_en", "name_ar"] and value:
                        value = f"{value} (Copy)"
                setattr(new_instance, field.name, value)

        # Set cloned_from to point to the original instance
        new_instance.cloned_from = self

        # Apply overrides
        for key, value in overrides.items():
            setattr(new_instance, key, value)

        new_instance.save()
        return new_instance


class WorkFlow(CompanyBaseWithNamedModelWithClone):
    """
    Represents a complete workflow with multiple pipelines.
    Each workflow can contain multiple pipelines for different departments.
    """

    status = models.CharField(
        max_length=20,
        choices=WorkflowStatus.choices,
        default=WorkflowStatus.ACTIVE,
        help_text=_("Status of the workflow"),
        verbose_name=_("Status"),
    )
    description = models.TextField(
        blank=True, help_text=_("Workflow description"), verbose_name=_("Description")
    )
    is_active = models.BooleanField(
        default=False,
        help_text=_("Whether this workflow is active and can be used"),
        verbose_name=_("Is Active"),
    )
    is_hidden = models.BooleanField(
        default=False,
        help_text=_("Whether this workflow is hidden (true for cloned workflows)"),
        verbose_name=_("Is Hidden"),
    )
    strategy = models.IntegerField(
        choices=WorkflowStrategy.choices,
        default=WorkflowStrategy.WORKFLOW_PIPELINE_STAGE,
        help_text=_(
            "Workflow approval strategy: 1=Workflow only, 2=Workflow→Pipeline, 3=Workflow→Pipeline→Stage"
        ),
        verbose_name=_("Workflow Strategy"),
    )
    workflow_info = models.JSONField(
        default=dict,
        null=True,
        blank=True,
        help_text=_(
            "Workflow configuration including approvals (for strategy 1 workflows)"
        ),
    )

    class Meta:
        # Remove company-based unique constraints since company is now optional
        ordering = ("-id",)
        verbose_name = _("Workflow")
        verbose_name_plural = _("Workflows")

    def validate_completeness(self):
        """Validate if the workflow is complete and can be activated (strategy-aware).

        Uses select_related/prefetch_related for optimal performance.

        Strategy 1: Full hierarchy required (workflow → pipeline → stage) with stage-level approvals
        Strategy 2: Two-level only (workflow → pipeline) with pipeline-level approvals, NO stages allowed
        Strategy 3: Single-level only (workflow) with workflow-level approvals, NO pipelines/stages allowed
        """
        # Strategy 1 (Workflow→Pipeline→Stage): Check stage_info for approvals (default/full hierarchy)
        if self.strategy == WorkflowStrategy.WORKFLOW_PIPELINE_STAGE:
            pipelines = self.pipelines.prefetch_related("stages").all()

            if not pipelines:
                return False, "Strategy 1 workflow must have at least one pipeline"

            for pipeline in pipelines:
                stages = list(pipeline.stages.all())  # Already prefetched
                if not stages:
                    return (
                        False,
                        f"Strategy 1 pipeline '{pipeline.name_en}' must have at least one stage",
                    )

                for stage in stages:
                    if not stage.is_complete():
                        return (
                            False,
                            f"Stage '{stage.name_en}' in pipeline '{pipeline.name_en}' is not properly configured",
                        )

            return True, "Strategy 1 workflow is complete and valid"

        # Strategy 2 (Workflow→Pipeline): Check pipeline_info for approvals, NO stages allowed
        if self.strategy == WorkflowStrategy.WORKFLOW_PIPELINE:
            pipelines = self.pipelines.prefetch_related("stages").all()

            if not pipelines:
                return False, "Strategy 2 workflow must have at least one pipeline"

            for pipeline in pipelines:
                # Check pipeline has approvals in pipeline_info
                pipeline_info = pipeline.pipeline_info or {}
                approvals = pipeline_info.get("approvals", [])

                if not approvals:
                    return (
                        False,
                        f"Strategy 2 pipeline '{pipeline.name_en}' must have approvals in pipeline_info",
                    )

                # IMPORTANT: Strategy 2 should NOT have any stages
                stages = list(pipeline.stages.all())
                if stages:
                    return (
                        False,
                        f"Strategy 2 pipeline '{pipeline.name_en}' cannot have stages (approvals are at pipeline level)",
                    )

            return True, "Strategy 2 workflow is complete and valid"

        # Strategy 3 (Workflow Only): Check workflow_info for approvals, NO pipelines or stages allowed
        if self.strategy == WorkflowStrategy.WORKFLOW_ONLY:
            workflow_info = self.workflow_info or {}
            approvals = workflow_info.get("approvals", [])

            if not approvals:
                return False, "Strategy 3 workflow must have approvals in workflow_info"

            # IMPORTANT: Strategy 3 should NOT have any pipelines or stages
            pipelines = self.pipelines.all()
            if pipelines.exists():
                return (
                    False,
                    "Strategy 3 workflow cannot have pipelines (approvals are at workflow level only)",
                )

            return True, "Strategy 3 workflow is complete and valid"

        return False, f"Unknown strategy: {self.strategy}"

    def update_active_status(self):
        """Update is_active based on workflow completeness."""
        is_valid, message = self.validate_completeness()
        old_status = self.is_active
        self.is_active = is_valid and self.status == WorkflowStatus.ACTIVE

        if old_status != self.is_active:
            self.save(update_fields=["is_active"])
            logger.info(
                f"Workflow {self.id} active status changed from {old_status} to {self.is_active}: {message}"
            )

        return self.is_active, message

    @property
    def completion_status(self):
        """Get workflow completion status."""
        is_valid, message = self.validate_completeness()
        return {
            "is_complete": is_valid,
            "message": message,
            "is_active": self.is_active,
            "can_be_activated": is_valid and self.status == WorkflowStatus.ACTIVE,
        }

    def save(self, *args, **kwargs):
        """Override save to auto-create default workflow actions for new workflows."""
        from django.conf import settings

        # Validate JSON field sizes before saving
        self._validate_json_fields()

        is_new = self.pk is None
        super().save(*args, **kwargs)

        # Auto-create default actions for new workflows if enabled in settings
        if is_new and getattr(settings, "WORKFLOW_AUTO_CREATE_ACTIONS", True):
            try:
                from .action_management import create_default_workflow_actions

                actions = create_default_workflow_actions(self)
                logger.info(
                    f"Auto-created {len(actions)} default workflow actions for workflow {self.id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to auto-create default workflow actions for workflow {self.id}: {e}",
                    exc_info=True,
                )

    def _validate_json_fields(self):
        """Validate JSON field sizes to prevent database bloat."""
        # Validate workflow_info
        if self.workflow_info:
            validate_json_size(
                self.workflow_info,
                MAX_WORKFLOW_INFO_SIZE,
                "workflow_info",
                raise_error=True,
            )

    def clone(self, modified_keys=None, overrides=None):
        logger.info(f"Starting clone process for WorkFlow: {self.id} ({self.name_en})")

        with transaction.atomic():
            # Clone workflow first
            cloned_workflow = super().clone(
                modified_keys=["name_en", "name_ar"], overrides={"is_hidden": True}
            )
            logger.info(f"Cloned WorkFlow {self.id} -> {cloned_workflow.id}")

            # Prefetch all related data in one query
            pipelines = list(self.pipelines.prefetch_related("stages").all())

            if not pipelines:
                logger.info("No pipelines to clone")
                return cloned_workflow

            # Prepare all pipelines for bulk creation
            pipelines_to_create = []
            pipeline_mapping = {}  # Maps old pipeline to new pipeline data

            for pipeline in pipelines:
                # Create a new pipeline instance (not saved yet)
                new_pipeline = Pipeline(
                    workflow=cloned_workflow,
                    company=pipeline.company,
                    name_en=f"{pipeline.name_en} (Copy)" if pipeline.name_en else None,
                    name_ar=f"{pipeline.name_ar} (Copy)" if pipeline.name_ar else None,
                    department_content_type=pipeline.department_content_type,
                    department_id=pipeline.department_id,
                    order=pipeline.order,
                    is_hidden=True,
                    pipeline_info=(
                        pipeline.pipeline_info.copy() if pipeline.pipeline_info else {}
                    ),
                    created_by=pipeline.created_by,
                    modified_by=pipeline.modified_by,
                    cloned_from=pipeline,
                )
                pipelines_to_create.append(new_pipeline)
                # Store reference for stage cloning
                pipeline_mapping[pipeline.id] = {
                    "pipeline_obj": new_pipeline,
                    "stages": list(pipeline.stages.all()),
                }

            # Bulk create all pipelines in one query
            created_pipelines = Pipeline.objects.bulk_create(pipelines_to_create)
            logger.info(f"Bulk created {len(created_pipelines)} pipelines")

            # Update pipeline_mapping with created pipelines (with IDs)
            for idx, pipeline_id in enumerate(pipeline_mapping.keys()):
                pipeline_mapping[pipeline_id]["created_pipeline"] = created_pipelines[
                    idx
                ]

            # Prepare all stages for bulk creation
            stages_to_create = []
            for pipeline_id, data in pipeline_mapping.items():
                created_pipeline = data["created_pipeline"]
                stages = data["stages"]

                for stage in stages:
                    new_stage = Stage(
                        pipeline=created_pipeline,
                        company=stage.company,
                        name_en=f"{stage.name_en} (Copy)" if stage.name_en else None,
                        name_ar=f"{stage.name_ar} (Copy)" if stage.name_ar else None,
                        form_info=stage.form_info.copy() if stage.form_info else [],
                        stage_info=stage.stage_info.copy() if stage.stage_info else {},
                        is_active=stage.is_active,
                        order=stage.order,
                        is_hidden=True,
                        created_by=stage.created_by,
                        modified_by=stage.modified_by,
                        cloned_from=stage,
                    )
                    stages_to_create.append(new_stage)

            # Bulk create all stages in one query
            if stages_to_create:
                created_stages = Stage.objects.bulk_create(stages_to_create)
                logger.info(f"Bulk created {len(created_stages)} stages")

            # Clone workflow actions
            try:
                from .action_management import clone_workflow_actions

                action_counts = clone_workflow_actions(
                    source_workflow=self,
                    target_workflow=cloned_workflow,
                    pipeline_mapping=pipeline_mapping,
                )
                logger.info(
                    f"Cloned workflow actions - "
                    f"Workflow: {action_counts['workflow']}, "
                    f"Pipeline: {action_counts['pipeline']}, "
                    f"Stage: {action_counts['stage']}"
                )
            except Exception as e:
                logger.error(f"Failed to clone workflow actions: {e}", exc_info=True)

        logger.info(
            f"Clone process completed successfully for WorkFlow: {cloned_workflow.id}"
        )
        return cloned_workflow


class Pipeline(CompanyBaseWithNamedModelWithClone):
    """
    Represents a pipeline within a workflow.
    Each pipeline belongs to a department and contains multiple stages.
    """

    workflow = models.ForeignKey(
        WorkFlow, on_delete=models.CASCADE, related_name="pipelines"
    )
    # Generic department field - can be mapped to any model via settings
    department_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("Content type of the department model"),
    )
    department_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("ID of the department object"),
    )
    department = GenericForeignKey("department_content_type", "department_id")
    order = models.PositiveIntegerField(
        default=0, help_text=_("Order of this pipeline in the workflow")
    )
    is_hidden = models.BooleanField(
        default=False,
        help_text=_("Whether this pipeline is hidden (true for cloned pipelines)"),
        verbose_name=_("Is Hidden"),
    )
    pipeline_info = models.JSONField(
        default=dict,
        null=True,
        blank=True,
        help_text=_(
            "Pipeline configuration including approvals (for strategy 2 workflows)"
        ),
    )

    @property
    def department_name(self):
        """Get the department name from the generic foreign key."""
        if not self.department:
            return None

        # Try common name attributes
        for attr in ["name", "title", "department_name", "__str__"]:
            if hasattr(self.department, attr):
                if attr == "__str__":
                    return str(self.department)
                value = getattr(self.department, attr)
                if value:
                    return value

        # Fallback to string representation
        return str(self.department)

    def save(self, *args, **kwargs):
        """Override save to validate JSON field sizes."""
        # Validate JSON field sizes before saving
        self._validate_json_fields()
        super().save(*args, **kwargs)

    def _validate_json_fields(self):
        """Validate JSON field sizes to prevent database bloat."""
        # Validate pipeline_info
        if self.pipeline_info:
            validate_json_size(
                self.pipeline_info,
                MAX_PIPELINE_INFO_SIZE,
                "pipeline_info",
                raise_error=True,
            )

    class Meta:
        # Remove company-based unique constraints since company is now optional
        ordering = ("order", "id")


class Stage(CompanyBaseWithNamedModelWithClone):
    """
    Represents a stage within a pipeline.
    Each stage can have form requirements and approval configurations.
    """

    pipeline = models.ForeignKey(
        Pipeline, on_delete=models.PROTECT, related_name="stages"
    )
    form_info = models.JSONField(
        default=list, null=True, help_text=_("Form configuration for this stage")
    )
    stage_info = models.JSONField(
        default=dict, null=True, help_text=_("Stage configuration including approvals")
    )
    is_active = models.BooleanField(default=False)
    order = models.PositiveIntegerField(
        default=0, help_text=_("Order of this stage in the pipeline")
    )
    is_hidden = models.BooleanField(
        default=False,
        help_text=_("Whether this stage is hidden (true for cloned stages)"),
        verbose_name=_("Is Hidden"),
    )

    # ========== ENHANCED ROLE STRATEGY FIELDS ==========
    # From django-approval-workflow v0.8.4+

    # Quorum strategy fields
    quorum_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_(
            "Number of approvals required for QUORUM strategy (e.g., 2 out of 5)"
        ),
    )
    quorum_total = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Total number of users for quorum calculation"),
    )
    percentage_required = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_(
            "Percentage required for PERCENTAGE strategy (e.g., 66.67 for 2/3)"
        ),
    )

    # Hierarchy strategy fields
    hierarchy_levels = models.PositiveIntegerField(
        default=1,
        help_text=_("Number of hierarchy levels to escalate for HIERARCHY_UP strategy"),
    )
    hierarchy_base_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=_("Base user for hierarchy calculation (e.g., account_manager)"),
    )

    # ========== SLA MANAGEMENT FIELDS ==========
    # From django-approval-workflow v0.8.4+

    due_date_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Hours until due date (calculated from stage start)"),
    )
    reminder_hours_before = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Send reminder X hours before due date"),
    )
    escalation_on_timeout = models.BooleanField(
        default=False,
        help_text=_("Auto-escalate to next level when timeout is reached"),
    )
    timeout_action = models.CharField(
        max_length=20,
        choices=[
            ("escalate", _("Escalate")),
            ("reject", _("Auto Reject")),
            ("delegate", _("Delegate")),
            ("auto_approve", _("Auto Approve")),
        ],
        default="escalate",
        help_text=_("Action to take when timeout is reached"),
    )
    max_escalation_level = models.PositiveIntegerField(
        default=3,
        help_text=_("Maximum number of escalation levels allowed"),
    )

    # ========== PARALLEL APPROVAL FIELDS ==========
    # From django-approval-workflow v0.8.4+

    parallel_group = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text=_("Group ID for parallel execution with other stages"),
    )
    parallel_required = models.BooleanField(
        default=False,
        help_text=_("All stages in group must complete before next sequential stage"),
    )

    class Meta:
        ordering = ("order", "id")
        unique_together = [("pipeline", "order")]

    def is_complete(self):
        """Check if the stage is properly configured and complete."""
        # Stage must have stage_info
        if not self.stage_info or not isinstance(self.stage_info, dict):
            return False

        # Stage must have at least one approval configured
        approvals = self.stage_info.get("approvals", [])
        if not approvals:
            return False

        # Validate each approval configuration
        for approval in approvals:
            if not self._validate_approval_config(approval):
                return False

        # If all validations pass and the stage is active, it's complete
        return self.is_active

    def _validate_approval_config(self, approval_config):
        """Validate a single approval configuration."""
        if not isinstance(approval_config, dict):
            return False

        approval_type = approval_config.get("approval_type")
        if not approval_type:
            return False

        # Get valid approval types from enum
        valid_types = [choice[0] for choice in ApprovalTypes.choices]
        if approval_type not in valid_types:
            return False

        # Validate based on an approval type
        if approval_type == ApprovalTypes.ROLE and not approval_config.get("user_role"):
            return False
        elif approval_type == ApprovalTypes.USER and not approval_config.get(
            "approval_user"
        ):
            return False
        elif approval_type == ApprovalTypes.SELF:
            # Self-approved doesn't require additional fields
            pass

        # Validate step_approval_type if provided (APPROVE, SUBMIT, CHECK_IN_VERIFY, MOVE)
        step_approval_type = approval_config.get("step_approval_type")
        if step_approval_type:
            valid_step_types = [choice[0] for choice in ApprovalType.choices]
            if step_approval_type not in valid_step_types:
                logger.warning(
                    f"Invalid step_approval_type '{step_approval_type}' in stage {self.name_en}"
                )
                return False

            # Validate SUBMIT type requirements
            if step_approval_type == ApprovalType.SUBMIT:
                if not approval_config.get("required_form"):
                    logger.warning(
                        f"SUBMIT type requires a form in stage {self.name_en}"
                    )
                    return False

            # Validate MOVE type restrictions
            if step_approval_type == ApprovalType.MOVE:
                if approval_config.get("required_form"):
                    logger.warning(
                        f"MOVE type cannot have a form in stage {self.name_en}"
                    )
                    return False

        return True

    def save(self, *args, **kwargs):
        """Override saves to update the workflow active status when stage changes."""
        # Check if we should skip workflow update (for bulk operations)
        skip_workflow_update = kwargs.pop("skip_workflow_update", False)

        # Validate JSON field sizes before saving
        self._validate_json_fields()

        super().save(*args, **kwargs)

        # Update workflow active status when stage is modified (unless skipped)
        if not skip_workflow_update and self.pipeline and self.pipeline.workflow:
            self.pipeline.workflow.update_active_status()

    def _validate_json_fields(self):
        """Validate JSON field sizes to prevent database bloat."""
        # Validate stage_info
        if self.stage_info:
            validate_json_size(
                self.stage_info,
                MAX_STAGE_INFO_SIZE,
                "stage_info",
                raise_error=True,
            )

        # Validate form_info
        if self.form_info:
            validate_json_size(
                self.form_info,
                MAX_STAGE_INFO_SIZE,  # Use same limit for form_info
                "form_info",
                raise_error=True,
            )


class WorkflowAttachment(models.Model):
    """
    Generic attachment of workflows to any model instance.
    Allows any model to use workflows without hardcoding relationships.
    """

    workflow = models.ForeignKey(
        WorkFlow, on_delete=models.CASCADE, related_name="attachments"
    )

    # Generic foreign key to any model
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text=_("The model type this workflow is attached to"),
    )
    object_id = models.CharField(
        max_length=255, help_text=_("The ID of the model instance")
    )
    target = GenericForeignKey("content_type", "object_id")

    # Current workflow state
    current_stage = models.ForeignKey(
        Stage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_attachments",
        help_text=_("Current stage in the workflow progression"),
    )
    current_pipeline = models.ForeignKey(
        Pipeline,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_attachments",
        help_text=_("Current pipeline in the workflow progression"),
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=WorkflowAttachmentStatus.choices,
        default=WorkflowAttachmentStatus.NOT_STARTED,
        help_text=_("Current status of workflow execution"),
    )

    # Metadata
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    started_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="started_workflow_attachments",
    )

    # Additional data storage
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Additional metadata for workflow execution"),
    )

    created_at = models.DateTimeField(auto_now_add=True, null=True)
    modified_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        unique_together = [("content_type", "object_id")]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["workflow", "status"]),
            models.Index(fields=["current_stage"]),
        ]

    def __str__(self):
        return f"Workflow '{self.workflow.name_en}' attached to {self.content_type.model}({self.object_id})"

    def save(self, *args, **kwargs):
        """Override save to ensure current_pipeline is always in sync with current_stage."""
        # Validate JSON field sizes before saving
        self._validate_json_fields()

        # Ensure current_pipeline is always in sync with current_stage
        if self.current_stage and not self.current_pipeline:
            self.current_pipeline = self.current_stage.pipeline
            logger.debug(
                f"Auto-syncing current_pipeline to {self.current_pipeline.name_en} "
                f"based on current_stage {self.current_stage.name_en}"
            )
        elif self.current_stage and self.current_pipeline:
            # Verify they're in sync
            if self.current_stage.pipeline.id != self.current_pipeline.id:
                logger.warning(
                    f"current_pipeline ({self.current_pipeline.name_en}) does not match "
                    f"current_stage.pipeline ({self.current_stage.pipeline.name_en}). "
                    f"Syncing to current_stage.pipeline."
                )
                self.current_pipeline = self.current_stage.pipeline

        super().save(*args, **kwargs)

    def _validate_json_fields(self):
        """Validate JSON field sizes to prevent database bloat."""
        # Validate metadata
        if self.metadata:
            validate_json_size(
                self.metadata,
                MAX_METADATA_SIZE,
                "metadata",
                raise_error=True,
            )

    @property
    def progress_percentage(self):
        """
        Calculate workflow completion percentage.

        Note: This property benefits from prefetch_related('workflow__pipelines__stages')
        when querying WorkflowAttachment to avoid N+1 queries.
        """
        # Check terminal states first (completed, rejected, canceled)
        if self.status in ["completed", "rejected", "cancelled"]:
            return 100 if self.status == "completed" else 0

        # Check if not started or no current stage
        if not self.current_stage or self.status == "not_started":
            return 0

        # Calculate based on the current position and strategy
        strategy = self.workflow.strategy

        # Strategy 3 (WORKFLOW_ONLY): No stages, progress is based on approval status
        if strategy == WorkflowStrategy.WORKFLOW_ONLY:
            # For workflow-only strategy, calculate progress differently
            # This is handled at the approval level, so return a default
            return 50 if self.status == "in_progress" else 0

        # Strategy 2 (WORKFLOW_PIPELINE): Progress based on pipelines, not stages
        if strategy == WorkflowStrategy.WORKFLOW_PIPELINE:
            return self._calculate_pipeline_progress()

        # Strategy 1 (WORKFLOW_PIPELINE_STAGE): Progress based on stages (default)
        return self._calculate_stage_progress()

    def _calculate_stage_progress(self) -> int:
        """Calculate progress percentage for stage-based workflows."""
        # Use cached workflow/pipelines/stages if available from prefetch_related
        workflow = self.workflow

        # Try to use prefetched data to avoid N+1 queries
        if hasattr(workflow, "_prefetched_objects_cache"):
            pipelines_cache = workflow._prefetched_objects_cache.get("pipelines")
            if pipelines_cache:
                # Use prefetched pipelines
                pipelines = pipelines_cache
            else:
                # Fallback to query
                pipelines = list(workflow.pipelines.all().order_by("order"))
        else:
            pipelines = list(workflow.pipelines.all().order_by("order"))

        total_stages = 0
        current_stage_position = 0

        for pipeline in pipelines:
            # Try to use prefetched stages
            if hasattr(pipeline, "_prefetched_objects_cache"):
                stages_cache = pipeline._prefetched_objects_cache.get("stages")
                if stages_cache:
                    stages = stages_cache
                else:
                    stages = list(pipeline.stages.all().order_by("order"))
            else:
                stages = list(pipeline.stages.all().order_by("order"))

            for stage in stages:
                total_stages += 1
                if stage.id == self.current_stage.id:
                    current_stage_position = total_stages

        if total_stages == 0:
            return 0

        # Progress based on current stage position (stage 1 of 2 = 50%)
        return int((current_stage_position / total_stages) * 100)

    def _calculate_pipeline_progress(self) -> int:
        """Calculate progress percentage for pipeline-based workflows."""
        workflow = self.workflow

        # Try to use prefetched data
        if hasattr(workflow, "_prefetched_objects_cache"):
            pipelines_cache = workflow._prefetched_objects_cache.get("pipelines")
            if pipelines_cache:
                pipelines = pipelines_cache
            else:
                pipelines = list(workflow.pipelines.all().order_by("order"))
        else:
            pipelines = list(workflow.pipelines.all().order_by("order"))

        total_pipelines = len(pipelines)
        if total_pipelines == 0:
            return 0

        # Find current pipeline position
        current_pipeline_position = 0
        for i, pipeline in enumerate(pipelines, 1):
            if self.current_pipeline and pipeline.id == self.current_pipeline.id:
                current_pipeline_position = i
                break

        if current_pipeline_position == 0:
            return 0

        # Progress based on current pipeline position
        return int((current_pipeline_position / total_pipelines) * 100)

    @property
    def next_stage(self):
        """Get the next stage in workflow progression (strategy-aware).

        Behavior depends on workflow strategy:
        - Strategy 1 (Workflow→Pipeline→Stage): Move stage to stage, then pipeline to pipeline (full hierarchy)
        - Strategy 2 (Workflow→Pipeline): Move to next pipeline (no stages exist)
        - Strategy 3 (Workflow Only): No movement, returns None (workflow completes after approvals)
        """
        # Get a workflow strategy
        strategy = self.workflow.strategy

        # Strategy 3 (Workflow Only): No movement between stages/pipelines
        # All approvals are at workflow level, so once complete, the workflow is done
        if strategy == WorkflowStrategy.WORKFLOW_ONLY:
            logger.debug(
                f"Strategy 3 (Workflow Only) - No next stage, workflow will complete after approvals"
            )
            return None

        # Strategy 2 (Workflow→Pipeline): Move to the next pipeline (no stages exist)
        if strategy == WorkflowStrategy.WORKFLOW_PIPELINE:
            current_pipeline = self.current_pipeline

            if not current_pipeline:
                # Return the first pipeline if no current pipeline set
                first_pipeline = self.workflow.pipelines.order_by("order").first()
                logger.debug(
                    f"Strategy 2 (Workflow→Pipeline) - No current pipeline, returning first pipeline"
                )
                return first_pipeline  # Note: This returns a Pipeline, not a Stage

            # Move to the next pipeline
            next_pipeline = (
                self.workflow.pipelines.filter(order__gt=current_pipeline.order)
                .order_by("order")
                .first()
            )

            if next_pipeline:
                logger.debug(
                    f"Strategy 2 (Workflow→Pipeline) - Moving to next pipeline '{next_pipeline.name_en}'"
                )
                return next_pipeline  # Note: This returns a Pipeline, not a Stage
            else:
                logger.debug(
                    f"Strategy 2 (Workflow→Pipeline) - No next pipeline, workflow will complete"
                )
                return None

        # Strategy 1 (Workflow→Pipeline→Stage): Default behavior - move stage to stage (full hierarchy)
        if not self.current_stage:
            # Return first stage of the first pipeline
            first_pipeline = self.workflow.pipelines.order_by("order").first()
            if first_pipeline:
                first_stage = first_pipeline.stages.order_by("order").first()
                if first_stage:
                    logger.debug(
                        f"Strategy 1 (Workflow→Pipeline→Stage) - Returning first stage '{first_stage.name_en}'"
                    )
                    return first_stage
            return None

        # Use the current_pipeline field for consistency, fallback to current_stage.pipeline
        current_pipeline = self.current_pipeline or self.current_stage.pipeline

        if not current_pipeline:
            logger.error(
                ERROR_MESSAGES["no_current_pipeline"].format(attachment_id=self.id)
            )
            return None

        # Try to get the next stage in the current pipeline
        next_stage = (
            current_pipeline.stages.filter(order__gt=self.current_stage.order)
            .order_by("order")
            .first()
        )

        if next_stage:
            logger.debug(
                f"Strategy 1 (Workflow→Pipeline→Stage) - Moving to next stage '{next_stage.name_en}' in same pipeline"
            )
            return next_stage

        # Move to the next pipeline
        next_pipeline = (
            self.workflow.pipelines.filter(order__gt=current_pipeline.order)
            .order_by("order")
            .first()
        )

        if next_pipeline:
            next_stage = next_pipeline.stages.order_by("order").first()
            logger.debug(
                f"Strategy 1 (Workflow→Pipeline→Stage) - Moving to first stage of next pipeline '{next_pipeline.name_en}'"
            )
            return next_stage

        logger.debug(
            f"Strategy 1 (Workflow→Pipeline→Stage) - No next stage or pipeline, workflow will complete"
        )
        return None  # Workflow complete

    def get_progress_info(self):
        """Get detailed progress information."""
        return {
            "current_stage": self.current_stage.name_en if self.current_stage else None,
            "current_pipeline": (
                self.current_pipeline.name_en if self.current_pipeline else None
            ),
            "status": self.status,
            "progress_percentage": self.progress_percentage,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "next_stage": self.next_stage.name_en if self.next_stage else None,
        }


class WorkflowConfiguration(models.Model):
    """
    Configuration for which models can use workflows.
    Allows registration of models that should support workflow functionality.
    """

    content_type = models.OneToOneField(
        ContentType,
        on_delete=models.CASCADE,
        help_text=_("The model type that can use workflows"),
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text=_("Whether workflow functionality is enabled for this model"),
    )
    auto_start_workflow = models.BooleanField(
        default=False,
        help_text=_("Whether to automatically start workflow when object is created"),
    )
    default_workflow = models.ForeignKey(
        WorkFlow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("Default workflow to use for this model"),
    )

    # Hook configurations
    pre_start_hook = models.CharField(
        max_length=255,
        blank=True,
        help_text=_(
            "Python path to function called before workflow starts (e.g., 'myapp.hooks.pre_start')"
        ),
    )
    post_complete_hook = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Python path to function called after workflow completes"),
    )

    # Field mappings
    status_field = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("Field name on the model to update with workflow status"),
    )
    stage_field = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("Field name on the model to store current stage"),
    )

    # Status values for workflow completion/rejection
    completion_status_value = models.CharField(
        max_length=100,
        blank=True,
        help_text=_(
            "Value to set in the status_field when workflow completes successfully "
            "(e.g., 'completed', 'won', 'closed')"
        ),
    )
    rejection_status_value = models.CharField(
        max_length=100,
        blank=True,
        help_text=_(
            "Value to set in the status_field when workflow is rejected "
            "(e.g., 'rejected', 'cancelled', 'lost')"
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True, null=True)
    modified_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        verbose_name = "Workflow Configuration"
        verbose_name_plural = "Workflow Configurations"

    def __str__(self):
        return f"Workflow config for {self.content_type.app_label}.{self.content_type.model}"


class WorkflowAction(models.Model):
    """
    Configurable actions that can be triggered at different workflow events.
    Supports inheritance: Stage -> Pipeline -> Workflow -> Default.
    """

    # Action configuration
    action_type = models.CharField(
        max_length=50,
        choices=ActionType.choices,
        help_text=_("The type of action/event that triggers this action"),
    )
    function_path = models.CharField(
        max_length=255,
        help_text=_(
            "Python path to the function to execute (e.g., 'myapp.actions.send_email')"
        ),
    )
    is_active = models.BooleanField(
        default=True, help_text=_("Whether this action is active")
    )

    # Scope - only one of these should be set (inheritance system)
    workflow = models.ForeignKey(
        WorkFlow,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="actions",
        help_text=_("Workflow this action belongs to (workflow-level action)"),
    )
    pipeline = models.ForeignKey(
        Pipeline,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="actions",
        help_text=_("Pipeline this action belongs to (pipeline-level action)"),
    )
    stage = models.ForeignKey(
        Stage,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="actions",
        help_text=_("Stage this action belongs to (stage-level action)"),
    )

    # Additional configuration
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Additional parameters to pass to the action function"),
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text=_("Execution order when multiple actions exist for the same event"),
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    modified_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        verbose_name = "Workflow Action"
        verbose_name_plural = "Workflow Actions"
        indexes = [
            models.Index(fields=["action_type"]),
            models.Index(fields=["workflow", "action_type"]),
            models.Index(fields=["pipeline", "action_type"]),
            models.Index(fields=["stage", "action_type"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(workflow__isnull=False, pipeline__isnull=True, stage__isnull=True)
                    | Q(
                        workflow__isnull=True,
                        pipeline__isnull=False,
                        stage__isnull=True,
                    )
                    | Q(
                        workflow__isnull=True,
                        pipeline__isnull=True,
                        stage__isnull=False,
                    )
                ),
                name="workflow_action_single_scope",
            )
        ]

    def __str__(self):
        scope = "Global"
        if self.stage:
            scope = f"Stage: {self.stage.name_en}"
        elif self.pipeline:
            scope = f"Pipeline: {self.pipeline.name_en}"
        elif self.workflow:
            scope = f"Workflow: {self.workflow.name_en}"

        return f"{self.get_action_type_display()} - {scope} - {self.function_path}"

    def clean(self):
        """Validate that exactly one scope is set."""
        scope_count = sum([bool(self.workflow), bool(self.pipeline), bool(self.stage)])

        if scope_count != 1:
            raise ValidationError(
                "Exactly one of workflow, pipeline, or stage must be set."
            )

    @property
    def scope_level(self):
        """Return the scope level (stage, pipeline, workflow)."""
        if self.stage:
            return "stage"
        elif self.pipeline:
            return "pipeline"
        elif self.workflow:
            return "workflow"
        return "default"

    @property
    def scope_object(self):
        """Return the scope object (Stage, Pipeline, or WorkFlow instance)."""
        if self.stage:
            return self.stage
        elif self.pipeline:
            return self.pipeline
        elif self.workflow:
            return self.workflow
        return None
