import React from 'react';
import { View, Text, Image, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

interface AdventureItem {
  id: string;
  title: string;
  image: string;
  badge: string;
  badgeColor: string;
  rating: string;
  location: string;
  actionLabel: string;
  actionRoute: string;
}

const FEED: AdventureItem[] = [
  {
    id: 'zanzibar',
    title: 'Zanzibar Beach Getaway',
    image: 'https://images.unsplash.com/photo-1573843981267-be1999ff37cd?q=80&w=400&auto=format&fit=crop',
    badge: 'Trending',
    badgeColor: '#0A4222',
    rating: '4.8',
    location: 'Zanzibar',
    actionLabel: 'View',
    actionRoute: '/(service)/adventure',
  },
  {
    id: 'nairobi-jazz',
    title: 'Nairobi Jazz Fest',
    image: 'https://images.unsplash.com/photo-1459749411175-04bf5292ceea?q=80&w=400&auto=format&fit=crop',
    badge: 'Upcoming',
    badgeColor: '#D97706',
    rating: '4.9',
    location: 'Nairobi',
    actionLabel: 'Tickets',
    actionRoute: '/(service)/events',
  },
  {
    id: 'maasai-mara',
    title: 'Maasai Mara Safari',
    image: 'https://images.unsplash.com/photo-1516426122078-c23e76319801?q=80&w=400&auto=format&fit=crop',
    badge: 'Tour',
    badgeColor: '#2563EB',
    rating: '5.0',
    location: 'Mara',
    actionLabel: 'Book',
    actionRoute: '/(service)/adventure',
  },
];

interface AdventureFeedProps {
  onNavigate?: (route: string) => void;
}

export const AdventureFeed = ({ onNavigate }: AdventureFeedProps) => {
  const router = useRouter();

  const open = (route: string) => {
    if (onNavigate) onNavigate(route);
    router.push(route as any);
  };

  return (
    <View style={styles.container}>
      {FEED.map((item) => (
        <TouchableOpacity
          key={item.id}
          style={styles.card}
          activeOpacity={0.95}
          accessibilityRole="button"
          accessibilityLabel={item.title}
          onPress={() => open(item.actionRoute)}
        >
          <Image source={{ uri: item.image }} style={styles.image} resizeMode="cover" />
          <View style={styles.content}>
            <View style={styles.topRow}>
              <View style={[styles.badge, { backgroundColor: item.badgeColor }]}>
                <Text style={styles.badgeText}>{item.badge}</Text>
              </View>
              <Ionicons name="heart-outline" size={16} color="#D1D5DB" />
            </View>
            <Text style={styles.title} numberOfLines={1}>{item.title}</Text>
            <View style={styles.bottomRow}>
              <View>
                <View style={styles.detailRow}>
                  <Ionicons name="star" size={10} color="#F7C815" />
                  <Text style={styles.detailText}>{item.rating}</Text>
                </View>
                <View style={[styles.detailRow, styles.detailRowSpacing]}>
                  <Ionicons name="location" size={10} color="#D97706" />
                  <Text style={styles.detailText}>{item.location}</Text>
                </View>
              </View>
              <TouchableOpacity
                style={styles.actionBtn}
                onPress={() => open(item.actionRoute)}
                accessibilityRole="button"
                accessibilityLabel={item.actionLabel + ' ' + item.title}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                <Text style={styles.actionText}>{item.actionLabel}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </TouchableOpacity>
      ))}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 20,
    gap: 12,
    marginBottom: 20,
  },
  card: {
    flexDirection: 'row',
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 10,
    elevation: 3,
    shadowColor: '#09381B',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.05,
    shadowRadius: 10,
  },
  image: {
    width: 100,
    height: 105,
    borderRadius: 12,
  },
  content: {
    flex: 1,
    marginLeft: 12,
    justifyContent: 'space-between',
    minWidth: 0,
  },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
  },
  badgeText: {
    color: '#FFFFFF',
    fontSize: 8,
    fontWeight: 'bold',
    textTransform: 'uppercase',
  },
  title: {
    color: '#09381B',
    fontSize: 14,
    fontWeight: 'bold',
    marginTop: 4,
  },
  bottomRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-end',
    marginTop: 6,
  },
  detailRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  detailRowSpacing: {
    marginTop: 2,
  },
  detailText: {
    color: '#6B7280',
    fontSize: 10,
    fontWeight: '500',
  },
  actionBtn: {
    backgroundColor: '#E5F3E9',
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: 10,
  },
  actionText: {
    color: '#09381B',
    fontSize: 11,
    fontWeight: 'bold',
  },
});

export default AdventureFeed;
