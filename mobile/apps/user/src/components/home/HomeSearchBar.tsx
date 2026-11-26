import React from 'react';
import { View, TextInput, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { homeDesign } from '../../theme/tokens';

const styles = StyleSheet.create({
  container: { paddingHorizontal: 20, marginTop: -25, marginBottom: 10, zIndex: 2 },
  searchBox: {
    minHeight: 58, flexDirection: 'row', alignItems: 'center',
    backgroundColor: '#FFFEFA', borderWidth: 1, borderColor: '#E9E1D2',
    borderRadius: 30, paddingHorizontal: 18, gap: 12,
    shadowColor: '#173D28', shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 0.12, shadowRadius: 12, elevation: 5,
  },
  input: { flex: 1, fontSize: 14, color: homeDesign.textDark, fontWeight: '500' },
  filter: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: homeDesign.primaryGreen,
    alignItems: 'center', justifyContent: 'center',
  },
});

interface HomeSearchBarProps {
  placeholder?: string;
  onChangeText?: (text: string) => void;
  value?: string;
}

export const HomeSearchBar = ({
  placeholder = 'Search destinations, events or services...',
  onChangeText,
  value = '',
}: HomeSearchBarProps) => (
  <View style={styles.container}>
    <View style={styles.searchBox}>
      <MaterialIcons name="search" size={24} color={homeDesign.primaryGreen} />
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor="#8A8275"
        style={styles.input}
        autoCorrect={false}
        accessibilityLabel="Search destinations, events, or services"
      />
      <View style={styles.filter}>
        <MaterialIcons name="tune" size={21} color="#FFFFFF" />
      </View>
    </View>
  </View>
);

export default HomeSearchBar;