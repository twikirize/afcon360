import React, { useState } from 'react';
import { View, Text, Pressable, StyleSheet, FlatList } from 'react-native';
import { colors, radii, spacing, typography } from '../../theme';
import { RegCard } from './RegCard';
import { RegCardSkeleton } from './RegCardSkeleton';
import { EmptyState } from '../common';

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

interface ModuleFlags {
  transport: boolean;
  accommodation: boolean;
}

type TabType = 'upcoming' | 'past' | 'all';

interface EventTabsProps {
  upcomingRegistrations: EventRegistration[];
  pastRegistrations: EventRegistration[];
  allRegistrations: EventRegistration[];
  modules: ModuleFlags;
  loading?: boolean;
  onViewTicket: (reg: EventRegistration) => void;
  onAddTravel: (reg: EventRegistration) => void;
  onFindStay: (reg: EventRegistration) => void;
  onInviteFriends: (reg: EventRegistration) => void;
  onCancel: (reg: EventRegistration) => void;
  style?: ViewStyle;
}

import { ViewStyle } from 'react-native';

const tabs: { key: TabType; label: string }[] = [
  { key: 'upcoming', label: 'Upcoming' },
  { key: 'past', label: 'Past' },
  { key: 'all', label: 'All' },
];

export function EventTabs({
  upcomingRegistrations,
  pastRegistrations,
  allRegistrations,
  modules,
  loading = false,
  onViewTicket,
  onAddTravel,
  onFindStay,
  onInviteFriends,
  onCancel,
  style,
}: EventTabsProps) {
  const [activeTab, setActiveTab] = useState<TabType>('upcoming');

  const getRegistrationsForTab = (tab: TabType) => {
    switch (tab) {
      case 'upcoming':
        return upcomingRegistrations;
      case 'past':
        return pastRegistrations;
      case 'all':
        return allRegistrations;
    }
  };

  const getEmptyStateConfig = (tab: TabType) => {
    switch (tab) {
      case 'upcoming':
        return {
          icon: '📅',
          title: 'No Upcoming Events',
          description: 'You haven&apos;t registered for any upcoming events yet.',
          actionLabel: 'Browse Events',
        };
      case 'past':
        return {
          icon: '📜',
          title: 'No Past Events',
          description: 'Your attended events will appear here.',
        };
      case 'all':
        return {
          icon: '🎫',
          title: 'No Registrations Yet',
          description: 'Register for an event to get started.',
          actionLabel: 'Browse Events',
        };
    }
  };

  const registrations = getRegistrationsForTab(activeTab);
  const emptyConfig = getEmptyStateConfig(activeTab);

  if (loading) {
    return (
      <View style={[styles.container, style]}>
        <View style={styles.tabBar}>
          {tabs.map((tab) => (
            <Pressable
              key={tab.key}
              onPress={() => setActiveTab(tab.key)}
              style={[
                styles.tab,
                activeTab === tab.key && styles.tabActive,
              ]}
            >
              <Text
                style={[
                  typography.label,
                  styles.tabLabel,
                  {
                    color: activeTab === tab.key ? colors.brand.primary : colors.text.secondary,
                    fontFamily: activeTab === tab.key ? 'PlusJakartaSans_700Bold' : 'PlusJakartaSans_400Regular',
                  },
                ]}
              >
                {tab.label}
                <Text style={[
                  styles.tabCount,
                  { backgroundColor: activeTab === tab.key ? colors.brand.primary : colors.border }
                ]}>
                  {registrations.length}
                </Text>
              </Text>
            </Pressable>
          ))}
        </View>
        <View style={styles.listContainer}>
          {Array.from({ length: 3 }).map((_, i) => (
            <RegCardSkeleton key={i} />
          ))}
        </View>
      </View>
    );
  }

  return (
    <View style={[styles.container, style]}>
      <View style={styles.tabBar}>
        {tabs.map((tab) => (
          <Pressable
            key={tab.key}
            onPress={() => setActiveTab(tab.key)}
            style={[
              styles.tab,
              activeTab === tab.key && styles.tabActive,
            ]}
          >
            <Text
              style={[
                typography.label,
                styles.tabLabel,
                {
                  color: activeTab === tab.key ? colors.brand.primary : colors.text.secondary,
                  fontFamily: activeTab === tab.key ? 'PlusJakartaSans_700Bold' : 'PlusJakartaSans_400Regular',
                },
              ]}
            >
              {tab.label}
              <Text style={[
                styles.tabCount,
                { backgroundColor: activeTab === tab.key ? colors.brand.primary : colors.border }
              ]}>
                {getRegistrationsForTab(tab.key).length}
              </Text>
            </Text>
          </Pressable>
        ))}
      </View>

      {registrations.length > 0 ? (
        <FlatList
          data={registrations}
          keyExtractor={(item) => item.registration_ref}
          renderItem={({ item }) => (
            <RegCard
              registration={item}
              modules={modules}
              onViewTicket={onViewTicket}
              onAddTravel={onAddTravel}
              onFindStay={onFindStay}
              onInviteFriends={onInviteFriends}
              onCancel={onCancel}
            />
          )}
          ItemSeparatorComponent={() => <View style={styles.separator} />}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
        />
      ) : (
        <EmptyState
          icon={<Text style={{ fontSize: 32 }}>{emptyConfig.icon}</Text>}
          title={emptyConfig.title}
          description={emptyConfig.description}
          actionLabel={emptyConfig.actionLabel}
          onActionPress={emptyConfig.actionLabel ? () => {} : undefined}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: spacing.md,
  },
  tabBar: {
    flexDirection: 'row',
    gap: spacing.sm,
    borderBottomWidth: 2,
    borderBottomColor: colors.border,
    paddingBottom: spacing.xs,
  },
  tab: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderBottomWidth: 3,
    borderBottomColor: 'transparent',
    marginBottom: -2,
  },
  tabActive: {
    borderBottomColor: colors.brand.primary,
  },
  tabLabel: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
  },
  tabCount: {
    marginLeft: spacing.xs,
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: radii.pill,
    fontSize: 10,
    fontWeight: '700',
    color: colors.surface,
  },
  listContainer: {
    paddingTop: spacing.md,
  },
  listContent: {
    paddingBottom: spacing.xxxl,
    gap: spacing.md,
  },
  separator: {
    height: spacing.md,
  },
});