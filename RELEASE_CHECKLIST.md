# Release v1.8.0 - Business Status Workflows

## Pre-Release Checklist

### Versioning

- [x] Version updated to `1.8.0` in `django_workflow_engine/__init__.py`
- [x] Version updated to `1.8.0` in `pyproject.toml`
- [x] `CHANGELOG.md` updated with `1.8.0`
- [x] `RELEASE_NOTES_1.8.0.md` created

### Code

- [x] Status graph strategy implemented through `WorkflowStrategy.STATUS_GRAPH`
- [x] Reusable status models and migrations added
- [x] Status graph transition services added
- [x] Status approval integration added using existing approval workflow package
- [x] Form-based transition approval support added
- [x] Helper services added in `django_workflow_engine.status_services`
- [x] Status REST URLs isolated in `django_workflow_engine/status_urls.py`
- [x] API extension settings added for custom project mixins and serializers
- [x] Audit fields added to status workflow design models
- [x] Transition and status-entry custom actions added
- [x] Action conditions and failure policies added
- [x] Transition actor authorization rules added
- [x] Company-specific default workflow provisioning added
- [x] Direct settings designs and `auto_generate_default_flow()` documented
- [x] Status transition approvals routed through the approval workflow system

### Documentation

- [x] `README.md` updated with Strategy 4 and status quick references
- [x] `STATUS_WORKFLOWS_GUIDE.md` added
- [x] `STATUS_WORKFLOW_IMPLEMENTATION_CASES.md` added
- [x] `CHANGELOG.md` updated
- [x] `MANIFEST.in` updated to include new release/status docs

### Validation

- [x] Focused status workflow tests passing
- [x] Full test suite passing
- [x] Django system check passing
- [x] Migration dry-run passing

---

## Release Validation Commands

Run before tagging or publishing:

```bash
python -m django check --settings=sandbox.settings
python -m django makemigrations django_workflow_engine --check --dry-run --settings=sandbox.settings
pytest -q
python -m build
twine check dist/*
```

Optional package builder:

```bash
python build_release.py
```

---

## Build Commands

```bash
rm -rf dist/ build/ django_dynamic_workflows.egg-info/
python -m build
twine check dist/*
```

---

## Publish Commands

Test PyPI:

```bash
twine upload --repository testpypi dist/*
```

Production PyPI:

```bash
twine upload dist/*
```

---

## Git Tag

```bash
git tag -a v1.8.0 -m "Release v1.8.0: Business Status Workflows"
git push origin v1.8.0
```

---

## GitHub Release

1. Create release for tag `v1.8.0`
2. Title: `v1.8.0: Business Status Workflows`
3. Body: copy from `RELEASE_NOTES_1.8.0.md`
4. Attach `dist/*` artifacts if desired
5. Publish release

---

## Migration Notes

Consumers should run:

```bash
python manage.py migrate django_workflow_engine
```

New migration:

- `0008_status_workflows.py`

---

## Release Summary

v1.8.0 adds first-class business status workflows for Tickets, Tasks, Opportunities, and any Django model. It includes status catalogs, graph transitions, transition approvals/forms, frontend-ready diagram APIs, helper services for custom APIs, and configurable status API base classes.

**Prepared date:** June 18, 2026
**Status:** Ready for release
