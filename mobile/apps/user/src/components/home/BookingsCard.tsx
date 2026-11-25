import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { spacing, radii } from '../../theme/tokens';
import { homeDesign } from '../../theme/tokens';

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 20,
    marginBottom: 20,
  },
  card: {
    backgroundColor: homeDesign.cardBg,
    borderRadius: 16,
    padding: 16,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#F0F0F0',
    shadowColor: homeDesign.shadowColor,
    shadowOffset: homeDesign.shadowOffset,
    shadowOpacity: homeDesign.shadowOpacity,
    shadowRadius: homeDesign.shadowRadius,
    elevation: homeDesign.elevation,
  },
  rowCenter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  bookingsIcon: {
    width: 40,
    height: 40,
    borderRadius: 8,
    backgroundColor: homeDesign.iconBgGreen,
    justifyContent: 'center',
    alignItems: 'center',
  },
  title: {
    fontSize: 15,
    fontWeight: '600',
    color: homeDesign.textDark,
    marginBottom: 2,
  },
  subtitle: {
    fontSize: 12,
    color: homeDesign.textGray,
  },
});

type MaterialIconName = 'event-note' | 'chevron-right';

export const BookingsCard = () => {
  const router = useRouter();

  const handlePress = () => {
    router.push('/(tabs)/activity' as any);
  };

  return (
    <View style={styles.container}>
      <TouchableOpacity
        style={styles.card}
        onPress={handlePress}
        accessibilityRole="button"
        accessibilityLabel="View your bookings"
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
      >
        <View style={styles.rowCenter}>
          <View style={styles.bookingsIcon}>
            <MaterialIcons name="event-note" size={22} color={homeDesign.primaryGreen} />
          </View>
          <View>
            <Text style={styles.title}>My bookings</Text>
            <Text style={styles.subtitle}>Manage your stays and rides</Text>
          </View>
        </View>
        <MaterialIcons name="chevron-right" size={24} color={homeDesign.textGray} />
      </TouchableOpacity>
    </View>
  );
};

export default BookingsCard;