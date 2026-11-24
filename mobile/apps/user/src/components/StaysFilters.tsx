import React, { useState, useEffect } from "react";
import { View, Text, Pressable, StyleSheet, ScrollView, TextInput } from "react-native";
import { colors, spacing, radii, typography } from "../theme/tokens";

export type StaysFilters = {
  priceMin?: number;
  priceMax?: number;
  minRating?: number;
  propertyTypes?: string[];
  amenities?: string[];
};

type StaysFiltersBottomSheetProps = {
  visible: boolean;
  onClose: () => void;
  onApply: (filters: StaysFilters) => void;
  initialFilters?: StaysFilters;
  properties?: Array<{ property_type: string; starting_price: string; rating: number }>;
};

const PROPERTY_TYPES = ["Hotel", "Apartment", "Villa", "Guesthouse", "Resort", "Hostel", "Lodge", "Camp"];
const AMENITIES = ["WiFi", "Pool", "Parking", "Restaurant", "Gym", "Spa", "Airport Shuttle", "Breakfast", "Pet Friendly", "Kitchen"];

export function StaysFiltersBottomSheet({
  visible,
  onClose,
  onApply,
  initialFilters,
  properties = [],
}: StaysFiltersBottomSheetProps) {
  const [priceMin, setPriceMin] = useState<string>(initialFilters?.priceMin?.toString() ?? "");
  const [priceMax, setPriceMax] = useState<string>(initialFilters?.priceMax?.toString() ?? "");
  const [minRating, setMinRating] = useState<number>(initialFilters?.minRating ?? 0);
  const [selectedTypes, setSelectedTypes] = useState<string[]>(initialFilters?.propertyTypes ?? []);
  const [selectedAmenities, setSelectedAmenities] = useState<string[]>(initialFilters?.amenities ?? []);

  useEffect(() => {
    if (initialFilters) {
      setPriceMin(initialFilters.priceMin?.toString() ?? "");
      setPriceMax(initialFilters.priceMax?.toString() ?? "");
      setMinRating(initialFilters.minRating ?? 0);
      setSelectedTypes(initialFilters.propertyTypes ?? []);
      setSelectedAmenities(initialFilters.amenities ?? []);
    }
  }, [initialFilters]);

  const toggleType = (type: string) => {
    setSelectedTypes((prev) => prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]);
  };

  const toggleAmenity = (amenity: string) => {
    setSelectedAmenities((prev) => prev.includes(amenity) ? prev.filter((a) => a !== amenity) : [...prev, amenity]);
  };

  const hasActiveFilters = () => {
    return priceMin !== "" || priceMax !== "" || minRating > 0 || selectedTypes.length > 0 || selectedAmenities.length > 0;
  };

  const clearAll = () => {
    setPriceMin("");
    setPriceMax("");
    setMinRating(0);
    setSelectedTypes([]);
    setSelectedAmenities([]);
  };

  const apply = () => {
    const filters: StaysFilters = {};
    if (priceMin !== "") filters.priceMin = Number(priceMin);
    if (priceMax !== "") filters.priceMax = Number(priceMax);
    if (minRating > 0) filters.minRating = minRating;
    if (selectedTypes.length > 0) filters.propertyTypes = selectedTypes;
    if (selectedAmenities.length > 0) filters.amenities = selectedAmenities;
    onApply(filters);
    onClose();
  };

  if (!visible) return null;

  return (
    <View style={styles.overlay} onTouchStart={onClose}>
      <View style={styles.sheet} onTouchStart={(e) => e.stopPropagation()}>
        <View style={styles.handle} />
        <View style={styles.header}>
          <Text style={styles.title}>Filters</Text>
          {hasActiveFilters() && (
            <Pressable onPress={clearAll} style={styles.clearButton}>
              <Text style={styles.clearText}>Clear all</Text>
            </Pressable>
          )}
        </View>
        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Price per night</Text>
            <View style={styles.priceInputs}>
              <TextInput
                placeholder="Min"
                value={priceMin}
                onChangeText={setPriceMin}
                keyboardType="numeric"
                style={styles.priceInput}
                placeholderTextColor="#87938C"
              />
              <Text style={styles.priceDivider}>–</Text>
              <TextInput
                placeholder="Max"
                value={priceMax}
                onChangeText={setPriceMax}
                keyboardType="numeric"
                style={styles.priceInput}
                placeholderTextColor="#87938C"
              />
            </View>
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Minimum rating</Text>
            <View style={styles.ratingStars}>
              {[1, 2, 3, 4, 5].map((star) => (
                <Pressable
                  key={star}
                  onPress={() => setMinRating(minRating === star ? 0 : star)}
                  style={styles.ratingStar}
                >
                  <Text style={[styles.ratingStarText, minRating >= star && styles.ratingStarFilled]}>★</Text>
                </Pressable>
              ))}
            </View>
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Property type</Text>
            <View style={styles.chipGrid}>
              {PROPERTY_TYPES.map((type) => (
                <Pressable
                  key={type}
                  onPress={() => toggleType(type)}
                  style={[styles.chip, selectedTypes.includes(type) && styles.chipSelected]}
                >
                  <Text style={[styles.chipText, selectedTypes.includes(type) && styles.chipTextSelected]}>{type}</Text>
                </Pressable>
              ))}
            </View>
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Amenities</Text>
            <View style={styles.chipGrid}>
              {AMENITIES.map((amenity) => (
                <Pressable
                  key={amenity}
                  onPress={() => toggleAmenity(amenity)}
                  style={[styles.chip, selectedAmenities.includes(amenity) && styles.chipSelected]}
                >
                  <Text style={[styles.chipText, selectedAmenities.includes(amenity) && styles.chipTextSelected]}>{amenity}</Text>
                </Pressable>
              ))}
            </View>
          </View>
        </ScrollView>
        <View style={styles.footer}>
          <Pressable onPress={onClose} style={[styles.button, styles.buttonSecondary]}>
            <Text style={styles.buttonTextSecondary}>Cancel</Text>
          </Pressable>
          <Pressable onPress={apply} style={styles.button}>
            <Text style={styles.buttonText}>Apply {hasActiveFilters() ? `(${Object.keys({
              priceMin: priceMin !== "" ? 1 : 0,
              priceMax: priceMax !== "" ? 1 : 0,
              minRating: minRating > 0 ? 1 : 0,
              propertyTypes: selectedTypes.length,
              amenities: selectedAmenities.length,
            }).filter(v => v).length})` : ""}</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: "flex-end",
    zIndex: 100,
  },
  sheet: {
    backgroundColor: "#FFFFFF",
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingBottom: 24,
    maxHeight: "85%",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: -4 },
    shadowOpacity: 0.15,
    shadowRadius: 20,
    elevation: 10,
  },
  handle: {
    width: 40,
    height: 5,
    borderRadius: 3,
    backgroundColor: "#D1D9D2",
    alignSelf: "center",
    marginTop: 10,
    marginBottom: 16,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 20,
    marginBottom: 8,
  },
  title: { color: "#122419", fontSize: 18, fontWeight: "900" },
  clearButton: { paddingHorizontal: 12, paddingVertical: 6 },
  clearText: { color: "#0E5B36", fontSize: 13, fontWeight: "800" },
  scrollContent: { paddingHorizontal: 20, gap: 20 },
  section: { gap: 10 },
  sectionTitle: { color: "#122419", fontSize: 14, fontWeight: "800" },
  priceInputs: { flexDirection: "row", alignItems: "center", gap: 10 },
  priceInput: {
    flex: 1,
    backgroundColor: "#F5F6F2",
    borderWidth: 1,
    borderColor: "#E6EAE4",
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: "#122419",
    fontSize: 15,
  },
  priceDivider: { color: "#6C766E", fontSize: 16, fontWeight: "700" },
  ratingStars: { flexDirection: "row", gap: 8 },
  ratingStar: { width: 40, height: 40, borderRadius: 12, backgroundColor: "#F5F6F2", alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#E6EAE4" },
  ratingStarText: { fontSize: 20, color: "#D1D9D2" },
  ratingStarFilled: { color: "#FFCC00" },
  chipGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    backgroundColor: "#F5F6F2",
    borderWidth: 1,
    borderColor: "#E6EAE4",
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  chipSelected: { backgroundColor: "#E8F4EC", borderColor: "#0E5B36" },
  chipText: { color: "#122419", fontSize: 12, fontWeight: "700" },
  chipTextSelected: { color: "#0E5B36" },
  footer: {
    flexDirection: "row",
    gap: 12,
    paddingHorizontal: 20,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: "#E6EAE4",
  },
  button: { flex: 1, backgroundColor: "#0E5B36", borderRadius: 14, paddingVertical: 14, alignItems: "center" },
  buttonSecondary: { backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#E6EAE4" },
  buttonText: { color: "#FFFFFF", fontSize: 14, fontWeight: "900" },
  buttonTextSecondary: { color: "#122419", fontSize: 14, fontWeight: "900" },
});

export default StaysFiltersBottomSheet;