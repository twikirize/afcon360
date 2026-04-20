├───app
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
│   │   │   │   routes.py
│   │   │   │   __init__.py
│   │   │   │
│   │   │   └───__pycache__
│   │   │           routes.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │
│   │   ├───moderator
│   │   │   │   routes.py
│   │   │   │   __init__.py
│   │   │   │
│   │   │   └───__pycache__
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
│   ├───Documentation
│   │       CLI Commands Reference.md
│   │       ID_SYSTEM_RULES.md
│   │
│   ├───events
│   │   │   events.md
│   │   │   metrics_service.py
│   │   │   models.py
│   │   │   permissions.py
│   │   │   routes.py
│   │   │   services.py
│   │   │   signals.py
│   │   │   signal_handlers.py
│   │   │   tasks.py
│   │   │   __init__.py
│   │   │
│   │   └───__pycache__
│   │           metrics_service.cpython-313.pyc
│   │           models.cpython-313.pyc
│   │           routes.cpython-313.pyc
│   │           services.cpython-313.pyc
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
│   │   │   │   registry.py
│   │   │   │
│   │   │   └───__pycache__
│   │   │           registry.cpython-313.pyc
│   │   │
│   │   └───__pycache__
│   │           models.cpython-313.pyc
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
│   │   │   │   compliance_checker.py
│   │   │   │   compliance_utils.py
│   │   │   │
│   │   │   └───__pycache__
│   │   │           compliance_checker.cpython-313.pyc
│   │   │           compliance_utils.cpython-313.pyc
│   │   │
│   │   └───__pycache__
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
│   ├───org
│   │   │   routes.py
│   │   │
│   │   └───__pycache__
│   │           routes.cpython-313.pyc
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
│   │   │   models.py
│   │   │   routes.py
│   │   │   services_with_audit.py
│   │   │   validators.py
│   │   │   wallet_structure.md
│   │   │   __init__.py
│   │   │
│   │   ├───api
│   │   │   │   admin_api.py
│   │   │   │   audit_api.py
│   │   │   │   wallet_api.py
│   │   │   │   webhook_api.py
│   │   │   │   __init__.py
│   │   │   │
│   │   │   └───__pycache__
│   │   │           admin_api.cpython-313.pyc
│   │   │           audit_api.cpython-313.pyc
│   │   │           wallet_api.cpython-313.pyc
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
│   │   ├───payments
│   │   │       flutterwave.py
│   │   │       paystack.py
│   │   │       __init__.py
│   │   │
│   │   ├───repositories
│   │   │   │   transaction_repository.py
│   │   │   │   wallet_repository.py
│   │   │   │   __init__.py
│   │   │   │
│   │   │   └───__pycache__
│   │   │           transaction_repository.cpython-313.pyc
│   │   │           wallet_repository.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │
│   │   ├───services
│   │   │   │   audit.py
│   │   │   │   audit_query_service.py
│   │   │   │   commission_service.py
│   │   │   │   currency_service.py
│   │   │   │   payout_service.py
│   │   │   │   wallet_admin_service.py
│   │   │   │   wallet_service.py
│   │   │   │   __init__.py
│   │   │   │
│   │   │   └───__pycache__
│   │   │           audit.cpython-313.pyc
│   │   │           audit_query_service.cpython-313.pyc
│   │   │           commission_service.cpython-313.pyc
│   │   │           currency_service.cpython-313.pyc
│   │   │           payout_service.cpython-313.pyc
│   │   │           wallet_admin_service.cpython-313.pyc
│   │   │           wallet_service.cpython-313.pyc
│   │   │           __init__.cpython-313.pyc
│   │   │
│   │   └───__pycache__
│   │           exceptions.cpython-313.pyc
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
├───migrations
│   │   alembic.ini
│   │   env.py
│   │   envy.html
│   │   README
│   │   script.py.mako
│   │
│   ├───versions
│   │   │   23ecc92eb3fd_add_event_model_indexes_and_constraints.py
│   │   │   67a805678c79_initial_clean_migration_with_all_models.py
│   │   │   6c994e0e5f9d_add_kyc_verification_fields_to_.py
│   │   │   75602feb99cc_fix_csrf_and_cleanup.py
│   │   │   8e254b19689d_feat_add_event_approval_workflow_with_.py
│   │   │   b512872ef96a_add_email_verified_phone_verified_and_.py
│   │   │   c76f972a4ed1_sync_schema_remove_fan_profiles_and_add_.py
│   │   │
│   │   └───__pycache__
│   │           23ecc92eb3fd_add_event_model_indexes_and_constraints.cpython-313.pyc
│   │           67a805678c79_initial_clean_migration_with_all_models.cpython-313.pyc
│   │           6c994e0e5f9d_add_kyc_verification_fields_to_.cpython-313.pyc
│   │           75602feb99cc_fix_csrf_and_cleanup.cpython-313.pyc
│   │           8e254b19689d_feat_add_event_approval_workflow_with_.cpython-313.pyc
│   │           b512872ef96a_add_email_verified_phone_verified_and_.cpython-313.pyc
│   │           c76f972a4ed1_sync_schema_remove_fan_profiles_and_add_.cpython-313.pyc
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
│       ERROR_FIXES_SUMMARY.md
│       IMPERSONATION_SYSTEM_STATUS.md
│       OWNER_SYSTEM_COMPLETE.md
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
│   └───__pycache__
│           test_flow.cpython-313-pytest-8.3.0.pyc
│
├───static
│   │   admin.css
│   │   deposit.css
│   │   home.css
│   │   owner.css
│   │   script.js
│   │   style.css
│   │
│   ├───admin
│   │       admin.css
│   │       owner.css
│   │
│   ├───css
│   │   │   dashboard.css
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
│   │   ├───global
│   │   │       main.js
│   │   │
│   │   └───modules
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
│   │   reset_password.html (add CSRF token)
│   │   reset_request.html
│   │   reset_request.html (add CSRF token)
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
│   │   └───owner
│   │           dashboard.html (ADDITION)
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
│   │   │   analytics.html
│   │   │   attendees.html
│   │   │   attendee_dashboard.html
│   │   │   create.html
│   │   │   edit.html
│   │   │   events_hub.html
│   │   │   event_theme.html
│   │   │   landing.html
│   │   │   list.html
│   │   │   my_events.html
│   │   │   my_registrations.html
│   │   │   not_found.html
│   │   │   organizer_dashboard.html
│   │   │   register.html
│   │   │   registration_confirmation.html
│   │   │   scanner.html
│   │   │   service_provider_dashboard.html
│   │   │
│   │   ├───admin
│   │   │   │   dashboard.html
│   │   │   │   events.html
│   │   │   │   pending.html
│   │   │   │   staff.html
│   │   │   │   staff.html.html
│   │   │   │
│   │   │   └───org
│   │   │           dashboard.html
│   │   │
│   │   ├───attendee
│   │   │       my_registrations.html
│   │   │       register.html
│   │   │       registration_confirmation.html
│   │   │
│   │   ├───organizer
│   │   │       analytics.html
│   │   │       attendees.html
│   │   │       edit.html
│   │   │       my_events.html
│   │   │       organizer_dashboard.html
│   │   │       scanner.html
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
│   │       dashboard.html
│   │       enhanced_dashboard.html
│   │
│   ├───kyc
│   │       complete_profile.html
│   │       limits.html
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
│   │       edit.html
│   │       overview.html
│   │
│   ├───transport
│   │   │   base.html
│   │   │   become_driver.html
│   │   │   book.html
│   │   │   booking_detatails.html
│   │   │   driver_dashboard.html
│   │   │   home.html
│   │   │   homes.html
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
│   │   inspect_db.py
│   │   phase_1.py
│   │   phase_2.py
│   │   project_structure.txt
│   │   read_llater.txt
│   │   sample_users.py
│   │   seed_roles.py
│   │   seed_roles_simple.py
│   │   setup_owner.py
│   │   test roles.py
│   │   test_audit_system.py
│   │   test_auth_import.py
│   │   test_fan_kyc.py
│   │   test_impersonation.py
│   │   test_impersonation_simple.py
│   │   test_kyc_compliance.py
│   │   test_simple.py
│   │   transport_model.py
│   │   user_roles_id.py
│   │   verify_fix.py
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


(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app>
