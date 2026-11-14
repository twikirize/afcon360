import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { eventClient } from "../services/api";
import type { NativeEventRegistration } from "@afcon360/mobile-core";

type RegistrationFilter = "upcoming" | "past" | "all";

type Props = {
  onOpenEvents: () => void;
  onOpenWebsite: (path: string) => void;
};

const BLUE = "#0E4CCD";
const BLUE_SOFT = "#DBEAFE";
const INK = "#1A1A1A";
const MUTED = "#6C757D";
const BORDER = "#E9ECEF";
const CANVAS = "#F2F4F2";
const WHITE = "#FFFFFF";

function localDateKey(value: Date): string {
  return String(value.getFullYear()) + "-" +
    String(value.getMonth() + 1).padStart(2, "0") + "-" +
    String(value.getDate()).padStart(2, "0");
}

function dateLabel(value: string | null | undefined): string {
  if (!value) return "Date to be announced";
  const datePart = value.slice(0, 10);
  const date = new Date(datePart + "T00:00:00");
  if (Number.isNaN(date.getTime())) return datePart;
  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric"
  });
}

function startDate(item: NativeEventRegistration): string {
  return (item.event.start_date || "").slice(0, 10);
}

function isCancelled(item: NativeEventRegistration): boolean {
  return ["cancelled", "refunded", "rejected"].includes(String(item.status).toLowerCase());
}

const card = {
  backgroundColor: WHITE,
  borderColor: BORDER,
  borderWidth: 1,
  borderRadius: 15,
  padding: 15,
  gap: 11
} as const;

const quiet = {
  color: MUTED,
  fontSize: 12,
  lineHeight: 18
} as const;

const heading = {
  color: INK,
  fontSize: 16,
  fontWeight: "900" as const
};

export function MyEventsOverview({ onOpenEvents, onOpenWebsite }: Props) {
  const [registrations, setRegistrations] = useState<NativeEventRegistration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<RegistrationFilter>("upcoming");
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });

  const loadRegistrations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await eventClient.listRegistrations(50, 0);
      setRegistrations(result.items ?? []);
    } catch (cause) {
      setError(cause instanceof Error
        ? cause.message
        : "Your event registrations could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRegistrations();
  }, [loadRegistrations]);

  const today = localDateKey(new Date());
  const active = useMemo(
    () => registrations.filter(item => !isCancelled(item)),
    [registrations]
  );
  const upcoming = useMemo(
    () => active
      .filter(item => !startDate(item) || startDate(item) >= today)
      .sort((a, b) => startDate(a).localeCompare(startDate(b))),
    [active, today]
  );
  const past = useMemo(
    () => active
      .filter(item => !!startDate(item) && startDate(item) < today)
      .sort((a, b) => startDate(b).localeCompare(startDate(a))),
    [active, today]
  );
  const attended = registrations.filter(item =>
    ["checked_in", "attended"].includes(String(item.status).toLowerCase())
  );
  const recent = useMemo(
    () => [...registrations]
      .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")))
      .slice(0, 5),
    [registrations]
  );

  const monthYear = calendarMonth.getFullYear();
  const monthIndex = calendarMonth.getMonth();
  const monthTitle = calendarMonth.toLocaleDateString(undefined, {
    month: "long",
    year: "numeric"
  });
  const firstWeekday = new Date(monthYear, monthIndex, 1).getDay();
  const daysInMonth = new Date(monthYear, monthIndex + 1, 0).getDate();
  const calendarCells: Array<number | null> = [
    ...Array.from({ length: firstWeekday }, () => null),
    ...Array.from({ length: daysInMonth }, (_, index) => index + 1)
  ];
  while (calendarCells.length % 7 !== 0) calendarCells.push(null);

  const registeredDates = new Set(
    registrations.map(startDate).filter(Boolean)
  );
  const pastEventDates = new Set(past.map(startDate).filter(Boolean));
  const dayKey = (day: number) =>
    String(monthYear) + "-" +
    String(monthIndex + 1).padStart(2, "0") + "-" +
    String(day).padStart(2, "0");

  const visibleRegistrations = filter === "upcoming"
    ? upcoming
    : filter === "past"
      ? past
      : registrations;

  const nextEvent = upcoming[0] ?? null;

  return (
    <View style={{ gap: 15 }}>
      <View
        style={{
          backgroundColor: "#EAF1FF",
          borderColor: "#C9DAFF",
          borderWidth: 1,
          borderRadius: 15,
          padding: 15,
          gap: 9
        }}
      >
        <Text style={{ color: BLUE, fontSize: 10, fontWeight: "900", letterSpacing: 0.9 }}>
          GROW WITH AFCON360
        </Text>
        <Text style={heading}>Become a Partner</Text>
        <Text style={quiet}>
          Already using AFCON360 as a customer? You can also offer services or operate an organisation.
        </Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          <Pressable
            accessibilityRole="button"
            onPress={() => onOpenWebsite("/onboarding/choose")}
            style={{ backgroundColor: BLUE, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 9 }}
          >
            <Text style={{ color: WHITE, fontSize: 11, fontWeight: "900" }}>Become a Partner ›</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={() => onOpenWebsite("/wallet/agent/apply")}
            style={{ backgroundColor: WHITE, borderColor: BLUE, borderWidth: 1, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 9 }}
          >
            <Text style={{ color: BLUE, fontSize: 11, fontWeight: "900" }}>Apply as Wallet Agent</Text>
          </Pressable>
        </View>
      </View>

      <View style={{ flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", gap: 8 }}>
        <View style={{ flex: 1, gap: 3 }}>
          <Text style={heading}>My Events</Text>
          <Text style={quiet}>Your attendee dashboard — tickets, activity and organizer tools</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          onPress={onOpenEvents}
          style={{ backgroundColor: BLUE, paddingHorizontal: 12, paddingVertical: 9, borderRadius: 9 }}
        >
          <Text style={{ color: WHITE, fontSize: 11, fontWeight: "900" }}>Browse Events</Text>
        </Pressable>
      </View>

      <View style={card}>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
          <Text style={heading}>Event Calendar</Text>
          <View style={{ flexDirection: "row", gap: 7 }}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Previous month"
              onPress={() => setCalendarMonth(new Date(monthYear, monthIndex - 1, 1))}
              style={styles.calendarButton}
            >
              <Text style={styles.calendarButtonText}>‹</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Next month"
              onPress={() => setCalendarMonth(new Date(monthYear, monthIndex + 1, 1))}
              style={styles.calendarButton}
            >
              <Text style={styles.calendarButtonText}>›</Text>
            </Pressable>
          </View>
        </View>
        <Text style={{ color: INK, fontSize: 12, fontWeight: "800", textAlign: "center" }}>
          {monthTitle}
        </Text>
        <View style={{ flexDirection: "row", justifyContent: "space-around" }}>
          {["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"].map(day => (
            <Text key={day} style={styles.weekday}>{day}</Text>
          ))}
        </View>
        <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
          {calendarCells.map((day, index) => {
            const hasEvent = day !== null && registeredDates.has(dayKey(day));
            const isPastEvent = day !== null && pastEventDates.has(dayKey(day));
            const isToday = day !== null && dayKey(day) === today;
            return (
              <View
                key={(day === null ? "blank" : String(day)) + ":" + String(index)}
                style={styles.calendarCell}
              >
                {day !== null ? (
                  <Pressable
                    accessibilityRole={hasEvent ? "button" : undefined}
                    accessibilityLabel={hasEvent ? "Events on " + dayKey(day) : undefined}
                    onPress={hasEvent ? onOpenEvents : undefined}
                    style={[
                      styles.calendarDay,
                      isToday ? styles.calendarToday : null
                    ]}
                  >
                    <Text style={{
                      color: isToday ? BLUE : INK,
                      fontSize: 11,
                      fontWeight: hasEvent || isToday ? "900" : "500"
                    }}>
                      {day}
                    </Text>
                    {hasEvent ? <View style={[styles.eventDot, { backgroundColor: isPastEvent ? MUTED : BLUE }]} /> : null}
                  </Pressable>
                ) : null}
              </View>
            );
          })}
        </View>
        <View style={{ flexDirection: "row", justifyContent: "center", gap: 16 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
            <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: BLUE }} />
            <Text style={quiet}>Upcoming</Text>
          </View>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
            <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: MUTED }} />
            <Text style={quiet}>Past</Text>
          </View>
        </View>
      </View>

      <View style={card}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={heading}>Next Event</Text>
          <Text style={{ color: BLUE, fontSize: 10, fontWeight: "900" }}>MY EVENTS</Text>
        </View>
        {nextEvent ? (
          <>
            <Text style={{ color: INK, fontSize: 16, fontWeight: "900" }}>
              {nextEvent.event.name || "Upcoming event"}
            </Text>
            <Text style={quiet}>
              {dateLabel(nextEvent.event.start_date)}
              {nextEvent.event.city ? "  ·  " + nextEvent.event.city : ""}
            </Text>
            <Text style={quiet}>
              {nextEvent.ticket_type} · {nextEvent.registration_reference}
            </Text>
            <Pressable onPress={onOpenEvents} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>View Ticket / Access Pass</Text>
            </Pressable>
          </>
        ) : (
          <>
            <Text style={{ color: INK, fontWeight: "800" }}>No scheduled events</Text>
            <Text style={quiet}>Explore the tournament and register for your next event.</Text>
            <Pressable onPress={onOpenEvents} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>Browse Events</Text>
            </Pressable>
          </>
        )}
      </View>

      <View style={card}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={heading}>Upcoming Reminders</Text>
          <Pressable onPress={() => onOpenWebsite("/theme/preferences")}>
            <Text style={{ color: BLUE, fontSize: 11, fontWeight: "900" }}>Manage Alerts</Text>
          </Pressable>
        </View>
        {upcoming.slice(0, 3).length ? upcoming.slice(0, 3).map(item => (
          <View
            key={item.registration_reference}
            style={{ borderTopWidth: 1, borderTopColor: BORDER, paddingTop: 9, gap: 3 }}
          >
            <Text style={{ color: INK, fontSize: 12, fontWeight: "900" }}>
              {item.event.name || "Event"}
            </Text>
            <Text style={quiet}>
              {dateLabel(item.event.start_date)}
              {item.event.city ? " · " + item.event.city : ""}
            </Text>
          </View>
        )) : (
          <Text style={quiet}>No upcoming event reminders.</Text>
        )}
      </View>

      <View style={card}>
        <Text style={heading}>Host Your Own Event</Text>
        <Text style={quiet}>
          Create events, sell tickets and grow your community. Your attendee history stays with you.
        </Text>
        <Pressable
          onPress={() => onOpenWebsite("/user/dashboard#events")}
          style={[styles.primaryButton, { alignSelf: "flex-start", paddingHorizontal: 15 }]}
        >
          <Text style={styles.primaryButtonText}>Host an Event ›</Text>
        </Pressable>
      </View>

      <View style={card}>
        <Text style={heading}>Tickets & Badges</Text>
        <View style={{ flexDirection: "row", gap: 10 }}>
          <View style={{ flex: 1, alignItems: "center", backgroundColor: CANVAS, borderRadius: 11, padding: 12, gap: 4 }}>
            <Text style={styles.statNumber}>{upcoming.length}</Text>
            <Text style={styles.statLabel}>ACTIVE TICKETS</Text>
          </View>
          <View style={{ flex: 1, alignItems: "center", backgroundColor: CANVAS, borderRadius: 11, padding: 12, gap: 4 }}>
            <Text style={styles.statNumber}>{attended.length}</Text>
            <Text style={styles.statLabel}>BADGES EARNED</Text>
          </View>
        </View>
        <Pressable onPress={onOpenEvents} style={{ alignSelf: "flex-end", paddingVertical: 3 }}>
          <Text style={{ color: BLUE, fontSize: 11, fontWeight: "900" }}>View All Tickets ›</Text>
        </Pressable>
      </View>

      <View style={card}>
        <Text style={heading}>Recent Activity</Text>
        {recent.length ? recent.map(item => (
          <View
            key={item.registration_reference}
            style={{ borderTopWidth: 1, borderTopColor: BORDER, paddingTop: 9, gap: 3 }}
          >
            <Text style={{ color: INK, fontSize: 12, fontWeight: "800" }}>
              {item.event.name || "Event"}
            </Text>
            <Text style={quiet}>
              {["checked_in", "attended"].includes(String(item.status).toLowerCase())
                ? "Attended"
                : "Registered"} · {item.ticket_type}
            </Text>
          </View>
        )) : (
          <Text style={quiet}>No activity yet. Register for an event to get started.</Text>
        )}
      </View>

      <View style={card}>
        <Text style={heading}>My Registrations</Text>
        <View style={{ flexDirection: "row", gap: 7 }}>
          {(["upcoming", "past", "all"] as RegistrationFilter[]).map(value => (
            <Pressable
              key={value}
              onPress={() => setFilter(value)}
              style={[
                styles.filterButton,
                filter === value ? styles.filterButtonActive : null
              ]}
            >
              <Text style={{
                color: filter === value ? BLUE : MUTED,
                fontSize: 10,
                fontWeight: "900",
                textTransform: "capitalize"
              }}>
                {value} {value === "upcoming" ? upcoming.length : value === "past" ? past.length : registrations.length}
              </Text>
            </Pressable>
          ))}
        </View>
        {loading ? (
          <ActivityIndicator color={BLUE} />
        ) : error ? (
          <Text style={{ color: "#A3332B", fontSize: 12, lineHeight: 18 }}>{error}</Text>
        ) : visibleRegistrations.length ? visibleRegistrations.slice(0, 8).map(item => (
          <View
            key={item.registration_reference}
            style={{ borderTopWidth: 1, borderTopColor: BORDER, paddingTop: 10, gap: 4 }}
          >
            <Text style={{ color: INK, fontWeight: "900", fontSize: 12 }}>
              {item.event.name || "Event"}
            </Text>
            <Text style={quiet}>
              {dateLabel(item.event.start_date)} · {item.ticket_type}
            </Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 7 }}>
              <Text style={{ color: BLUE, fontWeight: "800", fontSize: 10 }}>
                {String(item.status).replace(/_/g, " ")}
              </Text>
              <Text style={{ color: MUTED, fontSize: 10 }}>
                {item.registration_reference}
              </Text>
            </View>
          </View>
        )) : (
          <Text style={quiet}>
            {filter === "upcoming"
              ? "You have no upcoming event registrations."
              : filter === "past"
                ? "Your attended events will appear here."
                : "You have no event registrations yet."}
          </Text>
        )}
        <Pressable onPress={() => void loadRegistrations()} style={{ alignSelf: "flex-start", paddingVertical: 7 }}>
          <Text style={{ color: BLUE, fontSize: 11, fontWeight: "900" }}>Refresh registrations</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = {
  calendarButton: {
    width: 30,
    height: 30,
    borderRadius: 9,
    backgroundColor: BLUE_SOFT,
    alignItems: "center" as const,
    justifyContent: "center" as const
  },
  calendarButtonText: { color: BLUE, fontSize: 18, fontWeight: "900" as const },
  weekday: { color: MUTED, fontSize: 10, fontWeight: "900" as const, width: "13%", textAlign: "center" as const },
  calendarCell: { width: "14.285%", minHeight: 37, alignItems: "center" as const, justifyContent: "center" as const },
  calendarDay: { width: 29, height: 29, borderRadius: 15, alignItems: "center" as const, justifyContent: "center" as const },
  calendarToday: { backgroundColor: BLUE_SOFT, borderWidth: 1, borderColor: BLUE },
  eventDot: { position: "absolute" as const, bottom: 2, width: 4, height: 4, borderRadius: 2, backgroundColor: BLUE },
  primaryButton: { backgroundColor: BLUE, borderRadius: 9, paddingHorizontal: 12, paddingVertical: 11, alignItems: "center" as const },
  primaryButtonText: { color: WHITE, fontWeight: "900" as const, fontSize: 11 },
  statNumber: { color: BLUE, fontSize: 23, fontWeight: "900" as const },
  statLabel: { color: MUTED, fontSize: 9, fontWeight: "800" as const, letterSpacing: 0.5 },
  filterButton: { paddingVertical: 8, paddingHorizontal: 11, borderRadius: 20, backgroundColor: CANVAS },
  filterButtonActive: { backgroundColor: BLUE_SOFT }
} as const;
