import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useAuth } from '../../auth/AuthProvider';
import { homeDesign } from '../../theme/tokens';

const styles = StyleSheet.create({
  container: {
    minHeight: 76,
    paddingHorizontal: 22,
    paddingVertical: 12,
    backgroundColor: homeDesign.primaryGreen,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  mark: {
    width: 42, height: 42, borderRadius: 21,
    borderWidth: 1.5, borderColor: homeDesign.gold,
    alignItems: 'center', justifyContent: 'center',
  },
  brandName: {
    color: '#FFFDF6', fontSize: 27, fontWeight: '800',
    letterSpacing: -0.8, fontFamily: 'serif',
  },
  tagline: {
    color: '#E7C76D', fontSize: 9, fontWeight: '700',
    letterSpacing: 0.8, marginTop: -1,
  },
  actions: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  iconButton: {
    width: 40, height: 40, borderRadius: 20,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.22)',
    alignItems: 'center', justifyContent: 'center',
  },
  avatar: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: '#E6C56B', alignItems: 'center', justifyContent: 'center',
    borderWidth: 2, borderColor: '#E6C56B',
  },
});

export const HomeHeader = () => {
  const router = useRouter();
  const { user } = useAuth();

  return (
    <View style={styles.container}>
      <View style={styles.brand}>
        <View style={styles.mark}>
          <MaterialIcons name="public" size={25} color={homeDesign.gold} />
        </View>
        <View>
          <Text style={styles.brandName}>Pamoja</Text>
          <Text style={styles.tagline}>TOGETHER, EVERYWHERE.</Text>
        </View>
      </View>
      <View style={styles.actions}>
        <TouchableOpacity
          style={styles.iconButton}
          onPress={() => router.push('/notifications' as any)}
          accessibilityRole="button"
          accessibilityLabel="Notifications"
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <MaterialIcons name="notifications-none" size={23} color="#FFFFFF" />
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.avatar}
          onPress={() => router.push('/(tabs)/account' as any)}
          accessibilityRole="button"
          accessibilityLabel={user ? 'Open your account' : 'Open account'}
        >
          <MaterialIcons name="person-outline" size={23} color={homeDesign.primaryGreen} />
        </TouchableOpacity>
      </View>
    </View>
  );
};

export default HomeHeader;