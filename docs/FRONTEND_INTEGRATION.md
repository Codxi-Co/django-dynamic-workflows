# Frontend Integration

This is the frontend contract for workflow screens, action controls, status
diagrams, and assignment configuration. Examples assume the Django app is
mounted at `/api/workflow/`; change the prefix to match the host project.

## Integration flow

1. Load a workflow or attachment.
2. Render progress and current pipeline/stage/status.
3. Load available transitions for the attachment.
4. Show only actions allowed by the API response and current approval.
5. Submit an action, then refetch the attachment and status/history data.

The backend remains authoritative. Never infer permission from a button being
visible, and treat `400`, `403`, and `409` responses as expected domain states.

## Main endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/workflows/` | list workflows |
| `GET` | `/workflows/{id}/` | workflow detail |
| `GET` | `/workflows/{id}/pipeline_structure/` | pipeline/stage diagram data |
| `GET` | `/workflows/{id}/approval_summary/` | approval counts and breakdown |
| `GET` | `/attachments/` | list/filter attached workflows |
| `GET` | `/attachments/{id}/progress/` | progress snapshot |
| `POST` | `/attachments/{id}/approve/` | approve, reject, delegate, resubmit |
| `GET` | `/attachments/{id}/transitions/` | allowed status transitions |
| `POST` | `/attachments/{id}/transition/` | request a status transition |
| `POST` | `/attachments/{id}/approve_transition/` | approve a pending transition |
| `POST` | `/attachments/{id}/reject_transition/` | reject a pending transition |
| `GET` | `/status/models/` | workflow-enabled model catalog |
| `GET` | `/status/options/{app_label.model}/` | status options for a model |
| `GET` | `/status/transitions/{app_label.model}/` | diagram nodes and edges |
| `GET` | `/status/history/` | status history |

Attachment list filters include `content_type=app_label.model`, `status`, and
`workflow_id`.

## Approval configuration form

Use `approval_type` for the recipient selector:

```json
{
  "approval_type": "user",
  "approval_user": 42,
  "step_approval_type": "approve",
  "required_form": null
}
```

| Type | Additional input |
| --- | --- |
| `self-approved` | none |
| `user` | required user picker → `approval_user` |
| `role` | required role picker → `user_role`; optional strategy |
| `assigned` | none; resolved from the business object |
| `team_head` | existing team-head approval behavior |
| `department_head` | existing department-head approval behavior |

`step_approval_type` controls the second part of the form:

- `submit`: require a form picker.
- `move`: hide and clear the form picker.
- `approve` and `check_in_verify`: allow the configured form behavior.

`assigned` is the only new option and does not require a user picker. The
backend resolves its user when creating the step. Do not relabel
`step_approval_type` as the recipient type in the UI.

## Submit workflow actions

All approval actions use the attachment action endpoint:

```http
POST /api/workflow/attachments/73/approve/
Content-Type: application/json
```

Approve:

```json
{
  "action": "approved",
  "reason": "Budget confirmed",
  "form_data": {"cost_center": "FIN-01"}
}
```

Reject:

```json
{"action": "rejected", "reason": "Missing supplier quote"}
```

Delegate:

```json
{"action": "delegated", "delegate_to": 84, "reason": "Out of office"}
```

Resubmit/request changes:

```json
{
  "action": "resubmission",
  "stage_id": 9,
  "reason": "Correct the amount and submit again"
}
```

On success, refetch rather than mutating local state from assumptions:

```json
{
  "message": "Workflow action processed successfully",
  "action": "approved",
  "object_id": "125"
}
```

## Status transitions

Load the allowed transitions immediately before showing a transition menu:

```http
GET /api/workflow/attachments/73/transitions/
```

Then submit by stable transition key:

```json
{
  "transition_key": "send_to_finance",
  "reason": "Manager review complete",
  "metadata": {"client_request_id": "f37a..."}
}
```

A transition that requires approval can return while the object remains in its
current status. Display it as “pending approval”; do not optimistically move the
status badge. Use the transition approve/reject endpoints for the pending edge.

## Diagram rendering

`GET /status/transitions/{app_label.model}/` is intended for graph UIs. Treat
status IDs/keys and transition keys as stable identifiers. Labels, colors,
ordering, metadata, permission results, and available actions may change after
each request.

Recommended state handling:

- Normalize nodes by status ID and edges by transition key.
- Keep localized `name_en`/`name_ar` data; select by active locale.
- Use server-provided colors only after validating them as CSS colors.
- Mark the current status from the attachment, not from the diagram definition.
- Refetch diagram/attachment after every successful transition.

## Errors and concurrency

Render field errors next to the matching control and a top-level `error` or
`non_field_errors` message in the action panel. Common errors include:

- current user is not the assigned approver;
- another user already advanced the step;
- required form data is missing;
- transition is no longer available;
- assignment configuration resolved no active user.

Disable the submit button only while the request is in flight. If state changed
concurrently, refetch the attachment, progress, transitions, and history before
letting the user retry.

## Frontend release checklist

- API prefix is environment-configurable.
- Authentication and CSRF behavior matches the host Django project.
- Buttons are permission-aware but server errors remain handled.
- Loading, empty, pending-approval, rejected, completed, and cancelled states exist.
- Form rules for `submit` and `move` are enforced before submission.
- New forms send `approval_type`; `assigned` hides the user picker.
- Arabic and English labels are tested where both are enabled.
- Dates use the API timezone and are formatted only at display time.

For complete status payload definitions, see [Status Workflow API](STATUS_WORKFLOW_API.md).
For backend setup and assignment resolver configuration, see [Developer Guide](DEVELOPER_GUIDE.md).
