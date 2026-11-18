import React from "react";
import { Pressable, Text, View, StyleSheet } from "react-native";
import { useAuth } from "../auth/AuthProvider";
import { SearchBar } from "./SearchBar";

type GeminiHomeTopProps = {
  search: string;
  onSearchChange: (value: string) => void;
  onSearchSubmit: (value: string) => void;
  recentSearches: string[];
  onRecentPress: (value: string) => void;
  onClearRecent: () => void;
  onServicePress: (service: string) => void;
  onOpenActivity: () => void;
  onOpenAccount: () => void;
};

function ServiceCard({
  title,
  subtitle,
  icon,
  peach,
  website,
  onPress,
}: {
  title: string;
  subtitle: string;
  icon: string;
  peach?: boolean;
  website?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={website ? "Adventure and tourism on Pamoja website" : title}
      onPress={onPress}
      style={({ pressed }) => [styles.serviceCard, pressed && styles.pressed]}
    >
      <View style={styles.serviceCardTop}>
        <View style={[styles.serviceIconCircle, peach ? styles.peachIcon : styles.mintIcon]}>
          <Text style={styles.serviceIcon}>{icon}</Text>
        </View>
        <Text style={styles.diagonalArrow}>↗</Text>
      </View>
      <Text style={styles.serviceTitle}>{title}</Text>
      <Text style={styles.serviceSubtitle}>{subtitle}</Text>
      {website ? (
        <View style={styles.websiteHint}>
          <Text style={styles.websiteHintText}>TOURISM · WEBSITE</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

export function GeminiHomeTop({
  search,
  onSearchChange,
  onSearchSubmit,
  recentSearches,
  onRecentPress,
  onClearRecent,
  onServicePress,
  onOpenActivity,
  onOpenAccount,
}: GeminiHomeTopProps) {
  const { user } = useAuth();
  const greetingName = user?.display_name || user?.username;

  return (
    <View style={styles.container}>
      <View style={styles.topHeader}>
        <View style={styles.brandRow}>
          <View style={styles.emblemOuter}>
            <View style={styles.emblemInner}>
              <Text style={styles.emblemMark}>△</Text>
            </View>
          </View>
          <Text style={styles.brandTitle}>Pamoja</Text>
        </View>
        <View style={styles.topActions}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Open recent ride activity"
            onPress={onOpenActivity}
            style={styles.circleButton}
          >
            <View style={styles.historyIcon}>
              <View style={styles.historyHands}>
                <View style={styles.historyHandVertical} />
                <View style={styles.historyHandHorizontal} />
              </View>
            </View>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Open account"
            onPress={onOpenAccount}
            style={[styles.circleButton, styles.circleButtonMint]}
          >
            <View style={styles.personIcon}>
              <View style={styles.personHead} />
              <View style={styles.personShoulders} />
            </View>
          </Pressable>
        </View>
      </View>

      <View style={styles.heroStage}>
        <View style={styles.heroCard}>
          <View style={styles.heroGlowOrb} />
          <View style={styles.heroLeft}>
            <Text style={styles.heroEyebrow}>EAST AFRICA</Text>
            <Text style={styles.heroTitle}>Your world,{"\n"}together.</Text>
            <Text style={styles.heroSubtitle}>One app. More to explore.</Text>
            {greetingName ? (
              <Text style={styles.heroGreeting}>Good to see you, {greetingName}.</Text>
            ) : null}
          </View>
          <View style={styles.heroIllustration}>
            <View style={styles.sunHalo}>
              <View style={styles.sunDot} />
            </View>
            <View style={styles.skyline}>
              <View style={[styles.tower, { height: 40 }]} />
              <View style={[styles.tower, { height: 58, backgroundColor: "#5D9A74" }]} />
              <View style={[styles.tower, { height: 34 }]} />
              <View style={[styles.tower, { height: 50, backgroundColor: "#498762" }]} />
            </View>
            <View style={styles.travelerRow}>
              <View style={styles.travelerCircle}>
                <View style={styles.peopleGlyph}>
                  <View style={styles.peopleHeadLeft} />
                  <View style={styles.peopleHeadRight} />
                  <View style={styles.peopleBodyLeft} />
                  <View style={styles.peopleBodyRight} />
                </View>
              </View>
            </View>
          </View>
          <View style={styles.heroHillBand} />
        </View>
        <View style={styles.floatingSearch}>
          <SearchBar
            value={search}
            onChangeText={onSearchChange}
            onSubmit={onSearchSubmit}
            placeholder="Search events and tickets..."
            recentSearches={recentSearches}
            onRecentPress={onRecentPress}
            onClearRecent={onClearRecent}
            variant="gemini"
          />
        </View>
      </View>

      <View style={styles.serviceSection}>
        <Text style={styles.sectionTitle}>Make yourself feel at home</Text>
        <View style={styles.serviceGrid}>
          <ServiceCard title="Transport" subtitle="Find your ride" icon="🚌" onPress={() => onServicePress("rides")} />
          <ServiceCard title="Stays" subtitle="Find a place to stay" icon="🛏️" peach onPress={() => onServicePress("stays")} />
          <ServiceCard title="Events & Tickets" subtitle="Events & QR passes" icon="🎟️" peach onPress={() => onServicePress("events")} />
          <ServiceCard title="Adventure" subtitle="Tours, safaris & experiences" icon="🧭" website onPress={() => onServicePress("tourism")} />
        </View>
      </View>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Open Pamoja wallet"
        onPress={() => onServicePress("wallet")}
        style={({ pressed }) => [styles.walletBanner, pressed && styles.pressed]}
      >
        <View style={styles.bannerLeft}>
          <View style={styles.walletIconBox}>
            <View style={styles.walletShape}>
              <View style={styles.walletFlap}>
                <View style={styles.walletDot} />
              </View>
            </View>
          </View>
          <View style={styles.bannerCopy}>
            <Text style={styles.walletTitle}>Your Pamoja wallet</Text>
            <Text style={styles.walletSubtitle}>Payments, all in one place</Text>
          </View>
        </View>
        <Text style={styles.walletChevron}>›</Text>
      </Pressable>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Open your accommodation bookings"
        onPress={() => onServicePress("stays")}
        style={({ pressed }) => [styles.bookingsCard, pressed && styles.pressed]}
      >
        <View style={styles.bannerLeft}>
          <View style={[styles.serviceIconCircle, styles.mintIcon]}>
            <Text style={styles.bookingsIcon}>▦</Text>
          </View>
          <View style={styles.bannerCopy}>
            <Text style={styles.bookingsTitle}>My bookings</Text>
            <Text style={styles.bookingsSubtitle}>Manage your accommodation bookings</Text>
          </View>
        </View>
        <Text style={styles.bookingsChevron}>›</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 14 },
  topHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 2 },
  brandRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  emblemOuter: { width: 34, height: 34, borderRadius: 17, backgroundColor: "#F5B700", alignItems: "center", justifyContent: "center" },
  emblemInner: { width: 28, height: 28, borderRadius: 14, backgroundColor: "#0E5B36", alignItems: "center", justifyContent: "center" },
  emblemMark: { color: "#F5B700", fontSize: 15, fontWeight: "900", marginTop: -2 },
  brandTitle: { fontSize: 22, fontWeight: "800", color: "#0E5B36", letterSpacing: -0.4 },
  topActions: { flexDirection: "row", alignItems: "center", gap: 10 },
  circleButton: { width: 42, height: 42, borderRadius: 21, backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#E6EAE4", alignItems: "center", justifyContent: "center" },
  circleButtonMint: { backgroundColor: "#E6EFE8", borderColor: "transparent" },
  historyIcon: { width: 21, height: 21, borderRadius: 11, borderWidth: 1.8, borderColor: "#0E5B36", alignItems: "center", justifyContent: "center" },
  historyHands: { width: 10, height: 10, position: "relative" },
  historyHandVertical: { position: "absolute", left: 4, top: 0, width: 1.8, height: 5.5, borderRadius: 2, backgroundColor: "#0E5B36" },
  historyHandHorizontal: { position: "absolute", left: 4, top: 4, width: 5, height: 1.8, borderRadius: 2, backgroundColor: "#0E5B36" },
  personIcon: { width: 22, height: 22, alignItems: "center", justifyContent: "center" },
  personHead: { width: 8, height: 8, borderRadius: 4, borderWidth: 1.7, borderColor: "#0E5B36", marginBottom: 2 },
  personShoulders: { width: 17, height: 8, borderWidth: 1.7, borderColor: "#0E5B36", borderBottomWidth: 0, borderTopLeftRadius: 9, borderTopRightRadius: 9 },
  heroStage: { position: "relative", marginBottom: 4, zIndex: 10 },
  heroCard: { backgroundColor: "#D6EBDD", borderRadius: 24, borderWidth: 1, borderColor: "rgba(255,255,255,0.85)", paddingHorizontal: 18, paddingTop: 18, paddingBottom: 80, flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: 204, overflow: "hidden", position: "relative" },
  heroGlowOrb: { position: "absolute", top: -32, right: -20, width: 140, height: 140, borderRadius: 70, backgroundColor: "rgba(252,238,226,0.55)" },
  heroHillBand: { position: "absolute", left: 0, right: 0, bottom: 0, height: 68, backgroundColor: "rgba(30,91,57,0.72)", borderTopLeftRadius: 120, borderTopRightRadius: 80, zIndex: 1 },
  heroLeft: { flex: 1, justifyContent: "space-between", paddingRight: 8, zIndex: 2 },
  heroEyebrow: { fontSize: 10, fontWeight: "700", letterSpacing: 1.2, color: "#1F5C3D", marginBottom: 6 },
  heroTitle: { fontFamily: "serif", fontSize: 25, fontWeight: "700", color: "#093E24", lineHeight: 28, marginBottom: 12 },
  heroSubtitle: { fontSize: 13, fontWeight: "500", color: "#214A34" },
  heroGreeting: { fontSize: 10, fontWeight: "600", color: "#214A34", marginTop: 7 },
  heroIllustration: { width: 118, height: 112, alignItems: "center", justifyContent: "flex-end", position: "relative", zIndex: 2 },
  sunHalo: { position: "absolute", top: 0, left: 20, width: 24, height: 24, borderRadius: 12, backgroundColor: "rgba(245,183,0,0.24)", alignItems: "center", justifyContent: "center" },
  sunDot: { width: 11, height: 11, borderRadius: 5.5, backgroundColor: "#EA8426" },
  skyline: { flexDirection: "row", alignItems: "flex-end", gap: 5, opacity: 0.35, marginBottom: 8 },
  tower: { width: 12, backgroundColor: "#0E5B36", borderTopLeftRadius: 3, borderTopRightRadius: 3 },
  travelerRow: { alignItems: "center" },
  travelerCircle: { width: 56, height: 56, borderRadius: 28, backgroundColor: "#1E5B39", alignItems: "center", justifyContent: "center" },
  peopleGlyph: { width: 36, height: 30, position: "relative" },
  peopleHeadLeft: { position: "absolute", left: 6, top: 1, width: 10, height: 10, borderRadius: 5, backgroundColor: "#FFFFFF" },
  peopleHeadRight: { position: "absolute", right: 5, top: 1, width: 10, height: 10, borderRadius: 5, backgroundColor: "#FFFFFF" },
  peopleBodyLeft: { position: "absolute", left: 1, bottom: 1, width: 21, height: 13, borderTopLeftRadius: 14, borderTopRightRadius: 14, backgroundColor: "#FFFFFF" },
  peopleBodyRight: { position: "absolute", right: 1, bottom: 1, width: 21, height: 13, borderTopLeftRadius: 14, borderTopRightRadius: 14, backgroundColor: "#FFFFFF" },
  floatingSearch: { position: "absolute", left: 12, right: 12, bottom: 14, zIndex: 25 },
  serviceSection: { gap: 0 },
  sectionTitle: { fontFamily: "serif", fontSize: 20, fontWeight: "700", color: "#122419", marginBottom: 12 },
  serviceGrid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", gap: 10, marginBottom: 2 },
  serviceCard: { width: "48.3%", minHeight: 118, backgroundColor: "#FFFFFF", borderRadius: 18, borderWidth: 1, borderColor: "#E6EAE4", padding: 14, justifyContent: "flex-start" },
  serviceCardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 },
  serviceIconCircle: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  mintIcon: { backgroundColor: "#E8F4EC" },
  peachIcon: { backgroundColor: "#FCEEE2" },
  serviceIcon: { fontSize: 19 },
  diagonalArrow: { color: "#4A554C", fontSize: 18, transform: [{ rotate: "0deg" }] },
  serviceTitle: { fontSize: 15, fontWeight: "700", color: "#141915", marginBottom: 2 },
  serviceSubtitle: { fontSize: 11, color: "#6C766E" },
  websiteHint: { alignSelf: "flex-start", marginTop: 5, paddingHorizontal: 6, paddingVertical: 3, borderRadius: 6, backgroundColor: "rgba(23,61,40,0.08)" },
  websiteHintText: { color: "#0E5B36", fontSize: 7, fontWeight: "900", letterSpacing: 0.5 },
  walletBanner: { backgroundColor: "#0E5B36", borderRadius: 18, padding: 15, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  bannerLeft: { flexDirection: "row", alignItems: "center", gap: 12, flex: 1 },
  walletIconBox: { width: 44, height: 44, borderRadius: 12, backgroundColor: "rgba(255,255,255,0.16)", alignItems: "center", justifyContent: "center" },
  walletShape: { width: 26, height: 20, borderWidth: 2, borderColor: "#FFFFFF", borderRadius: 4, position: "relative" },
  walletFlap: { position: "absolute", right: -2, top: 4, width: 12, height: 9, borderWidth: 2, borderColor: "#FFFFFF", borderRadius: 3, backgroundColor: "#0E5B36", alignItems: "center", justifyContent: "center" },
  walletDot: { width: 3, height: 3, borderRadius: 2, backgroundColor: "#FFFFFF" },
  bannerCopy: { flex: 1 },
  walletTitle: { fontSize: 16, fontWeight: "700", color: "#FFFFFF", marginBottom: 2 },
  walletSubtitle: { fontSize: 12, color: "rgba(255,255,255,0.82)" },
  walletChevron: { color: "#FFFFFF", fontSize: 24, marginLeft: 8 },
  bookingsCard: { backgroundColor: "#FFFFFF", borderRadius: 18, borderWidth: 1, borderColor: "#E6EAE4", padding: 14, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  bookingsIcon: { fontSize: 18, color: "#0E5B36" },
  bookingsTitle: { fontSize: 15, fontWeight: "700", color: "#141915", marginBottom: 2 },
  bookingsSubtitle: { fontSize: 11, color: "#6C766E" },
  bookingsChevron: { color: "#6C766E", fontSize: 22 },
  pressed: { opacity: 0.82 },
});
