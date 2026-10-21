# Isolated H3 candidate migration path

This directory is deliberately outside the active application migration path at migrations/versions.

- The candidate builder reads only the approved local disposable H2-prime replay database.
- It produces a static SQL-backed migration under versions/.
- The isolated env.py accepts only loopback PostgreSQL and a database name matching afcon360_h3_candidate*_test.
- Before Alembic runs, the environment verifies that the target contains no application relations, custom types, routines, extensions, or extra schemas.
- It does not create, drop, truncate, or reset a database.
- It imports no AFCON360 application models and does not use metadata.create_all().
- It excludes public.alembic_version from the dump; Alembic owns the candidate database's version table.

The candidate does not replace the active migration chain. Do not move it into migrations/versions, retire existing revision files, stamp, upgrade, or cut over any protected database until the owner-approved H3-B gates pass.
