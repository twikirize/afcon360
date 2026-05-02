───app
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
│   │   │   listeners.py
│   │   │   routes.py
│   │   │   services.py
│   │   │   __init__.py
│   │   │   
│   │   ├───models
│   │   │   │   availability.py
│   │   │   │   booking.py
│   │   │   │   property.py
│   │   │   │   review.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           availability.cpython-313.pyc
│   │   │           booking.cpython-313.pyc
│   │   │           property.cpython-313.pyc
│   │   │           review.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───routes
│   │   │   │   admin_routes.py
│   │   │   │   guest_routes.py
│   │   │   │   host_routes.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           admin_routes.cpython-313.pyc
│   │   │           guest_routes.cpython-313.pyc
│   │   │           host_routes.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───services
│   │   │   │   abuse_prevention_service.py
│   │   │   │   availability_service.py
│   │   │   │   booking_service.py
│   │   │   │   identity_service.py
│   │   │   │   pricing_service.py
│   │   │   │   search_service.py
│   │   │   │   wallet_service.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           abuse_prevention_service.cpython-313.pyc
│   │   │           availability_service.cpython-313.pyc
│   │   │           booking_service.cpython-313.pyc
│   │   │           identity_service.cpython-313.pyc
│   │   │           pricing_service.cpython-313.pyc
│   │   │           search_service.cpython-313.pyc
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
│   │           __init__.cpython-313.pyc
│   │           
│   ├───admin
│   │   │   hooks.py
│   │   │   models.py
│   │   │   routes.py
│   │   │   routes_extended.py
│   │   │   routes_ultimate.py
│   │   │   services.py
│   │   │   __init__.py
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
│   │   ├───moderator
│   │   │   │   pipeline.py
│   │   │   │   registry.py
│   │   │   │   routes.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           pipeline.cpython-313.pyc
│   │   │           registry.cpython-313.pyc
│   │   │           routes.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
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
│   │   │   └───__pycache__
│   │   │           audit.cpython-313.pyc
│   │   │           decorators.cpython-313.pyc
│   │   │           models.cpython-313.pyc
│   │   │           routes.cpython-313.pyc
│   │   │           security_routes.cpython-313.pyc
│   │   │           security_service.cpython-313.pyc
│   │   │           utils.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
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
│   │           models.cpython-313.pyc
│   │           routes.cpython-313.pyc
│   │           services.cpython-313.pyc
│   │           __init__.cpython-313.pyc
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
│   │   │   decorators.py
│   │   │   email.py
│   │   │   helpers.py
│   │   │   kyc_compliance.py
│   │   │   kyc_routes.py
│   │   │   otp_service.py
│   │   │   ownership.py
│   │   │   policy.py
│   │   │   roles.py
│   │   │   routes.py
│   │   │   seed_roles.py
│   │   │   services.py
│   │   │   sessions.py
│   │   │   test_helpers.py
│   │   │   tokens.py
│   │   │   validators.py
│   │   │   __init__.py
│   │   │   
│   │   ├───services
│   │   │       org.py
│   │   │       
│   │   └───__pycache__
│   │           decorators.cpython-313.pyc
│   │           helpers.cpython-313.pyc
│   │           kyc_compliance.cpython-313.pyc
│   │           kyc_routes.cpython-313.pyc
│   │           otp_service.cpython-313.pyc
│   │           policy.cpython-313.pyc
│   │           roles.cpython-313.pyc
│   │           routes.cpython-313.pyc
│   │           seed_roles.cpython-313.pyc
│   │           services.cpython-313.pyc
│   │           sessions.cpython-313.pyc
│   │           tokens.cpython-313.pyc
│   │           validators.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───cli
│   │   │   owner.py
│   │   │   __init__.py
│   │   │   
│   │   └───__pycache__
│   │           owner.cpython-313.pyc
│   │           __init__.cpython-313.pyc
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
│   │       CLI Commands Reference.md
│   │       CSP_POLICY.md
│   │       ID_SYSTEM_RULES.md
│   │       SESSION_EXPORT_CSP_MIGRATION_2026-04-27.md
│   │       SYSTEM_OVERVIEW.md
│   │       
│   ├───events
│   │   │   constants.py
│   │   │   events.md
│   │   │   Events_CONTEXT.md
│   │   │   metrics_service.py
│   │   │   models.py
│   │   │   permissions.py
│   │   │   phase1.md
│   │   │   README.md
│   │   │   routes.py
│   │   │   services.py
│   │   │   settings_model.py
│   │   │   settings_routes.py
│   │   │   signals.py
│   │   │   signal_handlers.py
│   │   │   start.md
│   │   │   tasks.py
│   │   │   __init__.py
│   │   │   
│   │   └───__pycache__
│   │           constants.cpython-313.pyc
│   │           models.cpython-313.pyc
│   │           permissions.cpython-313.pyc
│   │           routes.cpython-313.pyc
│   │           services.cpython-313.pyc
│   │           settings_model.cpython-313.pyc
│   │           settings_routes.cpython-313.pyc
│   │           signals.cpython-313.pyc
│   │           signal_handlers.cpython-313.pyc
│   │           tasks.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───fan
│   │   │   models.py
│   │   │   routes.py
│   │   │   __init__.py
│   │   │   
│   │   ├───services
│   │   │       registry.py
│   │   │       
│   │   └───__pycache__
│   │           routes.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───forms
│   │       booking_forms.py
│   │       driver_forms.py
│   │       incident_forms.py
│   │       organisation_forms.py
│   │       settings_forms.py
│   │       vehicle_forms.py
│   │       __init__.py
│   │       
│   ├───identity
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
│   │   │           roles_permission.cpython-313.pyc
│   │   │           user.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───utils
│   │   │   └───__pycache__
│   │   │           compliance_checker.cpython-313.pyc
│   │   │           compliance_utils.cpython-313.pyc
│   │   │           
│   │   └───__pycache__
│   │           services.cpython-313.pyc
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
│   ├───models
│   │   │   audit.py
│   │   │   base.py
│   │   │   theme.py
│   │   │   __init__.py
│   │   │   
│   │   └───__pycache__
│   │           base.cpython-313.pyc
│   │           theme.cpython-313.pyc
│   │           __init__.cpython-313.pyc
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
│   │       sms_service.py
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
│   │   │   │   route_routes.py
│   │   │   │   settings_routes.py
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
│   ├───utils
│   │   │   audit.py
│   │   │   caching.py
│   │   │   exceptions.py
│   │   │   idempotency.py
│   │   │   id_guard.py
│   │   │   id_helpers.py
│   │   │   id_validator.py
│   │   │   module_switch.py
│   │   │   monitoring.py
│   │   │   rate_limiting.py
│   │   │   redis_lock.py
│   │   │   security.py
│   │   │   transactions.py
│   │   │   validators.py
│   │   │   __init__.py
│   │   │   
│   │   └───__pycache__
│   │           audit.cpython-313.pyc
│   │           caching.cpython-313.pyc
│   │           exceptions.cpython-313.pyc
│   │           idempotency.cpython-313.pyc
│   │           id_guard.cpython-313.pyc
│   │           module_switch.cpython-313.pyc
│   │           monitoring.cpython-313.pyc
│   │           rate_limiting.cpython-313.pyc
│   │           security.cpython-313.pyc
│   │           transactions.cpython-313.pyc
│   │           validators.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   ├───wallet
│   │   │   exceptions.py
│   │   │   validators.py
│   │   │   __init__.py
│   │   │   
│   │   ├───api
│   │   │   │   admin_api.py
│   │   │   │   fx_api.py
│   │   │   │   wallet_api.py
│   │   │   │   webhooks.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           admin_api.cpython-313.pyc
│   │   │           audit_api.cpython-313.pyc
│   │   │           fx_api.cpython-313.pyc
│   │   │           wallet_api.cpython-313.pyc
│   │   │           webhooks.cpython-313.pyc
│   │   │           webhook_api.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───middleware
│   │   │   │   idempotency.py
│   │   │   │   kill_switch.py
│   │   │   │   wallet_activation.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           idempotency.cpython-313.pyc
│   │   │           kill_switch.cpython-313.pyc
│   │   │           wallet_activation.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───models
│   │   │   │   audit.py
│   │   │   │   config.py
│   │   │   │   fx.py
│   │   │   │   ledger.py
│   │   │   │   transaction.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           audit.cpython-313.pyc
│   │   │           fx.cpython-313.pyc
│   │   │           ledger.cpython-313.pyc
│   │   │           transaction.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───payments
│   │   │       flutterwave.py
│   │   │       paystack.py
│   │   │       __init__.py
│   │   │       
│   │   ├───repositories
│   │   │   │   account_repository.py
│   │   │   │   ledger_repository.py
│   │   │   │   transaction_repository.py
│   │   │   │   wallet_repository.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           account_repository.cpython-313.pyc
│   │   │           ledger_repository.cpython-313.pyc
│   │   │           transaction_repository.cpython-313.pyc
│   │   │           wallet_repository.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   ├───services
│   │   │   │   compliance_engine.py
│   │   │   │   currency_service.py
│   │   │   │   fx_service.py
│   │   │   │   payment_gateway.py
│   │   │   │   regulatory_reporting.py
│   │   │   │   wallet_service.py
│   │   │   │   __init__.py
│   │   │   │   
│   │   │   └───__pycache__
│   │   │           audit.cpython-313.pyc
│   │   │           audit_query_service.cpython-313.pyc
│   │   │           commission_service.cpython-313.pyc
│   │   │           compliance_engine.cpython-313.pyc
│   │   │           currency_service.cpython-313.pyc
│   │   │           fx_service.cpython-313.pyc
│   │   │           payment_gateway.cpython-313.pyc
│   │   │           payout_service.cpython-313.pyc
│   │   │           regulatory_reporting.cpython-313.pyc
│   │   │           wallet_admin_service.cpython-313.pyc
│   │   │           wallet_service.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │           
│   │   └───__pycache__
│   │           exceptions.cpython-313.pyc
│   │           legacy_models.cpython-313.pyc
│   │           models.cpython-313.pyc
│   │           routes.cpython-313.pyc
│   │           validators.cpython-313.pyc
│   │           __init__.cpython-313.pyc
│   │           
│   └───__pycache__
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
├───flask_session
│       2029240f6d1128be89ddc32729463129
│       
├───instance
│       afcon360.db
│       dev.db
│       test.db
│       
├───Let me produce the SEARCH
│   └───REPLACE blocks now.static
│       └───js
│           └───modules
│               └───admin
│                       moderator_dashboard.js
│                       
├───Let's produce the block.app
│   └───wallet
│       └───services
│               compliance_engine.py
│               
├───Let's produce the SEARCH
│   └───REPLACE block.app
│       └───admin
│           └───moderator
│                   routes.py
│                   
├───migrations
│   │   alembic.ini
│   │   env.py
│   │   envy.html
│   │   README
│   │   script.py.mako
│   │   test_events.py
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
│   ├───versions
│   │   │   0f73dc769909_upgrade_wallet.py
│   │   │   0f73dc769909_upgrade_wallet.py.bak
│   │   │   1e93a437d0e6_add_moderation_notes_to_entity_tables.py
│   │   │   20260430_182327_ledger_rebuild.py
│   │   │   23ecc92eb3fd_add_event_model_indexes_and_constraints.py
│   │   │   489d61e4ca9b_add_event_assignments_table.py
│   │   │   5649512f749d_fix_moderation_log_relationships.py
│   │   │   56cf92e4fdef_add_compliance_models_and_integration_.py
│   │   │   654c1bf0ccea_add_event_settings_table.py
│   │   │   67a805678c79_initial_clean_migration_with_all_models.py
│   │   │   6c994e0e5f9d_add_kyc_verification_fields_to_.py
│   │   │   7053dc695af1_add_event_moderation_fields.py
│   │   │   75602feb99cc_fix_csrf_and_cleanup.py
│   │   │   80c9b2f7cb42_phase_6_event_ownership_transfers_.py
│   │   │   8e254b19689d_feat_add_event_approval_workflow_with_.py
│   │   │   add_fx_tables.py
│   │   │   add_moderation_notes_to_organisations.py
│   │   │   b512872ef96a_add_email_verified_phone_verified_and_.py
│   │   │   ba9cdabc4951_add_content_flags_table.py
│   │   │   c76f972a4ed1_sync_schema_remove_fan_profiles_and_add_.py
│   │   │   d8f7481b2ac0_fix_event_status_legacy_values.py
│   │   │   d9a2a9f82ed4_add_event_type_column_to_events_table.py
│   │   │   dce3342ee153_your_change_description.py
│   │   │   ee770bb1ee78_add_event_submission_preferences_and_.py
│   │   │   fix_compliance_bigint_types.py
│   │   │   
│   │   └───__pycache__
│   │           0f73dc769909_upgrade_wallet.cpython-313.pyc
│   │           1e93a437d0e6_add_moderation_notes_to_entity_tables.cpython-313.pyc
│   │           20260430_182327_ledger_rebuild.cpython-313.pyc
│   │           23ecc92eb3fd_add_event_model_indexes_and_constraints.cpython-313.pyc
│   │           489d61e4ca9b_add_event_assignments_table.cpython-313.pyc
│   │           5649512f749d_fix_moderation_log_relationships.cpython-313.pyc
│   │           56cf92e4fdef_add_compliance_models_and_integration_.cpython-313.pyc
│   │           654c1bf0ccea_add_event_settings_table.cpython-313.pyc
│   │           67a805678c79_initial_clean_migration_with_all_models.cpython-313.pyc
│   │           6c994e0e5f9d_add_kyc_verification_fields_to_.cpython-313.pyc
│   │           7053dc695af1_add_event_moderation_fields.cpython-313.pyc
│   │           75602feb99cc_fix_csrf_and_cleanup.cpython-313.pyc
│   │           80c9b2f7cb42_phase_6_event_ownership_transfers_.cpython-313.pyc
│   │           83d364eaafed_add_fx_rate_and_transaction_tables_for_.cpython-313.pyc
│   │           8e254b19689d_feat_add_event_approval_workflow_with_.cpython-313.pyc
│   │           add_fx_tables.cpython-313.pyc
│   │           add_moderation_notes_to_organisations.cpython-313.pyc
│   │           b512872ef96a_add_email_verified_phone_verified_and_.cpython-313.pyc
│   │           ba9cdabc4951_add_content_flags_table.cpython-313.pyc
│   │           c76f972a4ed1_sync_schema_remove_fan_profiles_and_add_.cpython-313.pyc
│   │           d8f7481b2ac0_fix_event_status_legacy_values.cpython-313.pyc
│   │           d9a2a9f82ed4_add_event_type_column_to_events_table.cpython-313.pyc
│   │           dce3342ee153_your_change_description.cpython-313.pyc
│   │           ee770bb1ee78_add_event_submission_preferences_and_.cpython-313.pyc
│   │           fix_compliance_bigint_types.cpython-313.pyc
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
│       
├───pushups
│       auth.py
│       routes.py
│       __init__.py
│       
├───Readme's
│       2026-04-11_events_concurrency_fixes.md
│       admin-system-analysis.md
│       DASHBOARD_FIXES_COMPLETE.md
│       endpoints.md
│       ENDPOINT_FIXES_SUMMARY.md
│       ERROR_FIXES_SUMMARY.md
│       IMPERSONATION_SYSTEM_STATUS.md
│       Moderation.md
│       OWNER_SYSTEM_COMPLETE.md
│       PRODUCTION_README.md
│       registration_report2_15-04
│       reistration & user mgt.md
│       reistration_report_15_04.md
│       ULTIMATE_ADMIN_SYSTEM.md
│       
├───scripts
│   │   check_id_usage.py
│   │   db_audit.py
│   │   dumpedfiles.py
│   │   generate_missing_migrations.py
│   │   init_settings.py
│   │   script.js
│   │   seed_roles.py
│   │   test_flow.py
│   │   
│   └───.pytest_cache
│       │   .gitignore
│       │   CACHEDIR.TAG
│       │   README.md
│       │   
│       └───v
│           └───cache
│                   lastfailed
│                   nodeids
│                   stepwise
│                   
├───static
│   │   deposit.css
│   │   home.css
│   │   script.js
│   │   style.css
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
│   │       │       
│   │       └───wallet
│   │               deposit.css
│   │               
│   ├───js
│   │   │   theme-manager.js
│   │   │   
│   │   ├───fan
│   │   │       dashboard.js
│   │   │       
│   │   ├───global
│   │   │       main.js
│   │   │       
│   │   └───modules
│   │       ├───admin
│   │       │       admin_moderation.js
│   │       │       moderator_dashboard.js
│   │       │       
│   │       ├───events
│   │       └───transport
│   │               base.js
│   │               booking.js
│   │               dashboard.js
│   │               drivers.js
│   │               realtime.js
│   │               utils.js
│   │               vehicle.js
│   │               
│   └───transport
│       ├───css
│       │       base.css
│       │       bookings.css
│       │       dashboard.css
│       │       drivers.css
│       │       vehicles.css
│       │       
│       ├───images
│       │   ├───driver_avatars
│       │   └───vehicle_icons
│       └───js
│               booking.js
│               charts.js
│               dashboard.js
│               drivers.js
│               mapp.js
│               realtime.js
│               utils.js
│               vehicle.js
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
│   │   public_home.html
│   │   receiver_wallet.html
│   │   register.html
│   │   reset_confirm.html
│   │   reset_password.html
│   │   reset_request.html
│   │   super_admindashboard.html
│   │   test.html
│   │   tourism_detail.html
│   │   tourism_home.html
│   │   tournament_archive.html
│   │   tournament_home.html
│   │   transport_detail.html
│   │   transport_home.html
│   │   verify.html
│   │   view.html
│   │   wallet_activate.html
│   │   wallet_dashboard.html
│   │   wallet_home.html
│   │   wallet_terms.html
│   │   wallet_transactions.html
│   │   
│   ├───accommodation
│   │   │   Accomodation_module.md
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
│   ├───admin
│   │   │   admin.html
│   │   │   auditor_dashboard.html
│   │   │   content_dashboard.html
│   │   │   dashboard.html
│   │   │   global_theme.html
│   │   │   kyc_documents.html
│   │   │   manage_orgs.html
│   │   │   manage_roles.html
│   │   │   manage_submissions.html
│   │   │   manage_users.html
│   │   │   moderator_dashboard.html
│   │   │   org_audit.html
│   │   │   org_members.html
│   │   │   role_users.html
│   │   │   settings.html
│   │   │   super_dashboard.html
│   │   │   support_dashboard.html
│   │   │   update_profile.html
│   │   │   update_user.html
│   │   │   user_activity.html
│   │   │   view_user.html
│   │   │   view_user_ultimate.html
│   │   │   wallets.html
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
│   │   │       audit_log.html
│   │   │       base_moderator.html
│   │   │       categories.html
│   │   │       content.html
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
│   │   │       stats.html
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
│   │   └───owner
│   │           kyc_tiers.html
│   │           security_dashboard.html
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
│   │       pending_reviews_widget.html
│   │       status_badge.html
│   │       suspicious_activity_widget.html
│   │       
│   ├───email
│   │       verification.html
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
│   │   ├───organizer
│   │   │       analytics.html
│   │   │       attendees.html
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
│   │       verify_national_id.html
│   │       
│   ├───org
│   │       content_dashboard.html
│   │       dashboard.html
│   │       
│   ├───owner
│   │   │   audit_logs.html
│   │   │   backup_codes.html
│   │   │   danger_zone.html
│   │   │   dashboard.html
│   │   │   impersonate.html
│   │   │   later.html
│   │   │   manage_roles.html
│   │   │   settings.html
│   │   │   super_admins.html
│   │   │   system_health.html
│   │   │   users.html
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
│   │       content_dashboard.html
│   │       preferences.html
│   │       
│   └───wallet
│           deposit.html
│           dump.html
│           original_file.html
│           overview.html
│           send.html
│           transactions.html
│           withdraw.html
│           
├───templates_backup_20260429_001434
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
│   │   public_home.html
│   │   receiver_wallet.html
│   │   register.html
│   │   reset_confirm.html
│   │   reset_password.html
│   │   reset_request.html
│   │   super_admindashboard.html
│   │   test.html
│   │   tourism_detail.html
│   │   tourism_home.html
│   │   tournament_archive.html
│   │   tournament_home.html
│   │   transport_detail.html
│   │   transport_home.html
│   │   verify.html
│   │   view.html
│   │   wallet_activate.html
│   │   wallet_dashboard.html
│   │   wallet_home.html
│   │   wallet_terms.html
│   │   wallet_transactions.html
│   │   
│   ├───accommodation
│   │   │   Accomodation_module.md
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
│   ├───admin
│   │   │   admin.html
│   │   │   auditor_dashboard.html
│   │   │   content_dashboard.html
│   │   │   dashboard.html
│   │   │   global_theme.html
│   │   │   kyc_documents.html
│   │   │   manage_orgs.html
│   │   │   manage_roles.html
│   │   │   manage_submissions.html
│   │   │   manage_users.html
│   │   │   moderator_dashboard.html
│   │   │   org_audit.html
│   │   │   org_members.html
│   │   │   settings.html
│   │   │   super_dashboard.html
│   │   │   support_dashboard.html
│   │   │   update_profile.html
│   │   │   update_user.html
│   │   │   user_activity.html
│   │   │   view_user.html
│   │   │   view_user_ultimate.html
│   │   │   wallets.html
│   │   │   wallet_control.html
│   │   │   wallet_detail.html
│   │   │   wallet_stats.html
│   │   │   
│   │   ├───compliance
│   │   │       dashboard.html
│   │   │       reports.html
│   │   │       search.html
│   │   │       user_audit_profile.html
│   │   │       
│   │   ├───moderation
│   │   ├───moderator
│   │   │       audit_log.html
│   │   │       content.html
│   │   │       dashboard.html
│   │   │       flagged.html
│   │   │       flags.html
│   │   │       users.html
│   │   │       view_submission.html
│   │   │       _pending_table.html
│   │   │       
│   │   └───owner
│   │           kyc_tiers.html
│   │           security_dashboard.html
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
│   │       pending_reviews_widget.html
│   │       status_badge.html
│   │       suspicious_activity_widget.html
│   │       
│   ├───email
│   │       verification.html
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
│   │   ├───organizer
│   │   │       analytics.html
│   │   │       attendees.html
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
│   │       limits.html
│   │       moderate.html
│   │       moderate_document.html
│   │       overview.html
│   │       upgrade.html
│   │       verify_national_id.html
│   │       
│   ├───org
│   │       content_dashboard.html
│   │       dashboard.html
│   │       
│   ├───owner
│   │       audit_logs.html
│   │       backup_codes.html
│   │       danger_zone.html
│   │       dashboard.html
│   │       dashboard.html.bak
│   │       impersonate.html
│   │       later.html
│   │       manage_roles.html
│   │       settings.html
│   │       super_admins.html
│   │       system_health.html
│   │       users.html
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
│   │       content_dashboard.html
│   │       preferences.html
│   │       
│   └───wallet
│           deposit.html
│           dump.html
│           original_file.html
│           overview.html
│           send.html
│           transactions.html
│           withdraw.html
│           
├───tests
│   │   db_connector.py
│   │   ERRORS_RESOLVED.md
│   │   fix_enum_issue.py
│   │   fix_events_schema.py
│   │   fix_geometry_issue.py
│   │   fix_migration_gist.py
│   │   fix_owner.py
│   │   full_db_audit.py
│   │   generate_migration.py
│   │   init_settings.py
│   │   inspect_db.py
│   │   list_endpoints.py
│   │   manage.py
│   │   phase_1.py
│   │   phase_2.py
│   │   project_structure.txt
│   │   read_llater.txt
│   │   run_event_tests.py
│   │   sample_users.py
│   │   scanner.py
│   │   seed_roles.py
│   │   seed_roles_simple.py
│   │   setup_owner.py
│   │   test roles.py
│   │   testing12.py
│   │   tests_alone.py
│   │   test_audit_system.py
│   │   test_auth_import.py
│   │   test_boot.py
│   │   test_concurrency.py
│   │   test_concurrency_simple.py
│   │   test_current.py
│   │   test_event.py
│   │   test_events.py
│   │   test_event_workflow.py
│   │   test_fan_kyc.py
│   │   test_forensic_audit.py
│   │   test_impersonation.py
│   │   test_impersonation_simple.py
│   │   test_imports.py
│   │   test_kyc_compliance.py
│   │   test_kyc_integration.py
│   │   test_load.py
│   │   test_loose_coupling.py
│   │   test_payment_flow.py
│   │   test_registration_flow.py
│   │   test_services.py
│   │   test_simple.py
│   │   transport_model.py
│   │   tree.md
│   │   update_models_no_geometry.py
│   │   user_roles_id.py
│   │   verify_concurrency.py
│   │   verify_fix.py
│   │   verify_obed.py
│   │   verify_transport_tables.py
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
│   └───wallet
│           conftest.py
│           test_ledger_concurrency.py
│           __init__.py
│           
├───We'll produce a SEARCH
│   └───REPLACE block with empty SEARCH (new file).templates
│       └───admin
│           └───moderator
│                   items.html
│                   
└───__pycache__
        config.cpython-313.pyc