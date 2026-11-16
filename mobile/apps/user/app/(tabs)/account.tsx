import React, { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Pressable,
  StyleSheet,
  Text,
  View
} from "react-native";
import * as WebBrowser from "expo-web-browser";
import { useRouter } from "expo-router";
import { palette } from "@afcon360/mobile-ui";
import { PamojaScreen as AppScreen, PamojaPageHeader as PageHeader } from "../../src/components/PamojaScreen";
import { useAuth } from "../../src/auth/AuthProvider";
import { getSelectedApiBaseUrl } from "../../src/services/api";

const WEBSITE_ACTION_LABEL = "Opens on Pamoja website";

type WebsiteMenuRowProps = {
  title: string;
  description: string;
  symbol: string;
  onPress: () => void;
  last?: boolean;
  external?: boolean;
};

function WebsiteMenuRow({ title, description, symbol, onPress, last = false, external = true }: WebsiteMenuRowProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={external ? title + ". " + WEBSITE_ACTION_LABEL : title}
      onPress={onPress}
      style={({ pressed }) => [
        styles.menuRow,
        !last && styles.menuRowDivider,
        pressed && styles.menuRowPressed
      ]}
    >
      <View style={styles.menuIcon}>
        <Text style={styles.menuIconText}>{symbol}</Text>
      </View>
      <View style={styles.menuCopy}>
        <Text style={styles.menuTitle}>{title}</Text>
        <Text style={styles.menuDescription}>{description}</Text>
        {external ? <Text style={styles.menuHint}>{WEBSITE_ACTION_LABEL}</Text> : null}
      </View>
      <Text style={styles.menuArrow}>{external ? "↗" : "›"}</Text>
    </Pressable>
  );
}

function AccountMenuSection({
  title,
  description,
  children
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHeading}>
        <Text style={styles.sectionTitle}>{title}</Text>
        <Text style={styles.sectionDescription}>{description}</Text>
      </View>
      <View style={styles.menuCard}>{children}</View>
    </View>
  );
}

function accountInitials(value: string): string {
  const parts = value.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "AF";
  return parts.slice(0, 2).map(part => part[0]?.toUpperCase() ?? "").join("");
}



export default function Account() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const [websiteBaseUrl, setWebsiteBaseUrl] = useState("https://www.pamoja.space");

  useEffect(() => {
    let mounted = true;
    void getSelectedApiBaseUrl()
      .then(url => {
        if (mounted) setWebsiteBaseUrl(url);
      })
      .catch(() => {
        if (mounted) setWebsiteBaseUrl("https://www.pamoja.space");
      });
    return () => {
      mounted = false;
    };
  }, []);

  const openWebsite = useCallback(async (path: string) => {
    try {
      const base = new URL(websiteBaseUrl);
      const target = new URL(path, base.origin + "/");
      if (target.origin !== base.origin || (target.protocol !== "https:" && target.protocol !== "http:")) {
        throw new Error("That account page is not available on the selected AFCON360 server.");
      }
      await WebBrowser.openBrowserAsync(target.toString());
    } catch (error) {
      Alert.alert(
        "Website unavailable",
        error instanceof Error ? error.message : "AFCON360 could not open that account page."
      );
    }
  }, [websiteBaseUrl]);

  const signOut = async () => {
    try {
      await logout();
      router.replace("/login");
    } catch {
      // Local credentials are cleared by AuthProvider even if the server is
      // unreachable. Tell the user that remote revocation could not be proven.
      router.replace("/login");
      Alert.alert(
        "Server sign-out not confirmed",
        "This device has been signed out, but AFCON360 could not confirm that the server session was revoked. Connect to the internet and sign in again to refresh your session, and review any other devices where you are signed in."
      );
    }
  };

  const displayName = user?.display_name || user?.username || "AFCON360 member";
  const initials = accountInitials(displayName);

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Account"
        title="Your account."
        description="Manage your profile, personal settings, preferences and security."
      />

      <View style={styles.profileHero}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{initials}</Text>
        </View>
        <View style={styles.profileInfo}>
          <Text style={styles.profileEyebrow}>YOUR PAMOJA IDENTITY</Text>
          <Text style={styles.profileName} numberOfLines={2}>{displayName}</Text>
          <Text style={styles.profileUsername}>@{user?.username ?? "member"}</Text>
          <Text style={styles.profileEmail} numberOfLines={1}>{user?.email || "No email address on file"}</Text>
          <View style={styles.statusRow}>
            <View style={styles.statusPill}>
              <View style={styles.statusDot} />
              <Text style={styles.statusText}>SIGNED IN</Text>
            </View>
            <View style={[styles.statusPill, user?.email_verified ? styles.verifiedPill : styles.pendingPill]}>
              <Text style={[styles.statusText, user?.email_verified ? styles.verifiedText : styles.pendingText]}>
                {user?.email_verified ? "EMAIL VERIFIED" : "EMAIL NOT VERIFIED"}
              </Text>
            </View>
            <View style={[styles.statusPill, user?.mfa_enabled ? styles.verifiedPill : styles.pendingPill]}>
              <Text style={[styles.statusText, user?.mfa_enabled ? styles.verifiedText : styles.pendingText]}>
                {user?.mfa_enabled ? "2-STEP ENABLED" : "2-STEP NOT ENABLED"}
              </Text>
            </View>
          </View>
        </View>
      </View>

      <AccountMenuSection
        title="Profile"
        description="Your public identity and the information other people can see"
      >
        <WebsiteMenuRow
          title="Public profile"
          description="See how your profile appears to other people"
          symbol="◎"
          onPress={() => void openWebsite("/profile/me")}
        />
        <WebsiteMenuRow
          title="Edit profile"
          description="Update your display name, photo, bio and personal details"
          symbol="✎"
          onPress={() => void openWebsite("/profile/edit")}
          last
        />
      </AccountMenuSection>

      <AccountMenuSection
        title="Account overview & security"
        description="Your account details, password, recovery methods and sign-in protection"
      >
        <WebsiteMenuRow
          title="Account overview"
          description="Review login credentials, verification, roles, account limits and active sessions"
          symbol="▤"
          onPress={() => void openWebsite("/account")}
        />
        <WebsiteMenuRow
          title="Account settings"
          description="Manage email, phone, account details, security questions and recovery codes"
          symbol="⚙"
          onPress={() => void openWebsite("/account/settings")}
        />
        <WebsiteMenuRow
          title="Change password"
          description="Use your current password to set a new sign-in password"
          symbol="🔑"
          onPress={() => void openWebsite("/account/settings#password")}
        />
        <WebsiteMenuRow
          title="Security centre"
          description="Manage two-step verification, signed-in devices and recent security activity"
          symbol="⌑"
          onPress={() => void openWebsite("/account/security")}
          last
        />
      </AccountMenuSection>

      <AccountMenuSection
        title="Personalise your experience"
        description="Appearance and fan interests are separate settings"
      >
        <WebsiteMenuRow
          title="Preferences & accessibility"
          description="Choose your theme, text size, font, contrast, colour-vision and motion settings"
          symbol="◐"
          onPress={() => void openWebsite("/preferences")}
        />
        <WebsiteMenuRow
          title="Interests & Fan Profile"
          description="Activate or manage your Fan Profile, favourite sports and teams, match reminders and tournament updates"
          symbol="☆"
          onPress={() => void openWebsite("/settings/interests")}
          last
        />
      </AccountMenuSection>

      {user?.contexts && user.contexts.length > 0 ? (
        <AccountMenuSection
          title="Your workspaces"
          description="Personal and organisation access associated with your AFCON360 identity"
        >
          {user.contexts.map((context, index) => (
            <View
              key={(context.public_id || context.type) + ":" + context.label}
              style={[styles.contextRow, index < user.contexts!.length - 1 && styles.contextRowDivider]}
            >
              <View style={styles.contextIcon}>
                <Text style={styles.contextIconText}>{context.type === "individual" ? "◎" : "▦"}</Text>
              </View>
              <View style={styles.contextCopy}>
                <Text style={styles.contextName}>{context.label}</Text>
                <Text style={styles.contextMeta}>
                  {context.type === "individual" ? "Personal account" : (context.role || context.type.replace(/_/g, " "))}
                </Text>
              </View>
            </View>
          ))}
          <WebsiteMenuRow
            title="Switch account or workspace"
            description="Open the Pamoja dashboard to change your active personal or organisation workspace"
            symbol="⇄"
            onPress={() => void openWebsite("/dashboard")}
            last
          />
        </AccountMenuSection>
      ) : null}

      <AccountMenuSection
        title="Partner with Pamoja"
        description="Access opportunities to provide services and grow with the platform"
      >
        <WebsiteMenuRow
          title="Become a partner"
          description="Explore partner onboarding and available service-provider opportunities"
          symbol="＋"
          onPress={() => void openWebsite("/onboarding/choose")}
          last
        />
      </AccountMenuSection>

      <AccountMenuSection
        title="Dashboard"
        description="Open your AFCON360 activity and available workspaces"
      >
        <WebsiteMenuRow
          title="Open dashboard"
          description="View your event schedule, registrations, tickets, activity and discovery feed"
          symbol="▦"
          onPress={() => router.push("/(tabs)/index" as never)}
          external={false}
          last
        />
      </AccountMenuSection>

      <AccountMenuSection
        title="App settings"
        description="Settings for this installed AFCON360 app"
      >
        <WebsiteMenuRow
          title="Version & updates"
          description="View the installed version, check for updates and manage preview connections"
          symbol="⬆"
          onPress={() => router.push("/(service)/settings" as never)}
          external={false}
          last
        />
      </AccountMenuSection>

      <AccountMenuSection
        title="Privacy"
        description="How AFCON360 handles your information"
      >
        <WebsiteMenuRow
          title="Privacy notice"
          description="Read the AFCON360 privacy notice"
          symbol="◇"
          onPress={() => void WebBrowser.openBrowserAsync("https://www.pamoja.space/apps/privacy")}
          last
        />
      </AccountMenuSection>

      <View style={styles.accountActions}>
        <Text style={styles.sectionTitle}>Account actions</Text>
        <Pressable
          accessibilityRole="button"
          onPress={() => router.push("/(service)/delete-account" as never)}
          style={styles.deleteAction}
        >
          <Text style={styles.deleteActionTitle}>Delete AFCON360 account</Text>
          <Text style={styles.deleteActionDescription}>Permanently request account deletion from this device</Text>
          <Text style={styles.deleteActionArrow}>›</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={() => Alert.alert(
            "Sign out",
            "Sign out of AFCON360 on this device?",
            [
              { text: "Cancel", style: "cancel" },
              { text: "Sign out", style: "destructive", onPress: () => { void signOut(); } }
            ]
          )}
          style={styles.signOutAction}
        >
          <Text style={styles.signOutText}>Sign out</Text>
        </Pressable>
      </View>

      <Text style={styles.footerText}>AFCON360 · Your account, your experience.</Text>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  profileHero: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    padding: 17,
    borderRadius: 20,
    backgroundColor: "#D6EBDD",
    borderWidth: 1,
    borderColor: "#E6EAE4",
    overflow: "hidden"
  },
  avatar: {
    width: 62,
    height: 62,
    borderRadius: 21,
    borderWidth: 2,
    borderColor: "#FFCC00",
    backgroundColor: "#0E5B36",
    alignItems: "center",
    justifyContent: "center"
  },
  avatarText: { color: "#FFCC00", fontSize: 22, fontWeight: "900" },
  profileInfo: { flex: 1, minWidth: 0, gap: 3 },
  profileEyebrow: { color: "#1F5C3D", fontSize: 9, fontWeight: "900", letterSpacing: 1.4 },
  profileName: { color: "#093E24", fontSize: 19, lineHeight: 23, fontWeight: "900" },
  profileUsername: { color: "#0E5B36", fontSize: 11, fontWeight: "800" },
  profileEmail: { color: "#53665A", fontSize: 11, marginTop: 2 },
  statusRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 7 },
  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    alignSelf: "flex-start",
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: 99,
    backgroundColor: "rgba(14,91,54,0.10)"
  },
  statusDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: "#75D39A" },
  statusText: { color: "#0E5B36", fontSize: 8, fontWeight: "900", letterSpacing: 0.5 },
  verifiedPill: { backgroundColor: "#E8F4EC" },
  pendingPill: { backgroundColor: "#FFF4D5" },
  verifiedText: { color: "#0E5B36" },
  pendingText: { color: "#80611A" },
  contextRow: { minHeight: 58, flexDirection: "row", alignItems: "center", gap: 11, paddingHorizontal: 12, paddingVertical: 9 },
  contextRowDivider: { borderBottomWidth: 1, borderBottomColor: palette.border },
  contextIcon: { width: 38, height: 38, borderRadius: 12, alignItems: "center", justifyContent: "center", backgroundColor: "#E7F1E9" },
  contextIconText: { color: "#175D37", fontSize: 19, fontWeight: "900" },
  contextCopy: { flex: 1, minWidth: 0, gap: 2 },
  contextName: { color: palette.ink, fontSize: 12, fontWeight: "900" },
  contextMeta: { color: palette.muted, fontSize: 10, textTransform: "capitalize" },
  section: { gap: 9 },
  sectionHeading: { gap: 3 },
  sectionTitle: { color: palette.ink, fontSize: 14, fontWeight: "900", letterSpacing: 0.3 },
  sectionDescription: { color: palette.muted, fontSize: 11, lineHeight: 16 },
  menuCard: {
    overflow: "hidden",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: palette.border,
    backgroundColor: palette.surface
  },
  menuRow: {
    minHeight: 77,
    flexDirection: "row",
    alignItems: "center",
    gap: 11,
    paddingHorizontal: 12,
    paddingVertical: 11
  },
  menuRowDivider: { borderBottomWidth: 1, borderBottomColor: palette.border },
  menuRowPressed: { backgroundColor: "#F1F6F2" },
  menuIcon: {
    width: 42,
    height: 42,
    borderRadius: 13,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#E7F1E9"
  },
  menuIconText: { color: "#175D37", fontSize: 20, fontWeight: "800" },
  menuCopy: { flex: 1, minWidth: 0, gap: 2 },
  menuTitle: { color: palette.ink, fontSize: 12, fontWeight: "900" },
  menuDescription: { color: palette.muted, fontSize: 10, lineHeight: 15 },
  menuHint: { color: "#477655", fontSize: 8, fontWeight: "900", letterSpacing: 0.5, marginTop: 2 },
  menuArrow: { color: "#477655", fontSize: 19, fontWeight: "700", paddingHorizontal: 3 },
  deleteAction: {
    minHeight: 68,
    padding: 13,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#F0D6D4",
    backgroundColor: "#FFF8F7",
    justifyContent: "center"
  },
  deleteActionTitle: { color: "#9A342D", fontSize: 12, fontWeight: "900" },
  deleteActionDescription: { color: "#9B6A65", fontSize: 10, marginTop: 3, paddingRight: 20 },
  deleteActionArrow: { position: "absolute", right: 14, top: 17, color: "#9A342D", fontSize: 20 },
  signOutAction: {
    minHeight: 46,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: palette.border,
    backgroundColor: palette.surface,
    alignItems: "center",
    justifyContent: "center"
  },
  accountActions: { gap: 9, paddingTop: 2 },
  footerText: { color: palette.muted, textAlign: "center", fontSize: 10, paddingBottom: 4 },
  signOutText: { color: palette.ink, fontSize: 12, fontWeight: "900" },
});
