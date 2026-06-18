"""Helper services for status definitions and status workflow designs."""

from copy import deepcopy
from typing import Any, Dict, List, Optional

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.utils.module_loading import import_string

from .action_management import create_custom_workflow_actions
from .choices import TransitionRejectBehavior, WorkflowStrategy
from .models import (
    ModelStatus,
    ModelStatusConfiguration,
    Status,
    StatusTransition,
    WorkFlow,
    WorkflowConfiguration,
    WorkflowStatusNode,
    validate_approval_configuration_payload,
)
from .settings import get_default_status_workflow_config, get_default_status_workflows


def resolve_status_content_type(model: str) -> ContentType:
    """Resolve an app_label.model_name string to a ContentType."""
    try:
        app_label, model_name = model.split(".", 1)
    except (AttributeError, ValueError) as exc:
        raise ValueError("Invalid model. Use app_label.model_name") from exc

    try:
        return ContentType.objects.get(app_label=app_label, model=model_name.lower())
    except ContentType.DoesNotExist as exc:
        raise ValueError("Invalid model. Use app_label.model_name") from exc


def status_option(status_obj, model_status=None) -> Dict[str, Any]:
    """Return a frontend-friendly status option."""
    return {
        "id": status_obj.id,
        "key": status_obj.key,
        "label": status_obj.name_en,
        "label_en": status_obj.name_en,
        "label_ar": status_obj.name_ar,
        "category": status_obj.category,
        "color": status_obj.color,
        "icon": status_obj.icon,
        "metadata": status_obj.metadata,
        "is_initial": model_status.is_initial if model_status else False,
        "is_terminal": model_status.is_terminal if model_status else False,
        "order": model_status.order if model_status else 0,
    }


def action_option(action) -> Dict[str, Any]:
    """Return an action configuration suitable for APIs and diagram clients."""
    return {
        "id": action.id,
        "action_type": action.action_type,
        "function_path": action.function_path,
        "condition_function": action.condition_function,
        "failure_policy": action.failure_policy,
        "parameters": action.parameters,
        "order": action.order,
        "is_active": action.is_active,
    }


def create_status_for_model(
    *,
    model: str,
    name_en: str,
    name_ar: str = "",
    company=None,
    user=None,
    **kwargs,
) -> Status:
    """Create one status for a model without going through the REST API."""
    content_type = resolve_status_content_type(model)
    return Status.objects.create(
        content_type=content_type,
        name_en=name_en,
        name_ar=name_ar,
        company=company,
        created_by=user,
        modified_by=user,
        **kwargs,
    )


def get_status_flow_design(model: str, workflow: Optional[WorkFlow] = None):
    """Return the complete status configuration and workflow graph for a model."""
    content_type = resolve_status_content_type(model)
    config = (
        ModelStatusConfiguration.objects.filter(content_type=content_type)
        .select_related("default_status")
        .prefetch_related("model_statuses__status")
        .first()
    )
    if not workflow:
        workflow_config = WorkflowConfiguration.objects.filter(
            content_type=content_type
        ).first()
        workflow = workflow_config.default_workflow if workflow_config else None

    statuses = []
    if config:
        company_filter = Q()
        if workflow and workflow.company_id:
            company_filter = Q(status__company__isnull=True) | Q(
                status__company_id=workflow.company_id
            )
        statuses = [
            status_option(model_status.status, model_status)
            for model_status in config.model_statuses.select_related("status")
            .filter(company_filter, is_active=True)
            .order_by("order", "id")
        ]

    nodes = []
    transitions = []
    if workflow:
        nodes = [
            {
                "id": node.id,
                "status_id": node.status_id,
                "code": node.status.key,
                "label": node.status.name_en,
                "label_en": node.status.name_en,
                "label_ar": node.status.name_ar,
                "category": node.status.category,
                "color": node.status.color,
                "icon": node.status.icon,
                "metadata": {**node.status.metadata, **node.metadata},
                "is_initial": node.is_initial,
                "is_terminal": node.is_terminal,
                "order": node.order,
                "actions": [
                    action_option(action)
                    for action in node.actions.filter(is_active=True).order_by(
                        "order", "id"
                    )
                ],
            }
            for node in workflow.status_nodes.select_related("status")
            .filter(is_active=True)
            .order_by("order", "id")
        ]
        transitions = [
            {
                "id": transition.id,
                "code": transition.key,
                "label": transition.name_en,
                "label_en": transition.name_en,
                "label_ar": transition.name_ar,
                "from": transition.from_status.status.key,
                "to": transition.to_status.status.key,
                "source": transition.from_status_id,
                "target": transition.to_status_id,
                "approvals": (transition.approval_config or {}).get("approvals", []),
                "reject_behavior": transition.reject_behavior,
                "reject_to": (
                    transition.reject_to_status.status.key
                    if transition.reject_to_status
                    else None
                ),
                "permission_codename": transition.permission_codename,
                "metadata": transition.metadata,
                "order": transition.order,
                "is_active": transition.is_active,
                "actions": [
                    action_option(action)
                    for action in transition.actions.filter(is_active=True).order_by(
                        "order", "id"
                    )
                ],
            }
            for transition in workflow.status_transitions.select_related(
                "from_status__status", "to_status__status", "reject_to_status__status"
            )
            .filter(is_active=True)
            .order_by("order", "id")
        ]

    return {
        "model": f"{content_type.app_label}.{content_type.model}",
        "content_type": content_type.id,
        "configuration": (
            {
                "id": config.id,
                "status_field": config.status_field,
                "default_status": config.default_status_id,
                "auto_create_attachment": config.auto_create_attachment,
                "allow_direct_change": config.allow_direct_change,
                "is_enabled": config.is_enabled,
            }
            if config
            else None
        ),
        "workflow": (
            {
                "id": workflow.id,
                "name_en": workflow.name_en,
                "name_ar": workflow.name_ar,
                "description": workflow.description,
                "status": workflow.status,
                "strategy": workflow.strategy,
                "is_active": workflow.is_active,
            }
            if workflow
            else None
        ),
        "statuses": statuses,
        "nodes": nodes,
        "transitions": transitions,
        "diagram": {"nodes": nodes, "edges": transitions},
    }


@transaction.atomic
def create_status_flow_design(data: Dict[str, Any], user=None) -> Dict[str, Any]:
    """Create statuses, model config, workflow nodes, and transitions in one call."""
    content_type = resolve_status_content_type(data.get("model"))
    workflow_data = data.get("workflow", {})
    statuses_data = data.get("statuses", [])
    transitions_data = data.get("transitions", [])
    merge_model_statuses = data.get("merge_model_statuses", False)
    register_default_workflow = data.get("register_default_workflow", True)
    if not statuses_data:
        raise ValueError("statuses is required")

    company_id = data.get("company") or workflow_data.get("company")
    status_by_code = {}
    status_only_fields = {
        "key",
        "name_en",
        "name_ar",
        "category",
        "color",
        "icon",
        "description",
        "metadata",
        "is_active",
    }
    for index, status_data in enumerate(statuses_data):
        code = status_data.get("code") or status_data.get("key")
        if not code:
            raise ValueError(f"statuses[{index}].code is required")
        status_kwargs = {
            field: value
            for field, value in status_data.items()
            if field in status_only_fields
        }
        status_obj = Status.objects.create(
            **status_kwargs,
            company_id=status_data.get("company", company_id),
            content_type=content_type,
            created_by=user,
            modified_by=user,
        )
        status_by_code[code] = status_obj
        status_by_code[status_obj.key] = status_obj

    default_code = data.get("default_status") or statuses_data[0].get("code")
    default_status = status_by_code.get(default_code)
    if not default_status:
        raise ValueError("default_status does not match any status code")

    config, created_config = ModelStatusConfiguration.objects.get_or_create(
        content_type=content_type,
        defaults={
            "is_enabled": data.get("is_enabled", True),
            "status_field": data.get("status_field", ""),
            "default_status": default_status,
            "auto_create_attachment": data.get("auto_create_attachment", True),
            "allow_direct_change": data.get("allow_direct_change", True),
            "created_by": user,
            "modified_by": user,
        },
    )
    config.is_enabled = data.get("is_enabled", True)
    config.status_field = data.get("status_field", config.status_field)
    config.auto_create_attachment = data.get(
        "auto_create_attachment", config.auto_create_attachment
    )
    config.allow_direct_change = data.get(
        "allow_direct_change", config.allow_direct_change
    )
    config.modified_by = user
    if created_config or not merge_model_statuses:
        config.default_status = default_status
    config.save()
    if user and not config.created_by_id:
        config.created_by = user
        config.save(update_fields=["created_by"])

    if not merge_model_statuses:
        ModelStatus.objects.filter(configuration=config).delete()
    terminal_codes = set(data.get("terminal_statuses", []))
    for index, status_data in enumerate(statuses_data):
        code = status_data.get("code") or status_data.get("key")
        ModelStatus.objects.update_or_create(
            configuration=config,
            status=status_by_code[code],
            defaults={
                "is_initial": code == default_code
                or status_data.get("is_initial", False),
                "is_terminal": status_data.get("is_terminal", code in terminal_codes),
                "order": status_data.get("order", index),
                "is_active": status_data.get("is_active", True),
                "created_by": user,
                "modified_by": user,
            },
        )

    workflow = WorkFlow.objects.create(
        company_id=workflow_data.get("company", company_id),
        name_en=workflow_data.get("name_en", f"{content_type.name} Status Flow"),
        name_ar=workflow_data.get("name_ar", workflow_data.get("name_en", "")),
        description=workflow_data.get("description", ""),
        workflow_info=workflow_data.get("workflow_info", {}),
        status=workflow_data.get("status", "active"),
        strategy=workflow_data.get("strategy", WorkflowStrategy.STATUS_GRAPH),
        created_by=user,
        modified_by=user,
    )

    if register_default_workflow:
        WorkflowConfiguration.objects.update_or_create(
            content_type=content_type,
            defaults={
                "is_enabled": True,
                "default_workflow": workflow,
                "auto_start_workflow": data.get("auto_start_workflow", False),
                "status_field": data.get("workflow_status_field", ""),
            },
        )

    node_by_code = {}
    for index, status_data in enumerate(statuses_data):
        code = status_data.get("code") or status_data.get("key")
        status_obj = status_by_code[code]
        node = WorkflowStatusNode.objects.create(
            workflow=workflow,
            status=status_obj,
            is_initial=code == default_code or status_data.get("is_initial", False),
            is_terminal=status_data.get("is_terminal", code in terminal_codes),
            order=status_data.get("order", index),
            is_active=status_data.get("is_active", True),
            metadata=status_data.get("node_metadata", {}),
            created_by=user,
            modified_by=user,
        )
        node_by_code[code] = node
        node_by_code[status_obj.key] = node
        actions_data = status_data.get("actions") or status_data.get("status_actions")
        if actions_data:
            created_actions = create_custom_workflow_actions(
                actions_data, status_node=node
            )
            if len(created_actions) != len(actions_data):
                raise ValueError(f"Could not create all actions for status '{code}'")

    for index, transition_data in enumerate(transitions_data):
        from_code = transition_data.get("from")
        to_code = transition_data.get("to")
        transition_key = transition_data.get("code") or transition_data.get("key")
        transition_name = (
            transition_data.get("name_en")
            or transition_data.get("label_en")
            or transition_data.get("label")
        )
        if not transition_key:
            raise ValueError(f"transitions[{index}].code is required")
        if not transition_name:
            raise ValueError(f"transitions[{index}].name_en is required")
        if from_code not in node_by_code or to_code not in node_by_code:
            raise ValueError(f"transitions[{index}] references unknown status code")

        approvals = transition_data.get("approvals")
        if approvals is None:
            approvals = transition_data.get("approval_config", {}).get("approvals", [])
        approvals = approvals or []
        approval_config = {"approvals": approvals}
        validate_approval_configuration_payload(
            approval_config, require_approvals=bool(approvals)
        )
        reject_to = transition_data.get("reject_to")
        transition = StatusTransition.objects.create(
            workflow=workflow,
            key=transition_key,
            name_en=transition_name,
            name_ar=transition_data.get("name_ar", ""),
            description=transition_data.get("description", ""),
            from_status=node_by_code[from_code],
            to_status=node_by_code[to_code],
            requires_approval=bool(approvals),
            approval_config=approval_config,
            reject_behavior=transition_data.get(
                "reject_behavior", TransitionRejectBehavior.STAY_CURRENT
            ),
            reject_to_status=node_by_code.get(reject_to) if reject_to else None,
            permission_codename=transition_data.get("permission_codename", ""),
            metadata=transition_data.get("metadata", {}),
            order=transition_data.get("order", index),
            is_active=transition_data.get("is_active", True),
            created_by=user,
            modified_by=user,
        )
        actions_data = transition_data.get("actions") or transition_data.get(
            "transition_actions"
        )
        if actions_data:
            created_actions = create_custom_workflow_actions(
                actions_data, transition=transition
            )
            if len(created_actions) != len(actions_data):
                raise ValueError(
                    f"Could not create all actions for transition '{transition_key}'"
                )

    workflow.update_active_status()
    return get_status_flow_design(
        f"{content_type.app_label}.{content_type.model}", workflow=workflow
    )


def _default_workflow_model_label(model: str) -> str:
    content_type = resolve_status_content_type(model)
    return f"{content_type.app_label}.{content_type.model}"


def _build_default_workflow_design(
    model: str,
    company,
    user=None,
    configuration: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    configuration = configuration or get_default_status_workflow_config(model)
    if not configuration:
        raise ValueError(f"No default status workflow configured for '{model}'")

    if configuration.get("factory"):
        factory = import_string(configuration["factory"])
        design = factory(company=company, model=model, user=user)
    elif "design" in configuration:
        design = deepcopy(configuration.get("design") or {})
    else:
        design = deepcopy(configuration)
        for control_key in ("auto_start", "company_field", "key"):
            design.pop(control_key, None)

    if not isinstance(design, dict):
        raise ValueError("Default status workflow design must be a dictionary")

    design = deepcopy(design)
    design["model"] = model
    design["company"] = getattr(company, "pk", company)
    design["merge_model_statuses"] = True
    design["register_default_workflow"] = False
    design.setdefault("allow_direct_change", False)

    workflow_data = design.setdefault("workflow", {})
    workflow_key = configuration.get("key", "default")
    workflow_info = workflow_data.setdefault("workflow_info", {})
    workflow_info.update(
        {
            "default_status_workflow": True,
            "default_status_model": _default_workflow_model_label(model),
            "default_status_key": workflow_key,
        }
    )
    return design


def get_company_default_status_workflow(
    model: str,
    company,
    key: str = "default",
) -> Optional[WorkFlow]:
    """Return an existing company-owned default status workflow."""
    company_id = getattr(company, "pk", company)
    model_label = _default_workflow_model_label(model)
    workflows = WorkFlow.objects.filter(
        company_id=company_id,
        strategy=WorkflowStrategy.STATUS_GRAPH,
        is_hidden=False,
    ).order_by("id")
    for workflow in workflows:
        info = workflow.workflow_info or {}
        if (
            info.get("default_status_workflow")
            and info.get("default_status_model") == model_label
            and info.get("default_status_key") == key
        ):
            return workflow
    return None


def get_or_create_default_status_workflow(
    *,
    model: str,
    company,
    user=None,
) -> WorkFlow:
    """Idempotently provision the configured default workflow for one company/model."""
    configuration = get_default_status_workflow_config(model)
    if not configuration:
        raise ValueError(f"No default status workflow configured for '{model}'")

    key = configuration.get("key", "default")
    existing = get_company_default_status_workflow(model, company, key=key)
    if existing:
        return existing

    design = _build_default_workflow_design(
        model=model,
        company=company,
        user=user,
        configuration=configuration,
    )
    result = create_status_flow_design(design, user=user)
    return WorkFlow.objects.get(pk=result["workflow"]["id"])


def ensure_default_status_workflows_for_company(
    company,
    *,
    user=None,
    models: Optional[List[str]] = None,
) -> Dict[str, WorkFlow]:
    """Provision every configured default status workflow for a company."""
    configured_models = models or [
        model for model in get_default_status_workflows() if model != "default"
    ]
    return {
        model: get_or_create_default_status_workflow(
            model=model,
            company=company,
            user=user,
        )
        for model in configured_models
    }


def auto_generate_default_flow(
    company_id: int,
    flow=None,
    *,
    user=None,
) -> Dict[str, WorkFlow]:
    """
    Provision company-owned status workflows from settings or an explicit design.

    With no flow, every model in DEFAULT_STATUS_WORKFLOWS is provisioned.
    A string provisions one configured model. A dictionary may be one design
    containing ``model`` or a mapping of model labels to designs.
    """
    company_model = get_user_model()
    try:
        company = company_model._default_manager.get(pk=company_id)
    except company_model.DoesNotExist as exc:
        raise ValueError(f"Company with id '{company_id}' does not exist") from exc

    audit_user = user or company
    if flow is None:
        return ensure_default_status_workflows_for_company(
            company,
            user=audit_user,
        )

    if isinstance(flow, str):
        return {
            flow: get_or_create_default_status_workflow(
                model=flow,
                company=company,
                user=audit_user,
            )
        }

    if not isinstance(flow, dict):
        raise ValueError("flow must be a model label or a workflow design dictionary")

    if flow.get("model"):
        explicit_flows = {flow["model"]: flow}
    else:
        explicit_flows = flow

    generated = {}
    for model, configuration in explicit_flows.items():
        if not isinstance(configuration, dict):
            raise ValueError(f"Flow design for '{model}' must be a dictionary")

        workflow_key = configuration.get("key", "default")
        existing = get_company_default_status_workflow(
            model,
            company,
            key=workflow_key,
        )
        if existing:
            generated[model] = existing
            continue

        design = _build_default_workflow_design(
            model=model,
            company=company,
            user=audit_user,
            configuration=configuration,
        )
        result = create_status_flow_design(design, user=audit_user)
        generated[model] = WorkFlow.objects.get(pk=result["workflow"]["id"])

    return generated


def get_or_create_default_status_workflow_for_object(obj, user=None) -> WorkFlow:
    """Resolve the object's company and provision its configured default workflow."""
    model = f"{obj._meta.app_label}.{obj.__class__.__name__}"
    configuration = get_default_status_workflow_config(model)
    if not configuration:
        raise ValueError(f"No default status workflow configured for '{model}'")

    company_field = configuration.get("company_field", "company")
    company = obj
    for part in company_field.split("."):
        company = getattr(company, part, None)
        if company is None:
            break
    if company is None:
        raise ValueError(
            f"Could not resolve company using field '{company_field}' on {model}"
        )

    return get_or_create_default_status_workflow(
        model=model,
        company=company,
        user=user,
    )


def attach_default_status_workflow(obj, user=None, auto_start=None, metadata=None):
    """Provision and attach the object's company-specific default workflow."""
    from .services import attach_workflow_to_object

    model = f"{obj._meta.app_label}.{obj.__class__.__name__}"
    configuration = get_default_status_workflow_config(model) or {}
    workflow = get_or_create_default_status_workflow_for_object(obj, user=user)
    if auto_start is None:
        auto_start = configuration.get("auto_start", True)
    return attach_workflow_to_object(
        obj,
        workflow,
        user=user,
        auto_start=auto_start,
        metadata=metadata,
    )
