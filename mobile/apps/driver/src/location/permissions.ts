import * as Location from "expo-location";
export async function requestForegroundDriverLocation() {
  const permission = await Location.requestForegroundPermissionsAsync();
  if (permission.status !== "granted") return { granted: false as const, permission };
  const current = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
  return {
    granted: true as const,
    permission,
    location: {
      latitude: current.coords.latitude,
      longitude: current.coords.longitude,
      accuracy: current.coords.accuracy,
      observedAt: current.timestamp
    }
  };
}
