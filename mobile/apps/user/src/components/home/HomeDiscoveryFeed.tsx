import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

type FeedItem = { feed_id: string; type: string; title?: string; body?: string; image_url?: string; link_url?: string; author_name?: string; source_module?: string; created_at?: string | null };
type FeedResponse = { items?: FeedItem[]; page?: number; has_more?: boolean; error?: string };
type Category = 'All' | 'Events' | 'Updates' | 'Offers';
const FILTERS: Category[] = ['All', 'Events', 'Updates', 'Offers'];

function kind(item: FeedItem): Category {
  const source = (item.source_module || '').toLowerCase();
  if (item.type === 'ad' || source.includes('offer') || source.includes('promotion') || source.includes('marketing')) return 'Offers';
  if (item.type === 'event' || source.includes('event')) return 'Events';
  return 'Updates';
}
function dateLabel(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

export const HomeDiscoveryFeed = ({ baseUrl, refreshKey = 0 }: { baseUrl: string; refreshKey?: number }) => {
  const router = useRouter();
  const [items, setItems] = useState<FeedItem[]>([]);
  const [filter, setFilter] = useState<Category>('All');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const inFlight = useRef(false);

  const load = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    setError('');
    try {
      const query = new URLSearchParams({ page: '1', per_page: '10', layout: 'mixed', seed: String(Date.now()) });
      const response = await fetch(baseUrl.replace(/\/$/, '') + '/api/home/feed?' + query.toString());
      if (!response.ok) throw new Error('Could not refresh Pamoja highlights.');
      const result = await response.json() as FeedResponse;
      if (result.error && !Array.isArray(result.items)) throw new Error(result.error);
      setItems(Array.isArray(result.items) ? result.items.slice(0, 8) : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Highlights are temporarily unavailable.');
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, [baseUrl]);

  useEffect(() => { void load(); }, [load, refreshKey]);

  const openItem = async (item: FeedItem) => {
    const category = kind(item);
    if (category === 'Events') { router.push('/(service)/events' as any); return; }
    const link = item.link_url || '';
    if (/^https?:\/\//i.test(link)) { try { await Linking.openURL(link); } catch { /* no-op */ } }
    else if (link.startsWith('/')) { try { await Linking.openURL(baseUrl.replace(/\/$/, '') + link); } catch { /* no-op */ } }
  };
  const visible = items.filter((item) => filter === 'All' || kind(item) === filter);

  return (
    <View style={styles.container}>
      <View style={styles.heading}>
        <View style={styles.headingCopy}>
          <Text style={styles.title}>Pamoja Highlights</Text>
          <Text style={styles.subtitle}>Events, updates and offers worth a look.</Text>
        </View>
        <MaterialIcons name="campaign" size={25} color={homeDesign.primaryGreen} />
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>
        {FILTERS.map((value) => <Pressable key={value} onPress={() => setFilter(value)} style={[styles.filter, filter === value && styles.filterActive]}><Text style={[styles.filterText, filter === value && styles.filterTextActive]}>{value}</Text></Pressable>)}
      </ScrollView>
      {loading ? <View style={styles.state}><ActivityIndicator color={homeDesign.primaryGreen} /><Text style={styles.stateText}>Loading highlights…</Text></View>
        : error && items.length === 0 ? <Pressable onPress={() => void load()} style={styles.state}><MaterialIcons name="cloud-off" size={24} color={homeDesign.textGray} /><Text style={styles.stateText}>{error} Tap to retry.</Text></Pressable>
        : visible.length === 0 ? <View style={styles.state}><Text style={styles.stateText}>Fresh Pamoja highlights will appear here.</Text></View>
        : <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.cards}>
          {visible.map((item) => {
            const category = kind(item);
            const sponsored = item.type === 'ad';
            return <Pressable key={item.feed_id} onPress={() => void openItem(item)} style={styles.card}>
              <View style={styles.media}>
                {item.image_url ? <Image source={{ uri: item.image_url }} style={styles.image} resizeMode="cover" /> : <View style={styles.imageFallback}><MaterialIcons name={category === 'Events' ? 'event' : category === 'Offers' ? 'local-offer' : 'campaign'} size={30} color="#F0D27A" /></View>}
                <Text style={styles.pill}>{sponsored ? 'SPONSORED' : category.toUpperCase()}</Text>
              </View>
              <View style={styles.cardCopy}>
                <Text style={styles.cardTitle} numberOfLines={2}>{item.title || item.author_name || 'Discover more on Pamoja'}</Text>
                <View style={styles.cardFoot}><Text style={styles.date}>{dateLabel(item.created_at)}</Text><MaterialIcons name="arrow-forward" size={16} color={homeDesign.primaryGreen} /></View>
              </View>
            </Pressable>;
          })}
        </ScrollView>}
      {error && items.length > 0 ? <Text style={styles.inlineError}>{error}</Text> : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: { marginTop: 8, marginBottom: 20 },
  heading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  headingCopy: { flex: 1 },
  title: { color: homeDesign.textDark, fontSize: 26, lineHeight: 32, fontWeight: '900', letterSpacing: -0.7, fontFamily: 'serif' },
  subtitle: { color: homeDesign.textGray, fontSize: 12, marginTop: 3 },
  filters: { gap: 7, paddingBottom: 12 },
  filter: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 18, backgroundColor: '#F0EBDD', borderWidth: 1, borderColor: '#E6DDCA' },
  filterActive: { backgroundColor: homeDesign.primaryGreen, borderColor: homeDesign.primaryGreen },
  filterText: { color: homeDesign.primaryGreen, fontSize: 11, fontWeight: '800' },
  filterTextActive: { color: '#FFFFFF' },
  cards: { gap: 11, paddingRight: 4 },
  card: { width: 224, borderRadius: 18, overflow: 'hidden', backgroundColor: '#FFFEFA', borderWidth: 1, borderColor: homeDesign.borderColor },
  media: { height: 112, backgroundColor: homeDesign.primaryGreen },
  image: { width: '100%', height: '100%' },
  imageFallback: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: homeDesign.primaryGreen },
  pill: { position: 'absolute', left: 10, top: 9, color: '#F8E9B8', backgroundColor: 'rgba(0,42,23,0.82)', overflow: 'hidden', borderRadius: 10, paddingHorizontal: 8, paddingVertical: 5, fontSize: 8, fontWeight: '900', letterSpacing: 0.7 },
  cardCopy: { paddingHorizontal: 12, paddingVertical: 11, minHeight: 77, justifyContent: 'space-between' },
  cardTitle: { color: homeDesign.textDark, fontSize: 13, lineHeight: 18, fontWeight: '800' },
  cardFoot: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 },
  date: { color: homeDesign.textGray, fontSize: 10 },
  state: { minHeight: 105, borderRadius: 17, backgroundColor: '#FFFEFA', borderWidth: 1, borderColor: homeDesign.borderColor, alignItems: 'center', justifyContent: 'center', padding: 18, gap: 8 },
  stateText: { color: homeDesign.textGray, fontSize: 12, textAlign: 'center', lineHeight: 18 },
  inlineError: { color: '#9A342D', fontSize: 10, marginTop: 7 },
});
export default HomeDiscoveryFeed;
