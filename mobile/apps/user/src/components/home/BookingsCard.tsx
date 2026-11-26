import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

const styles = StyleSheet.create({
  container: { marginBottom: 20 },
  card: {
    backgroundColor: '#FFFEFA', borderRadius: 18, padding: 14,
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    borderWidth: 1, borderColor: homeDesign.borderColor,
    shadowColor: '#173D28', shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.06, shadowRadius: 9, elevation: 2,
  },
  left: { flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1 },
  icon: {
    width: 43, height: 43, borderRadius: 14, backgroundColor: '#E8F0E8',
    alignItems: 'center', justifyContent: 'center',
  },
  title: { fontSize: 15, fontWeight: '800', color: homeDesign.textDark, marginBottom: 3 },
  subtitle: { fontSize: 11, color: homeDesign.textGray },
  action: {
    width: 36, height: 36, borderRadius: 18, backgroundColor: '#E8F0E8',
    alignItems: 'center', justifyContent: 'center',
  },
});

export const BookingsCard = () => {
  const router = useRouter();
  return (
    <View style={styles.container}>
      <TouchableOpacity
        style={styles.card}
        onPress={() => router.push('/(tabs)/activity' as any)}
        accessibilityRole="button"
        accessibilityLabel="View your bookings"
        activeOpacity={0.9}
      >
        <View style={styles.left}>
          <View style={styles.icon}>
            <MaterialIcons name="event-note" size={22} color={homeDesign.primaryGreen} />
          </View>
          <View>
            <Text style={styles.title}>My bookings</Text>
            <Text style={styles.subtitle}>Manage your stays, rides and tickets</Text>
          </View>
        </View>
        <View style={styles.action}>
          <MaterialIcons name="arrow-forward" size={18} color={homeDesign.primaryGreen} />
        </View>
      </TouchableOpacity>
    </View>
  );
};

export default BookingsCard;