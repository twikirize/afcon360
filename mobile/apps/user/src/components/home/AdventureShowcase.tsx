import React from 'react';
import { ImageBackground, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

const DESTINATIONS = [
  { title: 'Zanzibar Beach Gateway', place: 'Tanzania · Indian Ocean', image: 'https://images.unsplash.com/photo-1500375592092-40eb2168fd21?auto=format&fit=crop&w=1000&q=85', tag: 'BEACH ESCAPE' },
  { title: 'Bwindi Forest Escape', place: 'Uganda · Mountain gorillas', image: 'https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=1000&q=85', tag: 'WILD AFRICA' },
  { title: 'Serengeti Horizons', place: 'Tanzania · Safari country', image: 'https://images.unsplash.com/photo-1516426122078-c23e76319801?auto=format&fit=crop&w=1000&q=85', tag: 'ON SAFARI' },
];

export const AdventureShowcase = () => {
  const router = useRouter();
  return (
    <View style={styles.container}>
      <View style={styles.heading}>
        <View style={styles.headingCopy}>
          <Text style={styles.title}>Your Next Adventure</Text>
          <Text style={styles.subtitle}>A little inspiration for where to go next.</Text>
        </View>
        <MaterialIcons name="explore" size={25} color={homeDesign.primaryGreen} />
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.scroller}>
        {DESTINATIONS.map((destination) => (
          <Pressable key={destination.title} onPress={() => router.push('/(service)/adventure' as any)} style={styles.card}>
            <ImageBackground source={{ uri: destination.image }} style={styles.image} imageStyle={styles.imageRadius} resizeMode="cover">
              <View style={styles.scrim}>
                <Text style={styles.tag}>{destination.tag}</Text>
                <View style={styles.cardBottom}>
                  <View style={styles.copy}>
                    <Text style={styles.destination}>{destination.title}</Text>
                    <Text style={styles.place}>{destination.place}</Text>
                  </View>
                  <View style={styles.arrow}><MaterialIcons name="arrow-forward" size={19} color={homeDesign.primaryGreen} /></View>
                </View>
              </View>
            </ImageBackground>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { marginTop: 26, marginBottom: 22 },
  heading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 },
  headingCopy: { flex: 1 },
  title: { color: homeDesign.textDark, fontSize: 27, lineHeight: 33, fontWeight: '900', letterSpacing: -0.7, fontFamily: 'serif' },
  subtitle: { color: homeDesign.textGray, fontSize: 12, marginTop: 3 },
  scroller: { paddingRight: 4, gap: 12 },
  card: { width: 268, height: 174, borderRadius: 20, overflow: 'hidden', backgroundColor: homeDesign.primaryGreen },
  image: { flex: 1 },
  imageRadius: { borderRadius: 20 },
  scrim: { flex: 1, justifyContent: 'space-between', padding: 14, backgroundColor: 'rgba(4,28,17,0.20)' },
  tag: { alignSelf: 'flex-start', overflow: 'hidden', color: '#F8E9B8', backgroundColor: 'rgba(0,42,23,0.72)', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 6, fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  cardBottom: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between' },
  copy: { flex: 1, paddingRight: 8 },
  destination: { color: '#FFFFFF', fontSize: 19, lineHeight: 23, fontWeight: '900' },
  place: { color: '#F4F0E6', fontSize: 11, marginTop: 4, fontWeight: '600' },
  arrow: { width: 34, height: 34, borderRadius: 17, backgroundColor: '#FFFDF6', alignItems: 'center', justifyContent: 'center' },
});
