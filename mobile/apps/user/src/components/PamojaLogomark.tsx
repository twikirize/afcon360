import React from "react";
import Svg, { Path } from "react-native-svg";

interface PamojaLogomarkProps {
  size?: number;
  color?: string;
  strokeWidth?: number;
}

/**
 * The Pamoja logomark: one P whose stem splits in two, a leaf inside the open
 * bowl, and a second leaf on the left of the stem.
 *
 * These are the exact paths the tab bar disc has always drawn. They live here
 * so no second surface can quietly render a different P — the previous
 * duplicate, `PamojaMark`, was a heavier 64-unit drawing that no screen used.
 */
export const PamojaLogomark = ({ size = 26, color = "#FFFFFF", strokeWidth = 5.5 }: PamojaLogomarkProps) => (
  <Svg
    width={size}
    height={size}
    viewBox="0 0 100 100"
    fill="none"
    stroke={color}
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <Path d="M 35 85 L 35 45 C 35 20, 50 15, 65 15 C 85 15, 85 45, 65 55 C 55 60, 45 60, 45 60 L 45 85" />
    <Path d="M 45 60 C 45 40, 60 30, 68 30 C 68 45, 55 60, 45 60" />
    <Path d="M 35 50 C 20 50, 20 40, 30 40 C 33 40, 35 45, 35 50" />
  </Svg>
);

export default PamojaLogomark;