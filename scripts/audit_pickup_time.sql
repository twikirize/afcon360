BEGIN READ ONLY;

SELECT 'DB=' || current_database();
SELECT 'REV=' || version_num FROM alembic_version;

SELECT 'COL=' || column_name
       || ' nullable=' || is_nullable
       || ' type=' || data_type
FROM information_schema.columns
WHERE table_name = 'transport_bookings'
  AND column_name IN ('pickup_time', 'pickup_mode', 'request_received_at')
ORDER BY column_name;

SELECT 'CHECK=' || conname
       || ' | ' || pg_get_constraintdef(oid)
       || ' | valid=' || convalidated
FROM pg_constraint
WHERE conrelid = 'transport_bookings'::regclass
  AND contype = 'c'
ORDER BY conname;

SELECT 'COUNTS'
       || ' instant_total='   || count(*) FILTER (WHERE pickup_mode = 'instant')::text
       || ' instant_null='    || count(*) FILTER (WHERE pickup_mode = 'instant'   AND pickup_time IS NULL)::text
       || ' scheduled_total=' || count(*) FILTER (WHERE pickup_mode = 'scheduled')::text
       || ' scheduled_null='  || count(*) FILTER (WHERE pickup_mode = 'scheduled' AND pickup_time IS NULL)::text
FROM transport_bookings;

ROLLBACK;