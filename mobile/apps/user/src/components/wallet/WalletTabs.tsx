import React from "react";
import { View } from "react-native";
import { WalletTabButton } from "./WalletUI";
import type { WalletTab } from "./types";

type WalletTabsProps = {
  activeTab: WalletTab;
  onTabChange: (tab: WalletTab) => void;
  onTabPress?: () => void;
};

const TABS: WalletTab[] = ["balance", "deposit", "send", "history", "pin"];

export function WalletTabs({ activeTab, onTabChange, onTabPress }: WalletTabsProps) {
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
      {TABS.map((tab) => (
        <WalletTabButton
          key={tab}
          label={tab.charAt(0).toUpperCase() + tab.slice(1)}
          active={activeTab === tab}
          onPress={() => { onTabChange(tab); onTabPress?.(); }}
        />
      ))}
    </View>
  );
}

export default WalletTabs;