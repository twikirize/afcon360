import React, { useRef, useEffect, useCallback } from "react";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import type { MapMessage, Place } from "./types";

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

type MapViewProps = {
  pickup: Place | null;
  dropoff: Place | null;
  onMapMessage: (message: MapMessage) => void;
  onMapReady: () => void;
  onMapError: (error: string) => void;
};

export function MapView({ pickup, dropoff, onMapMessage, onMapReady, onMapError }: MapViewProps) {
  const mapRef = useRef<WebView>(null);
  const mapResolveSeq = useRef({ pickup: 0, dropoff: 0 });

  const handleMapMessage = useCallback((event: WebViewMessageEvent) => {
    try {
      const message = JSON.parse(event.nativeEvent.data) as MapMessage;
      onMapMessage(message);
    } catch {
      onMapError("The map returned an unreadable location. Use place search or GPS instead.");
    }
  }, [onMapMessage, onMapError]);

  useEffect(() => {
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
      onMessage={handleMapMessage}
      onLoadEnd={onMapReady}
      onError={() => onMapError("The map could not load. Place search and device GPS remain available.")}
      onHttpError={() => onMapError("Map tiles are temporarily unavailable. Place search and device GPS remain available.")}
      style={{ width: "100%", height: 300 }}
    />
  );
}

export default MapView;