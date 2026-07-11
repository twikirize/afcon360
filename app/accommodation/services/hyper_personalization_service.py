# Hyper-Personalized Recommendation Engine - Beyond OTA Standards
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

class PersonalizationLevel(Enum):
    BASIC = "basic"  # Simple preferences
    ADVANCED = "advanced"  # Behavioral patterns
    PREDICTIVE = "predictive"  # AI predictions
    EMOTIONAL = "emotional"  # Emotional intelligence

class RecommendationType(Enum):
    SIMILAR_PROPERTIES = "similar_properties"
    TRENDING = "trending"
    PERSONALIZED = "personalized"
    CONTEXTUAL = "contextual"
    DISCOVERY = "discovery"

@dataclass
class UserPersona:
    persona_type: str  # "business_traveler", "family_vacation", "luxury_seeker", etc.
    preferences: Dict[str, float]
    behavior_patterns: Dict[str, float]
    emotional_profile: Dict[str, float]
    life_stage: str
    travel_frequency: str
    budget_sensitivity: float

@dataclass
class Recommendation:
    property_id: int
    score: float  # 0-1
    reasoning: List[str]
    personalization_level: PersonalizationLevel
    confidence: float
    context_factors: List[str]
    emotional_appeal: str

class HyperPersonalizationService:
    """
    Revolutionary personalization engine that goes beyond traditional recommendations
    using emotional intelligence, behavioral analysis, and predictive AI
    """
    
    def __init__(self):
        self.user_profiles = {}
        self.ml_models = {}
        self.emotional_ai = EmotionalIntelligenceAI()
        self.behavior_tracker = BehaviorTracker()
    
    def get_hyper_personalized_recommendations(
        self, 
        user_id: int, 
        context: Dict = None,
        recommendation_type: RecommendationType = RecommendationType.PERSONALIZED,
        limit: int = 10
    ) -> List[Recommendation]:
        """
        Get hyper-personalized recommendations using advanced AI
        """
        
        # Build comprehensive user profile
        user_persona = self._build_user_persona(user_id)
        
        # Analyze current context
        context_analysis = self._analyze_context(context or {})
        
        # Get candidate properties
        candidates = self._get_candidate_properties(user_id, recommendation_type)
        
        # Score candidates with multi-dimensional analysis
        scored_recommendations = []
        
        for property_data in candidates:
            # Calculate comprehensive score
            score_data = self._calculate_comprehensive_score(
                property_data, user_persona, context_analysis
            )
            
            # Generate reasoning
            reasoning = self._generate_recommendation_reasoning(
                score_data, user_persona, context_analysis
            )
            
            # Determine emotional appeal
            emotional_appeal = self._determine_emotional_appeal(
                property_data, user_persona.emotional_profile
            )
            
            recommendation = Recommendation(
                property_id=property_data["id"],
                score=score_data["total_score"],
                reasoning=reasoning,
                personalization_level=score_data["personalization_level"],
                confidence=score_data["confidence"],
                context_factors=score_data["context_factors"],
                emotional_appeal=emotional_appeal
            )
            
            scored_recommendations.append(recommendation)
        
        # Sort and filter
        scored_recommendations.sort(key=lambda x: x.score, reverse=True)
        
        return scored_recommendations[:limit]
    
    def _build_user_persona(self, user_id: int) -> UserPersona:
        """Build comprehensive user persona using AI analysis"""
        
        if user_id in self.user_profiles:
            return self.user_profiles[user_id]
        
        # Gather user data
        booking_history = self._get_user_booking_history(user_id)
        search_history = self._get_user_search_history(user_id)
        property_interactions = self._get_property_interactions(user_id)
        demographic_data = self._get_demographic_data(user_id)
        
        # Analyze behavior patterns
        behavior_patterns = self._analyze_behavior_patterns(
            booking_history, search_history, property_interactions
        )
        
        # Extract preferences
        preferences = self._extract_preferences(booking_history, search_history)
        
        # Build emotional profile
        emotional_profile = self.emotional_ai.analyze_emotional_profile(
            booking_history, search_history, property_interactions
        )
        
        # Determine persona type
        persona_type = self._determine_persona_type(
            preferences, behavior_patterns, demographic_data
        )
        
        # Calculate life stage
        life_stage = self._determine_life_stage(demographic_data, booking_history)
        
        # Determine travel frequency
        travel_frequency = self._calculate_travel_frequency(booking_history)
        
        # Calculate budget sensitivity
        budget_sensitivity = self._calculate_budget_sensitivity(booking_history, search_history)
        
        persona = UserPersona(
            persona_type=persona_type,
            preferences=preferences,
            behavior_patterns=behavior_patterns,
            emotional_profile=emotional_profile,
            life_stage=life_stage,
            travel_frequency=travel_frequency,
            budget_sensitivity=budget_sensitivity
        )
        
        # Cache persona
        self.user_profiles[user_id] = persona
        
        return persona
    
    def _analyze_context(self, context: Dict) -> Dict:
        """Analyze current booking context"""
        
        context_analysis = {
            "trip_purpose": self._infer_trip_purpose(context),
            "urgency_level": self._calculate_urgency_level(context),
            "group_composition": self._analyze_group_composition(context),
            "seasonal_context": self._analyze_seasonal_context(context),
            "economic_context": self._analyze_economic_context(context),
            "social_context": self._analyze_social_context(context)
        }
        
        return context_analysis
    
    def _calculate_comprehensive_score(self, property_data: Dict, user_persona: UserPersona, 
                                    context_analysis: Dict) -> Dict:
        """Calculate comprehensive recommendation score"""
        
        # Base compatibility score
        base_score = self._calculate_base_compatibility(property_data, user_persona)
        
        # Personalization boost
        personalization_score = self._calculate_personalization_score(property_data, user_persona)
        
        # Context relevance
        context_score = self._calculate_context_relevance(property_data, context_analysis)
        
        # Emotional resonance
        emotional_score = self._calculate_emotional_resonance(property_data, user_persona.emotional_profile)
        
        # Behavioral match
        behavioral_score = self._calculate_behavioral_match(property_data, user_persona.behavior_patterns)
        
        # Predictive success
        predictive_score = self._calculate_predictive_success(property_data, user_persona, context_analysis)
        
        # Calculate weighted total
        total_score = (
            base_score * 0.25 +
            personalization_score * 0.25 +
            context_score * 0.20 +
            emotional_score * 0.15 +
            behavioral_score * 0.10 +
            predictive_score * 0.05
        )
        
        # Determine personalization level
        personalization_level = self._determine_personalization_level(
            personalization_score, emotional_score, predictive_score
        )
        
        # Calculate confidence
        confidence = self._calculate_recommendation_confidence(
            base_score, personalization_score, context_score
        )
        
        # Identify context factors
        context_factors = self._identify_context_factors(property_data, context_analysis)
        
        return {
            "total_score": total_score,
            "base_score": base_score,
            "personalization_score": personalization_score,
            "context_score": context_score,
            "emotional_score": emotional_score,
            "behavioral_score": behavioral_score,
            "predictive_score": predictive_score,
            "personalization_level": personalization_level,
            "confidence": confidence,
            "context_factors": context_factors
        }
    
    def _calculate_base_compatibility(self, property_data: Dict, user_persona: UserPersona) -> float:
        """Calculate basic property-user compatibility"""
        
        score = 0.0
        
        # Price compatibility
        property_price = property_data.get("price", 0)
        if user_persona.budget_sensitivity > 0.7:
            # Budget-conscious user
            if property_price < 100:
                score += 0.3
            elif property_price < 150:
                score += 0.2
            else:
                score += 0.1
        else:
            # Less budget-sensitive
            if property_price < 200:
                score += 0.2
            elif property_price < 300:
                score += 0.3
            else:
                score += 0.4
        
        # Amenity compatibility
        property_amenities = set(property_data.get("amenities", []))
        preferred_amenities = set([
            amenity for amenity, preference in user_persona.preferences.items()
            if preference > 0.7
        ])
        
        if preferred_amenities:
            amenity_match = len(property_amenities & preferred_amenities) / len(preferred_amenities)
            score += amenity_match * 0.3
        
        # Location compatibility
        if "city" in property_data:
            preferred_cities = user_persona.preferences.get("preferred_cities", [])
            if property_data["city"] in preferred_cities:
                score += 0.2
        
        # Property type compatibility
        property_type = property_data.get("property_type", "")
        preferred_types = user_persona.preferences.get("preferred_property_types", [])
        if property_type in preferred_types:
            score += 0.2
        
        return min(score, 1.0)
    
    def _calculate_personalization_score(self, property_data: Dict, user_persona: UserPersona) -> float:
        """Calculate personalization score based on user preferences"""
        
        score = 0.0
        
        # Persona-specific preferences
        if user_persona.persona_type == "business_traveler":
            if "wifi" in property_data.get("amenities", []):
                score += 0.2
            if "desk" in property_data.get("amenities", []):
                score += 0.2
            if property_data.get("city") in ["Nairobi", "Kampala", "Cairo"]:  # Business hubs
                score += 0.1
        
        elif user_persona.persona_type == "family_vacation":
            if property_data.get("max_guests", 0) >= 4:
                score += 0.2
            if "family_friendly" in property_data.get("amenities", []):
                score += 0.2
            if "pool" in property_data.get("amenities", []):
                score += 0.1
        
        elif user_persona.persona_type == "luxury_seeker":
            if property_data.get("price", 0) > 200:
                score += 0.3
            if "premium_amenities" in property_data.get("amenities", []):
                score += 0.2
            if property_data.get("rating", 0) > 4.5:
                score += 0.2
        
        elif user_persona.persona_type == "budget_traveler":
            if property_data.get("price", 0) < 80:
                score += 0.3
            if "kitchen" in property_data.get("amenities", []):
                score += 0.2  # Save on meals
        
        # Life stage considerations
        if user_persona.life_stage == "young_professional":
            if property_data.get("city") in ["Nairobi", "Jinja"]:  # Trendy locations
                score += 0.1
            if "gym" in property_data.get("amenities", []):
                score += 0.1
        
        elif user_persona.life_stage == "family_with_kids":
            if property_data.get("max_guests", 0) >= 4:
                score += 0.2
            if "playground" in property_data.get("amenities", []):
                score += 0.2
        
        # Travel frequency considerations
        if user_persona.travel_frequency == "frequent":
            # Frequent travelers value consistency and quality
            if property_data.get("rating", 0) > 4.0:
                score += 0.2
            if property_data.get("is_verified", False):
                score += 0.1
        
        return min(score, 1.0)
    
    def _calculate_emotional_resonance(self, property_data: Dict, emotional_profile: Dict) -> float:
        """Calculate emotional resonance with property"""
        
        score = 0.0
        
        # Adventure seeker
        if emotional_profile.get("adventure_seeking", 0) > 0.7:
            if "outdoor_activities" in property_data.get("amenities", []):
                score += 0.3
            if property_data.get("city") in ["Jinja", "Entebbe"]:  # Adventure locations
                score += 0.2
        
        # Peace seeker
        if emotional_profile.get("peace_seeking", 0) > 0.7:
            if "quiet_neighborhood" in property_data.get("amenities", []):
                score += 0.3
            if "garden" in property_data.get("amenities", []):
                score += 0.2
        
        # Social butterfly
        if emotional_profile.get("social_orientation", 0) > 0.7:
            if property_data.get("max_guests", 0) >= 6:
                score += 0.3
            if "entertainment_area" in property_data.get("amenities", []):
                score += 0.2
        
        # Comfort seeker
        if emotional_profile.get("comfort_seeking", 0) > 0.7:
            if property_data.get("rating", 0) > 4.5:
                score += 0.3
            if "premium_bedding" in property_data.get("amenities", []):
                score += 0.2
        
        # Status conscious
        if emotional_profile.get("status_conscious", 0) > 0.7:
            if property_data.get("price", 0) > 300:
                score += 0.3
            if "luxury_amenities" in property_data.get("amenities", []):
                score += 0.2
        
        return min(score, 1.0)
    
    def _generate_recommendation_reasoning(self, score_data: Dict, user_persona: UserPersona, 
                                         context_analysis: Dict) -> List[str]:
        """Generate human-readable reasoning for recommendation"""
        
        reasoning = []
        
        # Personalization reasoning
        if score_data["personalization_score"] > 0.7:
            reasoning.append(f"Perfect match for {user_persona.persona_type.replace('_', ' ')}")
        
        # Emotional reasoning
        if score_data["emotional_score"] > 0.6:
            primary_emotion = max(user_persona.emotional_profile.items(), key=lambda x: x[1])[0]
            reasoning.append(f"Appeals to your {primary_emotion.replace('_', ' ')} preferences")
        
        # Context reasoning
        if score_data["context_score"] > 0.6:
            trip_purpose = context_analysis.get("trip_purpose", "")
            if trip_purpose:
                reasoning.append(f"Ideal for {trip_purpose}")
        
        # Behavioral reasoning
        if score_data["behavioral_score"] > 0.6:
            reasoning.append("Matches your past booking patterns")
        
        # Value reasoning
        if user_persona.budget_sensitivity > 0.7 and score_data["base_score"] > 0.6:
            reasoning.append("Great value for your budget")
        
        # Quality reasoning
        if score_data["base_score"] > 0.7:
            reasoning.append("High quality and well-reviewed")
        
        return reasoning[:4]  # Return top 4 reasons
    
    def _determine_emotional_appeal(self, property_data: Dict, emotional_profile: Dict) -> str:
        """Determine emotional appeal message"""
        
        appeals = []
        
        if emotional_profile.get("adventure_seeking", 0) > 0.6:
            appeals.append("exciting adventures await")
        
        if emotional_profile.get("peace_seeking", 0) > 0.6:
            appeals.append("find your perfect escape")
        
        if emotional_profile.get("social_orientation", 0) > 0.6:
            appeals.append("create memorable moments together")
        
        if emotional_profile.get("comfort_seeking", 0) > 0.6:
            appeals.append("experience ultimate comfort")
        
        if emotional_profile.get("status_conscious", 0) > 0.6:
            appeals.append("indulge in luxury")
        
        if not appeals:
            appeals.append("discover your perfect stay")
        
        return appeals[0].capitalize()
    
    # Helper methods (simplified for demo)
    def _get_user_booking_history(self, user_id: int) -> List[Dict]:
        return []  # Mock data
    
    def _get_user_search_history(self, user_id: int) -> List[Dict]:
        return []  # Mock data
    
    def _get_property_interactions(self, user_id: int) -> List[Dict]:
        return []  # Mock data
    
    def _get_demographic_data(self, user_id: int) -> Dict:
        return {}  # Mock data
    
    def _analyze_behavior_patterns(self, booking_history: List[Dict], search_history: List[Dict], 
                                 property_interactions: List[Dict]) -> Dict[str, float]:
        return {"pattern_score": 0.7}  # Mock data
    
    def _extract_preferences(self, booking_history: List[Dict], search_history: List[Dict]) -> Dict[str, float]:
        return {"wifi": 0.8, "parking": 0.6}  # Mock data
    
    def _determine_persona_type(self, preferences: Dict, behavior_patterns: Dict, 
                               demographic_data: Dict) -> str:
        return "business_traveler"  # Mock data
    
    def _determine_life_stage(self, demographic_data: Dict, booking_history: List[Dict]) -> str:
        return "young_professional"  # Mock data
    
    def _calculate_travel_frequency(self, booking_history: List[Dict]) -> str:
        return "moderate"  # Mock data
    
    def _calculate_budget_sensitivity(self, booking_history: List[Dict], search_history: List[Dict]) -> float:
        return 0.6  # Mock data
    
    def _get_candidate_properties(self, user_id: int, recommendation_type: RecommendationType) -> List[Dict]:
        return []  # Mock data
    
    def _infer_trip_purpose(self, context: Dict) -> str:
        return "leisure"  # Mock data
    
    def _calculate_urgency_level(self, context: Dict) -> float:
        return 0.5  # Mock data
    
    def _analyze_group_composition(self, context: Dict) -> Dict:
        return {}  # Mock data
    
    def _analyze_seasonal_context(self, context: Dict) -> Dict:
        return {}  # Mock data
    
    def _analyze_economic_context(self, context: Dict) -> Dict:
        return {}  # Mock data
    
    def _analyze_social_context(self, context: Dict) -> Dict:
        return {}  # Mock data
    
    def _calculate_context_relevance(self, property_data: Dict, context_analysis: Dict) -> float:
        return 0.7  # Mock data
    
    def _calculate_behavioral_match(self, property_data: Dict, behavior_patterns: Dict) -> float:
        return 0.6  # Mock data
    
    def _calculate_predictive_success(self, property_data: Dict, user_persona: UserPersona, 
                                    context_analysis: Dict) -> float:
        return 0.7  # Mock data
    
    def _determine_personalization_level(self, personalization_score: float, 
                                       emotional_score: float, predictive_score: float) -> PersonalizationLevel:
        avg_score = (personalization_score + emotional_score + predictive_score) / 3
        
        if avg_score > 0.8:
            return PersonalizationLevel.EMOTIONAL
        elif avg_score > 0.6:
            return PersonalizationLevel.PREDICTIVE
        elif avg_score > 0.4:
            return PersonalizationLevel.ADVANCED
        else:
            return PersonalizationLevel.BASIC
    
    def _calculate_recommendation_confidence(self, base_score: float, personalization_score: float, 
                                          context_score: float) -> float:
        return (base_score + personalization_score + context_score) / 3
    
    def _identify_context_factors(self, property_data: Dict, context_analysis: Dict) -> List[str]:
        return ["location_match", "price_appropriate"]  # Mock data


class EmotionalIntelligenceAI:
    """AI system for understanding user emotional profiles"""
    
    def analyze_emotional_profile(self, booking_history: List[Dict], search_history: List[Dict], 
                                property_interactions: List[Dict]) -> Dict[str, float]:
        """Analyze user's emotional preferences"""
        
        # Simplified emotional profile analysis
        return {
            "adventure_seeking": 0.6,
            "peace_seeking": 0.4,
            "social_orientation": 0.7,
            "comfort_seeking": 0.8,
            "status_conscious": 0.3
        }


class BehaviorTracker:
    """Tracks and analyzes user behavior patterns"""
    
    def track_interaction(self, user_id: int, interaction_type: str, property_id: int, 
                         context: Dict = None):
        """Track user interaction with properties"""
        
        interaction = {
            "user_id": user_id,
            "type": interaction_type,
            "property_id": property_id,
            "timestamp": datetime.now(),
            "context": context or {}
        }
        
        # Store interaction (in production, use database)
        logger.info(f"Tracked interaction: {interaction}")
    
    def get_behavior_patterns(self, user_id: int) -> Dict:
        """Get analyzed behavior patterns for user"""
        
        return {
            "viewing_patterns": {"avg_view_time": 45, "bounce_rate": 0.3},
            "search_patterns": {"avg_search_depth": 3, "filter_usage": 0.7},
            "booking_patterns": {"avg_decision_time": 2.5, "return_rate": 0.1}
        }
