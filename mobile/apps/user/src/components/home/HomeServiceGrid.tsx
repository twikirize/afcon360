import React from 'react';
import { View, Text, TouchableOpacity, ImageBackground, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

type ServiceKey = 'transport' | 'stays' | 'events' | 'adventure';

interface Service {
  key: ServiceKey;
  label: string;
  hint: string;
  icon: string;
  image: string;
  destination: string;
}

const SERVICES: Service[] = [
  {
    key: 'transport',
    label: 'Transport',
    hint: 'Ride with ease',
    icon: 'directions-car',
    image: 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=800&q=85',
    destination: '/(service)/ride',
  },
  {
    key: 'stays',
    label: 'Stays',
    hint: 'Find the best stays',
    icon: 'hotel',
    image: 'https://images.unsplash.com/photo-1611892440504-42a792e24d32?auto=format&fit=crop&w=800&q=85',
    destination: '/(service)/stays',
  },
  {
    key: 'events',
    label: 'Events & Tickets',
    hint: 'Be part of it',
    icon: 'confirmation-number',
    image: 'https://images.unsplash.com/photo-1506157786151-b8491531f063?auto=format&fit=crop&w=800&q=85',
    destination: '/(service)/events',
  },
  {
    key: 'adventure',
    label: 'Adventure',
    hint: 'Explore more',
    icon: 'explore',
    image: 'https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=800&q=85',
    destination: '/(service)/adventure',
  },
];

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between',
    marginBottom: 20,
  },
  card: {
    width: '48.5%', height: 142, borderRadius: 17, overflow: 'hidden',
    marginBottom: 13, backgroundColor: homeDesign.primaryGreen,
  },
  image: { borderRadius: 17 },
  shade: {
    flex: 1, justifyContent: 'flex-end', padding: 13,
    backgroundColor: 'rgba(3, 25, 15, 0.42)',
  },
  iconRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 7 },
  iconWrap: {
    width: 34, height: 34, borderRadius: 17, backgroundColor: 'rgba(13, 59, 37, 0.88)',
    borderWidth: 1, borderColor: '#E6C56B', alignItems: 'center', justifyContent: 'center',
  },
  arrow: {
    marginLeft: 'auto', width: 28, height: 28, borderRadius: 14,
    backgroundColor: '#FFFDF6', alignItems: 'center', justifyContent: 'center',
  },
  title: { color: '#FFFFFF', fontSize: 15, fontWeight: '800' },
  hint: { color: '#F5F0E4', fontSize: 11, marginTop: 2, fontWeight: '500' },
});

type MaterialIconName = 'directions-car' | 'hotel' | 'confirmation-number' | 'explore' | 'arrow-forward';

interface HomeServiceGridProps { onServicePress?: (key: ServiceKey) => void; }

export const HomeServiceGrid = ({ onServicePress }: HomeServiceGridProps) => {
  const router = useRouter();
  const handlePress = (service: Service) => {
    onServicePress?.(service.key);
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
          activeOpacity={0.88}
        >
          <ImageBackground source={{ uri: service.image }} style={StyleSheet.absoluteFill} imageStyle={styles.image}>
            <View style={styles.shade}>
              <View style={styles.iconRow}>
                <View style={styles.iconWrap}>
                  <MaterialIcons name={service.icon as MaterialIconName} size={19} color={homeDesign.gold} />
                </View>
                <View style={styles.arrow}>
                  <MaterialIcons name="arrow-forward" size={17} color={homeDesign.primaryGreen} />
                </View>
              </View>
              <Text style={styles.title}>{service.label}</Text>
              <Text style={styles.hint}>{service.hint}</Text>
            </View>
          </ImageBackground>
        </TouchableOpacity>
      ))}
    </View>
  );
};

export default HomeServiceGrid;