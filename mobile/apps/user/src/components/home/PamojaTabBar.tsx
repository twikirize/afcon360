import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';

const CenterLogo = () => (
  <Svg
    width="26"
    height="26"
    viewBox="0 0 100 100"
    fill="none"
    stroke="white"
    strokeWidth="5.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <Path d="M 35 85 L 35 45 C 35 20, 50 15, 65 15 C 85 15, 85 45, 65 55 C 55 60, 45 60, 45 60 L 45 85" />
    <Path d="M 45 60 C 45 40, 60 30, 68 30 C 68 45, 55 60, 45 60" />
    <Path d="M 35 50 C 20 50, 20 40, 30 40 C 33 40, 35 45, 35 50" />
  </Svg>
);

type TabIcon = 'home' | 'clipboard-outline' | 'wallet' | 'person-outline';

const TAB_LABELS: Record<string, string> = {
  index: 'Home',
  activity: 'Activity',
  explore: 'Explore',
  wallet: 'Wallet',
  account: 'Account',
};

const TAB_ICONS: Record<string, TabIcon> = {
  index: 'home',
  activity: 'clipboard-outline',
  wallet: 'wallet',
  account: 'person-outline',
};

const TAB_HREF: Record<string, string> = {
  index: '/',
  activity: '/(tabs)/activity',
  explore: '/(tabs)/explore',
  wallet: '/(tabs)/wallet',
  account: '/(tabs)/account',
};

const LEFT_TABS = ['index', 'activity'];
const RIGHT_TABS = ['wallet', 'account'];
const FAB_TAB = 'explore';

interface PamojaTabBarProps {
  state: { index: number; routes: Array<{ key: string; name: string }> };
  // expo-router's vendored bottom tab bar supplies these; it does NOT supply navigation.
  navigateToTab?: (routeKey: string) => void;
  emitter?: {
    emit: (event: { type: 'tabPress'; target: string; canPreventDefault?: boolean }) => {
      defaultPrevented?: boolean;
    };
  };
  insets?: { bottom?: number };
}

export const PamojaTabBar = ({ state, navigateToTab, emitter, insets }: PamojaTabBarProps) => {
  const router = useRouter();
  const safeAreaInsets = useSafeAreaInsets();
  const bottomInset = insets?.bottom ?? safeAreaInsets.bottom;
  const activeName = state.routes[state.index]?.name;
  const fabRoute = state.routes.find((route) => route.name === FAB_TAB);
  const fabFocused = activeName === FAB_TAB;

  const press = (route: { key: string; name: string }, focused: boolean) => {
    const event = emitter?.emit({ type: 'tabPress', target: route.key, canPreventDefault: true });
    if (focused || event?.defaultPrevented) return;
    if (navigateToTab) {
      navigateToTab(route.key);
      return;
    }
    // Defensive fallback: if the navigator ever stops passing navigateToTab, still navigate.
    const href = TAB_HREF[route.name];
    if (href) router.navigate(href as never);
  };

  const renderItem = (name: string) => {
    const route = state.routes.find((entry) => entry.name === name);
    if (!route) return null;
    const focused = activeName === name;
    const color = focused ? '#F7C815' : '#E5E7EB';

    return (
      <TouchableOpacity
        key={route.key}
        style={styles.navItem}
        activeOpacity={0.7}
        accessibilityRole="tab"
        accessibilityLabel={TAB_LABELS[name] ?? name}
        accessibilityState={{ selected: focused }}
        hitSlop={{ top: 8, bottom: 8, left: 6, right: 6 }}
        onPress={() => press(route, focused)}
      >
        <Ionicons name={TAB_ICONS[name] ?? 'ellipse-outline'} size={19} color={color} />
        <Text style={[styles.navText, { color }]}>{TAB_LABELS[name] ?? name}</Text>
        {focused ? <View style={styles.activeIndicator} /> : null}
      </TouchableOpacity>
    );
  };

  const renderFab = () => {
    if (!fabRoute) return null;
    return (
      <TouchableOpacity
        key={fabRoute.key}
        style={styles.fabItem}
        activeOpacity={0.85}
        accessibilityRole="tab"
        accessibilityLabel="Explore Pamoja"
        accessibilityHint="Opens the Explore screen"
        accessibilityState={{ selected: fabFocused }}
        onPress={() => press(fabRoute, fabFocused)}
      >
        <View style={styles.fabWrapper}>
          <View style={[styles.fabGlow, fabFocused ? styles.fabGlowFocused : null]}>
            <View style={[styles.fab, fabFocused ? styles.fabFocused : null]}>
              <CenterLogo />
            </View>
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <View style={[styles.navContainer, { paddingBottom: bottomInset > 0 ? bottomInset + 8 : 16 }]}>
      <LinearGradient
        colors={['rgba(20, 86, 46, 0.98)', 'rgba(4, 33, 15, 0.99)'] as const}
        start={{ x: 0.1, y: 0 }}
        end={{ x: 0.9, y: 1 }}
        style={styles.bottomNav}
      >
        <View style={styles.navGroup}>{LEFT_TABS.map(renderItem)}</View>
        {renderFab()}
        <View style={styles.navGroup}>{RIGHT_TABS.map(renderItem)}</View>
      </LinearGradient>
    </View>
  );
};

const styles = StyleSheet.create({
  navContainer: {
    backgroundColor: 'transparent',
    paddingHorizontal: 14,
    paddingTop: 8,
  },
  bottomNav: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderRadius: 32,
    paddingVertical: 6,
    paddingHorizontal: 8,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255, 255, 255, 0.14)',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0, 0, 0, 0.35)',
    // No overflow: 'hidden' here — the raised centre disc and its gold glow must
    // render outside the bar. The gradient rounds its own corners.
    elevation: 12,
    shadowColor: '#04210F',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.35,
    shadowRadius: 20,
  },
  navGroup: {
    flex: 1,
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  navItem: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 4,
    paddingHorizontal: 6,
    minWidth: 52,
  },
  navText: {
    fontSize: 9.5,
    fontWeight: '500',
    marginTop: 3,
  },
  activeIndicator: {
    position: 'absolute',
    bottom: -1,
    width: 12,
    height: 2,
    backgroundColor: '#F7C815',
    borderRadius: 2,
  },
  // The disc is 46pt tall including its 2pt halo, so it sits inside the pill's
  // own height beside the 19pt tab icons instead of rising above them.
  fabItem: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  fabWrapper: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  fabGlow: {
    padding: 2,
    borderRadius: 23,
    backgroundColor: 'rgba(247,200,21,0.2)',
  },
  fabGlowFocused: {
    backgroundColor: 'rgba(247,200,21,0.34)',
  },
  fab: {
    width: 42,
    height: 42,
    borderRadius: 21,
    // Lighter than the bar's darkest end so the disc reads as a raised control
    // instead of a hole in the pill.
    backgroundColor: '#0C4527',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#f7c815',
    shadowColor: '#f7c815',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.5,
    shadowRadius: 10,
    elevation: 6,
  },
  // Selected cue only: brighter gold rim and a wider cast. The disc interior
  // (dark green + white mark) stays exactly as specified.
  fabFocused: {
    borderColor: '#FFE785',
    shadowOpacity: 0.7,
    shadowRadius: 14,
    elevation: 8,
  },
});

export default PamojaTabBar;
