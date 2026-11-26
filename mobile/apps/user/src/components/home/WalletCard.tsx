import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 20,
    marginBottom: 12,
  },
  walletBanner: {
    minHeight: 155,
    marginTop: 34,
    borderRadius: 29,
    backgroundColor: homeDesign.walletBg,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 18,
    paddingVertical: 22,
    elevation: 8,
    shadowColor: '#66501C',
    shadowOpacity: 0.2,
    shadowRadius: 9,
    shadowOffset: { width: 0, height: 5 },
  },
  walletIcon: {
    width: 65,
    alignItems: 'center',
    justifyContent: 'center',
  },
  walletDivider: {
    width: 2,
    height: 75,
    backgroundColor: homeDesign.walletDivider,
    marginHorizontal: 13,
  },
  walletText: {
    flex: 1,
  },
  walletTitle: {
    fontSize: 19,
    fontWeight: '800',
    color: '#FFFFFF',
  },
  walletSubtitle: {
    fontSize: 14,
    color: homeDesign.walletText,
    marginTop: 7,
  },
  topUpButton: {
    backgroundColor: homeDesign.goldAccent,
    paddingHorizontal: 15,
    paddingVertical: 15,
    borderRadius: 30,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  topUpText: {
    fontSize: 15,
    fontWeight: '900',
    color: homeDesign.primaryGreenDark,
  },
});

type IoniconsName = 'wallet' | 'arrow-forward';

export const WalletCard = () => {
  const router = useRouter();

  const handlePress = () => {
    router.push('/(tabs)/wallet' as any);
  };

  const handleTopUpPress = () => {
    router.push('/(tabs)/wallet' as any);
  };

  return (
    <View style={styles.container}>
      <TouchableOpacity
        activeOpacity={0.9}
        style={styles.walletBanner}
        onPress={handlePress}
        accessibilityRole="button"
        accessibilityLabel="Open your Pamoja wallet"
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
      >
        <View style={styles.walletIcon}>
          <Ionicons name="wallet" size={65} color={homeDesign.goldAccent} />
        </View>
        <View style={styles.walletDivider} />
        <View style={styles.walletText}>
          <Text style={styles.walletTitle}>Your Pamoja Wallet</Text>
          <Text style={styles.walletSubtitle}>Pay, book and enjoy more</Text>
        </View>
        <TouchableOpacity style={styles.topUpButton} onPress={handleTopUpPress} accessibilityRole="button" accessibilityLabel="Top up your wallet" hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
          <Text style={styles.topUpText}>Top Up</Text>
          <Ionicons name="arrow-forward" size={21} color={homeDesign.primaryGreenDark} />
        </TouchableOpacity>
      </TouchableOpacity>
    </View>
  );
};

export default WalletCard;