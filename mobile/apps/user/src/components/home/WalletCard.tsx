import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

export const WalletCard = () => {
  const router = useRouter();

  return (
    <View style={styles.wrapper}>
      <TouchableOpacity
        activeOpacity={0.9}
        style={styles.banner}
        onPress={() => router.push('/(tabs)/wallet' as any)}
        accessibilityRole="button"
        accessibilityLabel="Open your Pamoja wallet"
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
      >
        <LinearGradient
          colors={['#0F5227', '#04210F'] as const}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.bannerFill}
        />
        <View style={styles.left}>
          <View style={styles.iconBox}>
            <Ionicons name="wallet" size={22} color="#09381B" />
          </View>
          <View style={styles.textWrap}>
            <Text style={styles.title}>Your Pamoja Wallet</Text>
            <Text style={styles.subtitle}>Pay, book and enjoy more</Text>
          </View>
        </View>
        <TouchableOpacity
          style={styles.topUp}
          onPress={() => router.push('/(tabs)/wallet' as any)}
          accessibilityRole="button"
          accessibilityLabel="Top up your wallet"
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Text style={styles.topUpText}>Top Up</Text>
          <Ionicons name="arrow-forward" size={14} color="#09381B" />
        </TouchableOpacity>
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  wrapper: {
    marginHorizontal: 20,
    marginTop: 20,
    elevation: 6,
    shadowColor: '#09381B',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.2,
    shadowRadius: 10,
  },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    borderRadius: 16,
    backgroundColor: '#0A4222',
    overflow: 'hidden',
  },
  bannerFill: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    borderRadius: 16,
  },
  left: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    minWidth: 0,
  },
  iconBox: {
    width: 42,
    height: 42,
    borderRadius: 12,
    backgroundColor: homeDesign.goldAccent,
    justifyContent: 'center',
    alignItems: 'center',
  },
  textWrap: {
    marginLeft: 12,
    flex: 1,
    minWidth: 0,
  },
  title: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: 'bold',
  },
  subtitle: {
    color: '#E5E7EB',
    fontSize: 10,
    marginTop: 2,
  },
  topUp: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: homeDesign.goldAccent,
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 20,
    gap: 4,
  },
  topUpText: {
    color: '#09381B',
    fontSize: 11,
    fontWeight: 'bold',
  },
});

export default WalletCard;
