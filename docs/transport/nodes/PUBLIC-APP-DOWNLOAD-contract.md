# PUBLIC-APP-DOWNLOAD — Contract

## 1. Guarantee
Visitors can find one public download page at /download.
It clearly presents AFCON360 User and Driver apps and their
availability across Android, iOS and web.

Only verified public distribution links may be activated.
Internal preview APKs must never be presented as public releases.

## 2. Current Behavior
The website has a shared desktop navigation, mobile drawer
and footer. There is currently no public download page.

The website itself remains accessible through a browser.
Android preview builds are not production store releases.

## 3. Scope-In
- Add a public GET /download page.
- Add AFCON360 User and Driver app sections.
- Show Android and iOS availability honestly.
- Provide a working link to the existing web platform.
- Add Download App links to desktop navigation,
  mobile navigation and the global footer.
- Make the page responsive and accessible.
- Add automated tests for public access and link safety.
- Allow official HTTPS store links to be configured later.

## 4. Scope-Out
- No separate repository.
- No About Us page in this work item.
- No Privacy Policy, Terms or legal documents in this work item.
- No public distribution of internal preview APKs.
- No changes to mobile application code or signing workflow.
- No production deployment.

## 5. Interface Contract
Canonical page: GET /download.

Applications:
- AFCON360 User
- AFCON360 Driver

Platform destinations:
- Android
- iOS
- Web

An official download button appears only when a valid HTTPS
distribution URL is configured. Otherwise show Coming Soon.

## 6. Proof of Done
- Anonymous visitors receive HTTP 200 at /download.
- Both applications display correctly.
- Android and iOS unavailable states are accurate.
- Web link works.
- Desktop, mobile and footer navigation link to /download.
- Invalid or non-HTTPS external URLs are never activated.
- Targeted automated tests pass using the PostgreSQL test database.

## 7. Rollback
Revert the feature branch changes without altering production
data, migrations or the mobile application branch.

## 8. Constraints
- Follow AGENTS.md and the EGGE workflow.
- No database migrations or production database changes.
- Do not invent privacy, security or data-protection claims.
- Do not advertise internal preview APKs as public releases.
- Keep website work isolated from mobile application work.

## 9. Acceptance Criteria
The page is visually consistent with the existing website,
works on desktop and mobile, and clearly distinguishes
available services from platforms still awaiting release.

The change must be reviewed and tested before merging or deploying.
