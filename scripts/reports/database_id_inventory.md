# Database ID Inventory


## _pg_foreign_data_wrappers.authorization_identifier

Type:
name

Nullable:
YES

---

## _pg_foreign_data_wrappers.oid

Type:
oid

Nullable:
YES

---

## _pg_foreign_servers.authorization_identifier

Type:
name

Nullable:
YES

---

## _pg_foreign_servers.oid

Type:
oid

Nullable:
YES

---

## _pg_foreign_tables.authorization_identifier

Type:
name

Nullable:
YES

---

## _pg_user_mappings.authorization_identifier

Type:
name

Nullable:
YES

---

## _pg_user_mappings.oid

Type:
oid

Nullable:
YES

---

## accommodation_amenities_master.id

Type:
bigint

Nullable:
NO

---

## accommodation_availability_rules.id

Type:
bigint

Nullable:
NO

---

## accommodation_availability_rules.property_id

Type:
bigint

Nullable:
NO

---

## accommodation_blocked_dates.booking_id

Type:
bigint

Nullable:
YES

---

## accommodation_blocked_dates.id

Type:
bigint

Nullable:
NO

---

## accommodation_blocked_dates.property_id

Type:
bigint

Nullable:
NO

---

## accommodation_booking_history.booking_id

Type:
bigint

Nullable:
NO

---

## accommodation_booking_history.changed_by_user_id

Type:
bigint

Nullable:
YES

---

## accommodation_booking_history.id

Type:
bigint

Nullable:
NO

---

## accommodation_bookings.assigned_room_id

Type:
bigint

Nullable:
YES

---

## accommodation_bookings.booked_by_user_id

Type:
bigint

Nullable:
NO

---

## accommodation_bookings.cancelled_by_user_id

Type:
bigint

Nullable:
YES

---

## accommodation_bookings.context_id

Type:
character varying

Nullable:
YES

---

## accommodation_bookings.event_id

Type:
bigint

Nullable:
YES

---

## accommodation_bookings.event_participation_id

Type:
bigint

Nullable:
YES

---

## accommodation_bookings.group_booking_id

Type:
character varying

Nullable:
YES

---

## accommodation_bookings.guest_user_id

Type:
bigint

Nullable:
YES

---

## accommodation_bookings.host_user_id

Type:
bigint

Nullable:
NO

---

## accommodation_bookings.id

Type:
bigint

Nullable:
NO

---

## accommodation_bookings.idempotency_key

Type:
character varying

Nullable:
YES

---

## accommodation_bookings.paid_at

Type:
timestamp without time zone

Nullable:
YES

---

## accommodation_bookings.primary_guest_id

Type:
bigint

Nullable:
YES

---

## accommodation_bookings.property_id

Type:
bigint

Nullable:
NO

---

## accommodation_bookings.room_type_id

Type:
bigint

Nullable:
YES

---

## accommodation_bookings.wallet_txn_id

Type:
character varying

Nullable:
YES

---

## accommodation_inventory_blocks.id

Type:
bigint

Nullable:
NO

---

## accommodation_inventory_blocks.room_type_id

Type:
bigint

Nullable:
NO

---

## accommodation_photos.id

Type:
bigint

Nullable:
NO

---

## accommodation_photos.property_id

Type:
bigint

Nullable:
NO

---

## accommodation_properties.id

Type:
bigint

Nullable:
NO

---

## accommodation_properties.owner_org_id

Type:
bigint

Nullable:
YES

---

## accommodation_properties.owner_user_id

Type:
bigint

Nullable:
YES

---

## accommodation_property_amenities.amenity_id

Type:
bigint

Nullable:
NO

---

## accommodation_property_amenities.id

Type:
bigint

Nullable:
NO

---

## accommodation_property_amenities.property_id

Type:
bigint

Nullable:
NO

---

## accommodation_reviews.booking_id

Type:
bigint

Nullable:
NO

---

## accommodation_reviews.id

Type:
bigint

Nullable:
NO

---

## accommodation_reviews.property_id

Type:
bigint

Nullable:
NO

---

## accommodation_reviews.reviewer_id

Type:
bigint

Nullable:
NO

---

## accommodation_room_bookings.booking_id

Type:
bigint

Nullable:
NO

---

## accommodation_room_bookings.id

Type:
bigint

Nullable:
NO

---

## accommodation_room_bookings.room_id

Type:
bigint

Nullable:
NO

---

## accommodation_room_categories.id

Type:
bigint

Nullable:
NO

---

## accommodation_room_categories.property_id

Type:
bigint

Nullable:
NO

---

## accommodation_room_types.id

Type:
bigint

Nullable:
NO

---

## accommodation_room_types.property_id

Type:
bigint

Nullable:
NO

---

## accommodation_rooms.category_id

Type:
bigint

Nullable:
NO

---

## accommodation_rooms.features_override

Type:
json

Nullable:
YES

---

## accommodation_rooms.id

Type:
bigint

Nullable:
NO

---

## accommodation_rooms.property_id

Type:
bigint

Nullable:
NO

---

## accommodation_rules.id

Type:
bigint

Nullable:
NO

---

## accommodation_rules.property_id

Type:
bigint

Nullable:
NO

---

## accommodation_wishlists.id

Type:
bigint

Nullable:
NO

---

## accommodation_wishlists.property_id

Type:
bigint

Nullable:
NO

---

## accommodation_wishlists.user_id

Type:
bigint

Nullable:
NO

---

## accounts.id

Type:
uuid

Nullable:
NO

---

## accounts.user_id

Type:
bigint

Nullable:
NO

---

## agent_commissions.agent_id

Type:
bigint

Nullable:
NO

---

## agent_commissions.id

Type:
bigint

Nullable:
NO

---

## agent_commissions.paid_at

Type:
timestamp without time zone

Nullable:
YES

---

## agent_commissions.paid_by

Type:
bigint

Nullable:
YES

---

## agent_commissions.recipient_id

Type:
bigint

Nullable:
YES

---

## agent_commissions.source_id

Type:
character varying

Nullable:
NO

---

## api_audit_logs.correlation_id

Type:
character varying

Nullable:
YES

---

## api_audit_logs.id

Type:
bigint

Nullable:
NO

---

## api_audit_logs.request_id

Type:
character varying

Nullable:
YES

---

## api_keys.id

Type:
bigint

Nullable:
NO

---

## api_keys.key_id

Type:
character varying

Nullable:
NO

---

## api_keys.owner_id

Type:
bigint

Nullable:
NO

---

## attributes.dtd_identifier

Type:
name

Nullable:
YES

---

## audit_logs.device_id

Type:
character varying

Nullable:
YES

---

## audit_logs.id

Type:
bigint

Nullable:
NO

---

## audit_logs.org_id

Type:
bigint

Nullable:
YES

---

## audit_logs.resource_id

Type:
character varying

Nullable:
YES

---

## audit_logs.user_id

Type:
bigint

Nullable:
YES

---

## auth_configurations.google_client_id

Type:
character varying

Nullable:
YES

---

## auth_configurations.id

Type:
bigint

Nullable:
NO

---

## auth_configurations.sendgrid_api_key

Type:
character varying

Nullable:
YES

---

## auth_configurations.sendgrid_enabled

Type:
boolean

Nullable:
NO

---

## auth_configurations.sendgrid_from_email

Type:
character varying

Nullable:
YES

---

## auth_configurations.sendgrid_from_name

Type:
character varying

Nullable:
YES

---

## auth_configurations.sms_provider_preference

Type:
character varying

Nullable:
NO

---

## auth_configurations.twilio_account_sid

Type:
character varying

Nullable:
YES

---

## columns.dtd_identifier

Type:
name

Nullable:
YES

---

## columns.identity_cycle

Type:
character varying

Nullable:
YES

---

## columns.identity_generation

Type:
character varying

Nullable:
YES

---

## columns.identity_increment

Type:
character varying

Nullable:
YES

---

## columns.identity_maximum

Type:
character varying

Nullable:
YES

---

## columns.identity_minimum

Type:
character varying

Nullable:
YES

---

## columns.identity_start

Type:
character varying

Nullable:
YES

---

## columns.is_identity

Type:
character varying

Nullable:
YES

---

## compliance_audit_logs.decided_at

Type:
timestamp without time zone

Nullable:
NO

---

## compliance_audit_logs.decided_by

Type:
bigint

Nullable:
YES

---

## compliance_audit_logs.entity_id

Type:
bigint

Nullable:
NO

---

## compliance_audit_logs.id

Type:
bigint

Nullable:
NO

---

## compliance_cases.flag_id

Type:
bigint

Nullable:
YES

---

## compliance_cases.id

Type:
bigint

Nullable:
NO

---

## compliance_cases.kyc_id

Type:
bigint

Nullable:
YES

---

## compliance_cases.organisation_id

Type:
bigint

Nullable:
YES

---

## compliance_cases.payout_id

Type:
bigint

Nullable:
YES

---

## compliance_cases.public_id

Type:
character varying

Nullable:
NO

---

## compliance_cases.user_id

Type:
bigint

Nullable:
YES

---

## compliance_reports.id

Type:
bigint

Nullable:
NO

---

## compliance_reports.public_id

Type:
character varying

Nullable:
NO

---

## compliance_settings.id

Type:
bigint

Nullable:
NO

---

## content_flags.ai_confidence

Type:
double precision

Nullable:
YES

---

## content_flags.compliance_case_id

Type:
bigint

Nullable:
YES

---

## content_flags.entity_id

Type:
bigint

Nullable:
NO

---

## content_flags.id

Type:
bigint

Nullable:
NO

---

## content_submissions.assigned_to_id

Type:
bigint

Nullable:
YES

---

## content_submissions.category_id

Type:
bigint

Nullable:
NO

---

## content_submissions.id

Type:
bigint

Nullable:
NO

---

## content_submissions.item_id

Type:
bigint

Nullable:
YES

---

## data_access_logs.id

Type:
bigint

Nullable:
NO

---

## data_access_logs.resource_id

Type:
character varying

Nullable:
YES

---

## data_access_logs.subject_user_id

Type:
bigint

Nullable:
NO

---

## data_change_logs.entity_id

Type:
character varying

Nullable:
NO

---

## data_change_logs.id

Type:
bigint

Nullable:
NO

---

## data_change_logs.public_id

Type:
character varying

Nullable:
NO

---

## data_subject_requests.id

Type:
bigint

Nullable:
NO

---

## data_subject_requests.identity_verified

Type:
boolean

Nullable:
NO

---

## data_subject_requests.public_id

Type:
character varying

Nullable:
NO

---

## data_subject_requests.user_id

Type:
bigint

Nullable:
NO

---

## data_type_privileges.dtd_identifier

Type:
name

Nullable:
YES

---

## discount_codes.event_id

Type:
bigint

Nullable:
NO

---

## discount_codes.id

Type:
bigint

Nullable:
NO

---

## discount_codes.valid_from

Type:
timestamp without time zone

Nullable:
NO

---

## discount_codes.valid_until

Type:
timestamp without time zone

Nullable:
YES

---

## domains.dtd_identifier

Type:
name

Nullable:
YES

---

## driver_profiles.id

Type:
bigint

Nullable:
NO

---

## driver_profiles.tenant_id

Type:
character varying

Nullable:
NO

---

## driver_profiles.user_id

Type:
bigint

Nullable:
NO

---

## driver_vehicle_history.driver_id

Type:
bigint

Nullable:
NO

---

## driver_vehicle_history.id

Type:
bigint

Nullable:
NO

---

## driver_vehicle_history.replacement_vehicle_id

Type:
bigint

Nullable:
YES

---

## driver_vehicle_history.tenant_id

Type:
character varying

Nullable:
NO

---

## driver_vehicle_history.vehicle_id

Type:
bigint

Nullable:
NO

---

## element_types.collection_type_identifier

Type:
name

Nullable:
YES

---

## element_types.dtd_identifier

Type:
name

Nullable:
YES

---

## emergency_access.id

Type:
bigint

Nullable:
NO

---

## emergency_access.incident_type

Type:
character varying

Nullable:
NO

---

## event_assignments.accommodation_booking_id

Type:
bigint

Nullable:
YES

---

## event_assignments.assigned_by_id

Type:
bigint

Nullable:
YES

---

## event_assignments.attendee_id

Type:
bigint

Nullable:
NO

---

## event_assignments.community_host_id

Type:
bigint

Nullable:
YES

---

## event_assignments.event_id

Type:
bigint

Nullable:
NO

---

## event_assignments.id

Type:
bigint

Nullable:
NO

---

## event_assignments.meal_booking_id

Type:
bigint

Nullable:
YES

---

## event_assignments.registration_id

Type:
bigint

Nullable:
YES

---

## event_assignments.transport_booking_id

Type:
bigint

Nullable:
YES

---

## event_host_registrations.approved_by_id

Type:
bigint

Nullable:
YES

---

## event_host_registrations.event_id

Type:
bigint

Nullable:
NO

---

## event_host_registrations.host_user_id

Type:
bigint

Nullable:
NO

---

## event_host_registrations.id

Type:
bigint

Nullable:
NO

---

## event_host_registrations.property_id

Type:
bigint

Nullable:
NO

---

## event_moderation_logs.event_id

Type:
bigint

Nullable:
NO

---

## event_moderation_logs.id

Type:
bigint

Nullable:
NO

---

## event_moderation_logs.user_id

Type:
bigint

Nullable:
NO

---

## event_payment_preferences.event_id

Type:
bigint

Nullable:
NO

---

## event_payment_preferences.id

Type:
bigint

Nullable:
NO

---

## event_payment_preferences.user_id

Type:
bigint

Nullable:
NO

---

## event_registrations.attendee_user_id

Type:
bigint

Nullable:
YES

---

## event_registrations.booked_by_user_id

Type:
bigint

Nullable:
YES

---

## event_registrations.checked_in_by_id

Type:
bigint

Nullable:
YES

---

## event_registrations.event_id

Type:
bigint

Nullable:
NO

---

## event_registrations.group_booking_id

Type:
character varying

Nullable:
YES

---

## event_registrations.id

Type:
bigint

Nullable:
NO

---

## event_registrations.id_number

Type:
character varying

Nullable:
YES

---

## event_registrations.id_type

Type:
character varying

Nullable:
YES

---

## event_registrations.ticket_type_id

Type:
bigint

Nullable:
NO

---

## event_registrations.user_id

Type:
bigint

Nullable:
YES

---

## event_registrations.wallet_txn_id

Type:
character varying

Nullable:
YES

---

## event_roles.assigned_by_id

Type:
bigint

Nullable:
YES

---

## event_roles.event_id

Type:
bigint

Nullable:
NO

---

## event_roles.id

Type:
bigint

Nullable:
NO

---

## event_roles.organisation_id

Type:
bigint

Nullable:
YES

---

## event_roles.user_id

Type:
bigint

Nullable:
NO

---

## event_settings.id

Type:
bigint

Nullable:
NO

---

## event_settings.updated_by_id

Type:
integer

Nullable:
YES

---

## event_themes.event_id

Type:
bigint

Nullable:
NO

---

## event_themes.id

Type:
bigint

Nullable:
NO

---

## event_ticket_types.event_id

Type:
bigint

Nullable:
NO

---

## event_ticket_types.id

Type:
bigint

Nullable:
NO

---

## event_transfer_logs.event_id

Type:
bigint

Nullable:
NO

---

## event_transfer_logs.from_owner_id

Type:
bigint

Nullable:
NO

---

## event_transfer_logs.id

Type:
bigint

Nullable:
NO

---

## event_transfer_logs.to_owner_id

Type:
bigint

Nullable:
NO

---

## event_transfer_logs.transferred_by_id

Type:
bigint

Nullable:
NO

---

## event_transfer_requests.approved_by_id

Type:
bigint

Nullable:
YES

---

## event_transfer_requests.event_id

Type:
bigint

Nullable:
NO

---

## event_transfer_requests.from_organization_id

Type:
bigint

Nullable:
YES

---

## event_transfer_requests.from_user_id

Type:
bigint

Nullable:
YES

---

## event_transfer_requests.id

Type:
bigint

Nullable:
NO

---

## event_transfer_requests.requested_by_id

Type:
bigint

Nullable:
NO

---

## event_transfer_requests.to_organization_id

Type:
bigint

Nullable:
YES

---

## event_transfer_requests.to_user_id

Type:
bigint

Nullable:
YES

---

## event_waitlist.event_id

Type:
bigint

Nullable:
NO

---

## event_waitlist.id

Type:
bigint

Nullable:
NO

---

## event_waitlist.ticket_type_id

Type:
bigint

Nullable:
YES

---

## event_waitlist.user_id

Type:
bigint

Nullable:
NO

---

## events.approved_by_id

Type:
bigint

Nullable:
YES

---

## events.created_by_entity_id

Type:
bigint

Nullable:
NO

---

## events.created_by_id

Type:
bigint

Nullable:
YES

---

## events.current_owner_id

Type:
bigint

Nullable:
NO

---

## events.deactivated_by_id

Type:
bigint

Nullable:
YES

---

## events.deleted_by_id

Type:
bigint

Nullable:
YES

---

## events.id

Type:
bigint

Nullable:
NO

---

## events.organization_id

Type:
bigint

Nullable:
YES

---

## events.organizer_id

Type:
bigint

Nullable:
NO

---

## events.original_creator_id

Type:
bigint

Nullable:
YES

---

## events.public_id

Type:
character varying

Nullable:
NO

---

## events.published_by_id

Type:
bigint

Nullable:
YES

---

## events.suspended_by_id

Type:
bigint

Nullable:
YES

---

## events.taken_down_by_id

Type:
bigint

Nullable:
YES

---

## events.updated_by_id

Type:
bigint

Nullable:
YES

---

## fan_profiles.id

Type:
bigint

Nullable:
NO

---

## fan_profiles.user_id

Type:
bigint

Nullable:
NO

---

## financial_audit_logs.from_user_id

Type:
bigint

Nullable:
YES

---

## financial_audit_logs.id

Type:
bigint

Nullable:
NO

---

## financial_audit_logs.organisation_id

Type:
bigint

Nullable:
YES

---

## financial_audit_logs.payment_provider

Type:
character varying

Nullable:
YES

---

## financial_audit_logs.to_user_id

Type:
bigint

Nullable:
YES

---

## financial_audit_logs.transaction_id

Type:
character varying

Nullable:
NO

---

## foreign_data_wrappers.authorization_identifier

Type:
name

Nullable:
YES

---

## foreign_servers.authorization_identifier

Type:
name

Nullable:
YES

---

## fx_rates.id

Type:
bigint

Nullable:
NO

---

## fx_transactions.dest_account_id

Type:
bigint

Nullable:
NO

---

## fx_transactions.id

Type:
bigint

Nullable:
NO

---

## fx_transactions.source_account_id

Type:
bigint

Nullable:
NO

---

## fx_transactions.transaction_id

Type:
character varying

Nullable:
NO

---

## fx_transactions.user_id

Type:
bigint

Nullable:
NO

---

## global_themes.id

Type:
bigint

Nullable:
NO

---

## idempotency_keys.id

Type:
uuid

Nullable:
NO

---

## idempotency_keys.resource_id

Type:
character varying

Nullable:
YES

---

## individual_documents.id

Type:
bigint

Nullable:
NO

---

## individual_documents.user_id

Type:
bigint

Nullable:
NO

---

## individual_verifications.decided_at

Type:
timestamp without time zone

Nullable:
YES

---

## individual_verifications.id

Type:
bigint

Nullable:
NO

---

## individual_verifications.provider_id

Type:
character varying

Nullable:
YES

---

## individual_verifications.reviewer_id

Type:
bigint

Nullable:
YES

---

## individual_verifications.user_id

Type:
bigint

Nullable:
NO

---

## kyc_records.compliance_case_id

Type:
integer

Nullable:
YES

---

## kyc_records.id

Type:
bigint

Nullable:
NO

---

## kyc_records.id_number

Type:
character varying

Nullable:
NO

---

## kyc_records.id_number_masked

Type:
character varying

Nullable:
YES

---

## kyc_records.id_type

Type:
character varying

Nullable:
YES

---

## kyc_records.provider

Type:
character varying

Nullable:
YES

---

## kyc_records.user_id

Type:
bigint

Nullable:
NO

---

## kyc_records.verification_id

Type:
character varying

Nullable:
YES

---

## kyc_records.verified_by_id

Type:
bigint

Nullable:
YES

---

## ledger_entries.account_id

Type:
uuid

Nullable:
NO

---

## ledger_entries.id

Type:
uuid

Nullable:
NO

---

## ledger_entries.transaction_id

Type:
uuid

Nullable:
NO

---

## manageable_categories.id

Type:
bigint

Nullable:
NO

---

## manageable_items.category_id

Type:
bigint

Nullable:
NO

---

## manageable_items.id

Type:
bigint

Nullable:
NO

---

## media.entity_id

Type:
character varying

Nullable:
NO

---

## media.id

Type:
bigint

Nullable:
NO

---

## media.public_id

Type:
character varying

Nullable:
NO

---

## media.upload_session_id

Type:
character varying

Nullable:
YES

---

## media.video_url

Type:
character varying

Nullable:
YES

---

## media.width

Type:
integer

Nullable:
YES

---

## media_processing_jobs.celery_task_id

Type:
character varying

Nullable:
YES

---

## media_processing_jobs.id

Type:
bigint

Nullable:
NO

---

## media_processing_jobs.media_id

Type:
bigint

Nullable:
NO

---

## media_settings.id

Type:
bigint

Nullable:
NO

---

## media_settings.module_overrides

Type:
json

Nullable:
NO

---

## media_settings.updated_by_id

Type:
bigint

Nullable:
YES

---

## mfa_secrets.id

Type:
bigint

Nullable:
NO

---

## mfa_secrets.user_id

Type:
bigint

Nullable:
NO

---

## moderation_logs.id

Type:
bigint

Nullable:
NO

---

## moderation_logs.moderator_id

Type:
bigint

Nullable:
NO

---

## moderation_logs.submission_id

Type:
bigint

Nullable:
NO

---

## org_member_permissions.id

Type:
bigint

Nullable:
NO

---

## org_member_permissions.member_id

Type:
bigint

Nullable:
NO

---

## org_member_permissions.permission_id

Type:
bigint

Nullable:
NO

---

## org_role_permissions.id

Type:
bigint

Nullable:
NO

---

## org_role_permissions.org_role_id

Type:
bigint

Nullable:
NO

---

## org_role_permissions.permission_id

Type:
bigint

Nullable:
NO

---

## org_roles.id

Type:
bigint

Nullable:
NO

---

## org_roles.organisation_id

Type:
bigint

Nullable:
NO

---

## org_user_roles.id

Type:
bigint

Nullable:
NO

---

## org_user_roles.organisation_member_id

Type:
bigint

Nullable:
NO

---

## org_user_roles.role_id

Type:
bigint

Nullable:
NO

---

## organisation_audit_logs.id

Type:
bigint

Nullable:
NO

---

## organisation_audit_logs.organisation_id

Type:
bigint

Nullable:
YES

---

## organisation_controllers.id

Type:
bigint

Nullable:
NO

---

## organisation_controllers.organisation_id

Type:
bigint

Nullable:
NO

---

## organisation_controllers.user_id

Type:
bigint

Nullable:
NO

---

## organisation_documents.id

Type:
bigint

Nullable:
NO

---

## organisation_documents.organisation_id

Type:
bigint

Nullable:
YES

---

## organisation_drivers.driver_id

Type:
bigint

Nullable:
NO

---

## organisation_drivers.id

Type:
bigint

Nullable:
NO

---

## organisation_drivers.organisation_id

Type:
bigint

Nullable:
NO

---

## organisation_kyb_checks.evidence

Type:
json

Nullable:
YES

---

## organisation_kyb_checks.id

Type:
bigint

Nullable:
NO

---

## organisation_kyb_checks.organisation_id

Type:
bigint

Nullable:
NO

---

## organisation_kyb_checks.provider_id

Type:
character varying

Nullable:
YES

---

## organisation_kyb_documents.id

Type:
bigint

Nullable:
NO

---

## organisation_kyb_documents.organisation_id

Type:
bigint

Nullable:
NO

---

## organisation_licenses.id

Type:
bigint

Nullable:
NO

---

## organisation_licenses.organisation_id

Type:
bigint

Nullable:
YES

---

## organisation_members.id

Type:
bigint

Nullable:
NO

---

## organisation_members.organisation_id

Type:
bigint

Nullable:
NO

---

## organisation_members.user_id

Type:
bigint

Nullable:
NO

---

## organisation_transport_profiles.can_provide_airport_transfers

Type:
boolean

Nullable:
YES

---

## organisation_transport_profiles.can_provide_city_tours

Type:
boolean

Nullable:
YES

---

## organisation_transport_profiles.can_provide_hotel_transfers

Type:
boolean

Nullable:
YES

---

## organisation_transport_profiles.can_provide_on_demand

Type:
boolean

Nullable:
YES

---

## organisation_transport_profiles.can_provide_stadium_shuttles

Type:
boolean

Nullable:
YES

---

## organisation_transport_profiles.id

Type:
bigint

Nullable:
NO

---

## organisation_transport_profiles.organisation_id

Type:
bigint

Nullable:
NO

---

## organisation_transport_profiles.tax_identification_number

Type:
character varying

Nullable:
YES

---

## organisation_transport_profiles.tenant_id

Type:
character varying

Nullable:
NO

---

## organisation_ubos.id

Type:
bigint

Nullable:
NO

---

## organisation_ubos.organisation_id

Type:
bigint

Nullable:
NO

---

## organisation_ubos.user_id

Type:
bigint

Nullable:
NO

---

## organisation_verifications.decided_at

Type:
timestamp without time zone

Nullable:
YES

---

## organisation_verifications.id

Type:
bigint

Nullable:
NO

---

## organisation_verifications.organisation_id

Type:
bigint

Nullable:
NO

---

## organisation_verifications.provider_id

Type:
character varying

Nullable:
YES

---

## organisation_verifications.reviewer_id

Type:
bigint

Nullable:
YES

---

## organisations.compliance_case_id

Type:
bigint

Nullable:
YES

---

## organisations.data_residency_country

Type:
character varying

Nullable:
YES

---

## organisations.id

Type:
bigint

Nullable:
NO

---

## organisations.org_id

Type:
character varying

Nullable:
NO

---

## organisations.primary_contact_user_id

Type:
bigint

Nullable:
YES

---

## organisations.tax_id

Type:
character varying

Nullable:
YES

---

## organizer_messages.event_id

Type:
bigint

Nullable:
NO

---

## organizer_messages.id

Type:
bigint

Nullable:
NO

---

## organizer_messages.public_id

Type:
character varying

Nullable:
NO

---

## organizer_messages.user_id

Type:
bigint

Nullable:
NO

---

## owner_audit_logs.id

Type:
bigint

Nullable:
NO

---

## owner_audit_logs.owner_id

Type:
bigint

Nullable:
NO

---

## owner_settings.id

Type:
bigint

Nullable:
NO

---

## owner_settings.owner_id

Type:
bigint

Nullable:
NO

---

## parameters.dtd_identifier

Type:
name

Nullable:
YES

---

## payment_method_configs.id

Type:
bigint

Nullable:
NO

---

## payment_method_configs.method_id

Type:
character varying

Nullable:
NO

---

## payment_method_configs.provider_name

Type:
character varying

Nullable:
NO

---

## payment_provider_configs.id

Type:
bigint

Nullable:
NO

---

## payment_provider_configs.provider_name

Type:
character varying

Nullable:
NO

---

## payout_requests.agent_id

Type:
bigint

Nullable:
NO

---

## payout_requests.id

Type:
bigint

Nullable:
NO

---

## payout_requests.paid_at

Type:
timestamp without time zone

Nullable:
YES

---

## payout_requests.paid_by

Type:
bigint

Nullable:
YES

---

## permissions.id

Type:
bigint

Nullable:
NO

---

## pg_aggregate.aggfnoid

Type:
regproc

Nullable:
NO

---

## pg_aios.io_id

Type:
integer

Nullable:
YES

---

## pg_aios.pid

Type:
integer

Nullable:
YES

---

## pg_am.oid

Type:
oid

Nullable:
NO

---

## pg_amop.oid

Type:
oid

Nullable:
NO

---

## pg_amproc.oid

Type:
oid

Nullable:
NO

---

## pg_attrdef.adrelid

Type:
oid

Nullable:
NO

---

## pg_attrdef.oid

Type:
oid

Nullable:
NO

---

## pg_attribute.attidentity

Type:
"char"

Nullable:
NO

---

## pg_attribute.attrelid

Type:
oid

Nullable:
NO

---

## pg_attribute.atttypid

Type:
oid

Nullable:
NO

---

## pg_auth_members.oid

Type:
oid

Nullable:
NO

---

## pg_auth_members.roleid

Type:
oid

Nullable:
NO

---

## pg_authid.oid

Type:
oid

Nullable:
NO

---

## pg_authid.rolvaliduntil

Type:
timestamp with time zone

Nullable:
YES

---

## pg_backend_memory_contexts.ident

Type:
text

Nullable:
YES

---

## pg_cast.oid

Type:
oid

Nullable:
NO

---

## pg_class.oid

Type:
oid

Nullable:
NO

---

## pg_class.relfrozenxid

Type:
xid

Nullable:
NO

---

## pg_class.relminmxid

Type:
xid

Nullable:
NO

---

## pg_class.relreplident

Type:
"char"

Nullable:
NO

---

## pg_class.reltoastrelid

Type:
oid

Nullable:
NO

---

## pg_collation.collprovider

Type:
"char"

Nullable:
NO

---

## pg_collation.oid

Type:
oid

Nullable:
NO

---

## pg_constraint.confrelid

Type:
oid

Nullable:
NO

---

## pg_constraint.conindid

Type:
oid

Nullable:
NO

---

## pg_constraint.conparentid

Type:
oid

Nullable:
NO

---

## pg_constraint.conrelid

Type:
oid

Nullable:
NO

---

## pg_constraint.contypid

Type:
oid

Nullable:
NO

---

## pg_constraint.convalidated

Type:
boolean

Nullable:
NO

---

## pg_constraint.oid

Type:
oid

Nullable:
NO

---

## pg_conversion.oid

Type:
oid

Nullable:
NO

---

## pg_database.datfrozenxid

Type:
xid

Nullable:
NO

---

## pg_database.datlocprovider

Type:
"char"

Nullable:
NO

---

## pg_database.datminmxid

Type:
xid

Nullable:
NO

---

## pg_database.oid

Type:
oid

Nullable:
NO

---

## pg_default_acl.oid

Type:
oid

Nullable:
NO

---

## pg_depend.classid

Type:
oid

Nullable:
NO

---

## pg_depend.objid

Type:
oid

Nullable:
NO

---

## pg_depend.objsubid

Type:
integer

Nullable:
NO

---

## pg_depend.refclassid

Type:
oid

Nullable:
NO

---

## pg_depend.refobjid

Type:
oid

Nullable:
NO

---

## pg_depend.refobjsubid

Type:
integer

Nullable:
NO

---

## pg_description.classoid

Type:
oid

Nullable:
NO

---

## pg_description.objoid

Type:
oid

Nullable:
NO

---

## pg_description.objsubid

Type:
integer

Nullable:
NO

---

## pg_enum.enumtypid

Type:
oid

Nullable:
NO

---

## pg_enum.oid

Type:
oid

Nullable:
NO

---

## pg_event_trigger.evtfoid

Type:
oid

Nullable:
NO

---

## pg_event_trigger.oid

Type:
oid

Nullable:
NO

---

## pg_extension.oid

Type:
oid

Nullable:
NO

---

## pg_foreign_data_wrapper.fdwvalidator

Type:
oid

Nullable:
NO

---

## pg_foreign_data_wrapper.oid

Type:
oid

Nullable:
NO

---

## pg_foreign_server.oid

Type:
oid

Nullable:
NO

---

## pg_foreign_table.ftrelid

Type:
oid

Nullable:
NO

---

## pg_group.grosysid

Type:
oid

Nullable:
YES

---

## pg_index.indexrelid

Type:
oid

Nullable:
NO

---

## pg_index.indisreplident

Type:
boolean

Nullable:
NO

---

## pg_index.indisvalid

Type:
boolean

Nullable:
NO

---

## pg_index.indrelid

Type:
oid

Nullable:
NO

---

## pg_inherits.inhrelid

Type:
oid

Nullable:
NO

---

## pg_init_privs.classoid

Type:
oid

Nullable:
NO

---

## pg_init_privs.objoid

Type:
oid

Nullable:
NO

---

## pg_init_privs.objsubid

Type:
integer

Nullable:
NO

---

## pg_language.lanplcallfoid

Type:
oid

Nullable:
NO

---

## pg_language.lanvalidator

Type:
oid

Nullable:
NO

---

## pg_language.oid

Type:
oid

Nullable:
NO

---

## pg_largeobject.loid

Type:
oid

Nullable:
NO

---

## pg_largeobject_metadata.oid

Type:
oid

Nullable:
NO

---

## pg_locks.classid

Type:
oid

Nullable:
YES

---

## pg_locks.objid

Type:
oid

Nullable:
YES

---

## pg_locks.objsubid

Type:
smallint

Nullable:
YES

---

## pg_locks.pid

Type:
integer

Nullable:
YES

---

## pg_locks.transactionid

Type:
xid

Nullable:
YES

---

## pg_locks.virtualxid

Type:
text

Nullable:
YES

---

## pg_namespace.oid

Type:
oid

Nullable:
NO

---

## pg_opclass.oid

Type:
oid

Nullable:
NO

---

## pg_operator.oid

Type:
oid

Nullable:
NO

---

## pg_opfamily.oid

Type:
oid

Nullable:
NO

---

## pg_parameter_acl.oid

Type:
oid

Nullable:
NO

---

## pg_partitioned_table.partdefid

Type:
oid

Nullable:
NO

---

## pg_partitioned_table.partrelid

Type:
oid

Nullable:
NO

---

## pg_policy.oid

Type:
oid

Nullable:
NO

---

## pg_policy.polrelid

Type:
oid

Nullable:
NO

---

## pg_prepared_xacts.gid

Type:
text

Nullable:
YES

---

## pg_proc.oid

Type:
oid

Nullable:
NO

---

## pg_publication.oid

Type:
oid

Nullable:
NO

---

## pg_publication_namespace.oid

Type:
oid

Nullable:
NO

---

## pg_publication_namespace.pnnspid

Type:
oid

Nullable:
NO

---

## pg_publication_namespace.pnpubid

Type:
oid

Nullable:
NO

---

## pg_publication_rel.oid

Type:
oid

Nullable:
NO

---

## pg_publication_rel.prpubid

Type:
oid

Nullable:
NO

---

## pg_publication_rel.prrelid

Type:
oid

Nullable:
NO

---

## pg_range.rngmultitypid

Type:
oid

Nullable:
NO

---

## pg_range.rngtypid

Type:
oid

Nullable:
NO

---

## pg_replication_origin.roident

Type:
oid

Nullable:
NO

---

## pg_replication_origin_status.external_id

Type:
text

Nullable:
YES

---

## pg_replication_origin_status.local_id

Type:
oid

Nullable:
YES

---

## pg_replication_slots.active_pid

Type:
integer

Nullable:
YES

---

## pg_replication_slots.datoid

Type:
oid

Nullable:
YES

---

## pg_replication_slots.invalidation_reason

Type:
text

Nullable:
YES

---

## pg_rewrite.oid

Type:
oid

Nullable:
NO

---

## pg_roles.oid

Type:
oid

Nullable:
YES

---

## pg_roles.rolvaliduntil

Type:
timestamp with time zone

Nullable:
YES

---

## pg_seclabel.classoid

Type:
oid

Nullable:
NO

---

## pg_seclabel.objoid

Type:
oid

Nullable:
NO

---

## pg_seclabel.objsubid

Type:
integer

Nullable:
NO

---

## pg_seclabel.provider

Type:
text

Nullable:
NO

---

## pg_seclabels.classoid

Type:
oid

Nullable:
YES

---

## pg_seclabels.objoid

Type:
oid

Nullable:
YES

---

## pg_seclabels.objsubid

Type:
integer

Nullable:
YES

---

## pg_seclabels.provider

Type:
text

Nullable:
YES

---

## pg_sequence.seqrelid

Type:
oid

Nullable:
NO

---

## pg_sequence.seqtypid

Type:
oid

Nullable:
NO

---

## pg_shadow.usesysid

Type:
oid

Nullable:
YES

---

## pg_shdepend.classid

Type:
oid

Nullable:
NO

---

## pg_shdepend.dbid

Type:
oid

Nullable:
NO

---

## pg_shdepend.objid

Type:
oid

Nullable:
NO

---

## pg_shdepend.objsubid

Type:
integer

Nullable:
NO

---

## pg_shdepend.refclassid

Type:
oid

Nullable:
NO

---

## pg_shdepend.refobjid

Type:
oid

Nullable:
NO

---

## pg_shdescription.classoid

Type:
oid

Nullable:
NO

---

## pg_shdescription.objoid

Type:
oid

Nullable:
NO

---

## pg_shseclabel.classoid

Type:
oid

Nullable:
NO

---

## pg_shseclabel.objoid

Type:
oid

Nullable:
NO

---

## pg_shseclabel.provider

Type:
text

Nullable:
NO

---

## pg_stat_activity.backend_xid

Type:
xid

Nullable:
YES

---

## pg_stat_activity.datid

Type:
oid

Nullable:
YES

---

## pg_stat_activity.leader_pid

Type:
integer

Nullable:
YES

---

## pg_stat_activity.pid

Type:
integer

Nullable:
YES

---

## pg_stat_activity.query_id

Type:
bigint

Nullable:
YES

---

## pg_stat_activity.usesysid

Type:
oid

Nullable:
YES

---

## pg_stat_all_indexes.idx_scan

Type:
bigint

Nullable:
YES

---

## pg_stat_all_indexes.idx_tup_fetch

Type:
bigint

Nullable:
YES

---

## pg_stat_all_indexes.idx_tup_read

Type:
bigint

Nullable:
YES

---

## pg_stat_all_indexes.indexrelid

Type:
oid

Nullable:
YES

---

## pg_stat_all_indexes.last_idx_scan

Type:
timestamp with time zone

Nullable:
YES

---

## pg_stat_all_indexes.relid

Type:
oid

Nullable:
YES

---

## pg_stat_all_tables.idx_scan

Type:
bigint

Nullable:
YES

---

## pg_stat_all_tables.idx_tup_fetch

Type:
bigint

Nullable:
YES

---

## pg_stat_all_tables.last_idx_scan

Type:
timestamp with time zone

Nullable:
YES

---

## pg_stat_all_tables.relid

Type:
oid

Nullable:
YES

---

## pg_stat_database.datid

Type:
oid

Nullable:
YES

---

## pg_stat_database.idle_in_transaction_time

Type:
double precision

Nullable:
YES

---

## pg_stat_database_conflicts.datid

Type:
oid

Nullable:
YES

---

## pg_stat_gssapi.pid

Type:
integer

Nullable:
YES

---

## pg_stat_progress_analyze.current_child_table_relid

Type:
oid

Nullable:
YES

---

## pg_stat_progress_analyze.datid

Type:
oid

Nullable:
YES

---

## pg_stat_progress_analyze.pid

Type:
integer

Nullable:
YES

---

## pg_stat_progress_analyze.relid

Type:
oid

Nullable:
YES

---

## pg_stat_progress_basebackup.pid

Type:
integer

Nullable:
YES

---

## pg_stat_progress_cluster.cluster_index_relid

Type:
oid

Nullable:
YES

---

## pg_stat_progress_cluster.datid

Type:
oid

Nullable:
YES

---

## pg_stat_progress_cluster.pid

Type:
integer

Nullable:
YES

---

## pg_stat_progress_cluster.relid

Type:
oid

Nullable:
YES

---

## pg_stat_progress_copy.datid

Type:
oid

Nullable:
YES

---

## pg_stat_progress_copy.pid

Type:
integer

Nullable:
YES

---

## pg_stat_progress_copy.relid

Type:
oid

Nullable:
YES

---

## pg_stat_progress_create_index.current_locker_pid

Type:
bigint

Nullable:
YES

---

## pg_stat_progress_create_index.datid

Type:
oid

Nullable:
YES

---

## pg_stat_progress_create_index.index_relid

Type:
oid

Nullable:
YES

---

## pg_stat_progress_create_index.pid

Type:
integer

Nullable:
YES

---

## pg_stat_progress_create_index.relid

Type:
oid

Nullable:
YES

---

## pg_stat_progress_vacuum.datid

Type:
oid

Nullable:
YES

---

## pg_stat_progress_vacuum.num_dead_item_ids

Type:
bigint

Nullable:
YES

---

## pg_stat_progress_vacuum.pid

Type:
integer

Nullable:
YES

---

## pg_stat_progress_vacuum.relid

Type:
oid

Nullable:
YES

---

## pg_stat_replication.pid

Type:
integer

Nullable:
YES

---

## pg_stat_replication.usesysid

Type:
oid

Nullable:
YES

---

## pg_stat_ssl.pid

Type:
integer

Nullable:
YES

---

## pg_stat_subscription.leader_pid

Type:
integer

Nullable:
YES

---

## pg_stat_subscription.pid

Type:
integer

Nullable:
YES

---

## pg_stat_subscription.relid

Type:
oid

Nullable:
YES

---

## pg_stat_subscription.subid

Type:
oid

Nullable:
YES

---

## pg_stat_subscription_stats.subid

Type:
oid

Nullable:
YES

---

## pg_stat_sys_indexes.idx_scan

Type:
bigint

Nullable:
YES

---

## pg_stat_sys_indexes.idx_tup_fetch

Type:
bigint

Nullable:
YES

---

## pg_stat_sys_indexes.idx_tup_read

Type:
bigint

Nullable:
YES

---

## pg_stat_sys_indexes.indexrelid

Type:
oid

Nullable:
YES

---

## pg_stat_sys_indexes.last_idx_scan

Type:
timestamp with time zone

Nullable:
YES

---

## pg_stat_sys_indexes.relid

Type:
oid

Nullable:
YES

---

## pg_stat_sys_tables.idx_scan

Type:
bigint

Nullable:
YES

---

## pg_stat_sys_tables.idx_tup_fetch

Type:
bigint

Nullable:
YES

---

## pg_stat_sys_tables.last_idx_scan

Type:
timestamp with time zone

Nullable:
YES

---

## pg_stat_sys_tables.relid

Type:
oid

Nullable:
YES

---

## pg_stat_user_functions.funcid

Type:
oid

Nullable:
YES

---

## pg_stat_user_indexes.idx_scan

Type:
bigint

Nullable:
YES

---

## pg_stat_user_indexes.idx_tup_fetch

Type:
bigint

Nullable:
YES

---

## pg_stat_user_indexes.idx_tup_read

Type:
bigint

Nullable:
YES

---

## pg_stat_user_indexes.indexrelid

Type:
oid

Nullable:
YES

---

## pg_stat_user_indexes.last_idx_scan

Type:
timestamp with time zone

Nullable:
YES

---

## pg_stat_user_indexes.relid

Type:
oid

Nullable:
YES

---

## pg_stat_user_tables.idx_scan

Type:
bigint

Nullable:
YES

---

## pg_stat_user_tables.idx_tup_fetch

Type:
bigint

Nullable:
YES

---

## pg_stat_user_tables.last_idx_scan

Type:
timestamp with time zone

Nullable:
YES

---

## pg_stat_user_tables.relid

Type:
oid

Nullable:
YES

---

## pg_stat_wal_receiver.pid

Type:
integer

Nullable:
YES

---

## pg_stat_xact_all_tables.idx_scan

Type:
bigint

Nullable:
YES

---

## pg_stat_xact_all_tables.idx_tup_fetch

Type:
bigint

Nullable:
YES

---

## pg_stat_xact_all_tables.relid

Type:
oid

Nullable:
YES

---

## pg_stat_xact_sys_tables.idx_scan

Type:
bigint

Nullable:
YES

---

## pg_stat_xact_sys_tables.idx_tup_fetch

Type:
bigint

Nullable:
YES

---

## pg_stat_xact_sys_tables.relid

Type:
oid

Nullable:
YES

---

## pg_stat_xact_user_functions.funcid

Type:
oid

Nullable:
YES

---

## pg_stat_xact_user_tables.idx_scan

Type:
bigint

Nullable:
YES

---

## pg_stat_xact_user_tables.idx_tup_fetch

Type:
bigint

Nullable:
YES

---

## pg_stat_xact_user_tables.relid

Type:
oid

Nullable:
YES

---

## pg_statio_all_indexes.idx_blks_hit

Type:
bigint

Nullable:
YES

---

## pg_statio_all_indexes.idx_blks_read

Type:
bigint

Nullable:
YES

---

## pg_statio_all_indexes.indexrelid

Type:
oid

Nullable:
YES

---

## pg_statio_all_indexes.relid

Type:
oid

Nullable:
YES

---

## pg_statio_all_sequences.relid

Type:
oid

Nullable:
YES

---

## pg_statio_all_tables.idx_blks_hit

Type:
bigint

Nullable:
YES

---

## pg_statio_all_tables.idx_blks_read

Type:
bigint

Nullable:
YES

---

## pg_statio_all_tables.relid

Type:
oid

Nullable:
YES

---

## pg_statio_all_tables.tidx_blks_hit

Type:
bigint

Nullable:
YES

---

## pg_statio_all_tables.tidx_blks_read

Type:
bigint

Nullable:
YES

---

## pg_statio_sys_indexes.idx_blks_hit

Type:
bigint

Nullable:
YES

---

## pg_statio_sys_indexes.idx_blks_read

Type:
bigint

Nullable:
YES

---

## pg_statio_sys_indexes.indexrelid

Type:
oid

Nullable:
YES

---

## pg_statio_sys_indexes.relid

Type:
oid

Nullable:
YES

---

## pg_statio_sys_sequences.relid

Type:
oid

Nullable:
YES

---

## pg_statio_sys_tables.idx_blks_hit

Type:
bigint

Nullable:
YES

---

## pg_statio_sys_tables.idx_blks_read

Type:
bigint

Nullable:
YES

---

## pg_statio_sys_tables.relid

Type:
oid

Nullable:
YES

---

## pg_statio_sys_tables.tidx_blks_hit

Type:
bigint

Nullable:
YES

---

## pg_statio_sys_tables.tidx_blks_read

Type:
bigint

Nullable:
YES

---

## pg_statio_user_indexes.idx_blks_hit

Type:
bigint

Nullable:
YES

---

## pg_statio_user_indexes.idx_blks_read

Type:
bigint

Nullable:
YES

---

## pg_statio_user_indexes.indexrelid

Type:
oid

Nullable:
YES

---

## pg_statio_user_indexes.relid

Type:
oid

Nullable:
YES

---

## pg_statio_user_sequences.relid

Type:
oid

Nullable:
YES

---

## pg_statio_user_tables.idx_blks_hit

Type:
bigint

Nullable:
YES

---

## pg_statio_user_tables.idx_blks_read

Type:
bigint

Nullable:
YES

---

## pg_statio_user_tables.relid

Type:
oid

Nullable:
YES

---

## pg_statio_user_tables.tidx_blks_hit

Type:
bigint

Nullable:
YES

---

## pg_statio_user_tables.tidx_blks_read

Type:
bigint

Nullable:
YES

---

## pg_statistic.starelid

Type:
oid

Nullable:
NO

---

## pg_statistic.stawidth

Type:
integer

Nullable:
NO

---

## pg_statistic_ext.oid

Type:
oid

Nullable:
NO

---

## pg_statistic_ext.stxrelid

Type:
oid

Nullable:
NO

---

## pg_statistic_ext_data.stxoid

Type:
oid

Nullable:
NO

---

## pg_stats.avg_width

Type:
integer

Nullable:
YES

---

## pg_stats_ext_exprs.avg_width

Type:
integer

Nullable:
YES

---

## pg_subscription.oid

Type:
oid

Nullable:
NO

---

## pg_subscription.subdbid

Type:
oid

Nullable:
NO

---

## pg_subscription_rel.srrelid

Type:
oid

Nullable:
NO

---

## pg_subscription_rel.srsubid

Type:
oid

Nullable:
NO

---

## pg_tablespace.oid

Type:
oid

Nullable:
NO

---

## pg_transform.oid

Type:
oid

Nullable:
NO

---

## pg_trigger.oid

Type:
oid

Nullable:
NO

---

## pg_trigger.tgconstrindid

Type:
oid

Nullable:
NO

---

## pg_trigger.tgconstrrelid

Type:
oid

Nullable:
NO

---

## pg_trigger.tgfoid

Type:
oid

Nullable:
NO

---

## pg_trigger.tgparentid

Type:
oid

Nullable:
NO

---

## pg_trigger.tgrelid

Type:
oid

Nullable:
NO

---

## pg_ts_config.oid

Type:
oid

Nullable:
NO

---

## pg_ts_dict.oid

Type:
oid

Nullable:
NO

---

## pg_ts_parser.oid

Type:
oid

Nullable:
NO

---

## pg_ts_template.oid

Type:
oid

Nullable:
NO

---

## pg_type.oid

Type:
oid

Nullable:
NO

---

## pg_type.typrelid

Type:
oid

Nullable:
NO

---

## pg_user.usesysid

Type:
oid

Nullable:
YES

---

## pg_user_mapping.oid

Type:
oid

Nullable:
NO

---

## pg_user_mappings.srvid

Type:
oid

Nullable:
YES

---

## pg_user_mappings.umid

Type:
oid

Nullable:
YES

---

## role_permissions.id

Type:
bigint

Nullable:
NO

---

## role_permissions.permission_id

Type:
bigint

Nullable:
NO

---

## role_permissions.role_id

Type:
bigint

Nullable:
NO

---

## roles.id

Type:
bigint

Nullable:
NO

---

## routines.dtd_identifier

Type:
name

Nullable:
YES

---

## routines.result_cast_dtd_identifier

Type:
name

Nullable:
YES

---

## security_event_logs.id

Type:
bigint

Nullable:
NO

---

## security_event_logs.user_id

Type:
bigint

Nullable:
YES

---

## sessions.device_id

Type:
character varying

Nullable:
YES

---

## sessions.id

Type:
bigint

Nullable:
NO

---

## sessions.session_id

Type:
character varying

Nullable:
NO

---

## sessions.user_id

Type:
bigint

Nullable:
NO

---

## sql_features.feature_id

Type:
character varying

Nullable:
YES

---

## sql_features.sub_feature_id

Type:
character varying

Nullable:
YES

---

## sql_implementation_info.implementation_info_id

Type:
character varying

Nullable:
YES

---

## sql_parts.feature_id

Type:
character varying

Nullable:
YES

---

## sql_sizing.sizing_id

Type:
integer

Nullable:
YES

---

## system_configurations.id

Type:
bigint

Nullable:
NO

---

## system_settings.id

Type:
bigint

Nullable:
NO

---

## transactions.account_id

Type:
uuid

Nullable:
YES

---

## transactions.client_request_id

Type:
character varying

Nullable:
NO

---

## transactions.id

Type:
uuid

Nullable:
NO

---

## transactions.payment_provider

Type:
character varying

Nullable:
YES

---

## transactions.recipient_user_id

Type:
bigint

Nullable:
YES

---

## transactions.user_id

Type:
bigint

Nullable:
YES

---

## transport_booking_payments.booking_id

Type:
bigint

Nullable:
NO

---

## transport_booking_payments.gateway_transaction_id

Type:
character varying

Nullable:
YES

---

## transport_booking_payments.id

Type:
bigint

Nullable:
NO

---

## transport_booking_payments.tenant_id

Type:
character varying

Nullable:
NO

---

## transport_bookings.assigned_driver_id

Type:
bigint

Nullable:
YES

---

## transport_bookings.assigned_route_id

Type:
bigint

Nullable:
YES

---

## transport_bookings.assigned_vehicle_id

Type:
bigint

Nullable:
YES

---

## transport_bookings.event_id

Type:
bigint

Nullable:
YES

---

## transport_bookings.event_participation_id

Type:
bigint

Nullable:
YES

---

## transport_bookings.external_booking_id

Type:
character varying

Nullable:
YES

---

## transport_bookings.fallback_provider

Type:
jsonb

Nullable:
YES

---

## transport_bookings.group_booking_id

Type:
character varying

Nullable:
YES

---

## transport_bookings.group_leader_id

Type:
bigint

Nullable:
YES

---

## transport_bookings.id

Type:
bigint

Nullable:
NO

---

## transport_bookings.insurance_provider

Type:
character varying

Nullable:
YES

---

## transport_bookings.original_provider_id

Type:
bigint

Nullable:
YES

---

## transport_bookings.original_provider_type

Type:
character varying

Nullable:
YES

---

## transport_bookings.provider_id

Type:
bigint

Nullable:
YES

---

## transport_bookings.provider_type

Type:
USER-DEFINED

Nullable:
NO

---

## transport_bookings.tenant_id

Type:
character varying

Nullable:
NO

---

## transport_bookings.user_id

Type:
bigint

Nullable:
NO

---

## transport_bookings.wallet_transaction_id

Type:
character varying

Nullable:
YES

---

## transport_contingency_plans.backup_provider_ids

Type:
jsonb

Nullable:
YES

---

## transport_contingency_plans.id

Type:
bigint

Nullable:
NO

---

## transport_contingency_plans.provider_id

Type:
bigint

Nullable:
NO

---

## transport_contingency_plans.provider_type

Type:
character varying

Nullable:
NO

---

## transport_contingency_plans.tenant_id

Type:
character varying

Nullable:
NO

---

## transport_demand_forecasts.confidence_interval_lower

Type:
integer

Nullable:
YES

---

## transport_demand_forecasts.confidence_interval_upper

Type:
integer

Nullable:
YES

---

## transport_demand_forecasts.confidence_score

Type:
integer

Nullable:
NO

---

## transport_demand_forecasts.id

Type:
bigint

Nullable:
NO

---

## transport_demand_forecasts.is_validated

Type:
boolean

Nullable:
YES

---

## transport_demand_forecasts.tenant_id

Type:
character varying

Nullable:
NO

---

## transport_demand_forecasts.valid_until

Type:
timestamp with time zone

Nullable:
NO

---

## transport_demand_forecasts.validated_at

Type:
timestamp with time zone

Nullable:
YES

---

## transport_incidents.booking_id

Type:
bigint

Nullable:
YES

---

## transport_incidents.driver_id

Type:
bigint

Nullable:
YES

---

## transport_incidents.id

Type:
bigint

Nullable:
NO

---

## transport_incidents.incident_category

Type:
character varying

Nullable:
YES

---

## transport_incidents.incident_reference

Type:
character varying

Nullable:
NO

---

## transport_incidents.incident_type

Type:
character varying

Nullable:
NO

---

## transport_incidents.reported_by_id

Type:
bigint

Nullable:
YES

---

## transport_incidents.tenant_id

Type:
character varying

Nullable:
NO

---

## transport_incidents.user_id

Type:
bigint

Nullable:
YES

---

## transport_incidents.vehicle_id

Type:
bigint

Nullable:
YES

---

## transport_incidents.videos

Type:
jsonb

Nullable:
YES

---

## transport_ratings.booking_id

Type:
bigint

Nullable:
NO

---

## transport_ratings.id

Type:
bigint

Nullable:
NO

---

## transport_ratings.provider_id

Type:
bigint

Nullable:
NO

---

## transport_ratings.provider_type

Type:
character varying

Nullable:
NO

---

## transport_ratings.safety_incident_type

Type:
character varying

Nullable:
YES

---

## transport_ratings.tenant_id

Type:
character varying

Nullable:
NO

---

## transport_ratings.user_id

Type:
bigint

Nullable:
NO

---

## transport_scheduled_routes.current_driver_id

Type:
bigint

Nullable:
YES

---

## transport_scheduled_routes.current_vehicle_id

Type:
bigint

Nullable:
YES

---

## transport_scheduled_routes.id

Type:
bigint

Nullable:
NO

---

## transport_scheduled_routes.provider_id

Type:
bigint

Nullable:
NO

---

## transport_scheduled_routes.provider_type

Type:
character varying

Nullable:
NO

---

## transport_scheduled_routes.tenant_id

Type:
character varying

Nullable:
NO

---

## transport_settings.can_be_overridden_env

Type:
boolean

Nullable:
YES

---

## transport_settings.id

Type:
bigint

Nullable:
NO

---

## transport_settings.tenant_id

Type:
character varying

Nullable:
NO

---

## transport_settings.validation_rules

Type:
jsonb

Nullable:
YES

---

## transport_vehicles.current_booking_id

Type:
bigint

Nullable:
YES

---

## transport_vehicles.id

Type:
bigint

Nullable:
NO

---

## transport_vehicles.insurance_provider

Type:
character varying

Nullable:
YES

---

## transport_vehicles.owner_id

Type:
bigint

Nullable:
NO

---

## transport_vehicles.tenant_id

Type:
character varying

Nullable:
NO

---

## transport_vehicles.tracking_device_id

Type:
character varying

Nullable:
YES

---

## user_dashboard_configs.id

Type:
bigint

Nullable:
NO

---

## user_dashboard_configs.user_id

Type:
bigint

Nullable:
NO

---

## user_dashboard_contexts.id

Type:
bigint

Nullable:
NO

---

## user_dashboard_contexts.user_id

Type:
bigint

Nullable:
NO

---

## user_defined_types.ref_dtd_identifier

Type:
name

Nullable:
YES

---

## user_defined_types.source_dtd_identifier

Type:
name

Nullable:
YES

---

## user_mapping_options.authorization_identifier

Type:
name

Nullable:
YES

---

## user_mappings.authorization_identifier

Type:
name

Nullable:
YES

---

## user_profile_audit.attempted_by_user_id

Type:
bigint

Nullable:
YES

---

## user_profile_audit.id

Type:
bigint

Nullable:
NO

---

## user_profile_audit.user_profile_id

Type:
bigint

Nullable:
NO

---

## user_profiles.id

Type:
bigint

Nullable:
NO

---

## user_profiles.id_document_mime

Type:
character varying

Nullable:
YES

---

## user_profiles.id_document_size

Type:
integer

Nullable:
YES

---

## user_profiles.id_document_url

Type:
character varying

Nullable:
YES

---

## user_profiles.id_number

Type:
character varying

Nullable:
YES

---

## user_profiles.id_type

Type:
USER-DEFINED

Nullable:
YES

---

## user_profiles.user_id

Type:
character varying

Nullable:
NO

---

## user_roles.id

Type:
bigint

Nullable:
NO

---

## user_roles.role_id

Type:
bigint

Nullable:
NO

---

## user_roles.user_id

Type:
bigint

Nullable:
NO

---

## user_theme_preferences.id

Type:
bigint

Nullable:
NO

---

## user_theme_preferences.user_id

Type:
bigint

Nullable:
NO

---

## users.default_org_id

Type:
bigint

Nullable:
YES

---

## users.id

Type:
bigint

Nullable:
NO

---

## users.public_id

Type:
character varying

Nullable:
NO

---

## wallet_audit_logs.actor_id

Type:
bigint

Nullable:
YES

---

## wallet_audit_logs.id

Type:
uuid

Nullable:
NO

---

## wallet_audit_logs.request_id

Type:
character varying

Nullable:
YES

---

## wallet_audit_logs.transaction_id

Type:
uuid

Nullable:
YES

---

## wallet_system_configs.id

Type:
bigint

Nullable:
NO

---

## webhook_events.id

Type:
bigint

Nullable:
NO

---

## webhook_events.provider

Type:
character varying

Nullable:
NO

---
