import React from "react";
import { Platform, View, StyleSheet } from "react-native";
import { colors, spacing, radii } from "../theme/tokens";
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

// WebView-based map (current implementation)
export function WebViewMap({ pickup, dropoff, onMapReady, onMapError, onMapMessage, style }: MapComponentProps) {
  const MAP_HTML = `
<!doctype html>
<html><head><meta name='viewport' content='width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no'>
<link rel='stylesheet' href='https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css'>
<style>html,body,#map{height:100%;width:100%;margin:0;background:#e9f0eb} .leaflet-container{font:13px sans-serif} .pin{width:22px;height:22px;border:3px solid white;border-radius:50%;box-shadow:0 2px 7px #0006} .pin.pickup{background:#0e6b4f} .pin.dropoff{background:#d92d20} .leaflet-control-attribution{font-size:9px!important}</style>
<script src='https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js'></script>
</head><body><div id='map'></div>
<script>
(function(){
  var map=L.map('map',{zoomControl:true,attributionControl:true}).setView([0.3136,32.5811],12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
  var pins={pickup:null,dropoff:null},line=null;
  function send(value){if(window.ReactNativeWebView)window.ReactNativeWebView.postMessage(JSON.stringify(value));}
  function icon(side){return L.divIcon({className:'',html:'<div class="pin '+side+'"></div>',iconSize:[22,22],iconAnchor:[11,11]});}
  function refresh(){if(line){map.removeLayer(line);line=null;} var p=pins.pickup,d=pins.dropoff; if(p&&d){line=L.polyline([[p.lat,p.lng],[d.lat,d.lng]],{color:'#0E5B36',weight:4,dashArray:'8 8',opacity:.9}).addTo(map);map.fitBounds(line.getBounds(),{padding:[34,34],maxZoom:15});}else if(p){map.setView([p.lat,p.lng],15);}else if(d){map.setView([d.lat,d.lng],15);}}
  window.__afconSetPin=function(p){var side=p.side;if(!side)return;if(!p.value){if(pins[side])map.removeLayer(pins[side]);pins[side]=null;refresh();return;}var v=p.value;if(pins[side]){pins[side].setLatLng([v.latitude,v.longitude]);}else{pins[side]=L.marker([v.latitude,v.longitude],{draggable:true,icon:icon(side)}).addTo(map);pins[side].on('dragend',function(){var ll=pins[side].getLatLng();send({type:'map_drag',side:side,latitude:ll.lat,longitude:ll.lng});});}refresh();};
  map.on('click',function(e){send({type:'map_tap',latitude:e.latlng.lat,longitude:e.latlng.lng});});
  setTimeout(function(){map.invalidateSize();send({type:'map_ready'});},250);
})();
</script></body></html>
`.trim();

  // Dynamic import to avoid bundling react-native-webview when using native maps
  const WebView = require("react-native-webview").default;

  const mapRef = React.useRef<any>(null);
  const mapResolveSeq = React.useRef({ pickup: 0, dropoff: 0 });

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
  }, [pickup, dropoff]);

  return (
    <WebView
      ref={mapRef}
      source={{ html: MAP_HTML, baseUrl: "https://www.openstreetmap.org" }}
      originWhitelist={["*"]}
      javaScriptEnabled
      domStorageEnabled
      scrollEnabled={false}
      nestedScrollEnabled={false}
      onMessage={onMapMessage}
      onLoadEnd={onMapReady}
      onError={() => onMapError("The map could not load. Place search and device GPS remain available.")}
      onHttpError={() => onMapError("Map tiles are temporarily unavailable. Place search and device GPS remain available.")}
      style={style}
    />
  );
}

// Native map placeholder (to be implemented with react-native-maps)
export function NativeMap({ pickup, dropoff, onMapReady, onMapError, onMapMessage, style }: MapComponentProps) {
  // TODO: Implement with react-native-maps when native rebuild is scheduled
  // import MapView, { Marker, Polyline } from 'react-native-maps';
  // 
  // return (
  //   <MapView
  //     style={style}
  //     initialRegion={{
  //       latitude: pickup?.latitude ?? 0.3136,
  //       longitude: pickup?.longitude ?? 32.5811,
  //       latitudeDelta: 0.0922,
  //       longitudeDelta: 0.0421,
  //     }}
  //     onMapReady={onMapReady}
  //   >
  //     {pickup && (
  //       <Marker
  //         coordinate={{ latitude: pickup.latitude, longitude: pickup.longitude }}
  //         title="Pickup"
  //         pinColor="#0e6b4f"
  //         draggable
  //         onDragEnd={(e) => onMapMessage({ type: 'map_drag', side: 'pickup', latitude: e.nativeEvent.coordinate.latitude, longitude: e.nativeEvent.coordinate.longitude })}
  //       />
  //     )}
  //     {dropoff && (
  //       <Marker
  //         coordinate={{ latitude: dropoff.latitude, longitude: dropoff.longitude }}
  //         title="Destination"
  //         pinColor="#d92d20"
  //         draggable
  //         onDragEnd={(e) => onMapMessage({ type: 'map_drag', side: 'dropoff', latitude: e.nativeEvent.coordinate.latitude, longitude: e.nativeEvent.coordinate.longitude })}
  //       />
  //     )}
  //     {pickup && dropoff && (
  //       <Polyline
  //         coordinates={[
  //           { latitude: pickup.latitude, longitude: pickup.longitude },
  //           { latitude: dropoff.latitude, longitude: dropoff.longitude },
  //         ]}
  //         strokeColor="#0E5B36"
  //         strokeWidth={4}
  //       />
  //     )}
  //     <MapView.OnPressEvent
  //       onPress={(e) => onMapMessage({ type: 'map_tap', latitude: e.nativeEvent.coordinate.latitude, longitude: e.nativeEvent.coordinate.longitude })}
  //     />
  //   </MapView>
  // );

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

  const handleMapMessage = React.useCallback((message: any) => {
    // Message handling is done by the screen component
    // This hook just provides the ref and state
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

export default Map;