import React, { useState } from "react";
import { Alert, Text } from "react-native";
import { useRouter } from "expo-router";
import { AppScreen, PageHeader, Panel, palette } from "@afcon360/mobile-ui";
import { AuthField, AuthNotice, AuthSubmit } from "@afcon360/mobile-ui/auth";
import { MobileAuthError } from "@afcon360/mobile-core";
import { useAuth } from "../src/auth/AuthProvider";

export default function DeleteAccountScreen() {
  const router = useRouter();
  const { deleteAccount, signingIn } = useAuth();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  return <AppScreen>
    <PageHeader eyebrow="Account control" title="Delete your account." description="Account deletion is permanent to your sign-in. Verified records may be anonymized and retained where required for financial, safety or legal duties." />
    <Panel>
      <AuthNotice>Read the account deletion information on AFCON360 first. Platform owner accounts cannot self-delete. You must confirm your password and any enrolled authenticator factor.</AuthNotice>
      <AuthField label="Current password" value={password} onChangeText={setPassword} secureTextEntry placeholder="Confirm your password" />
      <AuthField label='Type "DELETE MY ACCOUNT"' value={confirmation} onChangeText={setConfirmation} autoCapitalize="characters" placeholder="DELETE MY ACCOUNT" />
      <AuthField label="Authenticator code (when enabled)" value={mfaCode} onChangeText={setMfaCode} keyboardType="number-pad" maxLength={8} placeholder="Authenticator or backup code" />
      <AuthSubmit label="Request account deletion" loading={signingIn} disabled={!password || confirmation !== "DELETE MY ACCOUNT"} onPress={() => Alert.alert("Confirm account deletion", "Your AFCON360 account will be deleted or anonymized according to platform retention requirements. Continue?", [{text:"Keep account",style:"cancel"},{text:"Delete account",style:"destructive",onPress:() => deleteAccount(password,confirmation,mfaCode || undefined).then(() => { Alert.alert("Account request received","Your account deletion has been processed."); router.replace("/login"); }).catch(e => Alert.alert("Deletion unsuccessful",e instanceof MobileAuthError ? e.message : "AFCON360 could not process this request."))}])} />
    </Panel>
    <Text style={{ color: palette.muted, fontSize: 12 }}>You will be signed out on this device after the deletion request is accepted.</Text>
  </AppScreen>;
}
