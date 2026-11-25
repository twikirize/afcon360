import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Platform } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useAuth } from '../../auth/AuthProvider';
import { spacing, typography } from '../../theme/tokens';
import { homeDesign } from '../../theme/tokens';

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 12,
  },
  logoContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  logoIcon: {
    width: 28,
    height: 28,
    backgroundColor: homeDesign.primaryGreen,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
  },
  logoText: {
    fontSize: 22,
    fontWeight: '700',
    color: homeDesign.textDark,
    letterSpacing: -0.5,
  },
  headerActions: {
    flexDirection: 'row',
    gap: 12,
  },
  iconButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: homeDesign.borderColor,
    justifyContent: 'center',
    alignItems: 'center',
  },
});

type MaterialIconName = 'park' | 'notifications' | 'person-outline';

export const HomeHeader = () => {
  const router = useRouter();
  const { user } = useAuth();

  const handleNotificationPress = () => {
    router.push('/notifications' as any);
  };

  const handleProfilePress = () => {
    router.push('/(tabs)/account' as any);
  };

  return (
    <View style={styles.container}>
      <View style={styles.logoContainer}>
        <View style={styles.logoIcon}>
          <MaterialIcons name="park" size={18} color="#FFFFFF" />
        </View>
        <Text style={styles.logoText}>Pamoja</Text>
      </View>
      <View style={styles.headerActions}>
        <TouchableOpacity
          style={styles.iconButton}
          onPress={handleNotificationPress}
          accessibilityRole="button"
          accessibilityLabel="Notifications"
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <MaterialIcons name="notifications" size={22} color={homeDesign.textDark} />
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.iconButton}
          onPress={handleProfilePress}
          accessibilityRole="button"
          accessibilityLabel="Open Account"
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <MaterialIcons name="person-outline" size={22} color={homeDesign.textDark} />
        </TouchableOpacity>
      </View>
    </View>
  );
};

export default HomeHeader;