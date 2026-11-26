import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

const styles = StyleSheet.create({
  container: { marginBottom: 18 },
  card: {
    backgroundColor: homeDesign.primaryGreen, borderRadius: 19, padding: 17,
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    overflow: 'hidden',
  },
  left: { flexDirection: 'row', alignItems: 'center', gap: 13 },
  icon: {
    width: 48, height: 48, borderRadius: 15, backgroundColor: 'rgba(231,195,91,0.16)',
    alignItems: 'center', justifyContent: 'center',
  },
  title: { fontSize: 16, fontWeight: '800', color: '#FFFDF6', marginBottom: 3 },
  subtitle: { fontSize: 12, color: '#E2E9DF' },
  action: {
    backgroundColor: homeDesign.gold, paddingHorizontal: 17, paddingVertical: 11,
    borderRadius: 24, flexDirection: 'row', alignItems: 'center', gap: 5,
  },
  actionText: { color: '#173D28', fontWeight: '800', fontSize: 12 },
});

export const WalletCard = () => {
  const router = useRouter();
  return (
    <View style={styles.container}>
      <TouchableOpacity
        style={styles.card}
        onPress={() => router.push('/(tabs)/wallet' as any)}
        accessibilityRole="button"
        accessibilityLabel="Open your Pamoja wallet"
        activeOpacity={0.9}
      >
        <View style={styles.left}>
          <View style={styles.icon}>
            <MaterialIcons name="account-balance-wallet" size={27} color={homeDesign.gold} />
          </View>
          <View>
            <Text style={styles.title}>Your Pamoja Wallet</Text>
            <Text style={styles.subtitle}>Pay, book and enjoy more</Text>
          </View>
        </View>
        <View style={styles.action}>
          <Text style={styles.actionText}>Open</Text>
          <MaterialIcons name="arrow-forward" size={15} color="#173D28" />
        </View>
      </TouchableOpacity>
    </View>
  );
};

export default WalletCard;