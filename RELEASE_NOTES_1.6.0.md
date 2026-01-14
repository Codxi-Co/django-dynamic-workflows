# Release Notes - v1.6.0

**Release Date:** January 14, 2026
**Status:** ✅ Production Ready
**Tests:** 356/356 Passing (100%)
**Minimum Python:** 3.10+
**Minimum Django:** 5.2+
**Minimum django-approval-workflow:** 0.9.0+

---

## 🎉 Major Release: Enhanced Role Selection Strategies

This release adds powerful new role selection strategies from django-approval-workflow v0.9.0+, enabling complex approval workflows like committee decisions, board voting, and management escalation.

---

## ✨ What's New

### 1. Enhanced Role Selection Strategies

Added support for advanced role-based approval strategies:

#### QUORUM Strategy
- **N out of M users must approve**
- Use case: Committee decisions, board approvals
- Configuration: `quorum_count`, `quorum_total`
- Creates parallel approval instances

```python
{
    "approval_type": "role",
    "user_role": committee_role.id,
    "role_selection_strategy": RoleSelectionStrategy.QUORUM,
    "quorum_count": 2,
    "quorum_total": 5,
}
```

#### MAJORITY Strategy
- **More than 50% must approve**
- Use case: Democratic voting, board decisions
- Auto-calculates required approvals
- Creates parallel approval instances

```python
{
    "approval_type": "role",
    "user_role": board_role.id,
    "role_selection_strategy": RoleSelectionStrategy.MAJORITY,
}
```

#### PERCENTAGE Strategy
- **X% must approve**
- Use case: Supermajority requirements (66.67%, 75%)
- Configuration: `percentage_required`
- Creates parallel approval instances

```python
{
    "approval_type": "role",
    "user_role": shareholder_role.id,
    "role_selection_strategy": RoleSelectionStrategy.PERCENTAGE,
    "percentage_required": 66.67,
}
```

#### HIERARCHY Strategies
- **HIERARCHY_UP**: Escalate N levels up
- **HIERARCHY_CHAIN**: Complete management chain
- Use case: Management escalation workflows
- Configuration: `hierarchy_levels`, `hierarchy_base_user`

```python
{
    "approval_type": "role",
    "user_role": manager_role.id,
    "role_selection_strategy": RoleSelectionStrategy.HIERARCHY_UP,
    "hierarchy_levels": 3,
    "hierarchy_base_user": request.user.id,
}
```

### 2. Generic Role Users Discovery

New `get_users_from_role()` function supports multiple role model structures:

**Features:**
- ✅ Custom discovery function via `WORKFLOW_ROLE_USERS_FUNCTION` setting
- ✅ Automatic detection of common patterns (`users`, `user_set`, `userprofile_set`)
- ✅ Graceful fallback with detailed logging
- ✅ Works with any role model structure

**Configuration:**
```python
# settings.py
WORKFLOW_ROLE_USERS_FUNCTION = 'myapp.workflow.get_role_users'

# myapp/workflow.py
def get_role_users(role):
    """Custom function for: role → UserProfile → User"""
    return [up.user for up in role.userprofile_set.all()]
```

### 3. Stage Model Enhancements

Added 12 new fields to the `Stage` model:

**Quorum Strategy Fields:**
- `quorum_count` - Number of approvals required
- `quorum_total` - Total users for quorum calculation
- `percentage_required` - Percentage for PERCENTAGE strategy

**Hierarchy Strategy Fields:**
- `hierarchy_levels` - Number of levels to escalate
- `hierarchy_base_user` - Base user for hierarchy calculation

**SLA Management Fields:**
- `due_date_hours` - Hours until due date
- `reminder_hours_before` - Send reminder before due date
- `escalation_on_timeout` - Auto-escalate on timeout
- `timeout_action` - Action on timeout (escalate/reject/delegate)
- `max_escalation_level` - Maximum escalation level

**Parallel Approval Fields:**
- `parallel_group` - Group ID for parallel execution
- `parallel_required` - All stages in group must complete

---

## 🔧 Breaking Changes

**None!** This release is 100% backward compatible.

All existing workflows continue to work without modification.

---

## 🔄 Migrating from v1.5.x

### Step 1: Update Dependencies

```bash
pip install --upgrade django-dynamic-workflows==1.6.0
pip install --upgrade django-approval-workflow>=0.9.0
```

### Step 2: Run Migrations

```bash
python manage.py migrate django_workflow_engine
```

**Migration:** `0007_add_enhanced_role_strategies.py`

### Step 3: Configure Role Discovery (Optional)

If your role model uses a custom structure (not Django Group or direct ManyToMany):

```python
# settings.py
WORKFLOW_ROLE_USERS_FUNCTION = 'myapp.workflow.get_role_users'
```

### Step 4: Use Enhanced Strategies (Optional)

Existing workflows continue to work. Enhanced strategies are opt-in:

```python
# Before (still works)
stage_info = {
    "approvals": [
        {"approval_type": "role", "user_role": role.id}
    ]
}

# After (new options)
stage_info = {
    "approvals": [
        {
            "approval_type": "role",
            "user_role": role.id,
            "role_selection_strategy": RoleSelectionStrategy.QUORUM,
            "quorum_count": 2,
            "quorum_total": 5,
        }
    ]
}
```

---

## 📦 Installation

### Standard Installation

```bash
pip install django-dynamic-workflows==1.6.0
```

### With API Support

```bash
pip install "django-dynamic-workflows[api]==1.6.0"
```

### Development Installation

```bash
pip install "django-dynamic-workflows[dev]==1.6.0"
```

---

## 📝 Configuration

### Minimal Configuration

```python
# settings.py
INSTALLED_APPS = [
    # ...
    'django_workflow_engine',
    'approval_workflow',
]
```

### Custom Role Discovery (Optional)

```python
# settings.py
WORKFLOW_ROLE_USERS_FUNCTION = 'myapp.workflow.get_role_users'
```

### Custom Handler Discovery (Optional)

```python
# settings.py
WORKFLOW_HANDLER_DISCOVERY_FUNCTION = 'myapp.handlers.get_handler'
```

---

## 🚀 Quick Start

### Example 1: Committee Approval

```python
from approval_workflow.enums import RoleSelectionStrategy

# 2 out of 5 finance committee members must approve
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

### Example 2: Board Decision

```python
# Majority of board members must approve
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

### Example 3: Supermajority

```python
# 66.67% (2/3) of shareholders must approve
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

---

## 📚 Documentation

### New Documentation

1. **ENHANCED_ROLE_STRATEGIES_GUIDE.md**
   - Comprehensive guide for enhanced strategies
   - Quick start examples
   - Configuration reference
   - Troubleshooting

2. **PHASE_2_COMPLETE.md**
   - Implementation summary
   - Feature comparison
   - Migration guide

### Updated Documentation

- **README.md** - Updated with new features
- **APPROVAL_WORKFLOW_INTEGRATION_ANALYSIS.md** - Integration analysis
- **INTEGRATION_COMPLETE.md** - Phase 1.5 summary

---

## 🐛 Bug Fixes

- Fixed role users discovery in recipient_resolver.py to use generic `get_users_from_role()` function
- Improved error handling for custom role discovery functions
- Enhanced logging for role selection strategy activation

---

## ⚡ Performance

- No performance degradation
- Enhanced strategies (QUORUM, MAJORITY, PERCENTAGE) create parallel approval instances
- Standard strategies (CONSENSUS, ANYONE, HIERARCHY) maintain existing performance

---

## 🧪 Testing

- **Test Coverage:** 356 tests, 100% passing
- **Test Framework:** pytest
- **Django Versions:** 4.2, 5.0, 5.1, 5.2, 6.0
- **Python Versions:** 3.10, 3.11, 3.12, 3.13

---

## 🔮 Deprecations

**None.** All features from v1.5.x remain fully supported.

---

## 🙏 Acknowledgments

This release is based on features from:
- `django-approval-workflow` package v0.9.0+
- Enhanced role selection strategies
- Generic role discovery patterns

Thank you to the django-approval-workflow team for the excellent patterns and features!

---

## 📞 Support

- **Documentation:** [README.md](README.md)
- **Enhanced Strategies:** [ENHANCED_ROLE_STRATEGIES_GUIDE.md](ENHANCED_ROLE_STRATEGIES_GUIDE.md)
- **Issues:** [GitHub Issues](https://github.com/Codxi-Co/django-dynamic-workflows/issues)
- **Discussions:** [GitHub Discussions](https://github.com/Codxi-Co/django-dynamic-workflows/discussions)

---

## 📋 Full Changelog

### [1.6.0] - 2026-01-14

#### Added
- QUORUM role selection strategy support
- MAJORITY role selection strategy support
- PERCENTAGE role selection strategy support
- HIERARCHY escalation fields and support
- Generic role users discovery function `get_users_from_role()`
- 12 new fields to Stage model (quorum, hierarchy, SLA, parallel)
- `WORKFLOW_ROLE_USERS_FUNCTION` setting for custom role discovery
- Enhanced structured logging for role strategies

#### Changed
- Updated dependency to `django-approval-workflow>=0.9.0`
- Updated recipient_resolver.py to use generic role discovery
- Improved error handling and logging throughout

#### Fixed
- Role users discovery in recipient_resolver.py now uses generic function
- Better error messages for role discovery failures

#### Migration
- Added migration `0007_add_enhanced_role_strategies.py`

---

## ✅ Production Ready

This release has been:
- ✅ Thoroughly tested (356/356 tests passing)
- ✅ Documented with comprehensive guides
- ✅ Validated for backward compatibility
- ✅ Reviewed for security issues
- ✅ Performance tested

**Safe to upgrade from v1.5.x with zero downtime.**

---

**Version:** 1.6.0
**Release Date:** January 14, 2026
**Package:** django-dynamic-workflows
**Minimum Dependencies:** Django 4.2+, django-approval-workflow 0.9.0+
**License:** MIT

---

## 🎯 What's Next?

Future releases will include:
- **v1.7.0**: SLA management implementation
- **v1.8.0**: Parallel approval execution
- **v1.9.0**: Advanced hierarchy escalation with organization structure integration

Stay tuned for more powerful workflow features!
