import React from "react";
import { StyleSheet, Text, View } from "react-native";
import Svg, { Path } from "react-native-svg";

export function Afcon360Brand() {
  return (
    <View accessibilityRole="header" accessibilityLabel="AFCON360" style={styles.lockup}>
      <Svg width={43} height={48} viewBox="0 0 52 58" fill="none">
        <Path
          d="M26 3.5 46.5 9v17.2c0 12.2-7.8 21.8-20.5 28.2C13.3 48 5.5 38.4 5.5 26.2V9L26 3.5Z"
          fill="#F7FBF8"
          stroke="#219B64"
          strokeWidth={3.3}
          strokeLinejoin="round"
        />
        <Path
          d="m15.2 39.5 10.8-25 10.8 25M19.2 30.2h13.6"
          stroke="#219B64"
          strokeWidth={4.2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </Svg>
      <Text style={styles.wordmark}>AFCON360</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  lockup: {
    minHeight: 50,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 9,
    paddingTop: 2,
    paddingBottom: 3,
  },
  wordmark: {
    color: "#1E2D3A",
    fontSize: 24,
    lineHeight: 30,
    fontWeight: "900",
    letterSpacing: -0.65,
  },
});

export default Afcon360Brand;
