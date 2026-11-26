import React from 'react';
import { Redirect, Tabs } from 'expo-router';
import { MaterialIcons } from '@expo/vector-icons';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../../src/auth/AuthProvider';
import { palette } from '@afcon360/mobile-ui';
import { homeDesign } from '../../src/theme/tokens';

type TabIconName = 'home' | 'event-available' | 'account-balance-wallet' | 'person-outline';

const tabIcons: Record<string, TabIconName> = {
  index: 'home',
  activity: 'event-available',
  wallet: 'account-balance-wallet',
  account: 'person-outline',
};

const tabLabels: Record<string, string> = {
  index: 'Home',
  activity: 'Activity',
  wallet: 'Wallet',
  account: 'Account',
};

export default function UserTabs() {
  const insets = useSafeAreaInsets();
  const { user, loading, restoreError, retryRestoreSession } = useAuth();
  if (loading) return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.canvas }}><ActivityIndicator color={palette.green} /></View>;
  if (restoreError && !user) return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, backgroundColor: palette.canvas }}><Text style={{ color: palette.ink, textAlign: 'center', lineHeight: 22 }}>{restoreError}</Text><Pressable accessibilityRole="button" onPress={() => void retryRestoreSession()} style={{ marginTop: 16, padding: 14, backgroundColor: palette.green, borderRadius: 10 }}><Text style={{ color: '#FFFFFF', fontWeight: '800' }}>Retry saved session</Text></Pressable></View>;
  if (!user) return <Redirect href="/login" />;
  return (
    <Tabs
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: homeDesign.peachIcon,
        tabBarInactiveTintColor: palette.muted,
        tabBarLabelStyle: { fontSize: 11, fontWeight: '500' },
        tabBarStyle: {
          height: 66 + insets.bottom,
          paddingTop: 12,
          paddingBottom: insets.bottom > 0 ? insets.bottom + 8 : 30,
          borderTopWidth: 1,
          borderTopColor: homeDesign.borderColor,
          backgroundColor: homeDesign.cardBg,
        },
        tabBarIcon: ({ color, focused }) => (
          <View
            style={{
              backgroundColor: focused ? homeDesign.peachActive : 'transparent',
              borderRadius: 20,
              paddingHorizontal: 16,
              paddingVertical: 4,
            }}
          >
            <MaterialIcons
              name={tabIcons[route.name] ?? 'home'}
              size={24}
              color={typeof color === 'number' ? String(color) : (color ?? palette.muted)}
            />
          </View>
        ),
      })}
    >
      <Tabs.Screen name="index" options={{ title: tabLabels.index }} />
      <Tabs.Screen name="activity" options={{ title: tabLabels.activity }} />
      <Tabs.Screen name="wallet" options={{ title: tabLabels.wallet }} />
      <Tabs.Screen name="account" options={{ title: tabLabels.account }} />
    </Tabs>
  );
}