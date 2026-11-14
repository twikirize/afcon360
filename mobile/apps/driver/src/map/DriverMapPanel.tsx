import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, Text, TextInput, View } from "react-native";
import { WebView } from "react-native-webview";
import {
  ActionButton,
  Panel,
  SectionTitle,
  StatusPill,
  palette
} from "@afcon360/mobile-ui";
import { authClient } from "../services/api";
import { requestForegroundDriverLocation } from "../location/permissions";

type MapConfig = {
  tile_url_template: string;
  tile_attribution: string;
  tile_source_label: string;
  default_center: { latitude: number; longitude: number };
  default_zoom: number;
};

type DemandCell = {
  center: { latitude: number; longitude: number };
  request_count: number;
};

type DemandResponse = {
  success: boolean;
  state?: string;
  cells?: DemandCell[];
};

type Place = {
  label: string;
  latitude: number;
  longitude: number;
  provider: string;
};

type GeocodeResponse = {
  success: boolean;
  results: Place[];
  attribution?: string | null;
};

type Point = { latitude: number; longitude: number };

function safeScriptJson(value: unknown) {
  return JSON.stringify(value)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026");
}

function buildMapHtml(
  config: MapConfig,
  driverPoint: Point | null,
  selectedPlace: Place | null,
  cells: DemandCell[]
) {
  const payload = safeScriptJson({ config, driverPoint, selectedPlace, cells });
  return `<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
  <style>
    html,body,#map{height:100%;width:100%;margin:0;padding:0;background:#eef3ef}
    body{font-family:Arial,sans-serif}
    .leaflet-control-attribution{font-size:9px}
    .map-error{padding:18px;color:#34443a;font-size:14px}
  </style>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
</head>
<body>
<div id="map"><div class="map-error">Loading AFCON360 map…</div></div>
<script>
(function(){
  const data = ${payload};
  if (!window.L) {
    document.getElementById("map").innerHTML =
      '<div class="map-error">The map library could not load. Driver trips and offers remain available.</div>';
    return;
  }
  const fallback = data.config.default_center;
  const selected = data.selectedPlace;
  const driver = data.driverPoint;
  const center = driver || (selected ? {
    latitude:selected.latitude, longitude:selected.longitude
  } : fallback);
  const map = L.map("map", {zoomControl:true, attributionControl:true})
    .setView([center.latitude, center.longitude],
      driver || selected ? Math.max(14, data.config.default_zoom) : data.config.default_zoom);
  L.tileLayer(data.config.tile_url_template, {
    maxZoom:19,
    attribution:data.config.tile_attribution
  }).addTo(map);

  function addTextPopup(marker, text) {
    const node = document.createElement("div");
    node.textContent = String(text || "");
    marker.bindPopup(node);
  }

  if (driver) {
    const marker = L.marker([driver.latitude, driver.longitude]).addTo(map);
    addTextPopup(marker, "Your current device location (shown on this device)");
  }
  if (selected) {
    const marker = L.marker([selected.latitude, selected.longitude]).addTo(map);
    addTextPopup(marker, selected.label + " · " + selected.provider);
  }
  (data.cells || []).forEach(function(cell) {
    const point = cell.center;
    if (!point || !Number.isFinite(point.latitude) || !Number.isFinite(point.longitude)) return;
    const count = Number(cell.request_count) || 0;
    const marker = L.circleMarker([point.latitude, point.longitude], {
      radius:Math.min(18, 7 + count),
      color:"#9a4b00",
      weight:1,
      fillColor:"#f3a63b",
      fillOpacity:0.65
    }).addTo(map);
    addTextPopup(marker, count + " recent ride requests in this demand area");
  });
  if (!driver && !selected && !(data.cells || []).length) {
    const centre = L.circleMarker([fallback.latitude, fallback.longitude], {
      radius:4, color:"#53645a", fillOpacity:0.5
    }).addTo(map);
    addTextPopup(centre, "Default Kampala map centre — not your current location");
  }
  setTimeout(function(){ map.invalidateSize(); }, 150);
})();
</script>
</body>
</html>`;
}

export function DriverMapPanel() {
  const [config, setConfig] = useState<MapConfig | null>(null);
  const [cells, setCells] = useState<DemandCell[]>([]);
  const [demandState, setDemandState] = useState("loading");
  const [mapError, setMapError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchText, setSearchText] = useState("");
  const [searching, setSearching] = useState(false);
  const [places, setPlaces] = useState<Place[]>([]);
  const [attribution, setAttribution] = useState<string | null>(null);
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null);
  const [driverPoint, setDriverPoint] = useState<Point | null>(null);
  const [locating, setLocating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setMapError(null);
    const results = await Promise.allSettled([
      authClient.request<{ data: MapConfig }>("/api/mobile/v1/driver/map-config"),
      authClient.request<DemandResponse>("/api/mobile/v1/driver/demand/cells")
    ]);
    if (results[0].status === "fulfilled") {
      setConfig(results[0].value.data);
    } else {
      setMapError("Map settings are unavailable. Refresh to try again.");
    }
    if (results[1].status === "fulfilled") {
      const response = results[1].value;
      setCells(response.cells ?? []);
      setDemandState(response.state ?? (response.cells?.length ? "available" : "no_recent_demand"));
    } else {
      setCells([]);
      setDemandState("unavailable");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const locate = async () => {
    setLocating(true);
    try {
      const result = await requestForegroundDriverLocation();
      if (!result.granted) {
        setMapError("Allow location while using AFCON360 Driver to show your position on this map.");
        return;
      }
      setDriverPoint({
        latitude: result.location.latitude,
        longitude: result.location.longitude
      });
      setSelectedPlace(null);
      setMapError(null);
    } catch (error) {
      setMapError(error instanceof Error ? error.message : "Current location is unavailable.");
    } finally {
      setLocating(false);
    }
  };

  const search = async () => {
    const query = searchText.trim();
    if (query.length < 2) {
      setMapError("Enter at least two characters to search for a place.");
      return;
    }
    setSearching(true);
    setMapError(null);
    try {
      const response = await authClient.request<GeocodeResponse>(
        "/geo/api/geocode?q=" + encodeURIComponent(query) + "&limit=5"
      );
      setPlaces(response.results ?? []);
      setAttribution(response.attribution ?? null);
      if (!response.results?.length) setMapError("No matching places were found.");
    } catch (error) {
      setMapError(error instanceof Error ? error.message : "Place search is unavailable.");
    } finally {
      setSearching(false);
    }
  };

  const html = useMemo(
    () => config ? buildMapHtml(config, driverPoint, selectedPlace, cells) : undefined,
    [config, driverPoint, selectedPlace, cells]
  );

  return (
    <Panel>
      <View style={{ flexDirection:"row", alignItems:"center", justifyContent:"space-between", gap:8 }}>
        <SectionTitle>Driver map and demand</SectionTitle>
        <StatusPill tone={demandState === "available" ? "green" : "neutral"}>
          {demandState === "available" ? cells.length + " demand areas"
            : demandState === "location_unavailable" ? "Location needed"
            : demandState === "unavailable" ? "Demand unavailable"
            : "No recent demand"}
        </StatusPill>
      </View>
      <View style={{ flexDirection:"row", gap:8 }}>
        <TextInput
          value={searchText}
          onChangeText={setSearchText}
          placeholder="Find a pickup area or place"
          placeholderTextColor={palette.muted}
          returnKeyType="search"
          onSubmitEditing={() => { void search(); }}
          style={{
            flex:1, minWidth:0, borderWidth:1, borderColor:palette.border,
            borderRadius:12, paddingHorizontal:12, paddingVertical:10,
            color:palette.ink, backgroundColor:"#FFFFFF"
          }}
        />
        <ActionButton label={searching ? "…" : "Search"} disabled={searching} onPress={() => { void search(); }} />
      </View>
      {places.length ? (
        <View style={{ gap:6 }}>
          {places.map((place,index) => (
            <Pressable
              key={place.provider + "-" + place.latitude + "-" + place.longitude + "-" + index}
              onPress={() => {
                setSelectedPlace(place);
                setDriverPoint(null);
                setPlaces([]);
              }}
              style={{ padding:10, borderRadius:10, backgroundColor:"#F5F8F5" }}
            >
              <Text style={{ color:palette.ink, fontSize:12, fontWeight:"700" }}>{place.label}</Text>
              <Text style={{ color:palette.muted, fontSize:10 }}>{place.provider}</Text>
            </Pressable>
          ))}
          {attribution ? <Text style={{ color:palette.muted, fontSize:10 }}>{attribution}</Text> : null}
        </View>
      ) : null}
      <View style={{ height:250, overflow:"hidden", borderRadius:14, borderWidth:1, borderColor:palette.border }}>
        {loading || !html ? (
          <View style={{ flex:1, alignItems:"center", justifyContent:"center", gap:8 }}>
            <ActivityIndicator color={palette.green} />
            <Text style={{ color:palette.muted, fontSize:12 }}>Loading map settings…</Text>
          </View>
        ) : (
          <WebView
            originWhitelist={["*"]}
            source={{ html }}
            javaScriptEnabled
            domStorageEnabled
            setSupportMultipleWindows={false}
            onError={() => setMapError("Map could not be loaded. Check your internet connection.")}
          />
        )}
      </View>
      <View style={{ flexDirection:"row", gap:8 }}>
        <ActionButton label={locating ? "Locating…" : "Show my location"} disabled={locating} onPress={() => { void locate(); }} />
        <ActionButton label="Refresh map" disabled={loading} onPress={() => { void load(); }} />
      </View>
      {mapError ? (
        <Text accessibilityRole="alert" style={{ color:"#9A3A2F", fontSize:11 }}>{mapError}</Text>
      ) : null}
      <Text style={{ color:palette.muted, fontSize:10, lineHeight:15 }}>
        {demandState === "location_unavailable"
          ? "Publish a fresh Driver location while online to unlock nearby aggregate demand."
          : "Demand areas show only aggregated request counts in groups of at least three. Individual rider locations are never displayed."}
        {" "}Map tiles: {config?.tile_source_label ?? "not configured"}.
      </Text>
    </Panel>
  );
}
