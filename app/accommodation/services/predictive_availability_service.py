# Predictive Availability and Waitlist System - Beyond OTA Standards
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class AvailabilityPrediction(Enum):
    HIGH_PROBABILITY = "high_probability"  # >80% chance of availability
    MODERATE_PROBABILITY = "moderate_probability"  # 40-80% chance
    LOW_PROBABILITY = "low_probability"  # <40% chance
    UNLIKELY = "unlikely"  # <10% chance
    SOLD_OUT_PREDICTED = "sold_out_predicted"  # AI predicts sold out

class WaitlistPriority(Enum):
    VIP = "vip"  # High-value customers
    FLEXIBLE = "flexible"  # Flexible dates/guests
    URGENT = "urgent"  # Time-sensitive bookings
    STANDARD = "standard"  # Regular customers

@dataclass
class AvailabilityForecast:
    property_id: int
    date: date
    prediction: AvailabilityPrediction
    confidence_score: float  # 0-1
    factors: List[str]
    alternative_dates: List[date]
    price_impact: float  # Expected price change
    recommendation: str

@dataclass
class WaitlistEntry:
    id: str
    user_id: int
    property_id: int
    check_in: date
    check_out: date
    num_guests: int
    priority: WaitlistPriority
    flexibility_days: int
    max_price_increase: float  # Percentage
    notification_preferences: Dict
    created_at: datetime
    estimated_wait_time: Optional[timedelta] = None
    probability_of_success: float = 0.0

class PredictiveAvailabilityService:
    """
    Revolutionary predictive availability system that uses AI to forecast
    availability and manage waitlists more intelligently than any OTA
    """
    
    def __init__(self):
        self.ml_models = {}
        self.waitlist_manager = WaitlistManager()
        self.forecast_cache = {}
    
    def predict_availability(self, property_id: int, check_in: date, 
                           check_out: date, num_guests: int = 2) -> AvailabilityForecast:
        """
        Predict availability using advanced ML algorithms
        """
        
        # Gather historical data
        historical_data = self._gather_historical_data(property_id, check_in, check_out)
        
        # Analyze current booking patterns
        booking_patterns = self._analyze_booking_patterns(property_id, check_in)
        
        # Market demand analysis
        demand_analysis = self._analyze_market_demand(property_id, check_in, check_out)
        
        # Competitor availability
        competitor_data = self._analyze_competitor_availability(property_id, check_in, check_out)
        
        # Event impact analysis
        event_impact = self._analyze_event_impact(check_in, check_out)
        
        # Seasonality and trends
        seasonality = self._analyze_seasonality_patterns(check_in)
        
        # Run ML prediction
        prediction_result = self._run_availability_prediction(
            historical_data, booking_patterns, demand_analysis, 
            competitor_data, event_impact, seasonality
        )
        
        # Generate alternative dates
        alternatives = self._generate_alternative_dates(check_in, check_out, prediction_result)
        
        # Calculate price impact
        price_impact = self._predict_price_impact(property_id, prediction_result)
        
        # Create recommendation
        recommendation = self._generate_recommendation(prediction_result, alternatives, price_impact)
        
        return AvailabilityForecast(
            property_id=property_id,
            date=check_in,
            prediction=prediction_result["prediction"],
            confidence_score=prediction_result["confidence"],
            factors=prediction_result["factors"],
            alternative_dates=alternatives,
            price_impact=price_impact,
            recommendation=recommendation
        )
    
    def join_waitlist(self, user_id: int, property_id: int, check_in: date, 
                     check_out: date, num_guests: int, priority: WaitlistPriority = WaitlistPriority.STANDARD,
                     flexibility_days: int = 3, max_price_increase: float = 20.0) -> WaitlistEntry:
        """
        Add user to intelligent waitlist with priority scoring
        """
        
        # Calculate priority score
        priority_score = self._calculate_priority_score(user_id, property_id, priority, flexibility_days)
        
        # Estimate wait time
        estimated_wait = self._estimate_wait_time(property_id, check_in, check_out)
        
        # Calculate probability of success
        success_probability = self._calculate_success_probability(property_id, check_in, check_out, priority_score)
        
        # Create waitlist entry
        waitlist_entry = WaitlistEntry(
            id=f"wl_{user_id}_{property_id}_{int(datetime.now().timestamp())}",
            user_id=user_id,
            property_id=property_id,
            check_in=check_in,
            check_out=check_out,
            num_guests=num_guests,
            priority=priority,
            flexibility_days=flexibility_days,
            max_price_increase=max_price_increase,
            notification_preferences=self._get_default_notification_preferences(),
            created_at=datetime.now(),
            estimated_wait_time=estimated_wait,
            probability_of_success=success_probability
        )
        
        # Add to waitlist
        self.waitlist_manager.add_entry(waitlist_entry)
        
        # Send confirmation
        self._send_waitlist_confirmation(waitlist_entry)
        
        return waitlist_entry
    
    def process_waitlist_opportunities(self, property_id: int, newly_available_dates: List[Tuple[date, date]]) -> List[WaitlistEntry]:
        """
        Process waitlist when dates become available
        """
        
        matched_entries = []
        
        for check_in, check_out in newly_available_dates:
            # Find matching waitlist entries
            matches = self.waitlist_manager.find_matches(property_id, check_in, check_out)
            
            # Score and rank matches
            scored_matches = self._score_waitlist_matches(matches, check_in, check_out)
            
            # Select best matches
            selected_matches = self._select_best_matches(scored_matches, len(newly_available_dates))
            
            matched_entries.extend(selected_matches)
            
            # Notify selected users
            for entry in selected_matches:
                self._notify_waitlist_opportunity(entry, check_in, check_out)
        
        return matched_entries
    
    def _gather_historical_data(self, property_id: int, check_in: date, check_out: date) -> Dict:
        """Gather historical availability data"""
        
        # Get historical availability for same dates in previous years
        historical_availability = []
        
        for year_offset in range(1, 4):  # Last 3 years
            historical_date = check_in.replace(year=check_in.year - year_offset)
            
            # Query historical data (simplified)
            availability_rate = self._get_historical_availability_rate(property_id, historical_date)
            booking_velocity = self._get_historical_booking_velocity(property_id, historical_date)
            
            historical_availability.append({
                "year": check_in.year - year_offset,
                "availability_rate": availability_rate,
                "booking_velocity": booking_velocity
            })
        
        return {
            "historical_availability": historical_availability,
            "patterns": self._detect_historical_patterns(historical_availability)
        }
    
    def _analyze_booking_patterns(self, property_id: int, check_in: date) -> Dict:
        """Analyze current booking patterns"""
        
        # Recent booking trends
        recent_bookings = self._get_recent_bookings(property_id, days_back=30)
        
        # Booking velocity trends
        velocity_trend = self._calculate_booking_velocity_trend(recent_bookings)
        
        # Cancellation patterns
        cancellation_rate = self._calculate_cancellation_rate(property_id, check_in)
        
        # Last-minute booking patterns
        last_minute_rate = self._calculate_last_minute_rate(property_id, check_in)
        
        return {
            "recent_bookings": len(recent_bookings),
            "velocity_trend": velocity_trend,
            "cancellation_rate": cancellation_rate,
            "last_minute_rate": last_minute_rate,
            "pattern_score": self._calculate_pattern_score(velocity_trend, cancellation_rate, last_minute_rate)
        }
    
    def _analyze_market_demand(self, property_id: int, check_in: date, check_out: date) -> Dict:
        """Analyze overall market demand"""
        
        # Search volume trends
        search_trends = self._get_search_trends(property_id, check_in)
        
        # Market demand index
        demand_index = self._get_market_demand_index(check_in)
        
        # Property popularity score
        popularity_score = self._calculate_popularity_score(property_id)
        
        # Competitor demand
        competitor_demand = self._analyze_competitor_demand(property_id, check_in)
        
        return {
            "search_trends": search_trends,
            "demand_index": demand_index,
            "popularity_score": popularity_score,
            "competitor_demand": competitor_demand,
            "overall_demand": (search_trends + demand_index + popularity_score) / 3
        }
    
    def _analyze_competitor_availability(self, property_id: int, check_in: date, check_out: date) -> Dict:
        """Analyze competitor availability patterns"""
        
        # Get competitor properties
        competitors = self._get_competitor_properties(property_id)
        
        competitor_availability = {}
        for comp_id in competitors:
            availability = self._check_competitor_availability(comp_id, check_in, check_out)
            competitor_availability[comp_id] = availability
        
        # Calculate market availability rate
        available_competitors = sum(1 for avail in competitor_availability.values() if avail)
        total_competitors = len(competitor_availability)
        market_availability_rate = available_competitors / total_competitors if total_competitors > 0 else 0
        
        return {
            "competitor_availability": competitor_availability,
            "market_availability_rate": market_availability_rate,
            "competitive_pressure": 1 - market_availability_rate
        }
    
    def _analyze_event_impact(self, check_in: date, check_out: date) -> Dict:
        """Analyze impact of local events on availability"""
        
        # Get events during stay period
        events = self._get_events_in_period(check_in, check_out)
        
        if not events:
            return {"event_impact": 0.0, "events": []}
        
        # Calculate total impact
        total_impact = 0.0
        event_details = []
        
        for event in events:
            # Event size impact
            size_impact = min(event.get("attendees", 0) / 100000, 1.0)
            
            # Event type impact
            type_multiplier = {
                "sports": 1.5,
                "concert": 1.8,
                "conference": 1.3,
                "festival": 2.0,
                "holiday": 1.2
            }.get(event.get("type", ""), 1.0)
            
            # Distance impact
            distance = event.get("distance_km", 50)
            distance_impact = max(0, 1 - distance / 100)
            
            event_impact = size_impact * type_multiplier * distance_impact
            total_impact += event_impact
            
            event_details.append({
                "name": event.get("name"),
                "impact": event_impact,
                "type": event.get("type")
            })
        
        return {
            "event_impact": min(total_impact, 1.0),
            "events": event_details
        }
    
    def _analyze_seasonality_patterns(self, check_in: date) -> Dict:
        """Analyze seasonality patterns"""
        
        # Season classification
        month = check_in.month
        if month in [12, 1, 2]:
            season = "winter"
            season_multiplier = 1.2
        elif month in [3, 4, 5]:
            season = "spring"
            season_multiplier = 1.1
        elif month in [6, 7, 8]:
            season = "summer"
            season_multiplier = 1.3
        else:
            season = "fall"
            season_multiplier = 1.0
        
        # Day of week patterns
        day_of_week = check_in.weekday()
        if day_of_week >= 5:  # Weekend
            day_multiplier = 1.2
        elif day_of_week <= 2:  # Monday/Tuesday
            day_multiplier = 0.9
        else:
            day_multiplier = 1.0
        
        # Holiday proximity
        holiday_impact = self._calculate_holiday_proximity_impact(check_in)
        
        return {
            "season": season,
            "season_multiplier": season_multiplier,
            "day_multiplier": day_multiplier,
            "holiday_impact": holiday_impact,
            "overall_seasonality": season_multiplier * day_multiplier * (1 + holiday_impact)
        }
    
    def _run_availability_prediction(self, historical_data: Dict, booking_patterns: Dict,
                                    demand_analysis: Dict, competitor_data: Dict,
                                    event_impact: Dict, seasonality: Dict) -> Dict:
        """Run ML model for availability prediction"""
        
        # Feature engineering
        features = {
            "historical_availability_rate": np.mean([h["availability_rate"] for h in historical_data["historical_availability"]]) if historical_data["historical_availability"] else 0.5,
            "booking_velocity_trend": booking_patterns["velocity_trend"],
            "cancellation_rate": booking_patterns["cancellation_rate"],
            "market_demand": demand_analysis["overall_demand"],
            "competitor_pressure": competitor_data["competitive_pressure"],
            "event_impact": event_impact["event_impact"],
            "seasonality_factor": seasonality["overall_seasonality"],
            "days_until_booking": (date.today() - check_in).days
        }
        
        # Simplified ML prediction (in production, use trained model)
        base_probability = 0.5
        
        # Apply feature weights
        prediction_score = base_probability + (
            features["historical_availability_rate"] * 0.2 +
            features["booking_velocity_trend"] * 0.15 +
            features["market_demand"] * -0.2 +  # Higher demand = lower availability
            features["competitor_pressure"] * -0.15 +
            features["event_impact"] * -0.25 +
            features["seasonality_factor"] * -0.1
        )
        
        # Add some randomness for realism
        prediction_score += np.random.normal(0, 0.05)
        
        # Determine prediction category
        if prediction_score > 0.8:
            prediction = AvailabilityPrediction.HIGH_PROBABILITY
        elif prediction_score > 0.6:
            prediction = AvailabilityPrediction.MODERATE_PROBABILITY
        elif prediction_score > 0.4:
            prediction = AvailabilityPrediction.LOW_PROBABILITY
        elif prediction_score > 0.2:
            prediction = AvailabilityPrediction.UNLIKELY
        else:
            prediction = AvailabilityPrediction.SOLD_OUT_PREDICTED
        
        # Calculate confidence
        confidence = min(0.9, max(0.3, abs(prediction_score - 0.5) * 2))
        
        # Generate factors
        factors = []
        if features["event_impact"] > 0.3:
            factors.append(f"High event impact ({features['event_impact']:.1%})")
        if features["market_demand"] > 0.7:
            factors.append(f"Strong market demand ({features['market_demand']:.1%})")
        if features["seasonality_factor"] > 1.2:
            factors.append("Peak season demand")
        if features["competitor_pressure"] > 0.6:
            factors.append("High competitor occupancy")
        
        return {
            "prediction": prediction,
            "confidence": confidence,
            "raw_score": prediction_score,
            "factors": factors
        }
    
    def _generate_alternative_dates(self, check_in: date, check_out: date, prediction_result: Dict) -> List[date]:
        """Generate alternative date suggestions"""
        
        alternatives = []
        
        # Check dates before and after requested dates
        for offset in range(-7, 8):  # ±1 week
            if offset == 0:
                continue
            
            alt_date = check_in + timedelta(days=offset)
            
            # Skip if too far in the past
            if alt_date < date.today():
                continue
            
            # Check if alternative is likely available
            alt_prediction = self._quick_availability_check(alt_date)
            
            if alt_prediction > 0.6:  # Good availability probability
                alternatives.append(alt_date)
        
        # Sort by availability probability and proximity to original date
        alternatives.sort(key=lambda d: (self._quick_availability_check(d), abs((d - check_in).days)), reverse=True)
        
        return alternatives[:5]  # Return top 5 alternatives
    
    def _predict_price_impact(self, property_id: int, prediction_result: Dict) -> float:
        """Predict price impact based on availability"""
        
        prediction = prediction_result["prediction"]
        confidence = prediction_result["confidence"]
        
        # Price impact based on scarcity
        if prediction == AvailabilityPrediction.SOLD_OUT_PREDICTED:
            return 50.0  # 50% price increase
        elif prediction == AvailabilityPrediction.UNLIKELY:
            return 30.0
        elif prediction == AvailabilityPrediction.LOW_PROBABILITY:
            return 15.0
        elif prediction == AvailabilityPrediction.MODERATE_PROBABILITY:
            return 5.0
        else:
            return -5.0  # Potential discount for high availability
    
    def _generate_recommendation(self, prediction_result: Dict, alternatives: List[date], price_impact: float) -> str:
        """Generate booking recommendation"""
        
        prediction = prediction_result["prediction"]
        confidence = prediction_result["confidence"]
        
        if prediction == AvailabilityPrediction.HIGH_PROBABILITY:
            return "Book now - high availability expected with stable pricing"
        elif prediction == AvailabilityPrediction.MODERATE_PROBABILITY:
            return "Good availability - consider booking soon to secure current rates"
        elif prediction == AvailabilityPrediction.LOW_PROBABILITY:
            return "Limited availability - book now or consider alternative dates"
        elif prediction == AvailabilityPrediction.UNLIKELY:
            return "Very limited availability - join waitlist for best chance"
        else:
            return "Likely sold out - join waitlist for notifications if dates open up"
    
    # Helper methods (simplified for demo)
    def _get_historical_availability_rate(self, property_id: int, date: date) -> float:
        return 0.7  # Mock data
    
    def _get_historical_booking_velocity(self, property_id: int, date: date) -> float:
        return 0.5  # Mock data
    
    def _detect_historical_patterns(self, historical_availability: List[Dict]) -> Dict:
        return {"trend": "stable"}  # Mock data
    
    def _get_recent_bookings(self, property_id: int, days_back: int) -> List[Dict]:
        return []  # Mock data
    
    def _calculate_booking_velocity_trend(self, recent_bookings: List[Dict]) -> float:
        return 0.6  # Mock data
    
    def _calculate_cancellation_rate(self, property_id: int, check_in: date) -> float:
        return 0.1  # Mock data
    
    def _calculate_last_minute_rate(self, property_id: int, check_in: date) -> float:
        return 0.2  # Mock data
    
    def _calculate_pattern_score(self, velocity: float, cancellation: float, last_minute: float) -> float:
        return (velocity + (1 - cancellation) + last_minute) / 3
    
    def _get_search_trends(self, property_id: int, check_in: date) -> float:
        return 0.6  # Mock data
    
    def _get_market_demand_index(self, check_in: date) -> float:
        return 0.7  # Mock data
    
    def _calculate_popularity_score(self, property_id: int) -> float:
        return 0.8  # Mock data
    
    def _analyze_competitor_demand(self, property_id: int, check_in: date) -> float:
        return 0.6  # Mock data
    
    def _get_competitor_properties(self, property_id: int) -> List[int]:
        return [1001, 1002, 1003]  # Mock data
    
    def _check_competitor_availability(self, competitor_id: int, check_in: date, check_out: date) -> bool:
        return True  # Mock data
    
    def _get_events_in_period(self, check_in: date, check_out: date) -> List[Dict]:
        return []  # Mock data
    
    def _calculate_holiday_proximity_impact(self, check_in: date) -> float:
        return 0.0  # Mock data
    
    def _quick_availability_check(self, date: date) -> float:
        return 0.7  # Mock data
    
    def _calculate_priority_score(self, user_id: int, property_id: int, priority: WaitlistPriority, flexibility: int) -> float:
        return 0.8  # Mock data
    
    def _estimate_wait_time(self, property_id: int, check_in: date, check_out: date) -> timedelta:
        return timedelta(days=7)  # Mock data
    
    def _calculate_success_probability(self, property_id: int, check_in: date, check_out: date, priority_score: float) -> float:
        return 0.6  # Mock data
    
    def _get_default_notification_preferences(self) -> Dict:
        return {
            "email": True,
            "sms": True,
            "push": True,
            "immediate": True
        }
    
    def _send_waitlist_confirmation(self, entry: WaitlistEntry):
        logger.info(f"Waitlist confirmation sent for entry {entry.id}")
    
    def _notify_waitlist_opportunity(self, entry: WaitlistEntry, check_in: date, check_out: date):
        logger.info(f"Waitlist opportunity notified for entry {entry.id}")


class WaitlistManager:
    """Manages intelligent waitlist system"""
    
    def __init__(self):
        self.entries = {}  # In production, use database
        self.property_waitlists = {}  # property_id -> list of entries
    
    def add_entry(self, entry: WaitlistEntry):
        """Add entry to waitlist"""
        self.entries[entry.id] = entry
        
        if entry.property_id not in self.property_waitlists:
            self.property_waitlists[entry.property_id] = []
        
        self.property_waitlists[entry.property_id].append(entry)
        
        # Sort by priority score
        self.property_waitlists[entry.property_id].sort(
            key=lambda e: self._calculate_priority_score(e), reverse=True
        )
    
    def find_matches(self, property_id: int, check_in: date, check_out: date) -> List[WaitlistEntry]:
        """Find matching waitlist entries"""
        
        if property_id not in self.property_waitlists:
            return []
        
        matches = []
        
        for entry in self.property_waitlists[property_id]:
            # Check date flexibility
            if self._is_date_match(entry, check_in, check_out):
                matches.append(entry)
        
        return matches
    
    def _calculate_priority_score(self, entry: WaitlistEntry) -> float:
        """Calculate priority score for waitlist entry"""
        
        score = 0.5  # Base score
        
        # Priority level
        priority_scores = {
            WaitlistPriority.VIP: 0.4,
            WaitlistPriority.URGENT: 0.3,
            WaitlistPriority.FLEXIBLE: 0.2,
            WaitlistPriority.STANDARD: 0.0
        }
        score += priority_scores.get(entry.priority, 0)
        
        # Flexibility bonus
        score += entry.flexibility_days * 0.05
        
        # Price flexibility bonus
        score += entry.max_price_increase * 0.01
        
        # Wait time penalty (longer wait = higher priority)
        days_waiting = (datetime.now() - entry.created_at).days
        score += min(days_waiting * 0.02, 0.3)
        
        return min(score, 1.0)
    
    def _is_date_match(self, entry: WaitlistEntry, check_in: date, check_out: date) -> bool:
        """Check if entry matches available dates"""
        
        # Exact match
        if entry.check_in == check_in and entry.check_out == check_out:
            return True
        
        # Flexible dates
        flexibility = timedelta(days=entry.flexibility_days)
        
        earliest_check_in = entry.check_in - flexibility
        latest_check_in = entry.check_in + flexibility
        
        if earliest_check_in <= check_in <= latest_check_in:
            # Check if stay duration matches
            entry_duration = (entry.check_out - entry.check_in).days
            available_duration = (check_out - check_in).days
            
            # Allow ±1 day flexibility in duration
            if abs(entry_duration - available_duration) <= 1:
                return True
        
        return False
