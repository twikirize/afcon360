import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { colors, radii, spacing, typography, shadows } from '../../theme';
import { IconBadge } from '../common';

type ServiceCardProps = {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  onPress: () => void;
  external?: boolean;
  style?: ViewStyle;
};

import { ViewStyle } from 'react-native';

export function ServiceCard({
  icon,
  title,
  subtitle,
  onPress,
  external = false,
  style,
}: ServiceCardProps) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [
        styles.card,
        shadows.card,
        pressed && styles.cardPressed,
        style,
      ]}
    >
      <View style={styles.content}>
        <IconBadge size={36} variant="soft">{icon}</IconBadge>
        <View style={styles.textContent}>
          <Text style={[typography.cardTitle, styles.title, { color: colors.text.primary }]}>{title}</Text>
          <Text style={[typography.cardSubtitle, styles.subtitle, { color: colors.text.secondary }]}>{subtitle}</Text>
        </View>
      </View>
      {external && <Text style={styles.externalArrow}>↗</Text>}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    padding: spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  cardPressed: {
    opacity: 0.8,
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    flex: 1,
  },
  textContent: {
    flex: 1,
    gap: 2,
  },
  title: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
  },
  subtitle: {
    fontFamily: 'PlusJakartaSans_400Regular',
  },
  externalArrow: {
    color: colors.text.secondary,
    fontSize: 16,
    fontWeight: '600',
  },
});