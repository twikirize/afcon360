import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ImageBackground, useWindowDimensions } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

type ServiceKey = 'transport' | 'stays' | 'events' | 'adventure';
type ServiceIcon = 'car-outline' | 'bed-outline' | 'calendar-outline' | 'compass-outline';

interface Service {
  key: ServiceKey;
  title: string;
  subtitle: string;
  icon: ServiceIcon;
  image: string;
  destination: string;
}

const SERVICES: Service[] = [
  {
    key: 'transport',
    title: 'Transport',
    subtitle: 'Ride with ease',
    icon: 'car-outline',
    image: 'https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?q=80&w=400&auto=format&fit=crop',
    destination: '/(service)/ride',
  },
  {
    key: 'stays',
    title: 'Stays',
    subtitle: 'Find the best stays',
    icon: 'bed-outline',
    image: 'https://images.unsplash.com/photo-1611892440504-42a792e24d32?q=80&w=400&auto=format&fit=crop',
    destination: '/(service)/stays',
  },
  {
    key: 'events',
    title: 'Events & Tickets',
    subtitle: 'Be part of it',
    icon: 'calendar-outline',
    image: 'https://images.unsplash.com/photo-1492684223066-81342ee5ff30?q=80&w=400&auto=format&fit=crop',
    destination: '/(service)/events',
  },
  {
    key: 'adventure',
    title: 'Adventure',
    subtitle: 'Explore more',
    icon: 'compass-outline',
    image: 'https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?q=80&w=400&auto=format&fit=crop',
    destination: '/(service)/adventure',
  },
];

interface HomeServiceGridProps {
  onServicePress?: (key: ServiceKey) => void;
}

export const HomeServiceGrid = ({ onServicePress }: HomeServiceGridProps) => {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const cardWidth = (width - 20 * 2 - 12) / 2;

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
          accessibilityLabel={service.title}
          onPress={() => handlePress(service)}
          style={[styles.serviceCard, { width: cardWidth }]}
          activeOpacity={0.9}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <ImageBackground
            source={{ uri: service.image }}
            style={styles.cardImage}
            imageStyle={styles.cardImageStyle}
            resizeMode="cover"
          >
            <LinearGradient
              colors={['rgba(9, 56, 27, 0.28)', 'rgba(9, 56, 27, 0.96)'] as const}
              start={{ x: 0.5, y: 0 }}
              end={{ x: 0.5, y: 1 }}
              style={StyleSheet.absoluteFill}
            />
            <View style={styles.cardContent}>
              <View style={styles.iconCircle}>
                <Ionicons name={service.icon} size={19} color="#FFFFFF" />
              </View>
              <View style={styles.cardTextWrap}>
                <Text style={styles.cardTitle} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.8}>{service.title}</Text>
                <Text style={styles.cardSubtitle} numberOfLines={1}>{service.subtitle}</Text>
              </View>
            </View>
          </ImageBackground>
        </TouchableOpacity>
      ))}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: 20,
    gap: 12,
  },
  serviceCard: {
    height: 138,
    borderRadius: 16,
    overflow: 'hidden',
    backgroundColor: homeDesign.primaryGreenDark,
    elevation: 4,
    shadowColor: '#09381B',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
  },
  cardImage: {
    flex: 1,
  },
  cardImageStyle: {
    borderRadius: 16,
  },
  cardContent: {
    flex: 1,
    // Icon and words sit together at the bottom of the tile, both centred.
    justifyContent: 'flex-end',
    alignItems: 'center',
    padding: 12,
  },
  iconCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#0A4222',
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.8)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  cardTextWrap: {
    width: '100%',
    minWidth: 0,
    marginTop: 8,
    alignItems: 'center',
  },
  cardTitle: {
    color: '#FFFFFF',
    fontSize: 15,
    lineHeight: 19,
    fontWeight: '700',
    textAlign: 'center',
  },
  cardSubtitle: {
    color: '#E8F0EA',
    fontSize: 11,
    lineHeight: 15,
    marginTop: 2,
    textAlign: 'center',
  },
});

export default HomeServiceGrid;
