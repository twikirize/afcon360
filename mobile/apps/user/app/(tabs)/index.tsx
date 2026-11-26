import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshControl, StyleSheet, Text, View, StatusBar } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedScrollHandler,
} from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { getSelectedApiBaseUrl } from '../../src/services/api';
import { userOfflineRepository } from '../../src/offline/repositories';
import { useAuth } from '../../src/auth/AuthProvider';
import { spacing, radii } from '../../src/theme/tokens';
import { homeDesign } from '../../src/theme/tokens';
import {
  HomeHeader,
  HomeSearchBar,
  HomeHeroBanner,
  HomeServiceGrid,
  OurServicesHeader,
  WalletCard,
  BookingsCard,
} from '../../src/components/home';

const SITE = 'https://www.pamoja.space';

export default function UserHome() {
  const router = useRouter();
  const { user, isOffline, lastVerifiedAt, offlineStorageError, retryRestoreSession } = useAuth();
  const [apiBaseUrl, setApiBaseUrl] = useState(SITE);
  const [refreshing, setRefreshing] = useState(false);
  const [cachedFeedAt, setCachedFeedAt] = useState<number | null>(null);
  const requestInFlight = useRef(false);

  const scrollY = useSharedValue(0);
  const onScroll = useAnimatedScrollHandler({
    onScroll: (event) => {
      scrollY.value = event.contentOffset.y;
    },
  });

  useEffect(() => {
    let mounted = true;
    void getSelectedApiBaseUrl().then((url) => {
      if (mounted) setApiBaseUrl(url);
    }).catch(() => {
      if (mounted) setApiBaseUrl(SITE);
    });
    return () => { mounted = false; };
  }, []);

  const onRefresh = useCallback(async () => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    setRefreshing(true);

    try {
      if (user?.public_id) {
        const cachedEntry = await userOfflineRepository.readHomeFeed(user.public_id);
        if (cachedEntry) {
          setCachedFeedAt(cachedEntry.storedAt);
        }
      }
    } catch {
      // Ignore cache read errors
    }

    setRefreshing(false);
    requestInFlight.current = false;
  }, [user?.public_id]);

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <StatusBar barStyle="dark-content" />
      <Animated.ScrollView
        onScroll={onScroll}
        scrollEventThrottle={16}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={homeDesign.primaryGreen}
            colors={[homeDesign.primaryGreen]}
          />
        }
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.scrollViewContent}>
          <HomeHeader />

          {(isOffline || offlineStorageError) ? (
            <View style={styles.offlineBanner}>
              <Text style={styles.offlineTitle}>
                {isOffline ? 'Offline mode' : 'Offline cache unavailable'}
              </Text>
              <Text style={styles.offlineText}>
                {cachedFeedAt
                  ? 'Saved highlights from ' + new Date(cachedFeedAt).toLocaleString()
                  : lastVerifiedAt
                  ? 'Account last verified ' + new Date(lastVerifiedAt).toLocaleString()
                  : (offlineStorageError || 'Reconnect to refresh your Pamoja information.')}
              </Text>
              <Text
                accessibilityRole="button"
                onPress={() => void retryRestoreSession()}
                style={styles.retryText}
              >
                Retry connection
              </Text>
            </View>
          ) : null}

          <HomeHeroBanner onExplorePress={() => router.push('/(tabs)/explore' as any)} />

          <HomeSearchBar placeholder="Find a ride, event or stay..." />

          <View style={styles.mainContent}>
            <OurServicesHeader onViewAllPress={() => router.push('/(tabs)/explore' as any)} />

            <HomeServiceGrid />

            <WalletCard />

            <BookingsCard />
          </View>
        </View>
      </Animated.ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: homeDesign.bgColor,
  },
  scrollContent: {
    paddingTop: 35,
    paddingBottom: 35,
    paddingHorizontal: 24,
  },
  scrollViewContent: {
    paddingTop: spacing.sm,
  },
  offlineBanner: {
    backgroundColor: homeDesign.heroBg,
    borderRadius: radii.lg,
    padding: spacing.lg,
    marginHorizontal: spacing.lg,
    gap: spacing.sm,
  },
  offlineTitle: {
    color: homeDesign.primaryGreen,
    fontSize: 13,
    fontWeight: '900',
  },
  offlineText: {
    color: homeDesign.textGray,
    fontSize: 11,
    lineHeight: 16,
  },
  retryText: {
    color: homeDesign.primaryGreen,
    fontSize: 12,
    fontWeight: '900',
    marginTop: spacing.xs,
  },
  mainContent: {
    paddingHorizontal: 0,
    paddingTop: 0,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: homeDesign.textDark,
    marginBottom: 16,
  },
});