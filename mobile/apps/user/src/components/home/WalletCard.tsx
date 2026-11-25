import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { spacing, radii } from '../../theme/tokens';
import { homeDesign } from '../../theme/tokens';

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 20,
    marginBottom: 12,
  },
  card: {
    backgroundColor: homeDesign.primaryGreen,
    borderRadius: 16,
    padding: 16,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  rowCenter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  walletIcon: {
    width: 40,
    height: 40,
    borderRadius: 8,
    backgroundColor: 'rgba(255,255,255,0.15)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  title: {
    fontSize: 15,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 2,
  },
  subtitle: {
    fontSize: 12,
    color: 'rgba(255,255,255,0.8)',
  },
});

type MaterialIconName = 'account-balance-wallet' | 'chevron-right';

export const WalletCard = () => {
  const router = useRouter();

  const handlePress = () => {
    router.push('/(tabs)/wallet' as any);
  };

  return (
    <View style={styles.container}>
      <TouchableOpacity
        style={styles.card}
        onPress={handlePress}
        accessibilityRole="button"
        accessibilityLabel="Open your Pamoja wallet"
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
      >
        <View style={styles.rowCenter}>
          <View style={styles.walletIcon}>
            <MaterialIcons name="account-balance-wallet" size={22} color="#FFFFFF" />
          </View>
          <View>
            <Text style={styles.title}>Your Pamoja wallet</Text>
            <Text style={styles.subtitle}>Payments, all in one place</Text>
          </View>
        </View>
        <MaterialIcons name="chevron-right" size={24} color="#FFFFFF" />
      </TouchableOpacity>
    </View>
  );
};

export default WalletCard;