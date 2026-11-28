import React, { useEffect } from "react";
import { StyleSheet, View } from "react-native";
import Svg, { Circle, Defs, LinearGradient, Stop } from "react-native-svg";
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
} from "react-native-reanimated";
import { palette } from "@afcon360/mobile-ui";
import { PamojaLogomark } from "./PamojaLogomark";

const SIZE = 264;
const RADIUS = 104;
const STROKE = 6;
const CENTRE = SIZE / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

// A quarter of the ring, not a fraction of a duration: a boot gate cannot know
// how long it will wait, so the arc reads as a moving highlight rather than a
// progress percentage it would be inventing.
const ARC = CIRCUMFERENCE * 0.26;
const GAP = CIRCUMFERENCE - ARC;

/**
 * What the app shows while it restores a session. It is the canonical brand
 * mark in a green disc with a gold arc orbiting it, so the first thing a reader
 * sees is Pamoja rather than a platform-coloured activity indicator.
 */
export function PamojaLoader() {
  const spin = useSharedValue(0);
  const breathe = useSharedValue(1);

  useEffect(() => {
    spin.value = withRepeat(withTiming(360, { duration: 1250, easing: Easing.linear }), -1, false);
    breathe.value = withRepeat(
      withSequence(
        withTiming(0.965, { duration: 950, easing: Easing.inOut(Easing.quad) }),
        withTiming(1, { duration: 950, easing: Easing.inOut(Easing.quad) })
      ),
      -1,
      false
    );
  }, [breathe, spin]);

  const arcStyle = useAnimatedStyle(() => ({ transform: [{ rotate: `${spin.value}deg` }] }));
  const discStyle = useAnimatedStyle(() => ({ transform: [{ scale: breathe.value }] }));

  return (
    <View accessibilityRole="progressbar" accessibilityLabel="Loading Pamoja" style={styles.root}>
      <View style={styles.stack}>
        <Svg width={SIZE} height={SIZE} style={StyleSheet.absoluteFill}>
          <Circle cx={CENTRE} cy={CENTRE} r={RADIUS} stroke={palette.greenSoft} strokeWidth={STROKE} fill="none" />
        </Svg>

        <Animated.View style={[StyleSheet.absoluteFill, arcStyle]}>
          <Svg width={SIZE} height={SIZE}>
            <Defs>
              <LinearGradient
                id="pamojaLoaderArc"
                x1="0"
                y1="0"
                x2={SIZE}
                y2={SIZE}
                gradientUnits="userSpaceOnUse"
              >
                <Stop offset="0" stopColor="#E9A400" />
                <Stop offset="1" stopColor="#FFE785" />
              </LinearGradient>
            </Defs>
            <Circle
              cx={CENTRE}
              cy={CENTRE}
              r={RADIUS}
              stroke="url(#pamojaLoaderArc)"
              strokeWidth={STROKE}
              strokeLinecap="round"
              strokeDasharray={`${ARC} ${GAP}`}
              fill="none"
              transform={`rotate(-90 ${CENTRE} ${CENTRE})`}
            />
          </Svg>
        </Animated.View>

        <Animated.View style={[styles.halo, discStyle]}>
          <View style={styles.disc}>
            <PamojaLogomark size={76} />
          </View>
        </Animated.View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: palette.canvas,
  },
  stack: {
    width: SIZE,
    height: SIZE,
    alignItems: "center",
    justifyContent: "center",
  },
  // The floating-icon lockup at twice its design size: a dark disc with a gold
  // rim inside a soft gold halo, with the mark at 76 inside 144. Every dimension
  // is doubled together so the proportions stay the design's own.
  halo: {
    padding: 6,
    borderRadius: 90,
    backgroundColor: "rgba(247,200,21,0.2)",
  },
  disc: {
    width: 144,
    height: 144,
    borderRadius: 72,
    backgroundColor: "#04210F",
    justifyContent: "center",
    alignItems: "center",
    borderWidth: 6,
    borderColor: "#F7C815",
    shadowColor: "#F7C815",
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.6,
    shadowRadius: 30,
    elevation: 10,
  },
});

export default PamojaLoader;