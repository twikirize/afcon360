/**
 * AFCON360 Driver Map Module
 * MapLibre GL integration for driver dashboard home view
 * Provides: driver location, demand heatmap stub, surge badges, nearby request pins
 */
(function () {
    "use strict";
    console.log('[DriverMap] IIFE started');

    // ============================================================
    // CONFIGURATION
    // ============================================================
    var MAP_CONFIG = {
        // Default to Kampala, Uganda - will be overridden by driver location
        defaultCenter: [32.5825, 0.3476],
        defaultZoom: 13,
        // Minimal inline style - works without external connections
        // Will be enhanced when CSP allows tile connections
        styleUrl: null,
        inlineStyle: {
            version: 8,
            name: "Minimal",
            sources: {},
            layers: [
                {
                    id: "background",
                    type: "background",
                    paint: { "background-color": "#e8f0e8" }
                }
            ]
        },
        maxZoom: 18,
        minZoom: 10
    };

    // Heatmap configuration (stub - will connect to real API later)
    var HEATMAP_CONFIG = {
        radius: 30,
        maxZoom: 15,
        opacity: 0.6,
        intensity: 1,
        weight: function (feature) {
            return feature.properties?.demand || 1;
        }
    };

    // Surge badge configuration
    var SURGE_CONFIG = {
        minZoom: 12,
        maxBadges: 20,
        pulseDuration: 2000
    };

    // ============================================================
    // STATE
    // ============================================================
    var map = null;
    var driverMarker = null;
    var driverPulseMarker = null;
    var heatmapLayerId = "demand-heatmap";
    var heatmapSourceId = "demand-heatmap-source";
    var surgeLayerId = "surge-badges";
    var surgeSourceId = "surge-badges-source";
    var requestPinsLayerId = "request-pins";
    var requestPinsSourceId = "request-pins-source";
    var currentDriverLocation = null;
    var animationFrameId = null;
    var isMapReady = false;
    var mapContainer = null;

    // ============================================================
    // UTILITIES
    // ============================================================
    function $(selector, context) {
        return (context || document).querySelector(selector);
    }

    function createElement(tag, className, attributes) {
        var el = document.createElement(tag);
        if (className) el.className = className;
        if (attributes) Object.keys(attributes).forEach(function (k) {
            el.setAttribute(k, attributes[k]);
        });
        return el;
    }

    function debounce(fn, ms) {
        var timer = null;
        return function () {
            var args = arguments;
            var ctx = this;
            clearTimeout(timer);
            timer = setTimeout(function () {
                fn.apply(ctx, args);
            }, ms);
        };
    }

    // ============================================================
    // MAP INITIALIZATION
    // ============================================================
    function initMap(containerId, options) {
        mapContainer = typeof containerId === "string" ? document.getElementById(containerId) : containerId;
        if (!mapContainer) {
            console.warn("[DriverMap] Container not found:", containerId);
            return Promise.reject(new Error("Container not found"));
        }

        if (!window.maplibregl) {
            console.warn("[DriverMap] MapLibre GL not loaded");
            return Promise.reject(new Error("MapLibre GL not loaded"));
        }

        var opts = Object.assign({}, MAP_CONFIG, options);

        // Check if map already exists
        if (map) {
            console.log("[DriverMap] Map already initialized");
            return Promise.resolve(map);
        }

        return new Promise(function (resolve, reject) {
            try {
                var style = opts.inlineStyle || opts.styleUrl;
                map = new maplibregl.Map({
                    container: mapContainer,
                    style: style,
                    center: opts.defaultCenter,
                    zoom: opts.defaultZoom,
                    maxZoom: opts.maxZoom,
                    minZoom: opts.minZoom,
                    attributionControl: false,
                    cooperativeGestures: true,
                    touchPitch: false,
                    touchRotate: false,
                    dragRotate: false,
                    keyboard: false,
                    doubleClickZoom: false,
                    boxZoom: false,
                    trackResize: true
                });

                map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
                map.addControl(new maplibregl.GeolocateControl({
                    positionOptions: { enableHighAccuracy: true },
                    trackUserLocation: true,
                    showUserHeading: true
                }), "top-right");

                map.on("load", function () {
                    isMapReady = true;
                    setupMapLayers();
                    resolve(map);
                });

                map.on("error", function (e) {
                    console.error("[DriverMap] Map error:", e.error);
                    if (!isMapReady) reject(e.error);
                });

                // Handle resize
                var resizeHandler = debounce(function () {
                    if (map) map.resize();
                }, 250);
                window.addEventListener("resize", resizeHandler);

                // Store cleanup function
                map._cleanup = function () {
                    window.removeEventListener("resize", resizeHandler);
                };

            } catch (err) {
                console.error("[DriverMap] Initialization failed:", err);
                reject(err);
            }
        });
    }

    // ============================================================
    // LAYER SETUP
    // ============================================================
    function setupMapLayers() {
        if (!map || !map.loaded()) return;

        // Check if we're using the minimal inline style (no glyphs, no reference layers)
        var style = map.getStyle();
        var hasGlyphs = style && style.glyphs;
        var hasWaterwayLabel = style && style.layers && style.layers.some(function(l) { return l.id === "waterway-label"; });
        var isMinimalStyle = !hasGlyphs || !hasWaterwayLabel;

        // 1. Heatmap source & layer (stub - empty GeoJSON initially)
        // Only add if style has waterway-label reference layer
        if (!isMinimalStyle) {
            if (!map.getSource(heatmapSourceId)) {
                map.addSource(heatmapSourceId, {
                    type: "geojson",
                    data: { type: "FeatureCollection", features: [] }
                });
            }

            if (!map.getLayer(heatmapLayerId)) {
                map.addLayer({
                    id: heatmapLayerId,
                    type: "heatmap",
                    source: heatmapSourceId,
                    maxzoom: HEATMAP_CONFIG.maxZoom,
                    paint: {
                        "heatmap-radius": HEATMAP_CONFIG.radius,
                        "heatmap-opacity": HEATMAP_CONFIG.opacity,
                        "heatmap-intensity": HEATMAP_CONFIG.intensity,
                        "heatmap-weight": ["get", "demand"],
                        "heatmap-color": [
                            "interpolate", ["linear"], ["heatmap-density"],
                            0, "rgba(0,0,255,0)",
                            0.2, "rgb(0, 255, 255)",
                            0.4, "rgb(0, 255, 0)",
                            0.6, "rgb(255, 255, 0)",
                            0.8, "rgb(255, 128, 0)",
                            1, "rgb(255, 0, 0)"
                        ]
                    }
                }, "waterway-label"); // Insert before labels
            }
        } else {
            console.log("[DriverMap] Skipping heatmap layer - minimal style detected");
        }

        // 2. Surge badges source & layer
        // Only add if style has glyphs (required for text-field)
        if (!isMinimalStyle && hasGlyphs) {
            if (!map.getSource(surgeSourceId)) {
                map.addSource(surgeSourceId, {
                    type: "geojson",
                    data: { type: "FeatureCollection", features: [] }
                });
            }

            if (!map.getLayer(surgeLayerId)) {
                map.addLayer({
                    id: surgeLayerId,
                    type: "symbol",
                    source: surgeSourceId,
                    minzoom: SURGE_CONFIG.minZoom,
                    layout: {
                        "text-field": ["concat", ["get", "multiplier"], "×"],
                        "text-font": ["DIN Offc Pro Medium", "Arial Unicode MS Bold"],
                        "text-size": 14,
                        "text-offset": [0, -1.5],
                        "text-anchor": "top",
                        "icon-image": "surge-badge",
                        "icon-size": 1,
                        "icon-allow-overlap": true,
                        "icon-ignore-placement": true
                    },
                    paint: {
                        "text-color": "#ffffff",
                        "text-halo-color": "#dc3545",
                        "text-halo-width": 2,
                        "text-halo-blur": 1
                    }
                });
            }
        } else {
            console.log("[DriverMap] Skipping surge badges layer - minimal style or no glyphs");
        }

        // 3. Request pins source & layer
        if (!map.getSource(requestPinsSourceId)) {
            map.addSource(requestPinsSourceId, {
                type: "geojson",
                data: { type: "FeatureCollection", features: [] }
            });
        }

        if (!map.getLayer(requestPinsLayerId)) {
            map.addLayer({
                id: requestPinsLayerId,
                type: "symbol",
                source: requestPinsSourceId,
                layout: {
                    "icon-image": "request-pin",
                    "icon-size": 1,
                    "icon-allow-overlap": true,
                    "icon-ignore-placement": true
                }
            });
        }

        // Add custom marker images
        addCustomMarkerImages();
    }

    function addCustomMarkerImages() {
        // Surge badge - red circle with white text
        if (!map.hasImage("surge-badge")) {
            var surgeCanvas = document.createElement("canvas");
            surgeCanvas.width = 48;
            surgeCanvas.height = 48;
            var ctx = surgeCanvas.getContext("2d");
            ctx.beginPath();
            ctx.arc(24, 24, 20, 0, Math.PI * 2);
            ctx.fillStyle = "#dc3545";
            ctx.fill();
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 2;
            ctx.stroke();
            map.addImage("surge-badge", surgeCanvas, { pixelRatio: 2 });
        }

        // Request pin - blue pin with pulse
        if (!map.hasImage("request-pin")) {
            var pinCanvas = document.createElement("canvas");
            pinCanvas.width = 48;
            pinCanvas.height = 48;
            var pctx = pinCanvas.getContext("2d");
            pctx.beginPath();
            pctx.moveTo(24, 4);
            pctx.bezierCurveTo(24, 4, 4, 4, 4, 24);
            pctx.bezierCurveTo(4, 24, 24, 44, 24, 44);
            pctx.bezierCurveTo(24, 44, 44, 24, 44, 24);
            pctx.bezierCurveTo(44, 24, 24, 4, 24, 4);
            pctx.fillStyle = "#2563eb";
            pctx.fill();
            pctx.strokeStyle = "#ffffff";
            pctx.lineWidth = 2;
            pctx.stroke();
            // Inner white circle
            pctx.beginPath();
            pctx.arc(24, 24, 8, 0, Math.PI * 2);
            pctx.fillStyle = "#ffffff";
            pctx.fill();
            map.addImage("request-pin", pinCanvas, { pixelRatio: 2 });
        }
    }

    // ============================================================
    // DRIVER LOCATION
    // ============================================================
    function updateDriverLocation(lat, lng, accuracy, heading) {
        if (!map || !isMapReady) {
            currentDriverLocation = { lat: lat, lng: lng, accuracy: accuracy, heading: heading };
            return;
        }

        var coords = [lng, lat];
        currentDriverLocation = { lat: lat, lng: lng, accuracy: accuracy, heading: heading };

        // Create or update driver marker (blue pulsing dot)
        if (!driverMarker) {
            var markerEl = createElement("div", "driver-marker");
            markerEl.innerHTML = '<div class="driver-pulse"></div><div class="driver-dot"></div>';
            driverMarker = new maplibregl.Marker({ element: markerEl, anchor: "center" })
                .setLngLat(coords)
                .addTo(map);
        } else {
            driverMarker.setLngLat(coords);
        }

        // Update heading if provided
        if (typeof heading === "number" && driverMarker._element) {
            driverMarker._element.style.transform = "rotate(" + heading + "deg)";
        }

        // Optional: pan to driver location on first fix
        if (map.getZoom() < 14) {
            map.flyTo({ center: coords, zoom: 15, duration: 1500, essential: true });
        }
    }

    function startDriverPulse() {
        if (!driverMarker || !driverMarker._element) return;
        var pulseEl = driverMarker._element.querySelector(".driver-pulse");
        if (pulseEl) {
            pulseEl.style.animation = "driver-pulse 2s ease-out infinite";
        }
    }

    function stopDriverPulse() {
        if (!driverMarker || !driverMarker._element) return;
        var pulseEl = driverMarker._element.querySelector(".driver-pulse");
        if (pulseEl) {
            pulseEl.style.animation = "none";
        }
    }

    // ============================================================
    // HEATMAP (DEMAND VISUALIZATION)
    // ============================================================
    function updateHeatmap(geojsonData) {
        if (!map || !map.loaded()) return;
        var source = map.getSource(heatmapSourceId);
        if (source) {
            source.setData(geojsonData);
        }
    }

    function clearHeatmap() {
        updateHeatmap({ type: "FeatureCollection", features: [] });
    }

    // Stub: generate mock heatmap data for demo
    function generateMockHeatmap(center, count) {
        var features = [];
        for (var i = 0; i < count; i++) {
            var offsetLat = (Math.random() - 0.5) * 0.02; // ~1km
            var offsetLng = (Math.random() - 0.5) * 0.02;
            var demand = Math.random() * 10 + 1;
            features.push({
                type: "Feature",
                geometry: { type: "Point", coordinates: [center[0] + offsetLng, center[1] + offsetLat] },
                properties: { demand: demand, timestamp: Date.now() }
            });
        }
        return { type: "FeatureCollection", features: features };
    }

    // ============================================================
    // SURGE BADGES
    // ============================================================
    function updateSurgeBadges(surgeZones) {
        if (!map || !map.loaded()) return;
        var features = surgeZones.map(function (zone) {
            return {
                type: "Feature",
                geometry: { type: "Point", coordinates: [zone.lng, zone.lat] },
                properties: { multiplier: zone.multiplier.toFixed(1) }
            };
        });
        var source = map.getSource(surgeSourceId);
        if (source) {
            source.setData({ type: "FeatureCollection", features: features });
        }
    }

    function clearSurgeBadges() {
        updateSurgeBadges([]);
    }

    // ============================================================
    // REQUEST PINS (NEARBY OFFERS)
    // ============================================================
    function updateRequestPins(requests) {
        if (!map || !map.loaded()) return;
        var features = requests.map(function (req) {
            return {
                type: "Feature",
                geometry: { type: "Point", coordinates: [req.lng, req.lat] },
                properties: {
                    id: req.id,
                    pickup: req.pickup,
                    dropoff: req.dropoff,
                    fare: req.fare,
                    distance: req.distance,
                    ttl: req.ttl
                }
            };
        });
        var source = map.getSource(requestPinsSourceId);
        if (source) {
            source.setData({ type: "FeatureCollection", features: features });
        }
    }

    function clearRequestPins() {
        updateRequestPins([]);
    }

    // ============================================================
    // MAP CONTROLS
    // ============================================================
    function centerOnDriver() {
        if (!map || !currentDriverLocation) return;
        map.flyTo({
            center: [currentDriverLocation.lng, currentDriverLocation.lat],
            zoom: 15,
            duration: 1000,
            essential: true
        });
    }

    function setMapStyle(styleUrl) {
        if (!map) return;
        map.setStyle(styleUrl).once("style.load", function () {
            setupMapLayers();
            if (currentDriverLocation) {
                updateDriverLocation(currentDriverLocation.lat, currentDriverLocation.lng, currentDriverLocation.accuracy, currentDriverLocation.heading);
            }
        });
    }

    function destroyMap() {
        if (map) {
            if (map._cleanup) map._cleanup();
            if (animationFrameId) cancelAnimationFrame(animationFrameId);
            map.remove();
            map = null;
            driverMarker = null;
            driverPulseMarker = null;
            currentDriverLocation = null;
            isMapReady = false;
        }
    }

    function getMap() {
        return map;
    }

    function isReady() {
        return isMapReady && map && map.loaded();
    }

    // ============================================================
    // PUBLIC API
    // ============================================================
    window.DriverMap = {
        init: initMap,
        updateDriverLocation: updateDriverLocation,
        startDriverPulse: startDriverPulse,
        stopDriverPulse: stopDriverPulse,
        updateHeatmap: updateHeatmap,
        clearHeatmap: clearHeatmap,
        generateMockHeatmap: generateMockHeatmap,
        updateSurgeBadges: updateSurgeBadges,
        clearSurgeBadges: clearSurgeBadges,
        updateRequestPins: updateRequestPins,
        clearRequestPins: clearRequestPins,
        centerOnDriver: centerOnDriver,
        setStyle: setMapStyle,
        destroy: destroyMap,
        getMap: getMap,
        isReady: isReady,
        // Expose config for external tuning
        CONFIG: MAP_CONFIG
    };

    // Auto-initialize if container exists on DOMContentLoaded
    document.addEventListener("DOMContentLoaded", function () {
        var container = document.getElementById("driverMap");
        if (container && !container.dataset.mapInitialized) {
            container.dataset.mapInitialized = "1";
            initMap(container).catch(function (err) {
                console.warn("[DriverMap] Auto-init failed:", err.message);
            });
        }
    });

    // Expose globally for inline script usage
    window.DriverMap = DriverMap;

})();