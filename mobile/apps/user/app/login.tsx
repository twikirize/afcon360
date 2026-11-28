import React, { useEffect } from "react";
import { useRouter } from "expo-router";
import { useAuth } from "../src/auth/AuthProvider";
import { SignInScreen } from "../src/auth/SignInScreen";

/**
 * The standalone sign-in route. It survives for deep links and for anything
 * that still points at /login, but the app no longer opens here: the Account
 * tab renders the same screen in place when nobody is signed in.
 */
export default function LoginScreen() {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (!loading && user) router.replace("/(tabs)");
  }, [loading, user, router]);

  return <SignInScreen />;
}
