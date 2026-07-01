2026-06-18 09:41:15,651 [INFO] app.admin: \u2705 Registered compliance blueprint
2026-06-18 09:41:15,656 [INFO] app.admin: \u2705 Registered support blueprint
2026-06-18 09:41:15,660 [INFO] app.admin: \u2705 Registered auditor blueprint
2026-06-18 09:41:15,784 [INFO] app.admin: \u2705 Registered trust_settings blueprint
2026-06-18 09:41:15,792 [INFO] app.admin: \u2705 Registered role-based admin route modules
2026-06-18 09:41:16,237 [INFO] app: \u2705 Mail extension initialized
2026-06-18 09:41:16,237 [INFO] app: \U0001f6e1\ufe0f IDGuard enabled with 1 String FK exceptions
2026-06-18 09:41:16,238 [INFO] app: \u2705 IDGuard initialized for runtime ID mixing protection
2026-06-18 09:41:16,482 [INFO] app.events.signal_handlers: Events module signal handlers connected
2026-06-18 09:41:16,482 [INFO] app: Events module signal handlers connected
2026-06-18 09:41:16,515 [INFO] app: \u2705 Tournament module registered
2026-06-18 09:41:16,520 [INFO] app: \u2705 Tourism module registered with routes
2026-06-18 09:41:16,547 [INFO] app.transport.api.routes: \u2705 Transport API resources registered (32 endpoints)
2026-06-18 09:41:16,562 [INFO] app: \u2705 Transport API initialized - /api/transport/* routes live
2026-06-18 09:41:16,562 [INFO] app: \u2705 Transport module initialized (Deep Lazy)
2026-06-18 09:41:16,581 [INFO] app: \u2705 Transport module registered
2026-06-18 09:41:16,592 [INFO] app: \u2705 Accommodation module registered
2026-06-18 09:41:16,596 [INFO] app: \u2705 Wallet module registered
2026-06-18 09:41:16,702 [DEBUG] app: CLI commands not found � skipping
2026-06-18 09:41:16,704 [INFO] app: \u2705 IDGuard CLI commands registered
2026-06-18 09:41:16,704 [INFO] app.events.signal_handlers: Events module signal handlers connected
2026-06-18 09:41:16,704 [INFO] app: \u2705 Event signal handlers connected
2026-06-18 09:41:16,706 [INFO] app: \u2705 Module disabled page handler registered
2026-06-18 09:41:16,708 [INFO] app: \u2705 Template helpers registered (safe_url, module_enabled)
2026-06-18 09:41:16,714 [INFO] app: \u2705 Module API blueprint registered
2026-06-18 09:41:16,717 [INFO] app: \u2705 Health API blueprint registered
2026-06-18 09:41:16,721 [INFO] app: \u2705 Module reload hooks initialized (Instant Effect)
2026-06-18 09:41:16,727 [INFO] app.endpoint_validator: \u2705 All known endpoint references validated successfully
2026-06-18 09:41:16,729 [INFO] app: \u2705 App factory completed in 3.97 seconds
Settings routes registered to events blueprint
['admin.auditor.api_audit_logs', 'admin.auditor.compliance_reports', 'admin.auditor.dashboard', 'admin.auditor.data_access_logs', 'admin.auditor.export_logs', 'admin.auditor.financial_audit', 'admin.auditor.forensic_logs', 'admin.auditor.security_events', 'admin.auditor_dashboard', 'admin.auditor_export', 'admin.compliance.aml_queue', 'admin.compliance.case_action', 'admin.compliance.case_history', 'admin.compliance.cases', 'admin.compliance.dashboard', 'admin.compliance.data_request_action', 'admin.compliance.data_requests', 'admin.compliance.escalations', 'admin.compliance.generate_report', 'admin.compliance.kyc_action', 'admin.compliance.kyc_queue', 'admin.compliance.licences', 'admin.compliance.org_action', 'admin.compliance.organisations', 'admin.compliance.payout_action', 'admin.compliance.payouts', 'admin.compliance.reports', 'admin.compliance.view_case', 'admin.compliance.view_data_request', 'admin.compliance.view_kyc', 'admin.compliance.view_org', 'admin.compliance.view_payout', 'admin.compliance_action', 'admin.compliance_dashboard', 'admin.moderator.activate_user', 'admin.moderator.add_user_note', 'admin.moderator.ai_analytics', 'admin.moderator.api_approve_submission', 'admin.moderator.api_auto_priority', 'admin.moderator.api_close_flag', 'admin.moderator.api_queue_health', 'admin.moderator.api_reject_submission', 'admin.moderator.api_resolve_flag', 'admin.moderator.approve_event', 'admin.moderator.approve_item', 'admin.moderator.approve_org', 'admin.moderator.approve_submission', 'admin.moderator.assign_flag', 'admin.moderator.assign_submission', 'admin.moderator.audit_insights', 'admin.moderator.audit_log', 'admin.moderator.audit_log_export', 'admin.moderator.bulk_flag_action', 'admin.moderator.bulk_submission_action', 'admin.moderator.bulk_user_action', 'admin.moderator.categories_list', 'admin.moderator.claim_submission', 'admin.moderator.close_flag', 'admin.moderator.content_moderation', 'admin.moderator.content_safety', 'admin.moderator.create_category', 'admin.moderator.create_flag_route', 'admin.moderator.cross_platform', 'admin.moderator.dashboard', 'admin.moderator.deactivate_user', 'admin.moderator.escalate_flag', 'admin.moderator.escalate_to_compliance', 'admin.moderator.escalation_queue', 'admin.moderator.events_list', 'admin.moderator.flag_event', 'admin.moderator.flag_item', 'admin.moderator.flag_kyc', 'admin.moderator.flag_org', 'admin.moderator.flag_submission', 'admin.moderator.flag_user', 'admin.moderator.flagged_content', 'admin.moderator.items_list', 'admin.moderator.kyc_queue', 'admin.moderator.moderate_action', 'admin.moderator.moderate_submission', 'admin.moderator.my_queue', 'admin.moderator.orgs_queue', 'admin.moderator.performance', 'admin.moderator.preview_submission', 'admin.moderator.queue_metrics', 'admin.moderator.refer_kyc_compliance', 'admin.moderator.refer_org_compliance', 'admin.moderator.reject_event', 'admin.moderator.reject_item', 'admin.moderator.reject_org', 'admin.moderator.reject_submission', 'admin.moderator.reject_user_verification', 'admin.moderator.reprioritise_flag', 'admin.moderator.request_changes', 'admin.moderator.resolve_escalation', 'admin.moderator.resolve_flag_route', 'admin.moderator.stats', 'admin.moderator.suspend_user', 'admin.moderator.toggle_category_active', 'admin.moderator.toggle_item_featured', 'admin.moderator.training', 'admin.moderator.training_content', 'admin.moderator.transport_bookings', 'admin.moderator.transport_drivers', 'admin.moderator.transport_moderate_action', 'admin.moderator.transport_moderation', 'admin.moderator.transport_third_party_applications', 'admin.moderator.transport_vehicles', 'admin.moderator.unified_queue', 'admin.moderator.unsuspend_user', 'admin.moderator.user_moderation', 'admin.moderator.verify_user', 'admin.moderator.view_category', 'admin.moderator.view_event', 'admin.moderator.view_flag', 'admin.moderator.view_item', 'admin.moderator.view_kyc', 'admin.moderator.view_org', 'admin.moderator.view_submission', 'admin.moderator.view_transport_booking', 'admin.moderator.view_transport_driver', 'admin.moderator.view_transport_vehicle', 'admin.moderator.view_user', 'admin.moderator.warn_user', 'admin.owner.compliance_dashboard', 'admin.owner.compliance_reports_page', 'admin.owner.kyc_compliance_reports', 'admin.support.dashboard', 'admin.support.kyc_approve', 'admin.support.kyc_pending', 'admin.support.kyc_reject', 'admin.support.kyc_review', 'admin.support.support_tickets', 'admin.support.user_search', 'admin.support.view_user', 'fx_api.get_supported_currencies', 'wallet.compliance_status', 'wallet_admin_api.auditor_reconciliation', 'wallet_admin_api.compliance_freeze_account', 'wallet_api.get_supported_currencies'

python -c "from app import create_app; app=create_app(); endpoints={r.endpoint for r in app.url_map.iter_rules()}; required=['admin.tourism_admin_dashboard','admin.event_manager_dashboard','admin.transport_admin_dashboard','admin.wallet_admin_dashboard','admin.accommodation_admin_dashboard','accommodation.host_dashboard','transport.driver_dashboard','admin.auditor.dashboard','admin.compliance.dashboard','admin.moderator.dashboard','admin.support.dashboard']; print({e:(e in endpoints) for e in required})"

shell


2026-06-18 09:45:05,314 [INFO] app.admin: \u2705 Registered owner blueprint
2026-06-18 09:45:05,360 [INFO] app.admin: \u2705 Registered moderator blueprint
2026-06-18 09:45:05,361 [INFO] app.admin: \u2705 Registered compliance blueprint
2026-06-18 09:45:05,362 [INFO] app.admin: \u2705 Registered support blueprint
2026-06-18 09:45:05,364 [INFO] app.admin: \u2705 Registered auditor blueprint
2026-06-18 09:45:05,456 [INFO] app.admin: \u2705 Registered trust_settings blueprint
2026-06-18 09:45:05,474 [INFO] app.admin: \u2705 Registered role-based admin route modules
2026-06-18 09:45:06,200 [INFO] app: \u2705 Mail extension initialized
2026-06-18 09:45:06,200 [INFO] app: \U0001f6e1\ufe0f IDGuard enabled with 1 String FK exceptions
2026-06-18 09:45:06,201 [INFO] app: \u2705 IDGuard initialized for runtime ID mixing protection
2026-06-18 09:45:06,648 [INFO] app.events.signal_handlers: Events module signal handlers connected
2026-06-18 09:45:06,649 [INFO] app: Events module signal handlers connected
2026-06-18 09:45:06,710 [INFO] app: \u2705 Tournament module registered
2026-06-18 09:45:06,720 [INFO] app: \u2705 Tourism module registered with routes
2026-06-18 09:45:06,803 [INFO] app.transport.api.routes: \u2705 Transport API resources registered (32 endpoints)
2026-06-18 09:45:06,815 [INFO] app: \u2705 Transport API initialized - /api/transport/* routes live
2026-06-18 09:45:06,815 [INFO] app: \u2705 Transport module initialized (Deep Lazy)
2026-06-18 09:45:06,834 [INFO] app: \u2705 Transport module registered
2026-06-18 09:45:06,843 [INFO] app: \u2705 Accommodation module registered
2026-06-18 09:45:06,847 [INFO] app: \u2705 Wallet module registered
2026-06-18 09:45:06,936 [DEBUG] app: CLI commands not found � skipping
2026-06-18 09:45:06,936 [INFO] app: \u2705 IDGuard CLI commands registered
2026-06-18 09:45:06,936 [INFO] app.events.signal_handlers: Events module signal handlers connected
2026-06-18 09:45:06,936 [INFO] app: \u2705 Event signal handlers connected
2026-06-18 09:45:06,938 [INFO] app: \u2705 Module disabled page handler registered
2026-06-18 09:45:06,939 [INFO] app: \u2705 Template helpers registered (safe_url, module_enabled)
2026-06-18 09:45:06,942 [INFO] app: \u2705 Module API blueprint registered
2026-06-18 09:45:06,944 [INFO] app: \u2705 Health API blueprint registered
2026-06-18 09:45:06,944 [INFO] app: \u2705 Module reload hooks initialized (Instant Effect)
2026-06-18 09:45:06,946 [INFO] app.endpoint_validator: \u2705 All known endpoint references validated successfully
2026-06-18 09:45:06,947 [INFO] app: \u2705 App factory completed in 5.00 seconds
Settings routes registered to events blueprint
{'admin.tourism_admin_dashboard': True, 
'admin.event_manager_dashboard': True, 
'admin.transport_admin_dashboard': True, 
'admin.wallet_admin_dashboard': True, 
'admin.accommodation_admin_dashboard': True,
'accommodation.host_dashboard': True, 
'transport.driver_dashboard': True, 
'admin.auditor.dashboard': True,
'admin.compliance.dashboard': True, 
'admin.moderator.dashboard': True, 
'admin.support.dashboard': True}