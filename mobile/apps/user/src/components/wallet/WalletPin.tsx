import React from "react";
import { Text, View, Alert } from "react-native";
import { colors, spacing } from "../../theme/tokens";
import {
  PamojaPanel as Panel,
  PamojaSectionTitle as SectionTitle,
  PamojaStatusPill as StatusPill,
} from "../PamojaScreen";
import {
  WalletField,
  WalletButton,
} from "./WalletUI";

type WalletPinProps = {
  pinStatus: { locked: boolean; pin_set: boolean } | null;
  newPin: string;
  confirmPin: string;
  currentPin: string;
  accountPassword: string;
  busy: boolean;
  error: string | null;
  notice: string | null;
  onNewPinChange: (value: string) => void;
  onConfirmPinChange: (value: string) => void;
  onCurrentPinChange: (value: string) => void;
  onAccountPasswordChange: (value: string) => void;
  onUpdatePin: () => void;
};

export function WalletPin({
  pinStatus,
  newPin,
  confirmPin,
  currentPin,
  accountPassword,
  busy,
  error,
  notice,
  onNewPinChange,
  onConfirmPinChange,
  onCurrentPinChange,
  onAccountPasswordChange,
  onUpdatePin,
}: WalletPinProps) {
  return (
    <Panel>
      <SectionTitle>Transaction PIN</SectionTitle>
      <StatusPill tone={pinStatus?.locked ? "gold" : pinStatus?.pin_set ? "green" : "gold"}>
        {pinStatus?.locked ? "PIN locked" : pinStatus?.pin_set ? "PIN set" : "PIN not set"}
      </StatusPill>
      <Text style={{ color: colors.text.muted, lineHeight: 19 }}>
        {pinStatus?.pin_set
          ? "To change your PIN, enter your current PIN and choose a new one."
          : "To set your first PIN, re-enter your AFCON360 account password and choose a new PIN."}
      </Text>
      {pinStatus?.pin_set ? (
        <WalletField
          label="Current PIN"
          value={currentPin}
          onChangeText={onCurrentPinChange}
          placeholder="Current 4–6 digit PIN"
          secureTextEntry
          keyboardType="numeric"
        />
      ) : (
        <WalletField
          label="AFCON360 account password"
          value={accountPassword}
          onChangeText={onAccountPasswordChange}
          placeholder="Current account password"
          secureTextEntry
        />
      )}
      <WalletField
        label="New PIN"
        value={newPin}
        onChangeText={onNewPinChange}
        placeholder="Choose 4–6 digits"
        secureTextEntry
        keyboardType="numeric"
      />
      <WalletField
        label="Confirm new PIN"
        value={confirmPin}
        onChangeText={onConfirmPinChange}
        placeholder="Enter the new PIN again"
        secureTextEntry
        keyboardType="numeric"
      />
      <WalletButton
        label={busy ? "Updating PIN…" : pinStatus?.pin_set ? "Change transaction PIN" : "Set transaction PIN"}
        onPress={onUpdatePin}
        disabled={busy || !newPin.trim() || !confirmPin.trim() || (pinStatus?.pin_set ? !currentPin.trim() : !accountPassword.trim())}
      />
    </Panel>
  );
}

export default WalletPin;