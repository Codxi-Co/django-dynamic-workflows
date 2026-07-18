# Enhanced Role Selection Strategies Guide

## Overview

django-workflow-engine v1.6.0+ supports advanced role selection strategies from django-approval-workflow v0.8.6+. These strategies allow you to implement complex approval workflows like:

- **QUORUM**: N out of M users must approve (e.g., 2 out of 5 committee members)
- **MAJORITY**: More than 50% must approve (e.g., board decisions)
- **PERCENTAGE**: X% must approve (e.g., 66.67% for supermajority)
- **HIERARCHY_UP**: Escalate N levels up the management chain
- **HIERARCHY_CHAIN**: Complete management chain escalation
- **CONSENSUS**: All users must approve (original behavior)
- **ANYONE**: Any one user can approve (original behavior)

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Strategy Types](#strategy-types)
3. [Configuration](#configuration)
4. [Generic Role Users Discovery](#generic-role-users-discovery)
5. [Examples](#examples)
6. [Migration Guide](#migration-guide)
7. [API Reference](#api-reference)

---

## Quick Start

### 1. Run Migrations

```bash
python manage.py migrate django_workflow_engine
```

### 2. Use Enhanced Strategies in Stage Configuration

```python
from django_workflow_engine.enums import RoleSelectionStrategy

stage_info = {
    "name_en": "Budget Approval",
    "approvals": [
        {
            "approval_type": "role",
            "user_role": finance_role.id,
            "role_selection_strategy": RoleSelectionStrategy.QUORUM,
            "quorum_count": 2,  # 2 out of 5 must approve
            "quorum_total": 5,
        }
    ]
}
```

---

## Strategy Types

### Enhanced Strategies (Create Multiple Parallel Steps)

These strategies create multiple approval instances in parallel:

#### QUORUM

**Description**: N out of M users must approve

**Use Case**: Committee decisions, board approvals

**Configuration**:
```python
{
    "approval_type": "role",
    "user_role": committee_role.id,
    "role_selection_strategy": RoleSelectionStrategy.QUORUM,
    "quorum_count": 2,  # Required approvals
    "quorum_total": 5,  # Total users
}
```

**Result**: Creates 5 parallel approval instances, requires 2 approvals

#### MAJORITY

**Description**: More than 50% must approve

**Use Case**: Board decisions, democratic voting

**Configuration**:
```python
{
    "approval_type": "role",
    "user_role": board_role.id,
    "role_selection_strategy": RoleSelectionStrategy.MAJORITY,
}
```

**Result**: Automatically calculates required = (total_users // 2) + 1

#### PERCENTAGE

**Description**: X% must approve

**Use Case**: Supermajority requirements (e.g., 66.67%, 75%)

**Configuration**:
```python
{
    "approval_type": "role",
    "user_role": shareholder_role.id,
    "role_selection_strategy": RoleSelectionStrategy.PERCENTAGE,
    "percentage_required": 66.67,  # 2/3 supermajority
}
```

**Result**: Calculates required = int(total * percentage / 100) + 1

### Standard Strategies (Single Step)

These strategies create a single step with `assigned_role` - the approval-workflow package handles the logic:

#### CONSENSUS

**Description**: All users must approve sequentially

**Configuration**:
```python
{
    "approval_type": "role",
    "user_role": management_role.id,
    "role_selection_strategy": RoleSelectionStrategy.CONSENSUS,
}
```

#### ANYONE (Default)

**Description**: Any one user can approve

**Configuration**:
```python
{
    "approval_type": "role",
    "user_role": manager_role.id,
    "role_selection_strategy": RoleSelectionStrategy.ANYONE,
}
```

#### HIERARCHY_UP

**Description**: Escalate N levels up the management chain

**Configuration**:
```python
{
    "approval_type": "role",
    "user_role": manager_role.id,
    "role_selection_strategy": RoleSelectionStrategy.HIERARCHY_UP,
    "hierarchy_levels": 3,  # Escalate up to 3 levels
    "hierarchy_base_user": request.user.id,  # Start from this user
}
```

#### HIERARCHY_CHAIN

**Description**: Complete management chain escalation

**Configuration**:
```python
{
    "approval_type": "role",
    "user_role": manager_role.id,
    "role_selection_strategy": RoleSelectionStrategy.HIERARCHY_CHAIN,
}
```

---

## Configuration

### Stage Model Fields

The following fields have been added to the `Stage` model:

#### Quorum Strategy Fields

```python
class Stage(models.Model):
    quorum_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Number of approvals required for QUORUM strategy"
    )
    quorum_total = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total users for quorum calculation"
    )
    percentage_required = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Percentage required for PERCENTAGE strategy (e.g., 66.67)"
    )
```

#### Hierarchy Strategy Fields

```python
class Stage(models.Model):
    hierarchy_levels = models.PositiveIntegerField(
        default=1,
        help_text="Number of hierarchy levels to escalate"
    )
    hierarchy_base_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Base user for hierarchy calculation"
    )
```

#### SLA Management Fields

```python
class Stage(models.Model):
    due_date_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Hours until due date (relative to stage start)"
    )
    reminder_hours_before = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Send reminder X hours before due date"
    )
    escalation_on_timeout = models.BooleanField(
        default=False,
        help_text="Auto-escalate when timeout is reached"
    )
    timeout_action = models.CharField(
        max_length=20,
        choices=[
            ("escalate", "Escalate"),
            ("reject", "Auto Reject"),
            ("delegate", "Delegate"),
        ],
        default="escalate",
        help_text="Action when timeout is reached"
    )
    max_escalation_level = models.PositiveIntegerField(
        default=3,
        help_text="Maximum escalation level for SLA timeouts"
    )
```

#### Parallel Approval Fields

```python
class Stage(models.Model):
    parallel_group = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Group ID for parallel execution with other stages"
    )
    parallel_required = models.BooleanField(
        default=False,
        help_text="All stages in group must complete before next sequential stage"
    )
```

---

## Generic Role Users Discovery

### The Problem

Different projects have different role model structures:

- Direct ManyToMany: `role.users.all()`
- Django Group: `role.user_set.all()`
- UserProfile pattern: `role.userprofile_set.all()` → `user`
- Custom pattern: `role.employee_set.all()` → `profile.user`

### The Solution

The `get_users_from_role()` function in `utils.py` provides generic discovery:

#### Method 1: Custom Discovery Function (Highest Priority)

```python
# settings.py
WORKFLOW_ROLE_USERS_FUNCTION = 'myapp.workflow.get_users_from_role'

# myapp/workflow.py
def get_users_from_role(role):
    """Custom function to get users from a role.

    Example for: role → UserProfile → User
    """
    return [up.user for up in role.userprofile_set.all()]
```

#### Method 2: Direct `users` Attribute

```python
# Role model with direct ManyToManyField
class Role(models.Model):
    users = models.ManyToManyField(User)
```

#### Method 3: Django Group's `user_set`

```python
# Uses Django's built-in Group model
from django.contrib.auth.models import Group

role = Group.objects.get(name='Managers')
```

#### Method 4: UserProfile Pattern

```python
# Automatically detects: role.userprofile_set → user
class Role(models.Model):
    # UserProfile has FK to both Role and User
    pass
```

#### Method 5: Common Patterns

Automatically tries:
- `role.profile_set`
- `role.member_set`
- `role.employee_set`

### Implementation Example

For your project (role → UserProfile → User):

```python
# settings.py
WORKFLOW_ROLE_USERS_FUNCTION = 'myapp.workflow.get_role_users'

# myapp/workflow.py
from django.contrib.auth import get_user_model

User = get_user_model()

def get_role_users(role):
    """
    Get users from role.

    Project structure: Role → UserProfile → User
    """
    return [
        user_profile.user
        for user_profile in role.userprofile_set.all()
        if hasattr(user_profile, 'user') and user_profile.user
    ]
```

---

## Examples

### Example 1: Purchase Order Approval

**Requirement**: 2 out of 5 finance committee members must approve

```python
from approval_workflow.enums import RoleSelectionStrategy

# Create workflow
workflow = WorkFlow.objects.create(
    name_en="Purchase Order Approval",
    strategy=WorkflowStrategy.WORKFLOW_PIPELINE_STAGE
)

# Create stage with QUORUM strategy
stage = Stage.objects.create(
    name_en="Finance Committee Approval",
    pipeline=pipeline,
    order=1,
    stage_info={
        "approvals": [
            {
                "approval_type": "role",
                "user_role": finance_committee_role.id,
                "role_selection_strategy": RoleSelectionStrategy.QUORUM,
                "quorum_count": 2,
                "quorum_total": 5,
            }
        ]
    }
)
```

### Example 2: Board Decision Approval

**Requirement**: Majority of board members must approve

```python
stage = Stage.objects.create(
    name_en="Board Approval",
    pipeline=pipeline,
    order=1,
    stage_info={
        "approvals": [
            {
                "approval_type": "role",
                "user_role": board_role.id,
                "role_selection_strategy": RoleSelectionStrategy.MAJORITY,
            }
        ]
    }
)
```

### Example 3: Supermajority Approval

**Requirement**: 66.67% (2/3) of shareholders must approve

```python
stage = Stage.objects.create(
    name_en="Shareholder Approval",
    pipeline=pipeline,
    order=1,
    stage_info={
        "approvals": [
            {
                "approval_type": "role",
                "user_role": shareholder_role.id,
                "role_selection_strategy": RoleSelectionStrategy.PERCENTAGE,
                "percentage_required": 66.67,
            }
        ]
    }
)
```

### Example 4: Management Escalation

**Requirement**: Escalate up to 3 management levels

```python
stage = Stage.objects.create(
    name_en="Management Approval",
    pipeline=pipeline,
    order=1,
    stage_info={
        "approvals": [
            {
                "approval_type": "role",
                "user_role": manager_role.id,
                "role_selection_strategy": RoleSelectionStrategy.HIERARCHY_UP,
                "hierarchy_levels": 3,
                "hierarchy_base_user": request.user.id,
            }
        ]
    }
)
```

---

## Migration Guide

### For Existing Projects

#### Step 1: Update Dependencies

```bash
pip install --upgrade django-workflow-engine>=1.6.0
pip install --upgrade django-approval-workflow>=0.8.6
```

#### Step 2: Run Migrations

```bash
python manage.py migrate django_workflow_engine
```

#### Step 3: Configure Role Users Discovery (If Needed)

If your role model uses a custom structure:

```python
# settings.py
WORKFLOW_ROLE_USERS_FUNCTION = 'myapp.workflow.get_role_users'
```

#### Step 4: Update Stage Configurations (Optional)

Existing stages continue to work with ANYONE strategy (default).

To use enhanced strategies, update stage configurations:

```python
# Before (still works)
stage_info = {
    "approvals": [
        {
            "approval_type": "role",
            "user_role": manager_role.id,
        }
    ]
}

# After (new options available)
stage_info = {
    "approvals": [
        {
            "approval_type": "role",
            "user_role": committee_role.id,
            "role_selection_strategy": RoleSelectionStrategy.QUORUM,
            "quorum_count": 2,
            "quorum_total": 5,
        }
    ]
}
```

---

## API Reference

### get_users_from_role(role)

Get users from a role using generic discovery mechanism.

**Parameters**:
- `role`: The role object (Group, custom Role, etc.)

**Returns**:
- `List[User]`: List of User objects

**Example**:
```python
from django_workflow_engine.utils import get_users_from_role

users = get_users_from_role(role)
print(f"Found {len(users)} users")
```

### build_approval_steps(stage, created_by_user, start_step=1)

Build approval steps for a stage with enhanced strategy support.

**Parameters**:
- `stage`: The Stage instance
- `created_by_user`: The user who created the workflow item
- `start_step`: The starting step number (default: 1)

**Returns**:
- `List[Dict]`: List of approval step configurations

**Example**:
```python
from django_workflow_engine.utils import build_approval_steps

steps = build_approval_steps(stage, user)
print(f"Created {len(steps)} approval steps")
```

---

## Troubleshooting

### Issue: "No users found for role X"

**Solution**: Configure `WORKFLOW_ROLE_USERS_FUNCTION` in settings:

```python
WORKFLOW_ROLE_USERS_FUNCTION = 'myapp.workflow.get_role_users'
```

### Issue: QUORUM strategy not working

**Solution**: Ensure both `quorum_count` and `quorum_total` are set:

```python
{
    "role_selection_strategy": RoleSelectionStrategy.QUORUM,
    "quorum_count": 2,
    "quorum_total": 5,
}
```

### Issue: PERCENTAGE strategy defaults to MAJORITY

**Solution**: Ensure `percentage_required` is set:

```python
{
    "role_selection_strategy": RoleSelectionStrategy.PERCENTAGE,
    "percentage_required": 66.67,
}
```

---

## Performance Considerations

### Enhanced Strategies (QUORUM, MAJORITY, PERCENTAGE)

These create multiple approval instances in parallel:
- More database queries
- Higher memory usage
- Better for small to medium role sizes (< 50 users)

### Standard Strategies (CONSENSUS, ANYONE, HIERARCHY)

These create single approval instances:
- Fewer database queries
- Lower memory usage
- Better for large role sizes

---

## Best Practices

1. **Use QUORUM for small groups** (committees, boards)
2. **Use MAJORITY for democratic decisions** (voting)
3. **Use PERCENTAGE for supermajorities** (critical decisions)
4. **Use HIERARCHY for management chains** (escalation)
5. **Use CONSENSUS for critical approvals** (all must agree)
6. **Use ANYONE for simple approvals** (any manager can approve)

---

## Changelog

### v1.6.0 (January 14, 2026)

**Added**:
- QUORUM, MAJORITY, PERCENTAGE strategy support
- HIERARCHY escalation fields
- SLA management fields
- Parallel approval fields
- Generic role users discovery function

**Changed**:
- Enhanced `build_approval_steps()` to support new strategies
- Added `get_users_from_role()` utility function

**Migration**: `0007_add_enhanced_role_strategies.py`

---

## Support

For questions or issues:
1. Check this guide
2. Review test cases in `tests/test_services.py`
3. Open an issue on GitHub

---

**Version**: 1.6.0+
**Last Updated**: January 14, 2026
**Package**: django-workflow-engine
**Dependency**: django-approval-workflow v0.8.6+
