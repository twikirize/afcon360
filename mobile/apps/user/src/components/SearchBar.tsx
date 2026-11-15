import React, { useState, useRef, useEffect } from 'react';
import { View, Text, TextInput, Pressable, StyleSheet, Animated } from 'react-native';
import { colors, typography, spacing, radii, shadows } from '../theme/tokens';

type SearchBarProps = {
  value: string;
  onChangeText: (text: string) => void;
  onSubmit?: (text: string) => void;
  placeholder?: string;
  recentSearches?: string[];
  onRecentPress?: (text: string) => void;
  onClearRecent?: () => void;
};

const styles = StyleSheet.create({
  container: {
    position: 'relative',
    zIndex: 20,
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    minHeight: 48,
    paddingHorizontal: spacing.md,
    borderRadius: radii.lg,
    backgroundColor: colors.surface.white,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadows.card,
  },
  inputWrapperFocused: {
    borderColor: colors.brand.emerald,
  },
  icon: {
    color: colors.brand.emerald,
    fontSize: 24,
    lineHeight: 28,
    fontWeight: '700',
  },
  input: {
    flex: 1,
    minHeight: 44,
    color: colors.text.ink,
    fontSize: typography.body.fontSize,
    paddingVertical: 0,
  },
  clearButton: {
    padding: spacing.xs,
  },
  clearText: {
    color: colors.text.muted,
    fontSize: 22,
    lineHeight: 26,
  },
  recentContainer: {
    position: 'absolute',
    top: '100%',
    left: 0,
    right: 0,
    marginTop: spacing.xs,
    borderRadius: radii.lg,
    backgroundColor: colors.surface.white,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadows.hero,
    overflow: 'hidden',
    zIndex: 30,
  },
  recentHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  recentTitle: {
    color: colors.text.ink,
    fontSize: typography.caption.fontSize,
    fontWeight: '900',
    letterSpacing: 0.5,
  },
  clearRecentText: {
    color: colors.brand.emerald,
    fontSize: typography.caption.fontSize,
    fontWeight: '700',
  },
  recentItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
    minHeight: 44,
  },
  recentIcon: {
    color: colors.brand.emerald,
    fontSize: 16,
  },
  recentText: {
    flex: 1,
    color: colors.text.ink,
    fontSize: typography.body.fontSize,
  },
});

export const SearchBar = ({
  value,
  onChangeText,
  onSubmit,
  placeholder = 'Search highlights',
  recentSearches = [],
  onRecentPress,
  onClearRecent,
}: SearchBarProps) => {
  const [focused, setFocused] = useState(false);
  const [showRecent, setShowRecent] = useState(false);
  const [recentOpacity] = useState(new Animated.Value(0));
  const inputRef = useRef<React.ComponentRef<typeof TextInput>>(null);

  useEffect(() => {
    if (focused && recentSearches.length > 0) {
      setShowRecent(true);
      Animated.timing(recentOpacity, {
        toValue: 1,
        duration: 150,
        useNativeDriver: true,
      }).start();
    } else {
      Animated.timing(recentOpacity, {
        toValue: 0,
        duration: 150,
        useNativeDriver: true,
      }).start(() => {
        setShowRecent(false);
      });
    }
  }, [focused, recentSearches.length, recentOpacity]);

  const handleClear = () => {
    onChangeText('');
    inputRef.current?.focus();
  };

  const handleRecentPress = (text: string) => {
    onChangeText(text);
    onRecentPress?.(text);
    onSubmit?.(text);
    setShowRecent(false);
    inputRef.current?.blur();
  };

  return (
    <View style={styles.container}>
      <View style={[styles.inputWrapper, focused && styles.inputWrapperFocused]}>
        <Text style={styles.icon}>{'\u2315'}</Text>
        <TextInput
          ref={inputRef}
          value={value}
          onChangeText={onChangeText}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onSubmitEditing={onSubmit ? () => onSubmit(value) : undefined}
          placeholder={placeholder}
          placeholderTextColor='#87938C'
          returnKeyType='search'
          autoCorrect={false}
          style={styles.input}
          accessibilityLabel='Search Pamoja highlights'
          accessibilityHint='Filters the currently loaded trending highlights'
        />
        {value.length > 0 && (
          <Pressable
            accessibilityRole='button'
            accessibilityLabel='Clear search'
            onPress={handleClear}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            style={styles.clearButton}
          >
            <Text style={styles.clearText}>{'\u00D7'}</Text>
          </Pressable>
        )}
      </View>

      {showRecent && recentSearches.length > 0 && (
        <Animated.View style={[styles.recentContainer, { opacity: recentOpacity }]}>
          <View style={styles.recentHeader}>
            <Text style={styles.recentTitle}>RECENT SEARCHES</Text>
            <Pressable
              accessibilityRole='button'
              accessibilityLabel='Clear recent searches'
              onPress={onClearRecent}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            >
              <Text style={styles.clearRecentText}>Clear all</Text>
            </Pressable>
          </View>
          {recentSearches.map((term) => (
            <Pressable
              key={term}
              accessibilityRole='button'
              accessibilityLabel={term}
              onPress={() => handleRecentPress(term)}
              style={styles.recentItem}
            >
              <Text style={styles.recentIcon}>{'\u{1F551}'}</Text>
              <Text style={styles.recentText}>{term}</Text>
            </Pressable>
          ))}
        </Animated.View>
      )}
    </View>
  );
};

export default SearchBar;
