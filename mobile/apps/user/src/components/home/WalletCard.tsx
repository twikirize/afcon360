import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

const styles = StyleSheet.create({
  container: { marginTop: 28, marginBottom: 18 },
  card: {
    minHeight: 132,
    backgroundColor: '#003D1C',
    borderRadius: 25,
    paddingHorizontal: 16,
    paddingVertical: 20,
    flexDirection: 'row',
    alignItems: 'center',
    overflow: 'hidden',
    elevation: 7,
    shadowColor: '#173D28',
    shadowOpacity: 0.19,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 5 },
  },
  icon: {
    width: 57,
    alignItems: 'center',
    justifyContent: 'center',
  },
  divider: {
    width: 2,
    height: 72,
    backgroundColor: '#E8BD4F',
    marginHorizontal: 12,
    opacity: 0.95,
  },
  text: { flex: 1, minWidth: 0 },
  title: { fontSize: 19, fontWeight: '900', color: '#FFFDF6' },
  subtitle: { fontSize: 13, color: '#E2E9DF', marginTop: 6 },
  action: {
    backgroundColor: '#FFD21C',
    paddingHorizontal: 15,
    paddingVertical: 14,
    borderRadius: 26,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginLeft: 8,
  },
  actionText: { color: '#173D28', fontWeight: '900', fontSize: 14 },
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
        <View style={styles.icon}>
          <MaterialIcons name="account-balance-wallet" size={57} color="#FFD21C" />
        </View>
        <View style={styles.divider} />
        <View style={styles.text}>
          <Text style={styles.title} numberOfLines={1} adjustsFontSizeToFit>
            Your Pamoja Wallet
          </Text>
          <Text style={styles.subtitle} numberOfLines={1}>
            Pay, book and enjoy more
          </Text>
        </View>
        <View style={styles.action}>
          <Text style={styles.actionText}>Top Up</Text>
          <MaterialIcons name="arrow-forward" size={19} color="#173D28" />
        </View>
      </TouchableOpacity>
    </View>
  );
};

export default WalletCard;
