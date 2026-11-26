import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ImageBackground, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

type ServiceKey = 'transport' | 'stays' | 'events' | 'adventure';

interface Service {
  key: ServiceKey;
  title: string;
  subtitle: string;
  icon: string;
  image: string;
  destination: string;
}

const SERVICES: Service[] = [
  {
    key: 'transport',
    title: 'Transport',
    subtitle: 'Ride with ease',
    icon: 'car-outline',
    image: 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=900',
    destination: '/(service)/ride',
  },
  {
    key: 'stays',
    title: 'Stays',
    subtitle: 'Find the best stays',
    icon: 'bed-outline',
    image: 'https://images.unsplash.com/photo-1611892440504-42a792e24d32?w=900',
    destination: '/(service)/stays',
  },
  {
    key: 'events',
    title: 'Events & Tickets',
    subtitle: 'Be part of it',
    icon: 'calendar-outline',
    image: 'https://images.unsplash.com/photo-1506157786151-b8491531f063?w=900',
    destination: '/(service)/events',
  },
  {
    key: 'adventure',
    title: 'Adventure',
    subtitle: 'Explore more',
    icon: 'compass-outline',
    image: 'https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?w=900',
    destination: '/(service)/adventure',
  },
];

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    rowGap: 24,
  },
  serviceCard: {
    height: 185,
    borderRadius: 29,
    overflow: 'hidden',
    backgroundColor: homeDesign.primaryGreenDark,
    elevation: homeDesign.elevation,
    shadowColor: homeDesign.shadowColor,
    shadowOffset: homeDesign.shadowOffset,
    shadowOpacity: homeDesign.shadowOpacity,
    shadowRadius: homeDesign.shadowRadius,
  },
  cardImage: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  imageShade: {
    ...StyleSheet.absoluteFill,
    backgroundColor: homeDesign.cardShade,
  },
  cardContent: {
    minHeight: 88,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 10,
    backgroundColor: homeDesign.cardContentBg,
  },
  serviceIcon: {
    width: 54,
    height: 54,
    borderRadius: 27,
    borderWidth: 2,
    borderColor: homeDesign.serviceIconBorder,
    backgroundColor: homeDesign.serviceIconBg,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 8,
  },
  serviceText: {
    flex: 1,
    minWidth: 0,
  },
  serviceTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: '#FFFFFF',
  },
  serviceSubtitle: {
    fontSize: 12,
    color: '#F5F2E8',
    marginTop: 4,
  },
  arrowCircle: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#FFFFFF',
    justifyContent: 'center',
    alignItems: 'center',
    flexShrink: 0,
  },
});

type IoniconsName = 'car-outline' | 'bed-outline' | 'calendar-outline' | 'compass-outline' | 'arrow-forward';

interface HomeServiceGridProps {
  onServicePress?: (key: ServiceKey) => void;
}

export const HomeServiceGrid = ({ onServicePress }: HomeServiceGridProps) => {
  const router = useRouter();
  const { width: screenWidth } = useWindowDimensions();

  const horizontalPadding = 24;
  const columnGap = 16;
  const cardWidth = (screenWidth - horizontalPadding * 2 - columnGap) / 2;

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
          activeOpacity={0.88}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <ImageBackground
            source={{ uri: service.image }}
            style={styles.cardImage}
            imageStyle={{ borderRadius: 29 }}
            resizeMode="cover"
          >
            <View style={styles.imageShade} />
            <View style={styles.cardContent}>
              <View style={styles.serviceIcon}>
                <Ionicons name={service.icon as IoniconsName} size={26} color="#FFFFFF" />
              </View>
              <View style={styles.serviceText}>
                <Text style={styles.serviceTitle}>{service.title}</Text>
                <Text style={styles.serviceSubtitle}>{service.subtitle}</Text>
              </View>
              <View style={styles.arrowCircle}>
                <Ionicons name="arrow-forward" size={18} color={homeDesign.primaryGreenDark} />
              </View>
            </View>
          </ImageBackground>
        </TouchableOpacity>
      ))}
    </View>
  );
};

export default HomeServiceGrid;