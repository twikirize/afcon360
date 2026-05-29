# AI-Powered Conversational Search Service
import openai
from typing import List, Dict, Optional
import json
import re
from datetime import datetime, date, timedelta

class AISearchService:
    """Revolutionary AI search that understands natural language and intent"""
    
    def __init__(self):
        self.client = openai.OpenAI()
        self.conversation_context = {}
    
    def conversational_search(self, user_query: str, user_id: int, context: Dict = None) -> Dict:
        """
        Natural language search with context awareness
        Examples:
        - "I need a quiet place near the stadium for 3 nights, budget under $100"
        - "Show me romantic getaways with hot tubs"
        - "Find business hotels with good WiFi and meeting rooms"
        """
        
        # Extract intent and parameters using AI
        intent_analysis = self._analyze_search_intent(user_query, context)
        
        # Build search parameters
        search_params = self._build_search_params(intent_analysis)
        
        # Execute enhanced search
        results = self._execute_intelligent_search(search_params, user_id)
        
        # Generate natural language response
        response = self._generate_ai_response(user_query, results, intent_analysis)
        
        return {
            "results": results,
            "ai_response": response,
            "search_params": search_params,
            "conversation_id": self._get_conversation_id(user_id)
        }
    
    def _analyze_search_intent(self, query: str, context: Dict) -> Dict:
        """Use AI to understand search intent and extract parameters"""
        
        prompt = f"""
        Analyze this accommodation search query and extract structured parameters:
        
        Query: "{query}"
        Context: {context or {}}
        
        Extract:
        - location (city, venue, neighborhood)
        - dates (check_in, check_out, flexibility)
        - guests (adults, children, rooms)
        - budget (min_price, max_price, currency)
        - property_type (hotel, apartment, house, etc.)
        - amenities (WiFi, parking, pool, etc.)
        - atmosphere (quiet, romantic, business, family)
        - special_requirements (pet-friendly, accessible, etc.)
        - urgency level (immediate, planning, flexible)
        
        Return JSON format.
        """
        
        response = self.client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        
        return json.loads(response.choices[0].message.content)
    
    def _build_search_params(self, intent: Dict) -> Dict:
        """Convert AI intent to search parameters"""
        return {
            "location": intent.get("location"),
            "check_in": self._parse_dates(intent.get("dates", {}).get("check_in")),
            "check_out": self._parse_dates(intent.get("dates", {}).get("check_out")),
            "guests": intent.get("guests", {}).get("adults", 2),
            "price_range": (
                intent.get("budget", {}).get("min_price"),
                intent.get("budget", {}).get("max_price")
            ),
            "amenities": intent.get("amenities", []),
            "property_type": intent.get("property_type"),
            "atmosphere": intent.get("atmosphere"),
            "flexibility": intent.get("dates", {}).get("flexibility", 0)
        }
    
    def _execute_intelligent_search(self, params: Dict, user_id: int) -> List[Dict]:
        """Execute search with AI-enhanced ranking"""
        from app.accommodation.services.search_service import search_service
        
        # Get base results
        base_results = search_service.search_properties(
            city=params.get("location"),
            check_in=params.get("check_in"),
            check_out=params.get("check_out"),
            guests=params.get("guests")
        )
        
        # Apply AI ranking based on user preferences and intent
        ranked_results = self._ai_rank_results(base_results, params, user_id)
        
        return ranked_results
    
    def _ai_rank_results(self, results: List[Dict], params: Dict, user_id: int) -> List[Dict]:
        """Use AI to rank results based on user preferences and intent"""
        
        # Get user preferences and history
        user_profile = self._get_user_profile(user_id)
        
        # Score each property
        scored_results = []
        for result in results:
            score = self._calculate_property_score(result, params, user_profile)
            result["ai_score"] = score
            scored_results.append(result)
        
        # Sort by AI score
        return sorted(scored_results, key=lambda x: x["ai_score"], reverse=True)
    
    def _calculate_property_score(self, property: Dict, search_params: Dict, user_profile: Dict) -> float:
        """Calculate AI score for property matching"""
        score = 0.0
        
        # Base relevance (price, location, capacity)
        if search_params.get("price_range"):
            min_price, max_price = search_params["price_range"]
            if min_price <= property["price"] <= max_price:
                score += 0.3
        
        # Amenities matching
        if search_params.get("amenities"):
            matching_amenities = set(search_params["amenities"]) & set(property.get("amenities", []))
            score += len(matching_amenities) * 0.1
        
        # User preference learning
        if user_profile.get("preferences"):
            score += self._calculate_preference_score(property, user_profile["preferences"])
        
        # Atmosphere matching
        if search_params.get("atmosphere"):
            score += self._calculate_atmosphere_score(property, search_params["atmosphere"])
        
        # Quality signals (reviews, rating, verification)
        score += (property.get("rating", 0) / 5) * 0.2
        if property.get("is_verified"):
            score += 0.1
        
        return min(score, 1.0)  # Cap at 1.0
    
    def _generate_ai_response(self, query: str, results: List[Dict], intent: Dict) -> str:
        """Generate natural language response"""
        
        if not results:
            return f"I couldn't find any properties matching your request for {intent.get('location', 'that location')}. Would you like me to adjust the search criteria or dates?"
        
        top_result = results[0]
        response = f"I found {len(results)} great options for you! "
        
        if intent.get("atmosphere"):
            response += f"The best {intent['atmosphere']} choice is "
        else:
            response += "I'd recommend "
        
        response += f"{top_result['name']} at ${top_result['price']}/night. "
        
        if top_result.get("rating"):
            response += f"It has a {top_result['rating']}/5 rating "
        
        if top_result.get("amenities"):
            top_amenities = top_result["amenities"][:3]
            response += f"and offers {', '.join(top_amenities)}. "
        
        response += f"Would you like to see more details about this property or explore other options?"
        
        return response
    
    def _get_user_profile(self, user_id: int) -> Dict:
        """Get user preferences and booking history"""
        # Implement user profile retrieval
        return {
            "preferences": {},
            "booking_history": [],
            "search_history": []
        }
    
    def _parse_dates(self, date_str: str) -> Optional[date]:
        """Parse flexible date expressions"""
        if not date_str:
            return None
        
        try:
            # Handle "tomorrow", "next weekend", "this Friday"
            today = date.today()
            
            if date_str.lower() == "tomorrow":
                return today + timedelta(days=1)
            elif date_str.lower() == "today":
                return today
            elif "next weekend" in date_str.lower():
                days_until_saturday = (5 - today.weekday()) % 7
                return today + timedelta(days=days_until_saturday)
            
            # Try standard date parsing
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except:
            return None
    
    def _get_conversation_id(self, user_id: int) -> str:
        """Get or create conversation ID for user"""
        if user_id not in self.conversation_context:
            self.conversation_context[user_id] = f"conv_{user_id}_{datetime.now().timestamp()}"
        return self.conversation_context[user_id]
