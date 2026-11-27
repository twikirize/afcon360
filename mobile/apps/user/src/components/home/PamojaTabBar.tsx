import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { PamojaMark } from '../PamojaMark';

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
        <LinearGradient
          colors={fabFocused ? (['#FFE785', '#F7C815', '#C98F00'] as const) : (['#C9A227', '#8A6A12'] as const)}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.fabRing}
        >
          <LinearGradient
            colors={['#0C4527', '#04210F'] as const}
            start={{ x: 0.2, y: 0 }}
            end={{ x: 0.8, y: 1 }}
            style={styles.fabFace}
          >
            <PamojaMark size={22} showLeaf={false} />
          </LinearGradient>
        </LinearGradient>
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
    overflow: 'hidden',
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
  fabItem: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
  fabRing: {
    width: 38,
    height: 38,
    borderRadius: 19,
    padding: 2,
    // Dropped below the resting line of the icon row. translateY is 6, not 8,
    // because the larger ring's bottom edge must stay on the line the smaller
    // one used: offset = translateY + radius = 25. With paddingVertical 6 and
    // `overflow: hidden`, this clips ~4pt of the circle, exactly as before.
    transform: [{ translateY: 6 }],
    alignItems: 'center',
    justifyContent: 'center',
  },
  fabFace: {
    flex: 1,
    width: '100%',
    borderRadius: 17,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default PamojaTabBar;
