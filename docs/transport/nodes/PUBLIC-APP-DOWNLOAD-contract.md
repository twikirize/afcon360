# PUBLIC-APP-DOWNLOAD — Contract

## 1. Guarantee
Visitors can find one public download page at /download.
It clearly presents AFCON360 User and Driver apps and their
availability across Android, iOS and web.

Only verified public distribution links may be activated.
Internal preview APKs must never be presented as public releases.

## 2. Current Behavior
The public /download page presents the AFCON360 User and Driver apps.
Each app card now includes a direct browser entry point to its existing
web experience. Android and iOS store links remain conditional on verified
official distribution URLs being configured.

The page also links to the existing GitHub pre-release APK assets for both Android apps. These are internal test builds, not Play Store releases.

## 3. Scope-In
- Add a public GET /download page.
- Add AFCON360 User and Driver app sections.
- Show Android and iOS availability honestly.
- Provide a working, app-specific browser link for the Fan experience and Driver Workspace.
- Link each Android card to its corresponding GitHub pre-Play APK asset, with an explicit internal-preview warning.
- Keep Download App out of the primary desktop menu and mobile drawer.
- Retain one persistent Download App link in the global footer.
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

Each app card always exposes its existing browser experience:
- AFCON360 User → the public Pamoja web experience.
- AFCON360 Driver → the authenticated Driver Workspace.

An Android or iOS download button appears only when a valid HTTPS
official store URL is configured (`AFCON360_USER_ANDROID_STORE_URL`,
`AFCON360_USER_IOS_STORE_URL`, `AFCON360_DRIVER_ANDROID_STORE_URL`,
`AFCON360_DRIVER_IOS_STORE_URL`). Otherwise show Coming Soon.
GitHub pre-Play APKs may be linked only with clear internal-test labeling and an explicit warning that they are not Play Store releases.

## 6. Proof of Done
- Anonymous visitors receive HTTP 200 at /download.
- Both applications display correctly.
- Android and iOS unavailable states are accurate.
- Both app-specific browser links render with the expected destinations.
- The User and Driver cards link to their corresponding GitHub pre-Play APK assets and clearly identify them as internal previews.
- The global footer links to /download.
- The primary desktop menu and mobile drawer do not duplicate the download link.
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
