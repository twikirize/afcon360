import React from 'react';
import { View, Text, ImageBackground, TouchableOpacity, StyleSheet, Dimensions } from 'react-native';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

const styles = StyleSheet.create({
  container: {
    marginHorizontal: -6,
    marginTop: -2,
  },
  hero: {
    height: 365,
    width: SCREEN_WIDTH - 36,
    borderRadius: 17,
    overflow: 'hidden',
    justifyContent: 'flex-end',
    backgroundColor: homeDesign.primaryGreenDark,
  },
  heroImage: {
    borderRadius: 17,
  },
  heroShade: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(5, 24, 19, 0.34)',
  },
  heroContent: {
    paddingHorizontal: 23,
    paddingBottom: 30,
  },
  heroKicker: {
    color: '#E7D5A5',
    fontSize: 9,
    letterSpacing: 2,
    fontWeight: '700',
    marginBottom: 12,
  },
  heroTitle: {
    color: '#FFF9EC',
    fontSize: 34,
    lineHeight: 37,
    fontWeight: '500',
    letterSpacing: -0.7,
  },
  heroDescription: {
    color: '#F3EEE3',
    fontSize: 12,
    lineHeight: 18,
    maxWidth: 255,
    marginTop: 10,
  },
  heroButton: {
    alignSelf: 'flex-start',
    backgroundColor: '#FFFCF5',
    borderRadius: 4,
    paddingVertical: 12,
    paddingHorizontal: 16,
    marginTop: 18,
  },
  heroButtonText: {
    color: homeDesign.primaryGreenDark,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.3,
  },
  heroCounter: {
    position: 'absolute',
    right: 20,
    top: 19,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
  },
  counterDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: homeDesign.goldAccent,
  },
  counterText: {
    color: '#FFF9EC',
    fontSize: 9,
    letterSpacing: 1.3,
  },
});

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
      <ImageBackground
        source={require('../../../assets/pamoja-hero.jpeg')}
        style={styles.hero}
        imageStyle={styles.heroImage}
        resizeMode="cover"
      >
        <View style={styles.heroShade} />
        <View style={styles.heroCounter}>
          <View style={styles.counterDot} />
          <Text style={styles.counterText}>01 / 04</Text>
        </View>
        <View style={styles.heroContent}>
          <Text style={styles.heroKicker}>THE WORLD, OPEN TO YOU</Text>
          <Text style={styles.heroTitle}>Make every{'\\n'}journey matter.</Text>
          <Text style={styles.heroDescription}>
            Move, stay, explore and experience more — all in one place.
          </Text>
          <TouchableOpacity style={styles.heroButton} onPress={handleExplorePress} accessibilityRole="button" accessibilityLabel="Explore Pamoja" hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Text style={styles.heroButtonText}>Explore Pamoja  \u2197</Text>
          </TouchableOpacity>
        </View>
      </ImageBackground>
    </View>
  );
};

export default HomeHeroBanner;