# Trust-Based Security System

## Overview
The trust-based security system automatically determines user privileges based on objective, measurable factors. This eliminates bias and ensures consistent security enforcement across the platform.

---

## WHO Determines Security?

### 1. **The Algorithm (Primary Decision Maker)**
- Calculates trust scores automatically
- Applies consistent rules to all users
- No human intervention in scoring
- Real-time evaluation on every action

### 2. **System Administrators (Policy Setters)**
- Configure trust thresholds (HIGH: 70+, MEDIUM: 40-69, LOW: <40)
- Define role hierarchies and permissions
- Set security policies and rules
- Monitor and audit trust decisions

### 3. **Users (Self-Determined)**
- Build trust through positive behavior
- Earn higher privileges over time
- Lose trust through violations
- Control their own security level

---

## HOW Security is Determined

### Trust Scoring System (0-100 Points)

| Factor | Points | Requirement | Security Rationale |
|--------|--------|-------------|-------------------|
| **Super Admin/Owner Role** | **AUTO HIGH** | System role | Ultimate platform control |
| **Admin Role** | +40 | Platform management | High responsibility |
| **Event Manager/Moderator** | +25 | Content oversight | Proven capability |
| **KYC Level 2+** | +30 | Full identity verification | Strong identity assurance |
| **KYC Level 1** | +15 | Basic verification | Some identity assurance |
| **Email Verified** | +15 | Confirmed email | Account legitimacy |
| **Account Age 30+ days** | +15 | Established account | Stability indicator |
| **Account Age 7+ days** | +8 | Not brand new | Basic stability |
| **5+ Successful Events** | +20 | Proven track record | Demonstrated competence |
| **2+ Successful Events** | +10 | Some experience | Initial competence |

---

## Security Levels

### HIGH TRUST (70+ points)
**Privileges:**
- Events auto-publish **immediately**
- Skip moderation queue
- Full platform access
- Immediate public visibility

**Who Qualifies:**
- Super Admin/Owner (automatic)
- Admin + KYC Level 2 + Verified (40+30+15 = 85 points)
- Event Manager + KYC Level 2 + 30+ days (25+30+15 = 70 points)
- Moderator + KYC Level 2 + Verified + 30+ days (25+30+15+15 = 85 points)
- 5+ successful events + full verification (20+30+15+15 = 80 points)

**Example Users:**
```
User: OBEDZ
- Roles: moderator, accommodation_admin, tourism_admin
- KYC Level: 2
- Email Verified: True
- Account Age: 21 days
- Score: ~93 points
- Result: HIGH TRUST - Auto-publish immediately
```

---

### MEDIUM TRUST (40-69 points)
**Privileges:**
- Events auto-publish **after approval**
- Faster moderation review
- Limited platform access
- Public visibility after approval

**Who Qualifies:**
- Event Manager + Verified (25+15 = 40 points)
- KYC Level 2 + Verified (30+15 = 45 points)
- Admin role only (40 points)
- 2+ successful events + verification (10+15+15+8 = 48 points)
- KYC Level 1 + Verified + 30+ days (15+15+15 = 45 points)

**Workflow:**
1. User submits event → Status: `PENDING_APPROVAL`
2. Moderator approves → Status: `APPROVED`
3. **System auto-publishes** → Status: `PUBLISHED` (automatic)
4. Event visible to public

---

### LOW TRUST (<40 points)
**Privileges:**
- **Manual publishing required**
- Full moderation review
- Restricted platform access
- No automatic publishing

**Who Qualifies:**
- New unverified users (0 points)
- Email verified only (15 points)
- KYC Level 1 only (15 points)
- New accounts (<7 days) with basic verification (15+0 = 15 points)
- Users with violations or flags

**Example Users:**
```
User: kyctest_user
- Roles: user
- KYC Level: 0
- Email Verified: True
- Account Age: 5 days
- Score: ~15 points
- Result: LOW TRUST - Manual publishing required
```

**Workflow:**
1. User submits event → Status: `PENDING_APPROVAL`
2. Moderator approves → Status: `APPROVED`
3. **Moderator must manually publish** → Status: `PUBLISHED`
4. Event visible to public

---

## Real-World Examples

### Example 1: High Trust User (OBEDZ)
```
Roles: ['moderator', 'accommodation_admin', 'tourism_admin']
KYC Level: 2 (+30 points)
Email Verified: True (+15 points)
Account Age: 21 days (+8 points)
Moderator Role: (+25 points)
Successful Events: 0 (+0 points)

TOTAL SCORE: ~78 points
TRUST LEVEL: HIGH
RESULT: Events auto-publish immediately
```

### Example 2: Medium Trust User (Hypothetical)
```
Roles: ['event_manager']
KYC Level: 1 (+15 points)
Email Verified: True (+15 points)
Account Age: 10 days (+8 points)
Event Manager Role: (+25 points)
Successful Events: 0 (+0 points)

TOTAL SCORE: ~63 points
TRUST LEVEL: MEDIUM
RESULT: Events auto-publish after approval
```

### Example 3: Low Trust User (kyctest_user)
```
Roles: ['user']
KYC Level: 0 (+0 points)
Email Verified: True (+15 points)
Account Age: 5 days (+0 points)
User Role: (+0 points)
Successful Events: 0 (+0 points)

TOTAL SCORE: ~15 points
TRUST LEVEL: LOW
RESULT: Manual publishing required
```

---

## How Users Build Trust

### Path to HIGH TRUST (70+ points)

**Option 1: Role + Verification**
1. Get promoted to Event Manager (+25)
2. Complete KYC Level 2 (+30)
3. Verify email (+15)
4. Wait 30 days (+15)
= **85 points → HIGH TRUST**

**Option 2: Experience + Verification**
1. Complete KYC Level 2 (+30)
2. Verify email (+15)
3. Wait 30 days (+15)
4. Successfully complete 5 events (+20)
= **80 points → HIGH TRUST**

**Option 3: Admin Role**
1. Get promoted to Admin (+40)
2. Complete KYC Level 1 (+15)
3. Verify email (+15)
= **70 points → HIGH TRUST**

---

## Security Audit Trail

Every trust decision is logged:
```python
logger.info(f"Trust analysis for user {user.id} ({user.username}): "
           f"Level={trust_level}, Auto-publish={should_auto_publish}, "
           f"Reason={trust_reason}")
```

Example log:
```
INFO: Trust analysis for user 2 (OBEDZ): 
      Level=high, Auto-publish=True, 
      Reason=High trust user - auto-publishing immediately
```

---

## Adjusting Trust Thresholds

To modify trust levels, edit `app/events/trust_service.py`:

```python
# Current thresholds
if score >= 70:
    return TrustLevel.HIGH
elif score >= 40:
    return TrustLevel.MEDIUM
else:
    return TrustLevel.LOW
```

**Recommended adjustments:**
- **More strict**: Increase thresholds (HIGH: 80+, MEDIUM: 50-79)
- **More lenient**: Decrease thresholds (HIGH: 60+, MEDIUM: 30-59)
- **Custom levels**: Add VERY_HIGH, VERY_LOW tiers

---

## Future Enhancements

### Planned Features:
1. **Violation tracking**: Deduct points for policy violations
2. **Appeal system**: Users can request trust review
3. **Dynamic thresholds**: Adjust based on platform risk level
4. **ML-based scoring**: Predict user behavior patterns
5. **Trust decay**: Reduce trust for inactive accounts
6. **Peer review**: Community trust ratings

### Potential Factors:
- Payment history (successful transactions)
- User reports (flags, complaints)
- Content quality scores
- Response time to support tickets
- Community engagement metrics

---

## API for Trust Analysis

```python
from app.events.trust_service import EventTrustService

# Get trust level
trust_level = EventTrustService.calculate_trust_level(user)

# Check auto-publish eligibility
should_auto, reason = EventTrustService.should_auto_publish(user)

# Get detailed analysis
analysis = EventTrustService.get_trust_analysis(user)
print(analysis)
# {
#     'user_id': 2,
#     'username': 'OBEDZ',
#     'trust_level': 'high',
#     'should_auto_publish': True,
#     'reason': 'High trust user - auto-publishing immediately',
#     'factors': {...}
# }
```

---

## Security Best Practices

1. **Never hardcode trust levels** - Always calculate dynamically
2. **Log all trust decisions** - Maintain audit trail
3. **Review thresholds regularly** - Adjust based on platform needs
4. **Monitor for abuse** - Watch for trust gaming attempts
5. **Transparent to users** - Show users their trust score and how to improve
6. **Fair and consistent** - Apply same rules to all users
7. **Privacy-conscious** - Don't expose sensitive trust factors publicly

---

## Compliance and Legal

- **GDPR Compliant**: Trust scores are based on user actions, not personal data
- **Fair and Non-Discriminatory**: Objective criteria applied equally
- **Transparent**: Users can see their trust level and factors
- **Auditable**: Complete log of all trust decisions
- **Reversible**: Trust can be rebuilt through positive behavior

---

## Summary

**WHO determines security?**
- Algorithm (primary)
- System admins (policy)
- Users (self-determined through behavior)

**HOW is security determined?**
- Objective scoring system (0-100 points)
- Multiple factors (roles, KYC, age, history)
- Three trust levels (HIGH, MEDIUM, LOW)
- Automatic, consistent, auditable

**Result:**
- Fair, transparent security
- No human bias
- Users control their own trust level
- Platform security maintained
