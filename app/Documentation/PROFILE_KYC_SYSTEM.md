# Profile and KYC System Documentation

## Page Types and Differences

### 1. Account Page (`/account`)
**URL**: `http://localhost:5000/account`

**Purpose**: Private dashboard for the current user to manage their account and view their overall status.

**Audience**: Only the logged-in user (private).

**Features**:
- Wallet balance and transaction limits
- KYC tier and verification progress
- Profile completion percentage with link to edit
- Quick action cards (Wallet, Bookings, Trips, Settings)
- Role-specific sections (Driver, Host, Admin)
- Account limits (daily, monthly, per-transaction)
- Links to edit profile and view public profile

**Key Difference**: This is the user's private dashboard showing account-level information, financial data, and settings. It's where users go to manage their account and see their overall status.

### 2. Profile Edit Page (`/profile/edit`)
**URL**: `http://localhost:5000/profile/edit`

**Purpose**: Form for editing personal profile information.

**Audience**: Only the logged-in user (private).

**Features**:
- Edit personal information (name, DOB, gender, nationality)
- Edit contact information (email, phone)
- Edit address information (address, city, country)
- Profile completion progress bar
- Field locking for verified accounts (immutable fields disabled)
- Tips for completing profile
- Verification status warnings

**Key Difference**: This is specifically for editing profile data. It has field locking after KYC verification to prevent identity fraud. It's a functional form, not a display page.

### 3. Public Profile Page (`/profile/<public_id>`)
**URL**: `http://localhost:5000/profile/720ace2b-1d5e-40a7-87d5-c984ad47c000`

**Purpose**: Public view of a user's profile information.

**Audience**: Anyone who has the profile URL (public).

**Features**:
- Profile avatar and cover photo
- Full name and username
- Location (city, country)
- Verification badge
- Bio/personal description
- KYC verification status
- Personal information (DOB, gender, nationality, email, phone)
- Stats (events, reviews, stays, trips)
- Role badges (owner, admin, driver, host)
- Badges and achievements
- Recent activity feed
- Profile completion (only visible to profile owner)
- Edit buttons (only visible to profile owner)

**Key Difference**: This is a public-facing profile that others can view. It shows limited personal information (no sensitive data). The profile owner sees additional options to edit their profile. It's designed to showcase a user's identity and activity on the platform.

### 4. Fan Dashboard (`/fan/dashboard`)
**URL**: `http://localhost:5000/fan/dashboard`

**Purpose**: Dashboard for fans to manage their fan-related activities.

**Audience**: Users with fan role.

**Features**:
- Fan-specific content and activities
- Events they're attending
- Fan engagement metrics
- Fan community features

**Key Difference**: This is role-specific for fans, focusing on fan activities rather than general account management or profile display.

## Navigation Flow

```
User logs in
    ↓
Account Page (/account) - Main dashboard
    ↓
    ├─→ Edit Profile (/profile/edit) - Update personal info
    ├─→ Public Profile (/profile/<id>) - View own profile
    ├─→ Fan Dashboard (/fan/dashboard) - If fan role
    └─→ Other role-specific dashboards
```

## Summary

| Page | URL | Privacy | Purpose | Key Features |
|------|-----|---------|---------|--------------|
| Account | `/account` | Private | Account management | Wallet, KYC, limits, quick actions |
| Profile Edit | `/profile/edit` | Private | Edit profile data | Form with field locking, completion tips |
| Public Profile | `/profile/<id>` | Public | Display profile | Avatar, stats, activity, roles |
| Fan Dashboard | `/fan/dashboard` | Private | Fan activities | Fan-specific features |

## Overview

The profile system separates user authentication (User model) from personal identity information (UserProfile model). This architecture enforces immutability after KYC verification to prevent identity fraud and account selling.

## Data Structure

### UserProfile Model
Located in `app/profile/models.py`

**Core Fields:**
- `user_id` (String, FK to users.public_id) - Links to authentication
- `full_name` (String, NOT NULL) - Legal full name
- `date_of_birth` (Date) - Date of birth
- `gender` (Enum: male/female/other/unspecified) - Gender
- `nationality` (String) - Nationality
- `address` (String) - Street address
- `city` (String) - City
- `country` (String) - Country
- `phone_number` (String) - Phone with country code
- `email` (String) - Email address

**Identity Documents:**
- `id_type` (Enum: passport/national_id/driver_license/other)
- `id_number` (String) - ID number
- `id_document_url` (String) - Document storage URL
- `id_document_mime` (String) - MIME type
- `id_document_size` (Integer) - Size in bytes

**Verification Status:**
- `verification_status` (Enum: pending/verified/rejected/suspended)
- `kyc_level` (Enum: basic/enhanced/government)
- `email_verified` (Boolean)
- `phone_verified` (Boolean)
- `profile_completed` (Boolean)

## Immutability After Verification

### Immutable Fields
The following fields CANNOT be changed after verification_status = "verified":
- `full_name`
- `date_of_birth`
- `gender`
- `nationality`
- `id_type`
- `id_number`
- `id_document_url`
- `id_document_mime`
- `id_document_size`

### Enforcement Mechanism

1. **Database-Level Event Listener** (`app/profile/models.py:300-331`)
   - SQLAlchemy `before_update` event listener
   - Checks for changes to immutable fields when verification_status = "verified"
   - Automatically raises ValueError if change attempted
   - Logs to UserProfileAudit table
   - Logs to ForensicAuditService

2. **Application-Level Validation** (`app/profile/routes.py:314-412`)
   - `edit_profile()` route checks verification status before updates
   - Explicitly prevents changes to immutable fields for verified users
   - Provides user-friendly error messages
   - Logs blocked attempts to forensic audit

3. **UI-Level Locking** (`templates/profile/edit.html`)
   - Fields marked `readonly` or `disabled` when `is_verified = True`
   - Visual indicators (gray background, lock badge)
   - Warning message displayed for verified accounts

## Mutable Fields

These fields CAN always be changed:
- `address`
- `city`
- `country`
- `phone_number`
- `email` (requires re-verification if changed)

## Profile Completion Calculation

### Method: `get_completion_percentage()`
Located in `app/profile/models.py:154-180`

**Calculation:**
- Email verified: 20%
- Phone verified: 20%
- Full name: 20%
- Address: 20%
- City: 10%
- Country: 10%

**Total: 100%**

### Completion Flag
The `profile_completed` flag is automatically set to `True` when completion reaches 100% and `False` when below 100%.

## Routes

### Profile Routes (`app/profile/routes.py`)

1. **GET /account** - `account_overview()`
   - Shows user account dashboard
   - Displays profile completion percentage
   - Shows KYC tier and progress
   - Links to edit profile if incomplete

2. **GET/POST /profile/edit** - `edit_profile()`
   - Edit profile form
   - Enforces field immutability based on verification status
   - Updates profile_completed flag automatically
   - Logs blocked changes for verified users

3. **GET /profile/<public_id>** - `view_profile()`
   - Public profile view
   - Shows limited information (no sensitive data)

4. **GET /profile/me** - `my_public_profile()`
   - Redirects to current user's public profile

## KYC Verification Flow

### Tier System (`app/auth/kyc_compliance.py`)

- **Tier 0**: Unregistered - No transactions
- **Tier 1**: Basic - Phone verified (1M UGX daily)
- **Tier 2**: Standard - National ID verified (10M UGX daily)
- **Tier 3**: Enhanced - Additional documents
- **Tier 4**: Premium - Full KYC
- **Tier 5**: Corporate - Business accounts

### Verification Routes (`app/kyc/routes.py`)

1. **GET/POST /kyc/verify/national-id** - NIRA verification
2. **GET/POST /kyc/verify/address** - Address verification
3. **GET /kyc/upgrade** - View available upgrades
4. **GET /kyc/limits** - View transaction limits

## Security Features

### Audit Logging

1. **UserProfileAudit Table** - Tracks attempted changes to immutable fields
2. **ForensicAuditService** - Logs security events including blocked changes
3. **Comprehensive Audit** - Logs all profile-related actions

### Fraud Prevention

1. **Immutability after verification** - Prevents identity switching
2. **Unique constraints** - Email and phone must be globally unique
3. **Watchlist checking** - National IDs checked against watchlists
4. **Re-verification required** - Email changes require re-verification

## Testing Checklist

- [ ] Profile creation for new users
- [ ] Profile editing for unverified users (all fields editable)
- [ ] Profile editing for verified users (only mutable fields editable)
- [ ] Profile completion percentage calculation
- [ ] Profile completion flag updates automatically
- [ ] Email change requires re-verification
- [ ] Attempted changes to immutable fields are logged
- [ ] Account overview displays correct completion percentage
- [ ] Links from account overview to edit profile work correctly
- [ ] Public profile view shows appropriate information
- [ ] KYC verification flow works end-to-end

## Common Issues

### Profile updates not saving
- Check if user is verified (immutable fields locked)
- Check database constraints (unique email/phone)
- Check form validation errors
- Review flash messages for specific errors

### Completion percentage not updating
- Ensure `get_completion_percentage()` is used consistently
- Check that profile_completed flag is being updated
- Verify email_verified and phone_verified flags are set

### Field locking not working
- Check verification_status is "verified"
- Ensure IMMUTABLE_AFTER_VERIFICATION set is correct
- Verify event listener is registered
- Check for database-level constraints

## Migration Notes

When migrating from old profile system:
1. Ensure all profiles have user_id pointing to public_id (not integer id)
2. Set default verification_status = "pending" for existing profiles
3. Recalculate profile completion percentages
4. Update profile_completed flags based on new calculation
5. Run audit to identify any existing violations
