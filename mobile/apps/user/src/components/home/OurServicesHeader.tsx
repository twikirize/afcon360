import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 35,
  },
  headingLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flexShrink: 1,
  },
  goldLine: {
    width: 9,
    height: 65,
    borderRadius: 5,
    backgroundColor: homeDesign.goldLine,
    marginRight: 16,
  },
  sectionTitle: {
    fontSize: 38,
    fontWeight: '900',
    color: homeDesign.primaryGreenDark,
    letterSpacing: -1.5,
  },
  viewAll: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  viewAllText: {
    fontSize: 18,
    fontWeight: '700',
    color: homeDesign.primaryGreen,
  },
});

type IoniconsName = 'arrow-forward';

interface OurServicesHeaderProps {
  onViewAllPress?: () => void;
}

export const OurServicesHeader = ({ onViewAllPress }: OurServicesHeaderProps) => {
  const router = useRouter();

  const handleViewAllPress = () => {
    if (onViewAllPress) {
      onViewAllPress();
    } else {
      router.push('/(tabs)/explore' as any);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.headingLeft}>
        <View style={styles.goldLine} />
        <Text style={styles.sectionTitle}>Our Services</Text>
      </View>
      <TouchableOpacity style={styles.viewAll} onPress={handleViewAllPress}>
        <Text style={styles.viewAllText}>View all</Text>
        <Ionicons name="arrow-forward" size={24} color={homeDesign.primaryGreen} />
      </TouchableOpacity>
    </View>
  );
};

export default OurServicesHeader;