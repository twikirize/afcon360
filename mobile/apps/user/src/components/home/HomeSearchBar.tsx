import React from 'react';
import { View, TextInput, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { spacing, radii, typography } from '../../theme/tokens';
import { homeDesign } from '../../theme/tokens';

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 20,
    paddingVertical: 10,
  },
  searchBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: homeDesign.cardBg,
    borderWidth: 1,
    borderColor: homeDesign.borderColor,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 10,
  },
  icon: {
    color: homeDesign.textGray,
    fontSize: 22,
  },
  input: {
    flex: 1,
    fontSize: 15,
    color: homeDesign.textDark,
    fontWeight: '500',
  },
});

interface HomeSearchBarProps {
  placeholder?: string;
  onChangeText?: (text: string) => void;
  value?: string;
}

type MaterialIconName = 'search';

export const HomeSearchBar = ({
  placeholder = 'Find a ride, event or stay...',
  onChangeText,
  value = '',
}: HomeSearchBarProps) => {
  return (
    <View style={styles.container}>
      <View style={styles.searchBox}>
        <MaterialIcons name="search" size={22} color={homeDesign.textGray} />
        <TextInput
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          placeholderTextColor={homeDesign.textGray}
          style={styles.input}
          autoCorrect={false}
          accessibilityLabel="Search for rides, events, or stays"
        />
      </View>
    </View>
  );
};

export default HomeSearchBar;