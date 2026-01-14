# Django Approval Workflow → Django Workflow Engine Integration Analysis

## 📋 Executive Summary

This document analyzes the key changes in `django-approval-workflow` package (v0.8.4 - v0.8.6) and provides a roadmap for implementing these features in `django-workflow-engine`.

**Last Updated:** January 13, 2026
**Approval Workflow Version:** v0.8.6
**Workflow Engine Version:** v1.5.5+

---

## 🎯 Key Features to Implement

### Priority Level 1: Critical Features

1. **Handler Discovery Enhancement** (v0.8.5)
2. **Enhanced Role Selection Strategies** (v0.8.4)
3. **Translation Support** (i18n)

### Priority Level 2: Important Features

4. **Enhanced Structured Logging**
5. **SLA Management**
6. **Parallel Approval Support**

---

## 1. Handler Discovery Enhancement ⭐ HIGH PRIORITY

### What's New in Approval Workflow v0.8.5

**New Setting:** `APPROVAL_HANDLER_DISCOVERY_FUNCTION`

```python
# settings.py
APPROVAL_HANDLER_DISCOVERY_FUNCTION = 'myapp.handlers.get_handler_for_instance'
```

**Handler Resolution Order:**
1. **Custom discovery function** (new!)
2. Settings-based `APPROVAL_HANDLERS` list
3. Auto-discovery (fallback)

### Implementation for Workflow Engine

**Current State:**
- ✅ Already has `get_handler_for_instance()` in handlers.py
- ❌ Missing custom discovery function support

**Required Changes:**

```python
# django_workflow_engine/handlers.py

def get_handler_for_instance(instance: "ApprovalInstance") -> BaseApprovalHandler:
    """
    Dynamically resolve the custom approval handler for the instance's model.

    Handler Resolution Order:
        1. Custom discovery function (APPROVAL_HANDLER_DISCOVERY_FUNCTION)
        2. Settings-based list (APPROVAL_HANDLERS)
        3. Auto-discovery fallback
    """
    from django.conf import settings

    # NEW: Try custom handler discovery function first
    discovery_function_path = getattr(
        settings, "WORKFLOW_HANDLER_DISCOVERY_FUNCTION", None
    )
    if discovery_function_path:
        try:
            module_path, function_name = discovery_function_path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[function_name])
            discovery_function = getattr(module, function_name)
            handler = discovery_function(instance)
            if handler:
                logger.debug(
                    f"Handler resolved via custom discovery function - "
                    f"Workflow: {instance.flow.workflow.id}, "
                    f"Handler: {handler.__class__.__name__}"
                )
                return handler
        except (ImportError, AttributeError, ValueError) as e:
            logger.warning(
                f"Failed to use custom handler discovery function - "
                f"Path: {discovery_function_path}, Error: {e}"
            )

    # Rest of existing logic...
    # Continue with settings-based and auto-discovery
```

**Settings Documentation:**

```python
# Option 1: Custom discovery function
WORKFLOW_HANDLER_DISCOVERY_FUNCTION = 'myapp.workflow_handlers.get_handler'

# Option 2: Handler list (existing)
WORKFLOW_APPROVAL_HANDLERS = [
    'myapp.handlers.PurchaseOrderApprovalHandler',
    'myapp.handlers.LeaveRequestApprovalHandler',
]

# Option 3: Auto-discovery (existing, will be used as fallback)
# For model 'PurchaseOrder' in app 'myapp', looks for:
# myapp.approval.PurchaseOrderApprovalHandler
```

---

## 2. Enhanced Role Selection Strategies ⭐ HIGH PRIORITY

### What's New in Approval Workflow v0.8.4

**New Strategies:**

| Strategy | Description | Use Case |
|----------|-------------|----------|
| `QUORUM` | N out of M users must approve | Committee decisions (2/5) |
| `MAJORITY` | >50% must approve | Board decisions |
| `PERCENTAGE` | X% must approve | Flexible requirements |
| `HIERARCHY_UP` | Escalate N levels up | Management chain |
| `HIERARCHY_CHAIN` | Complete chain | Full hierarchy |

### Implementation for Workflow Engine

**Current State:**
- ✅ Has `RoleSelectionStrategy` enum in workflow-engine (uses approval_workflow's)
- ❌ Stage models need to support quorum/hierarchy fields

**Required Changes:**

#### Step 1: Add Fields to Stage Model

```python
# django_workflow_engine/models.py

class Stage(CompanyBaseWithNamedModelWithClone):
    # ... existing fields ...

    # NEW: Quorum Strategy Fields
    quorum_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Number of approvals required for QUORUM strategy")
    )
    quorum_total = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Total users for quorum calculation")
    )
    percentage_required = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Percentage required for PERCENTAGE strategy (e.g., 66.67)")
    )

    # NEW: Hierarchy Strategy Fields
    hierarchy_levels = models.PositiveIntegerField(
        default=1,
        help_text=_("Number of hierarchy levels to escalate")
    )
    hierarchy_base_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=_("Base user for hierarchy calculation")
    )
```

#### Step 2: Update Approval Step Building

```python
# django_workflow_engine/utils.py

def build_approval_steps(stage, approval_user, start_step=1):
    """
    Build approval steps for a stage, supporting enhanced role strategies.
    """
    from .choices import RoleSelectionStrategy

    role_selection_strategy = stage.approval_type.role_selection_strategy if stage.approval_type else None

    if role_selection_strategy == RoleSelectionStrategy.QUORUM:
        return _build_quorum_steps(stage, approval_user, start_step)
    elif role_selection_strategy == RoleSelectionStrategy.MAJORITY:
        return _build_majority_steps(stage, approval_user, start_step)
    elif role_selection_strategy == RoleSelectionStrategy.PERCENTAGE:
        return _build_percentage_steps(stage, approval_user, start_step)
    elif role_selection_strategy in [RoleSelectionStrategy.HIERARCHY_UP,
                                      RoleSelectionStrategy.HIERARCHY_CHAIN]:
        return _build_hierarchy_steps(stage, approval_user, start_step)
    else:
        # Original logic for ANYONE, CONSENSUS, ROUND_ROBIN
        return _build_standard_steps(stage, approval_user, start_step)
```

#### Step 3: Implement Strategy Builders

```python
def _build_quorum_steps(stage, approval_user, start_step):
    """Build steps for QUORUM strategy."""
    from approval_workflow.models import Role

    role = stage.approval_type.approval_role if stage.approval_type else None
    if not role:
        return []

    quorum_count = stage.quorum_count or 1
    quorum_total = stage.quorum_total or role.users.count()

    # Get all role users and create instances
    users = role.users.all()[:quorum_total]

    steps = []
    for i, user in enumerate(users[:quorum_total], start_step):
        steps.append({
            "step": i,
            "assigned_to": user,
            "approval_type": "approve",
            "role": role,
            "extra_fields": {
                "quorum_count": quorum_count,
                "quorum_total": quorum_total,
                "parallel_group": f"quorum_{stage.id}",
            }
        })

    return steps


def _build_majority_steps(stage, approval_user, start_step):
    """Build steps for MAJORITY strategy (>50%)."""
    from approval_workflow.models import Role

    role = stage.approval_type.approval_role if stage.approval_type else None
    if not role:
        return []

    users = list(role.users.all())
    total = len(users)
    required = (total // 2) + 1  # More than 50%

    steps = []
    for i, user in enumerate(users, start_step):
        steps.append({
            "step": i,
            "assigned_to": user,
            "approval_type": "approve",
            "role": role,
            "extra_fields": {
                "quorum_count": required,
                "quorum_total": total,
                "parallel_group": f"majority_{stage.id}",
            }
        })

    return steps


def _build_percentage_steps(stage, approval_user, start_step):
    """Build steps for PERCENTAGE strategy."""
    from approval_workflow.models import Role

    role = stage.approval_type.approval_role if stage.approval_type else None
    if not role or not stage.percentage_required:
        return []

    users = list(role.users.all())
    total = len(users)
    required = int(total * stage.percentage_required / 100) + 1

    steps = []
    for i, user in enumerate(users, start_step):
        steps.append({
            "step": i,
            "assigned_to": user,
            "approval_type": "approve",
            "role": role,
            "extra_fields": {
                "quorum_count": required,
                "quorum_total": total,
                "parallel_group": f"percentage_{stage.id}",
            }
        })

    return steps


def _build_hierarchy_steps(stage, approval_user, start_step):
    """Build steps for HIERARCHY_UP or HIERARCHY_CHAIN strategies."""
    from approval_workflow.models import Role

    role = stage.approval_type.approval_role if stage.approval_type else None
    if not role:
        return []

    base_user = stage.hierarchy_base_user or approval_user
    levels = stage.hierarchy_levels

    # Get users at each hierarchy level
    steps = []
    for level in range(1, levels + 1):
        # Get managers at this level
        managers_at_level = _get_managers_at_level(base_user, role, level)

        for manager in managers_at_level:
            steps.append({
                "step": start_step + level - 1,
                "assigned_to": manager,
                "approval_type": "approve",
                "role": role,
                "extra_fields": {
                    "hierarchy_level": level,
                    "hierarchy_base_user_id": base_user.id,
                }
            })

    return steps
```

---

## 3. Enhanced Structured Logging

### What's New

**Emoji-based structured logs:**

```
[APPROVAL_WORKFLOW] ✨ NEW FLOW CREATED | Flow ID: 123
[APPROVAL_WORKFLOW] 🎯 ACTIVATING ROLE-BASED STEP | Strategy: hierarchy_up
[APPROVAL_WORKFLOW] ✅ QUORUM REACHED | Approvals: 2/2
[APPROVAL_WORKFLOW] 📊 QUORUM PROGRESS | Progress: 1/2
```

### Implementation

```python
# django_workflow_engine/logging_utils.py

import logging
from typing import Any, Dict

# Event emojis
LOG_EMOJIS = {
    "flow_created": "✨",
    "step_activated": "🎯",
    "step_approved": "✅",
    "step_rejected": "❌",
    "quorum_reached": "✅",
    "quorum_progress": "📊",
    "hierarchy_escalate": "📈",
    "workflow_completed": "🎉",
    "error": "⚠️",
}

def log_workflow_event(event_type: str, **context):
    """Log workflow event with emoji and structured format."""
    emoji = LOG_EMOJIS.get(event_type, "📌")

    # Format context
    context_str = " | ".join([f"{k}: {v}" for k, v in context.items()])

    logger.info(f"[WORKFLOW_ENGINE] {emoji} {event_type.upper()} | {context_str}")
```

---

## 4. Translation Support (i18n) ⭐ HIGH PRIORITY

### What's New

**Complete Arabic translations included:**

| English | Arabic |
|---------|---------|
| "Approval Flow" | "مسار الموافقة" |
| "Anyone with role can approve" | "أي شخص لديه الدور يمكنه الموافقة" |
| "Require N out of M users" | "يتطلب موافقة N من أصل M مستخدمين" |

### Implementation

**Status:** ✅ Already implemented in workflow-engine!
- ✅ Created `translation_utils.py`
- ✅ Created `locale/ar/LC_MESSAGES/django.po`
- ✅ Bilingual logging support
- ✅ User language detection

**Missing:** None! This is already complete.

---

## 5. SLA Management

### What's New

**New Model Fields:**

```python
# ApprovalInstance model (approval-workflow)
due_date = models.DateTimeField(null=True, blank=True)
reminder_sent = models.BooleanField(default=False)
escalation_on_timeout = models.BooleanField(default=False)
timeout_action = models.CharField(...)  # escalate, delegate, auto_approve, reject
escalation_level = models.PositiveIntegerField(default=0)
max_escalation_level = models.PositiveIntegerField(default=3)
```

### Implementation for Workflow Engine

**Option 1:** Add to Stage model (recommended)
```python
class Stage(CompanyBaseWithNamedModelWithClone):
    # SLA Fields
    due_date_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Hours until due date (relative to stage start)")
    )
    reminder_hours_before = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Send reminder X hours before due date")
    )
    escalation_on_timeout = models.BooleanField(
        default=False,
        help_text=_("Auto-escalate when timeout is reached")
    )
    timeout_action = models.CharField(
        max_length=20,
        choices=[("escalate", "Escalate"), ("reject", "Auto Reject")],
        default="escalate",
        help_text=_("Action when timeout is reached")
    )
```

**Option 2:** Add to WorkflowAttachment
```python
class WorkflowAttachment(BaseModel):
    # Per-attachment SLA tracking
    stage_due_date = models.DateTimeField(null=True, blank=True)
    stage_reminder_sent = models.BooleanField(default=False)
    stage_escalation_level = models.PositiveIntegerField(default=0)
```

---

## 6. Parallel Approval Support

### What's New

```python
# Parallel approval tracks
{
    "step": 1,
    "assigned_to": finance_manager,
    "parallel_group": "pre_approval",  # Same group = runs in parallel
    "parallel_required": True,          # Must complete before step 3
}
{
    "step": 2,
    "assigned_to": legal_counsel,
    "parallel_group": "pre_approval",  # Same group = parallel
    "parallel_required": True,          # Must complete
}
# Step 3 waits for both steps 1 and 2 to complete
```

### Implementation

**Add to Stage model:**
```python
class Stage(CompanyBaseWithNamedModelWithClone):
    parallel_group = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text=_("Group ID for parallel execution with other stages")
    )
    parallel_required = models.BooleanField(
        default=False,
        help_text=_("All stages in group must complete before next sequential stage")
    )
```

---

## 📊 Implementation Priority Matrix

| Feature | Priority | Complexity | Impact | Status |
|---------|----------|------------|--------|--------|
| Handler Discovery | 🔴 High | Low | High | ⏳ Pending |
| Role Strategies | 🔴 High | High | High | ⏳ Pending |
| Translation | 🟢 Done | - | High | ✅ Complete |
| Enhanced Logging | 🟡 Medium | Low | Medium | ⏳ Pending |
| SLA Management | 🟡 Medium | Medium | Medium | ⏳ Pending |
| Parallel Approvals | 🟡 Medium | Medium | Low | ⏳ Pending |

---

## 🚀 Implementation Roadmap

### Phase 1: Critical Features (Week 1)

1. ✅ **Handler Discovery Enhancement**
   - Add `WORKFLOW_HANDLER_DISCOVERY_FUNCTION` support
   - Update `get_handler_for_instance()`
   - Add documentation

2. ✅ **Enhanced Role Strategies**
   - Add model fields (quorum, hierarchy, etc.)
   - Implement strategy builders
   - Add tests

### Phase 2: Quality Improvements (Week 2)

3. ✅ **Enhanced Structured Logging**
   - Add emoji-based logging
   - Implement structured format
   - Update all log statements

4. ✅ **SLA Management**
   - Add SLA fields to models
   - Implement due date tracking
   - Add escalation logic

### Phase 3: Advanced Features (Week 3)

5. ✅ **Parallel Approval Support**
   - Add parallel_group fields
   - Implement parallel execution logic
   - Add tests

6. ✅ **Documentation & Examples**
   - Update README
   - Add migration guide
   - Create examples

---

## 📝 Migration Guide for Existing Projects

### Step 1: Update Dependencies

```bash
# Update approval-workflow to v0.8.6+
pip install django-approval-workflow>=0.8.6

# Update workflow-engine (after implementing changes)
pip install django-workflow-engine>=1.6.0
```

### Step 2: Run Migrations

```bash
python manage.py migrate django_workflow_engine
```

### Step 3: Update Handler Configuration (Optional)

```python
# Before
WORKFLOW_APPROVAL_HANDLERS = [
    'myapp.handlers.POApprovalHandler',
]

# After (new option)
WORKFLOW_HANDLER_DISCOVERY_FUNCTION = 'myapp.workflow.get_handler'
```

### Step 4: Use New Role Strategies

```python
# Before
stage_info = {
    "approvals": [
        {"approval_type": "role", "role_selection_strategy": "consensus"}
    ]
}

# After (new options)
stage_info = {
    "approvals": [
        {
            "approval_type": "role",
            "role_selection_strategy": "quorum",
            "quorum_count": 2,
            "quorum_total": 5
        }
    ]
}
```

---

## ✅ Testing Checklist

- [ ] Handler discovery function works
- [ ] QUORUM strategy creates N instances
- [ ] MAJORITY strategy calculates correctly
- [ ] PERCENTAGE strategy works
- [ ] HIERARCHY_UP escalates correctly
- [ ] Enhanced logs show emojis
- [ ] Translations work in Arabic
- [ ] SLA due dates are tracked
- [ ] Parallel approvals execute correctly
- [ ] All existing tests still pass

---

## 📖 Additional Resources

### Approval Workflow Documentation
- [ENHANCED_FEATURES.md](/path/to/approval-workflow/ENHANCED_FEATURES.md)
- [CHANGELOG.md](/path/to/approval-workflow/CHANGELOG.md)

### Workflow Engine Documentation
- [README.md](/path/to/workflow-engine/README.md)
- [MIGRATION_GUIDE.md](/path/to/workflow-engine/MIGRATION_GUIDE.md)

### API Reference
- `ApprovalInstance` model (approval-workflow)
- `Stage` model (workflow-engine)
- `start_flow()` function
- `advance_flow()` function

---

**Version:** 1.0
**Last Updated:** January 13, 2026
**Author:** AI Assistant (Claude)
