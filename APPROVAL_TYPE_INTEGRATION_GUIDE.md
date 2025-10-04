# Approval Type Integration Guide

## Overview

The `django-workflow-engine` package now supports approval behavior types from `django-approval-workflow`. This allows you to control HOW approval steps behave, in addition to WHO approves.

## Two Types of Approval Configuration

### 1. `approval_type` (WHO approves)
Controls who can approve the step:
- `self-approved` - Creator approves their own work
- `role` - Any user with a specific role
- `user` - Specific user
- `team_head` - Team leader
- `department_head` - Department leader

### 2. `step_approval_type` (HOW it behaves) **NEW**
Controls the behavior and validation of the approval step:
- `approve` - Standard approval (default)
- `submit` - Requires form data submission
- `check_in_verify` - Two-phase check-in/verify flow
- `move` - Simple transfer without forms

## Approval Step Types

### APPROVE (Default)
**Behavior:** Standard approval step with optional form validation

**Use When:** Regular approval workflows

**Requirements:**
- Form: Optional
- form_data: Only required if form has a schema

**Example:**
```json
{
  "approval_type": "user",
  "approval_user": 123,
  "step_approval_type": "approve",
  "required_form": 456
}
```

---

### SUBMIT
**Behavior:** Mandatory data submission step

**Use When:** Initial submissions, data collection, form-based workflows

**Requirements:**
- Form: **Required** ✅
- form_data: **Required** ✅

**Validation:**
- Will reject if no form is attached
- Will reject if no form_data is provided during approval

**Example:**
```json
{
  "approval_type": "self-approved",
  "step_approval_type": "submit",
  "required_form": 789
}
```

**API Usage:**
```python
# When approving a SUBMIT step
{
  "action": "approved",
  "form_data": {
    "amount": 500,
    "category": "travel",
    "description": "Business trip"
  }
}
```

---

### CHECK_IN_VERIFY
**Behavior:** Two-phase verification flow (check-in → verify)

**Use When:** Quality control, physical verification, compliance checks

**Requirements:**
- Form: Optional
- form_data: Optional

**How It Works:**
1. **Phase 1 (Check-in):** User first checks in
   - Returns same approval instance
   - Stays on current step
   - Stores check-in metadata in `extra_fields`

2. **Phase 2 (Verify):** User then approves
   - Moves to next step
   - Workflow progresses

**Example:**
```json
{
  "approval_type": "role",
  "user_role": 10,
  "role_selection_strategy": "anyone",
  "step_approval_type": "check_in_verify"
}
```

**API Usage:**
```python
# First call - Check in
POST /api/opportunities/123/approve/
{
  "action": "approved"
}
# Response: Same step, extra_fields contains {"checked_in": true, ...}

# Second call - Verify
POST /api/opportunities/123/approve/
{
  "action": "approved",
  "comment": "Verified and approved"
}
# Response: Moves to next step
```

---

### MOVE
**Behavior:** Simple transfer/routing without forms

**Use When:** Status changes, document routing, workflow transitions

**Requirements:**
- Form: **Not allowed** ❌
- form_data: **Not allowed** ❌

**Validation:**
- Will reject if any form is attached
- Will reject if form_data is provided during approval

**Example:**
```json
{
  "approval_type": "user",
  "approval_user": 456,
  "step_approval_type": "move"
}
```

---

## Complete Stage Configuration Example

```json
{
  "name_en": "Expense Approval Stage",
  "name_ar": "مرحلة الموافقة على المصروفات",
  "order": 1,
  "stage_info": {
    "color": "#4CAF50",
    "approvals": [
      {
        "approval_type": "self-approved",
        "step_approval_type": "submit",
        "required_form": 100
      },
      {
        "approval_type": "role",
        "user_role": 5,
        "role_selection_strategy": "anyone",
        "step_approval_type": "approve",
        "required_form": 101
      },
      {
        "approval_type": "user",
        "approval_user": 789,
        "step_approval_type": "check_in_verify"
      },
      {
        "approval_type": "user",
        "approval_user": 999,
        "step_approval_type": "move"
      }
    ]
  }
}
```

## Validation Rules

### API Level (Serializer)
✅ Case-insensitive: `"SUBMIT"`, `"submit"`, `"Submit"` all work
✅ Validates against allowed types
✅ SUBMIT requires `required_form`
✅ MOVE rejects `required_form`

### Service Level (utils.py)
✅ Defaults to `APPROVE` if not specified
✅ Validates type before passing to approval_workflow
✅ Logs warnings for invalid types

### Model Level (Stage._validate_approval_config)
✅ Validates during stage configuration
✅ Prevents invalid configurations from being saved

## Migration from Old Configuration

If you have existing stages **without** `step_approval_type`:
- ✅ They will default to `approve` behavior
- ✅ No migration needed
- ✅ Fully backward compatible

To add the new field to existing stages:
```python
# Update existing stage
PATCH /api/workflows/1/pipelines/2/stages/3/
{
  "stage_info": {
    "approvals": [
      {
        "approval_type": "user",
        "approval_user": 123,
        "step_approval_type": "submit",  # Add this
        "required_form": 456
      }
    ]
  }
}
```

## Error Messages

### SUBMIT without form:
```
"SUBMIT step_approval_type requires a required_form to be specified"
```

### MOVE with form:
```
"MOVE step_approval_type cannot have a required_form"
```

### Invalid type:
```
"Invalid step_approval_type: xyz. Must be one of: approve, submit, check_in_verify, move"
```

## Testing Your Implementation

### Test SUBMIT Type
```bash
# Create stage with SUBMIT
POST /api/stages/
{
  "stage_info": {
    "approvals": [{
      "approval_type": "self-approved",
      "step_approval_type": "submit",
      "required_form": 123
    }]
  }
}

# Try to approve without form_data (should fail)
POST /api/opportunities/456/approve/
{
  "action": "approved"
}

# Approve with form_data (should succeed)
POST /api/opportunities/456/approve/
{
  "action": "approved",
  "form_data": {"field": "value"}
}
```

### Test MOVE Type
```bash
# Try to create MOVE with form (should fail)
POST /api/stages/
{
  "stage_info": {
    "approvals": [{
      "approval_type": "user",
      "approval_user": 123,
      "step_approval_type": "move",
      "required_form": 456  # This will be rejected
    }]
  }
}
```

### Test CHECK_IN_VERIFY
```bash
# First approval (check-in)
POST /api/opportunities/789/approve/
{
  "action": "approved"
}
# Should return same step

# Second approval (verify)
POST /api/opportunities/789/approve/
{
  "action": "approved"
}
# Should move to next step
```

## Changes Made to django-approval-workflow

### Fixed SUBMIT Validation Gap
**Before:** SUBMIT only required form_data if form had a schema
**After:** SUBMIT always requires form_data when form is attached

**File:** `approval_workflow/services.py:357`

```python
# OLD (had a bug):
if form_schema and not form_data:
    raise ValueError("This step requires form_data (SUBMIT type).")

# NEW (fixed):
if not form_data:
    raise ValueError("This step requires form_data (SUBMIT type).")
```

## Support

For questions or issues:
1. Check the test files in `django-approval-workflow/approval_workflow/tests/test_approval_types.py`
2. Review examples in CRM integration
3. Contact the development team

---

**Version:** 1.0
**Last Updated:** 2025-10-04
**Compatible with:**
- django-approval-workflow >= 1.2.1
- django-workflow-engine >= latest
