import React from "react";
import { Text, View } from "react-native";
import * as WebBrowser from "expo-web-browser";
import { useRouter } from "expo-router";
import { AppScreen, PageHeader, Panel, StatusPill, palette } from "@afcon360/mobile-ui";
import { AuthLink, AuthNotice, AuthShell } from "@afcon360/mobile-ui/auth";
import { useAuth } from "./AuthProvider";
import { SignInForm } from "./SignInForm";
import { SERVER_SELECTION_ENABLED } from "../services/api";

const SITE = "https://www.pamoja.space";

/**
 * The complete sign-in surface: the one the app used to open on, now shared by
 * the /login route and the signed-out Account tab. It mounts its own screen and
 * scroll view, so a tab that was scrolled deep into a signed-in account starts
 * this one at the top instead of inheriting that offset.
 *
 * Signing in is not navigation. Auth state changes, and whatever the caller
 * shows when `useAuth().user` is set appears in place.
 */
export function SignInScreen() {
  const router = useRouter();
  const { restoreError, retryRestoreSession, mfaChallenge, mfaType, mfaDestinationHint } = useAuth();

  return (
    <AppScreen>
      <AuthShell>
        <View style={{ gap: 9 }}>
          <StatusPill>AFCON360 User</StatusPill>
          <PageHeader
            eyebrow="Welcome back"
            title={mfaChallenge ? "Verify it’s you." : "Your journey starts here."}
            description={
              mfaChallenge
                ? mfaType === "sms"
                  ? `We sent a sign-in code to ${mfaDestinationHint ?? "your verified phone"}. It expires in five minutes.`
                  : "Enter the current code from your authenticator app to finish signing in."
                : "Sign in with your existing AFCON360 account. Your website account works here too."
            }
          />
        </View>
        <Panel>
          {restoreError ? (
            <>
              <AuthNotice>
                {restoreError} Your saved credentials have not been deleted. Check your connection and retry the session check.
              </AuthNotice>
              <AuthLink label="Retry saved session" onPress={() => { void retryRestoreSession(); }} />
            </>
          ) : null}
          <SignInForm />
          {SERVER_SELECTION_ENABLED && !mfaChallenge ? <AuthLink label="Connection settings (preview)" onPress={() => router.push("/server-settings" as never)} /> : null}
          <AuthLink label="Back to AFCON360 website home" onPress={() => WebBrowser.openBrowserAsync(SITE)} />
        </Panel>
        <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18, textAlign: "center" }}>
          Protected by AFCON360 Identity. Your password and authenticator codes are sent only over HTTPS and are never stored on this device.
        </Text>
      </AuthShell>
    </AppScreen>
  );
}

export default SignInScreen;
