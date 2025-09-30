# Changelog

All notable changes to django-dynamic-workflows will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.8] - 2025-09-30

### 🎯 ApprovalTypes Enhancements
- **Updated ApprovalTypes enum**: Added new approval type choices with translation support
  - `SELF = "self-approved"` - Self approval type
  - `ROLE = "role"` - Role-based approval
  - `USER = "user"` - User-specific approval
  - `TEAM_HEAD = "team_head"` - Team head approval (reserved for future use)
  - `DEPARTMENT_HEAD = "department_head"` - Department head approval (reserved for future use)
- **Dynamic validation**: Stage model now validates approval types against ApprovalTypes enum dynamically
- **Translation ready**: All approval type labels now use `gettext_lazy` for internationalization

### 🌍 Translation Improvements
- **Complete model translation**: All `help_text` and `verbose_name` strings now wrapped with `_()` for translation
- **BaseCompanyModel translations**: Company, name fields fully translatable
- **Pipeline model translations**: Department fields with proper translation support
- **Stage model translations**: Form and stage info fields translated
- **WorkflowAttachment translations**: All workflow state fields translatable
- **WorkflowConfiguration translations**: Hook and field mapping descriptions translated
- **WorkflowAction translations**: Action configuration fields fully translated

### 🔧 StageSerializer Enhancements
- **Pipeline validation**: Added smart pipeline detection from URL or request body
- **URL parameter support**: Automatically extracts `pipeline` or `pipeline_pk` from URL kwargs
- **Body parameter support**: Falls back to pipeline from request body if not in URL
- **Clear error messages**: Descriptive validation error when pipeline is missing
- **Create vs Update logic**: Pipeline validation only required for create operations

### ✅ Testing
- **Added stage update test**: New test case `test_update_stage_info_with_role_approval`
- **Validates name fields**: Tests confirm Stage has `name_en` and `name_ar` fields
- **Approval configuration test**: Verifies role-based approval with all required fields
- **11/11 tests passing**: All serializer tests pass with new changes

### 🗄️ Database Migrations
- **Migration 0002**: Created migration for model option changes
- **Index optimization**: Renamed indexes for better clarity
- **Field updates**: Updated cloned_from fields with proper help text
- **Status choices**: Updated WorkflowStatus and WorkflowAttachmentStatus choices

### 📋 Technical Details
- **Backward compatible**: All changes maintain backward compatibility
- **No breaking changes**: Existing code continues to work without modifications
- **Enhanced validation**: More robust approval type validation using enum
- **Better DX**: Improved developer experience with clearer error messages

---

## [1.0.7] - 2025-09-30

### 🚀 New Workflow Serializers
- **Added WorkFlowSerializer**: Complete nested creation of workflows with pipelines and stages in a single API call
- **Added PipelineSerializer**: Create pipelines with automatic stage generation based on `number_of_stages` parameter
- **Added StageSerializer**: Create and update stages with approval configuration validation
- **Nested serialization support**: Create entire workflow hierarchies in one request with proper validation
- **README examples now functional**: All serializer examples in documentation are now fully working

### ⚡ Workflow Auto-Activation System
- **Intelligent stage activation**: Stages automatically activate when approval configurations are added
- **Auto-deactivation**: Stages deactivate when all approvals are removed
- **Workflow-level activation**: Workflows automatically activate when all stages are properly configured
- **Real-time validation**: Stage and workflow status updates happen automatically on configuration changes
- **Performance optimized**: Added `skip_workflow_update` parameter to Stage.save() for bulk operations

### 🔧 Serializer Improvements
- **Refactored WorkflowApprovalSerializer**: Now uses standard DRF `self.instance` pattern instead of custom `object_instance` parameter
- **Developer flexibility**: All serializers now use `fields = "__all__"` in Meta, allowing easy customization by subclassing
- **Better context handling**: Automatic `company` extraction from context when not provided
- **Standard DRF patterns**: Simplified serializer initialization following Django Rest Framework conventions
- **Comprehensive logging**: Added structured logging throughout all serializers using WorkflowLogger

### 🎯 Validation & Error Handling
- **Case-insensitive approval types**: Approval types ('user', 'role', 'self') now validated case-insensitively
- **Case-insensitive strategies**: Role selection strategies ('anyone', 'consensus', etc.) validated case-insensitively
- **Stage completion validation**: Stages require proper approval configuration to be considered complete
- **Better error messages**: Clear validation errors with helpful guidance for developers

### 🚀 Performance Optimizations
- **Query optimization**: Added `prefetch_related` to workflow validation to prevent N+1 queries
- **Bulk operation support**: Stage.save() accepts `skip_workflow_update` flag for bulk operations
- **Reduced redundant validation**: Workflow active status only updates when necessary
- **Optimized test fixtures**: Test setup optimized to reduce unnecessary workflow validations

### 📚 Documentation Updates
- **Fixed README examples**: Updated all code examples to use correct lowercase approval types and strategies
- **Added comprehensive tests**: 10 new tests validating all README serializer examples work correctly
- **Better developer guidance**: Enhanced documentation with working examples and best practices

### 🧪 Testing Improvements
- **All tests passing**: 143/143 tests passing with new validation requirements
- **Updated test fixtures**: All test stages now include proper `stage_info` with approvals
- **README example tests**: New test file validates all documentation examples work correctly
- **Improved test patterns**: Tests now follow standard DRF patterns with `instance=` parameter

### 🛠 Technical Details
- **Migration path**: Existing workflows need stages updated with approval configurations to activate
- **Backward compatible**: No breaking changes to existing API or data structures
- **Standard DRF usage**: WorkflowApprovalSerializer now follows standard serializer patterns
- **Proper field configuration**: Read-only and write-only fields properly configured across all serializers

### 📋 Migration Notes
- Existing stages without approval configurations will be inactive until approvals are added
- WorkflowApprovalSerializer usage changed from `object_instance=obj` to `instance=obj` (standard DRF)
- All serializers can be customized by subclassing and overriding `fields` in Meta
- Test execution time: ~84 seconds for 143 tests (integration tests with full database setup)

---

## [1.0.6] - 2025-09-28

### 🔧 DRF Spectacular Compatibility Fixes
- **Fixed type hint warnings**: Added `@extend_schema_field` decorators to all SerializerMethodField methods in serializers
- **Resolved GenericForeignKey warnings**: Created custom `GenericForeignKeyField` to properly handle Pipeline.department field serialization
- **Enhanced API documentation**: All serializer method fields now have proper type annotations for OpenAPI schema generation
- **Improved field resolution**: Replaced direct department field usage with department_detail field using custom serializer

### 📋 Technical Improvements
- **Added drf-spectacular import**: Imported extend_schema_field decorator for type hint support
- **Custom field implementation**: Created GenericForeignKeyField class for consistent GenericForeignKey serialization
- **Type safety**: All SerializerMethodField methods now have explicit return type declarations
- **Schema compliance**: Full compatibility with drf-spectacular OpenAPI schema generation

### 🚫 Resolved Warnings
- Fixed "unable to resolve type hint" warnings for all serializer method fields
- Resolved Pipeline.department model field resolution issues
- Eliminated DRF Spectacular W001 warnings across all serializers

## [1.0.5] - 2025-09-28

### 🚀 Complete Resubmission & Delegation Implementation
- **Enhanced resubmission logic**: Implemented proper `after_resubmission` handler with stage transitions and workflow event triggers
- **Added delegation logic**: New `after_delegate` handler with delegate user assignment and workflow event integration
- **WorkflowApprovalSerializer integration**: All approval actions (approve, reject, delegate, resubmission) now use `advance_flow` with proper parameter passing
- **Comprehensive test coverage**: Completely rewritten flow tests using WorkflowApprovalSerializer instead of manual assignment

### 🔧 Workflow Engine Improvements
- **Handler integration**: Added `ActionType.AFTER_DELEGATE` and `ActionType.AFTER_RESUBMISSION` workflow event triggers
- **Stage transition logic**: Resubmission properly updates workflow attachment to target resubmission stage
- **Metadata tracking**: Resubmission steps include `resubmission_stage_id` in extra_fields for audit trail
- **Error handling**: Improved error handling and validation in serializer save method

### 📋 Testing & Validation
- **advance_flow integration tests**: Added comprehensive mocking tests to verify correct parameter passing to approval workflow
- **End-to-end flow tests**: New tests validate complete approval progression using proper serializer patterns
- **Real workflow simulation**: Tests now use actual WorkflowApprovalSerializer patterns from production implementations

### 📚 Documentation Updates
- **Feature highlights**: Updated README with new resubmission and delegation capabilities
- **Implementation notes**: Added documentation about workflow event triggers and stage transitions
- **Known limitations**: Documented step number conflict issue in approval workflow package for resubmission edge cases

## [1.0.4] - 2025-09-27

### 🔄 Clone Tracking & API Improvements
- **Added `cloned_from` field**: All workflow models (WorkFlow, Pipeline, Stage) now automatically track their clone origin
- **Enhanced clone functionality**: Base clone method automatically sets clone relationships and handles field copying
- **Improved API consistency**: Renamed `department_object_id` to `department_id` for cleaner, more intuitive API

### 📚 Configuration Documentation
- **Comprehensive configuration guide**: Added detailed DEPARTMENT_MODEL setting documentation to README
- **Flexible department mapping**: Document support for mapping departments to any model (custom models, auth.Group, etc.)
- **Developer-friendly examples**: Enhanced configuration examples with real-world use cases

### 🛠 Technical Improvements
- **Optimized service functions**: Enhanced workflow data retrieval functions with better performance
- **Updated migrations**: Clean field renaming with proper migration handling
- **Code quality**: Applied formatting improvements with isort and black

### 📋 Migration Notes
- **Seamless upgrade**: Field rename handled transparently in migrations
- **No breaking changes**: All existing functionality preserved
- **130 tests passing**: Full test coverage maintained

---

## [1.0.3] - 2025-09-27

### 🔧 Model Updates
- Allowed `null=True` on timestamp and related fields to improve migration flexibility
- Ensures smoother installation on existing databases without requiring defaults

### 🛠 Migration Notes
- If upgrading from `1.0.2`, run migrations to apply the `null=True` changes
- New installs are not affected

---

## [1.0.2] - 2025-07-15

### 🚀 Enhancements
- **Refactored Department** to be fully generic and non-blocking for developer usage
- **Updated Company model**: defaults to `AUTH_USER_MODEL` for better integration
- **Optimized service helpers**: added utilities such as `get_detailed_workflow_data` with focus on performance
- **Developer support APIs**: ready-made endpoints to simplify implementation and accelerate onboarding

### 🛠 Technical Improvements
- Refined model structure for clarity and future-proofing
- Improved separation between workflow orchestration and developer integration layers

### 📋 Migration Notes
- Fully backward compatible
- Developers can now use generic departments without schema changes

---

## [1.0.1] - 2024-12-27

### 🎉 Production-Ready Release
This release marks the completion of extensive testing, optimization, and internationalization work, making django-dynamic-workflows fully production-ready for enterprise deployment.

### ✅ Test Coverage & Quality Improvements
- **Achieved 100% test pass rate**: Fixed all 58 failing tests, now 69/69 tests pass
- **Added comprehensive test mocking**: Optimized test execution speed by 43% (70s → 40s)
- **Enhanced test reliability**: Added proper fixtures and database optimization
- **Improved error handling**: Better validation and error messages throughout

### 🌍 Internationalization & Localization
- **Full Arabic translation support**: Complete translation of all user-facing text
- **Enhanced English translations**: Refined and standardized all English text
- **RTL support**: Right-to-left text rendering for Arabic interface
- **Dynamic language switching**: API responses adapt to request language headers
- **Translated components**:
  - Model verbose names and field labels
  - Validation error messages and API responses
  - Email templates and notifications
  - Admin interface and help text

### 📊 Advanced Logging & Monitoring
- **Structured logging system**: Comprehensive workflow operation tracking
- **Performance monitoring**: Execution time tracking for optimization
- **Contextual logging**: Rich metadata for debugging and analysis
- **Workflow event tracking**: Complete audit trail of all workflow operations
- **Error tracking**: Detailed error logging with context information

### 🚀 Performance Optimizations
- **Faster test execution**: Comprehensive mocking strategy for slow operations
- **Database optimizations**: Reduced query count and improved caching
- **Email backend mocking**: Eliminated slow email operations in tests
- **Memory usage improvements**: Optimized object creation and cleanup

### 🔧 Developer Experience Enhancements
- **Better error messages**: Clear, actionable error descriptions in both languages
- **Improved documentation**: Enhanced README with clearer examples
- **Translation management**: Added management commands for translation compilation
- **Development tools**: Optimized pytest configuration and test fixtures

### 📦 Package Improvements
- **Updated dependencies**: Removed version pinning for latest compatibility
- **Enhanced metadata**: Improved package description and keywords
- **Better structure**: Organized code with clear separation of concerns
- **Documentation updates**: Added TRANSLATIONS.md with comprehensive i18n guide

### 🛠 Technical Improvements
- **Serializer enhancements**: Better validation logic and error handling
- **Service layer optimization**: More efficient workflow operations
- **Model improvements**: Enhanced progress calculation and status management
- **API refinements**: More robust request/response handling

### 📋 Migration Notes
- All existing functionality remains backward compatible
- New translation files need to be compiled: `python manage.py compilemessages`
- Recommended to update to latest dependency versions
- Enhanced logging may increase log volume (configure appropriately)

### 🎯 Use Case Validation
Successfully tested for:
- CRM workflow replacement scenarios
- Multi-tenant enterprise applications
- High-volume workflow processing
- International deployments requiring Arabic/English support
- Complex approval processes with multiple stages

---

## [1.0.0] - 2024-09-26

### Added
- Initial release of Django Dynamic Workflows
- Generic workflow attachment system for any Django model
- Database-stored configurable actions with inheritance system
- Integration with django-approval-workflow package
- WorkFlow, Pipeline, Stage hierarchical structure
- WorkflowAction model with database-stored function paths
- Action inheritance: Stage → Pipeline → Workflow → Default
- Default email actions for all workflow events
- WorkflowAttachment model for generic model binding
- WorkflowConfiguration for model registration
- Comprehensive admin interface
- Action types: AFTER_APPROVE, AFTER_REJECT, AFTER_RESUBMISSION, AFTER_DELEGATE, AFTER_MOVE_STAGE, AFTER_MOVE_PIPELINE, ON_WORKFLOW_START, ON_WORKFLOW_COMPLETE
- Dynamic function execution system
- Rich context passing to action functions
- Progress tracking and status management
- API serializers for workflow approval actions
- Comprehensive usage examples and documentation

### Features
- Attach workflows to any model without hardcoded relationships
- Configure workflow actions dynamically in database
- Execute Python functions by database-stored paths
- Smart email notifications with automatic recipient detection
- Workflow progression through approval actions only
- Error resilient action execution with logging
- Django admin integration with rich interfaces
- Support for metadata and custom parameters

### Dependencies
- Django >= 4.0
- django-approval-workflow >= 0.8.0
