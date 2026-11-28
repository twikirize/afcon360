import React from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { colors, radii, spacing } from "../../theme/tokens";
import { getMapOrigin, tileUrlTemplateFor } from "../../services/mapTiles";
import type { Place } from "../ride/types";

// Map provider type - can be extended when native maps are available
export type MapProviderType = "webview" | "native";

// Configuration for map provider
export const MAP_PROVIDER: MapProviderType = "webview"; // Change to "native" when react-native-maps is configured

// Base map interface that both providers must implement
export interface MapProviderInterface {
  onMapReady: () => void;
  onMapError: (error: string) => void;
  onMapMessage: (message: any) => void;
  pickup: Place | null;
  dropoff: Place | null;
}

// Props for the map component
export interface MapComponentProps extends MapProviderInterface {
  style?: any;
  testID?: string;
}

export const MAP_TILE_ERROR_MESSAGE =
  "Map unavailable right now. Search for a place or use your current location.";

/**
 * Leaflet page. The tile layer is a RELATIVE path resolved against the API
 * origin we load the page from, so tiles always come through our server
 * proxy. Map readiness is reported only after the first real tile paints;
 * total initial tile failure reports a truthful unavailable state instead of
 * hiding broken tiles behind a premature WebView-loaded signal.
 */
function buildMapHtml(): string {
  return `
<!doctype html>
<html><head><meta name='viewport' content='width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no'>
<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
  integrity='sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=' crossorigin=''>
<style>
html,body,#map{height:100%;width:100%;margin:0;background:#dfe7e0}
.leaflet-container{font:13px sans-serif;background:#dfe7e0}
.pin{width:22px;height:22px;border:3px solid white;border-radius:50% 50% 50% 0;transform:rotate(-45deg);position:relative;box-shadow:0 2px 7px #0006}.pin:after{content:'';position:absolute;width:6px;height:6px;left:5px;top:5px;border-radius:50%;background:#fff}
.pin.pickup{background:#0e6b4f}
.pin.dropoff{background:#d92d20}
.leaflet-control-attribution{font-size:9px!important;background:rgba(255,255,255,.78)!important}
</style>
<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
  integrity='sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=' crossorigin=''></script>
</head><body><div id='map'></div>
<script>
(function(){
  function send(value){if(window.ReactNativeWebView)window.ReactNativeWebView.postMessage(JSON.stringify(value));}
  if(!window.L){send({type:'map_library_error'});return;}
  var map=L.map('map',{zoomControl:false,attributionControl:true,zoomSnap:0.5}).setView([0.3136,32.5811],12);
  L.control.zoom({position:'bottomright'}).addTo(map);
  var tiles=L.tileLayer('/geo/api/tiles/{z}/{x}/{y}.png',{
    maxZoom:19,
    attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  });
  var tileOk=0,tileFailed=0,reportedDown=false,failedTimer=null;
  tiles.on('tileload',function(){
    tileOk++;
    if(tileOk===1){
      if(failedTimer){clearTimeout(failedTimer);failedTimer=null;}
      send({type:'map_ready'});
    }
  });
  tiles.on('tileerror',function(){
    tileFailed++;
    // Tile requests are independent. Give the rest of the viewport time to
    // return before declaring the entire map unavailable.
    if(tileOk===0&&tileFailed>=4&&!reportedDown&&!failedTimer){
      failedTimer=setTimeout(function(){
        failedTimer=null;
        if(tileOk===0&&tileFailed>=4&&!reportedDown){
          reportedDown=true;
          send({type:'map_tiles_unavailable'});
        }
      },3000);
    }
  });
  tiles.addTo(map);
  var pins={pickup:null,dropoff:null},line=null;
  function icon(side){return L.divIcon({className:'',html:'<div class="pin '+side+'"></div>',iconSize:[22,22],iconAnchor:[11,11]});}
  function refresh(){
    if(line){map.removeLayer(line);line=null;}
    var p=pins.pickup,d=pins.dropoff;
    if(p&&d){
      line=L.polyline([[p.lat,p.lng],[d.lat,d.lng]],{color:'#0E5B36',weight:4,dashArray:'8 8',opacity:.9}).addTo(map);
      map.fitBounds(line.getBounds(),{padding:[34,34],maxZoom:15});
    } else if(p){map.setView([p.lat,p.lng],15);}
    else if(d){map.setView([d.lat,d.lng],15);}
  }
  window.__afconSetPin=function(payload){
    var side=payload.side;if(!side)return;
    if(!payload.value){
      if(pins[side])map.removeLayer(pins[side]);
      pins[side]=null;refresh();return;
    }
    var v=payload.value;
    if(pins[side]){pins[side].setLatLng([v.latitude,v.longitude]);}
    else{
      pins[side]=L.marker([v.latitude,v.longitude],{draggable:true,icon:icon(side)}).addTo(map);
      pins[side].on('dragend',function(){var ll=pins[side].getLatLng();send({type:'map_drag',side:side,latitude:ll.lat,longitude:ll.lng});});
    }
    refresh();
  };
  map.on('click',function(e){send({type:'map_tap',latitude:e.latlng.lat,longitude:e.latlng.lng});});
  setTimeout(function(){map.invalidateSize();},250);
})();
</script></body></html>
`.trim();
}

const MAP_HTML = buildMapHtml();

// WebView-based map (current implementation)
export function WebViewMap({ pickup, dropoff, onMapReady, onMapError, onMapMessage, style }: MapComponentProps) {
  // Dynamic import to avoid bundling react-native-webview when using native maps
  const WebView = require("react-native-webview").default;

  const mapRef = React.useRef<any>(null);
  const [origin, setOrigin] = React.useState<string | null>(null);

  React.useEffect(() => {
    let active = true;
    void getMapOrigin()
      .then(next => {
        if (active) setOrigin(next);
      })
      .catch(() => {
        if (active) onMapError(MAP_TILE_ERROR_MESSAGE);
      });
    return () => {
      active = false;
    };
  }, [onMapError]);

  React.useEffect(() => {
    const updatePin = (side: "pickup" | "dropoff", value: Place | null) => {
      const payload = JSON.stringify({ side, value: value ? {
        label: value.label,
        latitude: value.latitude,
        longitude: value.longitude,
        source: value.source
      } : null });
      mapRef.current?.injectJavaScript("window.__afconSetPin&&window.__afconSetPin(" + payload + ");true;");
    };
    updatePin("pickup", pickup);
    updatePin("dropoff", dropoff);
  }, [pickup, dropoff, origin]);

  // The WebView posts JSON strings; handing React Native's raw event object
  // to the caller silently dropped every map tap and pin drag.
  const handleMessage = React.useCallback((event: any) => {
    let message: any;
    try {
      message = JSON.parse(event?.nativeEvent?.data ?? "");
    } catch {
      return;
    }
    if (!message || typeof message.type !== "string") return;
    if (message.type === "map_ready") onMapReady();
    if (message.type === "map_tiles_unavailable" || message.type === "map_library_error") {
      onMapError(MAP_TILE_ERROR_MESSAGE);
      return;
    }
    onMapMessage(message);
  }, [onMapError, onMapMessage]);

  if (!origin) {
    return (
      <View style={[styles.placeholder, style]}>
        <ActivityIndicator color={colors.brand.green} />
      </View>
    );
  }

  return (
    <WebView
      ref={mapRef}
      source={{ html: MAP_HTML, baseUrl: origin + "/" }}
      originWhitelist={["*"]}
      javaScriptEnabled
      domStorageEnabled
      cacheEnabled
      scrollEnabled={false}
      nestedScrollEnabled={false}
      onMessage={handleMessage}
      onError={() => onMapError(MAP_TILE_ERROR_MESSAGE)}
      style={[styles.fill, style]}
    />
  );
}

// Native map placeholder (to be implemented with react-native-maps)
export function NativeMap({ pickup, dropoff, onMapReady, onMapError, onMapMessage, style }: MapComponentProps) {
  // TODO: Implement with react-native-maps when native rebuild is scheduled
  // Fallback to WebView for now
  console.warn("NativeMap not yet implemented, falling back to WebViewMap");
  return <WebViewMap pickup={pickup} dropoff={dropoff} onMapReady={onMapReady} onMapError={onMapError} onMapMessage={onMapMessage} style={style} />;
}

// Main Map component that selects the provider based on configuration
export function Map({ pickup, dropoff, onMapReady, onMapError, onMapMessage, style, testID }: MapComponentProps) {
  if (MAP_PROVIDER === "native") {
    return <NativeMap pickup={pickup} dropoff={dropoff} onMapReady={onMapReady} onMapError={onMapError} onMapMessage={onMapMessage} style={style} testID={testID} />;
  }
  return <WebViewMap pickup={pickup} dropoff={dropoff} onMapReady={onMapReady} onMapError={onMapError} onMapMessage={onMapMessage} style={style} testID={testID} />;
}

// Hook for managing map state (can be used by screens)
export function useMapState() {
  const [mapReady, setMapReady] = React.useState(false);
  const [mapError, setMapError] = React.useState<string | null>(null);
  const mapRef = React.useRef<any>(null);
  const mapResolveSeq = React.useRef({ pickup: 0, dropoff: 0 });

  const handleMapMessage = React.useCallback(() => {
    // Message handling is done by the screen component
  }, []);

  const updatePin = React.useCallback((side: "pickup" | "dropoff", value: Place | null) => {
    mapRef.current?.updatePin?.(side, value);
  }, []);

  return {
    mapReady,
    setMapReady,
    mapError,
    setMapError,
    mapRef,
    mapResolveSeq,
    handleMapMessage,
    updatePin,
  };
}

export { tileUrlTemplateFor };

const styles = StyleSheet.create({
  fill: { flex: 1 },
  placeholder: {
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface.canvas,
    borderRadius: radii.lg,
    gap: spacing.sm,
  },
});

export default Map;
