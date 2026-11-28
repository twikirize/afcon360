import React from "react";
import { useAuth } from "../../src/auth/AuthProvider";
import { WalletScreen } from "../../src/components/wallet/WalletScreen";
import { WalletGuestView } from "../../src/components/wallet/WalletGuestView";

export default function WalletRoute() {
  const { user } = useAuth();
  // Signed out, the tab shows the public wallet page the website serves at
  // /wallet/home; signed in, it shows the live wallet.
  return user ? <WalletScreen /> : <WalletGuestView />;
}
