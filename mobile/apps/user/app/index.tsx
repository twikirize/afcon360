import React from "react";
import { Redirect } from "expo-router";

/**
 * The app always opens on the tabs, and the tabs open on Home.
 *
 * Opening the app never asks for a session: Home and Explore are public, the
 * Wallet tab renders its guest view, and the Account tab renders the sign-in
 * screen in place when nobody is signed in. The /login route still exists for
 * deep links and for "Continue to sign in" from registration, but nothing on
 * the startup path depends on it.
 *
 * Loading and restore failures are handled by the tabs layout, which owns the
 * spinner and the retry surface, so this route only has to choose the group.
 */
export default function Index() {
  return <Redirect href="/(tabs)" />;
}
