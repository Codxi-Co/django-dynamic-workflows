"""Management command to set up sample workflows."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from django_workflow_engine.services import create_workflow

User = get_user_model()


class Command(BaseCommand):
    """Management command to create sample workflows."""

    help = "Create sample workflows for testing and development"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--company-id",
            type=int,
            required=True,
            help="Company ID to create workflows for",
        )
        parser.add_argument(
            "--user-id", type=int, required=True, help="User ID to set as creator"
        )
        parser.add_argument(
            "--department-id",
            type=int,
            required=True,
            help="Department ID for pipelines",
        )

    def handle(self, *args, **options):
        """Handle command execution."""
        try:
            # Import here to avoid circular imports
            from django.apps import apps

            Company = apps.get_model("companies", "Company")
            Department = apps.get_model("common", "Department")

            company = Company.objects.get(id=options["company_id"])
            user = User.objects.get(id=options["user_id"])
            department = Department.objects.get(id=options["department_id"])

            # Create sample workflows
            workflows_data = [
                {
                    "name_en": "Customer Onboarding Workflow",
                    "name_ar": "سير عمل إعداد العميل",
                    "pipelines": [
                        {
                            "name_en": "Document Collection",
                            "name_ar": "جمع المستندات",
                            "department_id": department.id,
                            "number_of_stages": 3,
                        },
                        {
                            "name_en": "Verification Process",
                            "name_ar": "عملية التحقق",
                            "department_id": department.id,
                            "number_of_stages": 2,
                        },
                        {
                            "name_en": "Final Approval",
                            "name_ar": "الموافقة النهائية",
                            "department_id": department.id,
                            "number_of_stages": 1,
                        },
                    ],
                },
                {
                    "name_en": "Document Processing Workflow",
                    "name_ar": "سير عمل معالجة المستندات",
                    "pipelines": [
                        {
                            "name_en": "Initial Review",
                            "name_ar": "المراجعة الأولية",
                            "department_id": department.id,
                            "number_of_stages": 2,
                        },
                        {
                            "name_en": "Quality Check",
                            "name_ar": "فحص الجودة",
                            "department_id": department.id,
                            "number_of_stages": 1,
                        },
                        {
                            "name_en": "Final Processing",
                            "name_ar": "المعالجة النهائية",
                            "department_id": department.id,
                            "number_of_stages": 1,
                        },
                    ],
                },
            ]

            created_workflows = []

            for workflow_data in workflows_data:
                workflow = create_workflow(
                    company=company,
                    name_en=workflow_data["name_en"],
                    name_ar=workflow_data["name_ar"],
                    created_by=user,
                    pipelines_data=workflow_data["pipelines"],
                )
                created_workflows.append(workflow)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created workflow: {workflow.name_en} (ID: {workflow.id})"
                    )
                )

                # Display pipeline information
                for pipeline in workflow.pipelines.all():
                    self.stdout.write(
                        f"  - Pipeline: {pipeline.name_en} ({pipeline.stages.count()} stages)"
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSuccessfully created {len(created_workflows)} sample workflows!"
                )
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error creating workflows: {str(e)}"))
            raise
