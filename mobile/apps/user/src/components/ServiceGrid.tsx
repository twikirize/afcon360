import React from "react";
import { View, StyleSheet } from "react-native";
import { ServiceEntry } from "./ServiceEntry";
import { spacing } from "../theme/tokens";

type ServiceKey = "rides" | "stays" | "events" | "adventure" | "wallet" | "tourism";

const EXPLORE_SERVICES: ServiceKey[] = ["rides", "stays", "events", "adventure"];

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    rowGap: spacing.md,
  },
  tileWrap: {
    width: "48.6%",
  },
});

export const ServiceGrid = ({ onServicePress }: { onServicePress: (key: string) => void }) => (
  <View style={styles.container}>
    {EXPLORE_SERVICES.map((key, index) => (
      <View key={key} style={styles.tileWrap}>
        <ServiceEntry key={key} onPress={() => onServicePress(key)} index={index} />
      </View>
    ))}
  </View>
);

export default ServiceGrid;