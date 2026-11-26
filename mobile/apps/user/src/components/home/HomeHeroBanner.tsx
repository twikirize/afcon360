import React from 'react';
import { View, Text, ImageBackground, TouchableOpacity, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

const HERO_IMAGE_URL = 'https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=1400&q=88';

const styles = StyleSheet.create({
  container: {
    minHeight: 360,
    marginBottom: 0,
    overflow: 'hidden',
    backgroundColor: homeDesign.primaryGreen,
  },
  image: { opacity: 0.94 },
  shade: {
    flex: 1,
    minHeight: 360,
    paddingHorizontal: 24,
    paddingTop: 28,
    paddingBottom: 32,
    justifyContent: 'center',
    backgroundColor: 'rgba(5, 37, 23, 0.48)',
  },
  eyebrow: {
    alignSelf: 'flex-start',
    backgroundColor: homeDesign.gold,
    borderRadius: 30,
    paddingHorizontal: 14,
    paddingVertical: 7,
    color: '#183B29',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.7,
    overflow: 'hidden',
    marginBottom: 18,
  },
  title: {
    color: '#FFFFFF',
    fontSize: 42,
    lineHeight: 45,
    fontWeight: '800',
    letterSpacing: -1.5,
    maxWidth: 310,
    fontFamily: 'serif',
  },
  gold: { color: homeDesign.gold },
  subtitle: {
    color: '#F6F4EB',
    fontSize: 15,
    lineHeight: 22,
    fontWeight: '500',
    maxWidth: 280,
    marginTop: 14,
  },
  cta: {
    marginTop: 23,
    alignSelf: 'flex-start',
    backgroundColor: homeDesign.gold,
    borderRadius: 30,
    paddingHorizontal: 21,
    paddingVertical: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  ctaText: { color: '#173D28', fontSize: 14, fontWeight: '800' },
});

interface HomeHeroBannerProps { onExplorePress?: () => void; }

export const HomeHeroBanner = ({ onExplorePress }: HomeHeroBannerProps) => {
  const router = useRouter();
  const handleExplorePress = () => {
    if (onExplorePress) onExplorePress();
    else router.push('/(tabs)/explore' as any);
  };

  return (
    <ImageBackground source={{ uri: HERO_IMAGE_URL }} style={styles.container} imageStyle={styles.image}>
      <View style={styles.shade}>
        <Text style={styles.eyebrow}>EXPLORE AFRICA  ·  BEYOND</Text>
        <Text style={styles.title}>Your World,{'\n'}<Text style={styles.gold}>Together.</Text></Text>
        <Text style={styles.subtitle}>Discover destinations, events and experiences across the globe.</Text>
        <TouchableOpacity
          style={styles.cta}
          onPress={handleExplorePress}
          accessibilityRole="button"
          accessibilityLabel="Explore Pamoja"
        >
          <Text style={styles.ctaText}>Explore Now</Text>
          <MaterialIcons name="arrow-forward" size={18} color="#173D28" />
        </TouchableOpacity>
      </View>
    </ImageBackground>
  );
};

export default HomeHeroBanner;