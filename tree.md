├───app
│   │   celery_app.py
│   │   CHECK_DUAL_ID_ISSUES.md
│   │   cli.py
│   │   config.py
│   │   extensions.py
│   │   placeholder.py
│   │   providers.py
│   │   routes.py
│   │   tourism.py
│   │   utils.py
│   │   __init__.py
│   │   
│   ├───accommodation
│   │   │   event_listeners.py
│   │   │   forms.py
│   │   │   listeners.py
│   │   │   routes.py
│   │   │   routes_old.py
│   │   │   services.py
│   │   │   __init__.py
│   │   │   
│   │   ├───models
│   │   │       availability.py
│   │   │       booking.py
│   │   │       property.py
│   │   │       review.py
│   │   │       wishlist.py
│   │   │       __init__.py
│   │   │       
│   │   ├───services
│   │   │       abuse_prevention_service.py
│   │   │       ai_search_service.py
│   │   │       ai_trip_planner_service.py
│   │   │       availability_service.py
│   │   │       blockchain_reviews_service.py
│   │   │       booking_service.py
│   │   │       competitive_intelligence_service.py
│   │   │       dynamic_pricing_service.py
│   │   │       gamified_loyalty_service.py
│   │   │       host_service.py
│   │   │       hyper_personalization_service.py
│   │   │       identity_service.py
│   │   │       immersive_tour_service.py
│   │   │       payment_option_service.py
│   │   │       predictive_availability_service.py
│   │   │       pricing_service.py
│   │   │       search_service.py
│   │   │       urgency_service.py
│   │   │       voice_booking_service.py
│   │   │       wallet_service.py
│   │   │       __init__.py
│   │   │       
│   │   └───state_machine
│   │           booking_states.py
│   │           __init__.py
│   │           
│   ├───admin
│   │   │   decorators.py
│   │   │   hooks.py
│   │   │   models.py
│   │   │   routes.py
│   │   │   services.py
│   │   │   trust_settings.py
│   │   │   __init__.py
│   │   │   
│   │   ├───admin_services
│   │   │       ai_detection.py
│   │   │       analytics_service.py
│   │   │       content_safety.py
│   │   │       cross_platform.py
│   │   │       escalation_workflow.py
│   │   │       moderation_queue.py
│   │   │       payment_methods.py
│   │   │       training_system.py
│   │   │       __init__.py
│   │   │       
│   │   ├───auditor
│   │   │       routes.py
│   │   │       __init__.py
│   │   │       
│   │   ├───compliance
│   │   │       models.py
│   │   │       routes.py
│   │   │       services.py
│   │   │       __init__.py
│   │   │       
│   │   ├───models
│   │   │       core.py
│   │   │       emergency_access.py
│   │   │       moderation.py
│   │   │       __init__.py
│   │   │       
│   │   ├───moderator
│   │   │       pipeline.py
│   │   │       registry.py
│   │   │       routes.py
│   │   │       __init__.py
│   │   │       
│   │   ├───owner
│   │   │   │   audit.py
│   │   │   │   decorators.py
│   │   │   │   models.py
│   │   │   │   routes.py
│   │   │   │   security_routes.py
│   │   │   │   security_service.py
│   │   │   │   security_settings.py
│   │   │   │   settings.md
│   │   │   │   utils.py
│   │   │   │   wallet_config.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───api
│   │   │           module_api.py
│   │   │           
│   │   ├───route_modules
│   │   │       accommodation_admin.py
│   │   │       event_manager.py
│   │   │       org_admin.py
│   │   │       org_member.py
│   │   │       settings.py
│   │   │       tourism_admin.py
│   │   │       transport_admin.py
│   │   │       wallet_admin.py
│   │   │       __init__.py
│   │   │       
│   │   ├───services
│   │   │       __init__.py
│   │   │       
│   │   ├───staff
│   │   │       __init__.py
│   │   │       
│   │   └───support
│   │           routes.py
│   │           __init__.py
│   │           
│   ├───api
│   │       health.py
│   │       
│   ├───audit
│   │       comprehensive_audit.py
│   │       forensic_audit.py
│   │       models.py
│   │       user.py
│   │       __init__.py
│   │       
│   ├───auth
│   │   │   config_model.py
│   │   │   decorators.py
│   │   │   delegation.py
│   │   │   email.py
│   │   │   helpers.py
│   │   │   kyc_compliance.py
│   │   │   kyc_routes.py
│   │   │   onboarding_routes.py
│   │   │   otp_service.py
│   │   │   ownership.py
│   │   │   password_policy.py
│   │   │   policy.py
│   │   │   roles.py
│   │   │   routes.py
│   │   │   seed_roles.py
│   │   │   services.py
│   │   │   sessions.py
│   │   │   session_management.py
│   │   │   test_helpers.py
│   │   │   tokens.py
│   │   │   validators.py
│   │   │   __init__.py
│   │   │   
│   │   └───services
│   │           org.py
│   │           
│   ├───backup
│   │       backup_service.py
│   │       
│   ├───cli
│   │       owner.py
│   │       __init__.py
│   │       
│   ├───compliance
│   │       aml_service.py
│   │       
│   ├───core
│   │       context.py
│   │       model_registry.py
│   │       
│   ├───dashboard
│   │       routes.py
│   │       
│   ├───Documentation
│   │       ADMIN_CSP_MIGRATION_SUMMARY.md
│   │       ARCHITECTURE_PASS_5_FINAL.md
│   │       AUTH_SYSTEM_ARCHITECTURE.md
│   │       AUTH_SYSTEM_IMPLEMENTATION.md
│   │       CLI Commands Reference.md
│   │       CSP_POLICY.md
│   │       IDENTITY_POLICIES.md
│   │       ID_SYSTEM_RULES.md
│   │       MODERATOR_CAPABILITIES.md
│   │       MODERATOR_SYSTEM_COMPLETE.md
│   │       NAV_REDESIGN_PASS_6.md
│   │       ONBOARDING_IMPLEMENTATION_GUIDE.md
│   │       ONBOARDING_IMPLEMENTATION_REPORT.md
│   │       ONBOARDING_REMEDIATION_PASS_2.md
│   │       PROFILE_KYC_SYSTEM.md
│   │       RECONCILE_WALLET.md
│   │       SESSION_EXPORT_CSP_MIGRATION_2026-04-27.md
│   │       SYSTEM_OVERVIEW.md
│   │       TRUST_BASED_SECURITY.md
│   │       WALLET_AND_USER IDENTITIES.MD
│   │       
│   ├───events
│   │   │   constants.py
│   │   │   events.md
│   │   │   Events_CONTEXT.md
│   │   │   metrics_service.py
│   │   │   models.py
│   │   │   payment_config.py
│   │   │   permissions.py
│   │   │   phase1.md
│   │   │   README.md
│   │   │   routes.py
│   │   │   routes_accommodation.py
│   │   │   routes_community_hosts.py
│   │   │   services.py
│   │   │   settings_model.py
│   │   │   settings_routes.py
│   │   │   signals.py
│   │   │   signal_handlers.py
│   │   │   start.md
│   │   │   tasks.py
│   │   │   trust_service.py
│   │   │   __init__.py
│   │   │   
│   │   └───services
│   │           payment_service.py
│   │           
│   ├───fan
│   │   │   models.py
│   │   │   routes.py
│   │   │   __init__.py
│   │   │   
│   │   └───services
│   │           registry.py
│   │           
│   ├───forms
│   │       booking_forms.py
│   │       driver_forms.py
│   │       incident_forms.py
│   │       organisation_forms.py
│   │       organization_forms.py
│   │       settings_forms.py
│   │       vehicle_forms.py
│   │       __init__.py
│   │       
│   ├───identity
│   │   │   routes.py
│   │   │   services.py
│   │   │   __init__.py
│   │   │   
│   │   ├───individuals
│   │   │       individual_document.py
│   │   │       individual_verification.py
│   │   │       __init__.py
│   │   │       
│   │   ├───models
│   │   │       compliance_audit_log.py
│   │   │       compliance_settings.py
│   │   │       kyb.py
│   │   │       licence_document.py
│   │   │       note.py
│   │   │       organisation.py
│   │   │       organisation_controller.py
│   │   │       organisation_member.py
│   │   │       organization_types.py
│   │   │       roles_permission.py
│   │   │       user.py
│   │   │       __init__.py
│   │   │       
│   │   ├───services
│   │   │       organization_permissions.py
│   │   │       organization_registration.py
│   │   │       user_roles.py
│   │   │       __init__.py
│   │   │       
│   │   └───utils
│   │           
│   ├───kyc
│   │       models.py
│   │       nira_verification.py
│   │       routes.py
│   │       services.py
│   │       upgrade_routes.py
│   │       __init__.py
│   │       
│   ├───middleware
│   │       reload_modules.py
│   │       
│   ├───models
│   │       audit.py
│   │       base.py
│   │       system_config.py
│   │       theme.py
│   │       __init__.py
│   │       
│   ├───owner
│   │   └───routes
│   │           role_management.py
│   │           settings.py
│   │           
│   ├───profile
│   │       models.py
│   │       routes.py
│   │       __init__.py
│   │       
│   ├───services
│   │       module_toggle_service.py
│   │       sms_service.py
│   │       __init__.py
│   │       
│   ├───tasks
│   │       reconcile.py
│   │       webhook_processor.py
│   │       
│   ├───tools
│   │       inspect_project.py
│   │       theme_routes.py
│   │       theme_service.py
│   │       
│   ├───tourism
│   │       routes.py
│   │       __init__.py
│   │       
│   ├───tournament
│   │       routes.py
│   │       __init__.py
│   │       
│   ├───transport
│   │   │   decorator.py
│   │   │   event_listeners.py
│   │   │   listeners.py
│   │   │   models.py
│   │   │   routes.py
│   │   │   view_models.py
│   │   │   __init__.py
│   │   │   
│   │   ├───api
│   │   │       analytic_routes.py
│   │   │       booking_routes.py
│   │   │       dashboard_routes.py
│   │   │       driver_routes.py
│   │   │       incident_routes.py
│   │   │       organisation_routes.py
│   │   │       routes.py
│   │   │       route_routes.py
│   │   │       settings_routes.py
│   │   │       utils.py
│   │   │       vehicle_routes.py
│   │   │       __init__.py
│   │   │       
│   │   ├───services
│   │   │       booking_service.py
│   │   │       dashboard_service.py
│   │   │       external_platforms.py
│   │   │       future_adds.py
│   │   │       matching_service.py
│   │   │       notification_service.py
│   │   │       payment_service.py
│   │   │       promotion_service.py
│   │   │       provider_service.py
│   │   │       settings_service.py
│   │   │       tracking_service.py
│   │   │       __init__.py
│   │   │       
│   │   └───utils
│   │           helpers.py
│   │           __init__.py
│   │           
│   ├───user
│   │       routes.py
│   │       
│   ├───utils
│   │       audit.py
│   │       caching.py
│   │       db_retry.py
│   │       error_handler.py
│   │       exceptions.py
│   │       idempotency.py
│   │       id_guard.py
│   │       id_helpers.py
│   │       id_validator.py
│   │       module_disabled.py
│   │       module_guard.py
│   │       module_switch.py
│   │       monitoring.py
│   │       rate_limiting.py
│   │       redis_lock.py
│   │       security.py
│   │       template_helpers.py
│   │       transactions.py
│   │       validators.py
│   │       widget_loader.py
│   │       __init__.py
│   │       
│   └───wallet
│       │   decorators.py
│       │   exceptions.py
│       │   models.py
│       │   routes.py
│       │   routes_pin.py
│       │   services.py
│       │   validators.py
│       │   WALLET_SYSTEM_DOCUMENTATION1.md
│       │   WALLET_SYSTEM_DOCUMENTATION_AIDER.md
│       │   __init__.py
│       │   
│       ├───api
│       │       admin_api.py
│       │       admin_webhook_routes.py
│       │       fx_api.py
│       │       wallet_api.py
│       │       webhooks.py
│       │       __init__.py
│       │       
│       ├───middleware
│       │       idempotency.py
│       │       kill_switch.py
│       │       wallet_activation.py
│       │       wallet_check.py
│       │       __init__.py
│       │       
│       ├───models
│       │       admin_audit.py
│       │       aggregator.py
│       │       audit.py
│       │       commission.py
│       │       config.py
│       │       fraud_detection.py
│       │       fx.py
│       │       ledger.py
│       │       nonce_protection.py
│       │       payout.py
│       │       reconciliation.py
│       │       transaction.py
│       │       travel_rule.py
│       │       webhook_event.py
│       │       __init__.py
│       │       
│       ├───payments
│       │       alipay.py
│       │       flutterwave.py
│       │       mobile_money.py
│       │       paypal.py
│       │       paystack.py
│       │       visa.py
│       │       wechat.py
│       │       __init__.py
│       │       
│       ├───repositories
│       │       account_repository.py
│       │       commission_repository.py
│       │       ledger_repository.py
│       │       payout_repository.py
│       │       transaction_repository.py
│       │       wallet_repository.py
│       │       __init__.py
│       │       
│       ├───routes
│       │       regulator_api.py
│       │       
│       └───services
│               admin_audit_service.py
│               aggregator_service.py
│               commission_service.py
│               compliance_engine.py
│               currency_service.py
│               fraud_detection_service.py
│               fx_service.py
│               nonce_protection_service.py
│               payment_gateway.py
│               payout_service.py
│               regulatory_reporting.py
│               regulator_service.py
│               travel_rule_service.py
│               wallet_notifications.py
│               wallet_service.py
│               wallet_status_service.py
│               __init__.py
│               
├───docs
│       enterprise_readiness_assessment.md
│       payment_system_documentation.md
│       
├───instance
│       afcon360.db
│       dev.db
│       test.db
│       
├───migrations
│   │   alembic.ini
│   │   env.py
│   │   envy.html
│   │   README
│   │   script.py.mako
│   │   test_events.py
│   │   
│   └───versions
│           0f73dc769909_upgrade_wallet.py
│           120311fa7a45_commissionservice_pay_commission.py
│           1e93a437d0e6_add_moderation_notes_to_entity_tables.py
│           1ec02d475973_add_transaction_pin_hash_column_to_.py
│           20240512_001_create_system_config.py
│           20260430_182327_ledger_rebuild.py
│           23ecc92eb3fd_add_event_model_indexes_and_constraints.py
│           24a3a276de3f_add_public_id_to_datachangelog.py
│           2fc46778f352_merge_enhance_mfa_kyc_fields_with_.py
│           326afa83a2fa_add_verified_column_to_accounts.py
│           32d4d4a2fded_add_enterprise_moderation_features_to_.py
│           33109d1a4a4b_add_protected_account_fields_to_users.py
│           3b9698ba7dd0_merge_migrations.py
│           42cc84c21004_add_community_host_id_to_eventassignment.py
│           489d61e4ca9b_add_event_assignments_table.py
│           4f863ac4b7c3_enforce_not_null_on_ledger_entries_transaction_id.py
│           526b870ba631_add_owner_type_and_terms_accepted_at_to_.py
│           559ed1dc362b_merge_two_heads.py
│           5649512f749d_fix_moderation_log_relationships.py
│           56cf92e4fdef_add_compliance_models_and_integration_.py
│           5a52752fe439_message.py
│           654c1bf0ccea_add_event_settings_table.py
│           67a805678c79_initial_clean_migration_with_all_models.py
│           696448994561_add_account_id_to_transactions_py.py
│           6c46a97365d0_add_emergency_access_fields_to_users_.py
│           6c994e0e5f9d_add_kyc_verification_fields_to_.py
│           7053dc695af1_add_event_moderation_fields.py
│           723b9cea8d97_add_org_settings_column_to_.py
│           75602feb99cc_fix_csrf_and_cleanup.py
│           79b4ffde1124_add_raw_body_to_webhook_events.py
│           7d2872a2c358_add_trust_based_security_settings_to_.py
│           80c9b2f7cb42_phase_6_event_ownership_transfers_.py
│           8e254b19689d_feat_add_event_approval_workflow_with_.py
│           8eddbe3d8a03_aggregators_integration.py
│           9a90ef638142_add_emergency_access_table.py
│           add_auth_configuration_table.py
│           add_fx_tables.py
│           add_moderation_notes_to_organisations.py
│           add_ota_search_indexes.py
│           af20cf39283a_sync_onboarding_models.py
│           b512872ef96a_add_email_verified_phone_verified_and_.py
│           ba9cdabc4951_add_content_flags_table.py
│           bd22abbdba18_still_wallet.py
│           c76f972a4ed1_sync_schema_remove_fan_profiles_and_add_.py
│           ceadd442d369_update_contentflag_model_with_.py
│           create_payment_config_tables.py
│           create_system_config_table.py
│           d8f7481b2ac0_fix_event_status_legacy_values.py
│           d9a2a9f82ed4_add_event_type_column_to_events_table.py
│           dc216edcf743_fix_enterprise_moderation_table_and_add_.py
│           dce3342ee153_your_change_description.py
│           e7c5932521a3_drop_fan_profiles_table.py
│           e9c505703ce2_add_driver_profile_onboarding.py
│           ee770bb1ee78_add_event_submission_preferences_and_.py
│           enhance_mfa_kyc_fields.py
│           enhance_mfa_kyc_fields_fixed.py
│           f898e8aae452_add_systemconfiguration_model_for_.py
│           fefed84f1389_merge_heads.py
│           fix_compliance_bigint_types.py
│           fix_migration_state.py
│           
├───pushups
│       auth.py
│       routes.py
│       __init__.py
│       
├───Readme's
│       2026-04-11_events_concurrency_fixes.md
│       admin-system-analysis.md
│       ALL_QA.md
│       App_Roadmap.md
│       ARCHITECTURE_PASS_5_IMPLEMENTATION_REPORT.md
│       DASHBOARD_FIXES_COMPLETE.md
│       DEPLOYMENT_GUIDE.md
│       DEPLOYMENT_READINESS_ASSESSMENT.md
│       endpoints.md
│       ENDPOINT_FIXES_SUMMARY.md
│       ERROR_FIXES_SUMMARY.md
│       IMPERSONATION_SYSTEM_STATUS.md
│       Moderation.md
│       MODULE_ISOLATION_AUDIT.md
│       MODULE_ISOLATION_IMPLEMENTATION_REPORT.md
│       MODULE_ISOLATION_INTEGRATION_REPORT.md
│       OWNER_SYSTEM_COMPLETE.md
│       P0_FIXES_REPORT.md
│       PRODUCTION_README.md
│       registration_report2_15-04
│       reistration & user mgt.md
│       reistration_report_15_04.md
│       security_assessment.md
│       SECURITY_FIXES_COMPLETE.md
│       SECURITY_FIXES_IMPLEMENTED.md
│       SECURITY_FIXES_README.md
│       tests.md
│       ULTIMATE_ADMIN_SYSTEM.md
│       USER_ROLE_MGT.MD
│       VERIFICATION_REPORT.md
│       WALLET_DEPLOYMENT_AUDIT.md
│       WALLET_IMPLEMENTATION_STATUS.md
│       WALLET_STATUS_REPORT.md
│       WALLET_SYSTEM_ANALYSIS.md
│       
├───reports
│       wallet_deepseek_audit.md
│       
├───scripts
│       check_id_usage.py
│       db_audit.py
│       dumpedfiles.py
│       generate_missing_migrations.py
│       init_settings.py
│       migrate_fan_profiles.py
│       reset_test_db.py
│       script.js
│       seed_roles.py
│       setup_test_db.py
│       setup_test_db_schema.py
│       test_flow.py
│       
├───static
│   │   manifest.json
│   │   
│   ├───css
│   │   │   dashboard.css
│   │   │   
│   │   ├───fan
│   │   │       dashboard.css
│   │   │       
│   │   ├───generated
│   │   │       global-theme.css
│   │   │       user-1.css
│   │   │       
│   │   ├───global
│   │   │       home.css
│   │   │       style.css
│   │   │       theme-components.css
│   │   │       theme-variables.css
│   │   │       
│   │   └───modules
│   │       ├───accommodation
│   │       │       calendar.css
│   │       │       detail.css
│   │       │       explore.css
│   │       │       home.css
│   │       │       moderate.css
│   │       │       moderate_base.css
│   │       │       moderate_detail.css
│   │       │       search.css
│   │       │       
│   │       ├───admin
│   │       │       admin.css
│   │       │       owner.css
│   │       │       
│   │       ├───events
│   │       │       attendee.css
│   │       │       base_events.css
│   │       │       dashboard.css
│   │       │       forms.css
│   │       │       hub.css
│   │       │       public.css
│   │       │       scanner.css
│   │       │       
│   │       ├───transport
│   │       │       base.css
│   │       │       bookings.css
│   │       │       dashboard.css
│   │       │       drivers.css
│   │       │       vehicles.css
│   │       │       
│   │       └───wallet
│   │               deposit.css
│   │               send.css
│   │               wallet.css
│   │               
│   ├───images
│   │   └───transport
│   │       ├───driver_avatars
│   │       └───vehicle_icons
│   └───js
│       │   theme-manager.js
│       │   
│       ├───fan
│       │       dashboard.js
│       │       
│       ├───global
│       │       main.js
│       │       script.js
│       │       theme-manager.js
│       │       
│       └───modules
│           ├───accommodation
│           │       checkout.js
│           │       detail.js
│           │       explore.js
│           │       search.js
│           │       
│           ├───admin
│           │       admin_moderation.js
│           │       moderator_dashboard.js
│           │       
│           ├───events
│           │       event-create.js
│           │       event-register.js
│           │       
│           └───transport
│                   base.js
│                   booking.js
│                   charts.js
│                   dashboard.js
│                   drivers.js
│                   mapp.js
│                   realtime.js
│                   utils.js
│                   vehicle.js
│                   
├───templates
│   │   accommodation_home.html
│   │   admin_payouts.html
│   │   agent_commissions.html
│   │   agent_payout_history.html
│   │   agent_payout_request.html
│   │   base.html
│   │   bulk_verify.html
│   │   codes for re-use on public html.html
│   │   fan_profile.html
│   │   login.html
│   │   mfa.html
│   │   module_disabled.html
│   │   public_home.html
│   │   receiver_wallet.html
│   │   register.html
│   │   reset_confirm.html
│   │   reset_password.html
│   │   reset_request.html
│   │   super_admin_dashboard.html
│   │   test.html
│   │   tourism_detail.html
│   │   tourism_home.html
│   │   tournament_archive.html
│   │   tournament_home.html
│   │   transport_detail.html
│   │   transport_home.html
│   │   verify.html
│   │   view.html
│   │   
│   ├───accommodation
│   │   │   Accomodation_module.md
│   │   │   explore.html
│   │   │   home.html
│   │   │   moderate.html
│   │   │   moderate_booking.html
│   │   │   moderate_property.html
│   │   │   moderate_review.html
│   │   │   
│   │   ├───admin
│   │   ├───guest
│   │   │       checkout.html
│   │   │       confirmation.html
│   │   │       detail.html
│   │   │       my_bookings.html
│   │   │       search.html
│   │   │       
│   │   └───host
│   │           calendar.html
│   │           
│   ├───admin
│   │   │   accommodation_admin_dashboard.html
│   │   │   admin.html
│   │   │   auditor_dashboard.html
│   │   │   content_dashboard.html
│   │   │   dashboard.html
│   │   │   event_manager_dashboard.html
│   │   │   global_theme.html
│   │   │   kyc_documents.html
│   │   │   manage_orgs.html
│   │   │   manage_roles.html
│   │   │   manage_submissions.html
│   │   │   manage_users.html
│   │   │   moderator_dashboard.html
│   │   │   org_admin_dashboard.html
│   │   │   org_audit.html
│   │   │   org_members.html
│   │   │   org_member_dashboard.html
│   │   │   payment_methods.html
│   │   │   role_users.html
│   │   │   settings.html
│   │   │   super_admin_dashboard.html
│   │   │   super_admin_settings.html
│   │   │   super_dashboard.html
│   │   │   support_dashboard.html
│   │   │   tourism_admin_dashboard.html
│   │   │   transport_admin_dashboard.html
│   │   │   trust_settings.html
│   │   │   update_profile.html
│   │   │   update_user.html
│   │   │   user_activity.html
│   │   │   view_user.html
│   │   │   view_user_ultimate.html
│   │   │   wallets.html
│   │   │   wallet_admin_dashboard.html
│   │   │   wallet_commissions.html
│   │   │   wallet_control.html
│   │   │   wallet_detail.html
│   │   │   wallet_stats.html
│   │   │   
│   │   ├───compliance
│   │   │       aml_queue.html
│   │   │       base_compliance.html
│   │   │       cases.html
│   │   │       case_history.html
│   │   │       dashboard.html
│   │   │       data_requests.html
│   │   │       escalations.html
│   │   │       generate_report.html
│   │   │       kyc_queue.html
│   │   │       licences.html
│   │   │       organisations.html
│   │   │       payouts.html
│   │   │       reports.html
│   │   │       search.html
│   │   │       user_audit_profile.html
│   │   │       view_case.html
│   │   │       
│   │   ├───moderation
│   │   ├───moderator
│   │   │       ai_analytics.html
│   │   │       audit_log.html
│   │   │       base_moderator.html
│   │   │       categories.html
│   │   │       content.html
│   │   │       content_safety.html
│   │   │       cross_platform.html
│   │   │       dashboard.html
│   │   │       escalations.html
│   │   │       events.html
│   │   │       flagged.html
│   │   │       flags.html
│   │   │       items.html
│   │   │       kyc.html
│   │   │       my_queue.html
│   │   │       orgs.html
│   │   │       README.md
│   │   │       settings.html
│   │   │       stats.html
│   │   │       training.html
│   │   │       training_content.html
│   │   │       transport.html
│   │   │       transport_bookings.html
│   │   │       transport_booking_view.html
│   │   │       transport_drivers.html
│   │   │       transport_driver_view.html
│   │   │       transport_third_party.html
│   │   │       transport_vehicles.html│   │   │       transport_vehicle_view.html
│   │   │       users.html
│   │   │       view_event.html
│   │   │       view_flag.html
│   │   │       view_item.html
│   │   │       view_kyc.html
│   │   │       view_org.html
│   │   │       view_submission.html
│   │   │       view_user.html
│   │   │       _pending_table.html
│   │   │       
│   │   ├───owner
│   │   │       auth_settings.html
│   │   │       kyc_tiers.html
│   │   │       security_dashboard.html
│   │   │       
│   │   └───settings
│   │           analytics.html
│   │           impersonation.html
│   │           moderation.html
│   │           platform.html
│   │           system.html
│   │           
│   ├───audit
│   │       aml_review.html
│   │       api_logs.html
│   │       base_audit.html
│   │       data_access.html
│   │       financial_logs.html
│   │       security_events.html
│   │       
│   ├───auditor
│   │       dashboard.html
│   │       
│   ├───auth
│   │       recover_question.html
│   │       recover_request.html
│   │       
│   ├───compliance
│   │       dashboard.html
│   │       
│   ├───components
│   │       audit_timeline.html
│   │       kyc_badge.html
│   │       kyc_tier_badge.html
│   │       mfa_status.html
│   │       pending_reviews_widget.html
│   │       status_badge.html
│   │       suspicious_activity_widget.html
│   │       
│   ├───dashboard
│   │       user_dashboard.html
│   │       
│   ├───email
│   │       verification.html
│   │       
│   ├───errors
│   │       404.html
│   │       500.html
│   │       
│   ├───events
│   │   │   events_hub.html
│   │   │   event_theme.html
│   │   │   moderate.html
│   │   │   moderate_detail.html
│   │   │   
│   │   ├───admin
│   │   │   │   dashboard.html
│   │   │   │   events.html
│   │   │   │   pending.html
│   │   │   │   settings.html
│   │   │   │   staff.html
│   │   │   │   
│   │   │   └───org
│   │   │           dashboard.html
│   │   │           
│   │   ├───attendee
│   │   │       attendee_dashboard.html
│   │   │       my_registrations.html
│   │   │       register.html
│   │   │       registration_confirmation.html
│   │   │       
│   │   ├───community_host
│   │   │       register.html
│   │   │       
│   │   ├───organizer
│   │   │       accommodation_manage.html
│   │   │       analytics.html
│   │   │       attendees.html
│   │   │       community_hosts.html
│   │   │       create.html
│   │   │       edit.html
│   │   │       my_events.html
│   │   │       organizer_dashboard.html
│   │   │       scanner.html
│   │   │       waitlist.html
│   │   │       
│   │   ├───public
│   │   │       landing.html
│   │   │       list.html
│   │   │       not_found.html
│   │   │       
│   │   └───service_provider
│   │           service_provider_dashboard.html
│   │           
│   ├───fan
│   │   │   dashboard.html
│   │   │   
│   │   └───components
│   │           left_pane.html
│   │           middle_pane.html
│   │           mobile_nav.html
│   │           right_pane.html
│   │           
│   ├───kyc
│   │       complete_profile.html
│   │       index.html
│   │       limits.html
│   │       moderate.html
│   │       moderate_document.html
│   │       overview.html
│   │       upgrade.html
│   │       verify_address.html
│   │       verify_national_id.html
│   │       verify_upload.html
│   │       
│   ├───onboarding
│   │       choose.html
│   │       choose_individual.html
│   │       choose_organisation.html
│   │       driver_step1.html
│   │       driver_step2.html
│   │       driver_step3.html
│   │       event_organiser.html
│   │       fan.html
│   │       host_step1.html
│   │       host_step2.html
│   │       organisation_step1.html
│   │       organisation_step2.html
│   │       _progress_bar.html
│   │       _wizard_styles.html
│   │       
│   ├───org
│   │       content_dashboard.html
│   │       dashboard.html
│   │       dashboard_old.html
│   │       members.html
│   │       members_old.html
│   │       register.html
│   │       selector.html
│   │       settings.html
│   │       settings_old.html
│   │       wallet.html
│   │       
│   ├───owner
│   │   │   add_payment_gateway.html
│   │   │   admin_audit_log.html
│   │   │   aggregator_settings.html
│   │   │   audit_logs.html
│   │   │   backup_codes.html
│   │   │   compliance_settings.html
│   │   │   configure_fraud_detection.html
│   │   │   configure_nonce_protection.html
│   │   │   configure_travel_rule.html
│   │   │   danger_zone.html
│   │   │   dashboard.html
│   │   │   error_logs.html
│   │   │   impersonate.html
│   │   │   later.html
│   │   │   manage_aggregators.html
│   │   │   manage_roles.html
│   │   │   settings.html
│   │   │   super_admins.html
│   │   │   system_health.html
│   │   │   users.html
│   │   │   wallet_capabilities.html
│   │   │   wallet_settings.html
│   │   │   
│   │   ├───role_management
│   │   │       audit_log.html
│   │   │       dashboard.html
│   │   │       users.html
│   │   │       
│   │   └───wallet_config
│   │           edit_provider.html
│   │           env_setup.html
│   │           index.html
│   │           providers.html
│   │           system.html
│   │           
│   ├───placeholder
│   │       coming_soon.html
│   │       
│   ├───profile
│   │       account.html
│   │       edit.html
│   │       public.html
│   │       
│   ├───tourism
│   │       moderate.html
│   │       moderate_listing.html
│   │       
│   ├───transport
│   │   │   base.html
│   │   │   become_driver.html
│   │   │   book.html
│   │   │   booking_detatails.html
│   │   │   driver_dashboard.html
│   │   │   home.html
│   │   │   homes.html
│   │   │   home_pane.html
│   │   │   moderate.html
│   │   │   moderate_booking.html
│   │   │   moderate_driver.html
│   │   │   moderate_vehicle.html
│   │   │   register_vehicle.html
│   │   │   structure
│   │   │   vehicle_dashboard.html
│   │   │   
│   │   ├───admin
│   │   │       dashboard.html
│   │   │       
│   │   ├───analytics
│   │   │       drivers.html
│   │   │       history.html
│   │   │       index.html
│   │   │       performance.html
│   │   │       revenue.html
│   │   │       vehicles.html
│   │   │       
│   │   ├───bookings
│   │   │       assign.html
│   │   │       edit.html
│   │   │       history.html
│   │   │       index.html
│   │   │       new.html
│   │   │       payments.html
│   │   │       show.html
│   │   │       timeline.html
│   │   │       _form.html
│   │   │       
│   │   ├───dashboard
│   │   │   │   base_dashboard.html
│   │   │   │   index.html
│   │   │   │   keep.html
│   │   │   │   overview.html
│   │   │   │   
│   │   │   └───widgets
│   │   │           booking_card.html
│   │   │           driver_card.html
│   │   │           vehicle_card.html
│   │   │           
│   │   ├───drivers
│   │   │       dashboard.html
│   │   │       edit.html
│   │   │       history.html
│   │   │       index.html
│   │   │       location.html
│   │   │       new.html
│   │   │       show.html
│   │   │       verification.html
│   │   │       _form.html
│   │   │       
│   │   ├───incidents
│   │   │       edit.html
│   │   │       evidence.html
│   │   │       history.html
│   │   │       index.html
│   │   │       investigate.html
│   │   │       new.html
│   │   │       show.html
│   │   │       _form.html
│   │   │       
│   │   ├───organisations
│   │   │       dashboard.html
│   │   │       drivers.html
│   │   │       edit.html
│   │   │       index.html
│   │   │       new.html
│   │   │       show.html
│   │   │       vehicles.html
│   │   │       _form.html
│   │   │       
│   │   ├───partials
│   │   │   │   overview.html
│   │   │   │   sidebar.html
│   │   │   │   
│   │   │   ├───modals
│   │   │   │       assign_driver.html
│   │   │   │       assign_vehicle.html
│   │   │   │       confirm_delete.html
│   │   │   │       update_status.html
│   │   │   │       
│   │   │   └───tables
│   │   │           booking_row.html
│   │   │           driver_row.html
│   │   │           vehicle_row.html
│   │   │           
│   │   ├───routes
│   │   │       edit.html
│   │   │       history.html
│   │   │       index.html
│   │   │       new.html
│   │   │       schedule.html
│   │   │       show.html
│   │   │       _form.html
│   │   │       
│   │   ├───settings
│   │   │       advanced.html
│   │   │       booking.html
│   │   │       general.html
│   │   │       index.html
│   │   │       integrations.html
│   │   │       payment.html
│   │   │       safety.html
│   │   │       vehicles.html
│   │   │       
│   │   └───vehicles
│   │           edit.html
│   │           history.html
│   │           index.html
│   │           location.html
│   │           maintenance.html
│   │           new.html
│   │           show.html
│   │           _form.html
│   │           
│   ├───user
│   │       base_user_dashboard.html
│   │       content_dashboard.html
│   │       my_registrations.html
│   │       preferences.html
│   │       user_dashboard.html
│   │       
│   └───wallet
│       │   agent_payout_history.html
│       │   agent_payout_request.html
│       │   base_wallet.html
│       │   compliance.html
│       │   deposit.html
│       │   dump.html
│       │   fx_rates.html
│       │   original_file.html
│       │   overview.html
│       │   payment_gateway.html
│       │   send.html
│       │   transactions.html
│       │   transaction_history.html
│       │   transfer.html
│       │   wallet_activate.html
│       │   wallet_dashboard.html
│       │   wallet_home.html
│       │   wallet_settings.html
│       │   WALLET_SYSTEM_DOCUMENTATION.md
│       │   wallet_terms.html
│       │   wallet_transactions.html
│       │   webhooks_list.html
│       │   webhooks_stats.html
│       │   webhook_detail.html
│       │   withdraw.html
│       │   
│       └───admin
│               financial_controller.html
│               payment_aggregator.html
│               regulator_access.html
│               sandbox_testing.html
│               
└───tests
        check_alembic.py
        check_settings_table.py
        check_table.py
        check_tables.py
        clear_cache.py
        conftest.py
        db_connector.py
        ERRORS_RESOLVED.md
        find_wallet_relationship.py
        fix_enum_issue.py
        fix_events_schema.py
        fix_geometry_issue.py
        fix_migration_gist.py
        fix_owner.py
        full_db_audit.py
        generate_migration.py
        hooks_web_unit_tests.py
        init_settings.py
        inspect_db.py
        list_endpoints.py
        manage.py
        phase_1.py
        phase_2.py
        project_structure.txt
        read_llater.txt
        run_event_tests.py
        sample_users.py
        scanner.py
        seed_roles.py
        seed_roles_simple.py
        setup_owner.py
        simpletests.py
        simple_template_check.py
        temp_fix.py
        test roles.py
        testing12.py
        tests_alone.py
        test_alipay_model.py
        test_audit_system.py
        test_auth_import.py
        test_boot.py
        test_concurrency.py
        test_concurrency_simple.py
        test_current.py
        test_db_public_id.py
        test_dead_letter_alert.py
        test_events.py
        test_event_workflow.py
        test_fan_kyc.py
        test_forensic_audit.py
        test_idguard.py
        test_impersonation.py
        test_impersonation_simple.py
        test_imports.py
        test_kyc_compliance.py
        test_kyc_integration.py
        test_live_module_isolation.py
        test_load.py
        test_loose_coupling.py
        test_module_integration.py
        test_module_integration_simple.py
        test_module_isolation.py
        test_onboarding.py
        test_owner_trust_integration.py
        test_payment_flow.py
        test_pin_lockout_and_transfer_and_idempotency.py
        test_process_webhook_dead_letter.py
        test_registration_flow.py
        test_services.py
        test_simple.py
        test_simple_imports.py
        test_template_fix.py
        test_template_rendering.py
        test_trust_card.py
        test_trust_system.py
        transport_model.py
        tree.md
        update_models_no_geometry.py
        user_roles_id.py
        verify_architecture.py
        verify_concurrency.py
        verify_db.py
        verify_fix.py
        verify_obed.py
        verify_tables.py
        verify_template.py
        verify_transport_tables.py