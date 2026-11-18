export const colors = {
  brand: {
    dark: '#173D28',
    green: '#28633C',
    greenSoft: '#E8F4EC',
    emerald: '#29965B',
    gold: '#FFCC00',
    goldSoft: '#FFF1C8',
  },
  surface: {
    canvas: '#F4F7F4',
    white: '#FFFFFF',
    card: '#FFFFFF',
    overlay: 'rgba(23,61,40,0.08)',
  },
  text: {
    ink: '#17261D',
    muted: '#6D7B73',
    inverse: '#FFFFFF',
    onGold: '#173D28',
  },
  border: '#E2E9E3',
  status: {
    error: '#9A342D',
    errorBg: '#FFF0EE',
    success: '#29965B',
  },
};

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 28 };
export const radii = { sm: 8, md: 12, lg: 16, xl: 22, pill: 999, full: 9999 };
export const typography = {
  display: { fontSize: 32, lineHeight: 38, fontWeight: '900' as const, letterSpacing: -1 },
  title: { fontSize: 22, lineHeight: 28, fontWeight: '900' as const, letterSpacing: -0.5 },
  headline: { fontSize: 18, lineHeight: 24, fontWeight: '800' as const },
  body: { fontSize: 14, lineHeight: 20, fontWeight: '500' as const },
  caption: { fontSize: 11, lineHeight: 15, fontWeight: '600' as const, letterSpacing: 0.5 },
  overline: { fontSize: 9, lineHeight: 12, fontWeight: '900' as const, letterSpacing: 1.1 },
};
export const shadows = {
  card: { shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 8, elevation: 2 },
  cardPressed: { shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.04, shadowRadius: 4, elevation: 1 },
  hero: { shadowColor: '#173D28', shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.15, shadowRadius: 24, elevation: 6 },
};
