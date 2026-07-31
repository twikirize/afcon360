├───app
│   │   celery_app.py
│   │   CHECK_DUAL_ID_ISSUES.md
│   │   cli.py
│   │   config.py
│   │   extensions.py
│   │   placeholder.py
│   │   providers.py
│   │   routes.py
│   │   utils.py
│   │   __init__.py
│   │   
│   ├───accommodation
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
│   │   │   │   commission.py
│   │   │   │   guest_identity.py
│   │   │   │   guest_profile.py
│   │   │   │   host_profile.py
│   │   │   │   moderation.py
│   │   │   │   platform_override.py
│   │   │   │   property.py
│   │   │   │   property_document.py
│   │   │   │   property_payment_method.py
│   │   │   │   review.py
│   │   │   │   room.py
│   │   │   │   wishlist.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           availability.cpython-313.pyc
│   │   │           booking.cpython-313.pyc
│   │   │           booking_payment.cpython-313.pyc
│   │   │           booking_policy.cpython-313.pyc
│   │   │           commission.cpython-313.pyc
│   │   │           guest_identity.cpython-313.pyc
│   │   │           guest_profile.cpython-313.pyc
│   │   │           host_profile.cpython-313.pyc
│   │   │           moderation.cpython-313.pyc
│   │   │           platform_override.cpython-313.pyc
│   │   │           property.cpython-313.pyc
│   │   │           property_document.cpython-313.pyc
│   │   │           property_payment_method.cpython-313.pyc
│   │   │           review.cpython-313.pyc
│   │   │           room.cpython-313.pyc
│   │   │           wishlist.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───services
│   │   │   │   abuse_prevention_service.py
│   │   │   │   ai_search_service.py
│   │   │   │   ai_trip_planner_service.py
│   │   │   │   availability_service.py
│   │   │   │   blockchain_reviews_service.py
│   │   │   │   booking_service.py
│   │   │   │   competitive_intelligence_service.py
│   │   │   │   dynamic_pricing_service.py
│   │   │   │   gamified_loyalty_service.py
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
│   │   │   │   review_service.py
│   │   │   │   search_service.py
│   │   │   │   trust_service.py
│   │   │   │   urgency_service.py
│   │   │   │   verification_engine.py
│   │   │   │   voice_booking_service.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   ├───payment_processors
│   │   │   │   │   base.py
│   │   │   │   │   card_processor.py
│   │   │   │   │   invoice_processor.py
│   │   │   │   │   mobile_money_processor.py
│   │   │   │   │   mock_gateway_processor.py
│   │   │   │   │   wallet_processor.py
│   │   │   │   │   __init__.py
│   │   │   │   │   
│   │   │   │   └───__pycache__
│   │   │   │           base.cpython-313.pyc
│   │   │   │           card_processor.cpython-313.pyc
│   │   │   │           invoice_processor.cpython-313.pyc
│   │   │   │           mobile_money_processor.cpython-313.pyc
│   │   │   │           mock_gateway_processor.cpython-313.pyc
│   │   │   │           wallet_processor.cpython-313.pyc
│   │   │   │           __init__.cpython-313.pyc
│   │   │   │           
│   │   │   └───__pycache__
│   │   │           abuse_prevention_service.cpython-313.pyc
│   │   │           availability_service.cpython-313.pyc
│   │   │           booking_service.cpython-313.pyc
│   │   │           host_service.cpython-313.pyc
│   │   │           identity_service.cpython-313.pyc
│   │   │           marketplace_service.cpython-313.pyc
│   │   │           media_service.cpython-313.pyc
│   │   │           moderation_service.cpython-313.pyc
│   │   │           payment_option_service.cpython-313.pyc
│   │   │           payment_policy_service.cpython-313.pyc
│   │   │           pricing_service.cpython-313.pyc
│   │   │           readiness_service.cpython-313.pyc
│   │   │           review_service.cpython-313.pyc
│   │   │           search_service.cpython-313.pyc
│   │   │           urgency_service.cpython-313.pyc
│   │   │           wallet_service.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───state_machine
│   │   │   │   booking_states.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           booking_states.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   └───__pycache__
│   │           forms.cpython-313.pyc
│   │           routes.cpython-313.pyc
│   │           sockets.cpython-313.pyc
│   │           utils.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───admin
│   │   │   decorators.py
│   │   │   hooks.py
│   │   │   models.py
│   │   │   routes.py
│   │   │   routes_extended.py.bak
│   │   │   routes_ultimate.py
│   │   │   routes_ultimate.py.bak
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
│   │   │   └───__pycache__
│   │   │           payment_methods.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───auditor
│   │   │   │   routes.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           routes.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───compliance
│   │   │   │   models.py
│   │   │   │   routes.py
│   │   │   │   services.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           models.cpython-313.pyc
│   │   │           routes.cpython-313.pyc
│   │   │           services.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───models
│   │   │   │   core.py
│   │   │   │   emergency_access.py
│   │   │   │   moderation.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           core.cpython-313.pyc
│   │   │           emergency_access.cpython-313.pyc
│   │   │           moderation.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───moderator
│   │   │   │   pipeline.py
│   │   │   │   registry.py
│   │   │   │   routes.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           registry.cpython-313.pyc
│   │   │           routes.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───owner
│   │   │   │   audit.py
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
│   │   │   ├───api
│   │   │   │   │   module_api.py
│   │   │   │   │   
│   │   │   │   └───__pycache__
│   │   │   │           module_api.cpython-313.pyc
│   │   │   │           
│   │   │   └───__pycache__
│   │   │           audit.cpython-313.pyc
│   │   │           csp_routes.cpython-313.pyc
│   │   │           decorators.cpython-313.pyc
│   │   │           escrow_routes.cpython-313.pyc
│   │   │           escrow_services.cpython-313.pyc
│   │   │           models.cpython-313.pyc
│   │   │           rate_limit_notifications.cpython-313.pyc
│   │   │           rate_limit_service.cpython-313.pyc
│   │   │           routes.cpython-313.pyc
│   │   │           security_routes.cpython-313.pyc
│   │   │           security_service.cpython-313.pyc
│   │   │           utils.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
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
│   │   │   └───__pycache__
│   │   │           accommodation_admin.cpython-313.pyc
│   │   │           event_manager.cpython-313.pyc
│   │   │           org_admin.cpython-313.pyc
│   │   │           org_member.cpython-313.pyc
│   │   │           settings.cpython-313.pyc
│   │   │           tourism_admin.cpython-313.pyc
│   │   │           transport_admin.cpython-313.pyc
│   │   │           wallet_admin.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───services
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───staff
│   │   │       __init__.py
│   │   │       
│   │   ├───support
│   │   │   │   routes.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           routes.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   └───__pycache__
│   │           decorators.cpython-313.pyc
│   │           routes.cpython-313.pyc
│   │           routes_ultimate.cpython-313.pyc
│   │           trust_settings.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───api
│   │   │   health.py
│   │   │   
│   │   └───__pycache__
│   │           health.cpython-313.pyc
│   │           
│   ├───audit
│   │   │   comprehensive_audit.py
│   │   │   forensic_audit.py
│   │   │   models.py
│   │   │   user.py
│   │   │   __init__.py
│   │   │   
│   │   └───__pycache__
│   │           comprehensive_audit.cpython-313.pyc
│   │           forensic_audit.cpython-313.pyc
│   │           models.cpython-313.pyc
│   │           user.cpython-313.pyc
│   │           __init__.cpython-313.pyc
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
│   │   ├───services
│   │   │       org.py
│   │   │       
│   │   └───__pycache__
│   │           config_model.cpython-313.pyc
│   │           decorators.cpython-313.pyc
│   │           delegation.cpython-313.pyc
│   │           helpers.cpython-313.pyc
│   │           kyc_compliance.cpython-313.pyc
│   │           kyc_routes.cpython-313.pyc
│   │           onboarding_routes.cpython-313.pyc
│   │           otp_service.cpython-313.pyc
│   │           policy.cpython-313.pyc
│   │           roles.cpython-313.pyc
│   │           routes.cpython-313.pyc
│   │           seed_roles.cpython-313.pyc
│   │           services.cpython-313.pyc
│   │           sessions.cpython-313.pyc
│   │           tokens.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───backup
│   │       backup_service.py
│   │       
│   ├───cli
│   │   │   owner.py
│   │   │   __init__.py
│   │   │   
│   │   └───__pycache__
│   │           owner.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───compliance
│   │       aml_service.py
│   │       
│   ├───core
│   │   │   context.py
│   │   │   model_registry.py
│   │   │   
│   │   └───__pycache__
│   │           context.cpython-313.pyc
│   │           model_registry.cpython-313.pyc
│   │           
│   ├───Documentation
│   │       ADMIN_CSP_MIGRATION_SUMMARY.md
│   │       ARCHITECTURE_PASS_5_FINAL.md
│   │       AUTH_SYSTEM_ARCHITECTURE.md
│   │       AUTH_SYSTEM_IMPLEMENTATION.md
│   │       CLI Commands Reference.md
│   │       CSP_POLICY.md
│   │       FLASK_LOGIN_STATIC_FILES_BUG.md
│   │       IDENTITY_POLICIES.md
│   │       ID_SYSTEM_RULES.md
│   │       MODERATOR_CAPABILITIES.md
│   │       MODERATOR_SYSTEM_COMPLETE.md
│   │       NAV_REDESIGN_PASS_6.md
│   │       ONBOARDING_IMPLEMENTATION_GUIDE (1).md
│   │       ONBOARDING_IMPLEMENTATION_GUIDE.md
│   │       ONBOARDING_IMPLEMENTATION_REPORT.md
│   │       ONBOARDING_REMEDIATION_PASS_2.md
│   │       PROFILE_KYC_SYSTEM.md
│   │       RATE_LIMITING_IMPLEMENTATION.md
│   │       RECONCILE_WALLET.md
│   │       SESSION_EXPORT_CSP_MIGRATION_2026-04-27.md
│   │       SYSTEM_OVERVIEW.md
│   │       TRUST_BASED_SECURITY.md
│   │       WALLET_AND_USER IDENTITIES.MD
│   │       
│   ├───events
│   │   │   assignment.py
│   │   │   attendee_accounts.py
│   │   │   bulk_upload.py
│   │   │   constants.py
│   │   │   events.md
│   │   │   Events_CONTEXT.md
│   │   │   metrics_service.py
│   │   │   models.py
│   │   │   payment_config.py
│   │   │   payment_service.py
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
│   │   │   view_models.py
│   │   │   __init__.py
│   │   │   
│   │   └───__pycache__
│   │           attendee_accounts.cpython-313.pyc
│   │           bulk_upload.cpython-313.pyc
│   │           constants.cpython-313.pyc
│   │           models.cpython-313.pyc
│   │           payment_config.cpython-313.pyc
│   │           payment_service.cpython-313.pyc
│   │           permissions.cpython-313.pyc
│   │           routes.cpython-313.pyc
│   │           routes_community_hosts.cpython-313.pyc
│   │           services.cpython-313.pyc
│   │           settings_model.cpython-313.pyc
│   │           settings_routes.cpython-313.pyc
│   │           signals.cpython-313.pyc
│   │           signal_handlers.cpython-313.pyc
│   │           tasks.cpython-313.pyc
│   │           trust_service.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───event_accommodation
│   │   │   __init__.py
│   │   │   
│   │   ├───models
│   │   │   │   badge.py
│   │   │   │   opportunity.py
│   │   │   │   visibility.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           badge.cpython-313.pyc
│   │   │           opportunity.cpython-313.pyc
│   │   │           visibility.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───services
│   │   │       badge_service.py
│   │   │       discovery_service.py
│   │   │       invitation_service.py
│   │   │       matching_service.py
│   │   │       
│   │   └───__pycache__
│   │           __init__.cpython-313.pyc
│   │           
│   ├───fan
│   │   │   GEMINI_AGENT_FAN_MERGE.md
│   │   │   migrate_fan_to_profile.py
│   │   │   models.py
│   │   │   routes.py
│   │   │   __init__.py
│   │   │   
│   │   ├───services
│   │   │   │   fan_profile_service.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           fan_profile_service.cpython-313.pyc
│   │   │           
│   │   └───__pycache__
│   │           models.cpython-313.pyc
│   │           routes.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
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
│   │   └───__pycache__
│   │           organization_forms.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───identity
│   │   │   routes.py
│   │   │   services.py
│   │   │   __init__.py
│   │   │   
│   │   ├───individuals
│   │   │   │   individual_document.py
│   │   │   │   individual_verification.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           individual_document.cpython-313.pyc
│   │   │           individual_verification.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───models
│   │   │   │   compliance_audit_log.py
│   │   │   │   compliance_settings.py
│   │   │   │   kyb.py
│   │   │   │   licence_document.py
│   │   │   │   note.py
│   │   │   │   organisation.py
│   │   │   │   organisation_controller.py
│   │   │   │   organisation_member.py
│   │   │   │   organization_types.py
│   │   │   │   roles_permission.py
│   │   │   │   user.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           compliance_audit_log.cpython-313.pyc
│   │   │           compliance_settings.cpython-313.pyc
│   │   │           kyb.cpython-313.pyc
│   │   │           licence_document.cpython-313.pyc
│   │   │           organisation.cpython-313.pyc
│   │   │           organisation_controller.cpython-313.pyc
│   │   │           organisation_member.cpython-313.pyc
│   │   │           organization_types.cpython-313.pyc
│   │   │           roles_permission.cpython-313.pyc
│   │   │           user.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───services
│   │   │   │   organization_permissions.py
│   │   │   │   organization_registration.py
│   │   │   │   user_roles.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           organization_permissions.cpython-313.pyc
│   │   │           organization_registration.cpython-313.pyc
│   │   │           user_roles.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   └───__pycache__
│   │           routes.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───kyc
│   │   │   models.py
│   │   │   nira_verification.py
│   │   │   routes.py
│   │   │   services.py
│   │   │   upgrade_routes.py
│   │   │   __init__.py
│   │   │   
│   │   └───__pycache__
│   │           models.cpython-313.pyc
│   │           nira_verification.cpython-313.pyc
│   │           routes.cpython-313.pyc
│   │           services.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
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
│   │   │   │   image.py
│   │   │   │   video.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           image.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───storage
│   │   │   │   local.py
│   │   │   │   oci.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           local.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───utils
│   │   │   │   content_moderator.py
│   │   │   │   monitoring.py
│   │   │   │   perceptual_hash.py
│   │   │   │   quota_manager.py
│   │   │   │   virus_scanner.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           content_moderator.cpython-313.pyc
│   │   │           perceptual_hash.cpython-313.pyc
│   │   │           quota_manager.cpython-313.pyc
│   │   │           virus_scanner.cpython-313.pyc
│   │   │           
│   │   └───__pycache__
│   │           admin_routes.cpython-313.pyc
│   │           models.cpython-313.pyc
│   │           routes.cpython-313.pyc
│   │           service.cpython-313.pyc
│   │           settings_service.cpython-313.pyc
│   │           tasks.cpython-313.pyc
│   │           validators.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───middleware
│   │   │   reload_modules.py
│   │   │   
│   │   └───__pycache__
│   │           reload_modules.cpython-313.pyc
│   │           
│   ├───models
│   │   │   analytics.py
│   │   │   audit.py
│   │   │   base.py
│   │   │   notification.py
│   │   │   system_config.py
│   │   │   theme.py
│   │   │   
│   │   └───__pycache__
│   │           base.cpython-313.pyc
│   │           notification.cpython-313.pyc
│   │           system_config.cpython-313.pyc
│   │           theme.cpython-313.pyc
│   │           
│   ├───owner
│   │   └───routes
│   │       │   role_management.py
│   │       │   settings.py
│   │       │   
│   │       └───__pycache__
│   │               role_management.cpython-313.pyc
│   │               
│   ├───profile
│   │   │   models.py
│   │   │   routes.py
│   │   │   __init__.py
│   │   │   
│   │   └───__pycache__
│   │           models.cpython-313.pyc
│   │           routes.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───services
│   │   │   analytics.py
│   │   │   module_toggle_service.py
│   │   │   notification_service.py
│   │   │   sms_service.py
│   │   │   __init__.py
│   │   │   
│   │   └───__pycache__
│   │           analytics.cpython-313.pyc
│   │           module_toggle_service.cpython-313.pyc
│   │           notification_service.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───tasks
│   │   │   cleanup.py
│   │   │   reconcile.py
│   │   │   webhook_processor.py
│   │   │   
│   │   └───__pycache__
│   │           cleanup.cpython-313.pyc
│   │           webhook_processor.cpython-313.pyc
│   │           
│   ├───tools
│   │   │   inspect_project.py
│   │   │   theme_routes.py
│   │   │   theme_service.py
│   │   │   
│   │   └───__pycache__
│   │           theme_routes.cpython-313.pyc
│   │           theme_service.cpython-313.pyc
│   │           
│   ├───tourism
│   │   │   routes.py
│   │   │   __init__.py
│   │   │   
│   │   └───__pycache__
│   │           routes.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───tournament
│   │   │   routes.py
│   │   │   __init__.py
│   │   │   
│   │   └───__pycache__
│   │           routes.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───transport
│   │   │   decorator.py
│   │   │   event_listeners.py
│   │   │   listeners.py
│   │   │   models.py
│   │   │   routes.py
│   │   │   routes.py~
│   │   │   view_models.py
│   │   │   __init__.py
│   │   │   
│   │   ├───api
│   │   │   │   analytic_routes.py
│   │   │   │   booking_routes.py
│   │   │   │   dashboard_routes.py
│   │   │   │   driver_routes.py
│   │   │   │   incident_routes.py
│   │   │   │   organisation_routes.py
│   │   │   │   routes.py
│   │   │   │   routes.py.bak
│   │   │   │   route_routes.py
│   │   │   │   settings_routes.py
│   │   │   │   utils.py
│   │   │   │   vehicle_routes.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           analytic_routes.cpython-313.pyc
│   │   │           booking_routes.cpython-313.pyc
│   │   │           dashboard_routes.cpython-313.pyc
│   │   │           driver_routes.cpython-313.pyc
│   │   │           incident_routes.cpython-313.pyc
│   │   │           organisation_routes.cpython-313.pyc
│   │   │           routes.cpython-313.pyc
│   │   │           route_routes.cpython-313.pyc
│   │   │           settings_routes.cpython-313.pyc
│   │   │           vehicle_routes.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───services
│   │   │   │   booking_service.py
│   │   │   │   dashboard_service.py
│   │   │   │   external_platforms.py
│   │   │   │   future_adds.py
│   │   │   │   matching_service.py
│   │   │   │   notification_service.py
│   │   │   │   payment_service.py
│   │   │   │   promotion_service.py
│   │   │   │   provider_service.py
│   │   │   │   settings_service.py
│   │   │   │   tracking_service.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           booking_service.cpython-313.pyc
│   │   │           dashboard_service.cpython-313.pyc
│   │   │           external_platforms.cpython-313.pyc
│   │   │           matching_service.cpython-313.pyc
│   │   │           notification_service.cpython-313.pyc
│   │   │           payment_service.cpython-313.pyc
│   │   │           promotion_service.cpython-313.pyc
│   │   │           provider_service.cpython-313.pyc
│   │   │           settings_service.cpython-313.pyc
│   │   │           tracking_service.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───utils
│   │   │   │   helpers.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           helpers.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   └───__pycache__
│   │           decorator.cpython-313.pyc
│   │           listeners.cpython-313.pyc
│   │           models.cpython-313.pyc
│   │           routes.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───user
│   │   │   routes.py
│   │   │   use_dashboard.md
│   │   │   
│   │   └───__pycache__
│   │           routes.cpython-313.pyc
│   │           
│   ├───utils
│   │   │   audit.py
│   │   │   caching.py
│   │   │   db_retry.py
│   │   │   error_handler.py
│   │   │   exceptions.py
│   │   │   idempotency.py
│   │   │   id_guard.py
│   │   │   id_helpers.py
│   │   │   id_kinds.py
│   │   │   id_validator.py
│   │   │   module_disabled.py
│   │   │   module_guard.py
│   │   │   module_switch.py
│   │   │   monitoring.py
│   │   │   rate_limiting.py
│   │   │   redis_lock.py
│   │   │   security.py
│   │   │   template_helpers.py
│   │   │   transactions.py
│   │   │   validators.py
│   │   │   widget_loader.py
│   │   │   __init__.py
│   │   │   
│   │   └───__pycache__
│   │           audit.cpython-313.pyc
│   │           caching.cpython-313.pyc
│   │           db_retry.cpython-313.pyc
│   │           error_handler.cpython-313.pyc
│   │           exceptions.cpython-313.pyc
│   │           idempotency.cpython-313.pyc
│   │           id_guard.cpython-313.pyc
│   │           id_kinds.cpython-313.pyc
│   │           id_validator.cpython-313.pyc
│   │           module_disabled.cpython-313.pyc
│   │           module_guard.cpython-313.pyc
│   │           module_switch.cpython-313.pyc
│   │           monitoring.cpython-313.pyc
│   │           rate_limiting.cpython-313.pyc
│   │           security.cpython-313.pyc
│   │           template_helpers.cpython-313.pyc
│   │           transactions.cpython-313.pyc
│   │           validators.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───wallet
│   │   │   AFCON360_WALLET_AUDIT_ARCHIVE.md
│   │   │   AFCON360_WALLET_AUDIT_REPORT.md
│   │   │   AFCON360_WALLET_PRODUCTION_GUIDE.md
│   │   │   decorators.py
│   │   │   ESCROW.md
│   │   │   ESCROW_ARCHITECTURE.md
│   │   │   exceptions.py
│   │   │   implement.md
│   │   │   IMPLEMENTATION_REPORT.md
│   │   │   PAYMENT_ARCHITECTURE.md
│   │   │   routes.py
│   │   │   routes_pin.py
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
│   │   │   └───__pycache__
│   │   │           admin_api.cpython-313.pyc
│   │   │           fx_api.cpython-313.pyc
│   │   │           wallet_api.cpython-313.pyc
│   │   │           webhooks.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───middleware
│   │   │   │   idempotency.py
│   │   │   │   kill_switch.py
│   │   │   │   wallet_activation.py
│   │   │   │   wallet_check.py
│   │   │   │   wallet_check.py (new file)
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           idempotency.cpython-313.pyc
│   │   │           kill_switch.cpython-313.pyc
│   │   │           wallet_check.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───models
│   │   │   │   adjustment.py
│   │   │   │   admin_audit.py
│   │   │   │   aggregator.py
│   │   │   │   audit.py
│   │   │   │   commission.py
│   │   │   │   config.py
│   │   │   │   fraud_detection.py
│   │   │   │   fx.py
│   │   │   │   ledger.py
│   │   │   │   nonce_protection.py
│   │   │   │   payment_method.py
│   │   │   │   payout.py
│   │   │   │   reconciliation.py
│   │   │   │   transaction.py
│   │   │   │   transaction.py.before-fix
│   │   │   │   travel_rule.py
│   │   │   │   webhook_event.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           adjustment.cpython-313.pyc
│   │   │           admin_audit.cpython-313.pyc
│   │   │           aggregator.cpython-313.pyc
│   │   │           audit.cpython-313.pyc
│   │   │           commission.cpython-313.pyc
│   │   │           config.cpython-313.pyc
│   │   │           fraud_detection.cpython-313.pyc
│   │   │           fx.cpython-313.pyc
│   │   │           ledger.cpython-313.pyc
│   │   │           nonce_protection.cpython-313.pyc
│   │   │           payment_method.cpython-313.pyc
│   │   │           payout.cpython-313.pyc
│   │   │           reconciliation.cpython-313.pyc
│   │   │           transaction.cpython-313.pyc
│   │   │           travel_rule.cpython-313.pyc
│   │   │           webhook_event.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───payments
│   │   │       alipay.py
│   │   │       flutterwave.py
│   │   │       mobile_money.py
│   │   │       paypal.py
│   │   │       paystack.py
│   │   │       visa.py
│   │   │       wechat.py
│   │   │       __init__.py
│   │   │       
│   │   ├───repositories
│   │   │   │   account_repository.py
│   │   │   │   commission_repository.py
│   │   │   │   ledger_repository.py
│   │   │   │   payout_repository.py
│   │   │   │   transaction_repository.py
│   │   │   │   wallet_repository.py
│   │   │   │   webhook_repository.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           account_repository.cpython-313.pyc
│   │   │           commission_repository.cpython-313.pyc
│   │   │           ledger_repository.cpython-313.pyc
│   │   │           payout_repository.cpython-313.pyc
│   │   │           transaction_repository.cpython-313.pyc
│   │   │           wallet_repository.cpython-313.pyc
│   │   │           webhook_repository.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───routes
│   │   │       regulator_api.py
│   │   │       
│   │   ├───services
│   │   │   │   admin_audit_service.py
│   │   │   │   aggregator_service.py
│   │   │   │   commission_service.py
│   │   │   │   compliance_engine.py
│   │   │   │   currency_service.py
│   │   │   │   fraud_detection_service.py
│   │   │   │   fx_service.py
│   │   │   │   nonce_protection_service.py
│   │   │   │   payment_gateway.py
│   │   │   │   payout_service.py
│   │   │   │   reconciliation_service.py
│   │   │   │   regulatory_reporting.py
│   │   │   │   regulator_service.py
│   │   │   │   travel_rule_service.py
│   │   │   │   wallet_notifications.py
│   │   │   │   wallet_service.py
│   │   │   │   wallet_status_service.py
│   │   │   │   webhook_service.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           admin_audit_service.cpython-313.pyc
│   │   │           aggregator_service.cpython-313.pyc
│   │   │           commission_service.cpython-313.pyc
│   │   │           compliance_engine.cpython-313.pyc
│   │   │           currency_service.cpython-313.pyc
│   │   │           fraud_detection_service.cpython-313.pyc
│   │   │           fx_service.cpython-313.pyc
│   │   │           nonce_protection_service.cpython-313.pyc
│   │   │           payment_gateway.cpython-313.pyc
│   │   │           payout_service.cpython-313.pyc
│   │   │           reconciliation_service.cpython-313.pyc
│   │   │           regulatory_reporting.cpython-313.pyc
│   │   │           regulator_service.cpython-313.pyc
│   │   │           travel_rule_service.cpython-313.pyc
│   │   │           wallet_notifications.cpython-313.pyc
│   │   │           wallet_service.cpython-313.pyc
│   │   │           wallet_status_service.cpython-313.pyc
│   │   │           webhook_service.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   └───__pycache__
│   │           exceptions.cpython-313.pyc
│   │           routes.cpython-313.pyc
│   │           routes_pin.cpython-313.pyc
│   │           validators.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   └───__pycache__
│           celery_app.cpython-313.pyc
│           config.cpython-313.pyc
│           extensions.cpython-313.pyc
│           placeholder.cpython-313.pyc
│           __init__.cpython-313.pyc
│           
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
├───docker
│   └───nginx
│           afcon360.conf
│           nginx.conf
│           
├───docs
│   │   enterprise_readiness_assessment.md
│   │   payment_system_documentation.md
│   │   
│   └───saved_work
│           create_tables.sh
│           docker-compose.yml
│           inspect_db.sh
│           lazy_table_creator.py
│           table_inspector.py
│           table_monitor.py
│           
├───flask_session
├───Implement
│       ESCROW_IMPLEMENTATION_BRIEF.md
│       kilo_implemettion.md
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
│   │   │   0260706_add_system_configs_table.py
│   │   │   048ce13b1bfe_add_group_label_to_event_registrations.py
│   │   │   04d05161190f_add_booking_commission.py
│   │   │   07c931b46c36_add_server_default_to_processing_.py
│   │   │   0df1a94b3534_add_multi_guest_booking_fields_for_.py
│   │   │   0e5655df8acd_add_accommodation_architecture_.py
│   │   │   100e8db8a57f_enforce_inventory_block_reason_enum_at_.py
│   │   │   15a1f8d5f2bb_after_fixing_mgration_errors_clean_up.py
│   │   │   18288f7196e0_add_accommodation_query_performance_.py
│   │   │   1d30290f4f67_add_room_types_and_inventory_blocks_.py
│   │   │   20260627_add_media_tables.py
│   │   │   20260629_add_media_enhancements.py
│   │   │   20260701_add_room_types_and_inventory_blocks.py
│   │   │   20260701_add_room_type_id_to_bookings.py
│   │   │   20260718_1951_make_organisations_compliance_case_id_.py
│   │   │   20260724_1040_add_status_check_constraint.py
│   │   │   2459945a58a4_add_fan_profiles_and_dashboard_contexts.py
│   │   │   273c374bade0_add_missing_columns_to_system_configs.py
│   │   │   2a0f0f631427_add_wishlist_table.py
│   │   │   2d264b2fdc99_add_host_profiles_property_documents_.py
│   │   │   2fa5d406a740_make_accommodation_datetimes_timezone_.py
│   │   │   31eef7f1f4a2_add_accommodation_booking_payments.py
│   │   │   330ce9bd4864_add_notifications_and_property_.py
│   │   │   5582ce532c6f_add_agents_enabled_to_wallet_config.py
│   │   │   5661738e7748_add_archived_columns_to_property.py
│   │   │   5796d94e890f_add_approved_to_property_status_check_.py
│   │   │   586b35d32d53_add_property_public_id.py
│   │   │   69095234e1b0_add_booked_by_snapshot_fields_to_.py
│   │   │   6e9dbae2ac1a_replace_roomcategory_with_roomtype_in_.py
│   │   │   721f6a09485d_merge_media_migration.py
│   │   │   76c9e829b84b_add_rate_limit_settings_table.py
│   │   │   8120b21c333e_add_booking_approval_and_property_.py
│   │   │   87f479367218_add_organizer_messages_table.py
│   │   │   88d91ff49abe_add_platform_account_fields.py
│   │   │   978aa0c43706_add_published_status_to_property_.py
│   │   │   a8dda837031d_add_aggregator_sandbox_live_mode_and_.py
│   │   │   a976e4599bfe_merge_final_heads.py
│   │   │   ab6dd422c152_initial_schema.py
│   │   │   b5b8d696abbf_create_aggregators_table.py
│   │   │   ba262522c43c_convert_accommodation_enums_to_strings.py
│   │   │   c845c6583732_sync_property_status_check_constraint_.py
│   │   │   d95160fba1fd_merge_20260717_rooms.py
│   │   │   db911bfe67b9_merge_system_configs_and_other_branch.py
│   │   │   ec4fff3b4299_add_media_module_tables.py
│   │   │   ed6307401623_make_wallet_admin_events_datetimes_.py
│   │   │   
│   │   └───__pycache__
│   │           0260706_add_system_configs_table.cpython-313.pyc
│   │           048ce13b1bfe_add_group_label_to_event_registrations.cpython-313.pyc
│   │           04d05161190f_add_booking_commission.cpython-313.pyc
│   │           07c931b46c36_add_server_default_to_processing_.cpython-313.pyc
│   │           0df1a94b3534_add_multi_guest_booking_fields_for_.cpython-313.pyc
│   │           0e5655df8acd_add_accommodation_architecture_.cpython-313.pyc
│   │           100e8db8a57f_enforce_inventory_block_reason_enum_at_.cpython-313.pyc
│   │           15a1f8d5f2bb_after_fixing_mgration_errors_clean_up.cpython-313.pyc
│   │           18288f7196e0_add_accommodation_query_performance_.cpython-313.pyc
│   │           1d30290f4f67_add_room_types_and_inventory_blocks_.cpython-313.pyc
│   │           20260627_add_media_tables.cpython-313.pyc
│   │           20260629_add_media_enhancements.cpython-313.pyc
│   │           20260701_add_room_types_and_inventory_blocks.cpython-313.pyc
│   │           20260701_add_room_type_id_to_bookings.cpython-313.pyc
│   │           20260718_1951_make_organisations_compliance_case_id_.cpython-313.pyc
│   │           20260724_1040_add_status_check_constraint.cpython-313.pyc
│   │           2459945a58a4_add_fan_profiles_and_dashboard_contexts.cpython-313.pyc
│   │           273c374bade0_add_missing_columns_to_system_configs.cpython-313.pyc
│   │           2a0f0f631427_add_wishlist_table.cpython-313.pyc
│   │           2d264b2fdc99_add_host_profiles_property_documents_.cpython-313.pyc
│   │           2fa5d406a740_make_accommodation_datetimes_timezone_.cpython-313.pyc
│   │           31eef7f1f4a2_add_accommodation_booking_payments.cpython-313.pyc
│   │           330ce9bd4864_add_notifications_and_property_.cpython-313.pyc
│   │           39725f6deaac_add_accommodation_architecture_.cpython-313.pyc
│   │           5582ce532c6f_add_agents_enabled_to_wallet_config.cpython-313.pyc
│   │           5661738e7748_add_archived_columns_to_property.cpython-313.pyc
│   │           5796d94e890f_add_approved_to_property_status_check_.cpython-313.pyc
│   │           586b35d32d53_add_property_public_id.cpython-313.pyc
│   │           69095234e1b0_add_booked_by_snapshot_fields_to_.cpython-313.pyc
│   │           6e9dbae2ac1a_replace_roomcategory_with_roomtype_in_.cpython-313.pyc
│   │           721f6a09485d_merge_media_migration.cpython-313.pyc
│   │           76c9e829b84b_add_rate_limit_settings_table.cpython-313.pyc
│   │           8120b21c333e_add_booking_approval_and_property_.cpython-313.pyc
│   │           81f8d3d2af77_add_accommodation_architecture_.cpython-313.pyc
│   │           87f479367218_add_organizer_messages_table.cpython-313.pyc
│   │           88d91ff49abe_add_platform_account_fields.cpython-313.pyc
│   │           90dbd473780b_add_accommodation_architecture_.cpython-313.pyc
│   │           978aa0c43706_add_published_status_to_property_.cpython-313.pyc
│   │           a8dda837031d_add_aggregator_sandbox_live_mode_and_.cpython-313.pyc
│   │           a976e4599bfe_merge_final_heads.cpython-313.pyc
│   │           ab6dd422c152_initial_schema.cpython-313.pyc
│   │           b5b8d696abbf_create_aggregators_table.cpython-313.pyc
│   │           b86f15c73f11_replace_roomcategory_with_roomtype_in_.cpython-313.pyc
│   │           ba262522c43c_convert_accommodation_enums_to_strings.cpython-313.pyc
│   │           c845c6583732_sync_property_status_check_constraint_.cpython-313.pyc
│   │           d95160fba1fd_merge_20260717_rooms.cpython-313.pyc
│   │           db911bfe67b9_merge_system_configs_and_other_branch.cpython-313.pyc
│   │           ec4fff3b4299_add_media_module_tables.cpython-313.pyc
│   │           ed6307401623_make_wallet_admin_events_datetimes_.cpython-313.pyc
│   │           fa47a4cddc7d_add_media_processing_tracking_fields.cpython-313.pyc
│   │           
│   └───__pycache__
│           env.cpython-313.pyc
│           
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
│       ask-debug-mode-rules.md
│       code-mode-rules.md
│       global-rules.md
│       
├───scripts
│   │   backfill_room_types.py
│   │   check_id_usage.py
│   │   complete_fix.py
│   │   create_migration.py
│   │   create_system_configs.py
│   │   db_audit.py
│   │   dumpedfiles.py
│   │   fix_remaining.py
│   │   generate_missing_migrations.py
│   │   init_settings.py
│   │   inspect_database_ids.py
│   │   inspect_identity_map.py
│   │   inspect_id_fields.py
│   │   inspect_id_usage.py
│   │   lazy_table_creator.py
│   │   migrate_enums_to_strings.py
│   │   migrate_fan_profiles.py
│   │   migration_agent_config.py
│   │   reset_test_db.py
│   │   restore_git.py
│   │   run_backfill.py
│   │   scan_null_bytes.py
│   │   script.js
│   │   seed_payment_methods.py
│   │   seed_roles.py
│   │   seed_system_configs.py
│   │   seed_test_marketplace_accounts.py
│   │   setup_platform_escrow.py
│   │   setup_test_db.py
│   │   setup_test_db_schema.py
│   │   table_inspector.py
│   │   table_monitor.py
│   │   test_flow.py
│   │   verify_bookings.py
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
│   ├───security
│   │       identity_audit.py
│   │       
│   └───__pycache__
│           migration_agent_config.cpython-313.pyc
│           seed_payment_methods.cpython-313.pyc
│           seed_test_marketplace_accounts.cpython-313.pyc
│           setup_platform_escrow.cpython-313.pyc
│           
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
│   │   ├───generated
│   │   │       global-theme.css
│   │   │       user-1.css
│   │   │       
│   │   ├───global
│   │   │       home.css
│   │   │       mobile-utilities.css
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
│   │       │       host-dashboard.css
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
│   │       ├───media
│   │       │       media.css
│   │       │       
│   │       ├───transport
│   │       │       base.css
│   │       │       bookings.css
│   │       │       dashboard.css
│   │       │       drivers.css
│   │       │       vehicles.css
│   │       │       
│   │       ├───user
│   │       │       dashboard.css
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
│   └───js
│       │   theme-manager.js
│       │   
│       ├───fan
│       │       dashboard.js
│       │       
│       ├───global
│       │       main.js
│       │       media-manager.js
│       │       script.js
│       │       theme-manager.js
│       │       
│       └───modules
│           ├───accommodation
│           │       checkout.js
│           │       detail.js
│           │       explore.js
│           │       host-dashboard-enhanced.js
│           │       host-dashboard.js
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
│   │   │   abacus-property-group-static-site.zip
│   │   │   Accomodation_module.md
│   │   │   booking.md
│   │   │   explore.html
│   │   │   home.html
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
│   │   │       checkout.html
│   │   │       confirmation.html
│   │   │       detail.html
│   │   │       my_bookings.html
│   │   │       review_form.html
│   │   │       search.html
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
│   │       │   register.html
│   │       │   rooms.html
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
│   │       
│   ├───compliance
│   │       dashboard.html
│   │       
│   ├───components
│   │       audit_timeline.html
│   │       kyc_badge.html
│   │       kyc_tier_badge.html
│   │       media_gallery.html
│   │       media_upload.html
│   │       mfa_status.html
│   │       pending_reviews_widget.html
│   │       status_badge.html
│   │       suspicious_activity_widget.html
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
│   │   │   │   assignment_dashboard.html
│   │   │   │   attendees_list.html
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
│   │   │       registerO.html
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
│   │   │       messages.html
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
│   ├───macros
│   │       admin_macros.html
│   │       booking_macros.html
│   │       flash_messages.html
│   │       form_macros.html
│   │       ui_macros.html
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
│   │       host_step2.html
│   │       organisation_step1.html
│   │       organisation_step2.html
│   │       standard.html
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
│  
