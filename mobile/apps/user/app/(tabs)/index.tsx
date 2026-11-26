import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshControl, StyleSheet, Text, View } from 'react-native';
import Animated, { useSharedValue, useAnimatedScrollHandler } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { getSelectedApiBaseUrl } from '../../src/services/api';
import { userOfflineRepository } from '../../src/offline/repositories';
import { useAuth } from '../../src/auth/AuthProvider';
import { spacing, radii, homeDesign } from '../../src/theme/tokens';
import {
  HomeHeader,
  HomeSearchBar,
  HomeHeroBanner,
  HomeServiceGrid,
  WalletCard,
  AdventureShowcase,
  HomeDiscoveryFeed,
  HomeQuickAction,
  BookingsCard,
} from '../../src/components/home';

const SITE = 'https://www.pamoja.space';

export default function UserHome() {
  const router = useRouter();
  const { user, isOffline, lastVerifiedAt, offlineStorageError, retryRestoreSession } = useAuth();
  const [apiBaseUrl, setApiBaseUrl] = useState(SITE);
  const [refreshing, setRefreshing] = useState(false);
  const [feedRefreshKey, setFeedRefreshKey] = useState(0);
  const [cachedFeedAt, setCachedFeedAt] = useState<number | null>(null);
  const requestInFlight = useRef(false);
  const scrollY = useSharedValue(0);
  const onScroll = useAnimatedScrollHandler({ onScroll: (event) => { scrollY.value = event.contentOffset.y; } });

  useEffect(() => {
    let mounted = true;
    void getSelectedApiBaseUrl().then((url) => { if (mounted) setApiBaseUrl(url); }).catch(() => { if (mounted) setApiBaseUrl(SITE); });
    return () => { mounted = false; };
  }, []);

  const onRefresh = useCallback(async () => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    setRefreshing(true);
    setFeedRefreshKey((value) => value + 1);
    try {
      if (user?.public_id) {
        const cachedEntry = await userOfflineRepository.readHomeFeed(user.public_id);
        if (cachedEntry) setCachedFeedAt(cachedEntry.storedAt);
      }
    } catch { /* Keep current content if cache is unavailable. */ }
    setRefreshing(false);
    requestInFlight.current = false;
  }, [user?.public_id]);

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <Animated.ScrollView onScroll={onScroll} scrollEventThrottle={16} contentContainerStyle={styles.scrollContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={homeDesign.gold} colors={[homeDesign.primaryGreen]} />}
        showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
        <View style={styles.scrollViewContent}>
          <HomeHeader />
          {(isOffline || offlineStorageError) ? (
            <View style={styles.offlineBanner}>
              <Text style={styles.offlineTitle}>{isOffline ? 'Offline mode' : 'Offline cache unavailable'}</Text>
              <Text style={styles.offlineText}>
                {cachedFeedAt ? 'Saved highlights from ' + new Date(cachedFeedAt).toLocaleString()
                  : lastVerifiedAt ? 'Account last verified ' + new Date(lastVerifiedAt).toLocaleString()
                  : (offlineStorageError || 'Reconnect to refresh your Pamoja information.')}
              </Text>
              <Text accessibilityRole="button" onPress={() => void retryRestoreSession()} style={styles.retryText}>Retry connection</Text>
            </View>
          ) : null}
          <HomeHeroBanner onExplorePress={() => router.push('/(tabs)/explore' as any)} />
          <HomeSearchBar placeholder="Search destinations, events or services..." />
          <View style={styles.mainContent}>
            <View style={styles.sectionHeading}>
              <Text style={styles.sectionTitle}>Our Services</Text>
              <Text accessibilityRole="button" onPress={() => router.push('/(tabs)/explore' as any)} style={styles.viewAll}>View all  ›</Text>
            </View>
            <HomeServiceGrid />
            <WalletCard />
            <AdventureShowcase />
            <HomeDiscoveryFeed baseUrl={apiBaseUrl} refreshKey={feedRefreshKey} />
            <HomeQuickAction />
            <BookingsCard />
          </View>
        </View>
      </Animated.ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: homeDesign.bgColor },
  scrollContent: { paddingBottom: 100 },
  scrollViewContent: { paddingTop: 0 },
  offlineBanner: { backgroundColor: homeDesign.iconBgGreen, borderRadius: radii.lg, padding: spacing.lg, marginHorizontal: spacing.lg, marginVertical: spacing.md, gap: spacing.sm },
  offlineTitle: { color: homeDesign.primaryGreen, fontSize: 13, fontWeight: '900' },
  offlineText: { color: homeDesign.textGray, fontSize: 11, lineHeight: 16 },
  retryText: { color: homeDesign.primaryGreen, fontSize: 12, fontWeight: '900', marginTop: spacing.xs },
  mainContent: { paddingHorizontal: 20, paddingTop: 22 },
  sectionHeading: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 17 },
  sectionTitle: { fontSize: 30, lineHeight: 36, fontWeight: '900', color: homeDesign.textDark, letterSpacing: -0.8, fontFamily: 'serif' },
  viewAll: { color: homeDesign.primaryGreen, fontSize: 17, fontWeight: '800' },
});
