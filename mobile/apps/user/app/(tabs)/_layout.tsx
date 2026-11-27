import React from 'react';
import { Redirect, Tabs } from 'expo-router';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import { useAuth } from '../../src/auth/AuthProvider';
import { palette } from '@afcon360/mobile-ui';
import { PamojaTabBar } from '../../src/components/home/PamojaTabBar';

export default function UserTabs() {
  const { user, loading, restoreError, retryRestoreSession } = useAuth();
  if (loading) return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.canvas }}><ActivityIndicator color={palette.green} /></View>;
  if (restoreError && !user) return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, backgroundColor: palette.canvas }}><Text style={{ color: palette.ink, textAlign: 'center', lineHeight: 22 }}>{restoreError}</Text><Pressable accessibilityRole="button" onPress={() => void retryRestoreSession()} style={{ marginTop: 16, padding: 14, backgroundColor: palette.green, borderRadius: 10 }}><Text style={{ color: '#FFFFFF', fontWeight: '800' }}>Retry saved session</Text></Pressable></View>;
  if (!user) return <Redirect href="/login" />;
  return (
    <Tabs
      screenOptions={{ headerShown: false }}
      tabBar={(props) => <PamojaTabBar {...(props as any)} />}
    >
      <Tabs.Screen name="index" options={{ title: 'Home' }} />
      <Tabs.Screen name="activity" options={{ title: 'Activity' }} />
      <Tabs.Screen name="explore" options={{ title: 'Explore' }} />
      <Tabs.Screen name="wallet" options={{ title: 'Wallet' }} />
      <Tabs.Screen name="account" options={{ title: 'Account' }} />
    </Tabs>
  );
}
