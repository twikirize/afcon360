import React from "react";
import { useRouter } from "expo-router";
import { AppScreen } from "@afcon360/mobile-ui";
import { PasswordResetFlow } from "@afcon360/mobile-ui/auth";
import { authClient } from "../src/services/api";

export default function ForgotPasswordScreen() {
  const router = useRouter();

  return (
    <AppScreen>
      <PasswordResetFlow
        appLabel="AFCON360 Driver"
        onRequestCode={identifier => authClient.requestPasswordReset(identifier)}
        onConfirmCode={input => authClient.confirmPasswordReset(input)}
        onBack={() => router.replace("/login")}
        onComplete={() => router.replace("/login")}
      />
    </AppScreen>
  );
}
