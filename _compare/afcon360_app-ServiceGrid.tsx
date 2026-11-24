import React from 'react';
import { View, StyleSheet } from 'react-native';
import { ServiceCard } from './ServiceCard';
import { spacing } from '../../theme';

interface ServiceItem {
  key: string;
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  onPress: () => void;
  external?: boolean;
}

type ServiceGridProps = {
  services: ServiceItem[];
  columns?: 2 | 1;
  style?: ViewStyle;
};

import { ViewStyle } from 'react-native';

export function ServiceGrid({
  services,
  columns = 2,
  style,
}: ServiceGridProps) {
  return (
    <View style={[styles.container, { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' }, style]}>
      {services.map((service, index) => (
        <View key={service.key} style={[styles.item, columns === 2 && styles.itemHalf]}>
          <ServiceCard
            icon={service.icon}
            title={service.title}
            subtitle={service.subtitle}
            onPress={service.onPress}
            external={service.external}
          />
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: spacing.cardGap,
  },
  item: {
    flex: 1,
  },
  itemHalf: {
    width: '48.5%',
  },
});