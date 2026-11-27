import React from 'react';
import { View, Text, ImageBackground, TextInput, TouchableOpacity, StyleSheet } from 'react-native';
import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

const styles = StyleSheet.create({
  container: {
    marginTop: 2,
  },
  hero: {
    height: 365,
    width: '100%',
    borderRadius: 17,
    overflow: 'hidden',
    justifyContent: 'flex-end',
    backgroundColor: homeDesign.primaryGreenDark,
  },
  heroImage: {
    borderRadius: 17,
  },
  heroScrim: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
  },
  heroContent: {
    paddingHorizontal: 23,
    paddingBottom: 64,
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
  searchWrap: {
    position: 'absolute',
    bottom: -25,
    left: 16,
    right: 16,
    height: 50,
    borderRadius: 25,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.38)',
    elevation: 8,
    shadowColor: '#04210F',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.28,
    shadowRadius: 14,
  },
  searchTint: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    backgroundColor: 'rgba(6, 40, 20, 0.42)',
  },
  searchGloss: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: '55%',
  },
  searchInner: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 15,
  },
  searchIcon: {
    marginRight: 10,
  },
  searchInput: {
    flex: 1,
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '500',
    padding: 0,
  },
  searchFilterBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: 'rgba(247, 200, 21, 0.55)',
  },
  searchFilterFace: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
  },
});

interface HomeHeroBannerProps {
  onExplorePress?: () => void;
  searchValue?: string;
  onSearchChange?: (text: string) => void;
  onSearchSubmit?: () => void;
  onSearchFilterPress?: () => void;
}

export const HomeHeroBanner = ({
  onExplorePress,
  searchValue = '',
  onSearchChange,
  onSearchSubmit,
  onSearchFilterPress,
}: HomeHeroBannerProps) => {
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
        <LinearGradient
          colors={['rgba(5, 24, 19, 0.06)', 'rgba(5, 24, 19, 0.42)', 'rgba(5, 24, 19, 0.86)'] as const}
          start={{ x: 0.5, y: 0 }}
          end={{ x: 0.5, y: 1 }}
          style={styles.heroScrim}
        />
        <View style={styles.heroCounter}>
          <View style={styles.counterDot} />
          <Text style={styles.counterText}>01 / 04</Text>
        </View>
        <View style={styles.heroContent}>
          <Text style={styles.heroKicker}>THE WORLD, OPEN TO YOU</Text>
          <Text style={styles.heroTitle}>Make every{'\n'}journey matter.</Text>
          <Text style={styles.heroDescription}>
            Move, stay, explore and experience more — all in one place.
          </Text>
          <TouchableOpacity
            style={styles.heroButton}
            onPress={handleExplorePress}
            accessibilityRole="button"
            accessibilityLabel="Explore Pamoja"
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Text style={styles.heroButtonText}>Explore Pamoja  {'\u2197'}</Text>
          </TouchableOpacity>
        </View>
      </ImageBackground>

      <View style={styles.searchWrap}>
        <View style={styles.searchTint} />
        <BlurView tint="dark" intensity={45} style={StyleSheet.absoluteFill} />
        <LinearGradient
          colors={['rgba(255, 255, 255, 0.26)', 'rgba(255, 255, 255, 0.02)'] as const}
          start={{ x: 0, y: 0 }}
          end={{ x: 0, y: 1 }}
          style={styles.searchGloss}
          pointerEvents="none"
        />
        <View style={styles.searchInner}>
          <Ionicons name="search" size={19} color="rgba(255, 255, 255, 0.92)" style={styles.searchIcon} />
          <TextInput
            value={searchValue}
            onChangeText={onSearchChange}
            onSubmitEditing={() => onSearchSubmit?.()}
            placeholder="Search stays, transport, events..."
            placeholderTextColor="rgba(255, 255, 255, 0.72)"
            style={styles.searchInput}
            returnKeyType="search"
            autoCorrect={false}
            accessibilityLabel="Search for stays, transport, events or experiences"
          />
          <TouchableOpacity
            style={styles.searchFilterBtn}
            onPress={onSearchFilterPress}
            accessibilityRole="button"
            accessibilityLabel="Browse all Pamoja services"
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <LinearGradient
              colors={['#14442A', '#08260F'] as const}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={styles.searchFilterFace}
            />
            <Ionicons name="options-outline" size={17} color="#F7C815" />
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
};

export default HomeHeroBanner;
