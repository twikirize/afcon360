# AFCON360 Project Tree (generated: 2026-08-26 14:30:00)

├───_engineering_verification/
├───app/
├───accommodation/
│   ├───models/
│   │   ├───__init__.py
│   │   ├───availability.py
│   │   ├───booking.py
│   │   ├───booking_payment.py
│   │   ├───booking_policy.py
│   │   ├───commission.py
│   │   ├───feedback.py
│   │   ├───guest_identity.py
│   │   ├───guest_profile.py
│   │   ├───guest_registration.py
│   │   ├───host_profile.py
│   │   ├───moderation.py
│   │   ├───platform_override.py
│   │   ├───property.py
│   │   ├───property_document.py
│   │   ├───property_payment_method.py
│   │   ├───review.py
│   │   ├───room.py
│   │   └───wishlist.py
│   ├───services/
│   │   ├───payment_processors/
│   │   │   ├───__init__.py
│   │   │   ├───base.py
│   │   │   ├───card_processor.py
│   │   │   ├───invoice_processor.py
│   │   │   ├───mobile_money_processor.py
│   │   │   ├───mock_gateway_processor.py
│   │   │   └───wallet_processor.py
│   │   ├───__init__.py
│   │   ├───abuse_prevention_service.py
│   │   ├───ai_search_service.py
│   │   ├───ai_trip_planner_service.py
│   │   ├───availability_service.py
│   │   ├───blockchain_reviews_service.py
│   │   ├───booking_service.py
│   │   ├───competitive_intelligence_service.py
│   │   ├───dynamic_pricing_service.py
│   │   ├───gamified_loyalty_service.py
│   │   ├───guest_dashboard_service.py
│   │   ├───host_service.py
│   │   ├───hyper_personalization_service.py
│   │   ├───identity_service.py
│   │   ├───immersive_tour_service.py
│   │   ├───marketplace_service.py
│   │   ├───media_service.py
│   │   ├───moderation_service.py
│   │   ├───payment_option_service.py
│   │   ├───payment_policy_service.py
│   │   ├───predictive_availability_service.py
│   │   ├───pricing_service.py
│   │   ├───readiness_service.py
│   │   ├───review_service.py
│   │   ├───search_service.py
│   │   ├───trust_service.py
│   │   ├───urgency_service.py
│   │   ├───verification_engine.py
│   │   └───voice_booking_service.py
│   ├───state_machine/
│   │   ├───__init__.py
│   │   └───booking_states.py
│   ├───utils/
│   │   └───decorators.py
│   ├───__init__.py
│   ├───forms.py
│   ├───listeners.py
│   ├───routes.py
│   ├───sockets.py
│   └───utils.py
├───admin/
│   ├───admin_services/
│   │   ├───__init__.py
│   │   ├───ai_detection.py
│   │   ├───analytics_service.py
│   │   ├───content_safety.py
│   │   ├───cross_platform.py
│   │   ├───escalation_workflow.py
│   │   ├───moderation_queue.py
│   │   ├───payment_methods.py
│   │   └───training_system.py
│   ├───auditor/
│   │   ├───__init__.py
│   │   └───routes.py
│   ├───compliance/
│   │   ├───__init__.py
│   │   ├───models.py
│   │   ├───routes.py
│   │   └───services.py
│   ├───models/
│   │   ├───__init__.py
│   │   ├───core.py
│   │   ├───emergency_access.py
│   │   └───moderation.py
│   ├───moderator/
│   │   ├───__init__.py
│   │   ├───pipeline.py
│   │   ├───registry.py
│   │   └───routes.py
│   ├───owner/
│   │   ├───api/
│   │   │   └───module_api.py
│   │   ├───__init__.py
│   │   ├───audit.py
│   │   ├───csp_routes.py
│   │   ├───decorators.py
│   │   ├───escrow_routes.py
│   │   ├───escrow_services.py
│   │   ├───models.py
│   │   ├───rate_limit_notifications.py
│   │   ├───rate_limit_service.py
│   │   ├───routes.py
│   │   ├───security_routes.py
│   │   ├───security_service.py
│   │   ├───security_settings.py
│   │   ├───settings.md
│   │   ├───utils.py
│   │   └───wallet_config.py
│   ├───route_modules/
│   │   ├───__init__.py
│   │   ├───accommodation_admin.py
│   │   ├───event_manager.py
│   │   ├───org_admin.py
│   │   ├───org_member.py
│   │   ├───settings.py
│   │   ├───tourism_admin.py
│   │   ├───transport_admin.py
│   │   └───wallet_admin.py
│   ├───services/
│   │   └───__init__.py
│   ├───staff/
│   │   └───__init__.py
│   ├───support/
│   │   ├───__init__.py
│   │   └───routes.py
│   ├───__init__.py
│   ├───decorators.py
│   ├───hooks.py
│   ├───models.py
│   ├───routes.py
│   ├───routes_ultimate.py
│   ├───services.py
│   └───trust_settings.py
├───api/
│   └───health.py
├───audit/
│   ├───__init__.py
│   ├───comprehensive_audit.py
│   ├───forensic_audit.py
│   ├───models.py
│   └───user.py
├───auth/
│   ├───services/
│   │   └───org.py
│   ├───models/
│   │   ├───__init__.py
│   │   └───delegation.py
│   ├───__init__.py
│   ├───config_model.py
│   ├───decorators.py
│   ├───delegation.py
│   ├───email.py
│   ├───email_validation.py
│   ├───helpers.py
│   ├───kyc_compliance.py
│   ├───kyc_routes.py
│   ├───onboarding_routes.py
│   ├───otp_service.py
│   ├───otp_store.py
│   ├───ownership.py
│   ├───password_policy.py
│   ├───pending_registration.py
│   ├───policy.py
│   ├───registration_policy.py
│   ├───roles.py
│   ├───routes.py
│   ├───seed_roles.py
│   ├───services.py
│   ├───session_management.py
│   ├───sessions.py
│   ├───test_helpers.py
│   ├───tokens.py
│   └───validators.py
├───backup/
│   └───backup_service.py
├───cli/
│   ├───__init__.py
│   └───owner.py
├───compliance/
│   ├───aml_regulatory_models.py
│   ├───aml_regulatory_service.py
│   └───aml_service.py
├───core/
│   ├───context.py
│   └───model_registry.py
├───Documentation/
│   ├───adr/
│   │   └───ADR-001-events-organizer-semantics.md
│   ├───ADMIN_CSP_MIGRATION_SUMMARY.md
│   ├───ARCHITECTURE_PASS_5_FINAL.md
│   ├───AUTH_SYSTEM_ARCHITECTURE.md
│   ├───AUTH_SYSTEM_IMPLEMENTATION.md
│   ├───CLI Commands Reference.md
│   ├───CSP_POLICY.md
│   ├───FLASK_LOGIN_STATIC_FILES_BUG.md
│   ├───ID_SYSTEM_RULES.md
│   ├───IDENTITY_POLICIES.md
│   ├───MODERATOR_CAPABILITIES.md
│   ├───MODERATOR_SYSTEM_COMPLETE.md
│   ├───NAV_REDESIGN_PASS_6.md
│   ├───ONBOARDING_IMPLEMENTATION_GUIDE (1).md
│   ├───ONBOARDING_IMPLEMENTATION_GUIDE.md
│   ├───ONBOARDING_IMPLEMENTATION_REPORT.md
│   ├───ONBOARDING_REMEDIATION_PASS_2.md
│   ├───PROFILE_KYC_SYSTEM.md
│   ├───RATE_LIMITING_IMPLEMENTATION.md
│   ├───RECONCILE_WALLET.md
│   ├───SESSION_EXPORT_CSP_MIGRATION_2026-04-27.md
│   ├───SYSTEM_OVERVIEW.md
│   ├───TRUST_BASED_SECURITY.md
│   └───WALLET_AND_USER IDENTITIES.MD
├───event_accommodation/
│   ├───models/
│   │   ├───__init__.py
│   │   ├───badge.py
│   │   ├───opportunity.py
│   │   └───visibility.py
│   ├───services/
│   │   ├───badge_service.py
│   │   ├───discovery_service.py
│   │   ├───invitation_service.py
│   │   └───matching_service.py
│   └───__init__.py
├───events/
│   ├───__init__.py
│   ├───assignment.py
│   ├───attendee_accounts.py
│   ├───bulk_upload.py
│   ├───constants.py
│   ├───events.md
│   ├───Events_CONTEXT.md
│   ├───metrics_service.py
│   ├───models.py
│   ├───payment_config.py
│   ├───payment_service.py
│   ├───permissions.py
│   ├───phase1.md
│   ├───README.md
│   ├───routes.py
│   ├───routes_accommodation.py
│   ├───routes_community_hosts.py
│   ├───services.py
│   ├───settings_model.py
│   ├───settings_routes.py
│   ├───signal_handlers.py
│   ├───signals.py
│   ├───start.md
│   ├───tasks.py
│   ├───trust_service.py
│   └───view_models.py
├───feed/
│   ├───__init__.py
│   ├───models.py
│   ├───routes.py
│   └───services.py
├───monitor/
│   ├───__init__.py
│   ├───broadcaster.py
│   └───routes.py
├───fan/
│   ├───services/
│   │   └───fan_profile_service.py
│   ├───__init__.py
│   ├───GEMINI_AGENT_FAN_MERGE.md
│   ├───migrate_fan_to_profile.py
│   ├───models.py
│   └───routes.py
├───forms/
│   ├───__init__.py
│   ├───booking_forms.py
│   ├───driver_forms.py
│   ├───incident_forms.py
│   ├───organisation_forms.py
│   ├───organization_forms.py
│   ├───settings_forms.py
│   └───vehicle_forms.py
├───identity/
│   ├───individuals/
│   │   ├───__init__.py
│   │   ├───individual_document.py
│   │   └───individual_verification.py
│   ├───models/
│   │   ├───__init__.py
│   │   ├───compliance_audit_log.py
│   │   ├───compliance_settings.py
│   │   ├───kyb.py
│   │   ├───licence_document.py
│   │   ├───note.py
│   │   ├───organisation.py
│   │   ├───organisation_controller.py
│   │   ├───organisation_member.py
│   │   ├───organization_types.py
│   │   ├───roles_permission.py
│   │   └───user.py
│   ├───services/
│   │   ├───__init__.py
│   │   ├───organization_permissions.py
│   │   ├───organization_registration.py
│   │   └───user_roles.py
│   ├───__init__.py
│   ├───routes.py
│   └───services.py
├───kyc/
│   ├───__init__.py
│   ├───models.py
│   ├───nira_verification.py
│   ├───routes.py
│   ├───services.py
│   └───upgrade_routes.py
├───media/
│   ├───processors/
│   │   ├───__init__.py
│   │   ├───document.py
│   │   ├───image.py
│   │   └───video.py
│   ├───storage/
│   │   ├───__init__.py
│   │   ├───local.py
│   │   └───oci.py
│   ├───utils/
│   │   ├───content_moderator.py
│   │   ├───monitoring.py
│   │   ├───perceptual_hash.py
│   │   ├───quota_manager.py
│   │   └───virus_scanner.py
│   ├───__init__.py
│   ├───admin_routes.py
│   ├───metrics.py
│   ├───models.py
│   ├───routes.py
│   ├───service.py
│   ├───settings_service.py
│   ├───tasks.py
│   └───validators.py
├───middleware/
│   └───reload_modules.py
├───models/
│   ├───analytics.py
│   ├───audit.py
│   ├───base.py
│   ├───notification.py
│   ├───system_config.py
│   └───theme.py
├───notifications/
│   ├───channel_handlers/
│   │   ├───__init__.py
│   │   ├───email.py
│   │   ├───in_app.py
│   │   ├───push.py
│   │   ├───sms.py
│   │   └───webhook.py
│   ├───events/
│   │   ├───__init__.py
│   │   ├───bus.py
│   │   ├───consumers.py
│   │   ├───context.py
│   │   ├───exceptions.py
│   │   ├───models.py
│   │   ├───outbox.py
│   │   ├───policy.py
│   │   ├───publisher.py
│   │   ├───registry.py
│   │   ├───replay.py
│   │   ├───routes.py
│   │   ├───schemas.py
│   │   ├───tasks.py
│   │   └───webhooks.py
│   ├───integrations/
│   │   └───__init__.py
│   ├───__init__.py
│   ├───_notification_implement.md
│   ├───context.py
│   ├───listeners.py
│   ├───mock_data.py
│   ├───models.py
│   ├───pages.py
│   ├───preferences.py
│   ├───README.md
│   ├───routes.py
│   ├───services.py
│   ├───settings.py
│   ├───signals.py
│   ├───sms_service.py
│   ├───tasks.py
│   ├───template_loader.py
│   └───utils.py
├───owner/
│   └───routes/
│       ├───role_management.py
│       └───settings.py
├───profile/
│   ├───services/
│   │   ├───__init__.py
│   │   └───change_request_service.py
│   ├───__init__.py
│   ├───models.py
│   └───routes.py
├───tasks/
│   ├───accommodation_reminders.py
│   ├───cleanup.py
│   ├───reconcile.py
│   └───webhook_processor.py
├───tools/
│   ├───inspect_project.py
│   ├───theme_routes.py
│   └───theme_service.py
├───tourism/
│   ├───__init__.py
│   └───routes.py
├───tournament/
│   ├───__init__.py
│   └───routes.py
├───transport/
│   ├───api/
│   │   ├───__init__.py
│   │   ├───analytic_routes.py
│   │   ├───booking_routes.py
│   │   ├───dashboard_routes.py
│   │   ├───driver_routes.py
│   │   ├───incident_routes.py
│   │   ├───organisation_routes.py
│   │   ├───route_routes.py
│   │   ├───routes.py
│   │   ├───settings_routes.py
│   │   ├───utils.py
│   │   └───vehicle_routes.py
│   ├───services/
│   │   ├───__init__.py
│   │   ├───booking_service.py
│   │   ├───dashboard_service.py
│   │   ├───external_platforms.py
│   │   ├───future_adds.py
│   │   ├───matching_service.py
│   │   ├───notification_service.py
│   │   ├───payment_service.py
│   │   ├───promotion_service.py
│   │   ├───provider_service.py
│   │   ├───settings_service.py
│   │   └───tracking_service.py
│   ├───utils/
│   │   ├───__init__.py
│   │   └───helpers.py
│   ├───__init__.py
│   ├───decorator.py
│   ├───event_listeners.py
│   ├───listeners.py
│   ├───models.py
│   ├───routes.py
│   └───view_models.py
├───user/
│   ├───routes.py
│   └───use_dashboard.md
├───utils/
│   ├───__init__.py
│   ├───analytics.py
│   ├───audit.py
│   ├───caching.py
│   ├───db_retry.py
│   ├───error_handler.py
│   ├───exceptions.py
│   ├───flash_helpers.py
│   ├───id_guard.py
│   ├───id_helpers.py
│   ├───id_kinds.py
│   ├───id_validator.py
│   ├───idempotency.py
│   ├───immutable_fields.py
│   ├───module_disabled.py
│   ├───module_guard.py
│   ├───module_switch.py
│   ├───module_toggle_service.py
│   ├───money.py
│   ├───monitoring.py
│   ├───qr.py
│   ├───rate_limiting.py
│   ├───redis_lock.py
│   ├───security.py
│   ├───slugs.py
│   ├───template_helpers.py
│   ├───transactions.py
│   ├───url.py
│   ├───validators.py
│   └───widget_loader.py
├───wallet/
│   ├───api/
│   │   ├───__init__.py
│   │   ├───admin_api.py
│   │   ├───admin_webhook_routes.py
│   │   ├───fx_api.py
│   │   ├───wallet_api.py
│   │   └───webhooks.py
│   ├───middleware/
│   │   ├───__init__.py
│   │   ├───idempotency.py
│   │   ├───kill_switch.py
│   │   ├───wallet_activation.py
│   │   ├───wallet_check.py
│   │   └───wallet_check.py (new file)
│   ├───models/
│   │   ├───__init__.py
│   │   ├───adjustment.py
│   │   ├───admin_audit.py
│   │   ├───aggregator.py
│   │   ├───audit.py
│   │   ├───commission.py
│   │   ├───config.py
│   │   ├───creation_tracker.py
│   │   ├───fraud_alert.py
│   │   ├───fraud_detection.py
│   │   ├───fx.py
│   │   ├───ledger.py
│   │   ├───nonce_protection.py
│   │   ├───payment_method.py
│   │   ├───payout.py
│   │   ├───reconciliation.py
│   │   ├───transaction.py
│   │   ├───travel_rule.py
│   │   └───webhook_event.py
│   ├───payments/
│   │   ├───__init__.py
│   │   ├───alipay.py
│   │   ├───flutterwave.py
│   │   ├───mobile_money.py
│   │   ├───paypal.py
│   │   ├───paystack.py
│   │   ├───visa.py
│   │   └───wechat.py
│   ├───repositories/
│   │   ├───__init__.py
│   │   ├───account_repository.py
│   │   ├───commission_repository.py
│   │   ├───ledger_repository.py
│   │   ├───payout_repository.py
│   │   ├───transaction_repository.py
│   │   ├───wallet_repository.py
│   │   └───webhook_repository.py
│   ├───routes/
│   │   └───regulator_api.py
│   ├───services/
│   │   ├───__init__.py
│   │   ├───admin_audit_service.py
│   │   ├───aggregator_service.py
│   │   ├───commission_service.py
│   │   ├───compliance_engine.py
│   │   ├───currency_service.py
│   │   ├───fraud_detection_service.py
│   │   ├───fx_service.py
│   │   ├───identity_verification_service.py
│   │   ├───kyc_limit_service.py
│   │   ├───nonce_protection_service.py
│   │   ├───payment_gateway.py
│   │   ├───payout_service.py
│   │   ├───reconciliation_service.py
│   │   ├───regulator_service.py
│   │   ├───regulatory_reporting.py
│   │   ├───suspicious_activity_service.py
│   │   ├───travel_rule_service.py
│   │   ├───wallet_creation_tracker.py
│   │   ├───wallet_notifications.py
│   │   ├───wallet_service.py
│   │   ├───wallet_status_service.py
│   │   └───webhook_service.py
│   ├───__init__.py
│   ├───AFCON360_WALLET_AUDIT_ARCHIVE.md
│   ├───AFCON360_WALLET_AUDIT_REPORT.md
│   ├───AFCON360_WALLET_PRODUCTION_GUIDE.md
│   ├───decorators.py
│   ├───ESCROW.md
│   ├───ESCROW_ARCHITECTURE.md
│   ├───exceptions.py
│   ├───implement.md
│   ├───IMPLEMENTATION_REPORT.md
│   ├───PAYMENT_ARCHITECTURE.md
│   ├───routes.py
│   ├───routes_pin.py
│   ├───SECURITY_FRAUD_PREVENTION.md
│   ├───validators.py
│   └───WALLET_ARCHITECTURE.md
├───__init__.py
├───celery_app.py
├───CHECK_DUAL_ID_ISSUES.md
├───cli.py
├───config.py
├───extensions.py
├───placeholder.py
├───providers.py
├───routes.py
└───utils.py
├───docker/
└───nginx/
    ├───afcon360.conf
    └───nginx.conf
├───docs/
├───accommodation/
│   └───IMPLEMENTATION_VERIFICATION_REPORT.md
├───saved_work/
│   ├───create_tables.sh
│   ├───docker-compose.yml
│   ├───inspect_db.sh
│   ├───lazy_table_creator.py
│   ├───table_inspector.py
│   └───table_monitor.py
├───enterprise_readiness_assessment.md
└───payment_system_documentation.md
├───Implement/
├───booking_flow - Copy.md
├───booking_flow.md
├───ESCROW_IMPLEMENTATION_BRIEF.md
├───immutable_fileds.md
├───kilo_implemettion.md
└───report.md
├───mcps/
└───idea/
    └───tools/
        ├───build_project.json
        ├───cancel_sql_query.json
        ├───create_new_file.json
        ├───execute_run_configuration.json
        ├───execute_sql_query.json
        ├───execute_terminal_command.json
        ├───find_files_by_glob.json
        ├───find_files_by_name_keyword.json
        ├───generate_inspection_kts_api.json
        ├───generate_inspection_kts_examples.json
        ├───generate_psi_tree.json
        ├───get_all_open_file_paths.json
        ├───get_database_object_description.json
        ├───get_file_problems.json
        ├───get_file_text_by_path.json
        ├───get_project_dependencies.json
        ├───get_project_modules.json
        ├───get_repositories.json
        ├───get_run_configurations.json
        ├───get_symbol_info.json
        ├───list_database_connections.json
        ├───list_database_schemas.json
        ├───list_directory_tree.json
        ├───list_recent_sql_queries.json
        ├───list_schema_object_kinds.json
        ├───list_schema_objects.json
        ├───open_file_in_editor.json
        ├───preview_table_data.json
        ├───read_file.json
        ├───reformat_file.json
        ├───rename_refactoring.json
        ├───replace_text_in_file.json
        ├───run_inspection_kts.json
        ├───runNotebookCell.json
        ├───search_file.json
        ├───search_in_files_by_regex.json
        ├───search_in_files_by_text.json
        ├───search_regex.json
        ├───search_symbol.json
        ├───search_text.json
        ├───test_database_connection.json
        ├───validate_inspection_kts.json
        ├───xdebug_control_session.json
        ├───xdebug_evaluate_expression.json
        ├───xdebug_get_debugger_status.json
        ├───xdebug_get_frame_values.json
        ├───xdebug_get_stack.json
        ├───xdebug_get_threads.json
        ├───xdebug_get_value_by_path.json
        ├───xdebug_list_breakpoints.json
        ├───xdebug_remove_breakpoint.json
        ├───xdebug_run_to_line.json
        ├───xdebug_set_breakpoint.json
        ├───xdebug_set_variable.json
        └───xdebug_start_debugger_session.json
├───migrations/
├───versions/
│   ├───0260706_add_system_configs_table.py
│   ├───048ce13b1bfe_add_group_label_to_event_registrations.py
│   ├───04d05161190f_add_booking_commission.py
│   ├───07c931b46c36_add_server_default_to_processing_.py
│   ├───0989dcdb672f_add_booking_owner_identity_columns_.py
│   ├───0a82c41d6cb0_add_compliance_case_notes_and_.py
│   ├───0df1a94b3534_add_multi_guest_booking_fields_for_.py
│   ├───0e5655df8acd_add_accommodation_architecture_.py
│   ├───100e8db8a57f_enforce_inventory_block_reason_enum_at_.py
│   ├───15a1f8d5f2bb_after_fixing_mgration_errors_clean_up.py
│   ├───1787438348_sync_check_constraints.py
│   ├───18288f7196e0_add_accommodation_query_performance_.py
│   ├───1d30290f4f67_add_room_types_and_inventory_blocks_.py
│   ├───20260627_add_media_tables.py
│   ├───20260629_add_media_enhancements.py
│   ├───20260701_add_room_type_id_to_bookings.py
│   ├───20260701_add_room_types_and_inventory_blocks.py
│   ├───20260718_1951_make_organisations_compliance_case_id_.py
│   ├───20260724_1040_add_status_check_constraint.py
│   ├───20260811_1125_sync_compliance_notification_.py
│   ├───23a2748dc5d1_add_organizer_profiles_table.py
│   ├───2459945a58a4_add_fan_profiles_and_dashboard_contexts.py
│   ├───2499ed67dc8c_add_email_verified_at_and_phone_.py
│   ├───273c374bade0_add_missing_columns_to_system_configs.py
│   ├───2a0f0f631427_add_wishlist_table.py
│   ├───2d264b2fdc99_add_host_profiles_property_documents_.py
│   ├───2fa5d406a740_make_accommodation_datetimes_timezone_.py
│   ├───31eef7f1f4a2_add_accommodation_booking_payments.py
│   ├───330ce9bd4864_add_notifications_and_property_.py
│   ├───3395bb381c6a_add_accommodation_room_holds_guest_.py
│   ├───366d06e59f9c_add_guest_complaints_and_booking_.py
│   ├───396efe6667ff_add_verification_level_security_deposit_.py
│   ├───4855a635e4fd_add_acc_link_token_hash_and_acc_link_.py
│   ├───4f9a33fc2475_add_wallet_creation_events_table.py
│   ├───5582ce532c6f_add_agents_enabled_to_wallet_config.py
│   ├───5661738e7748_add_archived_columns_to_property.py
│   ├───5796d94e890f_add_approved_to_property_status_check_.py
│   ├───586b35d32d53_add_property_public_id.py
│   ├───5b1b44079291_add_account_fk_constraints.py
│   ├───5c7b672dd5e2_add_ck_inventory_block_reason_valid_to_.py
│   ├───69095234e1b0_add_booked_by_snapshot_fields_to_.py
│   ├───6e1eea37b83b_add_notification_module_column_with_.py
│   ├───6e9dbae2ac1a_replace_roomcategory_with_roomtype_in_.py
│   ├───721f6a09485d_merge_media_migration.py
│   ├───76c9e829b84b_add_rate_limit_settings_table.py
│   ├───8045e2548d4b_add_accommodation_room_holds_version_2.py
│   ├───8120b21c333e_add_booking_approval_and_property_.py
│   ├───87f479367218_add_organizer_messages_table.py
│   ├───88d91ff49abe_add_platform_account_fields.py
│   ├───8a0deccce6f6_initial_full_schema_baseline.py
│   ├───91911883eb58_drop_redundant_organizer_profiles_.py
│   ├───961bd8f150b3_aml_regulatory_and_biginteger_pk.py
│   ├───978aa0c43706_add_published_status_to_property_.py
│   ├───978f0c336ca4_add_cash_protection_fields_to_property_.py
│   ├───9a0b1c2d3e4f_backfill_event_owner_roles.py
│   ├───a7c3e91b4d28_add_users_email_format_check.py
│   ├───a8dda837031d_add_aggregator_sandbox_live_mode_and_.py
│   ├───a976e4599bfe_merge_final_heads.py
│   ├───ab6dd422c152_initial_schema.py
│   ├───acf73a88632f_add_accommodation_room_holds.py
│   ├───b5b8d696abbf_create_aggregators_table.py
│   ├───b8f317d76694_add_security_deposit_columns_to_bookings.py
│   ├───ba262522c43c_convert_accommodation_enums_to_strings.py
│   ├───bcf13cf9d185_add_created_by_to_inventory_blocks.py
│   ├───c3140d8ec04a_add_profile_change_requests_and_wallet_.py
│   ├───c845c6583732_sync_property_status_check_constraint_.py
│   ├───d95160fba1fd_merge_20260717_rooms.py
│   ├───db911bfe67b9_merge_system_configs_and_other_branch.py
│   ├───ec4fff3b4299_add_media_module_tables.py
│   ├───ec7e4f84cf90_add_idempotency_key_to_booking_payments.py
│   ├───ed6307401623_make_wallet_admin_events_datetimes_.py
│   ├───f2f97ca5a313_add_notification_tables_preferences_.py
│   └───f312046d12e8_create_accommodation_booking_payments_.py
├───alembic.ini
├───env.py
├───README
└───script.py.mako
├───prompts/
├───high_performer_os.html
├───media_implementation.md
├───MEDIA_SYSTEM_MASTER (1).md
├───MEDIA_SYSTEM_MASTER.md
├───refactor_events.md
└───the_plan.md
├───pushups/
├───__init__.py
├───auth.py
└───routes.py
├───Readme's/
├───2026-04-11_events_concurrency_fixes.md
├───admin-system-analysis.md
├───ALL_QA.md
├───AML_COMPLIANCE_GUIDE.md
├───App_Roadmap.md
├───ARCHITECTURE_PASS_5_IMPLEMENTATION_REPORT.md
├───DASHBOARD_FIXES_COMPLETE.md
├───DEPLOYMENT_GUIDE.md
├───DEPLOYMENT_READINESS_ASSESSMENT.md
├───ENDPOINT_FIXES_SUMMARY.md
├───endpoints.md
├───ERROR_FIXES_SUMMARY.md
├───IMPERSONATION_SYSTEM_STATUS.md
├───media_handling.md
├───Moderation.md
├───MODULE_ISOLATION_AUDIT.md
├───MODULE_ISOLATION_IMPLEMENTATION_REPORT.md
├───MODULE_ISOLATION_INTEGRATION_REPORT.md
├───OWNER_SYSTEM_COMPLETE.md
├───P0_FIXES_REPORT.md
├───PRODUCTION_README.md
├───registration_report2_15-04
├───reistration & user mgt.md
├───reistration_report_15_04.md
├───report.md
├───security_assessment.md
├───SECURITY_FIXES_COMPLETE.md
├───SECURITY_FIXES_IMPLEMENTED.md
├───SECURITY_FIXES_README.md
├───SECURITY_FIXES_README.zip
├───tests.md
├───ULTIMATE_ADMIN_SYSTEM.md
├───USER_ROLE_MGT.MD
├───VERIFICATION_REPORT.md
├───WALLET_DEPLOYMENT_AUDIT.md
├───WALLET_IMPLEMENTATION_STATUS.md
├───WALLET_STATUS_REPORT.md
└───WALLET_SYSTEM_ANALYSIS.md
├───reports/
├───security/
│   ├───identity_audit_20260718_084105.json
│   └───identity_audit_20260718_084222.json
├───media_system_implementation_report.md
├───MEDIA_SYSTEM_SETUP_GUIDE.md
└───wallet_deepseek_audit.md
├───rules/
├───ask-debug-mode-rules.md
├───code-mode-rules.md
└───global-rules.md
├───scripts/
├───reports/
│   ├───database_id_inventory.md
│   ├───id_field_inventory.md
│   └───id_usage_audit.md
├───security/
│   └───identity_audit.py
├───backfill_room_types.py
├───check_id_usage.py
├───complete_fix.py
├───create_migration.py
├───create_system_configs.py
├───db_audit.py
├───dumpedfiles.py
├───fix_remaining.py
├───generate_missing_migrations.py
├───init_settings.py
├───inspect_database_ids.py
├───inspect_id_fields.py
├───inspect_id_usage.py
├───inspect_identity_map.py
├───lazy_table_creator.py
├───migrate_enums_to_strings.py
├───migrate_fan_profiles.py
├───migration_agent_config.py
├───reset_test_db.py
├───restore_git.py
├───run_backfill.py
├───scan_null_bytes.py
├───script.js
├───seed_payment_methods.py
├───seed_roles.py
├───seed_system_configs.py
├───seed_test_marketplace_accounts.py
├───setup_platform_escrow.py
├───setup_test_db.py
├───setup_test_db_schema.py
├───table_inspector.py
├───table_monitor.py
├───test_flow.py
└───verify_bookings.py
├───static/
├───css/
│   ├───fan/
│   │   └───dashboard.css
│   ├───generated/
│   │   ├───global-theme.css
│   │   └───user-1.css
│   ├───global/
│   │   ├───home.css
│   │   ├───mobile-utilities.css
│   │   ├───style.css
│   │   ├───theme-components.css
│   │   └───theme-variables.css
│   ├───modules/
│   │   ├───accommodation/
│   │   │   ├───calendar.css
│   │   │   ├───checkout.css
│   │   │   ├───detail.css
│   │   │   ├───explore.css
│   │   │   ├───home.css
│   │   │   ├───host-bookings.css
│   │   │   ├───host-dashboard.css
│   │   │   ├───moderate.css
│   │   │   ├───moderate_base.css
│   │   │   ├───moderate_detail.css
│   │   │   └───search.css
│   │   ├───admin/
│   │   │   ├───admin.css
│   │   │   └───owner.css
│   │   ├───events/
│   │   │   ├───attendee.css
│   │   │   ├───base_events.css
│   │   │   ├───dashboard.css
│   │   │   ├───forms.css
│   │   │   ├───hub.css
│   │   │   ├───public.css
│   │   │   └───scanner.css
│   │   ├───media/
│   │   │   └───media.css
│   │   ├───transport/
│   │   │   ├───base.css
│   │   │   ├───bookings.css
│   │   │   ├───dashboard.css
│   │   │   ├───drivers.css
│   │   │   └───vehicles.css
│   │   ├───user/
│   │   │   ├───dashboard.css
│   │   │   └───shell.css
│   │   └───wallet/
│   │       ├───deposit.css
│   │       ├───send.css
│   │       └───wallet.css
│   └───dashboard.css
├───icons/
│   ├───icon-192.png
│   └───icon-512.png
├───images/
│   ├───company-brain-template.md
│   ├───creator-media-cofounder.skill
│   └───no-image.png
├───js/
│   ├───fan/
│   │   └───dashboard.js
│   ├───global/
│   │   ├───main.js
│   │   ├───media-manager.js
│   │   ├───script.js
│   │   └───theme-manager.js
│   ├───modules/
│   │   ├───accommodation/
│   │   │   ├───checkout.js
│   │   │   ├───detail.js
│   │   │   ├───explore.js
│   │   │   ├───host-dashboard-enhanced.js
│   │   │   ├───host-dashboard.js
│   │   │   └───search.js
│   │   ├───admin/
│   │   │   ├───admin_moderation.js
│   │   │   └───moderator_dashboard.js
│   │   ├───events/
│   │   │   ├───event-create.js
│   │   │   └───event-register.js
│   │   └───transport/
│   │       ├───base.js
│   │       ├───booking.js
│   │       ├───charts.js
│   │       ├───dashboard.js
│   │       ├───drivers.js
│   │       ├───mapp.js
│   │       ├───realtime.js
│   │       ├───utils.js
│   │       └───vehicle.js
│   └───theme-manager.js
├───manifest.json
└───MOBILE_OPTIMIZATION.md
├───templates/
├───accommodation/
│   ├───admin/
│   │   ├───_macros.html
│   │   ├───analytics.html
│   │   ├───booking_detail.html
│   │   ├───bookings.html
│   │   ├───financials.html
│   │   ├───pending_properties.html
│   │   ├───properties.html
│   │   ├───property_history.html
│   │   ├───property_history_partial.html
│   │   ├───settings.html
│   │   └───verification.html
│   ├───guest/
│   │   ├───_dashboard_content.html
│   │   ├───amend.html
│   │   ├───checkout.html
│   │   ├───claim_booking.html
│   │   ├───complaint_detail.html
│   │   ├───complaints.html
│   │   ├───confirmation.html
│   │   ├───dashboard.html
│   │   ├───dashboard_pane.html
│   │   ├───detail.html
│   │   ├───my_bookings.html
│   │   ├───pass.html
│   │   ├───register.html
│   │   ├───review_form.html
│   │   └───search.html
│   ├───host/
│   │   ├───listings/
│   │   │   └───create.html
│   │   ├───booking_detail.html
│   │   ├───booking_policy.html
│   │   ├───bookings.html
│   │   ├───calendar.html
│   │   ├───create_listing.html
│   │   ├───dashboard.html
│   │   ├───earnings.html
│   │   ├───edit_listing.html
│   │   ├───property_documents.html
│   │   ├───property_manage.html
│   │   ├───register.html
│   │   ├───room_availability.html
│   │   └───rooms.html
│   ├───Accomodation_module.md
│   ├───booking.md
│   ├───explore.html
│   ├───home.html
│   ├───home_pane.html
│   ├───moderate.html
│   ├───moderate_booking.html
│   ├───moderate_property.html
│   ├───moderate_review.html
│   ├───more_edits.md
│   ├───my_accommodation.html
│   └───my_accommodation_pane.html
├───admin/
│   ├───compliance/
│   │   ├───_aml_nav.html
│   │   ├───aml_attestations.html
│   │   ├───aml_backtest.html
│   │   ├───aml_ctr.html
│   │   ├───aml_jurisdictions.html
│   │   ├───aml_queue.html
│   │   ├───aml_report_detail.html
│   │   ├───aml_reports.html
│   │   ├───aml_retention.html
│   │   ├───aml_scenarios.html
│   │   ├───aml_terminated.html
│   │   ├───aml_training.html
│   │   ├───base_compliance.html
│   │   ├───case_history.html
│   │   ├───cases.html
│   │   ├───create_case.html
│   │   ├───dashboard.html
│   │   ├───data_requests.html
│   │   ├───escalations.html
│   │   ├───generate_report.html
│   │   ├───kyc_queue.html
│   │   ├───licences.html
│   │   ├───organisations.html
│   │   ├───payouts.html
│   │   ├───reports.html
│   │   ├───sar_filing.html
│   │   ├───search.html
│   │   ├───user_audit.html
│   │   ├───user_audit_profile.html
│   │   ├───view_case.html
│   │   ├───view_kyc.html
│   │   └───view_transaction.html
│   ├───moderator/
│   │   ├───_pending_table.html
│   │   ├───ai_analytics.html
│   │   ├───audit_log.html
│   │   ├───base_moderator.html
│   │   ├───categories.html
│   │   ├───content.html
│   │   ├───content_safety.html
│   │   ├───cross_platform.html
│   │   ├───dashboard.html
│   │   ├───escalations.html
│   │   ├───events.html
│   │   ├───flagged.html
│   │   ├───flags.html
│   │   ├───items.html
│   │   ├───kyc.html
│   │   ├───my_queue.html
│   │   ├───orgs.html
│   │   ├───README.md
│   │   ├───settings.html
│   │   ├───stats.html
│   │   ├───training.html
│   │   ├───training_content.html
│   │   ├───transport.html
│   │   ├───transport_booking_view.html
│   │   ├───transport_bookings.html
│   │   ├───transport_driver_view.html
│   │   ├───transport_drivers.html
│   │   ├───transport_third_party.html
│   │   ├───transport_vehicle_view.html
│   │   ├───transport_vehicles.html
│   │   ├───users.html
│   │   ├───view_event.html
│   │   ├───view_flag.html
│   │   ├───view_item.html
│   │   ├───view_kyc.html
│   │   ├───view_org.html
│   │   ├───view_submission.html
│   │   └───view_user.html
│   ├───owner/
│   │   ├───auth_settings.html
│   │   ├───kyc_tiers.html
│   │   └───security_dashboard.html
│   ├───settings/
│   │   ├───analytics.html
│   │   ├───impersonation.html
│   │   ├───moderation.html
│   │   ├───platform.html
│   │   └───system.html
│   ├───wallet/
│   │   └───webhook_detail.html
│   ├───accommodation_admin_dashboard.html
│   ├───admin.html
│   ├───auditor_dashboard.html
│   ├───content_dashboard.html
│   ├───dashboard.html
│   ├───event_manager_dashboard.html
│   ├───global_theme.html
│   ├───kyc_documents.html
│   ├───manage_orgs.html
│   ├───manage_roles.html
│   ├───manage_submissions.html
│   ├───manage_users.html
│   ├───media_settings.html
│   ├───moderator_dashboard.html
│   ├───org_admin_dashboard.html
│   ├───org_audit.html
│   ├───org_member_dashboard.html
│   ├───org_members.html
│   ├───payment_methods.html
│   ├───role_users.html
│   ├───settings.html
│   ├───super_admin_dashboard.html
│   ├───super_admin_settings.html
│   ├───super_dashboard.html
│   ├───support_dashboard.html
│   ├───tourism_admin_dashboard.html
│   ├───transport_admin_dashboard.html
│   ├───trust_settings.html
│   ├───update_profile.html
│   ├───update_user.html
│   ├───user_activity.html
│   ├───view_user.html
│   ├───view_user_ultimate.html
│   ├───wallet_adjustments.html
│   ├───wallet_admin_dashboard.html
│   ├───wallet_commissions.html
│   ├───wallet_control.html
│   ├───wallet_detail.html
│   ├───wallet_stats.html
│   └───wallets.html
├───audit/
│   ├───aml_review.html
│   ├───api_logs.html
│   ├───base_audit.html
│   ├───data_access.html
│   ├───financial_logs.html
│   └───security_events.html
├───auditor/
│   └───dashboard.html
├───auth/
│   ├───recover_question.html
│   ├───recover_request.html
│   ├───switch_role.html
│   ├───verify_options.html
│   ├───verify_otp.html
│   └───verify_signup.html
├───compliance/
│   └───dashboard.html
├───components/
│   ├───audit_timeline.html
│   ├───kyc_badge.html
│   ├───kyc_tier_badge.html
│   ├───media_gallery.html
│   ├───media_upload.html
│   ├───message_button.html
│   ├───mfa_status.html
│   ├───notification_bell.html
│   ├───pending_reviews_widget.html
│   ├───status_badge.html
│   ├───suspicious_activity_widget.html
│   └───verify_banners.html
├───email/
│   ├───message_confirmation.html
│   ├───organizer_message.html
│   └───verification.html
├───errors/
│   ├───404.html
│   └───500.html
├───events/
│   ├───_partials/
│   │   └───attendee_group_cell.html
│   ├───admin/
│   │   ├───org/
│   │   │   └───dashboard.html
│   │   ├───assignment_dashboard.html
│   │   ├───attendees_list.html
│   │   ├───dashboard.html
│   │   ├───events.html
│   │   ├───pending.html
│   │   ├───settings.html
│   │   └───staff.html
│   ├───attendee/
│   │   ├───attendee_dashboard.html
│   │   ├───my_registrations.html
│   │   ├───register.html
│   │   ├───registerO.html
│   │   └───registration_confirmation.html
│   ├───community_host/
│   │   └───register.html
│   ├───organizer/
│   │   ├───accommodation_manage.html
│   │   ├───analytics.html
│   │   ├───attendees.html
│   │   ├───community_hosts.html
│   │   ├───create.html
│   │   ├───edit.html
│   │   ├───messages.html
│   │   ├───my_events.html
│   │   ├───organizer_dashboard.html
│   │   ├───scanner.html
│   │   └───waitlist.html
│   ├───public/
│   │   ├───landing.html
│   │   ├───list.html
│   │   ├───list_pane.html
│   │   └───not_found.html
│   ├───service_provider/
│   │   └───service_provider_dashboard.html
│   ├───event_theme.html
│   ├───events_hub.html
│   ├───moderate.html
│   └───moderate_detail.html
├───fan/
│   ├───components/
│   │   ├───left_pane.html
│   │   ├───middle_pane.html
│   │   ├───mobile_nav.html
│   │   └───right_pane.html
│   └───dashboard.html
├───kyc/
│   ├───complete_profile.html
│   ├───index.html
│   ├───limits.html
│   ├───moderate.html
│   ├───moderate_document.html
│   ├───overview.html
│   ├───status.html
│   ├───upgrade.html
│   ├───verify_address.html
│   ├───verify_national_id.html
│   └───verify_upload.html
├───macros/
│   ├───admin_macros.html
│   ├───booking_macros.html
│   ├───flash_messages.html
│   ├───form_macros.html
│   └───ui_macros.html
├───notifications/
│   ├───email/
│   │   ├───admin_notification.html
│   │   ├───booking_cancelled.html
│   │   ├───booking_confirmation.html
│   │   ├───booking_confirmed.html
│   │   ├───booking_created.html
│   │   ├───booking_update.html
│   │   ├───default.html
│   │   ├───deposit_confirmed.html
│   │   ├───driver_assigned.html
│   │   ├───event_registered.html
│   │   ├───event_reminder.html
│   │   ├───internal_message.html
│   │   ├───internal_reply.html
│   │   ├───kyc_approved.html
│   │   ├───kyc_rejected.html
│   │   ├───login_alert.html
│   │   ├───message_notification.html
│   │   ├───new_signup.html
│   │   ├───password_reset.html
│   │   ├───payment_receipt.html
│   │   ├───payment_received.html
│   │   ├───platform_announcement.html
│   │   ├───property_approved.html
│   │   ├───property_archived.html
│   │   ├───property_changes_requested.html
│   │   ├───property_reinstated.html
│   │   ├───property_rejected.html
│   │   ├───property_restored.html
│   │   ├───property_submitted.html
│   │   ├───property_suspended.html
│   │   ├───review_received.html
│   │   ├───signup_notification.html
│   │   ├───system_alert.html
│   │   ├───transaction_completed.html
│   │   ├───transaction_notification.html
│   │   ├───verification_email.html
│   │   ├───wallet_deposit.html
│   │   ├───wallet_withdrawal.html
│   │   └───withdrawal_completed.html
│   ├───push/
│   │   ├───booking_cancelled.json
│   │   ├───booking_confirmation.json
│   │   ├───booking_created.json
│   │   ├───default.json
│   │   ├───driver_assigned.json
│   │   ├───event_registered.json
│   │   ├───event_reminder.json
│   │   ├───kyc_approved.json
│   │   ├───kyc_rejected.json
│   │   ├───new_signup.json
│   │   ├───password_reset.json
│   │   ├───review_received.json
│   │   ├───system_alert.json
│   │   ├───verification_email.json
│   │   ├───wallet_deposit.json
│   │   └───wallet_withdrawal.json
│   ├───sms/
│   │   ├───booking_cancelled.txt
│   │   ├───booking_confirmation.txt
│   │   ├───booking_created.txt
│   │   ├───default.txt
│   │   ├───driver_assigned.txt
│   │   ├───event_registered.txt
│   │   ├───kyc_approved.txt
│   │   ├───kyc_rejected.txt
│   │   ├───new_signup.txt
│   │   ├───password_reset.txt
│   │   ├───review_received.txt
│   │   ├───system_alert.txt
│   │   ├───verification_email.txt
│   │   ├───wallet_deposit.txt
│   │   └───wallet_withdrawal.txt
│   ├───inbox.html
│   └───messages.html
├───onboarding/
│   ├───_progress_bar.html
│   ├───_wizard_styles.html
│   ├───choose.html
│   ├───choose_individual.html
│   ├───choose_organisation.html
│   ├───driver_step1.html
│   ├───driver_step2.html
│   ├───driver_step3.html
│   ├───event_organiser.html
│   ├───fan.html.archived
│   ├───host_step1.html
│   ├───host_step2.html
│   ├───organisation_step1.html
│   ├───organisation_step2.html
│   └───standard.html
├───org/
│   ├───content_dashboard.html
│   ├───dashboard.html
│   ├───dashboard_old.html
│   ├───members.html
│   ├───members_old.html
│   ├───register.html
│   ├───selector.html
│   ├───settings.html
│   ├───settings_old.html
│   └───wallet.html
├───owner/
│   ├───escrow/
│   │   ├───create.html
│   │   ├───detail.html
│   │   ├───index.html
│   │   ├───settings.html
│   │   └───transactions.html
│   ├───platform_accounts/
│   │   ├───detail.html
│   │   └───index.html
│   ├───role_management/
│   │   ├───audit_log.html
│   │   ├───dashboard.html
│   │   └───users.html
│   ├───wallet_config/
│   │   ├───edit_provider.html
│   │   ├───env_setup.html
│   │   ├───index.html
│   │   ├───providers.html
│   │   └───system.html
│   ├───add_payment_gateway.html
│   ├───admin_audit_log.html
│   ├───aggregator_settings.html
│   ├───audit_logs.html
│   ├───backup_codes.html
│   ├───cash_settings.html
│   ├───compliance_settings.html
│   ├───configure_aml_kyc.html
│   ├───configure_fraud_detection.html
│   ├───configure_nonce_protection.html
│   ├───configure_rate_limiting.html
│   ├───configure_travel_rule.html
│   ├───danger_zone.html
│   ├───dashboard.html
│   ├───error_logs.html
│   ├───impersonate.html
│   ├───later.html
│   ├───manage_aggregators.html
│   ├───manage_regulator_access.html
│   ├───manage_roles.html
│   ├───module_settings.html
│   ├───regulatory_reports.html
│   ├───settings.html
│   ├───super_admins.html
│   ├───system_health.html
│   ├───users.html
│   ├───wallet_capabilities.html
│   └───wallet_settings.html
├───placeholder/
│   └───coming_soon.html
├───profile/
│   ├───account.html
│   ├───account_pane.html
│   ├───edit.html
│   └───public.html
├───shell/
│   └───dashboard_shell.html
├───tourism/
│   ├───moderate.html
│   └───moderate_listing.html
├───transport/
│   ├───admin/
│   │   └───dashboard.html
│   ├───analytics/
│   │   ├───drivers.html
│   │   ├───history.html
│   │   ├───index.html
│   │   ├───performance.html
│   │   ├───revenue.html
│   │   └───vehicles.html
│   ├───bookings/
│   │   ├───_form.html
│   │   ├───assign.html
│   │   ├───edit.html
│   │   ├───history.html
│   │   ├───index.html
│   │   ├───new.html
│   │   ├───payments.html
│   │   ├───show.html
│   │   └───timeline.html
│   ├───dashboard/
│   │   ├───widgets/
│   │   │   ├───booking_card.html
│   │   │   ├───driver_card.html
│   │   │   └───vehicle_card.html
│   │   ├───base_dashboard.html
│   │   ├───index.html
│   │   ├───keep.html
│   │   └───overview.html
│   ├───drivers/
│   │   ├───_form.html
│   │   ├───dashboard.html
│   │   ├───edit.html
│   │   ├───history.html
│   │   ├───index.html
│   │   ├───location.html
│   │   ├───new.html
│   │   ├───show.html
│   │   └───verification.html
│   ├───incidents/
│   │   ├───_form.html
│   │   ├───edit.html
│   │   ├───evidence.html
│   │   ├───history.html
│   │   ├───index.html
│   │   ├───investigate.html
│   │   ├───new.html
│   │   └───show.html
│   ├───organisations/
│   │   ├───_form.html
│   │   ├───dashboard.html
│   │   ├───drivers.html
│   │   ├───edit.html
│   │   ├───index.html
│   │   ├───new.html
│   │   ├───show.html
│   │   └───vehicles.html
│   ├───partials/
│   │   ├───modals/
│   │   │   ├───assign_driver.html
│   │   │   ├───assign_vehicle.html
│   │   │   ├───confirm_delete.html
│   │   │   └───update_status.html
│   │   ├───tables/
│   │   │   ├───booking_row.html
│   │   │   ├───driver_row.html
│   │   │   └───vehicle_row.html
│   │   ├───overview.html
│   │   └───sidebar.html
│   ├───routes/
│   │   ├───_form.html
│   │   ├───edit.html
│   │   ├───history.html
│   │   ├───index.html
│   │   ├───new.html
│   │   ├───schedule.html
│   │   └───show.html
│   ├───settings/
│   │   ├───advanced.html
│   │   ├───booking.html
│   │   ├───general.html
│   │   ├───index.html
│   │   ├───integrations.html
│   │   ├───payment.html
│   │   ├───safety.html
│   │   └───vehicles.html
│   ├───vehicles/
│   │   ├───_form.html
│   │   ├───edit.html
│   │   ├───history.html
│   │   ├───index.html
│   │   ├───location.html
│   │   ├───maintenance.html
│   │   ├───new.html
│   │   └───show.html
│   ├───base.html
│   ├───become_driver.html
│   ├───book.html
│   ├───booking_detatails.html
│   ├───driver_dashboard.html
│   ├───home.html
│   ├───home_pane.html
│   ├───homes.html
│   ├───moderate.html
│   ├───moderate_booking.html
│   ├───moderate_driver.html
│   ├───moderate_vehicle.html
│   ├───register_vehicle.html
│   ├───structure
│   └───vehicle_dashboard.html
├───user/
│   ├───partials/
│   │   ├───_fan_teams_widget.html
│   │   └───_tournament_hero.html
│   ├───settings/
│   │   └───interests.html
│   ├───_pane_base.html
│   ├───_reg_card.html
│   ├───base_user_dashboard.html
│   ├───content_dashboard.html
│   ├───my_registrations.html
│   ├───preferences.html
│   ├───settings_pane.html
│   └───user_dashboard.html
├───wallet/
│   ├───admin/
│   │   ├───financial_controller.html
│   │   ├───payment_aggregator.html
│   │   ├───regulator_access.html
│   │   └───sandbox_testing.html
│   ├───financial/
│   │   ├───account_detail.html
│   │   └───account_lookup.html
│   ├───_deposit_content.html
│   ├───_send_content.html
│   ├───agent_payout_history.html
│   ├───agent_payout_request.html
│   ├───base_wallet.html
│   ├───compliance.html
│   ├───deposit.html
│   ├───deposit_pane.html
│   ├───dump.html
│   ├───fx_rates.html
│   ├───original_file.html
│   ├───overview.html
│   ├───payment_gateway.html
│   ├───send.html
│   ├───send_pane.html
│   ├───transaction_history.html
│   ├───transactions.html
│   ├───transfer.html
│   ├───wallet_activate.html
│   ├───wallet_create.html
│   ├───wallet_dashboard.html
│   ├───wallet_dashboard_pane.html
│   ├───wallet_home.html
│   ├───wallet_settings.html
│   ├───WALLET_SYSTEM_DOCUMENTATION.md
│   ├───wallet_terms.html
│   ├───wallet_transactions.html
│   ├───webhook_detail.html
│   ├───webhooks_list.html
│   ├───webhooks_stats.html
│   └───withdraw.html
├───accommodation_home.html
├───admin_payouts.html
├───agent_commissions.html
├───agent_payout_history.html
├───agent_payout_request.html
├───base.html
├───bulk_verify.html
├───codes for re-use on public html.html
├───fan_profile.html
├───login.html
├───mfa.html
├───module_disabled.html
├───public_home.html
├───receiver_wallet.html
├───register.html
├───reset_confirm.html
├───reset_password.html
├───reset_request.html
├───super_admin_dashboard.html
├───test.html
├───tourism_detail.html
├───tourism_home.html
├───tournament_archive.html
├───tournament_home.html
├───tournament_home_pane.html
├───transport_detail.html
├───transport_home.html
├───verify.html
└───view.html
├───tests/
│   ├───notifications/
│   │   ├───__init__.py
│   │   ├───test_events.py
│   │   ├───test_models.py
│   │   └───test_user_controls.py
│   ├───wallet/
│   │   ├───__init__.py
│   │   ├───conftest.py
│   │   └───test_ledger_concurrency.py
│   ├───__init__.py
│   ├───backup_db.py
│   ├───check_alembic.py
│   ├───check_bugs.py
│   ├───check_db.py
│   ├───check_db_schema.py
│   ├───check_db_status.py
│   ├───check_enum_detail.py
│   ├───check_model.py
│   ├───check_schema.py
│   ├───check_settings_table.py
│   ├───check_table.py
│   ├───check_tables.py
│   ├───clear_cache.py
│   ├───compare_model_db.py
│   ├───conftest.py
│   ├───db_connector.py
│   ├───ERRORS_RESOLVED.md
│   ├───find_wallet_relationship.py
│   ├───fix_enum_issue.py
│   ├───fix_events_schema.py
│   ├───fix_geometry_issue.py
│   ├───fix_migration_gist.py
│   ├───fix_owner.py
│   ├───full_db_audit.py
│   ├───generate_migration.py
│   ├───hooks_web_unit_tests.py
│   ├───init_settings.py
│   ├───inspect_db.py
│   ├───list_endpoints.py
│   ├───manage.py
│   ├───phase_1.py
│   ├───phase_2.py
│   ├───postgres_contract.py
│   ├───read_llater.txt
│   ├───run_event_tests.py
│   ├───sample_users.py
│   ├───scanner.py
│   ├───seed_roles.py
│   ├───seed_roles_simple.py
│   ├───setup_owner.py
│   ├───simple_template_check.py
│   ├───simpletests.py
│   ├───temp_fix.py
│   ├───test roles.py
│   ├───test_accommodation_booking.py
│   ├───test_accommodation_capacity_rules.py
│   ├───test_accommodation_checkout_processes.py
│   ├───test_accommodation_date_range_rules.py
│   ├───test_accommodation_home.py
│   ├───test_accommodation_lifecycle_verification.py
│   ├───test_accommodation_modify_booking_dates.py
│   ├───test_accommodation_physical_room_assignment.py
│   ├───test_accommodation_roomtype.py
│   ├───test_accommodation_transaction_recovery.py
│   ├───test_addendum2_registration.py
│   ├───test_alipay_model.py
│   ├───test_audit_system.py
│   ├───test_auth_context.py
│   ├───test_auth_import.py
│   ├───test_boot.py
│   ├───test_compliance_kyc_action.py
│   ├───test_concurrency.py
│   ├───test_concurrency_simple.py
│   ├───test_current.py
│   ├───test_database_contract.py
│   ├───test_db_public_id.py
│   ├───test_dead_letter_alert.py
│   ├───test_event_accommodation_assignment_flow.py
│   ├───test_event_inventory_concurrency.py
│   ├───test_event_registration_availability.py
│   ├───test_event_transfer_lifecycle.py
│   ├───test_event_workflow.py
│   ├───test_events.py
│   ├───test_events_ownership_characterization.py
│   ├───test_events_user_workflows.py
│   ├───test_fan_kyc.py
│   ├───test_fix_accommodation_unit_availability.py
│   ├───test_forensic_audit.py
│   ├───test_get_organizer_metrics_canonical.py
│   ├───test_global_transaction_recovery.py
│   ├───test_guest_assignment_account_optional.py
│   ├───test_guest_coordination_accommodation.py
│   ├───test_guest_coordination_contract.py
│   ├───test_identity_events.py
│   ├───test_idguard.py
│   ├───test_impersonation.py
│   ├───test_impersonation_simple.py
│   ├───test_imports.py
│   ├───test_kyc_compliance.py
│   ├───test_kyc_integration.py
│   ├───test_kyc_reupload.py
│   ├───test_kyc_status_consistency.py
│   ├───test_kyc_upload_validation.py
│   ├───test_live_module_isolation.py
│   ├───test_load.py
│   ├───test_loose_coupling.py
│   ├───test_module_integration.py
│   ├───test_module_integration_simple.py
│   ├───test_module_isolation.py
│   ├───test_onboarding.py
│   ├───test_org_workspace.py
│   ├───test_owner_trust_integration.py
│   ├───test_payment_flow.py
│   ├───test_payment_method_capabilities.py
│   ├───test_phone_verification.py
│   ├───test_pin_lockout_and_transfer_and_idempotency.py
│   ├───test_process_webhook_dead_letter.py
│   ├───test_registration_flow.py
│   ├───test_services.py
│   ├───test_simple.py
│   ├───test_simple_imports.py
│   ├───test_template_fix.py
│   ├───test_template_rendering.py
│   ├───test_trust_card.py
│   ├───test_trust_system.py
│   ├───testing12.py
│   ├───tests_alone.py
│   ├───transport_model.py
│   ├───update_models_no_geometry.py
│   ├───user_roles_id.py
│   ├───verify_architecture.py
│   ├───verify_concurrency.py
│   ├───verify_db.py
│   ├───verify_fix.py
│   ├───verify_obed.py
│   ├───verify_tables.py
│   ├───verify_template.py
│   └───verify_transport_tables.py
├───__init__.py
├───backup_db.py
├───check_alembic.py
├───check_bugs.py
├───check_db.py
├───check_db_schema.py
├───check_db_status.py
├───check_enum_detail.py
├───check_model.py
├───check_schema.py
├───check_settings_table.py
├───check_table.py
├───check_tables.py
├───clear_cache.py
├───compare_model_db.py
├───conftest.py
├───db_connector.py
├───ERRORS_RESOLVED.md
├───find_wallet_relationship.py
├───fix_enum_issue.py
├───fix_events_schema.py
├───fix_geometry_issue.py
├───fix_migration_gist.py
├───fix_owner.py
├───full_db_audit.py
├───generate_migration.py
├───hooks_web_unit_tests.py
├───init_settings.py
├───inspect_db.py
├───list_endpoints.py
├───manage.py
├───phase_1.py
├───phase_2.py
├───read_llater.txt
├───run_event_tests.py
├───sample_users.py
├───scanner.py
├───seed_roles.py
├───seed_roles_simple.py
├───setup_owner.py
├───simple_template_check.py
├───simpletests.py
├───temp_fix.py
├───test roles.py
├───test_accommodation_booking.py
├───test_accommodation_home.py
├───test_accommodation_roomtype.py
├───test_alipay_model.py
├───test_audit_system.py
├───test_auth_import.py
├───test_boot.py
├───test_concurrency.py
├───test_concurrency_simple.py
├───test_current.py
├───test_db_public_id.py
├───test_dead_letter_alert.py
├───test_event_workflow.py
├───test_events.py
├───test_fan_kyc.py
├───test_forensic_audit.py
├───test_idguard.py
├───test_impersonation.py
├───test_impersonation_simple.py
├───test_imports.py
├───test_kyc_compliance.py
├───test_kyc_integration.py
├───test_live_module_isolation.py
├───test_load.py
├───test_loose_coupling.py
├───test_module_integration.py
├───test_module_integration_simple.py
├───test_module_isolation.py
├───test_onboarding.py
├───test_owner_trust_integration.py
├───test_payment_flow.py
├───test_pin_lockout_and_transfer_and_idempotency.py
├───test_process_webhook_dead_letter.py
├───test_registration_flow.py
├───test_services.py
├───test_simple.py
├───test_simple_imports.py
├───test_template_fix.py
├───test_template_rendering.py
├───test_trust_card.py
├───test_trust_system.py
├───testing12.py
├───tests_alone.py
├───transport_model.py
├───update_models_no_geometry.py
├───user_roles_id.py
├───verify_architecture.py
├───verify_concurrency.py
├───verify_db.py
├───verify_fix.py
├───verify_obed.py
├───verify_tables.py
├───verify_template.py
└───verify_transport_tables.py
├───_mail_flow_test.py
├───_mail_test.py
├───admin_route.py
├───AFCON360_ID_Architecture_and_Aider_Plan.md
├───AFCON360_TRUST_DISCOVERY_ARCHITECTURE.md
├───AFCON360_USER_DASHBOARD_IMPLEMENTATION.md
├───AGENTS.md
├───app.py
├───AUTH_SECURITY_INSTRUCTIONS.md
├───AUTH_SECURITY_REPORT.md
├───BACKLOG.md
├───backup_20260603_003918.json
├───check_constraint.py
├───check_quotes.py
├───check_super_admins.py
├───check_syntax.py
├───cleanup_stuck_booking.py
├───config.py
├───DASHBOARD_RESTRUCTURING_PLAN.md
├───DATABASE_SCALABILITY_ROADMAP.md
├───docker-compose.yml
├───docker-compose.yml.bak2
├───docker-entrypoint.sh
├───Dockerfile
├───Dockerfile.production
├───env.example
├───fb335177d8ffd3ba23b7c25404a12de9.jpg
├───find_duplicate_indexes.py
├───find_error.py
├───fix_column.py
├───fix_compliance_urls.py
├───fix_db_direct.py
├───fix_deprecations.ps1
├───fix_duplicate_indexes.py
├───GEMINI.md
├───images.jpg
├───implement.md
├───implement_host dashboard.md
├───IMPLEMENTATION_LOG.md
├───IMPLEMENTATION_SUMMARY.md
├───inspect_db.sh
├───investigate_status.py
├───KILO_DIRECTIVE.md
├───kilo_implement.md
├───kiro_history.md
├───lastgeminicli.md
├───make_snippet.py
├───mcp_server.py
├───MEDIA_WALLET_FIX_REPORT.md
├───notepad
├───PERFORMANCE_FIXES.md
├───PROFILE_ACCOUNT_ROUTES_SPEC.md
├───README.md
├───register_trust_settings.py
├───report.md
├───requirements.txt
├───run_project_audit.py
├───setup_log.txt
├───simple_tests.py
├───test.pdf
├───test_snippet.py
├───tree.md
├───trust_analysis_demo.py
├───user_dashboard_refined_with_switcher.html
├───validate_profile_pages.py
├───verify_changes.py
├───verify_freeze.py
├───verify_regulatory.py
├───verify_status_case.py
└───wallet_env_template.txt
