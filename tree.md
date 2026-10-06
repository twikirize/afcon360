# AFCON360 Project Tree (generated: 2026-08-26 14:30:00)

├───_engineering_verification/
├───app/
│   │   celery_app.py
│   │   CHECK_DUAL_ID_ISSUES.md
│   │   cli.py
│   │   config.py
│   │   extensions.py
│   │   kyc_config_schema.py
│   │   placeholder.py
│   │   providers.py
│   │   routes.py
│   │   utils.py
│   │   __init__.py
│   │   __init__.py.bak
│   │   
│   ├───accommodation
│   │   │   AFCON360_SEAMLESS_BOOKING_SPEC.md
│   │   │   booking_forms.py
│   │   │   catalog_data.py
│   │   │   forms.py
│   │   │   listeners.py
│   │   │   routes.py
│   │   │   sockets.py
│   │   │   utils.py
│   │   │   __init__.py
│   │   │   
│   │   ├───models
│   │   │   │   availability.py
│   │   │   │   booking.py
│   │   │   │   booking_payment.py
│   │   │   │   booking_policy.py
│   │   │   │   booking_price_adjustment.py
│   │   │   │   booking_registration_link.py
│   │   │   │   cancellation_policy.py
│   │   │   │   catalog.py
│   │   │   │   commission.py
│   │   │   │   feedback.py
│   │   │   │   guest_identity.py
│   │   │   │   guest_profile.py
│   │   │   │   guest_registration.py
│   │   │   │   host_profile.py
│   │   │   │   moderation.py
│   │   │   │   platform_override.py
│   │   │   │   property.py
│   │   │   │   property_document.py
│   │   │   │   property_payment_method.py
│   │   │   │   review.py
│   │   │   │   room.py
│   │   │   │   special_request.py
│   │   │   │   wishlist.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───services
│   │   │   │   abuse_prevention_service.py
│   │   │   │   ai_search_service.py
│   │   │   │   ai_trip_planner_service.py
│   │   │   │   availability_service.py
│   │   │   │   blockchain_reviews_service.py
│   │   │   │   booking_registration_link_service.py
│   │   │   │   booking_service.py
│   │   │   │   bulk_registration_service.py
│   │   │   │   catalog_service.py
│   │   │   │   competitive_intelligence_service.py
│   │   │   │   coordination_contract.py
│   │   │   │   dynamic_pricing_service.py
│   │   │   │   gamified_loyalty_service.py
│   │   │   │   guest_dashboard_service.py
│   │   │   │   host_service.py
│   │   │   │   hyper_personalization_service.py
│   │   │   │   identity_service.py
│   │   │   │   immersive_tour_service.py
│   │   │   │   marketplace_service.py
│   │   │   │   media_service.py
│   │   │   │   moderation_service.py
│   │   │   │   payment_option_service.py
│   │   │   │   payment_policy_service.py
│   │   │   │   predictive_availability_service.py
│   │   │   │   pricing_service.py
│   │   │   │   readiness_service.py
│   │   │   │   registration_permission_service.py
│   │   │   │   registration_service.py
│   │   │   │   review_service.py
│   │   │   │   search_service.py
│   │   │   │   special_request_service.py
│   │   │   │   transport_coordination.py
│   │   │   │   trust_service.py
│   │   │   │   urgency_service.py
│   │   │   │   verification_engine.py
│   │   │   │   voice_booking_service.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───payment_processors
│   │   │   │   │   base.py
│   │   │   │   │   card_processor.py
│   │   │   │   │   invoice_processor.py
│   │   │   │   │   mobile_money_processor.py
│   │   │   │   │   mock_gateway_processor.py
│   │   │   │   │   wallet_processor.py
│   │   │   │   │   __init__.py
│   │   │   │   │   
│   │   ├───state_machine
│   │   │   │   booking_states.py
│   │   │   │   payment_states.py
│   │   │   │   policy_evaluator.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   └───utils
│   │   │   │   decorators.py
│   │   │   │   
│   ├───admin
│   │   │   agent_mgmt.py
│   │   │   decorators.py
│   │   │   hooks.py
│   │   │   models.py
│   │   │   routes.py
│   │   │   routes_ultimate.py
│   │   │   services.py
│   │   │   trust_settings.py
│   │   │   __init__.py
│   │   │   
│   │   ├───admin_services
│   │   │   │   ai_detection.py
│   │   │   │   analytics_service.py
│   │   │   │   content_safety.py
│   │   │   │   cross_platform.py
│   │   │   │   escalation_workflow.py
│   │   │   │   moderation_queue.py
│   │   │   │   payment_methods.py
│   │   │   │   training_system.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───auditor
│   │   │   │   routes.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───compliance
│   │   │   │   models.py
│   │   │   │   routes.py
│   │   │   │   services.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───models
│   │   │   │   core.py
│   │   │   │   emergency_access.py
│   │   │   │   moderation.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───moderator
│   │   │   │   pipeline.py
│   │   │   │   registry.py
│   │   │   │   routes.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───owner
│   │   │   │   audit.py
│   │   │   │   backup_routes.py
│   │   │   │   csp_routes.py
│   │   │   │   decorators.py
│   │   │   │   escrow_routes.py
│   │   │   │   escrow_services.py
│   │   │   │   models.py
│   │   │   │   rate_limit_notifications.py
│   │   │   │   rate_limit_service.py
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
│   │   │   │   │   module_api.py
│   │   │   │   │   
│   │   ├───route_modules
│   │   │   │   accommodation_admin.py
│   │   │   │   event_manager.py
│   │   │   │   org_admin.py
│   │   │   │   org_member.py
│   │   │   │   settings.py
│   │   │   │   tourism_admin.py
│   │   │   │   transport_admin.py
│   │   │   │   wallet_admin.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───services
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───staff
│   │   │   │   __init__.py
│   │   │   │   
│   │   └───support
│   │   │   │   routes.py
│   │   │   │   __init__.py
│   │   │   │   
│   ├───api
│   │   │   health.py
│   │   │   
│   ├───audit
│   │   │   comprehensive_audit.py
│   │   │   forensic_audit.py
│   │   │   models.py
│   │   │   user.py
│   │   │   __init__.py
│   │   │   
│   ├───auth
│   │   │   config_model.py
│   │   │   context.py
│   │   │   decorators.py
│   │   │   delegation.py
│   │   │   deletion_guard.py
│   │   │   email.py
│   │   │   email_validation.py
│   │   │   helpers.py
│   │   │   kyc_compliance.py
│   │   │   kyc_routes.py
│   │   │   onboarding_routes.py
│   │   │   otp_service.py
│   │   │   otp_store.py
│   │   │   ownership.py
│   │   │   password_policy.py
│   │   │   pending_registration.py
│   │   │   phone_verification.py
│   │   │   policy.py
│   │   │   registration_policy.py
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
│   │   ├───models
│   │   │   │   delegation.py
│   │   │   │   
│   │   └───services
│   │   │   │   org.py
│   │   │   │   
│   ├───backup
│   │   │   backup_service.py
│   │   │   __init__.py
│   │   │   
│   ├───cli
│   │   │   owner.py
│   │   │   __init__.py
│   │   │   
│   ├───compliance
│   │   │   aml_regulatory_models.py
│   │   │   aml_regulatory_service.py
│   │   │   aml_service.py
│   │   │   
│   ├───core
│   │   │   context.py
│   │   │   model_registry.py
│   │   │   serializers.py
│   │   │   transport_permissions.py
│   │   │   validators.py
│   │   │   
│   ├───Documentation
│   │   │   ADMIN_CSP_MIGRATION_SUMMARY.md
│   │   │   ARCHITECTURE_PASS_5_FINAL.md
│   │   │   AUTH_SYSTEM_ARCHITECTURE.md
│   │   │   AUTH_SYSTEM_IMPLEMENTATION.md
│   │   │   CLI Commands Reference.md
│   │   │   CSP_POLICY.md
│   │   │   FLASK_LOGIN_STATIC_FILES_BUG.md
│   │   │   IDENTITY_POLICIES.md
│   │   │   ID_SYSTEM_RULES.md
│   │   │   MODERATOR_CAPABILITIES.md
│   │   │   MODERATOR_SYSTEM_COMPLETE.md
│   │   │   NAV_REDESIGN_PASS_6.md
│   │   │   ONBOARDING_IMPLEMENTATION_GUIDE (1).md
│   │   │   ONBOARDING_IMPLEMENTATION_GUIDE.md
│   │   │   ONBOARDING_IMPLEMENTATION_REPORT.md
│   │   │   ONBOARDING_REMEDIATION_PASS_2.md
│   │   │   PROFILE_KYC_SYSTEM.md
│   │   │   RATE_LIMITING_IMPLEMENTATION.md
│   │   │   RECONCILE_WALLET.md
│   │   │   SESSION_EXPORT_CSP_MIGRATION_2026-04-27.md
│   │   │   SYSTEM_OVERVIEW.md
│   │   │   TRUST_BASED_SECURITY.md
│   │   │   UNIFIED_IDENTITY_CONTEXT_SPEC.md
│   │   │   WALLET_AND_USER IDENTITIES.MD
│   │   │   
│   │   └───adr
│   │           ADR-001-events-organizer-semantics.md
│   │           
│   ├───events
│   │   │   accommodation_booking_service.py
│   │   │   accommodation_bridge.py
│   │   │   admin_pages.py
│   │   │   api.py
│   │   │   assignment.py
│   │   │   attendee_accounts.py
│   │   │   bulk_upload.py
│   │   │   constants.py
│   │   │   events.md
│   │   │   Events_CONTEXT.md
│   │   │   Events_CONTEXTO.md
│   │   │   Events_Migration_Report.md
│   │   │   Events_Phase1_Identity_Context_Spec.md
│   │   │   Events_Phase3_Consumer_Audit.md
│   │   │   Events_Phase4_Deprecation_Observation_Report.md
│   │   │   Events_Phase4_Development_Consumer_Certification.md
│   │   │   Events_Phase4_Legacy_Removal_Plan.md
│   │   │   Events_Phase4_Ownership_Authority_Consistency_Investigation.md
│   │   │   Events_Phase4_Remaining_Consumers_Audit.md
│   │   │   Events_Phase4_Remaining_Evidence_Investigation.md
│   │   │   Events_Phase4_Step1_Report.md
│   │   │   guest_coordination_service.py
│   │   │   guest_management.py
│   │   │   inventory.py
│   │   │   metrics_service.py
│   │   │   models.py
│   │   │   payment_config.py
│   │   │   payment_service.py
│   │   │   permissions.py
│   │   │   phase1.md
│   │   │   README.md
│   │   │   registration_availability.md
│   │   │   routes.py
│   │   │   routes_accommodation.py
│   │   │   routes_community_hosts.py
│   │   │   routes_organizer.py
│   │   │   sale_guard.py
│   │   │   services.py
│   │   │   settings_model.py
│   │   │   settings_routes.py
│   │   │   signals.py
│   │   │   signal_handlers.py
│   │   │   start.md
│   │   │   tasks.py
│   │   │   trust_service.py
│   │   │   view_models.py
│   │   │   __init__.py
│   │   │   
│   │   └───services
│   ├───event_accommodation
│   │   │   __init__.py
│   │   │   
│   │   ├───models
│   │   │   │   badge.py
│   │   │   │   opportunity.py
│   │   │   │   visibility.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   └───services
│   │   │   │   badge_service.py
│   │   │   │   discovery_service.py
│   │   │   │   invitation_service.py
│   │   │   │   matching_service.py
│   │   │   │   
│   ├───fan
│   │   │   GEMINI_AGENT_FAN_MERGE.md
│   │   │   migrate_fan_to_profile.py
│   │   │   models.py
│   │   │   routes.py
│   │   │   __init__.py
│   │   │   
│   │   └───services
│   │   │   │   fan_profile_service.py
│   │   │   │   registry.py
│   │   │   │   
│   ├───feed
│   │   │   models.py
│   │   │   routes.py
│   │   │   services.py
│   │   │   __init__.py
│   │   │   
│   ├───forms
│   │   │   booking_forms.py
│   │   │   driver_forms.py
│   │   │   incident_forms.py
│   │   │   organisation_forms.py
│   │   │   organization_forms.py
│   │   │   settings_forms.py
│   │   │   vehicle_forms.py
│   │   │   __init__.py
│   │   │   
│   ├───geo
│   │   │   activity.py
│   │   │   config.py
│   │   │   history.py
│   │   │   interfaces.py
│   │   │   map_renderer.py
│   │   │   models.py
│   │   │   README.md
│   │   │   realtime.py
│   │   │   routes.py
│   │   │   services.py
│   │   │   sql.py
│   │   │   validation.py
│   │   │   __init__.py
│   │   │   
│   │   └───providers
│   │   │   │   base.py
│   │   │   │   photon.py
│   │   │   │   tiles.py
│   │   │   │   valhalla.py
│   │   │   │   __init__.py
│   │   │   │   
│   ├───identity
│   │   │   catalog_data.py
│   │   │   ORG_ADMINISTRATION_SPEC.md
│   │   │   routes.py
│   │   │   services.py
│   │   │   __init__.py
│   │   │   
│   │   ├───individuals
│   │   │   │   individual_document.py
│   │   │   │   individual_verification.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───models
│   │   │   │   compliance_audit_log.py
│   │   │   │   compliance_settings.py
│   │   │   │   kyb.py
│   │   │   │   licence_document.py
│   │   │   │   note.py
│   │   │   │   organisation.py
│   │   │   │   organisation_catalogues.py
│   │   │   │   organisation_controller.py
│   │   │   │   organisation_member.py
│   │   │   │   organisation_provider_capability.py
│   │   │   │   organization_types.py
│   │   │   │   org_payment_gateway.py
│   │   │   │   provider_participation.py
│   │   │   │   roles_permission.py
│   │   │   │   user.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   └───services
│   │   │   │   capability_service.py
│   │   │   │   organisation_classification_service.py
│   │   │   │   organisation_kyb_service.py
│   │   │   │   organisation_role_provisioning.py
│   │   │   │   organisation_slug.py
│   │   │   │   organization_permissions.py
│   │   │   │   organization_registration.py
│   │   │   │   provider_participation_service.py
│   │   │   │   user_roles.py
│   │   │   │   __init__.py
│   │   │   │   
│   ├───kyc
│   │   │   models.py
│   │   │   nira_verification.py
│   │   │   reupload.py
│   │   │   routes.py
│   │   │   selfie_pair.py
│   │   │   services.py
│   │   │   upgrade_routes.py
│   │   │   __init__.py
│   │   │   
│   ├───media
│   │   │   admin_routes.py
│   │   │   metrics.py
│   │   │   models.py
│   │   │   routes.py
│   │   │   service.py
│   │   │   settings_service.py
│   │   │   tasks.py
│   │   │   validators.py
│   │   │   __init__.py
│   │   │   
│   │   ├───processors
│   │   │   │   document.py
│   │   │   │   image.py
│   │   │   │   video.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───storage
│   │   │   │   local.py
│   │   │   │   oci.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   └───utils
│   │   │   │   content_moderator.py
│   │   │   │   monitoring.py
│   │   │   │   perceptual_hash.py
│   │   │   │   quota_manager.py
│   │   │   │   virus_scanner.py
│   │   │   │   
│   ├───middleware
│   │   │   reload_modules.py
│   │   │   
│   ├───models
│   │   │   analytics.py
│   │   │   audit.py
│   │   │   base.py
│   │   │   notification.py
│   │   │   system_config.py
│   │   │   theme.py
│   │   │   
│   ├───monitor
│   │   │   broadcaster.py
│   │   │   routes.py
│   │   │   __init__.py
│   │   │   
│   ├───notifications
│   │   │   context.py
│   │   │   listeners.py
│   │   │   mock_data.py
│   │   │   models.py
│   │   │   pages.py
│   │   │   preferences.py
│   │   │   README.md
│   │   │   routes.py
│   │   │   services.py
│   │   │   settings.py
│   │   │   signals.py
│   │   │   sms_service.py
│   │   │   tasks.py
│   │   │   template_loader.py
│   │   │   utils.py
│   │   │   _notification_implement.md
│   │   │   __init__.py
│   │   │   
│   │   ├───channel_handlers
│   │   │   │   email.py
│   │   │   │   in_app.py
│   │   │   │   push.py
│   │   │   │   sms.py
│   │   │   │   webhook.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───events
│   │   │   │   bus.py
│   │   │   │   consumers.py
│   │   │   │   context.py
│   │   │   │   exceptions.py
│   │   │   │   models.py
│   │   │   │   outbox.py
│   │   │   │   policy.py
│   │   │   │   publisher.py
│   │   │   │   registry.py
│   │   │   │   replay.py
│   │   │   │   routes.py
│   │   │   │   schemas.py
│   │   │   │   tasks.py
│   │   │   │   webhooks.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   └───integrations
│   │   │   │   __init__.py
│   │   │   │   
│   ├───owner
│   │   └───routes
│   │       │   role_management.py
│   │       │   settings.py
│   │       │   
│   ├───production_console
│   │   │   routes.py
│   │   │   sockets.py
│   │   │   streaming.py
│   │   │   __init__.py
│   │   │   
│   ├───profile
│   │   │   models.py
│   │   │   routes.py
│   │   │   __init__.py
│   │   │   
│   │   └───services
│   │   │   │   canonical_identity.py
│   │   │   │   change_request_service.py
│   │   │   │   __init__.py
│   │   │   │   
│   ├───tasks
│   │   │   accommodation_reminders.py
│   │   │   backup_tasks.py
│   │   │   cleanup.py
│   │   │   reconcile.py
│   │   │   transport_permission_purge.py
│   │   │   transport_recovery.py
│   │   │   webhook_processor.py
│   │   │   
│   ├───tools
│   │   │   inspect_project.py
│   │   │   theme_routes.py
│   │   │   theme_service.py
│   │   │   
│   ├───tourism
│   │   │   routes.py
│   │   │   __init__.py
│   │   │   
│   ├───tournament
│   │   │   routes.py
│   │   │   __init__.py
│   │   │   
│   ├───transport
│   │   │   cli_driver.py
│   │   │   decorator.py
│   │   │   event_listeners.py
│   │   │   listeners.py
│   │   │   models.py
│   │   │   routes.py
│   │   │   view_models.py
│   │   │   __init__.py
│   │   │   
│   │   ├───api
│   │   │   │   analytic_routes.py
│   │   │   │   booking_routes.py
│   │   │   │   dashboard_routes.py
│   │   │   │   driver_routes.py
│   │   │   │   fare_routes.py
│   │   │   │   incident_routes.py
│   │   │   │   organisation_routes.py
│   │   │   │   reservation_routes.py
│   │   │   │   ride_options_routes.py
│   │   │   │   routes.py
│   │   │   │   route_routes.py
│   │   │   │   settings_routes.py
│   │   │   │   utils.py
│   │   │   │   vehicle_routes.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───services
│   │   │   │   accommodation_coordination.py
│   │   │   │   assignment_service.py
│   │   │   │   availability_service.py
│   │   │   │   booking_service.py
│   │   │   │   coordination_contract.py
│   │   │   │   dashboard_service.py
│   │   │   │   external_platforms.py
│   │   │   │   fare_service.py
│   │   │   │   future_adds.py
│   │   │   │   go_live_service.py
│   │   │   │   marketplace_service.py
│   │   │   │   matching_service.py
│   │   │   │   notification_service.py
│   │   │   │   offering_registry.py
│   │   │   │   offer_service.py
│   │   │   │   passenger_service.py
│   │   │   │   payment_methods.py
│   │   │   │   payment_service.py
│   │   │   │   promotion_service.py
│   │   │   │   provider_service.py
│   │   │   │   reservation_expiry_service.py
│   │   │   │   reservation_policy_evaluator.py
│   │   │   │   reservation_service.py
│   │   │   │   reservation_state_machine.py
│   │   │   │   settings_service.py
│   │   │   │   tracking_service.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   └───utils
│   │   │   │   helpers.py
│   │   │   │   __init__.py
│   │   │   │   
│   ├───user
│   │   │   routes.py
│   │   │   use_dashboard.md
│   │   │   
│   ├───utils
│   │   │   analytics.py
│   │   │   audit.py
│   │   │   caching.py
│   │   │   db_retry.py
│   │   │   error_handler.py
│   │   │   exceptions.py
│   │   │   flash_helpers.py
│   │   │   idempotency.py
│   │   │   id_guard.py
│   │   │   id_helpers.py
│   │   │   id_kinds.py
│   │   │   id_validator.py
│   │   │   immutable_fields.py
│   │   │   module_disabled.py
│   │   │   module_guard.py
│   │   │   module_switch.py
│   │   │   module_toggle_service.py
│   │   │   money.py
│   │   │   monitoring.py
│   │   │   qr.py
│   │   │   rate_limiting.py
│   │   │   redis_lock.py
│   │   │   security.py
│   │   │   singleflight.py
│   │   │   slugs.py
│   │   │   template_helpers.py
│   │   │   transactions.py
│   │   │   transaction_intent.py
│   │   │   url.py
│   │   │   validators.py
│   │   │   widget_loader.py
│   │   │   __init__.py
│   │   │   
│   └───wallet
│   │   │   AFCON360_WALLET_AUDIT_ARCHIVE.md
│   │   │   AFCON360_WALLET_AUDIT_REPORT.md
│   │   │   AFCON360_WALLET_PRODUCTION_GUIDE.md
│   │   │   decorators.py
│   │   │   ESCROW.md
│   │   │   ESCROW_ARCHITECTURE.md
│   │   │   exceptions.py
│   │   │   GLOBAL_FUNDS_ARCHITECTURE.md
│   │   │   implement.md
│   │   │   IMPLEMENTATION_REPORT.md
│   │   │   PAYMENT_ARCHITECTURE.md
│   │   │   routes.py
│   │   │   routes_pin.py
│   │   │   SECURITY_FRAUD_PREVENTION.md
│   │   │   validators.py
│   │   │   WALLET_ARCHITECTURE.md
│   │   │   __init__.py
│   │   │   
│   │   ├───api
│   │   │   │   admin_api.py
│   │   │   │   admin_webhook_routes.py
│   │   │   │   fx_api.py
│   │   │   │   wallet_api.py
│   │   │   │   webhooks.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───middleware
│   │   │   │   idempotency.py
│   │   │   │   kill_switch.py
│   │   │   │   wallet_activation.py
│   │   │   │   wallet_check.py
│   │   │   │   wallet_check.py (new file)
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───models
│   │   │   │   adjustment.py
│   │   │   │   admin_audit.py
│   │   │   │   agent_float.py
│   │   │   │   agent_onboarding.py
│   │   │   │   aggregator.py
│   │   │   │   audit.py
│   │   │   │   commission.py
│   │   │   │   config.py
│   │   │   │   creation_tracker.py
│   │   │   │   fraud_alert.py
│   │   │   │   fraud_detection.py
│   │   │   │   fx.py
│   │   │   │   ledger.py
│   │   │   │   nonce_protection.py
│   │   │   │   payment_identity.py
│   │   │   │   payment_method.py
│   │   │   │   payout.py
│   │   │   │   reconciliation.py
│   │   │   │   regulatory_volume.py
│   │   │   │   transaction.py
│   │   │   │   transaction.py.before-fix
│   │   │   │   travel_rule.py
│   │   │   │   webhook_event.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───payments
│   │   │   │   alipay.py
│   │   │   │   flutterwave.py
│   │   │   │   mobile_money.py
│   │   │   │   paypal.py
│   │   │   │   paystack.py
│   │   │   │   visa.py
│   │   │   │   wechat.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───repositories
│   │   │   │   account_repository.py
│   │   │   │   agent_float_repository.py
│   │   │   │   commission_repository.py
│   │   │   │   ledger_repository.py
│   │   │   │   payout_repository.py
│   │   │   │   transaction_repository.py
│   │   │   │   wallet_repository.py
│   │   │   │   webhook_repository.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   ├───routes
│   │   │   │   regulator_api.py
│   │   │   │   
│   │   ├───services
│   │   │   │   admin_audit_service.py
│   │   │   │   agent_cashin_service.py
│   │   │   │   agent_cashout_service.py
│   │   │   │   agent_float_service.py
│   │   │   │   agent_management_service.py
│   │   │   │   agent_onboarding_service.py
│   │   │   │   agent_reconciliation_service.py
│   │   │   │   agent_refund_service.py
│   │   │   │   agent_statement_service.py
│   │   │   │   agent_terms_service.py
│   │   │   │   aggregator_service.py
│   │   │   │   commission_service.py
│   │   │   │   compliance_engine.py
│   │   │   │   currency_service.py
│   │   │   │   deposit_intent.py
│   │   │   │   fraud_detection_service.py
│   │   │   │   fx_service.py
│   │   │   │   identity_verification_service.py
│   │   │   │   kyc_limit_service.py
│   │   │   │   nonce_protection_service.py
│   │   │   │   payment_gateway.py
│   │   │   │   payment_identity_service.py
│   │   │   │   payout_service.py
│   │   │   │   reconciliation_service.py
│   │   │   │   regulatory_reporting.py
│   │   │   │   regulatory_volume_calculator.py
│   │   │   │   regulatory_volume_policy_service.py
│   │   │   │   regulator_service.py
│   │   │   │   suspicious_activity_service.py
│   │   │   │   travel_rule_service.py
│   │   │   │   wallet_creation_tracker.py
│   │   │   │   wallet_notifications.py
│   │   │   │   wallet_service.py
│   │   │   │   wallet_status_service.py
│   │   │   │   webhook_service.py
│   │   │   │   withdrawal_intent.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   └───utils
│   │   │   │   account_number.py
│   │   │   │   
├───backups_today
│   │   app__init__.py.bak
│   │   base.html.bak
│   │   public_home.html.bak
│   │   
│   ├───accommodation
│   │       routes.py
│   │       services.py
│   │       __init__.py
│   │       
│   └───tourism
│           routes.py
│           __init__.py
│           
├───certs
│       dev-ca-cert.pem
│       dev-ca-key.pem
│       dev-cert.pem
│       dev-key.pem
│       devca-cert.pem
│       devca-key.pem
│       
├───docker
│   └───nginx
│           afcon360.conf
│           nginx.conf
│           
├───docs
│   │   ADR-001-event-accommodation-guest-bridge.md
│   │   enterprise_readiness_assessment.md
│   │   payment_system_documentation.md
│   │   POSTGRES_TESTING_CONTRACT.md
│   │   TEST_SUITE_FORENSIC_AUDIT_REPORT.md
│   │   THEME_COVERAGE.md
│   │   
│   ├───accommodation
│   │       IMPLEMENTATION_VERIFICATION_REPORT.md
│   │       
│   ├───saved_work
│   │   │   create_tables.sh
│   │   │   docker-compose.yml
│   │   │   inspect_db.sh
│   │   │   lazy_table_creator.py
│   │   │   table_inspector.py
│   │   │   table_monitor.py
│   │   │   
│   └───transport
│       │   00-MANIFESTO-EDITION-2.0.md
│       │   01-IMPLEMENTATION-PLAYBOOK.md
│       │   02-OPERATING-SYSTEM.md
│       │   d2-atomic-dispatch-claim.md
│       │   dashboard-preservation-inventory.md
│       │   geographic-graph-map.md
│       │   
│       ├───fixes
│       │       AUTH-REDIRECT-INDEX-evidence.md
│       │       AUTH-REDIRECT-INDEX-record.md
│       │       BL-17-18-CONSOLIDATION-record.md
│       │       BL-19-evidence.md
│       │       BL-19-record.md
│       │       BL-22-evidence.md
│       │       BL-22-record.md
│       │       BL-26-record.md
│       │       BL17-BL18-authority-boundary-evidence.md
│       │       CONSOLIDATED-REVIEW-record.md
│       │       DIAGNOSE-FRESH-LOCATION-GAP-record.md
│       │       DRIVER-OFFER-UX-REPAIR-1E-evidence.md
│       │       DRIVER-OFFER-UX-REPAIR-1E-record.md
│       │       Fix-1.1-contract.md
│       │       Fix-1.1-evidence.md
│       │       Fix-1.1-record.md
│       │       Fix-2.2-contract.md
│       │       Fix-2.2-evidence.md
│       │       Fix-2.2-record.md
│       │       Fix-2.3-contract.md
│       │       Fix-2.3-evidence.md
│       │       Fix-2.3-record.md
│       │       Fix-2.4-contract.md
│       │       Fix-2.4-evidence.md
│       │       Fix-2.4-record.md
│       │       Fix-2.5-contract.md
│       │       Fix-2.5-evidence.md
│       │       Fix-2.5-record.md
│       │       Fix-2.6-contract.md
│       │       Fix-2.6-evidence.md
│       │       Fix-2.6-record.md
│       │       NOTIF-BELL-SYSTEM-SOUND-1-evidence.md
│       │       NOTIF-BELL-SYSTEM-SOUND-1-record.md
│       │       REAL-RIDE-TRANSACTION-evidence.md
│       │       RECONCILIATION-DIRECTIVE.md
│       │       RECONCILIATION-Part-XIX-contract.md
│       │       T-10-evidence.md
│       │       T-10-record.md
│       │       
│       ├───nodes
│       │       D4-evidence.md
│       │       D4-record.md
│       │       L8-physical-runbook.md
│       │       SUPPLY-ELIGIBILITY-v1.md
│       │       SUPPLY-LOCK-SITE-1048-evidence.md
│       │       SUPPLY-LOCK-SITE-1048-record.md
│       │       
│       └───reference
│               EGGE-NODE-EXAMPLE.md
│               
├───flask_session
│       001ef2fa10829c691d9df96323176127
│       00748699ae2dc63acfc91432205f506f
│       00f80f9532ef105cbd701fad8115aa0b
│       01d7ea1038702f59f847b35c4f79f07a
│       01ff028164eb61bcb9e9cda8f78f743c
│       040ea20635e99a183a02a8d22d4af809
│       041f267a6e37a02d1e118dde7d168915
│       0446c84e181cdee68b1dc16b942b56bc
│       04e8e6d112f15c87ce2be90b9ccf5558
│       05b561b6b6b066542a90c212c5c65b22
│       065e29318566f18cd604382fe8c5e3d4
│       07b67c02b288eabae730246d85ec8f5c
│       07bc7ef588f0009e61bb9b09b6c6fd02
│       0851888ae0201887b62ed31ce312485c
│       08c39e7b1597e5d455b0e739cbae1ab3
│       08f26e1c02006cc7057a32dfb01a1abe
│       09233f0a7bcfaead3a73571f42bc4f0d
│       09c7b50be598cfe536a563a0a9bca05b
│       0a1bf21d00a0cfbf3616b3e24329bcac
│       0c956b1564d262b7de4300a082222aeb
│       0d1996304300586a8ce245fc83b57ead
│       0f16b3c1f0e7e70163df7647f05eae3e
│       0f9b8efdd608141be46af7abf8fe759c
│       10b20616edcb3e327b6e6dfdacf8a819
│       111eee0a7fc791c22a96ecb2a4a48084
│       11cb3a9f8fe73afe7d27895136c5a4e9
│       12deec4ef6a566e33b6d4d92e3d416cf
│       13a83a731306bdbd6d2ee7b3194a4aa1
│       13c117338aa166df9a08cc708b163e32
│       13ef573d98f5a8d91a94f40b581ecb4a
│       1573eac4140f3b758c2ce54ed5d97a18
│       157c7645bad9647bdaf71a730c0ed048
│       16089f4c701eeec7d284ea832dd57ea6
│       17151d46e26c71f6fc067564f1e5aec5
│       1764cdcddb1b2d5ed1e006c0334c9400
│       17c9f0857e166ad1e09a8f5b11b1f2ff
│       1b81d08e04a040497dc0777c703552d7
│       1d00b04ddc874564f44bd29ad839572e
│       1d06c69434ff8688f46e575c16154f06
│       1dd40def5f03611687648f168fa0ef38
│       1eae5d126b8b205e9becb150c455b456
│       1f7a54d42fcc78dfead2ac46c689e5a2
│       1fc11f6656f68cb02f43b502e3fd32f6
│       1ff33df8fa5a354395ffde1d74250d88
│       200edabc1ff697be85224bca35625a0f
│       2029240f6d1128be89ddc32729463129
│       207187ca5a9eaf8d320db7595bf28c66
│       20cd979f426287192dbdb186a4f613b3
│       229f2e7f37f1739d608b326e212f69a9
│       264deff25481173556eca1f2cf3d34a5
│       2926e444712beb585a41917f364fb1ff
│       29ca135e6715b1b3097de3f5b7767b52
│       2a054614ca326c2e51685395a1114d64
│       2ae5b8bef3106f5fc279abf2cd2b28cc
│       2c152a603ab5a2d5c155478ec1d7c7bf
│       2c59df70523a0385c52263181e01daa7
│       2d3274613afa12cecd6774a4e9276487
│       2de7f2a6915a6614eecdc2cf53800084
│       2e298eaba44e732c7cb481b37fd0cfad
│       2e2c82d9b70cf643740f865dba7116cc
│       31a6aca8fb50606cb19b95e37b565ca7
│       32202f3ab0757bba78ac36522abc27aa
│       352b99b74b5a961a875eb7c46f68bb7e
│       358bf93146234cae86d58d0711381202
│       362fd5155e376edc14878892040fd633
│       376291294a1bf9d6e65d0b23c9114e8f
│       378262583595cb23a930b8a3f4735843
│       37c436cd2ffe1af6fc9af5e16c7a019d
│       399edf5e6602581190c86a39e3e8f275
│       39b56410376397cdd0c73dac03bae867
│       3c2be553489aec4d108ad65fecfb495f
│       3c38eef90380f7a8158d32f20b45bfff
│       3c61fb0be24b6894a71abfe3e3fb2578
│       3d2083bbff4a904544f79f24c0f662c0
│       3d53b96c216b1522b66cbe5059958073
│       3d9082a81b3c66af2054118e9ce3ac6a
│       3dbb7188e15fd0190c3fdfc0ef191e86
│       3f1d95419f00b6338560b71e3ceed3c8
│       3fb5874761eafc931abff1785e91eeb6
│       40bc1ec3e9a77140f5edbb5cafdd148e
│       42383331d3ecfee874b27613e77c1e9d
│       4239ab808cd9fc0eb3f4ffd79778489c
│       44514de699f4e7f15612483ba920c705
│       450792828d0a6b83316524400588eb99
│       457ac48e56e7715309a650938a9c9ede
│       463d1198f0a44e5b26b180fdd5f23f58
│       465b64abd23d6363b79385e22a83a6f5
│       46ecf5d70e1d8acdec485e2e87532a3b
│       473225f397c1967849303acc83ad83b6
│       47c9b99fbd14ddbfa9ba2ed782f78f83
│       47da594689a7ef19ec926573fa8d9d5b
│       48469c3b20d2e787a466e439f9d4e538
│       48b513f63937aa221905af57b7a8b239
│       494ac6fcd2d61ff94d7e9a3c6bc842b9
│       4a49a5bd8d7fc8b25dfbbcb3ee99cd1e
│       4a6b2aa190a81a09b757d65bf7e317b7
│       4af87955b46201b82c1a75d8e3ca7faa
│       4b4ed0764a96898f372be9cf50909dfb
│       4c7d713fac923e166c2d3391b343241c
│       4d22e3d0afa7654b96ebc5da318ba4d1
│       4d5a08c5134e2ba89561da79407f3bf1
│       4e7b9c36c4b2852055bf33c8b9c1b3af
│       4e99154ad285cc55d4807cbe804c4f94
│       514d671b4aef45eaeb0abf24c5595216
│       518044611078f083063b699919934977
│       5257bc84270c276fabd5e90c0e6c7dbc
│       52b7e2365d00f91b2fdb1f39e973aeeb
│       52cb5727c7cb8aab871143cab8634d84
│       53f27da6bcf3a1bfa16aa5a457e53edb
│       53fed78f5e105f94850768616c3cae1a
│       54dc0b8d50bbae25db4e950791b75544
│       557d46a5403b52514c79df094fea9809
│       55bae2baf35ad5dc33634e32ae817257
│       5645b0ee659789ba54c4889e6cbd2cc8
│       56a06f22ed0c72af47b87fa03ac55629
│       56d60e0f010b04c0b318143a77f84476
│       56ef1c8aac86842d938ef8b0bf6fc1ea
│       571b9e3ff5e7a89971c7a08ed89db334
│       574a126b49fb04ba51954da074c99d5e
│       57ebde0775575ec028a9735a9e7101c5
│       584aecd9989af192f227d37fb67fdf9b
│       589858a91d93fe8c8bf74575053ac981
│       58d95b3bfd9794521648cd70dbf78f79
│       59f60f4143f0d1100b5c457295e38383
│       5a9c919078c4663fd1b1df291c2de59b
│       5b1f23820084e1e5087395ac233f674c
│       5bd379f3bd9e584f78a567cbaab6045a
│       5e3a23af047a918ba6923193aed34f26
│       5f391ccf1cafe3e492be48c95d751625
│       5f7668e434b48e9896f308ee6f29cf48
│       60e37f3d69a3ddd18d2bc2036855bb52
│       618bef691c363bef142e462b07af10ba
│       6227a2d0fb4df0ecac987696b1c4b63d
│       636f20e369b0240a69f0f3b3e52d2592
│       637f617f9ca79e33cac823caea463af3
│       63f9f3843a25b51c36f437a5e8a9b7af
│       643d6ef48c728cdc38fd17dfc9a9a9b8
│       645c2b5915c566e5898547b77a72a8c8
│       65211d08aab11fd1c67b2a10e524d850
│       681027c55ff98b071df2d80c22247df2
│       686abd1040e055f92fc21b6b2ec304ba
│       68f66ee2db5b4022ed4322a1a70ed45a
│       693d324f297483a932150b780a372b73
│       69937dd409855625ca518fd2b9ae35f9
│       69f54440b7101380c7d8e95f67681f32
│       6a0aa0fc483321ae2cb917cdd95ad590
│       6ac46675f4acadb947bdcc64740af5d8
│       6b5229e5a9a621fd6c242c55a32699a9
│       6bd6b30df33473677ab554592e41742d
│       6ccabcca2b6fe01ccc5b2eeafe6cab03
│       6e5c4736e21d127003a1f13ad79d4385
│       6fbb4c753ce5078adf39c85a4f8d1bc1
│       7286fd488599c3d385a4605bb445e035
│       72c676963e4f1eb22a3a304bf2556364
│       746429e3bc3a503f875680d6d5c8d29f
│       74d6c9e9637e06716b0decae4bbb1a5b
│       75f74d9bd79aaa34dfeea0bccb96c6f5
│       7817770d6e497aab59956915bf6be13b
│       789e75533bf5b55a71730cb857343f7e
│       79ebc00658b5287e007db126771f6f9a
│       7a070b10b45e07d76157045df5b152ed
│       7b106fe8a90e49ad8be0a983d9479b6f
│       7bf468f1f5f542e6f7b8294a4852c29b
│       7c0844c3c2923d6798713c87dae6beeb
│       7db798046cf3267ed8c2a22eed1335ee
│       7f4a3d14ffdaa75500f3de7ef86447e8
│       80792a29cef8cd33b50dbbc32314366a
│       810722a7976c1fcc3cbd9ffa0e3dc9c4
│       824b3bb5d29d6f1f1122148689da41c0
│       82b5490b0930291b856ea284ab7ab289
│       85c881e4cd771ae8a4dff8c9744cb0ab
│       85e8c7b811c31d63649847d41c9bea99
│       87ae0a20abdb85e2fc49e623f8176879
│       885238075d01321b5e5d7b10dfcb2dcb
│       88a190c151f7ac2facb081a46faaaeb2
│       89a622bed7ce62864c51e5c7abb5f193
│       8a659482e40919a405e2438aab460cb3
│       8b2082104c6cc166997c7f2aded5fdc1
│       8c2bfaaca2412e1882ddf046f90914c6
│       8d51e1073b2375b32d93b9264f088ad0
│       8de95eda1cc88889ac78151e101a415c
│       8ebcd72f8a5c5a27df54c497a2300fd4
│       8ef0cb4807b799d40a331c4e3eb604b0
│       8f7fd67ab746f52d80d0d2e355bc5fbf
│       91614e5070ec18addb3fc26d15e90b6e
│       91bcd1328cad587121518464d9edefeb
│       91c3ce5b59fcf96bd586df8fe77a63ec
│       9215c87aca55468c16bc1282200e327c
│       9240d1f39b6660391cc9fed4c0b49afc
│       94b81d51e66701e272264a7dcb38c1fe
│       94ccc25382f7d14f1ffbe00dcf46fdf3
│       94df65859c9083c1e2049f02c4ed2111
│       94ef05eb08d198cf4d0616bfc306ad75
│       9517161e091b4460d0e26bb661ca5425
│       95d968c0311930cd3dd3c2edec5c3f6f
│       9658450669aff80f21f442bf0d217ce5
│       96c32fa80c9905e6055d0a0141c537e9
│       96e180ba4c1699389229243b074504fe
│       96e2a18a0d1e12b23ad578dd386b288b
│       9780d217a1e78e9ca4cfedb1beaad5c9
│       978a66ceeb38ef8933d7e38f526cf490
│       97b22a88fc5a5e2239d7c9ab8b96ee51
│       981cf30f05e759e65876e60e6df0feaf
│       9bda5185d831092968b379fa326537df
│       9bdf30cf1ca6e2bce3dfc07c1ed096d1
│       9eb9f758707062330ab8a3f1f74e08de
│       a27a5c76b49e87f91d403680de6f842e
│       a2b036d373dd71e0cf02a5e790931fc8
│       a34d8f4717ba1b1cf062069da30f99ea
│       a388417885ebb1f4c994aa8a91e77275
│       a3a46c19788ff369c992cdaa20705066
│       a455916128d08bbb658c977b290dac38
│       a4eb74a36e9a43494b8915f51869ea72
│       a543c37fd7a1a5605c905b5dcfd02179
│       a705d0b366ad5b2cf08ff6bc66834d65
│       a7683b230d81ef1f88b3549b09ebc3ef
│       a8b4d8ef6ee4f1eb1bb0247457ba14da
│       aa39792eb3e3da75be2ea34ed96de1df
│       ab42fc9aaa1fdac1b73cfccc459e58f8
│       ab973678241ba57d8302751be45754f4
│       aec094322f3fbad2c22f0b0edeb9e168
│       af1badf7ee232f382881c66e66779a25
│       b11266b7c5c4548cbb61619fc18e324f
│       b281f187025000e61ba744a7e2073087
│       b2d2a2974966fbbb6f6c003874c22fb7
│       b39f0ec2bb5651f0373642b3d40da9a6
│       b49f4cafcbd6f77a4168a766728f9819
│       b4ae0f56db551bd52c9acca99ece9a40
│       b500b03471d813ca79a86e05bb7173a6
│       b69233e42fc776eed4a35c6327824ff7
│       b6d208ad59a9abdbd6f016756b38b007
│       b6daef0559c464527b96ad0dc23602bc
│       b70054ab6b55805b124da5f8cfeabfd7
│       b7a891aa6aed90d2e21298e9529978d3
│       ba0d5d0012a15f9b5a2062da960f1c23
│       ba7395cf1c7f9a1a4b755ad3f4991e64
│       bcaf1fa6416c3dfbd7e946176211e5c4
│       bdb4c36e69fd03dfb951c65f2950305d
│       be930d79cc3bd074893132f7ccc1c43d
│       bec00fbc5cc993dd9f248af23e6872d2
│       bfb6e3bcedb6626c13d15f8beea33952
│       c126dbfae90d21c3ed3328bc4001c352
│       c18e46f64aea29326406e880abe4c40c
│       c428c25124a58245643f06706f6ac6d4
│       c4d388f7f0d684be858780a02fd69705
│       c6285e8c0ebd56d5553e5bbcc2b485c6
│       caffb935eb1f398055c71892dfb610b3
│       cb7f342feac93812abcecb8fd48b8f0d
│       cc13b01153cd99157d34b1bd06a200f6
│       cc1b91617262867f71a8d4b4a96756d4
│       cc4d42c1c7c33c7d99d8725fd024565e
│       cc7e1c2ab13296b86ab42b188e672624
│       cc9f3d7342fbdd6a644d99768de52ce4
│       cce5dbeadf6ae2d8ec213444ef319a83
│       cd1f927d0dd26e67217c077097ea0e52
│       cd54c0f5445c004d99141067dff68937
│       cdbe78b5e8a4e4414b7335bc7e62fa42
│       ce3fb1267a4b194cd5f4c2c2a1d1f1c2
│       ced6e309f849246e2024aa47fabc25fe
│       d0c4ceca7cdc1c82981354ccfdc65e95
│       d191e66fb916ff855804c8243fdae6a8
│       d1bed6f2423cd99d9d0240dca33a3245
│       d25f9e6d18989605c917e56fe80c5f40
│       d2b4e23a38f7162cf2012f27036e6307
│       d3328a2d35ebadbee379443223257ada
│       d3da6d2266e8631072a3fcc743d65957
│       d3e6bdffe3005fe6474077d5e68d61de
│       d3f4a3aaf3f812f83a563af77b351731
│       d47fcb6235551652ab7e9f0137b51354
│       d4f07bb7b20183302567eb2372e5c5a4
│       d53c01927f0e4c4380d0fc270a225d00
│       d55e2b929136224c1f3d306ce7a37430
│       d9afcb665102239f98a0267414331748
│       da4d9d416bc0167779d0c3c5300c6ea5
│       da67a8c88836d1f63cb310438e1c6226
│       dabcc5d9ff1066800ee9ec8941225708
│       daf304221099ea81bad13a1c0e146b0c
│       dc34bc180ec3659ab846542a3bfe45db
│       dd5cbabd28fee9ec13ab6d5f7724a3cd
│       dd6317f299dfde7595f9e3405ae43ad7
│       dd865792ba4ecce7be14dbbda472ac9a
│       de06c154d56859e9f5ff6d0593ed344a
│       df44bdaf2489c410b7779223da3993ed
│       df48ad4d86101a600eb784e71c445cea
│       e05f7afe99e7b68bbc8b0954e7eed16a
│       e0d5d9c89cc2037539375324108fb25e
│       e153c51222c83acebafae5de26134217
│       e1b1a025567ac51a0078d61c259d043d
│       e20344cb53f02b883eeeb4f1ef4378f0
│       e27e36349eae6d6d4e8cb654c6af1696
│       e3297133b169bcb50fa32de1328227ba
│       e442fdba375658bdd6e4ccc823f0930c
│       e4564bfdba0dda90ffb50220c7550f05
│       e844db24c224e858f93c5df5168ff25b
│       e8c8ad73ef14b33557daf5832eb34c8c
│       e8f82a7ce82c481630102b85069fd6ea
│       e9b83acb34ee1d21a69296210f584136
│       ea02374650d07252e6a601b103a6d201
│       eada44962fbbd37153e1299e35783eab
│       eb25a14b6f5e4ed67833724e4bf8a2b2
│       eba976436c278fc78855452cfe370b5d
│       ec52c50f1af05365705a3de2e11f557c
│       ecbd14f482e5e6c2b35aeed1b64bf7fc
│       ecdc825a382c6376360b6c89fa400b89
│       ecfc85b2c50a1f8c2e390a7a16fa7dc9
│       eec4325872d9dcbd5f28cfe940e45d00
│       f025708b85c19fc37e578bbbea0e101d
│       f0dd52309f3635c0f3e4509b7aa2d358
│       f1429b70fd4f4c14de9c3b888257e89f
│       f14329d9e812d03a82a9ac880045ed8e
│       f1d5471e069a02fcf9f47dd627343747
│       f2068d9b2eebf7758693bbf2109b8c92
│       f22894d6818440abe171464357ad6c00
│       f3233bcd27952ea7969023b1d26e7cd7
│       f327871355b961dc127aed078867c26e
│       f440b1f9f809a09edf0b34fcd8e86347
│       f5b455c1ef51e9330e880a883b4c3d5f
│       f6032c5850df00f61b3cf9219bc2f4ee
│       f7a346f63211ade3604f2500050d4a28
│       f8c9393fc332e833789c0bf7be92f754
│       fa34706587d82330edbdf60a4517fdce
│       fb288a6f9ef8e9960dd37a593ca09eed
│       fbfc01abc26c49cd9795f5867e213d72
│       fcceb9188b15e60fc12b09396ccbca72
│       fceac144cb72df7243572e53b52f8c28
│       fde996d503d25afb9e3fa63f087a6073
│       fe0017c96200c12df55172cb3dab4d56
│       ff7d2aac5e368c6869416dc98cd0515b
│       ffbb0a63487dc61c08297f56a0cfa4a0
│       
├───githubcode
│       github_token.txt
│       
├───Implement
│       booking_flow - Copy.md
│       booking_flow.md
│       ESCROW_IMPLEMENTATION_BRIEF.md
│       immutable_fileds.md
│       kilo_implemettion.md
│       report.md
│       
├───journey
│       01-home.png
│       02-after-book.png
│       04-after-accept.png
│       05-en-route.png
│       06-arrived.png
│       07-in-progress.png
│       08-completed.png
│       BD769T-01-assigned.png
│       
├───loadtest
│       explain_atomic.py
│       locustfile.py
│       staging_server.py
│       
├───mcps
│   └───idea
│       └───tools
│               build_project.json
│               cancel_sql_query.json
│               create_new_file.json
│               execute_run_configuration.json
│               execute_sql_query.json
│               execute_terminal_command.json
│               find_files_by_glob.json
│               find_files_by_name_keyword.json
│               generate_inspection_kts_api.json
│               generate_inspection_kts_examples.json
│               generate_psi_tree.json
│               get_all_open_file_paths.json
│               get_database_object_description.json
│               get_file_problems.json
│               get_file_text_by_path.json
│               get_project_dependencies.json
│               get_project_modules.json
│               get_repositories.json
│               get_run_configurations.json
│               get_symbol_info.json
│               list_database_connections.json
│               list_database_schemas.json
│               list_directory_tree.json
│               list_recent_sql_queries.json
│               list_schema_objects.json
│               list_schema_object_kinds.json
│               open_file_in_editor.json
│               preview_table_data.json
│               read_file.json
│               reformat_file.json
│               rename_refactoring.json
│               replace_text_in_file.json
│               runNotebookCell.json
│               run_inspection_kts.json
│               search_file.json
│               search_in_files_by_regex.json
│               search_in_files_by_text.json
│               search_regex.json
│               search_symbol.json
│               search_text.json
│               test_database_connection.json
│               validate_inspection_kts.json
│               xdebug_control_session.json
│               xdebug_evaluate_expression.json
│               xdebug_get_debugger_status.json
│               xdebug_get_frame_values.json
│               xdebug_get_stack.json
│               xdebug_get_threads.json
│               xdebug_get_value_by_path.json
│               xdebug_list_breakpoints.json
│               xdebug_remove_breakpoint.json
│               xdebug_run_to_line.json
│               xdebug_set_breakpoint.json
│               xdebug_set_variable.json
│               xdebug_start_debugger_session.json
│               
├───migrations
│   │   alembic.ini
│   │   env.py
│   │   README
│   │   script.py.mako
│   │   
│   ├───versions
│   │   │   0050d44787c5_update_transport_cancellation_policy.py
│   │   │   1788711780_sync_check_constraints.py
│   │   │   1788729103_sync_check_constraints.py
│   │   │   1790097621_sync_check_constraints.py
│   │   │   20260830_1420_add_booking_flow_type.py
│   │   │   20260902_2255_add_org_provider_capabilities.py
│   │   │   20260930_1335_booking_status_enum_to_string.py
│   │   │   3a73c6e6cf29_add_provider_participations_universal_.py
│   │   │   43a863fe3531_organisation_classification_catalogues.py
│   │   │   5e80dc4ac345_transport_reservation_obligation_and_.py
│   │   │   6f8f4c204b61_add_geo_location_observation_history.py
│   │   │   71893e3a42a2_add_organisation_slug.py
│   │   │   8a0deccce6f6_initial_full_schema_baseline.py
│   │   │   9f75675b5e52_audit_schema_differences.py
│   │   │   a91ce8028ae4_th_3_d3_reservation_foundation.py
│   │   │   aab3e38879dc_add_booking_idempotency_key.py
│   │   │   b73d33d073e1_add_transport_permissions_table.py
│   │   │   bd9d3bb673aa_add_organisation_slug_column.py
│   │   │   c2f495a06ed4_add_is_agent_and_agent_code_columns_to_.py
│   │   │   e6f319ffc8c8_reservation_wallet_ref_unique.py
│   │   │   e8bf41930fb2_driver_matching_no_matching_column.py
│   │   │   f1658aba3410_accommodation_catalog_lookup_tables.py
│   │   │   f1fe91ef0ebf_add_listing_type_column_to_.py
│   │   │   f91075478868_production_console.py
│   │   │   guard_delete_v1_identity_deletion_guard_triggers.py
│   │   │   
│   └───_retired_versions
│   │       0020df051447_merge_backfill_event_roles.py
│   │       1787438348_sync_check_constraints.py
│   │       1787899767_sync_check_constraints.py
│   │       20260828_booking_mode_default.py
│   │       23a2748dc5d1_add_organizer_profiles_table.py
│   │       4855a635e4fd_add_acc_link_token_hash_and_acc_link_.py
│   │       5cc5d7b15a1b_add_operational_daily_monthly_ceilings_.py
│   │       69cd2e2f7251_transport_reservation_obligation_and_.py
│   │       91911883eb58_drop_redundant_organizer_profiles_.py
│   │       9a0b1c2d3e4f_backfill_event_owner_roles.py
│   │       ab6dd422c152_initial_schema.py
│   │       cancel_policy_001_add_cancellationpolicy_and.py
│   │       db8cd686f423_accommodation_add_missing_property_.py
│   │       f4a1b2c3d5e6_payment_identity_architecture.py
│   │       
├───model_backups
│       app__accommodation__models__availability.py_20260409011912.bak
│       app__accommodation__models__booking.py_20260409011912.bak
│       app__accommodation__models__property.py_20260409011912.bak
│       app__accommodation__models__review.py_20260409011912.bak
│       app__admin__models.py_20260409011912.bak
│       app__admin__owner__models.py_20260409011912.bak
│       app__audit__comprehensive_audit.py_20260409011912.bak
│       app__audit__models.py_20260409011912.bak
│       app__auth__sessions.py_20260409011912.bak
│       app__events__models.py_20260409011912.bak
│       app__fan__models.py_20260409011912.bak
│       app__identity__individuals__individual_document.py_20260409011912.bak
│       app__identity__individuals__individual_verification.py_20260409011912.bak
│       app__identity__models__compliance_audit_log.py_20260409011912.bak
│       app__identity__models__compliance_settings.py_20260409011912.bak
│       app__identity__models__kyb.py_20260409011912.bak
│       app__identity__models__licence_document.py_20260409011912.bak
│       app__identity__models__organisation.py_20260409011912.bak
│       app__identity__models__organisation_controller.py_20260409011912.bak
│       app__identity__models__organisation_member.py_20260409011912.bak
│       app__identity__models__roles_permission.py_20260409011912.bak
│       app__identity__models__user.py_20260409011912.bak
│       app__kyc__models.py_20260409011912.bak
│       app__models__audit.py_20260409011912.bak
│       app__models__base.py_20260409011912.bak
│       app__models__theme.py_20260409011912.bak
│       app__profile__models.py_20260409011912.bak
│       app__transport__models.py_20260409011912.bak
│       app__wallet__models.py_20260409011912.bak
│       fix_map.md
│       
├───prompts
│       high_performer_os.html
│       media_implementation.md
│       MEDIA_SYSTEM_MASTER (1).md
│       MEDIA_SYSTEM_MASTER.md
│       refactor_events.md
│       the_plan.md
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
│       AML_COMPLIANCE_GUIDE.md
│       App_Roadmap.md
│       ARCHITECTURE_PASS_5_IMPLEMENTATION_REPORT.md
│       DASHBOARD_FIXES_COMPLETE.md
│       DEPLOYMENT_GUIDE.md
│       DEPLOYMENT_READINESS_ASSESSMENT.md
│       endpoints.md
│       ENDPOINT_FIXES_SUMMARY.md
│       ERROR_FIXES_SUMMARY.md
│       IMPERSONATION_SYSTEM_STATUS.md
│       media_handling.md
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
│       report.md
│       security_assessment.md
│       SECURITY_FIXES_COMPLETE.md
│       SECURITY_FIXES_IMPLEMENTED.md
│       SECURITY_FIXES_README.md
│       SECURITY_FIXES_README.zip
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
│   │   media_system_implementation_report.md
│   │   MEDIA_SYSTEM_SETUP_GUIDE.md
│   │   wallet_deepseek_audit.md
│   │   
│   └───security
│           identity_audit_20260718_084105.json
│           identity_audit_20260718_084222.json
│           
├───rules
│       agent-context-index.md
│       agent-governance-rules.md
│       ask-debug-mode-rules.md
│       code-mode-rules.md
│       global-rules.md
│       
├───scripts
│   │   backfill_listing_type.py
│   │   backfill_room_types.py
│   │   check_id_usage.py
│   │   complete_fix.py
│   │   create_migration.py
│   │   create_system_configs.py
│   │   db_audit.py
│   │   dumpedfiles.py
│   │   fix_remaining.py
│   │   generate_migration.py
│   │   generate_missing_migrations.py
│   │   generate_step1_report.py
│   │   init_settings.py
│   │   inspect_database_ids.py
│   │   inspect_identity_map.py
│   │   inspect_id_fields.py
│   │   inspect_id_usage.py
│   │   lazy_table_creator.py
│   │   migrate_enums_to_strings.py
│   │   migrate_fan_profiles.py
│   │   migration_agent_config.py
│   │   provision_kampala_central_hotel.py
│   │   repro_g_standalone.py
│   │   reset_test_db.py
│   │   restore_git.py
│   │   restore_obedz_roles.py
│   │   restore_owner_roles.py
│   │   run_backfill.py
│   │   scan_null_bytes.py
│   │   script.js
│   │   seed_accommodation_catalogs.py
│   │   seed_organisation_catalogues.py
│   │   seed_payment_methods.py
│   │   seed_roles.py
│   │   seed_system_configs.py
│   │   seed_test_marketplace_accounts.py
│   │   seed_transport_driver.py
│   │   setup_platform_escrow.py
│   │   setup_test_db.py
│   │   setup_test_db_schema.py
│   │   stage4b4_opc_to_pp_forensics.py
│   │   sync_check_constraints.py
│   │   sync_check_constraints_ for_later.py
│   │   table_inspector.py
│   │   table_monitor.py
│   │   test_flow.py
│   │   test_normalize_repro.py
│   │   verify_bookings.py
│   │   verify_precedence_equiv.py
│   │   _diag_audit.py
│   │   _diag_final.py
│   │   _diag_forensic.py
│   │   _diag_identity.py
│   │   _diag_roleaudit.py
│   │   _diag_roleaux.py
│   │   _diag_roledb.py
│   │   _diag_roleviews.py
│   │   _diag_role_events.py
│   │   _diag_schema.py
│   │   _diag_tables.py
│   │   _verify_obedz.py
│   │   _verify_roles.py
│   │   
│   ├───.pytest_cache
│   │   │   .gitignore
│   │   │   CACHEDIR.TAG
│   │   │   README.md
│   │   │   
│   │   └───v
│   │       └───cache
│   │               lastfailed
│   │               nodeids
│   │               stepwise
│   │               
│   ├───reports
│   │       database_id_inventory.md
│   │       id_field_inventory.md
│   │       id_usage_audit.md
│   │       
│   └───security
│   │   │   identity_audit.py
│   │   │   
├───static
│   │   manifest.json
│   │   MOBILE_OPTIMIZATION.md
│   │   
│   ├───css
│   │   │   dashboard.css
│   │   │   
│   │   ├───fan
│   │   │       dashboard.css
│   │   │       
│   │   ├───feed
│   │   │       feed.css
│   │   │       
│   │   ├───generated
│   │   │       global-theme.css
│   │   │       
│   │   ├───global
│   │   │       dark-mode.css
│   │   │       home.css
│   │   │       kyc-ribbon.css
│   │   │       mobile-utilities.css
│   │   │       style.css
│   │   │       theme-components.css
│   │   │       theme-variables.css
│   │   │       
│   │   └───modules
│   │       ├───accommodation
│   │       │       calendar.css
│   │       │       checkout.css
│   │       │       detail.css
│   │       │       explore.css
│   │       │       home.css
│   │       │       host-bookings.css
│   │       │       host-dashboard.css
│   │       │       host-listing-form.css
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
│   │       │       public-past-event.css
│   │       │       public.css
│   │       │       registration-availability.css
│   │       │       scanner.css
│   │       │       
│   │       ├───media
│   │       │       media.css
│   │       │       
│   │       ├───onboarding
│   │       │       choose.css
│   │       │       
│   │       ├───transport
│   │       │       base.css
│   │       │       bookings.css
│   │       │       dashboard.css
│   │       │       driver-dashboard.css
│   │       │       drivers.css
│   │       │       vehicles.css
│   │       │       
│   │       ├───user
│   │       │       dashboard.css
│   │       │       selfie-capture.css
│   │       │       shell.css
│   │       │       
│   │       └───wallet
│   │               deposit.css
│   │               send.css
│   │               wallet.css
│   │               
│   ├───icons
│   │       icon-192.png
│   │       icon-512.png
│   │       
│   ├───images
│   │       company-brain-template.md
│   │       creator-media-cofounder.skill
│   │       no-image.png
│   │       
│   ├───js
│   │   │   theme-manager.js
│   │   │   
│   │   ├───admin
│   │   │       feed_layout_toggle.js
│   │   │       
│   │   ├───fan
│   │   │       dashboard.js
│   │   │       
│   │   ├───feed
│   │   │       feed.js
│   │   │       
│   │   ├───geo
│   │   │       geo-map.js
│   │   │       geo-realtime.js
│   │   │       
│   │   ├───global
│   │   │       frontend-console-tracker.js
│   │   │       main.js
│   │   │       media-manager.js
│   │   │       script.js
│   │   │       theme-manager.js
│   │   │       
│   │   └───modules
│   │       ├───accommodation
│   │       │       checkout.js
│   │       │       confirmation.js
│   │       │       detail.js
│   │       │       explore.js
│   │       │       guest_roster.js
│   │       │       host-dashboard-enhanced.js
│   │       │       host-dashboard.js
│   │       │       search.js
│   │       │       
│   │       ├───admin
│   │       │       admin_moderation.js
│   │       │       compliance-pdf-viewer.js
│   │       │       moderator_dashboard.js
│   │       │       
│   │       ├───events
│   │       │       event-create.js
│   │       │       event-register.js
│   │       │       guest-coordination.js
│   │       │       
│   │       ├───transport
│   │       │       accommodation_pane.js
│   │       │       base.js
│   │       │       booking.js
│   │       │       charts.js
│   │       │       dashboard.js
│   │       │       driver-dashboard.js
│   │       │       drivers.js
│   │       │       driver_alerts.js
│   │       │       driver_offer_poll.js
│   │       │       mapp.js
│   │       │       realtime.js
│   │       │       rider_matching.js
│   │       │       rider_status_sync.js
│   │       │       trips_panel.js
│   │       │       utils.js
│   │       │       vehicle.js
│   │       │       
│   │       └───user
│   │               dashboard-shell.js
│   │               events-calendar.js
│   │               kyc-ribbon.js
│   │               selfie-capture.js
│   │               user-dashboard.js
│   │               
│   └───transport
│           manifest.json
│           sw.js
│           
├───templates
│   │   accommodation_home.html
│   │   admin_payouts.html
│   │   agent_commissions.html
│   │   agent_payout_history.html
│   │   agent_payout_request.html
│   │   base.html
│   │   bulk_verify.html
│   │   fan_profile.html
│   │   login.html
│   │   mfa.html
│   │   module_disabled.html
│   │   monitor.html
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
│   │   tournament_home_pane.html
│   │   transport_detail.html
│   │   transport_home.html
│   │   utils.html
│   │   verify.html
│   │   view.html
│   │   
│   ├───accommodation
│   │   │   Accomodation_module.md
│   │   │   booking.md
│   │   │   explore.html
│   │   │   home.html
│   │   │   home_pane.html
│   │   │   moderate.html
│   │   │   moderate_booking.html
│   │   │   moderate_property.html
│   │   │   moderate_review.html
│   │   │   more_edits.md
│   │   │   my_accommodation.html
│   │   │   my_accommodation_pane.html
│   │   │   
│   │   ├───admin
│   │   │       analytics.html
│   │   │       bookings.html
│   │   │       booking_detail.html
│   │   │       financials.html
│   │   │       pending_properties.html
│   │   │       properties.html
│   │   │       property_history.html
│   │   │       property_history_partial.html
│   │   │       settings.html
│   │   │       verification.html
│   │   │       _macros.html
│   │   │       
│   │   ├───guest
│   │   │       add_request.html
│   │   │       amend.html
│   │   │       assignment_completion.html
│   │   │       checkout.html
│   │   │       claim_booking.html
│   │   │       complaints.html
│   │   │       complaint_detail.html
│   │   │       confirmation.html
│   │   │       dashboard.html
│   │   │       dashboard_pane.html
│   │   │       detail.html
│   │   │       edit_registration.html
│   │   │       guest_roster.html
│   │   │       my_bookings.html
│   │   │       pass.html
│   │   │       register.html
│   │   │       registration_link.html
│   │   │       review_form.html
│   │   │       search.html
│   │   │       _dashboard_content.html
│   │   │       
│   │   └───host
│   │       │   bookings.html
│   │       │   booking_detail.html
│   │       │   booking_policy.html
│   │       │   calendar.html
│   │       │   create_listing.html
│   │       │   dashboard.html
│   │       │   earnings.html
│   │       │   edit_listing.html
│   │       │   property_documents.html
│   │       │   property_manage.html
│   │       │   register.html
│   │       │   rooms.html
│   │       │   room_availability.html
│   │       │   
│   │       └───listings
│   │               create.html
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
│   │   │   media_settings.html
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
│   │   │   wallet_adjustments.html
│   │   │   wallet_admin_dashboard.html
│   │   │   wallet_commissions.html
│   │   │   wallet_control.html
│   │   │   wallet_detail.html
│   │   │   wallet_stats.html
│   │   │   
│   │   ├───agent_mgmt
│   │   │       detail.html
│   │   │       index.html
│   │   │       onboarding_detail.html
│   │   │       onboarding_list.html
│   │   │       payouts.html
│   │   │       reconciliation.html
│   │   │       
│   │   ├───compliance
│   │   │       aml_attestations.html
│   │   │       aml_backtest.html
│   │   │       aml_ctr.html
│   │   │       aml_jurisdictions.html
│   │   │       aml_queue.html
│   │   │       aml_reports.html
│   │   │       aml_report_detail.html
│   │   │       aml_retention.html
│   │   │       aml_scenarios.html
│   │   │       aml_terminated.html
│   │   │       aml_training.html
│   │   │       base_compliance.html
│   │   │       cases.html
│   │   │       case_history.html
│   │   │       create_case.html
│   │   │       dashboard.html
│   │   │       data_requests.html
│   │   │       escalations.html
│   │   │       generate_report.html
│   │   │       kyc_queue.html
│   │   │       licences.html
│   │   │       organisations.html
│   │   │       payouts.html
│   │   │       reports.html
│   │   │       sar_filing.html
│   │   │       search.html
│   │   │       user_audit.html
│   │   │       user_audit_profile.html
│   │   │       view_case.html
│   │   │       view_kyc.html
│   │   │       view_org.html
│   │   │       view_transaction.html
│   │   │       _aml_nav.html
│   │   │       
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
│   │   │       transport_vehicles.html
│   │   │       transport_vehicle_view.html
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
│   │   ├───settings
│   │   │       analytics.html
│   │   │       impersonation.html
│   │   │       moderation.html
│   │   │       platform.html
│   │   │       system.html
│   │   │       
│   │   └───wallet
│   │           webhook_detail.html
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
│   │       switch_role.html
│   │       verify_email.html
│   │       verify_options.html
│   │       verify_otp.html
│   │       verify_phone.html
│   │       verify_signup.html
│   │       
│   ├───compliance
│   │       dashboard.html
│   │       
│   ├───components
│   │       audit_timeline.html
│   │       kyc_badge.html
│   │       kyc_ribbon.html
│   │       kyc_tier_badge.html
│   │       media_gallery.html
│   │       media_upload.html
│   │       message_button.html
│   │       mfa_status.html
│   │       notification_bell.html
│   │       pending_reviews_widget.html
│   │       secure_action_modal.html
│   │       status_badge.html
│   │       suspicious_activity_widget.html
│   │       verify_banners.html
│   │       
│   ├───email
│   │       message_confirmation.html
│   │       organizer_message.html
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
│   │   │   │   analytics.html
│   │   │   │   assignment_dashboard.html
│   │   │   │   attendees_list.html
│   │   │   │   dashboard.html
│   │   │   │   events.html
│   │   │   │   organizers.html
│   │   │   │   pending.html
│   │   │   │   registrations.html
│   │   │   │   settings.html
│   │   │   │   staff.html
│   │   │   │   ticketing.html
│   │   │   │   
│   │   │   └───org
│   │   │           dashboard.html
│   │   │           
│   │   ├───attendee
│   │   │       my_registrations.html
│   │   │       register.html
│   │   │       registerO.html
│   │   │       registration_confirmation.html
│   │   │       registration_unavailable.html
│   │   │       
│   │   ├───community_host
│   │   │       register.html
│   │   │       
│   │   ├───organizer
│   │   │       accommodation_manage.html
│   │   │       accommodation_universal.html
│   │   │       analytics.html
│   │   │       assignments_universal.html
│   │   │       attendees.html
│   │   │       community_hosts.html
│   │   │       community_hosts_universal.html
│   │   │       create.html
│   │   │       dispatch_universal.html
│   │   │       edit.html
│   │   │       messages.html
│   │   │       my_events.html
│   │   │       organizer_dashboard.html
│   │   │       organizer_dashboard_1.html
│   │   │       organizer_dashboard_index.html
│   │   │       scanner.html
│   │   │       scanner_universal.html
│   │   │       staff_dashboard.html
│   │   │       staff_universal.html
│   │   │       waitlist.html
│   │   │       waitlist_universal.html
│   │   │       
│   │   ├───public
│   │   │       landing.html
│   │   │       list.html
│   │   │       list_pane.html
│   │   │       not_found.html
│   │   │       
│   │   ├───service_provider
│   │   │       service_provider_dashboard.html
│   │   │       
│   │   └───_partials
│   │           attendee_group_cell.html
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
│   ├───feed
│   │       _item_card.html
│   │       _layout_mixed.html
│   │       _layout_sections.html
│   │       _layout_tabbed.html
│   │       _sidebar_ad.html
│   │       
│   ├───geo
│   │       health.html
│   │       overview.html
│   │       
│   ├───identity
│   │       capabilities_dashboard.html
│   │       
│   ├───kyc
│   │       complete_profile.html
│   │       index.html
│   │       limits.html
│   │       moderate.html
│   │       moderate_document.html
│   │       overview.html
│   │       selfie_companion.html
│   │       status.html
│   │       upgrade.html
│   │       verify_address.html
│   │       verify_national_id.html
│   │       verify_upload.html
│   │       
│   ├───macros
│   │       admin_macros.html
│   │       booking_macros.html
│   │       flash_messages.html
│   │       form_macros.html
│   │       ui_macros.html
│   │       
│   ├───notifications
│   │   │   inbox.html
│   │   │   messages.html
│   │   │   
│   │   ├───email
│   │   │       admin_notification.html
│   │   │       booking_approved.html
│   │   │       booking_cancelled.html
│   │   │       booking_confirmation.html
│   │   │       booking_confirmed.html
│   │   │       booking_created.html
│   │   │       booking_payment_received_pending_approval.html
│   │   │       booking_pending_approval.html
│   │   │       booking_rejected.html
│   │   │       booking_update.html
│   │   │       default.html
│   │   │       deposit_confirmed.html
│   │   │       driver_assigned.html
│   │   │       event_accommodation_assigned.html
│   │   │       event_accommodation_cancelled.html
│   │   │       event_registered.html
│   │   │       event_reminder.html
│   │   │       internal_message.html
│   │   │       internal_reply.html
│   │   │       kyc_approved.html
│   │   │       kyc_rejected.html
│   │   │       login_alert.html
│   │   │       message_notification.html
│   │   │       new_signup.html
│   │   │       password_reset.html
│   │   │       payment_receipt.html
│   │   │       payment_received.html
│   │   │       platform_announcement.html
│   │   │       property_approved.html
│   │   │       property_archived.html
│   │   │       property_changes_requested.html
│   │   │       property_reinstated.html
│   │   │       property_rejected.html
│   │   │       property_restored.html
│   │   │       property_submitted.html
│   │   │       property_suspended.html
│   │   │       review_received.html
│   │   │       signup_notification.html
│   │   │       system_alert.html
│   │   │       transaction_completed.html
│   │   │       transaction_notification.html
│   │   │       verification_email.html
│   │   │       wallet_deposit.html
│   │   │       wallet_withdrawal.html
│   │   │       withdrawal_completed.html
│   │   │       
│   │   ├───push
│   │   │       booking_cancelled.json
│   │   │       booking_confirmation.json
│   │   │       booking_created.json
│   │   │       default.json
│   │   │       driver_assigned.json
│   │   │       event_registered.json
│   │   │       event_reminder.json
│   │   │       kyc_approved.json
│   │   │       kyc_rejected.json
│   │   │       new_signup.json
│   │   │       password_reset.json
│   │   │       review_received.json
│   │   │       system_alert.json
│   │   │       verification_email.json
│   │   │       wallet_deposit.json
│   │   │       wallet_withdrawal.json
│   │   │       
│   │   └───sms
│   │           booking_cancelled.txt
│   │           booking_confirmation.txt
│   │           booking_created.txt
│   │           default.txt
│   │           driver_assigned.txt
│   │           event_registered.txt
│   │           kyc_approved.txt
│   │           kyc_rejected.txt
│   │           new_signup.txt
│   │           password_reset.txt
│   │           review_received.txt
│   │           system_alert.txt
│   │           verification_email.txt
│   │           wallet_deposit.txt
│   │           wallet_withdrawal.txt
│   │           
│   ├───onboarding
│   │       choose.html
│   │       choose_individual.html
│   │       choose_organisation.html
│   │       driver_step1.html
│   │       driver_step2.html
│   │       driver_step3.html
│   │       event_organiser.html
│   │       fan.html.archived
│   │       host_step1.html
│   │       organisation_step1.html
│   │       organisation_step2.html
│   │       standard.html
│   │       _progress_bar.html
│   │       _wizard_styles.html
│   │       
│   ├───org
│   │       accommodation.html
│   │       bookings.html
│   │       content_dashboard.html
│   │       dashboard.html
│   │       dashboard_old.html
│   │       events.html
│   │       kyb.html
│   │       members.html
│   │       members_old.html
│   │       register.html
│   │       selector.html
│   │       settings.html
│   │       settings_old.html
│   │       transport.html
│   │       wallet.html
│   │       
│   ├───owner
│   │   │   add_payment_gateway.html
│   │   │   admin_audit_log.html
│   │   │   aggregator_settings.html
│   │   │   audit_logs.html
│   │   │   backups.html
│   │   │   backup_codes.html
│   │   │   cash_settings.html
│   │   │   compliance_settings.html
│   │   │   configure_aml_kyc.html
│   │   │   configure_fraud_detection.html
│   │   │   configure_nonce_protection.html
│   │   │   configure_rate_limiting.html
│   │   │   configure_travel_rule.html
│   │   │   danger_zone.html
│   │   │   dashboard.html
│   │   │   error_logs.html
│   │   │   impersonate.html
│   │   │   later.html
│   │   │   manage_aggregators.html
│   │   │   manage_regulator_access.html
│   │   │   manage_roles.html
│   │   │   module_settings.html
│   │   │   production_console.html
│   │   │   regulatory_reports.html
│   │   │   settings.html
│   │   │   super_admins.html
│   │   │   system_health.html
│   │   │   users.html
│   │   │   wallet_capabilities.html
│   │   │   wallet_settings.html
│   │   │   
│   │   ├───escrow
│   │   │       create.html
│   │   │       detail.html
│   │   │       index.html
│   │   │       settings.html
│   │   │       transactions.html
│   │   │       
│   │   ├───platform_accounts
│   │   │       detail.html
│   │   │       index.html
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
│   │           kyc_requirements.html
│   │           providers.html
│   │           system.html
│   │           
│   ├───placeholder
│   │       coming_soon.html
│   │       
│   ├───profile
│   │       account.html
│   │       account_pane.html
│   │       edit.html
│   │       edit_pane.html
│   │       public.html
│   │       public_pane.html
│   │       
│   ├───shell
│   │       dashboard_shell.html
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
│   │   │   homes.html
│   │   │   new_home.html
│   │   │   owner_application_review.html
│   │   │   register_vehicle.html
│   │   │   structure
│   │   │   vehicle_dashboard.html
│   │   │   vehicle_marketplace.html
│   │   │   
│   │   ├───admin
│   │   │       dashboard.html
│   │   │       details.html
│   │   │       drivers.html
│   │   │       driver_detail.html
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
│   │   │   │   assign.html
│   │   │   │   edit.html
│   │   │   │   history.html
│   │   │   │   index.html
│   │   │   │   payments.html
│   │   │   │   show.html
│   │   │   │   timeline.html
│   │   │   │   _trips_panel.html
│   │   │   │   
│   │   │   └───components
│   │   │           _booking_action.html
│   │   │           _booking_details.html
│   │   │           _fare_summary.html
│   │   │           _trip_search.html
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
│   │   ├───driver
│   │   │       base.html
│   │   │       driver_dashboard.html
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
│   │   ├───passengers
│   │   │       claim.html
│   │   │       
│   │   ├───rides
│   │   │       show.html
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
│   │   │   base_user_dashboard.html
│   │   │   content_dashboard.html
│   │   │   my_registrations.html
│   │   │   preferences.html
│   │   │   settings_pane.html
│   │   │   user_dashboard.html
│   │   │   _pane_base.html
│   │   │   _reg_card.html
│   │   │   
│   │   ├───partials
│   │   │       _fan_teams_widget.html
│   │   │       _tournament_hero.html
│   │   │       
│   │   └───settings
│   │           interests.html
│   │           
│   └───wallet
│       │   agent_applications.html
│       │   agent_application_detail.html
│       │   agent_apply.html
│       │   agent_cashout_request.html
│       │   agent_payout_history.html
│       │   agent_payout_request.html
│       │   agent_portal.html
│       │   agent_refund.html
│       │   agent_requirements.html
│       │   agent_statement.html
│       │   base_wallet.html
│       │   compliance.html
│       │   deposit.html
│       │   deposit_pane.html
│       │   dump.html
│       │   fx_rates.html
│       │   original_file.html
│       │   overview.html
│       │   payment_gateway.html
│       │   send.html
│       │   send_pane.html
│       │   transactions.html
│       │   transaction_history.html
│       │   transfer.html
│       │   wallet_activate.html
│       │   wallet_create.html
│       │   wallet_dashboard.html
│       │   wallet_dashboard_pane.html
│       │   wallet_home.html
│       │   wallet_settings.html
│       │   WALLET_SYSTEM_DOCUMENTATION.md
│       │   wallet_terms.html
│       │   wallet_transactions.html
│       │   webhooks_list.html
│       │   webhooks_stats.html
│       │   webhook_detail.html
│       │   withdraw.html
│       │   _deposit_content.html
│       │   _send_content.html
│       │   
│       ├───admin
│       │       financial_controller.html
│       │       payment_aggregator.html
│       │       regulator_access.html
│       │       sandbox_testing.html
│       │       
│       └───financial
│               account_detail.html
│               account_lookup.html
│               
├───templates_backup
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
│   │   │       transport_vehicles.html
│   │   │       transport_vehicle_view.html
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
├───tests
│   │   backup_db.py
│   │   check_alembic.py
│   │   check_bugs.py
│   │   check_db.py
│   │   check_db_schema.py
│   │   check_db_status.py
│   │   check_enum_detail.py
│   │   check_model.py
│   │   check_schema.py
│   │   check_settings_table.py
│   │   check_table.py
│   │   check_tables.py
│   │   cleanup_4b1.py
│   │   clear_cache.py
│   │   compare_model_db.py
│   │   conftest.py
│   │   db_connector.py
│   │   ERRORS_RESOLVED.md
│   │   find_wallet_relationship.py
│   │   fix_enum_issue.py
│   │   fix_events_schema.py
│   │   fix_geometry_issue.py
│   │   fix_migration_gist.py
│   │   fix_owner.py
│   │   full_db_audit.py
│   │   generate_migration.py
│   │   hooks_web_unit_tests.py
│   │   init_settings.py
│   │   inspect_db.py
│   │   list_endpoints.py
│   │   manage.py
│   │   phase_1.py
│   │   phase_2.py
│   │   postgres_contract.py
│   │   read_llater.txt
│   │   run_event_tests.py
│   │   run_event_tests.py.bak
│   │   sample_users.py
│   │   scanner.py
│   │   seed_roles.py
│   │   seed_roles_simple.py
│   │   setup_owner.py
│   │   simpletests.py
│   │   simple_template_check.py
│   │   temp_fix.py
│   │   test roles.py
│   │   testing12.py
│   │   tests_alone.py
│   │   test_accommodation_availability_distance.py
│   │   test_accommodation_booking.py
│   │   test_accommodation_capacity_rules.py
│   │   test_accommodation_checkout_processes.py
│   │   test_accommodation_date_range_rules.py
│   │   test_accommodation_home.py
│   │   test_accommodation_lifecycle_verification.py
│   │   test_accommodation_modify_booking_dates.py
│   │   test_accommodation_physical_room_assignment.py
│   │   test_accommodation_property_lifecycle.py
│   │   test_accommodation_roomtype.py
│   │   test_accommodation_transaction_recovery.py
│   │   test_addendum2_registration.py
│   │   test_agent_system_full.py
│   │   test_alipay_model.py
│   │   test_all_schemas.py
│   │   test_application_startup.py
│   │   test_assignment_ownership_boundary.py
│   │   test_assign_revoke_org_role.py
│   │   test_attendee_accommodation_booking.py
│   │   test_audit_system.py
│   │   test_audit_system.py.bak
│   │   test_auth_context.py
│   │   test_auth_helpers_stale_role.py
│   │   test_auth_import.py
│   │   test_auth_require_role.py
│   │   test_backlog1179_auth_security.py
│   │   test_batch3_final_package.py
│   │   test_bl23_transport_permission_guards.py
│   │   test_booking_mode.py
│   │   test_booking_mode_persistence.py
│   │   test_boot.py
│   │   test_canonical_identity_center.py
│   │   test_can_org_host.py
│   │   test_capability_operations.py
│   │   test_compliance_kyc_action.py
│   │   test_concurrency.py
│   │   test_concurrency_simple.py
│   │   test_coord_error.py
│   │   test_current.py
│   │   test_current.py.bak
│   │   test_database_contract.py
│   │   test_date_boundary_conversions.py
│   │   test_db_public_id.py
│   │   test_dead_letter_alert.py
│   │   test_debug_fake.py
│   │   test_deletion_guard.py
│   │   test_dev_tls.py
│   │   test_driver_context_recovery.py
│   │   test_driver_workspace_activation.py
│   │   test_driver_workspace_consolidation.py
│   │   test_driver_workspace_sections.py
│   │   test_email_verification_magic_link.py
│   │   test_email_verification_routes.py
│   │   test_event.py.bak
│   │   test_events.py
│   │   test_events_ownership_characterization.py
│   │   test_events_user_workflows.py
│   │   test_event_accommodation_assignment_flow.py
│   │   test_event_inventory_concurrency.py
│   │   test_event_registration_availability.py
│   │   test_event_transfer_lifecycle.py
│   │   test_event_workflow.py
│   │   test_event_workflow.py.bak
│   │   test_exception_keyword_args.py
│   │   test_fan_kyc.py
│   │   test_fix_accommodation_unit_availability.py
│   │   test_forensic_audit.py
│   │   test_geo_activity.py
│   │   test_geo_contract.py
│   │   test_geo_foundation.py
│   │   test_geo_geocoding.py
│   │   test_geo_history.py
│   │   test_geo_integration.py
│   │   test_geo_map_renderer.py
│   │   test_geo_nearby.py
│   │   test_geo_realtime.py
│   │   test_geo_rider_tracking.py
│   │   test_geo_routing.py
│   │   test_geo_search_contract.py
│   │   test_get_organizer_metrics_canonical.py
│   │   test_global_transaction_recovery.py
│   │   test_guest_assignment_account_optional.py
│   │   test_guest_coordination_accommodation.py
│   │   test_guest_coordination_contract.py
│   │   test_health_rate_limit.py
│   │   test_identity_bank_refinements.py
│   │   test_identity_events.py
│   │   test_idguard.py
│   │   test_impersonation.py
│   │   test_impersonation_simple.py
│   │   test_imports.py
│   │   test_isolation_contract.py
│   │   test_kyc_compliance.py
│   │   test_kyc_debug_tmp.py
│   │   test_kyc_identity_bidirectional.py
│   │   test_kyc_integration.py
│   │   test_kyc_limit_authorization.py
│   │   test_kyc_render_tmp.py
│   │   test_kyc_reupload.py
│   │   test_kyc_selfie_pairing.py
│   │   test_kyc_single_entry_national_id.py
│   │   test_kyc_single_entry_upload.py
│   │   test_kyc_status_consistency.py
│   │   test_kyc_upload_validation.py
│   │   test_live_module_isolation.py
│   │   test_load.py
│   │   test_load.py.bak
│   │   test_location_best.cjs
│   │   test_loose_coupling.py
│   │   test_module_integration.py
│   │   test_module_integration_simple.py
│   │   test_module_isolation.py
│   │   test_nav_follows_active_context.py
│   │   test_notifications_transport_payloads.py
│   │   test_notify_driver_assigned_bl22.py
│   │   test_onboarding.py
│   │   test_onboarding_new.py
│   │   test_onboarding_stage4.py
│   │   test_org10_adversarial_cross_property.py
│   │   test_org9_public_boundaries.py
│   │   test_organisation_classification.py
│   │   test_organisation_role_provisioning.py
│   │   test_organisation_slug.py
│   │   test_org_admin_remediation_http.py
│   │   test_org_classification_repair.py
│   │   test_org_creation_rbac_4b1.py
│   │   test_org_host_production_path.py
│   │   test_org_permission_read_path.py
│   │   test_org_provider_capability.py
│   │   test_org_workspace.py
│   │   test_orm_insert.py
│   │   test_owner_trust_integration.py
│   │   test_owner_trust_integration.py.bak
│   │   test_payment_flow.py
│   │   test_payment_method_capabilities.py
│   │   test_phase_c1_vehicle_ownership.py
│   │   test_phone_verification.py
│   │   test_pin_lockout_and_transfer_and_idempotency.py
│   │   test_policy_can_org_id_contract.py
│   │   test_policy_table.py
│   │   test_process_webhook_dead_letter.py
│   │   test_production_console.py
│   │   test_provider_participation.py
│   │   test_raw_insert.py
│   │   test_rdprobe_tmp.py
│   │   test_registration_flow.py
│   │   test_registration_flow.py.bak
│   │   test_registration_row_lock_concurrency.py
│   │   test_regulatory_volume_policy.py
│   │   test_rider_matching_search.cjs
│   │   test_rider_sync_driver_card.cjs
│   │   test_rooms_requested.py
│   │   test_schema_check.py
│   │   test_services.py
│   │   test_simple.py
│   │   test_simple_imports.py
│   │   test_snippet.py
│   │   test_stage4b2_capability_enforcement.py
│   │   test_stage4b3_organisation_capabilities.py
│   │   test_stage4b5_transport.py
│   │   test_stage4b6_org_write_gate.py
│   │   test_stage4b8_context_switch_e2e_proof.py
│   │   test_stage4b9_context_switch_nav_e2e.py
│   │   test_stage5b2_assignment_lifecycle.py
│   │   test_stage5b3_handoff_architecture.py
│   │   test_stage5b4_sync_synchronization.py
│   │   test_stage5b5_cancellation_reassignment_lifecycle.py
│   │   test_stage62a1_transport_serialization.py
│   │   test_stage62a_transport_auth_public_id.py
│   │   test_table_info.py
│   │   test_template_fix.py
│   │   test_template_rendering.py
│   │   test_transaction_intent.py
│   │   test_transport_admin_canonical_overview.py
│   │   test_transport_admin_permission_authority.py
│   │   test_transport_booking_geocoding.py
│   │   test_transport_booking_route_path.py
│   │   test_transport_booking_show.py
│   │   test_transport_concurrent_claim.py
│   │   test_transport_coordination_contract.py
│   │   test_transport_d2_evidence.py
│   │   test_transport_d3_scheduled_execution.py
│   │   test_transport_d5_execution_lifecycle.py
│   │   test_transport_dashboard_overview.py
│   │   test_transport_decorator_role_required.py
│   │   test_transport_drivers_admin_lock.py
│   │   test_transport_driver_dashboard.py
│   │   test_transport_fare_engine.py
│   │   test_transport_fare_governance.py
│   │   test_transport_front_page.py
│   │   test_transport_geographic_contract.py
│   │   test_transport_matching_distance.py
│   │   test_transport_my_trips_page.py
│   │   test_transport_passengers.py
│   │   test_transport_pwa_shell.py
│   │   test_transport_restful_auth.py
│   │   test_transport_rider_page.py
│   │   test_transport_ride_options.py
│   │   test_transport_service_integrity.py
│   │   test_transport_stage5t3.py
│   │   test_transport_stage5t4.py
│   │   test_transport_tracking_distance.py
│   │   test_transport_tracking_live.py
│   │   test_transport_vehicle_edit_update.py
│   │   test_trust_card.py
│   │   test_trust_system.py
│   │   test_users_schema.py
│   │   test_user_raw.py
│   │   test_wallet_authorization_limits.py
│   │   test_zz_tmp_login_context_verify.py
│   │   transport_model.py
│   │   update_models_no_geometry.py
│   │   user_roles_id.py
│   │   verify_architecture.py
│   │   verify_concurrency.py
│   │   verify_db.py
│   │   verify_db.py.bak
│   │   verify_fix.py
│   │   verify_obed.py
│   │   verify_tables.py
│   │   verify_template.py
│   │   verify_transport_tables.py
│   │   _diag_lock_pytest.py
│   │   _diag_lock_pytest2.py
│   │   _probe_f01_balance.py
│   │   __init__.py
│   │   
│   ├───.pytest_cache
│   │   │   .gitignore
│   │   │   CACHEDIR.TAG
│   │   │   README.md
│   │   │   
│   │   └───v
│   │       └───cache
│   │               nodeids
│   │               stepwise
│   │               
│   ├───auth
│   │   │   test_login_identifier_contract.py
│   │   │   
│   ├───helpers
│   │   │   isolation.py
│   │   │   __init__.py
│   │   │   
│   ├───integration
│   │   │   test_booking_idempotency.py
│   │   │   test_reservation_callback_idempotency.py
│   │   │   
│   ├───notifications
│   │   │   test_accommodation_reminders.py
│   │   │   test_bell_system_notifications.py
│   │   │   test_events.py
│   │   │   test_models.py
│   │   │   test_user_controls.py
│   │   │   __init__.py
│   │   │   
│   ├───transport
│   │   │   test_assignment_release_supply_invariant.py
│   │   │   test_booking_request_points.py
│   │   │   test_dashboard_cache_scope.py
│   │   │   test_directions_circuit_breaker.py
│   │   │   test_driver_console.py
│   │   │   test_driver_location_age_display.py
│   │   │   test_driver_location_permission.py
│   │   │   test_driver_offer_contract.py
│   │   │   test_driver_offer_passenger_first_name.py
│   │   │   test_idempotency_contract.py
│   │   │   test_marketplace_operational_flow.py
│   │   │   test_marketplace_service_organisation_ownership.py
│   │   │   test_marketplace_ux_harmonisation.py
│   │   │   test_match01_assignment_race.py
│   │   │   test_match01_no_match_terminals.py
│   │   │   test_match01_payload_stripping.py
│   │   │   test_match01_recovery_beat.py
│   │   │   test_match01_retry.py
│   │   │   test_match01_silent_rejection.py
│   │   │   test_match01_status_json.py
│   │   │   test_match01_status_string_contract.py
│   │   │   test_matching_pickup_zone.py
│   │   │   test_moderator_actions.py
│   │   │   test_org_registration_lock.py
│   │   │   test_promotion_apply_promo_no_double_discount.py
│   │   │   test_promotion_first_ride_branch.py
│   │   │   test_public_endpoint_rate_limits.py
│   │   │   test_reservation_api.py
│   │   │   test_reservation_d3.py
│   │   │   test_reservation_expiry.py
│   │   │   test_supply00_override.py
│   │   │   test_tile_provider_config.py
│   │   │   
│   ├───wallet
│   │   │   conftest.py
│   │   │   test_f01_balance_boundary.py
│   │   │   test_f02_cancellation_refund.py
│   │   │   test_f03a_balance_pay_atomicity.py
│   │   │   test_f03b_refund_payout_idempotency.py
│   │   │   test_f03c_is_admin_fix.py
│   │   │   test_f11_penalty_idempotency_key.py
│   │   │   test_ledger_concurrency.py
│   │   │   test_ledger_concurrency.py.bak
│   │   │   test_payment_identity.py
│   │   │   test_withdraw_api.py
│   │   │   __init__.py
│   │   │
(.venv) PS C:\Users\OBED\Desktop\afcon360_app>

