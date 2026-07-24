What this page currently is

This is not the public accommodation page.

It is an administrative listing management page whose primary purpose is to let admins browse properties and perform moderation actions.

The template expects the backend to provide:

properties (paginated results)
search_q
status_filter
status_options

So somewhere there is probably a route similar to

@accommodation_bp.route("/admin/properties")
def admin_properties():
    ...

which queries the database and passes these variables into this template.

What an admin can currently do

From the template, an admin can:

1. Search

Currently by

title
city
country

through

<input name="q">
2. Filter

Currently only by

status

which comes from

status_options

Likely values are

draft
pending_review
active
suspended
archived
3. Review a property

The clipboard icon goes to

url_for(
    'accommodation.moderate_property',
    property_id=prop.id
)

This suggests there is a dedicated moderation page.

4. Edit a property

Through

host_edit_listing

which is interesting because admins are using the host editor.

5. Approve

Only appears when

status == "pending_review"

and submits

moderate_property_approve()
6. Reject

Posts to

moderate_property_reject()

So today the workflow appears to be

Host creates property

↓

Draft

↓

Submit

↓

Pending Review

↓

Admin approves

↓

Active
What is missing

This is where I think the design becomes weak.

The page mixes listing management with publication management.

Those are actually different concepts.

For example a property can be

complete
verified
approved
active
published

Those are not the same thing.

Think of a property as moving through stages

Instead of thinking

Pending

↓

Active

think

Created

↓

Completed

↓

Submitted

↓

Under Review

↓

Approved

↓

Verified

↓

Published

↓

Bookable

↓

Archived

Each stage answers a different question.

Stage 1

Can the host still edit?

Stage 2

Has the host finished all required information?

Examples

photos
amenities
rooms
location
pricing
Stage 3

Has the host actually submitted it?

Some hosts save drafts for weeks.

Stage 4

Has an admin inspected it?

Stage 5

Did it pass review?

Stage 6

Has it been verified?

Verification may involve

documents
ownership
hotel licence
phone verification
Stage 7

Should customers see it?

This is actually different.

Sometimes you approve something but don't publish it yet.

For example

Hotel requested publication next week.

The current page only partially reflects this

Right now the table shows

status
verified

Those two fields aren't enough to explain where a property is in its lifecycle.

What should this page become?

I wouldn't think of it as

Property Management

I'd think of it as

Property Moderation Dashboard

An admin's thought process is usually

Show me properties that need my attention.

not

Show me every property.

The workflow becomes

Find property

↓

Inspect

↓

Take action

↓

Property moves to next stage

↓

Eventually becomes public

That is much cleaner.

Filters that would actually help admins

Instead of only

Status

I'd expect filters such as

Workflow
Draft
Awaiting submission
Pending review
Approved
Rejected
Verification
Verified
Not verified
Publication
Public
Hidden
Property type
Hotel
Apartment
Villa
Guest House
Country
City
Host
Date submitted
Missing information

Examples

No photos
No rooms
No amenities
Missing pricing

These are often the most useful moderation filters.

The actions should also reflect the workflow

Instead of just

Approve

Reject

the actions could become

View

Inspect

Approve

Reject

Request Changes

Suspend

Publish

Unpublish

Archive

Notice these are all different operations.

The biggest architectural question

Before changing anything, I would identify what actually controls whether a property appears on the public accommodation page.

For example, is the public query doing something like:

Property.query.filter_by(
    status="active",
    is_verified=True
)

or

Property.query.filter(
    Property.is_public == True
)

or

Property.query.filter(
    Property.status == PropertyStatus.ACTIVE
)

This is the key to understanding the current state. Until we know exactly what conditions the public accommodation page uses to select properties, it's difficult to redesign the moderation workflow safely.

I would start by locating these backend pieces:

The admin_properties route that renders this template.
The Property (or equivalent) model to see all available fields such as status, is_verified, is_active, published_at, etc.
The public accommodation route (accommodation.home or similar) that queries and displays listings for customers.

Once those three pieces are identified, we can map the entire lifecycle from host creates a property → admin moderates it → property becomes visible to customers, and then decide whether new statuses, filters, or publication controls are actually needed instead of guessing.

Yes. After seeing this code, I agree with your correction: an Event Host should not approve a property. Claude's earlier wording mixed two separate concepts.

Your existing model actually points toward a better design:

Moderator approves the property globally.
Event organiser approves the property's participation in an event.
Those are two different approvals.

The mistake is not that EventHostRegistration exists. The mistake is letting event approval mutate property moderation state.

The correct ownership model
1. Property approval (Accommodation + Admin)

Owned by:

app/accommodation
        +
app/admin/moderator

Your existing model:

PropertyModerationHistory

is exactly the right direction.

Flow:

Host creates property
        |
        v
Property.status = DRAFT

        |
        v

Host submits

        |
        v

Property.status = PENDING_REVIEW

        |
        v

Moderator reviews

        |
        +---- reject
        |
        +---- request changes
        |
        +---- approve

        v

Property.status = ACTIVE
Property.verification_status = VERIFIED

The moderator is:

moderated_by

in:

PropertyModerationHistory

That is the correct actor.

2. Event participation approval (Events)

This is where EventHostRegistration belongs.

Example:

John has:

Property:
John's 3 bedroom house

Status:
ACTIVE

Then:

AFCON organiser says:

We need accommodation near the stadium.

John clicks:

Offer this property for AFCON

Creates:

EventHostRegistration

property_id = John's house
event_id = AFCON
status = pending

Now the event organiser reviews.

They approve:

EventHostRegistration.status = approved

But they DO NOT touch:

Property.status
Property.is_verified
Property.is_active
Property.verification_status
Your Property model already supports this separation

You currently have:

status = Column(
    String(50),
    default="draft"
)

Good.

You have:

verification_status

Good.

You have:

verified_by

Good.

That means:

verified_by

should always point to:

moderator/admin/compliance officer

not:

event organiser
One thing I would change

This part:

class AccommodationPropertyType(enum.Enum):
    COMMUNITY_HOST = "community_host"

I would rethink.

A community host is not really a property type.

Your example proves it.

The same house can be:

Property Type:
ENTIRE_PLACE

but its participation can be:

Event Badge:
COMMUNITY_HOST

Example:

John's house:

Property:
3 bedroom home

Type:
entire_place

Badges:

AFCON 2027
Community Host

Wedding Festival
Private Invitation

Public Booking
Airbnb style

So I would move "community host" away from property type.

Better model

Instead of:

property_type = COMMUNITY_HOST

use something like:

Property
 |
 |
 +-- EventAvailabilityBadge

Example:

PropertyEventBadge

id

property_id

event_id

badge_type

visibility

approval_status

approved_by

approved_at

starts_at

expires_at

Where:

badge_type

could be:

COMMUNITY_HOST
EVENT_PARTNER
VIP_HOST
VOLUNTEER_HOST
ORGANISER_SELECTED
Your lifecycle becomes clean
Property lifecycle
DRAFT
 |
SUBMITTED
 |
PENDING_REVIEW
 |
ACTIVE
 |
SUSPENDED
 |
ARCHIVED

Controlled by:

Moderator
Event badge lifecycle
REQUESTED
 |
PENDING_EVENT_APPROVAL
 |
ACTIVE
 |
EXPIRED
 |
REVOKED

Controlled by:

Event organiser
Your hotel example

A hotel submits:

Hotel Kampala

Property:

ACTIVE

But:

Rooms = 0

Then:

Readiness = FAIL

Therefore:

Public visibility = NO

Even though:

Moderation approved = YES

This is the third state you need.

Currently you have:

Approval
Verification
Active

but you need:

Operational readiness

Something like:

listing_ready = False

or preferably a service:

AccommodationReadinessService

checking:

✓ Address
✓ Photos
✓ Pricing
✓ Rooms (if hotel)
✓ Availability
✓ Payment setup
✓ Policies

Only then:

can_be_publicly_booked()

returns true.

Auto approval fits here

Moderator approval can become automatic:

Example:

Individual:

KYC verified
+
clean history
+
complete listing

=
auto approved

Organisation:

KYB verified
+
licence verified
+
hotel documentation

=
auto approved

But still:

AccommodationReadinessService

must pass.

So:

KYC/KYB approval
          |
          v
Property moderation approval
          |
          v
Listing readiness
          |
          v
Public visibility

Four gates.

So your instinct is right: event hosts should never approve properties. They approve participation. The moderator approves the asset. Your existing PropertyModerationHistory is already the right foundation; the main correction is separating the event badge from the property itself.

so all is d=said lets now work dont do any code yet but lest do an arctect especially now the pain was on the poperty listin tillits bookable it was not visible both in back end anf front end the admn s haved no way of  seeing what is taking place, what is happenoing to tjhis porperty where is it next step by who all these now we can just link it with the event so as the a dmins or event host can create a badge and the property owners can  wear thes e badges like register to host  for an event then chose an event hen you are  visible to such group or the  system admins or host can select you and appoint you to be discoverable ifnot you are not seen in the  public  but it  this discorwabiity is only for  non full time hosrs like a hotel should not every day be looking for  adges it offerre accomodatin evry day so that logic of like community hosts shoiuld be alsoeasy during onboarding but the biggest piint first, so you going ot give a big context, goals and intentiosn and everything our agent wuld need to implement  as the best system we wenvisionhere

I understand the direction. Before touching code, the architecture needs to be corrected around the ownership of trust, visibility, moderation, and event-specific discovery.

The key insight I am taking from your explanation:

A "community host" is not a property category. It is a participation capability that a property owner can activate temporarily or selectively around events.

The mistake was making community hosts feel like another Airbnb-style accommodation type (COMMUNITY_HOST). That creates confusion because a hotel, lodge, apartment, or home does not become a different type of property. It becomes an event-linked accommodation participant.

The property remains an accommodation asset. The badge is the participation layer.

F360 Accommodation + Events Architecture Vision
1. Current pain being solved

Today the flow is:

Property Owner
      |
      |
Creates Property
      |
      |
Pending Review
      |
      |
Moderator approves
      |
      |
Active
      |
      |
Bookable

The problem:

During this lifecycle, nobody has enough operational visibility.

Admins cannot easily answer:

Who submitted this property?
Who reviewed it?
What stage is it in?
Why is it blocked?
Who requested changes?
Is it being prepared for an event?
Which event does it belong to?
Who made it visible?
Who assigned it?
When does that visibility expire?
Is it a permanent accommodation business or temporary community capacity?

The system needs a property lifecycle intelligence layer.

2. Core principle: Separate Property Identity from Participation Identity

A property has a permanent identity.

Example:

Lake View Apartment
Owner: John
Location: Kampala
Type: Entire Place
Status: Active

That never changes.

But participation changes.

Example:

Event:
Kampala Marathon 2027

Need:
50 community accommodation providers

John chooses:
"I want to host runners"

System creates:

Badge:
Kampala Marathon Community Host

Valid:
15 Jan 2027 - 25 Jan 2027

The property did not become a new property.

It gained an event participation credential.

3. Replace "Community Host Property Type"

Current:

AccommodationPropertyType

ENTIRE_PLACE
PRIVATE_ROOM
HOTEL_ROOM
COMMUNITY_HOST   ❌

Future concept:

PropertyType

ENTIRE_PLACE
PRIVATE_ROOM
SHARED_ROOM
HOTEL_ROOM
LODGE
HOSTEL

Separate:

PropertyParticipationType

EVENT_HOST
COMMUNITY_HOST
FESTIVAL_HOST
SPORTS_HOST
CONFERENCE_HOST
EMERGENCY_CAPACITY_PROVIDER
4. The badge system

The badge becomes the bridge between Events and Accommodation.

Concept:

Event
 |
 |
creates Host Opportunity
 |
 |
Property Owner applies
 |
 |
Moderator approves
 |
 |
Badge issued
 |
 |
Property becomes discoverable

Example:

Event Badge
🏅 Official Community Host
Kampala Music Festival 2027

Issued by:
Kampala Music Festival

Valid:
01 August - 15 August 2027

Status:
Active
5. Discovery rules

The biggest change:

Normal accommodation discovery

Hotels:

Property
 |
Active
 |
Verified
 |
Public
 |
Bookable

No badge required.

Event accommodation discovery

Community hosts:

Property
 |
Active
 |
Verified
 |
Has Event Badge
 |
Badge valid
 |
Visible to event audience

Without badge:

Property exists
+
Can be booked normally

BUT

Not visible inside event accommodation search
6. Visibility becomes a permission decision

Today visibility is tied to property approval.

Future:

There are multiple visibility channels.

Example:

Property
 |
 |
 +---- Public Marketplace
 |
 |
 +---- Event Marketplace
 |
 |
 +---- Admin Dashboard
 |
 |
 +---- Host Dashboard
 |
 |
 +---- Private Invitation

A property can be:

Public:
YES

Event:
NO

Admin:
YES

Host:
YES
7. Actors and responsibilities
Property Owner

Can:

Create property
Submit verification
Apply for badges
Accept event invitations
Remove participation
Choose availability

Cannot:

Approve themselves
Make themselves trusted
Issue badges
Event Host

Can:

Create accommodation requirements
Request community hosts
Invite properties
View approved event hosts
Manage event accommodation pool

Cannot:

Verify property ownership
Approve compliance
Moderator

Owns trust.

Moderator approves:

Property legitimacy
Safety
Compliance
Photos
Identity
Documents

Moderator decides:

Property:
approved

Badge:
approved
Admin

Sees everything.

Admin dashboard should answer:

Property journey
Property:
Sunset Apartment

Created:
12 Jan

Owner:
John

Submitted:
15 Jan

Moderator:
Mary

Current status:
Pending verification

Blocked because:
Missing license

Next action:
Owner upload document
8. Property lifecycle state machine

The property needs a stronger lifecycle.

Current:

draft
pending_review
active
suspended
archived

Better:

DRAFT

 |
 v

SUBMITTED

 |
 v

UNDER_REVIEW

 |
 +------------+
 |            |
 v            v

APPROVED    REJECTED


 |
 v

ACTIVE


 |
 +----------------+
 |                |
 v                v

SUSPENDED      ARCHIVED

Important:

A property can be:

ACTIVE
but

NOT EVENT DISCOVERABLE

because it has no badge.

9. Badge lifecycle

Separate state machine:

REQUESTED

 |
 v

UNDER_REVIEW

 |
 +-------------+
 |             |
 v             v

APPROVED     REJECTED


 |
 v

ACTIVE


 |
 v

EXPIRED

Example:

Kampala Marathon Badge

Requested:
01 March

Approved:
05 March

Active:
10 June - 20 June

Expires:
21 June
10. Event Host Registration Model

The relationship should not be:

Event -> Property

because one property can participate in many events.

Instead:

Event
 |
 |
EventAccommodationOpportunity
 |
 |
EventHostRegistration
 |
 |
Property

Meaning:

An event creates a demand.

Example:

EventAccommodationOpportunity

Event:
African Cup Final

Required:
500 beds

Area:
Kampala

Accepting:
Community Hosts
Hotels
Guest Houses

Then:

EventHostRegistration

Property:
John's Apartment

Event:
African Cup Final

Status:
Approved

Badge:
Issued

Visibility:
Event guests
11. Onboarding experience
Existing hotel

During onboarding:

What type of accommodation?

[Hotel]
[Apartment]
[Lodge]
[Home]

Done.

No badge.

Community participant

During onboarding:

Question:

Would you like to participate in events?

[Yes]
[No]

If yes:

Enable event hosting profile

Then:

Available for:

☑ Sports events
☑ Festivals
☑ Conferences
☑ Tourism events
12. Temporary hosting concept

Important point you raised:

They can appear for a certain event and never host again or after 5 years.

Exactly.

Therefore:

A badge is not a permanent identity.

It is a credential.

Example:

John's Apartment

Badges:

✔ Kampala Marathon 2027
Expired

✔ Tourism Expo 2028
Active

No badge currently
13. Admin intelligence layer

Create an accommodation command center.

Admins see:

Property pipeline
Submitted today:
45

Awaiting review:
18

Rejected:
7

Approved:
20
Badge pipeline
Event host applications

Music Festival:
120 applicants

Approved:
80

Pending:
30

Rejected:
10
Property history timeline

Example:

10 Feb
Owner created property

12 Feb
Submitted verification

15 Feb
Moderator requested documents

18 Feb
Documents uploaded

20 Feb
Approved

25 Feb
Applied for Marathon Host Badge

28 Feb
Badge approved
14. Relationship with your existing architecture

The good news:

Your existing structure already points here.

You already have:

app/events/
    routes_community_hosts.py
    routes_accommodation.py

and:

app/accommodation/
    host_service.py
    identity_service.py
    moderation

The missing architecture is the bridge module.

Conceptually:

app/event_accommodation/

    models/
        badge.py
        host_registration.py
        opportunity.py

    services/
        badge_service.py
        discovery_service.py
        matching_service.py
        invitation_service.py
Final architectural decision

The system should become:

EVENTS
  |
  |
creates accommodation demand
  |
  |
BADGE SYSTEM
  |
  |
temporarily grants participation
  |
  |
PROPERTY
  |
  |
bookable accommodation asset

Not:

COMMUNITY_HOST = PROPERTY TYPE

That was the wrong abstraction.

The cleaner model:

Properties are permanent.
Events are temporary.
Badges connect them.
Moderators control trust.
Hosts control demand.
Admins see the entire journey.

This architecture also fits your existing F360 direction because it turns events into an ecosystem layer instead of forcing accommodation to become event-specific.

let me steer you  abit uon listing my porperty ad admin may not teject a property and not apporve like incase thereis more information neeeded, how does these systems f=do it are poerty auto apprvied but before even lisitng the kyc should be at a certain percentage  fullfilled like individuals  most things should be there id, pj=hone and email, then he can list  th eporpeprty if kyc is full organisations  alo need their kyc full lilke name, tin, ursb requirements etc the kyc and and kyb are already detailed  then its not always the   host toask for the  badhge but the event host/ owner and not every property should  appear only becasu eof a badge no toehr will be permanent

I understand the correction. The previous architecture placed too much emphasis on "moderator approval of everything" and not enough on the trust ladder that already exists in your platform.

The important distinction is:

Property approval ≠ event participation approval.

A property should have its own independent lifecycle. An event badge is an additional visibility credential, not the thing that makes a property legitimate.

Let me reframe the architecture based on your steering.

1. First principle: Identity/KYC comes before property trust

The system should not start with:

User
 |
Create Property
 |
Admin decides

It should start with:

Identity
 |
KYC/KYB completion
 |
Eligibility to create property
 |
Property listing
 |
Property verification
 |
Public availability

The property inherits trust from the owner identity, but does not replace property verification.

2. KYC/KYB gate before listing
Individual owner

Before creating a property:

Minimum identity requirements:

Individual Account

Required:
✓ Email verified
✓ Phone verified
✓ Government ID verified
✓ Basic profile completed

Optional/advanced:
✓ Address verification
✓ Payment verification
✓ Additional documents

Then:

KYC Score >= required threshold
        |
        |
        v
Can create property
Organisation owner

Before listing:

Organisation

Required:

✓ Legal name
✓ Registration information
✓ TIN
✓ Registration documents
✓ Authorised representative
✓ Contact verification
✓ Organisation owner/controller verification

Then:

KYB Approved
        |
        |
        v
Can publish properties
3. Property lifecycle should not be only approve/reject

Your point is correct:

Admin may not reject, they may need more information.

Most mature marketplaces do not have only:

Approved
Rejected

They use a review workflow.

Example:

DRAFT

 |
 v

SUBMITTED

 |
 v

UNDER_REVIEW

 |
 +----------------+
 |                |
 v                v

APPROVED       NEEDS_INFORMATION


                     |
                     |
                     v

              OWNER_UPDATES


                     |
                     |
                     v

              UNDER_REVIEW


 |
 v

ACTIVE
4. What happens when information is missing?

Example:

Owner submits:

Property:
Lake View Apartments

Photos:
complete

Location:
complete

Ownership:
missing document

Moderator action:

NOT:

Reject

Instead:

Status:
NEEDS_INFORMATION

Reason:
Please upload proof of ownership or management authority.

Requested by:
Moderator Sarah

Deadline:
14 days

The owner receives a task.

5. Is a property automatically approved?

The answer is usually: partially.

Different systems separate:

Listing creation

from

Marketplace visibility

Example:

Airbnb-style logic:

A host can create a listing.

But visibility depends on:

identity
payment setup
trust checks
content completeness
risk checks

So F360 could do:

Owner completes KYC

        |

Allowed to create property

        |

Property saved as:

DRAFT

        |

Owner submits

        |

Automated checks

        |

Risk score

        |

Moderator review only if needed
6. Introduce property trust score

Instead of forcing humans to review every property:

Property Trust Score

built from:

Identity:

Owner KYC: 100%

Property:

Photos: complete
Location: verified
Description: complete
Documents: verified

Risk:

New account
Duplicate address
Suspicious pricing

Then:

Example:

Property Trust Score: 92%

Low risk

Auto activate

Another:

Property Trust Score: 45%

Needs review
7. Moderator role changes

Moderator is not the person who approves every property.

Moderator becomes:

Trust escalator

Handles:

incomplete verification
suspicious properties
complaints
fraud signals
high-risk listings

The workflow becomes:

System handles normal flow

Moderator handles exceptions
8. Now the event badge logic

Your correction is important:

It is not always the host asking for the badge. The event host/owner may create and assign it.

Exactly.

There are two flows.

Flow A: Event invites properties

Example:

Football tournament needs accommodation.

Event owner creates:

Event Accommodation Request

Need:
300 rooms

Location:
Kampala

Dates:
June 2027

Accept:
Hotels
Guest houses
Community hosts

System searches eligible properties.

Event host can:

Invite selected properties

Property owner receives:

Invitation:
Official Accommodation Partner

Accept?
YES / NO
Flow B: Owner applies

Optional:

Property owner sees:

Available opportunities:

Kampala Marathon Host Programme

Apply

Both are valid.

9. Badge does not create public visibility

This is the biggest correction.

A property should not become visible only because of a badge.

Wrong:

Badge
 |
Property becomes visible

Correct:

Property visibility
      |
      +---- Public marketplace
      |
      +---- Event marketplace
      |
      +---- Private invitation

Example:

Hotel:

Active
Verified
Public

No badge needed.

Community host:

Active
Verified

Public:
No

Event:
Kampala Marathon only

Badge:
Active
10. Permanent hosts versus temporary hosts

You are right:

A hotel should not be constantly dealing with badges.

So introduce:

Accommodation participation profile

Two categories:

Permanent accommodation providers

Examples:

Hotels
Lodges
Apartments

They are always discoverable.

Community/event hosts

Examples:

Family home
Spare apartment
Temporary rooms

They require participation credentials.

11. Final architecture view
                 USER / ORGANISATION
                         |
                         |
                    KYC / KYB
                         |
                         |
                 Property Creation
                         |
                         |
              Property Verification Engine
                         |
              +----------+----------+
              |                     |
        Normal Provider       Event Participant
              |                     |
              |                     |
      Public Marketplace       Badge System
                                    |
                              Event Discovery
12. The admin view becomes much clearer

Admin dashboard:

PROPERTY PIPELINE

Draft
Submitted
Under Review
Needs Information
Active
Suspended
Archived


EVENT PARTICIPATION

Badge Requests
Event Invitations
Active Event Hosts
Expired Participation


TRUST

KYC issues
KYB issues
Risk alerts
Fraud signals

The next architectural piece I would define before code is the exact boundary between:
is found in @app/accomodation/ boundaries.md
Property Verification
Identity KYC/KYB
Event Host Badge
Event Accommodation Matching

because those four should communicate but never own each other's responsibilities.