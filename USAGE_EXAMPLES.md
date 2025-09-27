# Django Workflow Engine - Usage Examples

## Basic Usage

### 1. Register a Model for Workflow Support

```python
# In your app's apps.py or management command
from django_workflow_engine.services import register_model_for_workflow
from myapp.models import Ticket, Lead

# Register Ticket model
register_model_for_workflow(
    Ticket,
    auto_start=False,
    status_field='workflow_status',
    stage_field='current_workflow_stage'
)

# Register Lead model with auto-start
register_model_for_workflow(
    Lead,
    auto_start=True,
    default_workflow=my_lead_workflow,
    status_field='status'
)
```

### 2. Attach Workflow to Any Object

```python
from django_workflow_engine.services import attach_workflow_to_object

# For a Ticket
ticket = Ticket.objects.get(pk=1)
attachment = attach_workflow_to_object(
    obj=ticket,
    workflow=customer_service_workflow,
    user=request.user,
    auto_start=True,
    metadata={'priority': 'high', 'department': 'support'}
)

# For a Lead
lead = Lead.objects.get(pk=5)
attachment = attach_workflow_to_object(
    obj=lead,
    workflow=sales_workflow,
    user=request.user
)
```

### 3. Check Workflow Progress

```python
from django_workflow_engine.services import get_workflow_progress, get_workflow_attachment

# Get progress information
progress = get_workflow_progress(workflow, ticket)
print(f"Progress: {progress['progress_percentage']}%")
print(f"Current Stage: {progress['current_stage']}")
print(f"Status: {progress['status']}")

# Get full attachment details
attachment = get_workflow_attachment(ticket)
if attachment:
    print(f"Next Stage: {attachment.next_stage.name_en if attachment.next_stage else 'Complete'}")
    print(f"Started by: {attachment.started_by.username if attachment.started_by else 'System'}")
```

### 4. Process Workflow Through Approval Actions

**Important**: Workflow progression is controlled through approval actions, not direct stage movement.

```python
from django_workflow_engine.serializers import WorkflowApprovalSerializer

# Approve current stage (moves to next stage automatically when final approval is reached)
serializer = WorkflowApprovalSerializer(
    data={
        'action': 'approved',
        'form_data': {'comment': 'All requirements met'},
    },
    object_instance=ticket,
    context={'request': request}
)

if serializer.is_valid():
    ticket = serializer.save()  # This will progress workflow if final approval
```

### 5. Handle Different Approval Actions

```python
# Reject workflow
serializer = WorkflowApprovalSerializer(
    data={
        'action': 'rejected',
        'reason': 'Missing required documentation'
    },
    object_instance=ticket,
    context={'request': request}
)

# Request resubmission to a previous stage
serializer = WorkflowApprovalSerializer(
    data={
        'action': 'resubmission',
        'stage_id': 123,  # Target stage for resubmission
        'reason': 'Please update the documentation'
    },
    object_instance=ticket,
    context={'request': request}
)

# Delegate to another user
serializer = WorkflowApprovalSerializer(
    data={
        'action': 'delegated',
        'user_id': 456,  # User to delegate to
        'reason': 'Delegating to subject matter expert'
    },
    object_instance=ticket,
    context={'request': request}
)
```

## Advanced Usage

### Custom Workflow Handlers

```python
# myapp/handlers.py
from django_workflow_engine.handlers import BaseWorkflowHandler
from myapp.models import Ticket

class TicketWorkflowHandler(BaseWorkflowHandler):
    def after_move_stage(self, obj, from_stage, to_stage, attachment):
        """Custom logic when ticket moves between stages."""
        # Update ticket status
        if hasattr(obj, 'status'):
            obj.status = f'in_{to_stage.name_en.lower().replace(" ", "_")}'
            obj.save()

        # Send notifications
        self.send_stage_notification(obj, to_stage)

    def after_move_pipeline(self, obj, from_pipeline, to_pipeline, attachment):
        """Custom logic when ticket moves between pipelines."""
        # Change ticket department
        obj.department = to_pipeline.department
        obj.save()

        # Notify new department
        self.notify_department_change(obj, from_pipeline, to_pipeline)

    def after_reject_stage(self, obj, stage, attachment, reason=None):
        """Custom logic when stage is rejected."""
        # Update ticket status
        obj.status = 'rejected'
        obj.rejection_reason = reason
        obj.save()

        # Send rejection notification
        self.send_rejection_notification(obj, reason)

    def send_stage_notification(self, ticket, stage):
        # Your notification logic here
        pass

    def notify_department_change(self, ticket, from_pipeline, to_pipeline):
        # Your department notification logic here
        pass

    def send_rejection_notification(self, ticket, reason):
        # Your rejection notification logic here
        pass
```

### Register Custom Handlers

```python
# In your handlers.py, update the get_workflow_handler_for_object function
def get_workflow_handler_for_object(obj) -> Optional[BaseWorkflowHandler]:
    """Get the appropriate workflow handler for an object."""
    if isinstance(obj, Ticket):
        return TicketWorkflowHandler()
    elif isinstance(obj, Lead):
        return LeadWorkflowHandler()

    return BaseWorkflowHandler()
```

### Integration with Approval Workflows

```python
from django_workflow_engine.handlers import BaseApprovalHandler
from approval_workflow.models import ApprovalInstance

class TicketApprovalHandler(BaseApprovalHandler):
    def __init__(self, instance=None):
        super().__init__()
        self.instance = instance

    def after_approve(self, approval_instance: ApprovalInstance):
        """Called after each approval step."""
        # Custom approval logic
        self.update_ticket_status('approved')

    def on_final_approve(self, approval_instance: ApprovalInstance):
        """Called after final approval - move to next stage."""
        from django_workflow_engine.services import move_to_next_stage

        # Move ticket to next workflow stage
        attachment = move_to_next_stage(self.instance)

        # Custom final approval logic
        self.handle_stage_completion()

    def after_reject(self, approval_instance: ApprovalInstance):
        """Called after rejection."""
        from django_workflow_engine.services import reject_workflow_stage

        # Reject the workflow stage
        current_attachment = get_workflow_attachment(self.instance)
        if current_attachment and current_attachment.current_stage:
            reject_workflow_stage(
                obj=self.instance,
                stage=current_attachment.current_stage,
                reason=approval_instance.comment
            )

    def update_ticket_status(self, status):
        if self.instance:
            self.instance.approval_status = status
            self.instance.save()

    def handle_stage_completion(self):
        # Custom logic when stage is complete
        pass
```

### Django Signals Integration

```python
# myapp/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django_workflow_engine.services import attach_workflow_to_object, is_model_workflow_enabled
from myapp.models import Ticket

@receiver(post_save, sender=Ticket)
def attach_workflow_to_new_ticket(sender, instance, created, **kwargs):
    """Automatically attach workflow to new tickets."""
    if created and is_model_workflow_enabled(Ticket):
        # Get default workflow for tickets
        try:
            from django_workflow_engine.models import WorkflowConfiguration
            from django.contrib.contenttypes.models import ContentType

            content_type = ContentType.objects.get_for_model(Ticket)
            config = WorkflowConfiguration.objects.get(content_type=content_type)

            if config.auto_start_workflow and config.default_workflow:
                attach_workflow_to_object(
                    obj=instance,
                    workflow=config.default_workflow,
                    user=instance.created_by,
                    auto_start=True
                )
        except WorkflowConfiguration.DoesNotExist:
            pass
```

### API Integration Example

```python
# views.py
from rest_framework.decorators import action
from rest_framework.response import Response
from django_workflow_engine.views import WorkflowMixin
from django_workflow_engine.serializers import WorkflowApprovalSerializer

class TicketViewSet(WorkflowMixin, ModelViewSet):
    """
    Ticket ViewSet with integrated workflow functionality.
    WorkflowMixin provides: attach_workflow, workflow_status, workflow_action, start_workflow
    """
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer

    # WorkflowMixin automatically provides these endpoints:
    # POST /tickets/{id}/attach_workflow/ - Attach workflow to ticket
    # GET  /tickets/{id}/workflow_status/ - Get workflow status
    # POST /tickets/{id}/workflow_action/ - Perform approval action
    # POST /tickets/{id}/start_workflow/ - Start workflow

    @action(detail=True, methods=['post'])
    def approve_stage(self, request, pk=None):
        """Custom approval endpoint with validation."""
        ticket = self.get_object()

        # Use WorkflowApprovalSerializer for proper validation
        serializer = WorkflowApprovalSerializer(
            data=request.data,
            object_instance=ticket,
            context={'request': request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': f'Action "{serializer.validated_data["action"]}" processed successfully',
                'ticket_id': ticket.pk
            })
        else:
            return Response(serializer.errors, status=400)
```

### Frontend Integration Examples

```javascript
// React/JavaScript examples

// Attach workflow to ticket
const attachWorkflow = async (ticketId, workflowId) => {
    const response = await fetch(`/api/tickets/${ticketId}/attach_workflow/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            workflow_id: workflowId,
            auto_start: true,
            metadata: { priority: 'high' }
        })
    });
    return response.json();
};

// Get workflow status
const getWorkflowStatus = async (ticketId) => {
    const response = await fetch(`/api/tickets/${ticketId}/workflow_status/`);
    return response.json();
};

// Approve current stage
const approveStage = async (ticketId, formData = {}) => {
    const response = await fetch(`/api/tickets/${ticketId}/workflow_action/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'approved',
            form_data: formData
        })
    });
    return response.json();
};

// Reject with reason
const rejectStage = async (ticketId, reason) => {
    const response = await fetch(`/api/tickets/${ticketId}/workflow_action/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'rejected',
            reason: reason
        })
    });
    return response.json();
};

// Request resubmission to specific stage
const requestResubmission = async (ticketId, stageId, reason) => {
    const response = await fetch(`/api/tickets/${ticketId}/workflow_action/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'resubmission',
            stage_id: stageId,
            reason: reason
        })
    });
    return response.json();
};

// Delegate to another user
const delegateApproval = async (ticketId, userId, reason) => {
    const response = await fetch(`/api/tickets/${ticketId}/workflow_action/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'delegated',
            user_id: userId,
            reason: reason
        })
    });
    return response.json();
};
```

## Management Commands

### Create Sample Workflows

```bash
# Create sample workflows
python manage.py setup_workflows --company-id 1 --user-id 1 --department-id 1
```

### Custom Management Commands

```python
# management/commands/attach_workflows.py
from django.core.management.base import BaseCommand
from django_workflow_engine.services import attach_workflow_to_object
from myapp.models import Ticket

class Command(BaseCommand):
    help = 'Attach workflows to existing tickets'

    def add_arguments(self, parser):
        parser.add_argument('--workflow-id', type=int, required=True)
        parser.add_argument('--batch-size', type=int, default=100)

    def handle(self, *args, **options):
        workflow = WorkFlow.objects.get(id=options['workflow_id'])
        tickets = Ticket.objects.filter(workflow_attachment__isnull=True)

        for ticket in tickets[:options['batch_size']]:
            attach_workflow_to_object(
                obj=ticket,
                workflow=workflow,
                auto_start=True
            )
            self.stdout.write(f"Attached workflow to ticket {ticket.id}")
```

This workflow engine provides maximum flexibility while maintaining the power of the approval workflow system!