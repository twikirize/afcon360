import React, { useState, useCallback } from 'react';
import {
  StyleSheet,
  Text,
  View,
  SafeAreaView,
  ScrollView,
  TextInput,
  TouchableOpacity,
  Image,
  Platform,
  StatusBar as RNStatusBar,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { StatusBar } from 'expo-status-bar';
import { useRouter } from 'expo-router';
import { useAuth } from '../../src/auth/AuthProvider';
import { colors, spacing, radii, typography, shadows } from '../../src/theme/tokens';

const COLORS = {
  bg: '#FCFCFC',
  primaryGreen: '#156C43',
  heroBg: '#E9F3EE',
  textDark: '#1A1A1A',
  textGray: '#717B7A',
  border: '#E5E7EB',
  cardBg: '#FFFFFF',
  iconBgGreen: '#F0F6F2',
  iconBgPeach: '#FDF3EE',
  iconTextPeach: '#D97706',
};

export default function HomeScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const [searchText, setSearchText] = useState('');

  const handleServicePress = useCallback((service: string) => {
    switch (service) {
      case 'transport':
        router.push('/(service)/ride' as never);
        break;
      case 'stays':
        router.push('/(service)/stays' as never);
        break;
      case 'events':
        router.push('/(service)/events' as never);
        break;
      case 'tickets':
        router.push('/(service)/events' as never);
        break;
      case 'wallet':
        router.push('/(tabs)/wallet' as never);
        break;
      case 'bookings':
        router.push('/(tabs)/bookings' as never);
        break;
      default:
        router.push('/(tabs)/explore' as never);
    }
  }, [router]);

  const handleSearchSubmit = useCallback(() => {
    if (searchText.trim()) {
      router.push({
        pathname: '/(service)/events',
        params: { query: searchText.trim() },
      } as never);
    }
  }, [searchText, router]);

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="dark" />

      <View style={styles.header}>
        <View style={styles.logoContainer}>
          <View style={styles.logoIcon}>
            <MaterialIcons name="park" size={18} color="white" />
          </View>
          <Text style={styles.logoText}>Pamoja</Text>
        </View>
        <View style={styles.headerActions}>
          <TouchableOpacity
            style={styles.iconButton}
            onPress={() => router.push('/(tabs)/activity' as never)}
            accessibilityLabel="Open activity"
          >
            <MaterialIcons name="notifications" size={22} color={COLORS.textDark} />
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.iconButton}
            onPress={() => router.push('/(tabs)/account' as never)}
            accessibilityLabel="Open account"
          >
            <MaterialIcons name="person-outline" size={22} color={COLORS.textDark} />
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView
        style={styles.scrollView}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.searchContainer}>
          <View style={styles.searchBox}>
            <MaterialIcons name="search" size={22} color={COLORS.textGray} />
            <TextInput
              style={styles.searchInput}
              placeholder="Find a ride, event or stay..."
              placeholderTextColor={COLORS.textGray}
              value={searchText}
              onChangeText={setSearchText}
              onSubmitEditing={handleSearchSubmit}
              autoCapitalize="none"
            />
          </View>
        </View>

        <View style={styles.heroBanner}>
          <View style={styles.heroTextContainer}>
            <Text style={styles.heroTitle}>Your world,{'\n'}together.</Text>
            <Text style={styles.heroSubtitle}>One app. More to explore.</Text>
          </View>
          <Image
            source={{
              uri: 'https://images.unsplash.com/photo-1573164713988-8665fc963095?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            }}
            style={styles.heroImage}
            resizeMode="cover"
          />
        </View>

        <View style={styles.mainContent}>
          <Text style={styles.sectionTitle}>Make yourself at home</Text>

          <View style={styles.gridContainer}>
            <TouchableOpacity
              style={styles.gridCard}
              onPress={() => handleServicePress('transport')}
              accessibilityLabel="Transport - Find your ride"
            >
              <View style={styles.cardTop}>
                <View style={styles.cardIcon}>
                  <MaterialIcons name="directions-car" size={20} color={COLORS.primaryGreen} />
                </View>
                <MaterialIcons name="arrow-outward" size={18} color={COLORS.textGray} />
              </View>
              <Text style={styles.cardTitle}>Transport</Text>
              <Text style={styles.cardSubtitle}>Find your ride</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.gridCard}
              onPress={() => handleServicePress('stays')}
              accessibilityLabel="Stays - Find a place to stay"
            >
              <View style={styles.cardTop}>
                <View style={[styles.cardIcon, { backgroundColor: COLORS.iconBgPeach }]}>
                  <MaterialIcons name="bed" size={20} color={COLORS.iconTextPeach} />
                </View>
                <MaterialIcons name="arrow-outward" size={18} color={COLORS.textGray} />
              </View>
              <Text style={styles.cardTitle}>Stays</Text>
              <Text style={styles.cardSubtitle}>Find a place to stay</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.gridCard}
              onPress={() => handleServicePress('events')}
              accessibilityLabel="Events - See what's happening"
            >
              <View style={styles.cardTop}>
                <View style={[styles.cardIcon, { backgroundColor: COLORS.iconBgPeach }]}>
                  <MaterialIcons name="calendar-month" size={20} color={COLORS.iconTextPeach} />
                </View>
                <MaterialIcons name="arrow-outward" size={18} color={COLORS.textGray} />
              </View>
              <Text style={styles.cardTitle}>Events</Text>
              <Text style={styles.cardSubtitle}>See what's happening</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.gridCard}
              onPress={() => handleServicePress('tickets')}
              accessibilityLabel="Tickets - Your event tickets"
            >
              <View style={styles.cardTop}>
                <View style={styles.cardIcon}>
                  <MaterialIcons name="confirmation-number" size={20} color={COLORS.primaryGreen} />
                </View>
                <MaterialIcons name="arrow-outward" size={18} color={COLORS.textGray} />
              </View>
              <Text style={styles.cardTitle}>Tickets</Text>
              <Text style={styles.cardSubtitle}>Your event tickets</Text>
            </TouchableOpacity>
          </View>

          <TouchableOpacity
            style={styles.walletCard}
            onPress={() => handleServicePress('wallet')}
            accessibilityLabel="Your Pamoja wallet"
          >
            <View style={styles.rowCenter}>
              <View style={styles.walletIcon}>
                <MaterialIcons name="account-balance-wallet" size={22} color="white" />
              </View>
              <View>
                <Text style={styles.walletTitle}>Your Pamoja wallet</Text>
                <Text style={styles.walletSubtitle}>Payments, all in one place</Text>
              </View>
            </View>
            <MaterialIcons name="chevron-right" size={24} color="white" />
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.bookingsCard}
            onPress={() => handleServicePress('bookings')}
            accessibilityLabel="My bookings"
          >
            <View style={styles.rowCenter}>
              <View style={styles.bookingsIcon}>
                <MaterialIcons name="event-note" size={22} color={COLORS.primaryGreen} />
              </View>
              <View>
                <Text style={styles.bookingsTitle}>My bookings</Text>
                <Text style={styles.bookingsSubtitle}>Manage your stays and rides</Text>
              </View>
            </View>
            <MaterialIcons name="chevron-right" size={24} color={COLORS.textGray} />
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: COLORS.bg,
    paddingTop: Platform.OS === 'android' ? RNStatusBar.currentHeight : 0,
  },
  header: {
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
    backgroundColor: COLORS.primaryGreen,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
  },
  logoText: {
    fontSize: 22,
    fontWeight: '700',
    color: COLORS.textDark,
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
    borderColor: COLORS.border,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: 100,
  },
  searchContainer: {
    paddingHorizontal: 20,
    paddingVertical: 10,
  },
  searchBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.cardBg,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 10,
  },
  searchInput: {
    flex: 1,
    fontSize: 15,
    color: COLORS.textDark,
    fontWeight: '500',
  },
  heroBanner: {
    marginHorizontal: 20,
    backgroundColor: COLORS.heroBg,
    borderRadius: 16,
    padding: 24,
    minHeight: 160,
    flexDirection: 'row',
    overflow: 'hidden',
  },
  heroTextContainer: {
    flex: 1,
    zIndex: 2,
    maxWidth: '60%',
  },
  heroTitle: {
    color: COLORS.primaryGreen,
    fontSize: 24,
    fontWeight: '700',
    lineHeight: 30,
    marginBottom: 12,
  },
  heroSubtitle: {
    color: COLORS.textGray,
    fontSize: 12,
    fontWeight: '500',
  },
  heroImage: {
    position: 'absolute',
    right: -10,
    bottom: 0,
    width: '50%',
    height: '110%',
    opacity: 0.9,
  },
  mainContent: {
    paddingHorizontal: 20,
    paddingTop: 24,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.textDark,
    marginBottom: 16,
  },
  gridContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginBottom: 16,
  },
  gridCard: {
    width: '48%',
    backgroundColor: COLORS.cardBg,
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: '#F0F0F0',
    marginBottom: 16,
    ...shadows.card,
  },
  cardTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 20,
  },
  cardIcon: {
    width: 36,
    height: 36,
    borderRadius: 8,
    backgroundColor: COLORS.iconBgGreen,
    justifyContent: 'center',
    alignItems: 'center',
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: COLORS.textDark,
    marginBottom: 4,
  },
  cardSubtitle: {
    fontSize: 12,
    color: COLORS.textGray,
    lineHeight: 16,
  },
  rowCenter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  walletCard: {
    backgroundColor: COLORS.primaryGreen,
    borderRadius: 16,
    padding: 16,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  walletIcon: {
    width: 40,
    height: 40,
    borderRadius: 8,
    backgroundColor: 'rgba(255,255,255,0.15)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  walletTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: 'white',
    marginBottom: 2,
  },
  walletSubtitle: {
    fontSize: 12,
    color: 'rgba(255,255,255,0.8)',
  },
  bookingsCard: {
    backgroundColor: COLORS.cardBg,
    borderRadius: 16,
    padding: 16,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#F0F0F0',
    ...shadows.card,
  },
  bookingsIcon: {
    width: 40,
    height: 40,
    borderRadius: 8,
    backgroundColor: COLORS.iconBgGreen,
    justifyContent: 'center',
    alignItems: 'center',
  },
  bookingsTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: COLORS.textDark,
    marginBottom: 2,
  },
  bookingsSubtitle: {
    fontSize: 12,
    color: COLORS.textGray,
  },
});