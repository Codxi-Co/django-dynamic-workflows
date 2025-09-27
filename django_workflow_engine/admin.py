"""Django admin configuration for workflow engine models."""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import (
    Pipeline,
    Stage,
    WorkFlow,
    WorkflowAction,
    WorkflowAttachment,
    WorkflowConfiguration,
)


@admin.register(WorkFlow)
class WorkFlowAdmin(admin.ModelAdmin):
    """Admin configuration for WorkFlow model."""

    list_display = [
        "name_en",
        "name_ar",
        "company",
        "status",
        "created_at",
        "is_active",
    ]
    list_filter = ["status", "company", "created_at"]
    search_fields = ["name_en", "name_ar", "description"]
    readonly_fields = ["created_at", "modified_at"]

    fieldsets = (
        (None, {"fields": ("company", "name_en", "name_ar", "status", "description")}),
        (
            "Audit",
            {
                "fields": ("created_by", "modified_by", "created_at", "modified_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    """Admin configuration for Pipeline model."""

    list_display = [
        "name_en",
        "name_ar",
        "workflow",
        "department",
        "company",
        "order",
        "created_at",
    ]
    list_filter = ["workflow", "department", "company", "created_at"]
    search_fields = ["name_en", "name_ar", "workflow__name_en"]
    readonly_fields = ["created_at", "modified_at"]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "workflow",
                    "company",
                    "name_en",
                    "name_ar",
                    "department",
                    "order",
                )
            },
        ),
        (
            "Audit",
            {
                "fields": ("created_by", "modified_by", "created_at", "modified_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    """Admin configuration for Stage model."""

    list_display = [
        "name_en",
        "name_ar",
        "pipeline",
        "is_active",
        "order",
        "created_at",
    ]
    list_filter = ["is_active", "pipeline__workflow", "pipeline", "created_at"]
    search_fields = ["name_en", "name_ar", "pipeline__name_en"]
    readonly_fields = ["created_at", "modified_at"]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "pipeline",
                    "company",
                    "name_en",
                    "name_ar",
                    "order",
                    "is_active",
                )
            },
        ),
        (
            "Configuration",
            {"fields": ("form_info", "stage_info"), "classes": ("collapse",)},
        ),
        (
            "Audit",
            {
                "fields": ("created_by", "modified_by", "created_at", "modified_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(WorkflowAttachment)
class WorkflowAttachmentAdmin(admin.ModelAdmin):
    """Admin configuration for WorkflowAttachment model."""

    list_display = [
        "id",
        "get_target_object",
        "workflow",
        "status",
        "current_stage",
        "progress_percentage",
        "started_at",
    ]
    list_filter = ["status", "workflow", "content_type", "started_at"]
    search_fields = ["object_id", "workflow__name_en"]
    readonly_fields = ["created_at", "modified_at", "progress_percentage"]

    fieldsets = (
        (None, {"fields": ("workflow", "content_type", "object_id", "status")}),
        (
            "Progress",
            {"fields": ("current_stage", "current_pipeline", "progress_percentage")},
        ),
        ("Tracking", {"fields": ("started_at", "completed_at", "started_by")}),
        ("Metadata", {"fields": ("metadata",), "classes": ("collapse",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "modified_at"), "classes": ("collapse",)},
        ),
    )

    def get_target_object(self, obj):
        """Get a link to the target object."""
        if obj.target:
            try:
                admin_url = reverse(
                    f"admin:{obj.content_type.app_label}_{obj.content_type.model}_change",
                    args=[obj.object_id],
                )
                return format_html('<a href="{}">{}</a>', admin_url, str(obj.target))
            except:
                return str(obj.target)
        return "-"

    get_target_object.short_description = "Target Object"


@admin.register(WorkflowConfiguration)
class WorkflowConfigurationAdmin(admin.ModelAdmin):
    """Admin configuration for WorkflowConfiguration model."""

    list_display = [
        "get_model_name",
        "is_enabled",
        "auto_start_workflow",
        "default_workflow",
        "created_at",
    ]
    list_filter = ["is_enabled", "auto_start_workflow", "content_type"]
    search_fields = ["content_type__app_label", "content_type__model"]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "content_type",
                    "is_enabled",
                    "auto_start_workflow",
                    "default_workflow",
                )
            },
        ),
        ("Field Mappings", {"fields": ("status_field", "stage_field")}),
        (
            "Hooks",
            {
                "fields": ("pre_start_hook", "post_complete_hook"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "modified_at"), "classes": ("collapse",)},
        ),
    )

    readonly_fields = ["created_at", "modified_at"]

    def get_model_name(self, obj):
        """Get formatted model name."""
        return f"{obj.content_type.app_label}.{obj.content_type.model}"

    get_model_name.short_description = "Model"


@admin.register(WorkflowAction)
class WorkflowActionAdmin(admin.ModelAdmin):
    """Admin configuration for WorkflowAction model."""

    list_display = [
        "action_type",
        "get_scope",
        "function_path",
        "is_active",
        "order",
        "created_at",
    ]
    list_filter = ["action_type", "is_active", "workflow", "pipeline", "stage"]
    search_fields = [
        "function_path",
        "workflow__name_en",
        "pipeline__name_en",
        "stage__name_en",
    ]
    readonly_fields = ["created_at", "modified_at", "scope_level"]

    fieldsets = (
        (None, {"fields": ("action_type", "function_path", "is_active", "order")}),
        (
            "Scope (select only one)",
            {
                "fields": ("workflow", "pipeline", "stage"),
                "description": "Select exactly one scope: Stage (highest priority) → Pipeline → Workflow",
            },
        ),
        ("Configuration", {"fields": ("parameters",), "classes": ("collapse",)}),
        ("Info", {"fields": ("scope_level",), "classes": ("collapse",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "modified_at"), "classes": ("collapse",)},
        ),
    )

    def get_scope(self, obj):
        """Get formatted scope information."""
        if obj.stage:
            return format_html(
                "<strong>Stage:</strong> {} ({})",
                obj.stage.name_en,
                obj.stage.pipeline.name_en,
            )
        elif obj.pipeline:
            return format_html(
                "<strong>Pipeline:</strong> {} ({})",
                obj.pipeline.name_en,
                obj.pipeline.workflow.name_en,
            )
        elif obj.workflow:
            return format_html("<strong>Workflow:</strong> {}", obj.workflow.name_en)
        return "Default"

    get_scope.short_description = "Scope"

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return (
            super()
            .get_queryset(request)
            .select_related(
                "workflow", "pipeline__workflow", "stage__pipeline__workflow"
            )
        )
