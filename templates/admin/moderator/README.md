# Moderator System Documentation

## Overview

The AFCON360 Moderator System provides a comprehensive content moderation interface for managing user submissions, flags, users, organisations, events, KYC verifications, and escalations. The system is built with Flask/Jinja2 templates and follows a consistent design system.

## Design System

The moderator interface uses a light theme design system defined in `base_moderator.html`:

### Color Palette
- `--ink`: #0a0a0f (primary text)
- `--ink-2`: #1a1a2e (secondary text)
- `--surface`: #ffffff (background)
- `--bg`: #f8f9fa (panel background)
- `--border`: #e5e7eb (borders)
- `--accent`: #6366f1 (primary accent)
- `--accent-lt`: #e0e7ff (accent light)
- `--accent-dk`: #4338ca (accent dark)
- `--green`: #10b981 (success)
- `--green-lt`: #d1fae5 (success light)
- `--red`: #ef4444 (error)
- `--red-lt`: #fee2e2 (error light)
- `--orange`: #f97316 (warning)
- `--orange-lt`: #ffedd5 (warning light)
- `--purple`: #8b5cf6 (info)
- `--purple-lt`: #ede9fe (info light)
- `--blue`: #3b82f6 (info)
- `--blue-lt`: #dbeafe (info light)

### Typography
- Font Display: Bricolage Grotesque (headings)
- Font Body: Lato (body text)
- Font Mono: JetBrains Mono (code/IDs)

### Components
- **Badges**: Status indicators with color-coded backgrounds
- **Buttons**: Primary, outline, ghost, and danger variants
- **Panels**: Card containers with headers and bodies
- **Tables**: Data tables with pagination
- **Forms**: Input fields, selects, and textareas
- **Pagination**: Page navigation with prev/next controls

## Template Structure

### Base Template
- `base_moderator.html`: Base template providing consistent layout, navigation, and styling for all moderator pages.

### Dashboard
- `dashboard.html`: Main dashboard with moderation queue statistics, critical flag banner, and activity metrics.

### Content Moderation
- `content.html`: List view of content submissions with filtering, sorting, and bulk actions.
- `view_submission.html`: Detailed view of a single submission with approval/rejection workflow and SLA indicators.

### Flag Management
- `flagged.html`: List view of flagged content with priority filters and status tabs.
- `view_flag.html`: Detailed view of a flag with resolution workflow and escalation options.

### User Management
- `users.html`: List view of users with verification and activity filters.
- `view_user.html`: Detailed view of a user with verification, suspension, and activation actions.

### Event Moderation
- `events.html`: List view of events for moderation.
- `view_event.html`: Detailed view of an event with approval/rejection workflow.

### Organisation Management
- `orgs.html`: List view of organisations with verification status.
- `view_org.html`: Detailed view of an organisation with verification and compliance referral actions.

### KYC Verification
- `kyc.html`: List view of KYC submissions with status filters.
- `view_kyc.html`: Detailed view of a KYC submission with document review and approval workflow.

### Escalations
- `escalations.html`: List view of escalated items requiring admin+ attention.

## Key Features

### SLA Tracking
- SLA due dates are tracked for content submissions and flags
- Visual indicators show overdue (red), urgent (<4 hours, orange), and normal (blue) status
- SLA banners appear prominently on detail pages

### Moderation Notes
- Internal moderation notes are separate from user-facing notes
- Notes are stored in `moderation_notes` field on entities
- Notes are only visible to moderators

### Role-Based Access
- Different actions available based on user roles (moderator, admin, super_admin, owner)
- Escalation features are restricted to admin+ roles
- Compliance referral requires appropriate permissions

### Bulk Actions
- Content submissions support bulk approve, request changes, and reject
- Checkboxes enable multi-select operations
- Confirmation dialogs prevent accidental bulk actions

### Priority-Based Styling
- Critical flags have red row highlighting
- High priority flags have orange row highlighting
- Medium priority flags have accent row highlighting

## Navigation

### Sidebar Navigation
The moderator sidebar includes links to:
- Dashboard
- Content Submissions
- Flagged Content
- Users
- Events
- Organisations
- KYC Verification
- Escalations

### Breadcrumbs
All pages include breadcrumb navigation showing the path from Dashboard to the current page.

## Common Patterns

### List View Pattern
1. Breadcrumbs
2. Heading row with title and description
3. Status/filter tabs with counts
4. Search/filter row with inputs
5. Data panel with table
6. Pagination controls
7. Empty state when no results

### Detail View Pattern
1. Breadcrumbs
2. SLA indicator banner (if applicable)
3. Heading row with ID, name, and status badges
4. Two-column layout (8:4 ratio on desktop)
5. Left column: Entity details, related information, moderation notes
6. Right column: Sticky action panel with decision forms
7. Collapsed state for already-reviewed items

### Action Panel Pattern
- Sticky positioning (top: 76px)
- Claim button for unassigned items
- Approve/reject forms with notes fields
- Escalation button for admin+ users
- Internal moderation notes field
- Confirmation dialogs for destructive actions

## Routing

### Content Routes
- `/admin/moderator/content/` - List content submissions
- `/admin/moderator/content/<id>` - View submission details
- `/admin/moderator/content/<id>/claim` - Claim assignment
- `/admin/moderator/content/<id>/approve` - Approve submission
- `/admin/moderator/content/<id>/request-changes` - Request changes
- `/admin/moderator/content/<id>/reject` - Reject submission
- `/admin/moderator/content/<id>/flag` - Flag content

### Flag Routes
- `/admin/moderator/flags/` - List flagged content
- `/admin/moderator/flags/<id>` - View flag details
- `/admin/moderator/flags/<id>/claim` - Claim flag
- `/admin/moderator/flags/<id>/resolve` - Resolve flag
- `/admin/moderator/flags/<id>/reject` - Reject flag
- `/admin/moderator/flags/<id>/escalate` - Escalate to admin
- `/admin/moderator/flags/<id>/notes` - Update moderation notes

### User Routes
- `/admin/moderator/users/` - List users
- `/admin/moderator/users/<id>` - View user details
- `/admin/moderator/users/<id>/approve-verification` - Approve verification
- `/admin/moderator/users/<id>/reject-verification` - Reject verification
- `/admin/moderator/users/<id>/suspend` - Suspend user
- `/admin/moderator/users/<id>/activate` - Activate user
- `/admin/moderator/users/<id>/notes` - Update moderation notes

### Organisation Routes
- `/admin/moderator/orgs/` - List organisations
- `/admin/moderator/orgs/<id>` - View organisation details
- `/admin/moderator/orgs/<id>/verify` - Verify organisation
- `/admin/moderator/orgs/<id>/refer-compliance` - Refer for compliance

### Event Routes
- `/admin/moderator/events/` - List events
- `/admin/moderator/events/<id>` - View event details
- `/admin/moderator/events/<id>/approve` - Approve event
- `/admin/moderator/events/<id>/reject` - Reject event

### KYC Routes
- `/admin/moderator/kyc/` - List KYC submissions
- `/admin/moderator/kyc/<id>` - View KYC details
- `/admin/moderator/kyc/<id>/approve` - Approve KYC
- `/admin/moderator/kyc/<id>/reject` - Reject KYC

### Escalation Routes
- `/admin/moderator/escalations/` - List escalations
- `/admin/moderator/escalations/<id>` - View escalation details
- `/admin/moderator/escalations/<id>/resolve` - Resolve escalation

## Status Values

### Content Submission Statuses
- `pending`: Awaiting moderation
- `changes_requested`: Requires user updates
- `approved`: Published
- `rejected`: Declined

### Flag Statuses
- `open`: Flag created, awaiting review
- `in_review`: Being reviewed by moderator
- `resolved`: Flag addressed
- `rejected`: Flag marked as invalid

### Flag Priorities
- `critical`: Immediate attention required
- `high`: Urgent
- `medium`: Normal priority
- `low`: Low priority
- `normal`: Default priority

### User Statuses
- `active`: Account active
- `inactive`: Account suspended

### Verification Statuses
- `verified`: Identity confirmed
- `unverified`: Awaiting verification

## Database Schema Changes

### SLA Fields
- `sla_due_at` timestamp added to `ContentSubmission` and `ContentFlag` models
- Calculated based on priority level at creation time

### Moderation Notes
- `moderation_notes` text field added to relevant entity models
- Separate from user-facing notes fields
- Internal-only visibility

## Best Practices

### When Reviewing Content
1. Check SLA status - prioritize overdue and urgent items first
2. Review content against community guidelines
3. Use moderation notes for internal context
4. Provide clear feedback to users when requesting changes
5. Assign to appropriate moderator if needed

### When Handling Flags
1. Critical flags require immediate attention
2. Review flagged entity in context
3. Document decisions with clear notes
4. Escalate complex cases to admin+
5. Mark invalid flags as rejected with reason

### When Verifying Users
1. Verify identity documents carefully
2. Check for document tampering
3. Cross-reference with other account data
4. Provide clear rejection reasons
5. Suspend accounts with clear justification

### When Managing Organisations
1. Verify business registration documents
2. Check contact information validity
3. Review member accounts
4. Refer to compliance for regulatory issues
5. Maintain audit trail

## Troubleshooting

### Common Issues
- **SLA indicators not showing**: Ensure `sla_due_at` field is populated and `now()` function is available in template context
- **Bulk actions not working**: Check JavaScript is loaded and form CSRF tokens are valid
- **Missing moderation notes**: Verify database migration for `moderation_notes` field has been run
- **Escalation button not appearing**: Check user has admin+ role and escalation route is defined

### Template Errors
- **"Undefined variable"**: Ensure all required variables are passed from route to template
- **"Template not found"**: Check template file exists in correct directory
- **"Block not defined"**: Verify base template includes the block being extended

## Security Considerations

- All forms include CSRF protection
- Role-based access control enforced at route level
- Moderation notes are internal-only
- Sensitive actions require confirmation dialogs
- Audit logging should track all moderation actions
- Rate limiting recommended for bulk operations

## Future Enhancements

- Add audit log viewer
- Implement moderation statistics dashboard
- Add bulk export functionality
- Support for custom moderation workflows
- Integration with external compliance tools
- Real-time notifications for critical flags
- Advanced search and filtering capabilities
- Mobile-responsive design improvements

## Support

For questions or issues related to the moderator system:
1. Check this documentation
2. Review route implementations in `moderator.py`
3. Verify database schema migrations
4. Check template variable requirements
5. Review user role permissions
