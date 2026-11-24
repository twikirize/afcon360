import React from "react";
import { Pressable, Text, View, StyleSheet, Image } from "react-native";
import { colors, typography, spacing, radii, shadows } from "../theme/tokens";

export type PropertyCardProps = {
  property: {
    public_id: string;
    title: string;
    city: string;
    country: string;
    starting_price: string;
    currency: string;
    rating: number;
    review_count: number;
    room_types: Array<{ room_token: string }>;
    main_image: string | null;
  };
  selected?: boolean;
  onPress: () => void;
  onWishlist?: () => void;
  isWishlisted?: boolean;
};

export function PropertyCard({ property, selected, onPress, onWishlist, isWishlisted }: PropertyCardProps) {
  const hasImage = property.main_image && property.main_image.trim().length > 0;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`View ${property.title} in ${property.city}, ${property.country}`}
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        selected && styles.cardSelected,
        pressed && styles.cardPressed,
      ]}
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
    >
      {hasImage ? (
        <View style={styles.imageWrapper}>
          <Image
            source={{ uri: property.main_image ?? undefined }}
            style={styles.image}
            resizeMode="cover"
          />
          {property.rating > 0 && (
            <View style={styles.ratingBadge}>
              <Text style={styles.ratingText}>★ {property.rating.toFixed(1)}</Text>
            </View>
          )}
          {onWishlist && (
            <Pressable
              onPress={(e) => { e.stopPropagation(); onWishlist(); }}
              accessibilityRole="button"
              accessibilityLabel={isWishlisted ? "Remove from wishlist" : "Add to wishlist"}
              style={styles.wishlistButton}
              hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
            >
              <Text style={styles.wishlistIcon}>{isWishlisted ? "♥" : "♡"}</Text>
            </Pressable>
          )}
        </View>
      ) : (
        <View style={styles.imagePlaceholder}>
          <Text style={styles.placeholderIcon}>🏨</Text>
          {onWishlist && (
            <Pressable
              onPress={(e) => { e.stopPropagation(); onWishlist(); }}
              accessibilityRole="button"
              accessibilityLabel={isWishlisted ? "Remove from wishlist" : "Add to wishlist"}
              style={styles.wishlistButton}
              hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
            >
              <Text style={styles.wishlistIcon}>{isWishlisted ? "♥" : "♡"}</Text>
            </Pressable>
          )}
        </View>
      )}
      <View style={styles.content}>
        <View style={styles.headerRow}>
          <Text style={[styles.title, selected && styles.titleSelected]} numberOfLines={2}>
            {property.title}
          </Text>
          {selected && <Text style={styles.selectedBadge}>SELECTED</Text>}
        </View>
        <Text style={styles.location}>{property.city}, {property.country}</Text>
        <View style={styles.priceRow}>
          <Text style={styles.price}>From {money(property.starting_price, property.currency)}</Text>
          <Text style={styles.perNight}>per night</Text>
        </View>
        <View style={styles.metaRow}>
          {property.rating > 0 && (
            <View style={styles.metaItem}>
              <Text style={styles.metaIcon}>★</Text>
              <Text style={styles.metaText}>{property.rating.toFixed(1)} · {property.review_count} reviews</Text>
            </View>
          )}
          {property.room_types.length > 0 && (
            <View style={styles.metaItem}>
              <Text style={styles.metaIcon}>🛏</Text>
              <Text style={styles.metaText}>{property.room_types.length} room type(s)</Text>
            </View>
          )}
        </View>
      </View>
    </Pressable>
  );
}

function money(value: string, currency: string): string {
  const number = Number(value);
  return Number.isFinite(number)
    ? `${number.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${currency}`
    : `${value} ${currency}`;
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: "#E6EAE4",
    borderRadius: 18,
    overflow: "hidden",
    backgroundColor: "#FFFFFF",
    ...shadows.card,
  },
  cardSelected: {
    borderColor: "#0E5B36",
    borderWidth: 2,
    backgroundColor: "#EFF6F0",
  },
  cardPressed: {
    opacity: 0.9,
  },
  imageWrapper: {
    position: "relative",
    height: 160,
  },
  image: {
    width: "100%",
    height: "100%",
  },
  imagePlaceholder: {
    height: 160,
    backgroundColor: "#E8F0E8",
    alignItems: "center",
    justifyContent: "center",
  },
  placeholderIcon: { fontSize: 48 },
  ratingBadge: {
    position: "absolute",
    top: 8,
    left: 8,
    backgroundColor: "rgba(0,0,0,0.7)",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  ratingText: { color: "#FFCC00", fontSize: 11, fontWeight: "900" },
  wishlistButton: {
    position: "absolute",
    top: 8,
    right: 8,
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "rgba(255,255,255,0.95)",
    alignItems: "center",
    justifyContent: "center",
    ...shadows.card,
  },
  wishlistIcon: { fontSize: 16, color: "#0E5B36" },
  content: { padding: 14, gap: 6 },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 8 },
  title: { color: "#122419", fontSize: 16, fontWeight: "900", lineHeight: 21, flex: 1 },
  titleSelected: { color: "#093E24" },
  selectedBadge: {
    backgroundColor: "#0E5B36",
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 6,
    flexShrink: 0,
  },
  location: { color: "#6C766E", fontSize: 12, lineHeight: 16 },
  priceRow: { flexDirection: "row", alignItems: "baseline", gap: 4 },
  price: { color: "#122419", fontSize: 16, fontWeight: "900" },
  perNight: { color: "#6C766E", fontSize: 11 },
  metaRow: { flexDirection: "row", gap: 12, flexWrap: "wrap", marginTop: 2 },
  metaItem: { flexDirection: "row", alignItems: "center", gap: 4 },
  metaIcon: { fontSize: 11 },
  metaText: { color: "#6C766E", fontSize: 11, fontWeight: "600" },
});

export default PropertyCard;