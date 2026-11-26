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
  icon: 'directions-car' | 'hotel' | 'confirmation-number' | 'explore';
  image: string;
  destination: string;
}

const SERVICES: Service[] = [
  {
    key: 'transport',
    label: 'Transport',
    hint: 'Ride with ease',
    icon: 'directions-car',
    image: 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=900&q=85',
    destination: '/(service)/ride',
  },
  {
    key: 'stays',
    label: 'Stays',
    hint: 'Find the best stays',
    icon: 'hotel',
    image: 'https://images.unsplash.com/photo-1611892440504-42a792e24d32?auto=format&fit=crop&w=900&q=85',
    destination: '/(service)/stays',
  },
  {
    key: 'events',
    label: 'Events & Tickets',
    hint: 'Be part of it',
    icon: 'confirmation-number',
    image: 'https://images.unsplash.com/photo-1506157786151-b8491531f063?auto=format&fit=crop&w=900&q=85',
    destination: '/(service)/events',
  },
  {
    key: 'adventure',
    label: 'Adventure',
    hint: 'Explore more',
    icon: 'explore',
    image: 'https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=900&q=85',
    destination: '/(service)/adventure',
  },
];

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    rowGap: 18,
    marginBottom: 0,
  },
  card: {
    width: '48.5%',
    height: 178,
    borderRadius: 23,
    overflow: 'hidden',
    marginBottom: 0,
    backgroundColor: homeDesign.primaryGreen,
    elevation: 5,
    shadowColor: '#173D28',
    shadowOpacity: 0.16,
    shadowRadius: 9,
    shadowOffset: { width: 0, height: 4 },
  },
  image: { borderRadius: 23 },
  shade: {
    flex: 1,
    justifyContent: 'flex-end',
    paddingHorizontal: 11,
    paddingVertical: 12,
    backgroundColor: 'rgba(3, 25, 15, 0.30)',
  },
  contentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 64,
    paddingHorizontal: 3,
  },
  iconWrap: {
    width: 57,
    height: 57,
    borderRadius: 30,
    backgroundColor: 'rgba(5, 67, 35, 0.96)',
    borderWidth: 2,
    borderColor: '#E8BD4F',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 9,
  },
  textWrap: { flex: 1, minWidth: 0 },
  title: { color: '#FFFFFF', fontSize: 15, fontWeight: '900' },
  hint: { color: '#F5F0E4', fontSize: 11, marginTop: 3, fontWeight: '500' },
  arrow: {
    width: 36,
    height: 36,
    borderRadius: 20,
    backgroundColor: '#FFFDF6',
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 4,
  },
});

interface HomeServiceGridProps {
  onServicePress?: (key: ServiceKey) => void;
}

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
          <ImageBackground
            source={{ uri: service.image }}
            style={StyleSheet.absoluteFill}
            imageStyle={styles.image}
            resizeMode="cover"
          >
            <View style={styles.shade}>
              <View style={styles.contentRow}>
                <View style={styles.iconWrap}>
                  <MaterialIcons name={service.icon} size={29} color="#FFFFFF" />
                </View>
                <View style={styles.textWrap}>
                  <Text style={styles.title} numberOfLines={1} adjustsFontSizeToFit>
                    {service.label}
                  </Text>
                  <Text style={styles.hint} numberOfLines={1}>
                    {service.hint}
                  </Text>
                </View>
                <View style={styles.arrow}>
                  <MaterialIcons name="arrow-forward" size={21} color={homeDesign.primaryGreen} />
                </View>
              </View>
            </View>
          </ImageBackground>
        </TouchableOpacity>
      ))}
    </View>
  );
};

export default HomeServiceGrid;
