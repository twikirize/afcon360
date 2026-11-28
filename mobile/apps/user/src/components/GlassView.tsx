import React from "react";
import type { ReactNode, RefObject } from "react";
import { StyleSheet, View } from "react-native";
import type { StyleProp, View as NativeView, ViewStyle } from "react-native";
import { BlurView } from "expo-blur";
import { LinearGradient } from "expo-linear-gradient";

type GlassViewProps = {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  contentStyle?: StyleProp<ViewStyle>;
  radius?: number;
  dark?: boolean;
  blurAmount?: number;
  blurTarget?: RefObject<NativeView | null>;
};

/**
 * Reusable frosted surface. The tint and sheen remain visible as a fallback
 * on platforms where native backdrop blur is unavailable.
 */
export function GlassView({
  children,
  style,
  contentStyle,
  radius = 24,
  dark = false,
  blurAmount = 22,
  blurTarget,
}: GlassViewProps) {
  const tint = dark ? "rgba(10,16,26,0.48)" : "rgba(255,255,255,0.76)";
  const sheen: [string, string] = dark
    ? ["rgba(255,255,255,0.18)", "rgba(255,255,255,0.02)"]
    : ["rgba(255,255,255,0.70)", "rgba(255,255,255,0.08)"];
  const edge = dark ? "rgba(255,255,255,0.18)" : "rgba(255,255,255,0.86)";

  return (
    <View style={[styles.shadow, { borderRadius: radius }, style]}>
      <View style={[styles.clip, { borderRadius: radius }]}>
        <View pointerEvents="none" style={[StyleSheet.absoluteFillObject, { backgroundColor: tint }]} />
        <BlurView
          pointerEvents="none"
          style={StyleSheet.absoluteFillObject}
          tint={dark ? "dark" : "light"}
          intensity={blurAmount}
          blurTarget={blurTarget}
          blurMethod="dimezisBlurViewSdk31Plus"
          blurReductionFactor={2}
        />
        <LinearGradient
          pointerEvents="none"
          colors={sheen}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={StyleSheet.absoluteFillObject}
        />
        <View pointerEvents="none" style={styles.topHighlight} />
        <View
          pointerEvents="none"
          style={[
            StyleSheet.absoluteFillObject,
            { borderRadius: radius, borderWidth: 1, borderColor: edge },
          ]}
        />
        <View style={[styles.content, contentStyle]}>{children}</View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  shadow: {
    shadowColor: "#10291C",
    shadowOpacity: 0.14,
    shadowRadius: 22,
    shadowOffset: { width: 0, height: 9 },
    elevation: 7,
  },
  clip: { flex: 1, overflow: "hidden" },
  content: { flex: 1 },
  topHighlight: {
    position: "absolute",
    top: 0,
    left: 1,
    right: 1,
    height: 1.5,
    backgroundColor: "rgba(255,255,255,0.94)",
  },
});

export default GlassView;
