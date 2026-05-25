# Release Notes - v1.7.0

**Release Date:** May 26, 2026
**Status:** Production Ready
**Tests:** 395/395 Passing (100%)
**Minimum Python:** 3.10+
**Minimum Django:** 5.2+
**Minimum django-approval-workflow:** 0.9.0+

---

## Per-Model Configuration with Default Fallback

This release adds a `"default"` key to all configuration dictionaries, enabling shared default workflows and actions across modules while allowing per-model overrides.

### Problem

When you have multiple modules (CRM, HR, Support), each with its own models and workflows, you had to configure every single model individually. No fallback existed for models without explicit configuration.

### Solution

Add a `"default"` key that acts as a fallback. Resolution order: **exact model match** → `"default"` key → existing behavior.

---

## What's New

### 1. Default Fallback for MODEL_WORKFLOW_MAPPINGS

```python
DJANGO_WORKFLOW_ENGINE = {
    "MODEL_WORKFLOW_MAPPINGS": {
        "default": ["generic_approval"],           # fallback for any unmapped model
        "crm.Opportunity": ["opportunity_approval"],
        "hr.LeaveRequest": ["leave_approval"],
    },
}
```

Unmapped models like `support.Ticket` automatically get `["generic_approval"]`.

### 2. Default Fallback for AUTO_START_WORKFLOWS

```python
DJANGO_WORKFLOW_ENGINE = {
    "AUTO_START_WORKFLOWS": {
        "default": {
            "workflow_slug": "generic_approval",
            "auto_start": True,
        },
        "crm.Opportunity": {
            "workflow_slug": "opportunity_approval",
            "auto_start": True,
            "conditions": {"amount__gte": 1000},
        },
    },
}
```

### 3. Dict Format for WORKFLOW_ACTIONS_CONFIG

`WORKFLOW_ACTIONS_CONFIG` now supports two formats:

**Format 1 — Flat list (backward compatible):**
```python
WORKFLOW_ACTIONS_CONFIG = [
    {"action_type": "after_approve", "function_path": "myapp.actions.send_email", "order": 1},
]
```

**Format 2 — Dict keyed by model string with `"default"` fallback:**
```python
WORKFLOW_ACTIONS_CONFIG = {
    "default": [
        {"action_type": "after_approve", "function_path": "myapp.actions.generic_email", "order": 1},
    ],
    "crm.Opportunity": [
        {"action_type": "after_approve", "function_path": "myapp.actions.opportunity_email", "order": 1},
    ],
    "hr.LeaveRequest": [
        {"action_type": "after_approve", "function_path": "myapp.actions.leave_email", "order": 1},
    ],
}
```

The action executor automatically resolves the model string from the `WorkflowAttachment.content_type`, so model-specific actions fire without any code changes.

---

## Complete Multi-Module Example

```python
# settings.py

DJANGO_WORKFLOW_ENGINE = {
    "ENABLED_MODELS": [
        "crm.Opportunity",
        "hr.LeaveRequest",
        "support.Ticket",
    ],
    "DEFAULT_STATUS_FIELD": "status",
    "DEPARTMENT_MODEL": "common.Department",

    "MODEL_WORKFLOW_MAPPINGS": {
        "default": ["generic_approval"],
        "crm.Opportunity": ["opportunity_approval"],
        "hr.LeaveRequest": ["leave_approval"],
        # support.Ticket → falls back to "default" → ["generic_approval"]
    },

    "AUTO_START_WORKFLOWS": {
        "default": {
            "workflow_slug": "generic_approval",
            "auto_start": True,
        },
        "crm.Opportunity": {
            "workflow_slug": "opportunity_approval",
            "auto_start": True,
        },
    },

    "PERMISSIONS": {
        "REQUIRE_PERMISSION_TO_START": True,
        "REQUIRE_PERMISSION_TO_APPROVE": True,
    },
}

WORKFLOW_ACTIONS_CONFIG = {
    "default": [
        {
            "action_type": "after_approve",
            "function_path": "myapp.actions.send_generic_approval",
            "parameters": {"template": "approved"},
            "order": 1,
        },
    ],
    "crm.Opportunity": [
        {
            "action_type": "after_approve",
            "function_path": "crm.actions.opportunity_approved",
            "parameters": {"template": "opportunity_approved"},
            "order": 1,
        },
    ],
    "hr.LeaveRequest": [
        {
            "action_type": "after_approve",
            "function_path": "hr.actions.leave_approved",
            "parameters": {"template": "leave_approved"},
            "order": 1,
        },
    ],
}
```

---

## Backward Compatibility

This release is 100% backward compatible:

- Existing flat-list `WORKFLOW_ACTIONS_CONFIG` works unchanged
- Models without `"default"` fallback behave exactly as before
- All 360 existing tests pass without modification
- No migrations required

---

## Migration from v1.6.x

### Step 1: Update Package

```bash
pip install --upgrade django-dynamic-workflows==1.7.0
```

### Step 2: Add "default" Keys (Optional)

Add `"default"` keys to your existing configuration. Models not explicitly listed will automatically use the defaults.

### Step 3: Convert WORKFLOW_ACTIONS_CONFIG (Optional)

If you want per-model actions, convert from flat list to dict format. The flat list continues to work.

---

## Testing

- **395 tests** (360 existing + 35 new), 100% passing
- New tests cover: default fallback, model-keyed resolution, flat-list compat, action type filtering, DB priority, settings validation

---

## Files Changed

- `django_workflow_engine/settings.py` — New helpers and validation
- `django_workflow_engine/services.py` — Default fallback in workflow/auto-start resolution
- `django_workflow_engine/action_management.py` — `model_string` parameter support
- `django_workflow_engine/action_executor.py` — Auto-resolve model string from attachment
- `tests/test_default_key_config.py` — 35 new tests
- `README.md` — Updated documentation
- `pyproject.toml` — Version bump to 1.7.0
- `CHANGELOG.md` — v1.7.0 entry

---

**Version:** 1.7.0
**Release Date:** May 26, 2026
**Package:** django-dynamic-workflows
**License:** MIT
