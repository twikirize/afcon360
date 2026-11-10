import React, { useCallback, useState } from "react";
import { ActivityIndicator, AppState, Pressable, Text, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import {
  ActionButton,
  AppScreen,
  EmptyState,
  PageHeader,
  Panel,
  SectionTitle,
  StatusPill,
  palette
} from "@afcon360/mobile-ui";
import { authClient } from "../src/services/api";

type DriverNotification = {
  public_id: string;
  type: string;
  module: "transport";
  subject?: string | null;
  body: string;
  priority?: string;
  status?: string;
  is_read: boolean;
  is_important: boolean;
  created_at?: string | null;
  read_at?: string | null;
};

type InboxResponse = {
  data: {
    items: DriverNotification[];
    total: number;
    unread_count: number;
    limit: number;
    offset: number;
  };
};

export default function DriverNotifications() {
  const router = useRouter();
  const [items, setItems] = useState<DriverNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await authClient.request<InboxResponse>(
        "/api/mobile/v1/driver/notifications?limit=50&offset=0"
      );
      setItems(response.data.items ?? []);
      setUnread(response.data.unread_count ?? 0);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Driver notifications could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
      const subscription = AppState.addEventListener("change", state => {
        if (state === "active") void load();
      });
      const timer = setInterval(() => {
        if (AppState.currentState === "active") void load();
      }, 30_000);
      return () => {
        subscription.remove();
        clearInterval(timer);
      };
    }, [load])
  );

  const markRead = async (item: DriverNotification) => {
    if (item.is_read) return;
    setBusy(item.public_id);
    try {
      await authClient.request(
        "/api/mobile/v1/driver/notifications/" +
          encodeURIComponent(item.public_id) +
          "/read",
        { method: "POST", body: {} }
      );
      setItems(current => current.map(row =>
        row.public_id === item.public_id ? { ...row, is_read: true } : row
      ));
      setUnread(current => Math.max(0, current - 1));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "This notification could not be marked as read.");
    } finally {
      setBusy(null);
    }
  };

  const markAllRead = async () => {
    setBusy("all");
    try {
      await authClient.request(
        "/api/mobile/v1/driver/notifications/read-all",
        { method: "POST", body: {} }
      );
      setItems(current => current.map(item => ({ ...item, is_read: true })));
      setUnread(0);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Notifications could not be marked as read.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <AppScreen>
      <PageHeader
        eyebrow="Transport notifications"
        title="Your Driver inbox."
        description="Updates for your AFCON360 Driver activity, offers and Transport account."
      />
      <Panel>
        <View style={{ flexDirection:"row", alignItems:"center", justifyContent:"space-between", gap:8 }}>
          <SectionTitle>Inbox</SectionTitle>
          <StatusPill tone={unread ? "gold" : "green"}>{unread} unread</StatusPill>
        </View>
        <View style={{ flexDirection:"row", gap:8 }}>
          <ActionButton label="Refresh" disabled={loading || busy !== null} onPress={() => { setLoading(true); void load(); }} />
          <ActionButton label={busy === "all" ? "Updating…" : "Mark all read"} disabled={unread === 0 || busy !== null} onPress={() => { void markAllRead(); }} />
        </View>
        {loading && !items.length ? <ActivityIndicator color={palette.green} /> : null}
        {error ? (
          <Text accessibilityRole="alert" style={{ color:"#9A3A2F", fontSize:12 }}>{error}</Text>
        ) : null}
        {!loading && !error && !items.length ? (
          <EmptyState title="No Transport notifications" description="New Driver activity and Transport updates will appear here." />
        ) : null}
        {items.map(item => (
          <Pressable
            key={item.public_id}
            onPress={() => { void markRead(item); }}
            disabled={busy !== null}
            style={{
              gap:7,
              padding:12,
              borderWidth:1,
              borderColor:palette.border,
              borderRadius:13,
              backgroundColor:item.is_read ? "#FFFFFF" : "#F2F8F4"
            }}
          >
            <View style={{ flexDirection:"row", justifyContent:"space-between", alignItems:"center", gap:8 }}>
              <Text style={{ color:palette.ink, flex:1, fontSize:13, fontWeight:"900" }}>
                {item.subject || item.type.replace(/_/g," ")}
              </Text>
              <StatusPill tone={item.is_read ? "neutral" : "gold"}>{item.is_read ? "Read" : "New"}</StatusPill>
            </View>
            <Text style={{ color:palette.ink, fontSize:12, lineHeight:18 }}>{item.body}</Text>
            <Text style={{ color:palette.muted, fontSize:10 }}>
              {(item.created_at ? new Date(item.created_at).toLocaleString() : "Time unavailable") +
                (item.priority ? " · " + item.priority + " priority" : "")}
            </Text>
            {busy === item.public_id ? <ActivityIndicator color={palette.green} /> : null}
          </Pressable>
        ))}
      </Panel>
      <ActionButton label="Back to Driver account" onPress={() => router.back()} />
    </AppScreen>
  );
}
