import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { spacing, radii } from '../../theme/tokens';
import { homeDesign } from '../../theme/tokens';

type ServiceKey = 'transport' | 'stays' | 'events' | 'tickets';

interface Service {
  key: ServiceKey;
  label: string;
  hint: string;
  icon: string;
  iconColor: string;
  bgColor: string;
  destination: string;
}

const SERVICES: Service[] = [
  {
    key: 'transport',
    label: 'Transport',
    hint: 'Find your ride',
    icon: 'directions-car',
    iconColor: homeDesign.primaryGreen,
    bgColor: homeDesign.iconBgGreen,
    destination: '/(service)/ride',
  },
  {
    key: 'stays',
    label: 'Stays',
    hint: 'Find a place to stay',
    icon: 'bed',
    iconColor: homeDesign.iconTextPeach,
    bgColor: homeDesign.iconBgPeach,
    destination: '/(service)/stays',
  },
  {
    key: 'events',
    label: 'Events',
    hint: "See what's happening",
    icon: 'calendar-month',
    iconColor: homeDesign.iconTextPeach,
    bgColor: homeDesign.iconBgPeach,
    destination: '/(service)/events',
  },
  {
    key: 'tickets',
    label: 'Tickets',
    hint: 'Your event tickets',
    icon: 'confirmation-number',
    iconColor: homeDesign.primaryGreen,
    bgColor: homeDesign.iconBgGreen,
    destination: '/(tabs)/activity',
  },
];

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginBottom: 16,
  },
  card: {
    width: '48%',
    backgroundColor: homeDesign.cardBg,
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: '#F0F0F0',
    marginBottom: 16,
    shadowColor: homeDesign.shadowColor,
    shadowOffset: homeDesign.shadowOffset,
    shadowOpacity: homeDesign.shadowOpacity,
    shadowRadius: homeDesign.shadowRadius,
    elevation: homeDesign.elevation,
  },
  cardTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 20,
  },
  iconWrapper: {
    width: 36,
    height: 36,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
  },
  arrowIcon: {
    color: homeDesign.textGray,
    fontSize: 18,
  },
  title: {
    fontSize: 15,
    fontWeight: '600',
    color: homeDesign.textDark,
    marginBottom: 4,
  },
  hint: {
    fontSize: 12,
    color: homeDesign.textGray,
    lineHeight: 16,
  },
});

type MaterialIconName = 'directions-car' | 'bed' | 'calendar-month' | 'confirmation-number' | 'arrow-outward';

interface HomeServiceGridProps {
  onServicePress?: (key: ServiceKey) => void;
}

export const HomeServiceGrid = ({ onServicePress }: HomeServiceGridProps) => {
  const router = useRouter();

  const handlePress = (service: Service) => {
    if (onServicePress) {
      onServicePress(service.key);
    }
    router.push(service.destination as any);
  };

  return (
    <View style={styles.container}>
      {SERVICES.map((service) => (
        <TouchableOpacity
          key={service.key}
          accessibilityRole="button"
          accessibilityLabel={service.label}
          onPress={() => handlePress(service)}
          style={styles.card}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <View style={styles.cardTop}>
            <View
              style={[
                styles.iconWrapper,
                { backgroundColor: service.bgColor },
              ]}
            >
              <MaterialIcons
                name={service.icon as MaterialIconName}
                size={20}
                color={service.iconColor}
              />
            </View>
            <MaterialIcons name="arrow-outward" size={18} color={homeDesign.textGray} />
          </View>
          <Text style={styles.title}>{service.label}</Text>
          <Text style={styles.hint}>{service.hint}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
};

export default HomeServiceGrid;