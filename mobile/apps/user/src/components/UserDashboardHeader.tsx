import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View
} from "react-native";
import { usePathname, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as WebBrowser from "expo-web-browser";
import { useAuth } from "../auth/AuthProvider";
import { getSelectedApiBaseUrl } from "../services/api";

const SITE = "https://www.pamoja.space";
const BLUE = "#0E4CCD";
const BLUE_SOFT = "#DBEAFE";
const INK = "#1A1A1A";
const MUTED = "#6C757D";
const BORDER = "#E9ECEF";
const CANVAS = "#F2F4F2";

type MenuKey =
  | "home" | "events" | "wallet" | "rides" | "stays" | "tourism"
  | "partner" | "public-profile" | "account" | "edit-profile" | "settings";

type MenuItem = {
  key: MenuKey;
  label: string;
  symbol: string;
  group: "journey" | "account";
  route?: string;
  webPath?: string;
};

function safeWebsiteUrl(path: string, baseUrl: string): string | null {
  if (!path || !baseUrl) return null;
  try {
    const base = new URL(baseUrl);
    const target = new URL(path, base.origin + "/");
    if (target.origin !== base.origin) return null;
    if (target.protocol !== "https:" && target.protocol !== "http:") return null;
    return target.toString();
  } catch {
    return null;
  }
}

const MENU_ITEMS: MenuItem[] = [
  { key: "home", label: "Home", symbol: "⌂", group: "journey", route: "/(tabs)" },
  { key: "events", label: "Events", symbol: "▣", group: "journey", route: "/(service)/events" },
  { key: "wallet", label: "Wallet", symbol: "◈", group: "journey", route: "/(tabs)/wallet" },
  { key: "rides", label: "Rides", symbol: "↗", group: "journey", route: "/(service)/ride" },
  { key: "stays", label: "Stays", symbol: "⌂", group: "journey", route: "/(service)/stays" },
  { key: "tourism", label: "Tourism", symbol: "⌖", group: "journey", webPath: "/tourism" },
  { key: "partner", label: "Become a Partner", symbol: "＋", group: "account", webPath: "/onboarding/choose" },
  { key: "public-profile", label: "Public Profile", symbol: "▤", group: "account", webPath: "/profile/me" },
  { key: "account", label: "Account", symbol: "○", group: "account", route: "/(tabs)/account" },
  { key: "edit-profile", label: "Edit Profile", symbol: "✎", group: "account", webPath: "/profile/edit" },
  { key: "settings", label: "Settings", symbol: "⚙", group: "account", webPath: "/theme/preferences" }
];

export function UserDashboardHeader() {
  const router = useRouter();
  const pathname = usePathname();
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [websiteBaseUrl, setWebsiteBaseUrl] = useState(SITE);
  const contexts = useMemo(() => user?.contexts ?? [], [user?.contexts]);
  const displayName = user?.display_name || user?.username || "AFCON360 User";
  const initial = displayName.trim().charAt(0).toUpperCase() || "U";
  const activeKey: MenuKey = useMemo(() => {
    const path = pathname.toLowerCase();
    if (path.includes("events")) return "events";
    if (path.includes("wallet")) return "wallet";
    if (path.includes("ride")) return "rides";
    if (path.includes("stays")) return "stays";
    if (path.includes("tourism")) return "tourism";
    if (path.includes("account")) return "account";
    return "home";
  }, [pathname]);

  useEffect(() => {
    let active = true;
    void getSelectedApiBaseUrl().then(url => {
      if (active && url) setWebsiteBaseUrl(url);
    }).catch(() => {
      if (active) setWebsiteBaseUrl(SITE);
    });
    return () => { active = false; };
  }, []);

  const openWebsite = (path: string) => {
    const target = safeWebsiteUrl(path, websiteBaseUrl);
    if (target) void WebBrowser.openBrowserAsync(target);
    else Alert.alert("Website unavailable", "AFCON360 could not resolve the selected server for this page. Check your connection settings and try again.");
  };

  const activate = (item: MenuItem) => {
    setDrawerOpen(false);
    if (item.route) {
      router.push(item.route as never);
      return;
    }
    if (item.webPath) openWebsite(item.webPath);
  };

  const chooseContext = (context: { type: string; label: string; role?: string | null }) => {
    setAccountOpen(false);
    if (context.type === "personal") {
      Alert.alert("Personal account", "The AFCON360 User app is currently operating in your personal account.");
      return;
    }
    Alert.alert(
      "Continue on AFCON360 website",
      "Your " + context.label + " access is recognised, but changing operating context is not yet available through the native mobile API. Open the website to switch context securely.",
      [
        { text: "Cancel", style: "cancel" },
        { text: "Open website", onPress: () => openWebsite("/user/dashboard") }
      ]
    );
  };

  return (
    <>
      <View style={styles.header}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Open dashboard menu"
          onPress={() => setDrawerOpen(true)}
          style={styles.headerButton}
        >
          <Text style={styles.headerButtonText}>☰</Text>
        </Pressable>
        <View style={styles.headerGreeting}>
          <Text numberOfLines={1} style={styles.headerGreetingTitle}>Welcome back, {displayName}</Text>
          <Text numberOfLines={1} style={styles.headerGreetingSub}>Your AFCON 360 overview for today</Text>
        </View>
        <View style={styles.headerActions}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Search events"
            onPress={() => router.push({ pathname: "/(service)/events", params: { query: "" } } as never)}
            style={styles.headerButton}
          >
            <Text style={styles.headerActionText}>⌕</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Open notifications"
            onPress={() => openWebsite("/notifications")}
            style={styles.headerButton}
          >
            <Text style={styles.headerActionText}>♧</Text>
            <View style={styles.notificationDot} />
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Account and operating contexts"
            onPress={() => setAccountOpen(true)}
            style={styles.avatarButton}
          >
            <Text style={styles.avatarText}>{initial}</Text>
            <Text style={styles.chevron}>⌄</Text>
          </Pressable>
        </View>
      </View>

      <Modal
        visible={drawerOpen}
        transparent
        animationType="fade"
        statusBarTranslucent
        onRequestClose={() => setDrawerOpen(false)}
      >
        <View style={styles.modalRoot}>
          <Pressable style={styles.scrim} onPress={() => setDrawerOpen(false)} />
          <View style={[styles.drawer, { paddingTop: insets.top + 12, paddingBottom: Math.max(18, insets.bottom + 12) }]}>
            <View style={styles.drawerTop}>
              <View style={styles.brand}>
                <View style={styles.brandMark}><Text style={styles.brandMarkText}>360</Text></View>
                <View>
                  <Text style={styles.brandName}>AFCON 360</Text>
                  <Text style={styles.brandCaption}>YOUR FAN WORKSPACE</Text>
                </View>
              </View>
              <Pressable accessibilityRole="button" accessibilityLabel="Close menu" onPress={() => setDrawerOpen(false)} style={styles.closeButton}>
                <Text style={styles.closeText}>×</Text>
              </Pressable>
            </View>

            <View style={styles.userCard}>
              <View style={styles.userAvatar}><Text style={styles.userAvatarText}>{initial}</Text></View>
              <View style={{ flex: 1, gap: 2 }}>
                <Text numberOfLines={1} style={styles.userName}>{displayName}</Text>
                <Text numberOfLines={1} style={styles.userEmail}>{user?.email || "Signed in to AFCON360"}</Text>
              </View>
            </View>

            <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.menuScroll}>
              <Text style={styles.menuSectionLabel}>YOUR JOURNEY</Text>
              {MENU_ITEMS.filter(item => item.group === "journey").map(item => (
                <Pressable
                  key={item.key}
                  accessibilityRole="button"
                  accessibilityHint={item.webPath ? "Opens on AFCON360 website" : undefined}
                  onPress={() => activate(item)}
                  style={({ pressed }) => [styles.menuItem, item.key === activeKey && styles.menuItemActive, pressed && styles.menuItemPressed]}
                >
                  <Text style={styles.menuSymbol}>{item.symbol}</Text>
                  <Text style={[styles.menuLabel, item.key === activeKey && styles.menuLabelActive]}>{item.label}</Text>
                  {item.webPath ? <Text style={styles.webTag}>WEB</Text> : null}
                  <Text style={styles.menuArrow}>›</Text>
                </Pressable>
              ))}
              <View style={styles.menuDivider} />
              <Text style={styles.menuSectionLabel}>ACCOUNT & PREFERENCES</Text>
              {MENU_ITEMS.filter(item => item.group === "account").map(item => (
                <Pressable
                  key={item.key}
                  accessibilityRole="button"
                  onPress={() => activate(item)}
                  style={({ pressed }) => [styles.menuItem, pressed && styles.menuItemPressed]}
                >
                  <Text style={styles.menuSymbol}>{item.symbol}</Text>
                  <Text style={styles.menuLabel}>{item.label}</Text>
                  <Text style={styles.menuArrow}>›</Text>
                </Pressable>
              ))}
            </ScrollView>
            <Text style={styles.drawerFoot}>AFCON360 · East Africa & Beyond</Text>
          </View>
        </View>
      </Modal>

      <Modal
        visible={accountOpen}
        transparent
        animationType="fade"
        statusBarTranslucent
        onRequestClose={() => setAccountOpen(false)}
      >
        <Pressable style={styles.accountScrim} onPress={() => setAccountOpen(false)}>
          <Pressable style={[styles.accountPanel, { marginTop: insets.top + 54 }]} onPress={() => undefined}>
            <View style={styles.accountPanelHead}>
              <View style={styles.userAvatar}><Text style={styles.userAvatarText}>{initial}</Text></View>
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={styles.userName}>{displayName}</Text>
                <Text style={styles.userEmail}>{user?.email || user?.username || ""}</Text>
              </View>
            </View>
            <Text style={styles.menuSectionLabel}>OPERATING CONTEXTS</Text>
            {contexts.length ? contexts.map((context, index) => (
              <Pressable
                key={context.type + ":" + (context.public_id || "personal") + ":" + index}
                accessibilityRole="button"
                onPress={() => chooseContext(context)}
                style={styles.contextItem}
              >
                <View style={styles.contextIcon}><Text style={styles.contextIconText}>{context.type === "personal" ? "○" : context.type === "organisation" ? "▦" : context.type === "driver" ? "↗" : context.type === "event" ? "▣" : "◇"}</Text></View>
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={styles.contextName}>{context.label}</Text>
                  <Text style={styles.contextRole}>{context.role ? context.role.replace(/_/g, " ") : context.type}</Text>
                </View>
                <Text style={styles.menuArrow}>›</Text>
              </Pressable>
            )) : (
              <Text style={styles.emptyContext}>Your personal AFCON360 account is active.</Text>
            )}
            <View style={styles.menuDivider} />
            <Pressable style={styles.accountLink} onPress={() => { setAccountOpen(false); router.push("/(tabs)/account" as never); }}>
              <Text style={styles.menuSymbol}>○</Text><Text style={styles.menuLabel}>Account settings</Text>
            </Pressable>
            <Pressable style={styles.accountLink} onPress={() => { setAccountOpen(false); openWebsite("/user/dashboard"); }}>
              <Text style={styles.menuSymbol}>↗</Text><Text style={styles.menuLabel}>Open website dashboard</Text>
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  header: {
    height: 62,
    paddingHorizontal: 12,
    backgroundColor: "#FFFFFF",
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
    flexDirection: "row",
    alignItems: "center",
    gap: 8
  },
  headerButton: {
    width: 38,
    height: 40,
    borderRadius: 11,
    alignItems: "center",
    justifyContent: "center"
  },
  headerButtonText: { color: INK, fontSize: 22, fontWeight: "700" },
  headerActionText: { color: INK, fontSize: 25, fontWeight: "500" },
  brand: { flexDirection: "row", alignItems: "center", gap: 8, flex: 1 },
  brandMark: { width: 34, height: 34, borderRadius: 10, backgroundColor: BLUE, alignItems: "center", justifyContent: "center" },
  brandMarkText: { color: "#FFFFFF", fontSize: 10, fontWeight: "900", letterSpacing: 0.6 },
  brandName: { color: INK, fontSize: 14, fontWeight: "900", letterSpacing: 0.3 },
  brandCaption: { color: MUTED, fontSize: 8, fontWeight: "800", letterSpacing: 1.1, marginTop: 1 },
  headerGreeting: { flex: 1, minWidth: 0, gap: 2 },
  headerGreetingTitle: { color: INK, fontSize: 12, fontWeight: "900" },
  headerGreetingSub: { color: MUTED, fontSize: 9 },
  headerActions: { flexDirection: "row", alignItems: "center", gap: 2 },
  notificationDot: { position: "absolute", width: 6, height: 6, borderRadius: 3, backgroundColor: BLUE, top: 8, right: 8 },
  avatarButton: { flexDirection: "row", alignItems: "center", gap: 3, paddingLeft: 4, paddingRight: 2 },
  avatarText: { width: 31, height: 31, borderRadius: 16, backgroundColor: BLUE_SOFT, color: BLUE, textAlign: "center", textAlignVertical: "center", overflow: "hidden", fontSize: 13, fontWeight: "900" },
  chevron: { color: MUTED, fontSize: 14 },
  modalRoot: { flex: 1, flexDirection: "row", backgroundColor: "rgba(18, 27, 37, 0.30)" },
  scrim: { ...StyleSheet.absoluteFillObject },
  drawer: {
    width: 306,
    maxWidth: "88%",
    backgroundColor: "#FFFFFF",
    paddingHorizontal: 17,
    borderTopRightRadius: 18,
    borderBottomRightRadius: 18,
    shadowColor: "#000000",
    shadowOpacity: 0.16,
    shadowRadius: 18,
    elevation: 16
  },
  drawerTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 18 },
  closeButton: { width: 34, height: 34, borderRadius: 17, backgroundColor: CANVAS, alignItems: "center", justifyContent: "center" },
  closeText: { color: INK, fontSize: 24, lineHeight: 27 },
  userCard: { flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: CANVAS, borderRadius: 14, padding: 11, marginBottom: 20 },
  userAvatar: { width: 38, height: 38, borderRadius: 19, backgroundColor: BLUE_SOFT, alignItems: "center", justifyContent: "center" },
  userAvatarText: { color: BLUE, fontSize: 16, fontWeight: "900" },
  userName: { color: INK, fontSize: 13, fontWeight: "900" },
  userEmail: { color: MUTED, fontSize: 10 },
  menuScroll: { paddingBottom: 14 },
  menuSectionLabel: { color: MUTED, fontSize: 9, fontWeight: "900", letterSpacing: 1.2, marginBottom: 8, marginTop: 3 },
  menuItem: { height: 46, flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 10, borderRadius: 11 },
  menuItemPressed: { backgroundColor: BLUE_SOFT },
  menuItemActive: { backgroundColor: "#EEF4FF", borderWidth: 1, borderColor: "#C7D9FF" },
  menuSymbol: { color: BLUE, fontSize: 18, fontWeight: "800", width: 24, textAlign: "center" },
  menuLabel: { color: INK, fontSize: 13, fontWeight: "700", flex: 1 },
  menuLabelActive: { color: BLUE, fontWeight: "900" },
  webTag: { color: BLUE, fontSize: 8, fontWeight: "900", letterSpacing: 0.6, backgroundColor: BLUE_SOFT, paddingHorizontal: 5, paddingVertical: 3, borderRadius: 5 },
  menuArrow: { color: MUTED, fontSize: 20 },
  menuDivider: { height: 1, backgroundColor: BORDER, marginVertical: 12 },
  drawerFoot: { color: MUTED, fontSize: 10, textAlign: "center", paddingTop: 12, borderTopWidth: 1, borderTopColor: BORDER },
  accountScrim: { flex: 1, backgroundColor: "rgba(18, 27, 37, 0.20)", alignItems: "flex-end", paddingHorizontal: 12 },
  accountPanel: { width: 310, maxWidth: "100%", backgroundColor: "#FFFFFF", borderRadius: 16, borderWidth: 1, borderColor: BORDER, padding: 15, shadowColor: "#000000", shadowOpacity: 0.14, shadowRadius: 16, elevation: 16 },
  accountPanelHead: { flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 16 },
  contextItem: { minHeight: 54, flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 7 },
  contextIcon: { width: 32, height: 32, borderRadius: 10, backgroundColor: CANVAS, alignItems: "center", justifyContent: "center" },
  contextIconText: { color: BLUE, fontSize: 17, fontWeight: "800" },
  contextName: { color: INK, fontSize: 12, fontWeight: "800" },
  contextRole: { color: MUTED, fontSize: 10, textTransform: "capitalize" },
  emptyContext: { color: MUTED, fontSize: 12, lineHeight: 18, paddingVertical: 10 },
  accountLink: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: 42 }
});
