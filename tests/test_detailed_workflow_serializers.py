"""
Test cases for detailed workflow serializers
"""

from django.test import TestCase

from django_workflow_engine.serializers import (
    PipelineDetailSerializer,
    StageDetailSerializer,
    WorkFlowDetailSerializer,
    WorkFlowListSerializer,
)

from .factories import CompleteWorkflowFactory


class DetailedWorkflowSerializersTest(TestCase):
    """Test detailed workflow serializers"""

    def setUp(self):
        """Set up test data"""
        self.workflow = CompleteWorkflowFactory(
            name_en="Purchase Request Workflow", name_ar="سير عمل طلب الشراء"
        )

    def test_stage_detail_serializer(self):
        """Test StageDetailSerializer"""
        # Get a stage from our workflow
        stage = self.workflow.pipelines.first().stages.first()

        serializer = StageDetailSerializer(stage)
        data = serializer.data

        # Check required fields
        expected_fields = [
            "id",
            "name_en",
            "name_ar",
            "order",
            "is_active",
            "stage_info",
            "approvals_count",
            "has_approvals",
            "approval_configuration",
            "created_at",
            "modified_at",
        ]
        for field in expected_fields:
            self.assertIn(field, data)

        # Check approval configuration structure
        approval_config = data["approval_configuration"]
        self.assertIn("approvals", approval_config)
        self.assertIn("color", approval_config)
        self.assertIn("total_approvals", approval_config)

        # Check that approvals count matches
        self.assertEqual(data["approvals_count"], len(approval_config["approvals"]))
        self.assertEqual(data["has_approvals"], data["approvals_count"] > 0)

    def test_pipeline_detail_serializer(self):
        """Test PipelineDetailSerializer"""
        pipeline = self.workflow.pipelines.first()

        serializer = PipelineDetailSerializer(pipeline)
        data = serializer.data

        # Check required fields
        expected_fields = [
            "id",
            "name_en",
            "name_ar",
            "order",
            "department",
            "department_name",
            "stages",
            "stages_count",
        ]
        for field in expected_fields:
            self.assertIn(field, data)

        # Check stages data
        self.assertIn("stages", data)
        self.assertGreater(len(data["stages"]), 0)
        self.assertEqual(data["stages_count"], len(data["stages"]))

        # Check stage structure
        stage = data["stages"][0]
        stage_fields = [
            "id",
            "name_en",
            "name_ar",
            "order",
            "is_active",
            "stage_info",
            "approvals_count",
            "has_approvals",
        ]
        for field in stage_fields:
            self.assertIn(field, stage)

    def test_workflow_detail_serializer(self):
        """Test WorkFlowDetailSerializer"""
        serializer = WorkFlowDetailSerializer(self.workflow)
        data = serializer.data

        # Check required fields
        expected_fields = [
            "id",
            "name_en",
            "name_ar",
            "company",
            "company_name",
            "is_active",
            "description",
            "pipelines",
            "pipelines_count",
            "total_stages_count",
            "workflow_summary",
        ]
        for field in expected_fields:
            self.assertIn(field, data)

        # Check nested pipelines
        self.assertIn("pipelines", data)
        self.assertGreater(len(data["pipelines"]), 0)
        self.assertEqual(data["pipelines_count"], len(data["pipelines"]))

        # Check workflow summary
        summary = data["workflow_summary"]
        summary_fields = [
            "total_pipelines",
            "total_stages",
            "total_approvals",
            "pipeline_breakdown",
        ]
        for field in summary_fields:
            self.assertIn(field, summary)

        # Verify summary counts match
        self.assertEqual(summary["total_pipelines"], len(data["pipelines"]))

        # Check pipeline breakdown
        self.assertGreater(len(summary["pipeline_breakdown"]), 0)
        breakdown = summary["pipeline_breakdown"][0]
        breakdown_fields = [
            "pipeline_name",
            "pipeline_order",
            "stages_count",
            "approvals_count",
        ]
        for field in breakdown_fields:
            self.assertIn(field, breakdown)

    def test_workflow_list_serializer(self):
        """Test WorkFlowListSerializer"""
        serializer = WorkFlowListSerializer(self.workflow)
        data = serializer.data

        # Check required fields
        expected_fields = [
            "id",
            "name_en",
            "name_ar",
            "company",
            "company_name",
            "is_active",
            "description",
            "pipelines_count",
            "total_stages_count",
        ]
        for field in expected_fields:
            self.assertIn(field, data)

        # Check that pipelines are not included (this is list view)
        self.assertNotIn("pipelines", data)
        self.assertNotIn("workflow_summary", data)

        # Check counts
        self.assertGreater(data["pipelines_count"], 0)
        self.assertGreater(data["total_stages_count"], 0)

    def test_approval_configuration_enrichment(self):
        """Test that approval configuration is properly enriched"""
        # Get a stage with approvals
        stage = self.workflow.pipelines.first().stages.first()

        serializer = StageDetailSerializer(stage)
        data = serializer.data

        approval_config = data["approval_configuration"]
        if approval_config["approvals"]:
            approval = approval_config["approvals"][0]

            # Check for enriched display fields
            self.assertIn("approval_type_display", approval)

            # If it's a role-based approval, check for strategy display
            if approval.get("role_selection_strategy"):
                self.assertIn("strategy_display", approval)

            # Verify display text is meaningful
            self.assertNotEqual(approval["approval_type_display"], "")
            if "strategy_display" in approval:
                self.assertNotEqual(approval["strategy_display"], "")

    def test_serializer_with_multiple_workflows(self):
        """Test serializers with multiple workflows"""
        workflow2 = CompleteWorkflowFactory(
            name_en="Leave Request Workflow", name_ar="سير عمل طلب الإجازة"
        )

        workflows = [self.workflow, workflow2]
        serializer = WorkFlowListSerializer(workflows, many=True)
        data = serializer.data

        self.assertEqual(len(data), 2)

        # Check that each workflow has the required fields
        for workflow_data in data:
            self.assertIn("id", workflow_data)
            self.assertIn("name_en", workflow_data)
            self.assertIn("pipelines_count", workflow_data)

    def test_empty_workflow_serialization(self):
        """Test serialization of workflow with no pipelines"""
        from .factories import WorkFlowFactory

        empty_workflow = WorkFlowFactory(
            name_en="Empty Workflow", name_ar="سير عمل فارغ"
        )

        serializer = WorkFlowDetailSerializer(empty_workflow)
        data = serializer.data

        # Should still work with empty pipelines
        self.assertEqual(data["pipelines_count"], 0)
        self.assertEqual(data["total_stages_count"], 0)
        self.assertEqual(len(data["pipelines"]), 0)

        # Check workflow summary
        summary = data["workflow_summary"]
        self.assertEqual(summary["total_pipelines"], 0)
        self.assertEqual(summary["total_stages"], 0)
        self.assertEqual(summary["total_approvals"], 0)
        self.assertEqual(len(summary["pipeline_breakdown"]), 0)
