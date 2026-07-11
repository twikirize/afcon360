# Real-Time Competitive Price Intelligence - Beyond OTA Standards
import asyncio
import aiohttp
import json
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import logging
import numpy as np

logger = logging.getLogger(__name__)

class CompetitorType(Enum):
    DIRECT_COMPETITOR = "direct_competitor"  # Same area, similar property
    INDIRECT_COMPETITOR = "indirect_competitor"  # Same area, different type
    MARKET_COMPETITOR = "market_competitor"  # Broader market
    PREMIUM_COMPETITOR = "premium_competitor"  # Higher-end properties
    BUDGET_COMPETITOR = "budget_competitor"  # Lower-end properties

class PricePosition(Enum):
    SIGNIFICANTLY_UNDER = "significantly_under"  # >20% below market
    SLIGHTLY_UNDER = "slightly_under"  # 5-20% below market
    AT_MARKET = "at_market"  # ±5% of market
    SLIGHTLY_OVER = "slightly_over"  # 5-20% above market
    SIGNIFICANTLY_OVER = "significantly_over"  # >20% above market

@dataclass
class CompetitorProperty:
    id: str
    name: str
    platform: str  # "booking.com", "hotels.com", "airbnb", etc.
    url: str
    price: float
    currency: str
    rating: float
    amenities: List[str]
    location: Dict[str, float]  # lat, lng
    property_type: str
    max_guests: int
    last_updated: datetime
    availability: Dict[str, bool]  # date -> available

@dataclass
class MarketIntelligence:
    property_id: int
    market_position: PricePosition
    competitor_count: int
    average_market_price: float
    price_gap_percentage: float
    recommended_price_range: Tuple[float, float]
    market_trends: Dict[str, float]
    competitive_insights: List[str]
    opportunity_score: float  # 0-1

class CompetitiveIntelligenceService:
    """
    Revolutionary competitive intelligence system that monitors competitor
    pricing in real-time and provides strategic pricing recommendations
    """
    
    def __init__(self):
        self.competitors_cache = {}
        self.price_history = {}
        self.market_trends = {}
        self.api_clients = {
            "booking.com": BookingComAPIClient(),
            "hotels.com": HotelsComAPIClient(),
            "airbnb": AirbnbAPIClient(),
            "expedia": ExpediaAPIClient()
        }
    
    async def get_real_time_intelligence(self, property_id: int, property_data: Dict, 
                                       check_in: date, check_out: date) -> MarketIntelligence:
        """
        Get comprehensive competitive intelligence in real-time
        """
        
        # Identify competitors
        competitors = await self._identify_competitors(property_id, property_data, check_in, check_out)
        
        # Gather competitor pricing
        competitor_pricing = await self._gather_competitor_pricing(competitors, check_in, check_out)
        
        # Analyze market position
        market_position = self._analyze_market_position(property_data, competitor_pricing)
        
        # Calculate market statistics
        market_stats = self._calculate_market_statistics(competitor_pricing)
        
        # Identify market trends
        trends = self._analyze_market_trends(property_id, competitor_pricing)
        
        # Generate competitive insights
        insights = self._generate_competitive_insights(property_data, competitor_pricing, market_position)
        
        # Calculate opportunity score
        opportunity_score = self._calculate_opportunity_score(market_position, trends, insights)
        
        # Recommend price range
        price_range = self._recommend_price_range(property_data, market_stats, trends)
        
        return MarketIntelligence(
            property_id=property_id,
            market_position=market_position,
            competitor_count=len(competitors),
            average_market_price=market_stats["average_price"],
            price_gap_percentage=market_stats["price_gap_percentage"],
            recommended_price_range=price_range,
            market_trends=trends,
            competitive_insights=insights,
            opportunity_score=opportunity_score
        )
    
    async def _identify_competitors(self, property_id: int, property_data: Dict, 
                                  check_in: date, check_out: date) -> List[CompetitorProperty]:
        """Identify relevant competitors using AI and location analysis"""
        
        competitors = []
        
        # Get location coordinates
        property_lat = property_data.get("latitude")
        property_lng = property_data.get("longitude")
        property_city = property_data.get("city")
        
        # Search across multiple platforms
        search_tasks = []
        
        for platform, client in self.api_clients.items():
            task = self._search_platform_competitors(
                client, property_city, property_lat, property_lng, 
                property_data, check_in, check_out
            )
            search_tasks.append(task)
        
        # Execute searches concurrently
        platform_results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # Process results
        for result in platform_results:
            if isinstance(result, Exception):
                logger.error(f"Platform search failed: {result}")
                continue
            
            competitors.extend(result)
        
        # Filter and categorize competitors
        filtered_competitors = self._filter_competitors(competitors, property_data)
        
        return filtered_competitors
    
    async def _search_platform_competitors(self, client, city: str, lat: float, lng: float,
                                         property_data: Dict, check_in: date, check_out: date) -> List[CompetitorProperty]:
        """Search for competitors on a specific platform"""
        
        try:
            # Build search query
            search_params = {
                "city": city,
                "check_in": check_in.strftime("%Y-%m-%d"),
                "check_out": check_out.strftime("%Y-%m-%d"),
                "guests": property_data.get("max_guests", 2),
                "radius_km": 5,  # Search within 5km
                "property_type": property_data.get("property_type", "any")
            }
            
            # Execute search
            results = await client.search_properties(search_params)
            
            # Convert to CompetitorProperty objects
            competitors = []
            for result in results:
                competitor = CompetitorProperty(
                    id=result["id"],
                    name=result["name"],
                    platform=client.platform_name,
                    url=result["url"],
                    price=result["price"],
                    currency=result["currency"],
                    rating=result.get("rating", 0),
                    amenities=result.get("amenities", []),
                    location=result.get("location", {"lat": 0, "lng": 0}),
                    property_type=result.get("property_type", ""),
                    max_guests=result.get("max_guests", 2),
                    last_updated=datetime.now(),
                    availability=result.get("availability", {})
                )
                competitors.append(competitor)
            
            return competitors
            
        except Exception as e:
            logger.error(f"Error searching {client.platform_name}: {e}")
            return []
    
    def _filter_competitors(self, competitors: List[CompetitorProperty], property_data: Dict) -> List[CompetitorProperty]:
        """Filter competitors based on relevance"""
        
        filtered = []
        
        for competitor in competitors:
            # Distance filter (within 10km)
            if self._calculate_distance(property_data, competitor) > 10:
                continue
            
            # Price range filter (±50% of property price)
            property_price = property_data.get("price", 100)
            if competitor.price < property_price * 0.5 or competitor.price > property_price * 1.5:
                continue
            
            # Guest capacity filter (±50% of property capacity)
            property_guests = property_data.get("max_guests", 2)
            if competitor.max_guests < property_guests * 0.5 or competitor.max_guests > property_guests * 1.5:
                continue
            
            filtered.append(competitor)
        
        # Sort by relevance (distance + price similarity)
        filtered.sort(key=lambda c: self._calculate_relevance_score(property_data, c), reverse=True)
        
        return filtered[:20]  # Return top 20 most relevant competitors
    
    async def _gather_competitor_pricing(self, competitors: List[CompetitorProperty], 
                                      check_in: date, check_out: date) -> Dict[str, float]:
        """Gather current pricing from all competitors"""
        
        pricing_data = {}
        
        # Batch pricing requests
        pricing_tasks = []
        
        for competitor in competitors:
            task = self._get_competitor_pricing(competitor, check_in, check_out)
            pricing_tasks.append(task)
        
        # Execute pricing requests concurrently
        pricing_results = await asyncio.gather(*pricing_tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(pricing_results):
            competitor = competitors[i]
            
            if isinstance(result, Exception):
                logger.error(f"Pricing failed for {competitor.name}: {result}")
                continue
            
            pricing_data[competitor.id] = result
        
        return pricing_data
    
    async def _get_competitor_pricing(self, competitor: CompetitorProperty, 
                                    check_in: date, check_out: date) -> float:
        """Get current pricing for specific competitor"""
        
        try:
            client = self.api_clients.get(competitor.platform)
            if not client:
                return competitor.price  # Fallback to cached price
            
            # Get real-time pricing
            pricing = await client.get_property_pricing(
                competitor.id, check_in, check_out
            )
            
            return pricing
            
        except Exception as e:
            logger.error(f"Error getting pricing for {competitor.name}: {e}")
            return competitor.price  # Fallback to cached price
    
    def _analyze_market_position(self, property_data: Dict, competitor_pricing: Dict[str, float]) -> PricePosition:
        """Analyze property's position in the market"""
        
        if not competitor_pricing:
            return PricePosition.AT_MARKET
        
        property_price = property_data.get("price", 100)
        competitor_prices = list(competitor_pricing.values())
        
        # Calculate market statistics
        avg_market_price = np.mean(competitor_prices)
        price_gap_percentage = ((property_price - avg_market_price) / avg_market_price) * 100
        
        # Determine position
        if price_gap_percentage < -20:
            return PricePosition.SIGNIFICANTLY_UNDER
        elif price_gap_percentage < -5:
            return PricePosition.SLIGHTLY_UNDER
        elif price_gap_percentage <= 5:
            return PricePosition.AT_MARKET
        elif price_gap_percentage <= 20:
            return PricePosition.SLIGHTLY_OVER
        else:
            return PricePosition.SIGNIFICANTLY_OVER
    
    def _calculate_market_statistics(self, competitor_pricing: Dict[str, float]) -> Dict:
        """Calculate market statistics"""
        
        if not competitor_pricing:
            return {
                "average_price": 0,
                "median_price": 0,
                "price_range": (0, 0),
                "price_gap_percentage": 0
            }
        
        prices = list(competitor_pricing.values())
        
        return {
            "average_price": np.mean(prices),
            "median_price": np.median(prices),
            "min_price": np.min(prices),
            "max_price": np.max(prices),
            "price_range": (np.min(prices), np.max(prices)),
            "price_gap_percentage": 0  # Will be calculated by caller
        }
    
    def _analyze_market_trends(self, property_id: int, competitor_pricing: Dict[str, float]) -> Dict[str, float]:
        """Analyze market trends"""
        
        trends = {}
        
        # Get historical pricing data
        historical_data = self._get_historical_pricing(property_id)
        
        if historical_data:
            # Calculate price trends
            recent_prices = list(historical_data.values())[-7:]  # Last 7 days
            if len(recent_prices) > 1:
                price_trend = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
                trends["price_trend"] = price_trend
            else:
                trends["price_trend"] = 0.0
        
        # Analyze competitor price movements
        competitor_trends = self._analyze_competitor_trends(competitor_pricing)
        trends.update(competitor_trends)
        
        # Market demand trends
        demand_trends = self._analyze_demand_trends(property_id)
        trends.update(demand_trends)
        
        return trends
    
    def _generate_competitive_insights(self, property_data: Dict, competitor_pricing: Dict[str, float],
                                     market_position: PricePosition) -> List[str]:
        """Generate actionable competitive insights"""
        
        insights = []
        
        # Price positioning insights
        if market_position == PricePosition.SIGNIFICANTLY_UNDER:
            insights.append("Your pricing is significantly below market - opportunity to increase rates")
        elif market_position == PricePosition.SIGNIFICANTLY_OVER:
            insights.append("Your pricing is significantly above market - risk of losing bookings")
        elif market_position == PricePosition.AT_MARKET:
            insights.append("Your pricing is well-positioned relative to competitors")
        
        # Competitive density insights
        competitor_count = len(competitor_pricing)
        if competitor_count > 15:
            insights.append("High competition in your area - differentiation is key")
        elif competitor_count < 5:
            insights.append("Low competition - opportunity to capture market share")
        
        # Price distribution insights
        if competitor_pricing:
            prices = list(competitor_pricing.values())
            price_std = np.std(prices)
            
            if price_std > 30:
                insights.append("High price variance in market - consider positioning strategy")
            else:
                insights.append("Stable pricing in market - competitive pricing effective")
        
        # Value proposition insights
        property_rating = property_data.get("rating", 0)
        if property_rating > 4.5 and market_position in [PricePosition.AT_MARKET, PricePosition.SLIGHTLY_UNDER]:
            insights.append("High rating with competitive pricing - strong value proposition")
        elif property_rating < 3.5 and market_position in [PricePosition.SLIGHTLY_OVER, PricePosition.SIGNIFICANTLY_OVER]:
            insights.append("Lower rating with premium pricing - consider improvements or price adjustment")
        
        return insights
    
    def _calculate_opportunity_score(self, market_position: PricePosition, trends: Dict[str, float],
                                  insights: List[str]) -> float:
        """Calculate opportunity score based on market position and trends"""
        
        score = 0.5  # Base score
        
        # Market position scoring
        position_scores = {
            PricePosition.SIGNIFICANTLY_UNDER: 0.8,  # High opportunity to increase
            PricePosition.SLIGHTLY_UNDER: 0.7,
            PricePosition.AT_MARKET: 0.6,
            PricePosition.SLIGHTLY_OVER: 0.4,
            PricePosition.SIGNIFICANTLY_OVER: 0.2  # Low opportunity, high risk
        }
        score += position_scores.get(market_position, 0.5) * 0.3
        
        # Trend scoring
        price_trend = trends.get("price_trend", 0)
        if price_trend > 0.05:  # Rising market
            score += 0.2
        elif price_trend < -0.05:  # Falling market
            score -= 0.1
        
        # Insight scoring
        positive_insights = sum(1 for insight in insights if "opportunity" in insight.lower())
        score += (positive_insights / len(insights)) * 0.2 if insights else 0
        
        return min(score, 1.0)
    
    def _recommend_price_range(self, property_data: Dict, market_stats: Dict, trends: Dict[str, float]) -> Tuple[float, float]:
        """Recommend optimal price range"""
        
        current_price = property_data.get("price", 100)
        avg_market_price = market_stats.get("average_price", current_price)
        
        # Base range around market average
        base_range = 0.2  # ±20%
        
        # Adjust based on trends
        price_trend = trends.get("price_trend", 0)
        if price_trend > 0.05:  # Rising market
            base_range = 0.25  # ±25%
        elif price_trend < -0.05:  # Falling market
            base_range = 0.15  # ±15%
        
        # Calculate range
        min_price = avg_market_price * (1 - base_range)
        max_price = avg_market_price * (1 + base_range)
        
        # Adjust for property quality
        property_rating = property_data.get("rating", 3.0)
        if property_rating > 4.5:
            max_price *= 1.1  # Premium properties can charge more
        elif property_rating < 3.0:
            max_price *= 0.9  # Lower-rated properties should be more competitive
        
        return (round(min_price, 2), round(max_price, 2))
    
    # Helper methods
    def _calculate_distance(self, property_data: Dict, competitor: CompetitorProperty) -> float:
        """Calculate distance between property and competitor"""
        
        lat1 = property_data.get("latitude", 0)
        lng1 = property_data.get("longitude", 0)
        lat2 = competitor.location.get("lat", 0)
        lng2 = competitor.location.get("lng", 0)
        
        # Simplified distance calculation (would use proper geodesic formula)
        return ((lat1 - lat2) ** 2 + (lng1 - lng2) ** 2) ** 0.5 * 111  # Rough km conversion
    
    def _calculate_relevance_score(self, property_data: Dict, competitor: CompetitorProperty) -> float:
        """Calculate relevance score for competitor"""
        
        score = 0.0
        
        # Distance relevance
        distance = self._calculate_distance(property_data, competitor)
        distance_score = max(0, 1 - distance / 10)  # Normalize to 0-1
        score += distance_score * 0.4
        
        # Price similarity
        property_price = property_data.get("price", 100)
        price_diff = abs(competitor.price - property_price) / property_price
        price_score = max(0, 1 - price_diff)
        score += price_score * 0.3
        
        # Capacity similarity
        property_guests = property_data.get("max_guests", 2)
        guest_diff = abs(competitor.max_guests - property_guests) / property_guests
        guest_score = max(0, 1 - guest_diff)
        score += guest_score * 0.2
        
        # Rating similarity
        property_rating = property_data.get("rating", 3.0)
        rating_diff = abs(competitor.rating - property_rating)
        rating_score = max(0, 1 - rating_diff / 2)
        score += rating_score * 0.1
        
        return score
    
    def _get_historical_pricing(self, property_id: int) -> Dict:
        """Get historical pricing data"""
        return self.price_history.get(property_id, {})
    
    def _analyze_competitor_trends(self, competitor_pricing: Dict[str, float]) -> Dict[str, float]:
        """Analyze competitor pricing trends"""
        return {"competitor_volatility": 0.1}  # Mock data
    
    def _analyze_demand_trends(self, property_id: int) -> Dict[str, float]:
        """Analyze demand trends"""
        return {"demand_trend": 0.05}  # Mock data


# API Client Classes (simplified for demo)
class BookingComAPIClient:
    platform_name = "booking.com"
    
    async def search_properties(self, params: Dict) -> List[Dict]:
        """Search properties on Booking.com"""
        # Mock implementation
        return [
            {
                "id": "bc_123",
                "name": "Competitor Hotel 1",
                "url": "https://booking.com/hotel/123",
                "price": 120.0,
                "currency": "USD",
                "rating": 4.2,
                "amenities": ["wifi", "pool"],
                "location": {"lat": 0.0, "lng": 0.0},
                "property_type": "hotel",
                "max_guests": 2
            }
        ]
    
    async def get_property_pricing(self, property_id: str, check_in: date, check_out: date) -> float:
        """Get property pricing"""
        return 120.0  # Mock data

class HotelsComAPIClient:
    platform_name = "hotels.com"
    
    async def search_properties(self, params: Dict) -> List[Dict]:
        return []  # Mock implementation
    
    async def get_property_pricing(self, property_id: str, check_in: date, check_out: date) -> float:
        return 110.0  # Mock data

class AirbnbAPIClient:
    platform_name = "airbnb"
    
    async def search_properties(self, params: Dict) -> List[Dict]:
        return []  # Mock implementation
    
    async def get_property_pricing(self, property_id: str, check_in: date, check_out: date) -> float:
        return 95.0  # Mock data

class ExpediaAPIClient:
    platform_name = "expedia"
    
    async def search_properties(self, params: Dict) -> List[Dict]:
        return []  # Mock implementation
    
    async def get_property_pricing(self, property_id: str, check_in: date, check_out: date) -> float:
        return 115.0  # Mock data
