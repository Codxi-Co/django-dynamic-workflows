"""
Simple test for workflow endpoints functionality
"""

from django.test import TestCase

from approval_workflow.choices import RoleSelectionStrategy
from rest_framework import status
from rest_framework.test import APIClient

from django_workflow_engine.choices import ApprovalTypes

from .factories import CompleteWorkflowFactory, UserFactory


class SimpleWorkflowEndpointsTest(TestCase):
    """Simple test for workflow endpoints"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.user = UserFactory()
        self.workflow = CompleteWorkflowFactory(
            name_en="Test Workflow", name_ar="سير عمل تجريبي"
        )

    def test_workflow_viewset_directly(self):
        """Test WorkFlowViewSet directly without URL routing"""
        from django.http import HttpRequest

        from rest_framework.request import Request

        from django_workflow_engine.views import WorkFlowViewSet

        # Create viewset instance
        viewset = WorkFlowViewSet()

        # Test get_queryset
        queryset = viewset.get_queryset()
        self.assertGreater(queryset.count(), 0)

        # Test get_serializer_class for list
        viewset.action = "list"
        serializer_class = viewset.get_serializer_class()
        self.assertEqual(serializer_class.__name__, "WorkFlowListSerializer")

        # Test get_serializer_class for retrieve
        viewset.action = "retrieve"
        serializer_class = viewset.get_serializer_class()
        self.assertEqual(serializer_class.__name__, "WorkFlowDetailSerializer")

    def test_workflow_detail_view_functionality(self):
        """Test the detail view functionality"""
        from django_workflow_engine.serializers import WorkFlowDetailSerializer
        from django_workflow_engine.views import WorkFlowViewSet

        # Create viewset and set up for detail view
        viewset = WorkFlowViewSet()
        viewset.action = "retrieve"

        # Get the workflow object
        workflow = viewset.get_queryset().first()
        self.assertIsNotNone(workflow)

        # Test serialization
        serializer = WorkFlowDetailSerializer(workflow)
        data = serializer.data

        # Verify basic structure
        self.assertIn("pipelines", data)
        self.assertIn("workflow_summary", data)
        self.assertGreater(data["pipelines_count"], 0)

    def test_pipeline_structure_action(self):
        """Test pipeline_structure custom action functionality"""
        from unittest.mock import Mock

        from django_workflow_engine.views import WorkFlowViewSet

        # Create viewset
        viewset = WorkFlowViewSet()

        # Mock request and get_object
        request = Mock()
        viewset.get_object = Mock(return_value=self.workflow)

        # Call pipeline_structure action
        response = viewset.pipeline_structure(request, pk=self.workflow.pk)

        # Verify response structure
        self.assertEqual(response.status_code, 200)
        data = response.data

        expected_fields = [
            "workflow_id",
            "workflow_name",
            "pipelines",
            "total_pipelines",
            "total_stages",
        ]
        for field in expected_fields:
            self.assertIn(field, data)

        self.assertEqual(data["workflow_id"], self.workflow.id)
        self.assertGreater(len(data["pipelines"]), 0)

    def test_approval_summary_action(self):
        """Test approval_summary custom action functionality"""
        from unittest.mock import Mock

        from django_workflow_engine.views import WorkFlowViewSet

        # Create viewset
        viewset = WorkFlowViewSet()

        # Mock request and get_object
        request = Mock()
        viewset.get_object = Mock(return_value=self.workflow)

        # Call approval_summary action
        response = viewset.approval_summary(request, pk=self.workflow.pk)

        # Verify response structure
        self.assertEqual(response.status_code, 200)
        data = response.data

        expected_fields = [
            "total_approvals",
            "by_type",
            "by_strategy",
            "stages_with_forms",
            "pipeline_breakdown",
        ]
        for field in expected_fields:
            self.assertIn(field, data)

        # Verify by_type structure
        by_type = data["by_type"]
        self.assertIn(ApprovalTypes.ROLE, by_type)
        self.assertIn(ApprovalTypes.USER, by_type)

    def test_workflow_statistics_action(self):
        """Test workflow_statistics custom action functionality"""
        from unittest.mock import Mock

        from django_workflow_engine.views import WorkFlowViewSet

        # Create viewset
        viewset = WorkFlowViewSet()

        # Mock request
        request = Mock()

        # Call workflow_statistics action
        response = viewset.workflow_statistics(request)

        # Verify response structure
        self.assertEqual(response.status_code, 200)
        data = response.data

        self.assertIn("overview", data)
        self.assertIn("by_company", data)

        # Verify overview
        overview = data["overview"]
        self.assertGreater(overview["total_workflows"], 0)

    def test_queryset_filtering(self):
        """Test queryset filtering functionality"""
        from unittest.mock import Mock

        from django_workflow_engine.views import WorkFlowViewSet

        # Create viewset
        viewset = WorkFlowViewSet()

        # Mock request with company filter
        request = Mock()
        request.query_params = {"company_id": self.workflow.company.id}
        viewset.request = request

        queryset = viewset.get_queryset()
        for workflow in queryset:
            self.assertEqual(workflow.company.id, self.workflow.company.id)

        # Mock request with active filter
        request.query_params = {"is_active": "true"}
        queryset = viewset.get_queryset()
        for workflow in queryset:
            self.assertTrue(workflow.is_active)

    def test_workflow_summary_calculation(self):
        """Test workflow summary calculation in detail serializer"""
        from django_workflow_engine.serializers import WorkFlowDetailSerializer

        serializer = WorkFlowDetailSerializer(self.workflow)
        data = serializer.data

        summary = data["workflow_summary"]

        # Verify summary calculations
        self.assertEqual(summary["total_pipelines"], data["pipelines_count"])

        # Calculate expected total stages
        expected_stages = sum(len(pipeline["stages"]) for pipeline in data["pipelines"])
        self.assertEqual(summary["total_stages"], expected_stages)

        # Verify pipeline breakdown
        self.assertEqual(len(summary["pipeline_breakdown"]), summary["total_pipelines"])

        for breakdown in summary["pipeline_breakdown"]:
            self.assertIn("pipeline_name", breakdown)
            self.assertIn("stages_count", breakdown)
            self.assertIn("approvals_count", breakdown)

    def test_approval_configuration_enrichment(self):
        """Test approval configuration enrichment in stages"""
        from django_workflow_engine.serializers import WorkFlowDetailSerializer

        serializer = WorkFlowDetailSerializer(self.workflow)
        data = serializer.data

        # Find a stage with approvals
        stage_with_approvals = None
        for pipeline in data["pipelines"]:
            for stage in pipeline["stages"]:
                if stage["has_approvals"]:
                    stage_with_approvals = stage
                    break
            if stage_with_approvals:
                break

        if stage_with_approvals:
            approval_config = stage_with_approvals["approval_configuration"]
            self.assertIn("approvals", approval_config)

            # Check enriched approval data
            for approval in approval_config["approvals"]:
                self.assertIn("approval_type_display", approval)

                # Check strategy display for role-based approvals
                if approval.get("role_selection_strategy"):
                    self.assertIn("strategy_display", approval)
                    self.assertNotEqual(approval["strategy_display"], "")

    def tearDown(self):
        """Clean up after tests"""
        # Clean up is handled automatically by Django test framework
        pass
