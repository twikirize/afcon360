import React from 'react';
import { StyleProp, StyleSheet, Text, TouchableOpacity, View, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { homeDesign } from '../../theme/tokens';

interface HomeSectionHeaderProps {
  title: string;
  actionLabel: string;
  onActionPress: () => void;
  style?: StyleProp<ViewStyle>;
}

export const HomeSectionHeader = ({ title, actionLabel, onActionPress, style }: HomeSectionHeaderProps) => (
  <View style={[styles.container, style]}>
    <Text style={styles.title}>{title}</Text>
    <TouchableOpacity
      style={styles.action}
      onPress={onActionPress}
      accessibilityRole="button"
      accessibilityLabel={actionLabel}
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
    >
      <Text style={styles.actionText}>{actionLabel}</Text>
      <Ionicons name="arrow-forward" size={16} color={homeDesign.primaryGreenDark} />
    </TouchableOpacity>
  </View>
);

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    marginTop: 20,
    marginBottom: 12,
  },
  title: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#09381B',
    fontFamily: 'serif',
  },
  action: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  actionText: {
    fontSize: 12,
    fontWeight: 'bold',
    color: '#09381B',
  },
});

export default HomeSectionHeader;
