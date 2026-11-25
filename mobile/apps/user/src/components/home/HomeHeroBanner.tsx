import React from 'react';
import { View, Text, Image, TouchableOpacity, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { spacing, radii } from '../../theme/tokens';
import { homeDesign } from '../../theme/tokens';

const HERO_IMAGE_URL = 'https://images.unsplash.com/photo-1573164713988-8665fc963095?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80';

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 20,
    backgroundColor: homeDesign.heroBg,
    borderRadius: 16,
    padding: 24,
    minHeight: 160,
    flexDirection: 'row',
    overflow: 'hidden',
  },
  textContainer: {
    flex: 1,
    zIndex: 2,
    maxWidth: '60%',
  },
  title: {
    color: homeDesign.primaryGreen,
    fontSize: 24,
    fontWeight: '700',
    lineHeight: 30,
    marginBottom: 12,
  },
  subtitle: {
    color: homeDesign.textGray,
    fontSize: 12,
    fontWeight: '500',
  },
  image: {
    position: 'absolute',
    right: -10,
    bottom: 0,
    width: '50%',
    height: '110%',
    opacity: 0.9,
  },
});

type MaterialIconName = 'arrow-forward';

interface HomeHeroBannerProps {
  onExplorePress?: () => void;
}

export const HomeHeroBanner = ({ onExplorePress }: HomeHeroBannerProps) => {
  const router = useRouter();

  const handleExplorePress = () => {
    if (onExplorePress) {
      onExplorePress();
    } else {
      router.push('/(tabs)/explore' as any);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.textContainer}>
        <Text style={styles.title}>Your world,{'\\n'}together.</Text>
        <Text style={styles.subtitle}>One app. More to explore.</Text>
      </View>
      <Image
        source={{ uri: HERO_IMAGE_URL }}
        style={styles.image}
        resizeMode="cover"
      />
    </View>
  );
};

export default HomeHeroBanner;