"""
Test cases for detailed workflow functions
"""

from django.test import TestCase

from approval_workflow.choices import RoleSelectionStrategy

from django_workflow_engine.choices import ApprovalTypes
from django_workflow_engine.services import (
    get_detailed_workflow_data,
    get_workflow_approval_summary,
    get_workflow_pipeline_structure,
    get_workflow_statistics,
)

from .factories import CompleteWorkflowFactory, UserFactory


class DetailedWorkflowFunctionsTest(TestCase):
    """Test detailed workflow functions"""

    def setUp(self):
        """Set up test data"""
        self.user = UserFactory()
        self.workflow1 = CompleteWorkflowFactory(
            name_en="Purchase Request Workflow", name_ar="سير عمل طلب الشراء"
        )
        self.workflow2 = CompleteWorkflowFactory(
            name_en="Leave Request Workflow", name_ar="سير عمل طلب الإجازة"
        )

    def test_get_detailed_workflow_data_single_workflow(self):
        """Test getting detailed data for a single workflow"""
        data = get_detailed_workflow_data(workflow_id=self.workflow1.id)

        self.assertIsNotNone(data)
        self.assertEqual(data["id"], self.workflow1.id)
        self.assertEqual(data["name_en"], self.workflow1.name_en)

        # Check nested structure
        self.assertIn("pipelines", data)
        self.assertIn("workflow_summary", data)
        self.assertGreater(len(data["pipelines"]), 0)

        # Check pipeline structure
        pipeline = data["pipelines"][0]
        self.assertIn("stages", pipeline)
        self.assertGreater(len(pipeline["stages"]), 0)

        # Check stage structure
        stage = pipeline["stages"][0]
        self.assertIn("approval_configuration", stage)
        self.assertIn("approvals_count", stage)

        # Check workflow summary
        summary = data["workflow_summary"]
        self.assertIn("total_pipelines", summary)
        self.assertIn("total_stages", summary)
        self.assertIn("total_approvals", summary)
        self.assertIn("pipeline_breakdown", summary)

    def test_get_detailed_workflow_data_nonexistent(self):
        """Test getting data for nonexistent workflow"""
        data = get_detailed_workflow_data(workflow_id=99999)
        self.assertIsNone(data)

    def test_get_detailed_workflow_data_all_workflows(self):
        """Test getting all workflows"""
        data = get_detailed_workflow_data()

        self.assertIsNotNone(data)
        self.assertIn("workflows", data)
        self.assertIn("total_count", data)
        self.assertIn("statistics", data)

        # Check we have both workflows
        self.assertEqual(len(data["workflows"]), 2)
        self.assertEqual(data["total_count"], 2)

        # Check workflow structure (summary format)
        workflow = data["workflows"][0]
        self.assertIn("pipelines_count", workflow)
        self.assertIn("total_stages_count", workflow)
        self.assertNotIn("pipelines", workflow)  # Should not include full pipelines

        # Check statistics
        stats = data["statistics"]
        self.assertIn("overview", stats)
        self.assertIn("by_company", stats)

    def test_get_detailed_workflow_data_with_company_filter(self):
        """Test filtering workflows by company"""
        company_id = self.workflow1.company.id
        company_username = self.workflow1.company.username
        data = get_detailed_workflow_data(company_id=company_id)

        self.assertIsNotNone(data)
        self.assertGreater(len(data["workflows"]), 0)

        # All workflows should belong to the specified company
        for workflow in data["workflows"]:
            self.assertEqual(workflow["company"], company_username)

    def test_get_detailed_workflow_data_include_inactive(self):
        """Test including inactive workflows"""
        # Mark one workflow as inactive
        self.workflow1.is_active = False
        self.workflow1.save()

        # Test without including inactive
        data_active_only = get_detailed_workflow_data()
        active_count = len(data_active_only["workflows"])

        # Test including inactive
        data_all = get_detailed_workflow_data(include_inactive=True)
        all_count = len(data_all["workflows"])

        # Should have more workflows when including inactive
        self.assertGreater(all_count, active_count)

    def test_get_workflow_pipeline_structure(self):
        """Test getting pipeline structure"""
        data = get_workflow_pipeline_structure(self.workflow1.id)

        self.assertIsNotNone(data)
        self.assertEqual(data["workflow_id"], self.workflow1.id)
        self.assertEqual(data["workflow_name"], self.workflow1.name_en)

        # Check structure
        self.assertIn("pipelines", data)
        self.assertIn("total_pipelines", data)
        self.assertIn("total_stages", data)

        # Check pipeline data
        pipeline = data["pipelines"][0]
        expected_fields = [
            "id",
            "name_en",
            "name_ar",
            "order",
            "department",
            "stages",
            "stages_count",
        ]
        for field in expected_fields:
            self.assertIn(field, pipeline)

        # Check stage data
        if pipeline["stages"]:
            stage = pipeline["stages"][0]
            stage_fields = [
                "id",
                "name_en",
                "name_ar",
                "order",
                "is_active",
                "approvals_count",
                "approval_types",
                "color",
                "has_forms",
            ]
            for field in stage_fields:
                self.assertIn(field, stage)

    def test_get_workflow_pipeline_structure_nonexistent(self):
        """Test getting pipeline structure for nonexistent workflow"""
        data = get_workflow_pipeline_structure(99999)
        self.assertIsNone(data)

    def test_get_workflow_approval_summary(self):
        """Test getting approval summary"""
        data = get_workflow_approval_summary(self.workflow1.id)

        self.assertIsNotNone(data)

        # Check required fields
        expected_fields = [
            "total_approvals",
            "by_type",
            "by_strategy",
            "stages_with_forms",
            "pipeline_breakdown",
        ]
        for field in expected_fields:
            self.assertIn(field, data)

        # Check by_type structure
        by_type = data["by_type"]
        self.assertIn(ApprovalTypes.ROLE, by_type)
        self.assertIn(ApprovalTypes.USER, by_type)
        self.assertIn(ApprovalTypes.SELF, by_type)

        # Check by_strategy structure
        by_strategy = data["by_strategy"]
        self.assertIn(RoleSelectionStrategy.ANYONE, by_strategy)
        self.assertIn(RoleSelectionStrategy.CONSENSUS, by_strategy)
        self.assertIn(RoleSelectionStrategy.ROUND_ROBIN, by_strategy)

        # Check pipeline breakdown
        self.assertGreater(len(data["pipeline_breakdown"]), 0)
        pipeline_breakdown = data["pipeline_breakdown"][0]
        breakdown_fields = [
            "pipeline_name",
            "pipeline_order",
            "stages",
            "total_approvals",
        ]
        for field in breakdown_fields:
            self.assertIn(field, pipeline_breakdown)

    def test_get_workflow_approval_summary_nonexistent(self):
        """Test getting approval summary for nonexistent workflow"""
        data = get_workflow_approval_summary(99999)
        self.assertIsNone(data)

    def test_get_workflow_statistics(self):
        """Test getting workflow statistics"""
        data = get_workflow_statistics()

        self.assertIsNotNone(data)
        self.assertIn("overview", data)
        self.assertIn("by_company", data)

        # Check overview structure
        overview = data["overview"]
        overview_fields = [
            "total_workflows",
            "active_workflows",
            "inactive_workflows",
            "total_pipelines",
            "total_stages",
            "total_approvals",
            "avg_pipelines_per_workflow",
            "avg_stages_per_workflow",
        ]
        for field in overview_fields:
            self.assertIn(field, overview)

        # Check that we have data
        self.assertEqual(overview["total_workflows"], 2)
        self.assertGreater(overview["total_pipelines"], 0)
        self.assertGreater(overview["total_stages"], 0)

        # Check by_company structure
        by_company = data["by_company"]
        self.assertIsInstance(by_company, dict)

    def test_get_workflow_statistics_with_company_filter(self):
        """Test getting statistics filtered by company"""
        company_id = self.workflow1.company.id
        data = get_workflow_statistics(company_id=company_id)

        self.assertIsNotNone(data)
        # Should have fewer or equal workflows than total
        total_data = get_workflow_statistics()
        self.assertLessEqual(
            data["overview"]["total_workflows"],
            total_data["overview"]["total_workflows"],
        )

    def test_approval_configuration_enrichment(self):
        """Test that approval configurations are properly enriched"""
        data = get_detailed_workflow_data(workflow_id=self.workflow1.id)

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

    def test_performance_with_multiple_workflows(self):
        """Test performance with multiple workflows"""
        # Create additional workflows to test performance
        for i in range(5):
            CompleteWorkflowFactory(
                name_en=f"Additional Workflow {i}", name_ar=f"سير عمل إضافي {i}"
            )

        # Test that we can get all workflows efficiently
        data = get_detailed_workflow_data()
        self.assertEqual(len(data["workflows"]), 7)  # 2 original + 5 new

        # Test statistics calculation
        stats = get_workflow_statistics()
        self.assertEqual(stats["overview"]["total_workflows"], 7)

    def test_function_consistency_with_serializers(self):
        """Test that functions produce consistent data with serializers"""
        from django_workflow_engine.serializers import WorkFlowDetailSerializer

        # Get data from function
        function_data = get_detailed_workflow_data(workflow_id=self.workflow1.id)

        # Get data from serializer
        serializer = WorkFlowDetailSerializer(self.workflow1)
        serializer_data = serializer.data

        # Compare key fields
        self.assertEqual(function_data["id"], serializer_data["id"])
        self.assertEqual(function_data["name_en"], serializer_data["name_en"])
        self.assertEqual(
            function_data["pipelines_count"], serializer_data["pipelines_count"]
        )
        self.assertEqual(
            function_data["total_stages_count"], serializer_data["total_stages_count"]
        )

    def test_database_query_optimization(self):
        """Test that functions use optimized database queries"""
        from django.db import connection
        from django.test.utils import override_settings

        # Enable query logging
        with override_settings(DEBUG=True):
            # Reset queries
            connection.queries.clear()

            # Call function
            get_detailed_workflow_data(workflow_id=self.workflow1.id)

            # Check number of queries (should be minimal due to prefetch_related)
            query_count = len(connection.queries)

            # Should be significantly fewer queries than naive approach
            # Exact number depends on the data structure, but should be < 10
            self.assertLess(query_count, 10)

    def tearDown(self):
        """Clean up after tests"""
        # Cleanup is handled automatically by Django test framework
        pass
