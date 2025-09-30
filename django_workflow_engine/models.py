"""Models for django_workflow_engine Django app.

Workflow management models (WorkFlow, Pipeline, Stage) for creating and managing
dynamic multi-step workflows. Integrates with django-approval-workflow package
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

from .choices import ActionType, ApprovalTypes, WorkflowAttachmentStatus, WorkflowStatus

logger = logging.getLogger(__name__)
User = get_user_model()


class BaseCompanyModel(models.Model):
    """Base model for company-scoped models."""

    # Optional company field - uses User model for company association
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

    class Meta:
        # Remove company-based unique constraints since company is now optional
        ordering = ("-id",)
        verbose_name = _("Workflow")
        verbose_name_plural = _("Workflows")

    def validate_completeness(self):
        """Validate if workflow is complete and can be activated.

        Uses select_related/prefetch_related for optimal performance.
        """
        # Use prefetch_related to fetch all pipelines and stages in 2 queries
        pipelines = self.pipelines.prefetch_related("stages").all()

        if not pipelines:
            return False, "Workflow must have at least one pipeline"

        for pipeline in pipelines:
            stages = list(pipeline.stages.all())  # Already prefetched
            if not stages:
                return (
                    False,
                    f"Pipeline '{pipeline.name_en}' must have at least one stage",
                )

            for stage in stages:
                if not stage.is_complete():
                    return (
                        False,
                        f"Stage '{stage.name_en}' in pipeline '{pipeline.name_en}' is not properly configured",
                    )

        return True, "Workflow is complete and valid"

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

    def clone(self, modified_keys=None, overrides=None):
        logger.info(f"Starting clone process for WorkFlow: {self.id} ({self.name_en})")

        with transaction.atomic():
            cloned_workflow = super().clone(modified_keys=["name_en", "name_ar"])
            logger.info(f"Cloned WorkFlow {self.id} -> {cloned_workflow.id}")

            pipeline_map = {}

            for pipeline in self.pipelines.all():
                cloned_pipeline = pipeline.clone(
                    modified_keys=["name_en", "name_ar"],
                    overrides={"workflow": cloned_workflow},
                )
                pipeline_map[pipeline.id] = cloned_pipeline
                logger.info(f"Cloned Pipeline {pipeline.id} -> {cloned_pipeline.id}")

                for stage in pipeline.stages.all():
                    stage.clone(
                        modified_keys=["name_en", "name_ar"],
                        overrides={"pipeline": cloned_pipeline},
                    )
                    logger.info(
                        f"Cloned Stage {stage.id} for Pipeline {cloned_pipeline.id}"
                    )

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

    @property
    def department_name(self):
        """Get department name from the generic foreign key."""
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

    class Meta:
        ordering = ("order", "id")
        unique_together = [("pipeline", "order")]

    def is_complete(self):
        """Check if stage is properly configured and complete."""
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

        # If all validations pass and stage is active, it's complete
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

        # Validate based on approval type
        if approval_type == ApprovalTypes.ROLE and not approval_config.get("user_role"):
            return False
        elif approval_type == ApprovalTypes.USER and not approval_config.get(
            "approval_user"
        ):
            return False
        elif approval_type == ApprovalTypes.SELF:
            # Self-approved doesn't require additional fields
            return True

        return True

    def save(self, *args, **kwargs):
        """Override save to update workflow active status when stage changes."""
        # Check if we should skip workflow update (for bulk operations)
        skip_workflow_update = kwargs.pop("skip_workflow_update", False)

        super().save(*args, **kwargs)

        # Update workflow active status when stage is modified (unless skipped)
        if not skip_workflow_update and self.pipeline and self.pipeline.workflow:
            self.pipeline.workflow.update_active_status()


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

    @property
    def progress_percentage(self):
        """Calculate workflow completion percentage."""
        if not self.current_stage or self.status == "not_started":
            return 0

        if self.status in ["completed", "rejected", "cancelled"]:
            return 100 if self.status == "completed" else 0

        # Calculate based on current position
        total_stages = 0
        current_stage_position = 0

        for pipeline in self.workflow.pipelines.all().order_by("order"):
            for stage in pipeline.stages.all().order_by("order"):
                total_stages += 1
                if stage.id == self.current_stage.id:
                    current_stage_position = total_stages

        if total_stages == 0:
            return 0

        # Progress based on current stage position (stage 1 of 2 = 50%)
        return int((current_stage_position / total_stages) * 100)

    @property
    def next_stage(self):
        """Get the next stage in workflow progression."""
        if not self.current_stage:
            # Return first stage of first pipeline
            first_pipeline = self.workflow.pipelines.order_by("order").first()
            if first_pipeline:
                return first_pipeline.stages.order_by("order").first()
            return None

        current_pipeline = self.current_stage.pipeline

        # Try to get next stage in current pipeline
        next_stage = (
            current_pipeline.stages.filter(order__gt=self.current_stage.order)
            .order_by("order")
            .first()
        )

        if next_stage:
            return next_stage

        # Move to next pipeline
        next_pipeline = (
            self.workflow.pipelines.filter(order__gt=current_pipeline.order)
            .order_by("order")
            .first()
        )

        if next_pipeline:
            return next_pipeline.stages.order_by("order").first()

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
