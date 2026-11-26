import React, { useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { homeDesign } from '../../theme/tokens';

const ACTIONS = [
  { label: 'Book a ride', icon: 'directions-car' as const, route: '/(service)/ride' },
  { label: 'Find a stay', icon: 'hotel' as const, route: '/(service)/stays' },
  { label: 'Get event tickets', icon: 'confirmation-number' as const, route: '/(service)/events' },
  { label: 'Explore adventures', icon: 'explore' as const, route: '/(service)/adventure' },
  { label: 'Open my wallet', icon: 'account-balance-wallet' as const, route: '/(tabs)/wallet' },
];

export const HomeQuickAction = () => {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const go = (route: string) => { setOpen(false); router.push(route as any); };
  return (
    <>
      <View style={styles.wrap}>
        <View style={styles.rule} />
        <Pressable accessibilityRole="button" accessibilityLabel="Open Pamoja quick actions" accessibilityHint="Shows shortcuts to rides, stays, events, adventures and your wallet" onPress={() => setOpen(true)} style={styles.button}>
          <Text style={styles.p}>P</Text>
          <View style={styles.spark}><MaterialIcons name="add" size={13} color="#173D28" /></View>
        </Pressable>
        <Text style={styles.caption}>QUICK ACCESS</Text>
      </View>
      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          <Pressable style={styles.sheet} onPress={() => undefined}>
            <View style={styles.sheetTop}>
              <View><Text style={styles.sheetTitle}>Pamoja, one tap away.</Text><Text style={styles.sheetSubtitle}>Where would you like to go?</Text></View>
              <Pressable accessibilityRole="button" accessibilityLabel="Close quick actions" onPress={() => setOpen(false)} style={styles.close}><MaterialIcons name="close" size={21} color={homeDesign.primaryGreen} /></Pressable>
            </View>
            {ACTIONS.map((action) => (
              <Pressable key={action.label} onPress={() => go(action.route)} style={styles.action}>
                <View style={styles.actionIcon}><MaterialIcons name={action.icon} size={22} color={homeDesign.primaryGreen} /></View>
                <Text style={styles.actionLabel}>{action.label}</Text>
                <MaterialIcons name="arrow-forward-ios" size={15} color="#9B9F96" />
              </Pressable>
            ))}
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
};

const styles = StyleSheet.create({
  wrap: { alignItems: 'center', justifyContent: 'center', marginTop: 3, marginBottom: 22, minHeight: 76 },
  rule: { position: 'absolute', left: 0, right: 0, height: 1, backgroundColor: homeDesign.borderColor },
  button: { width: 62, height: 62, borderRadius: 31, backgroundColor: homeDesign.primaryGreen, borderWidth: 3, borderColor: '#E8BD4F', alignItems: 'center', justifyContent: 'center', elevation: 7, shadowColor: '#173D28', shadowOpacity: 0.22, shadowRadius: 9, shadowOffset: { width: 0, height: 4 } },
  p: { color: '#FFFDF6', fontSize: 30, fontWeight: '900', fontFamily: 'serif', lineHeight: 36 },
  spark: { position: 'absolute', right: -2, top: -1, width: 21, height: 21, borderRadius: 11, backgroundColor: '#E8BD4F', alignItems: 'center', justifyContent: 'center' },
  caption: { color: homeDesign.textGray, fontSize: 8, fontWeight: '900', letterSpacing: 1.4, marginTop: 5 },
  backdrop: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(7,24,15,0.55)' },
  sheet: { backgroundColor: '#FFFDF6', borderTopLeftRadius: 28, borderTopRightRadius: 28, paddingHorizontal: 22, paddingTop: 25, paddingBottom: 35 },
  sheetTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 },
  sheetTitle: { color: homeDesign.textDark, fontSize: 22, fontWeight: '900', fontFamily: 'serif' },
  sheetSubtitle: { color: homeDesign.textGray, fontSize: 12, marginTop: 4 },
  close: { width: 38, height: 38, borderRadius: 19, backgroundColor: '#E8F0E8', alignItems: 'center', justifyContent: 'center' },
  action: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, borderTopWidth: 1, borderTopColor: homeDesign.borderColor },
  actionIcon: { width: 42, height: 42, borderRadius: 14, backgroundColor: '#E8F0E8', alignItems: 'center', justifyContent: 'center', marginRight: 13 },
  actionLabel: { flex: 1, color: homeDesign.textDark, fontSize: 14, fontWeight: '800' },
});
