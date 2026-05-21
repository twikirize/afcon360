// Configuration
let map;
let markers = [];
let currentProperties = [];
let currentBounds = null;
let currentFilters = {
    property_type: 'all',
    sort_by: 'relevance',
    min_price: null,
    max_price: null,
    min_rating: 0
};
let currentPage = 1;
let isLoading = false;
let hasMore = true;

// Initialize map
function initMap() {
    map = L.map('exploreMap').setView([0.3136, 32.5811], 12); // Kampala center
    
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; CartoDB',
        subdomains: 'abcd',
        maxZoom: 19,
        minZoom: 3
    }).addTo(map);
    
    map.on('moveend', function() {
        updateResultsFromMap();
    });
}

// Get current map bounds
function getMapBounds() {
    const bounds = map.getBounds();
    return {
        min_lat: bounds.getSouthWest().lat,
        max_lat: bounds.getNorthEast().lat,
        min_lng: bounds.getSouthWest().lng,
        max_lng: bounds.getNorthEast().lng
    };
}

// Update results from map view
let searchTimeout;
function updateResultsFromMap() {
    if (searchTimeout) clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        currentPage = 1;
        hasMore = true;
        fetchProperties();
    }, 300);
}

// Fetch properties from API
async function fetchProperties() {
    if (isLoading) return;
    isLoading = true;
    
    showLoading();
    
    const bounds = getMapBounds();
    const city = document.getElementById('cityInput').value;
    const checkIn = document.getElementById('checkIn').value;
    const checkOut = document.getElementById('checkOut').value;
    const guests = document.getElementById('guests').value;
    
    const params = new URLSearchParams();
    params.append('min_lat', bounds.min_lat);
    params.append('max_lat', bounds.max_lat);
    params.append('min_lng', bounds.min_lng);
    params.append('max_lng', bounds.max_lng);
    if (city) params.append('city', city);
    if (checkIn) params.append('check_in', checkIn);
    if (checkOut) params.append('check_out', checkOut);
    if (guests) params.append('guests', guests);
    params.append('property_type', currentFilters.property_type);
    params.append('sort_by', currentFilters.sort_by);
    if (currentFilters.min_price) params.append('min_price', currentFilters.min_price);
    if (currentFilters.max_price) params.append('max_price', currentFilters.max_price);
    if (currentFilters.min_rating) params.append('min_rating', currentFilters.min_rating);
    params.append('page', currentPage);
    
    try {
        const response = await fetch(`/accommodation/api/explore/search?${params.toString()}`);
        const data = await response.json();
        
        if (data.success) {
            if (currentPage === 1) {
                currentProperties = data.properties;
                updateMarkers(data.properties);
                updateResultsList(data.properties);
            } else {
                currentProperties = [...currentProperties, ...data.properties];
                addMarkers(data.properties);
                appendResultsList(data.properties);
            }
            
            document.getElementById('resultsCount').innerText = 
                `${data.total} properties found`;
            
            hasMore = data.has_more;
        }
    } catch (error) {
        console.error('Error fetching properties:', error);
        document.getElementById('resultsList').innerHTML = `
            <div class="empty-state">
                <i class="fas fa-exclamation-triangle"></i>
                <p>Error loading properties. Please try again.</p>
            </div>
        `;
    } finally {
        isLoading = false;
        hideLoading();
    }
}

// Update map markers (replace all)
function updateMarkers(properties) {
    // Clear existing markers
    markers.forEach(marker => map.removeLayer(marker));
    markers = [];
    
    properties.forEach(property => {
        if (property.latitude && property.longitude) {
            addMarker(property);
        }
    });
}

// Add markers (incremental)
function addMarkers(properties) {
    properties.forEach(property => {
        if (property.latitude && property.longitude && 
            !markers.some(m => m.options.propertyId === property.id)) {
            addMarker(property);
        }
    });
}

// Add single marker
function addMarker(property) {
    const markerColor = getMarkerColor(property.property_type);
    const icon = L.divIcon({
        className: 'custom-marker',
        html: `<div style="background: ${markerColor}; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; box-shadow: 0 2px 6px rgba(0,0,0,0.3);">${property.price}</div>`,
        iconSize: [28, 28],
        popupAnchor: [0, -14]
    });
    
    const marker = L.marker([property.latitude, property.longitude], { icon: icon, propertyId: property.id })
        .bindPopup(`
            <div class="custom-popup">
                <div class="popup-title">${escapeHtml(property.name)}</div>
                <div class="popup-price">${property.currency_symbol || '$'}${property.price}/night</div>
                <div>⭐ ${property.rating || 'New'}</div>
                <a href="/accommodation/guest/${property.slug || property.id}" target="_blank">View Details →</a>
            </div>
        `)
        .addTo(map);
    
    marker.options.propertyId = property.id;
    markers.push(marker);
}

// Get marker color based on property type
function getMarkerColor(propertyType) {
    const colors = {
        'hotel_room': '#2d5a2d',
        'entire_place': '#3498db',
        'private_room': '#e67e22',
        'shared_room': '#95a5a6'
    };
    return colors[propertyType] || '#2d5a2d';
}

// Update results list
function updateResultsList(properties) {
    const container = document.getElementById('resultsList');
    container.innerHTML = properties.map(property => renderPropertyCard(property)).join('');
}

// Append to results list
function appendResultsList(properties) {
    const container = document.getElementById('resultsList');
    container.insertAdjacentHTML('beforeend', properties.map(property => renderPropertyCard(property)).join(''));
}

// Render property card HTML
function renderPropertyCard(property) {
    const rating = property.rating || 0;
    const ratingText = rating >= 4.5 ? 'Exceptional' : rating >= 4 ? 'Excellent' : rating >= 3 ? 'Good' : 'New';
    const isWishlisted = property.is_wishlisted ? 'active' : '';
    
    return `
        <div class="property-card" data-id="${property.id}" onclick="goToDetail(${property.id}, '${property.slug}')">
            <div class="property-card-img">
                <img src="${property.images && property.images[0] ? property.images[0] : '/static/images/no-image.png'}" 
                     alt="${escapeHtml(property.name)}"
                     onerror="this.src='/static/images/no-image.png'">
                <button class="wishlist-btn ${isWishlisted}" onclick="toggleWishlist(event, ${property.id})">
                    <svg viewBox="0 0 24 24" stroke-width="2">
                        <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                    </svg>
                </button>
            </div>
            <div class="property-card-body">
                <div class="property-card-type">${getPropertyTypeLabel(property.property_type)}</div>
                <div class="property-card-title">${escapeHtml(property.name)}</div>
                <div class="property-card-location">📍 ${escapeHtml(property.city)}${property.country ? `, ${property.country}` : ''}</div>
                <div class="property-card-rating">
                    ${rating > 0 ? `
                        <span class="rating-badge">${rating.toFixed(1)}</span>
                        <span class="rating-text">${ratingText}</span>
                        <span class="review-count">(${property.reviews || 0} reviews)</span>
                    ` : '<span class="rating-text">New property</span>'}
                </div>
                <div class="property-card-price">
                    <div>
                        <span class="price-amount">${property.currency_symbol || '$'}${property.price}</span>
                        <span class="price-night">/ night</span>
                    </div>
                    <button class="view-detail-btn" onclick="goToDetail(event, ${property.id}, '${property.slug}')">View →</button>
                </div>
            </div>
        </div>
    `;
}

// Helper functions
function getPropertyTypeLabel(type) {
    const labels = {
        'hotel_room': '🏨 Hotel',
        'entire_place': '🏠 Entire home',
        'private_room': '🔑 Private room',
        'shared_room': '🛌 Shared room'
    };
    return labels[type] || '🏠 Accommodation';
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function goToDetail(event, id, slug) {
    if (event && event.stopPropagation) event.stopPropagation();
    window.location.href = `/accommodation/guest/${slug || id}`;
}

// Filter functions
function setPropertyType(type) {
    currentFilters.property_type = type;
    currentPage = 1;
    hasMore = true;
    
    document.querySelectorAll('.filter-chip[data-type]').forEach(el => {
        el.classList.remove('active');
        if (el.dataset.type === type) el.classList.add('active');
    });
    
    fetchProperties();
}

function setSort(sort) {
    currentFilters.sort_by = sort;
    currentPage = 1;
    hasMore = true;
    
    document.getElementById('sortSelect').value = sort;
    document.querySelectorAll('.filter-chip[data-sort]').forEach(el => {
        el.classList.remove('active');
        if (el.dataset.sort === sort) el.classList.add('active');
    });
    
    fetchProperties();
}

function handleSortChange() {
    setSort(document.getElementById('sortSelect').value);
}

function setMinRating(rating) {
    currentFilters.min_rating = rating;
    currentPage = 1;
    hasMore = true;
    
    document.querySelectorAll('.filter-chip[data-rating]').forEach(el => {
        el.classList.remove('active');
        if (parseFloat(el.dataset.rating) === rating) el.classList.add('active');
    });
    
    fetchProperties();
}

function applyPriceFilter() {
    const minPrice = document.getElementById('minPrice').value;
    const maxPrice = document.getElementById('maxPrice').value;
    
    currentFilters.min_price = minPrice ? parseFloat(minPrice) : null;
    currentFilters.max_price = maxPrice ? parseFloat(maxPrice) : null;
    currentPage = 1;
    hasMore = true;
    
    fetchProperties();
}

async function toggleWishlist(event, propertyId) {
    event.stopPropagation();
    
    const btn = event.currentTarget;
    const isActive = btn.classList.contains('active');
    const method = isActive ? 'DELETE' : 'POST';
    
    try {
        const response = await fetch(`/accommodation/api/explore/wishlist/${propertyId}`, {
            method: method,
            headers: {
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            }
        });
        
        if (response.ok) {
            if (isActive) {
                btn.classList.remove('active');
            } else {
                btn.classList.add('active');
            }
        }
    } catch (error) {
        console.error('Error toggling wishlist:', error);
    }
}

function handleSearch(event) {
    event.preventDefault();
    currentPage = 1;
    hasMore = true;
    fetchProperties();
}

// Loading states
function showLoading() {
    // handled by fetch
}

function hideLoading() {
    // handled by fetch
}

// Infinite scroll
const resultsList = document.getElementById('resultsList');
resultsList.addEventListener('scroll', function() {
    if (isLoading || !hasMore) return;
    
    const scrollTop = this.scrollTop;
    const scrollHeight = this.scrollHeight;
    const clientHeight = this.clientHeight;
    
    if (scrollTop + clientHeight >= scrollHeight - 200) {
        currentPage++;
        fetchProperties();
    }
});

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    initMap();
});