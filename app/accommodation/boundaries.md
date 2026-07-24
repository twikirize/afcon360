what is you plan here Property Verification
Identity KYC/KYB
Event Host Badge
Event Accommodation Matching

My plan is to make these four separate trust and discovery systems that communicate through clear contracts.

The biggest architectural mistake would be allowing one system to become responsible for another.

For example:

KYC should not approve properties.
Property verification should not decide event participation.
Event hosts should not verify identities.
Badges should not replace accommodation approval.

Each layer answers a different question.

F360 Trust + Accommodation Architecture
Layer 1: Identity KYC / KYB
Question it answers:

"Who is this person or organisation?"

This is the foundation.

It does not care about properties or events.

Individual example

John wants to participate.

KYC checks:

Identity
 |
 +-- Name
 +-- Phone
 +-- Email
 +-- Government ID
 +-- Address (if required)
 +-- Payment identity

Result:

Individual Trust Profile

KYC Status:
VERIFIED

KYC Level:
Level 2

Can:
✓ Create properties
✓ Receive payments
✓ Participate in events
Organisation example

A hotel company joins.

KYB checks:

Organisation
 |
 +-- Legal name
 +-- Registration number
 +-- TIN
 +-- URSB documents
 +-- Directors/controllers
 +-- Authorised representatives

Result:

Organisation Trust Profile

KYB Status:
VERIFIED

Can:
✓ List properties
✓ Receive business payments
✓ Partner with events

Important:

KYC/KYB is a gatekeeper.

It answers:

"Can this entity participate on F360?"

Layer 2: Property Verification
Question it answers:

"Is this accommodation listing legitimate and safe?"

Different question.

A verified person can still create a bad property.

Example:

John is verified.

But he uploads:

Luxury Kampala Villa

Photos:
fake

Address:
wrong

Ownership:
unclear

The property needs its own assessment.

Property lifecycle

I would design:

DRAFT

 |
SUBMITTED

 |
SYSTEM_CHECKS

 |
UNDER_REVIEW

 |
 +----------------+
 |                |
 v                v

ACTIVE       NEEDS_INFORMATION

                  |
                  |
                  v

             OWNER_UPDATE

                  |
                  |
                  v

             UNDER_REVIEW


 |
 v

SUSPENDED

 |
 v

ARCHIVED
System checks first

Before humans:

Property Verification Engine

Checks:

✓ Owner KYC/KYB valid
✓ Required fields completed
✓ Photos uploaded
✓ Location exists
✓ Duplicate detection
✓ Pricing anomalies
✓ Content safety
✓ Fraud signals

Then:

Low risk:

Auto activate

High risk:

Moderator queue

Moderator does not "approve everything".

Moderator handles exceptions.

Layer 3: Event Host Badge
Question it answers:

"Is this property allowed to participate in this particular event?"

This is temporary authorization.

Example:

A football tournament happens.

The event needs accommodation.

The event creates:

Accommodation Programme

Event:
AFCON Kampala 2027

Need:
500 beds

Area:
Kampala

Dates:
January 2027

Properties are matched.

A property receives:

Badge:

Official AFCON Community Host

Issued by:
AFCON Kampala Event Team

Valid:
01 Jan - 30 Jan

Status:
ACTIVE

The badge says:

This property is trusted for this event.

It does NOT say:

This property is a valid accommodation business.

That comes from Property Verification.

Badge lifecycle:

CREATED

 |
INVITED

 |
ACCEPTED

 |
VERIFIED

 |
ACTIVE

 |
EXPIRED
Layer 4: Event Accommodation Matching
Question it answers:

"Which accommodation options should this event audience see?"

This is discovery.

It combines information from the other three systems.

Input:

Event:

Kampala Marathon

Requirements:

Dates:
10-15 June

Location:
Kampala

Guests:
Athletes

Need:
500 rooms

The matching engine asks:

Identity
Is the owner trusted?

from:

KYC/KYB
Property
Is accommodation legitimate?

from:

Property Verification
Event
Does it have participation permission?

from:

Event Host Badge

Then produces:

Recommended Event Accommodation

1. Hotel A
   Permanent Provider

2. Apartment B
   Community Host Badge

3. Lodge C
   Event Partner
How they connect

The relationship should look like this:

                 USER
                   |
                   |
              KYC / KYB
                   |
                   |
          +--------+--------+
          |                 |
          |                 |
      PROPERTY          EVENT
          |                 |
          |                 |
 Property Verification   Badge System
          |                 |
          +--------+--------+
                   |
                   |
        Event Accommodation Matching
                   |
                   |
              Discovery Layer
Database ownership concept

I would avoid:

Event
  owns
Property

because that creates a mess.

Instead:

Property
 |
 |
EventHostRegistration
 |
 |
Event

Meaning:

A property exists independently.

A relationship records participation.

Example complete journey
Day 1

John registers.

KYC:
verified
Day 2

John creates:

Sunset Apartment

Property:

DRAFT
Day 3

System checks.

Property:

ACTIVE

Now it can appear publicly.

Day 50

A marathon organizer needs accommodation.

Creates:

Marathon Host Programme

System finds:

Sunset Apartment

because:

Location matches
Capacity matches
Property verified
Owner trusted

Event sends invitation.

John accepts.

Badge created:

Marathon Community Host 2027

During marathon:

Athletes search:

Marathon accommodation

They see:

Hotels
+
Verified community hosts

After marathon:

Badge expires.

Property remains:

ACTIVE

No damage.

The strategic benefit

This gives F360 three different marketplaces:

Normal accommodation marketplace

Permanent supply.

Hotels
Lodges
Apartments
Event accommodation marketplace

Temporary demand.

Sports
Festivals
Conferences
Weddings
Tourism events
Community capacity marketplace

Flexible supply.

Homes
Rooms
Temporary hosts

The architecture stays clean because:

KYC proves the person.
Property verification proves the accommodation.
Badge proves event participation.
Matching decides visibility.

That separation is what will make the system scalable