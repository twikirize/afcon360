import React from 'react';
import Svg, { Circle, Defs, LinearGradient, Path, Stop } from 'react-native-svg';

interface PamojaMarkProps {
  size?: number;
  showLeaf?: boolean;
}

export const PamojaMark = ({ size = 34, showLeaf = true }: PamojaMarkProps) => (
  <Svg width={size} height={size} viewBox="0 0 64 64" fill="none">
    <Defs>
      <LinearGradient id="pamojaMarkWhite" x1="14" y1="10" x2="50" y2="54" gradientUnits="userSpaceOnUse">
        <Stop offset="0" stopColor="#FFFFFF" />
        <Stop offset="1" stopColor="#EAF7DE" />
      </LinearGradient>
      <LinearGradient id="pamojaMarkGold" x1="30" y1="14" x2="54" y2="48" gradientUnits="userSpaceOnUse">
        <Stop offset="0" stopColor="#FFE785" />
        <Stop offset="1" stopColor="#E9A400" />
      </LinearGradient>
    </Defs>

    <Path d="M23 53V17" stroke="url(#pamojaMarkWhite)" strokeWidth="8" strokeLinecap="round" />
    <Path
      d="M23 21h12.5a12.5 12.5 0 0 1 0 25H23"
      stroke="url(#pamojaMarkWhite)"
      strokeWidth="8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <Path
      d="M28 25.5h7.5a8 8 0 0 1 0 16H28"
      stroke="url(#pamojaMarkGold)"
      strokeWidth="2"
      strokeLinecap="round"
      opacity="0.9"
    />
    {showLeaf ? (
      <Path d="M46.5 13.5c6.2-3.4 11.4.6 9.6 7.1-5.2 1.2-8.6-2.1-9.6-7.1Z" fill="url(#pamojaMarkGold)" />
    ) : null}
    <Circle cx="49.5" cy="51" r="2.2" fill="url(#pamojaMarkGold)" opacity="0.85" />
  </Svg>
);

export default PamojaMark;
