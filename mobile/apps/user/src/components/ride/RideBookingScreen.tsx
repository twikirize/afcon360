import React, { useCallback, useEffect, useState } from "react";
import { Alert, ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View, Platform } from "react-native";
import { StatusBar } from "expo-status-bar";
import { MaterialIcons } from "@expo/vector-icons";
import { walletClient } from "../../services/api";
import type { WalletAccount } from "@afcon360/mobile-core";
import { colors, spacing, radii, typography, shadows } from "../../theme/tokens";

// Custom colors matching the HTML mockup exactly
const MOCKUP_COLORS = {
  brandPrimary: '#16A34A',
  brandDark: '#15803D',
  bgColor: '#F4F6F9',
  cardBg: '#FFFFFF',
  textDark: '#1A1916',
  textLight: '#6B7280',
  borderColor: '#E5E7EB',
  brandLight: '#DCFCE7',
  red: '#EF4444',
  blue: '#3B82F6',
  gold: '#FFD700',
};

interface PaymentMethod {
  label: string;
  icon: string;
}

interface RideBookingState {
  userName: string;
  pickup: string;
  dropoff: string;
  selectedService: string;
  rideType: 'now' | 'later';
  selectedPayment: PaymentMethod | null;
  loading: boolean;
  error: string | null;
  paymentMethods: PaymentMethod[];
}

const SERVICES = [
  { id: 'on_demand', label: 'On-Demand', icon: 'car', active: true },
  { id: 'airport', label: 'Airport', icon: 'flight', active: false },
  { id: 'stadium', label: 'Stadium\nShuttle', icon: 'futbol', active: false, multiline: true },
  { id: 'hotel', label: 'Hotel\nTransfer', icon: 'hotel', active: false, multiline: true },
];

const RIDE_TYPES = [
  { id: 'now', label: 'Ride Now', active: true },
  { id: 'later', label: 'Schedule', active: false },
];

export function RideBookingScreen() {
  const [state, setState] = useState<RideBookingState>({
    userName: 'Andrew Kabito',
    pickup: '',
    dropoff: '',
    selectedService: 'on_demand',
    rideType: 'now',
    selectedPayment: { label: 'AFCON360 Wallet', icon: 'account-balance-wallet' },
    loading: true,
    error: null,
    paymentMethods: [],
  });

  const loadPaymentMethods = useCallback(async () => {
    try {
      const [summary] = await Promise.all([
        walletClient.getSummary(),
      ]);
      const methods: PaymentMethod[] = [];
      if (summary.accounts?.length) {
        methods.push({ label: 'AFCON360 Wallet', icon: 'account-balance-wallet' });
      }
      methods.push({ label: 'Mobile Money', icon: 'phone-android' });
      methods.push({ label: 'Credit/Debit Card', icon: 'credit-card' });
      setState(prev => ({ ...prev, paymentMethods: methods, loading: false }));
    } catch (e) {
      setState(prev => ({ ...prev, loading: false, error: e instanceof Error ? e.message : 'Failed to load payment methods' }));
    }
  }, []);

  useEffect(() => {
    void loadPaymentMethods();
  }, []);

  const setPickup = useCallback((value: string) => {
    setState(prev => ({ ...prev, pickup: value }));
  }, []);

  const setDropoff = useCallback((value: string) => {
    setState(prev => ({ ...prev, dropoff: value }));
  }, []);

  const handleBookRide = useCallback(() => {
    if (!state.pickup || !state.dropoff) {
      Alert.alert('Missing Locations', 'Please enter both pickup and destination.');
      return;
    }
    const paymentLabel = state.selectedPayment?.label || 'Unknown';
    Alert.alert('Booking Ride', `Booking ${state.selectedService} ride from "${state.pickup}" to "${state.dropoff}" using ${paymentLabel}.`);
  }, [state.pickup, state.dropoff, state.selectedService, state.selectedPayment]);

  const handleServicePress = useCallback((serviceId: string) => {
    setState(prev => ({ ...prev, selectedService: serviceId }));
  }, []);

  const handleRideTypePress = useCallback((type: 'now' | 'later') => {
    setState(prev => ({ ...prev, rideType: type }));
  }, []);

  const handlePaymentPress = useCallback(() => {
    Alert.alert('Payment Methods', 'Select your preferred payment method.', [
      { text: 'Cancel', style: 'cancel' },
      ...state.paymentMethods.map(method => ({
        text: method.label,
        onPress: () => setState(prev => ({ ...prev, selectedPayment: method })),
      })),
    ]);
  }, [state.paymentMethods]);

  return (
    <View style={styles.container}>
      <StatusBar style="light" />

      {/* Map Background */}
      <View style={styles.mapContainer}>
        <View style={styles.mapBg} />
        <View style={styles.mapMarker}>
          <View style={styles.markerPin}>
            <MaterialIcons name="location-on" size={20} color="white" as any />
          </View>
        </View>
      </View>

      {/* Top Bar */}
      <View style={styles.topBar}>
        <TouchableOpacity style={styles.menuBtn} onPress={() => Alert.alert('Menu', 'Menu coming soon')}>
          <MaterialIcons name="menu" size={24} color={COLORS.textDark} as any />
        </TouchableOpacity>
        <TouchableOpacity style={styles.profileBtn} onPress={() => Alert.alert('Profile', 'Profile coming soon')}>
          <MaterialIcons name="account-circle" size={24} color="white" as any />
        </TouchableOpacity>
      </View>

      {/* Bottom Sheet */}
      <ScrollView
        contentContainerStyle={styles.bottomSheetContent}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.sheetHandle} />

        <Text style={styles.greeting}>Where to, {state.userName}?</Text>

        {/* Location Inputs */}
        <View style={styles.locationInputs}>
          <View style={styles.inputRow}>
            <View style={styles.inputIcon}>
              <View style={styles.dot} />
            </View>
            <TextInput
              style={styles.inputField}
              placeholder="Pickup location"
              value={state.pickup}
              onChangeText={setPickup}
              autoCapitalize="words"
            />
          </View>
          <View style={styles.inputDivider} />
          <View style={styles.inputRow}>
            <View style={styles.inputIcon}>
              <View style={styles.square} />
            </View>
            <TextInput
              style={styles.inputField}
              placeholder="Where are you going?"
              value={state.dropoff}
              onChangeText={setDropoff}
              autoCapitalize="words"
            />
          </View>
        </View>

        {/* Service Selection */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Select Service</Text>
        </View>
        <View style={styles.serviceGrid}>
          {SERVICES.map((service) => (
            <TouchableOpacity
              key={service.id}
              style={[styles.serviceItem, service.active && styles.serviceItemActive]}
              onPress={() => handleServicePress(service.id)}
            >
              <MaterialIcons
                name={service.icon as any}
                size={24}
                color={service.active ? MOCKUP_COLORS.brandPrimary : COLORS.textDark}
              />
              <Text style={[styles.serviceLabel, service.active && styles.serviceLabelActive]}>
                {service.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Ride Type Toggle */}
        <View style={styles.rideTypeToggle}>
          {RIDE_TYPES.map((rt) => (
            <TouchableOpacity
              key={rt.id}
              style={[styles.rideTypeBtn, rt.active && styles.rideTypeBtnActive]}
              onPress={() => handleRideTypePress(rt.id as 'now' | 'later')}
            >
              <Text style={[styles.rideTypeBtnLabel, rt.active && styles.rideTypeBtnLabelActive]}>
                {rt.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Payment Method */}
        <TouchableOpacity style={styles.paymentSelector} onPress={handlePaymentPress}>
          <View style={styles.paymentLeft}>
            <View style={styles.paymentIcon}>
              <MaterialIcons name={state.selectedPayment?.icon as any} size={22} color={MOCKUP_COLORS.brandPrimary} />
            </View>
            <Text style={styles.paymentText}>{state.selectedPayment?.label || 'Unknown'}</Text>
          </View>
          <MaterialIcons name="chevron-right" size={20} color={COLORS.textLight} as any />
        </TouchableOpacity>

        {/* Book Button */}
        <TouchableOpacity style={styles.btnBook} onPress={handleBookRide}>
          <Text style={styles.btnBookText}>
            Confirm Ride <MaterialIcons name="arrow-forward" size={20} color="white" as any style={{ marginLeft: 4 }} />
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}

const COLORS = {
  textDark: '#1A1916',
  textLight: '#6B7280',
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: MOCKUP_COLORS.bgColor,
  },
  mapContainer: {
    flex: 1,
    position: 'relative',
  },
  mapBg: {
    flex: 1,
    backgroundColor: '#E5E9EC',
  },
  mapMarker: {
    position: 'absolute',
    top: '40%',
    left: '50%',
    transform: [{ translateX: -20 }, { translateY: -20 }],
    zIndex: 1,
    alignItems: 'center',
  },
  markerPin: {
    width: 40,
    height: 40,
    backgroundColor: MOCKUP_COLORS.brandPrimary,
    borderRadius: 20,
    borderTopRightRadius: 0,
    transform: [{ rotate: '-45deg' }],
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: MOCKUP_COLORS.brandPrimary,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 10,
    elevation: 8,
  },
  topBar: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    paddingTop: 20,
    paddingHorizontal: 20,
    paddingBottom: 10,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    zIndex: 10,
  },
  menuBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: MOCKUP_COLORS.cardBg,
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 10,
    elevation: 4,
  },
  profileBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: MOCKUP_COLORS.brandPrimary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  bottomSheetContent: {
    paddingHorizontal: 20,
    paddingBottom: 30,
  },
  sheetHandle: {
    width: 40,
    height: 4,
    backgroundColor: MOCKUP_COLORS.borderColor,
    borderRadius: 2,
    alignSelf: 'center',
    marginBottom: 16,
  },
  greeting: {
    fontSize: 22,
    fontWeight: '800',
    color: MOCKUP_COLORS.textDark,
    marginBottom: 20,
  },
  locationInputs: {
    backgroundColor: MOCKUP_COLORS.bgColor,
    borderRadius: 16,
    padding: 16,
    marginBottom: 24,
    position: 'relative',
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  inputIcon: {
    width: 12,
    alignItems: 'center',
  },
  dot: {
    width: 10,
    height: 10,
    backgroundColor: MOCKUP_COLORS.textDark,
    borderRadius: 5,
  },
  square: {
    width: 10,
    height: 10,
    backgroundColor: MOCKUP_COLORS.brandPrimary,
    borderRadius: 2,
  },
  inputField: {
    flex: 1,
    borderBottomWidth: 1,
    borderBottomColor: MOCKUP_COLORS.borderColor,
    fontSize: 14,
    fontWeight: '600',
    color: MOCKUP_COLORS.textDark,
    paddingVertical: 8,
  },
  inputDivider: {
    position: 'absolute',
    left: 21,
    top: 36,
    height: 20,
    width: 2,
    backgroundColor: '#D1D5DB',
  },
  sectionHeader: {
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: MOCKUP_COLORS.textDark,
  },
  serviceGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  serviceItem: {
    alignItems: 'center',
    width: '23.5%',
    paddingVertical: 10,
    borderRadius: 12,
    borderWidth: 1.5,
    borderColor: 'transparent',
  },
  serviceItemActive: {
    backgroundColor: MOCKUP_COLORS.brandLight,
    borderColor: MOCKUP_COLORS.brandPrimary,
  },
  serviceLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: MOCKUP_COLORS.textLight,
    textAlign: 'center',
    lineHeight: 14,
  },
  serviceLabelActive: {
    color: MOCKUP_COLORS.brandDark,
  },
  rideTypeToggle: {
    flexDirection: 'row',
    backgroundColor: MOCKUP_COLORS.bgColor,
    borderRadius: 12,
    padding: 4,
    marginBottom: 24,
  },
  rideTypeBtn: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderRadius: 8,
  },
  rideTypeBtnActive: {
    backgroundColor: MOCKUP_COLORS.cardBg,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  rideTypeBtnLabel: {
    fontSize: 13,
    fontWeight: '600',
    color: MOCKUP_COLORS.textLight,
  },
  rideTypeBtnLabelActive: {
    color: MOCKUP_COLORS.textDark,
  },
  paymentSelector: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: MOCKUP_COLORS.bgColor,
    padding: 16,
    borderRadius: 12,
    marginBottom: 24,
  },
  paymentLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  paymentIcon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: MOCKUP_COLORS.cardBg,
    justifyContent: 'center',
    alignItems: 'center',
  },
  paymentText: {
    fontSize: 14,
    fontWeight: '600',
    color: MOCKUP_COLORS.textDark,
  },
  btnBook: {
    width: '100%',
    backgroundColor: MOCKUP_COLORS.brandPrimary,
    paddingVertical: 18,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: MOCKUP_COLORS.brandPrimary,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
  btnBookText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
    flexDirection: 'row',
    alignItems: 'center',
  },
});

export default RideBookingScreen;