import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { colors, radii, spacing, typography, shadows } from '../../theme';
import { SectionHeader } from '../common';

interface EventRegistration {
  event: {
    id: string;
    name: string;
    slug: string;
    category: string;
    start_date: string;
    end_date?: string;
    city?: string;
    venue?: string;
    description?: string;
    flyer_url?: string;
    event_metadata?: Record<string, any>;
  };
  status: 'confirmed' | 'checked_in' | 'pending' | 'cancelled' | 'refunded' | 'rejected';
  ticket_type: string;
  registration_ref: string;
  registration_fee?: number;
  created_at: string;
}

interface UpcomingEventsPreviewProps {
  registrations: EventRegistration[];
  onViewAll: () => void;
  style?: ViewStyle;
}

import { ViewStyle } from 'react-native';

const statusConfig = {
  confirmed: { color: colors.brand.primary, label: 'Confirmed', icon: '✓' },
  checked_in: { color: colors.semantic.info, label: 'Checked In', icon: '✓' },
  pending: { color: colors.accent.terracotta, label: 'Pending', icon: '⏳' },
  cancelled: { color: colors.semantic.danger, label: 'Cancelled', icon: '✕' },
  refunded: { color: colors.semantic.danger, label: 'Refunded', icon: '↩' },
  rejected: { color: colors.semantic.danger, label: 'Rejected', icon: '✕' },
};

export function UpcomingEventsPreview({
  registrations,
  onViewAll,
  style,
}: UpcomingEventsPreviewProps) {
  if (registrations.length === 0) {
    return (
      <View style={[styles.emptyContainer, style]}>
        <View style={styles.emptyIcon}>
          <Text style={styles.emptyIconText}>📅</Text>
        </View>
        <Text style={[typography.cardTitle, styles.emptyTitle, { color: colors.text.primary }]}>
          No Upcoming Events
        </Text>
        <Text style={[typography.cardSubtitle, styles.emptyDescription, { color: colors.text.secondary }]}>
          You haven&apos;t registered for any upcoming events yet.
        </Text>
        <Pressable onPress={onViewAll} accessibilityRole="button" style={styles.emptyAction}>
          <Text style={[typography.label, styles.emptyActionText, { color: colors.brand.primary }]}>Browse Events →</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={[styles.container, style]}>
      <SectionHeader title="Upcoming Events" actionLabel="View all" onActionPress={onViewAll} />
      {registrations.slice(0, 3).map((reg) => {
        const { event, status, ticket_type, registration_ref } = reg;
        const { name, start_date, city } = event;
        const config = statusConfig[status];
        return (
          <View key={registration_ref} style={styles.eventItem}>
            <View style={styles.eventIcon}>
              <Text style={{ fontSize: 20 }}>🎫</Text>
            </View>
            <View style={styles.eventContent}>
              <Text style={[typography.cardTitle, styles.eventTitle, { color: colors.text.primary }]}>{name}</Text>
              <Text style={[typography.cardSubtitle, styles.eventMeta, { color: colors.text.secondary }]}>
                {start_date.slice(0, 10)}{city ? ` · ${city}` : ''}
              </Text>
              <Text style={[typography.caption, styles.eventDetail, { color: colors.text.secondary }]}>
                {ticket_type} · {registration_ref}
              </Text>
            </View>
            <View style={[styles.statusBadge, { backgroundColor: `${config.color}15`, borderColor: config.color }]}>
              <Text style={[typography.label, { color: config.color }]}>{config.icon} {config.label}</Text>
            </View>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: 'hidden',
    ...shadows.card,
  },
  emptyContainer: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.xxxl,
    alignItems: 'center',
    gap: spacing.md,
    ...shadows.card,
  },
  emptyIcon: {
    width: 70,
    height: 70,
    borderRadius: 35,
    backgroundColor: colors.brand.primaryLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyIconText: {
    fontSize: 28,
  },
  emptyTitle: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
  },
  emptyDescription: {
    fontFamily: 'PlusJakartaSans_400Regular',
    textAlign: 'center',
  },
  emptyAction: {
    marginTop: spacing.sm,
  },
  emptyActionText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
  },
  eventItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  eventIcon: {
    width: 44,
    height: 44,
    borderRadius: radii.md,
    backgroundColor: colors.brand.primaryLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  eventContent: {
    flex: 1,
    minWidth: 0,
    gap: spacing.xs,
  },
  eventTitle: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
  },
  eventMeta: {
    fontFamily: 'PlusJakartaSans_400Regular',
  },
  eventDetail: {
    fontFamily: 'PlusJakartaSans_500Medium',
  },
  statusBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radii.pill,
    borderWidth: 1,
    flexShrink: 0,
  },
});