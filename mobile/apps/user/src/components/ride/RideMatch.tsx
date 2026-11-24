import React from "react";
import { ActivityIndicator, Text, View, StyleSheet } from "react-native";
import { colors, spacing, radii, typography } from "../../theme/tokens";
import {
  PamojaPanel as Panel,
  PamojaSectionTitle as SectionTitle,
} from "../PamojaScreen";

type RideMatchProps = {
  requestError: string | null;
};

export function RideMatch({ requestError }: RideMatchProps) {
  return (
    <Panel>
      <View style={styles.matchingPanel}>
        <ActivityIndicator color={colors.brand.green} size="large" />
        <SectionTitle>{requestError ? "Ride request not completed" : "Sending your ride request…"}</SectionTitle>
        {requestError && <Text style={styles.errorText}>{requestError}</Text>}
      </View>
    </Panel>
  );
}

const styles = StyleSheet.create({
  matchingPanel: { alignItems: "center", paddingVertical: spacing.xxl, gap: spacing.md },
  errorText: { color: colors.status.error, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight, textAlign: "center", marginTop: spacing.sm },
});

export default RideMatch;