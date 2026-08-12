"""Add database-level email format check constraint on users.

Defence in depth for account creation: the application layer
(``app/auth/email_validation.py``) performs full validation - syntax,
normalisation, disposable/role blocking and MX lookup - and the verified
signup flow (``app/auth/pending_registration.py``) only inserts a row after an
emailed OTP has been confirmed.

This constraint is the last line of defence, guaranteeing that no code path -
including data imports, admin tooling or future features - can persist a
structurally invalid or non-normalised email address.

The check enforces:
  * exactly one "@", with non-empty local and domain parts
  * no whitespace anywhere in the address
  * a dotted domain ending in an alphabetic TLD of at least 2 characters
  * the stored value is lowercase (matching normalize_email())

Revision ID: a7c3e91b4d28
Revises: 6e1eea37b83b
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a7c3e91b4d28'
down_revision = '6e1eea37b83b'
branch_labels = None
depends_on = None


# POSIX regex: no spaces/@ in local part, dotted domain, alphabetic TLD >= 2.
_EMAIL_REGEX = r'^[^@[:space:]]+@[^@[:space:]]+\.[A-Za-z]{2,}$'

_CHECK_NAME = 'ck_users_email_format'


def upgrade():
    bind = op.get_bind()

    if bind.dialect.name != 'postgresql':
        # The POSIX-regex syntax below is PostgreSQL-specific. On other
        # backends the application-level validation still applies.
        return

    # Normalise any legacy rows so the constraint can be applied cleanly.
    op.execute(
        "UPDATE users SET email = lower(btrim(email)) "
        "WHERE email IS NOT NULL AND email <> lower(btrim(email))"
    )

    # Only add the constraint if every existing row satisfies it; otherwise
    # surface a clear error instead of a cryptic constraint violation.
    invalid = bind.execute(
        sa.text(
            "SELECT count(*) FROM users "
            "WHERE email IS NULL OR email !~ :pattern"
        ),
        {"pattern": _EMAIL_REGEX},
    ).scalar()

    if invalid:
        raise RuntimeError(
            f"Cannot add {_CHECK_NAME}: {invalid} existing user row(s) have an "
            "invalid email address. Clean these up before running this migration:\n"
            "  SELECT id, email FROM users WHERE email IS NULL OR email !~ "
            f"'{_EMAIL_REGEX}';"
        )

    op.create_check_constraint(
        _CHECK_NAME,
        'users',
        sa.text(f"email ~ '{_EMAIL_REGEX}' AND email = lower(email)"),
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    op.drop_constraint(_CHECK_NAME, 'users', type_='check')
