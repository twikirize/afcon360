# Set the clean commit
$CLEAN_COMMIT = "25b9359"

# List of corrupted files to restore
$corruptedFiles =


@(
        "README_clean.md",
        "app/Documentation/ONBOARDING_IMPLEMENTATION_GUIDE.md",
        "Readme's/security_assessment.md",
        "public_home_old.html",
        "templates/accommodation_home.html",
        "templates/org/members_old.html",
        "templates/owner/danger_zone.html",
        "templates/transport/admin/dashboard.html",
        "templates/wallet/deposit.html",
        "templates/wallet/send.html",
        "templates/wallet/wallet_terms.html",
        "templates_backup/admin_payouts.html",
        "templates_backup/admin/manage_users.html",
        "templates_backup/admin/org_members.html",
        "templates_backup/admin/user_activity.html",
        "templates_backup/admin/compliance/dashboard.html",
        "templates_backup/admin/compliance/organisations.html"
)


Write - Host
"🔄 Restoring ONLY corrupted files from commit $CLEAN_COMMIT..." - ForegroundColor
Cyan
Write - Host
""

$restoredCount = 0
$skippedCount = 0

foreach($file in $corruptedFiles) {
# Check if file exists in the clean commit
$exists = git
ls - tree - r $CLEAN_COMMIT - -name - only | Select - String - Pattern
"^$($file -replace '\\','\\')$"

if ($exists)
{
    # Restore the file from clean commit
    git
checkout $CLEAN_COMMIT - - $file
Write - Host
"✅ Restored: $file" - ForegroundColor
Green
$restoredCount + +
} else {
    Write - Host
"⚠️  Skipped: $file (not in clean commit)" - ForegroundColor
Yellow
$skippedCount + +
}
}

Write - Host
""
Write - Host
"📊 Summary:" - ForegroundColor
Cyan
Write - Host
"  ✅ Restored: $restoredCount files" - ForegroundColor
Green
Write - Host
"  ⏭️  Skipped: $skippedCount files (not in clean commit)" - ForegroundColor
Yellow