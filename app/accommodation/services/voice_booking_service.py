# Voice-First Booking Experience - Revolutionary Beyond OTA Standards
import speech_recognition as sr
import pyttsx3
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import logging
import json
import asyncio

logger = logging.getLogger(__name__)

class VoiceIntent(Enum):
    SEARCH = "search"
    BOOK = "book"
    MODIFY = "modify"
    CANCEL = "cancel"
    INFO = "info"
    HELP = "help"
    NAVIGATE = "navigate"

class VoiceState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    RESPONDING = "responding"
    ERROR = "error"

@dataclass
class VoiceCommand:
    intent: VoiceIntent
    entities: Dict[str, Union[str, int, float, date]]
    confidence: float
    raw_text: str
    processed_at: datetime

@dataclass
class VoiceResponse:
    text: str
    audio_data: Optional[bytes]
    response_type: str  # "text", "audio", "mixed"
    follow_up_questions: List[str]
    actions_required: List[Dict]

class VoiceBookingService:
    """
    Revolutionary voice-first booking service that enables natural,
    conversational booking experiences beyond current OTA capabilities
    """
    
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.tts_engine = pyttsx3.init()
        self.nlp_processor = VoiceNLPProcessor()
        self.booking_processor = VoiceBookingProcessor()
        self.conversation_manager = VoiceConversationManager()
        self.voice_state = VoiceState.IDLE
        self.active_session = None
    
    def start_voice_session(self, user_id: int, session_type: str = "booking") -> Dict:
        """Start voice booking session"""
        
        # Initialize session
        session_id = self._generate_session_id()
        self.active_session = {
            "session_id": session_id,
            "user_id": user_id,
            "session_type": session_type,
            "started_at": datetime.now(),
            "context": {},
            "conversation_history": [],
            "pending_actions": []
        }
        
        # Welcome message
        welcome_response = self._generate_welcome_message(session_type)
        
        # Start listening
        self.voice_state = VoiceState.LISTENING
        
        return {
            "session_id": session_id,
            "welcome_message": welcome_response,
            "voice_state": self.voice_state,
            "instructions": self._get_voice_instructions()
        }
    
    async def process_voice_input(self, session_id: str, audio_data: bytes) -> VoiceResponse:
        """Process voice input and generate response"""
        
        if not self.active_session or self.active_session["session_id"] != session_id:
            return self._create_error_response("Session not found")
        
        try:
            # Update state
            self.voice_state = VoiceState.PROCESSING
            
            # Convert speech to text
            text = await self._speech_to_text(audio_data)
            
            if not text:
                return self._create_error_response("Could not understand speech")
            
            # Process with NLP
            voice_command = self.nlp_processor.process_command(text)
            
            # Add to conversation history
            self._add_to_conversation_history(text, voice_command)
            
            # Execute command
            response = await self._execute_voice_command(voice_command)
            
            # Update state
            self.voice_state = VoiceState.RESPONDING
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing voice input: {e}")
            self.voice_state = VoiceState.ERROR
            return self._create_error_response("Processing error occurred")
    
    async def _execute_voice_command(self, command: VoiceCommand) -> VoiceResponse:
        """Execute voice command and generate response"""
        
        if command.intent == VoiceIntent.SEARCH:
            return await self._handle_search_command(command)
        elif command.intent == VoiceIntent.BOOK:
            return await self._handle_book_command(command)
        elif command.intent == VoiceIntent.MODIFY:
            return await self._handle_modify_command(command)
        elif command.intent == VoiceIntent.CANCEL:
            return await self._handle_cancel_command(command)
        elif command.intent == VoiceIntent.INFO:
            return await self._handle_info_command(command)
        elif command.intent == VoiceIntent.HELP:
            return await self._handle_help_command(command)
        elif command.intent == VoiceIntent.NAVIGATE:
            return await self._handle_navigate_command(command)
        else:
            return self._create_fallback_response(command)
    
    async def _handle_search_command(self, command: VoiceCommand) -> VoiceResponse:
        """Handle search commands"""
        
        # Extract search parameters
        search_params = self._extract_search_params(command.entities)
        
        # Validate parameters
        validation_result = self._validate_search_params(search_params)
        
        if not validation_result["is_valid"]:
            return self._create_clarification_response(validation_result["missing_fields"])
        
        # Perform search
        search_results = await self._perform_voice_search(search_params)
        
        # Generate response
        response_text = self._generate_search_response(search_results, search_params)
        
        # Generate audio
        audio_data = await self._text_to_speech(response_text)
        
        # Follow-up questions
        follow_up = self._generate_search_follow_up(search_results)
        
        return VoiceResponse(
            text=response_text,
            audio_data=audio_data,
            response_type="mixed",
            follow_up_questions=follow_up,
            actions_required=[{"action": "present_results", "data": search_results}]
        )
    
    async def _handle_book_command(self, command: VoiceCommand) -> VoiceResponse:
        """Handle booking commands"""
        
        # Extract booking parameters
        booking_params = self._extract_booking_params(command.entities)
        
        # Check if we have enough context
        if not self._has_booking_context(booking_params):
            return self._create_booking_clarification_response(booking_params)
        
        # Validate booking
        validation_result = await self._validate_booking(booking_params)
        
        if not validation_result["is_valid"]:
            return self._create_booking_error_response(validation_result["errors"])
        
        # Process booking
        booking_result = await self.booking_processor.process_booking(booking_params)
        
        # Generate response
        response_text = self._generate_booking_response(booking_result)
        
        # Generate audio
        audio_data = await self._text_to_speech(response_text)
        
        return VoiceResponse(
            text=response_text,
            audio_data=audio_data,
            response_type="mixed",
            follow_up_questions=[],
            actions_required=[{"action": "confirm_booking", "data": booking_result}]
        )
    
    async def _handle_modify_command(self, command: VoiceCommand) -> VoiceResponse:
        """Handle modification commands"""
        
        # Identify what to modify
        modification_target = command.entities.get("target")
        modification_params = command.entities.get("params", {})
        
        # Process modification
        modification_result = await self._process_modification(modification_target, modification_params)
        
        # Generate response
        response_text = self._generate_modification_response(modification_result)
        
        # Generate audio
        audio_data = await self._text_to_speech(response_text)
        
        return VoiceResponse(
            text=response_text,
            audio_data=audio_data,
            response_type="mixed",
            follow_up_questions=[],
            actions_required=[{"action": "confirm_modification", "data": modification_result}]
        )
    
    async def _handle_cancel_command(self, command: VoiceCommand) -> VoiceResponse:
        """Handle cancellation commands"""
        
        # Identify what to cancel
        cancellation_target = command.entities.get("target")
        cancellation_reason = command.entities.get("reason", "User requested")
        
        # Process cancellation
        cancellation_result = await self._process_cancellation(cancellation_target, cancellation_reason)
        
        # Generate response
        response_text = self._generate_cancellation_response(cancellation_result)
        
        # Generate audio
        audio_data = await self._text_to_speech(response_text)
        
        return VoiceResponse(
            text=response_text,
            audio_data=audio_data,
            response_type="mixed",
            follow_up_questions=[],
            actions_required=[{"action": "confirm_cancellation", "data": cancellation_result}]
        )
    
    async def _handle_info_command(self, command: VoiceCommand) -> VoiceResponse:
        """Handle information requests"""
        
        # Identify information type
        info_type = command.entities.get("type", "general")
        info_target = command.entities.get("target")
        
        # Get information
        info_result = await self._get_voice_information(info_type, info_target)
        
        # Generate response
        response_text = self._generate_info_response(info_result)
        
        # Generate audio
        audio_data = await self._text_to_speech(response_text)
        
        return VoiceResponse(
            text=response_text,
            audio_data=audio_data,
            response_type="mixed",
            follow_up_questions=self._generate_info_follow_up(info_result),
            actions_required=[]
        )
    
    async def _handle_help_command(self, command: VoiceCommand) -> VoiceResponse:
        """Handle help requests"""
        
        # Generate help response
        response_text = self._generate_help_response()
        
        # Generate audio
        audio_data = await self._text_to_speech(response_text)
        
        return VoiceResponse(
            text=response_text,
            audio_data=audio_data,
            response_type="mixed",
            follow_up_questions=["What would you like to do?"],
            actions_required=[]
        )
    
    async def _handle_navigate_command(self, command: VoiceCommand) -> VoiceResponse:
        """Handle navigation commands"""
        
        # Identify destination
        destination = command.entities.get("destination")
        
        # Generate navigation response
        response_text = self._generate_navigation_response(destination)
        
        # Generate audio
        audio_data = await self._text_to_speech(response_text)
        
        return VoiceResponse(
            text=response_text,
            audio_data=audio_data,
            response_type="mixed",
            follow_up_questions=[],
            actions_required=[{"action": "navigate", "destination": destination}]
        )
    
    def _create_fallback_response(self, command: VoiceCommand) -> VoiceResponse:
        """Create fallback response for unknown commands"""
        
        response_text = f"I'm not sure how to help with '{command.raw_text}'. Could you please rephrase that or ask for help?"
        
        return VoiceResponse(
            text=response_text,
            audio_data=None,
            response_type="text",
            follow_up_questions=["What would you like to do?", "Say 'help' for assistance"],
            actions_required=[]
        )
    
    # Helper methods
    async def _speech_to_text(self, audio_data: bytes) -> str:
        """Convert speech to text"""
        
        try:
            # Use speech recognition
            with sr.AudioFile(audio_data) as source:
                audio = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio)
                return text
        except Exception as e:
            logger.error(f"Speech to text error: {e}")
            return ""
    
    async def _text_to_speech(self, text: str) -> bytes:
        """Convert text to speech"""
        
        try:
            # Use text-to-speech
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()
            
            # In production, capture audio data
            return b"audio_data_placeholder"
        except Exception as e:
            logger.error(f"Text to speech error: {e}")
            return b""
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID"""
        return f"voice_{int(datetime.now().timestamp())}"
    
    def _generate_welcome_message(self, session_type: str) -> str:
        """Generate welcome message"""
        
        welcome_messages = {
            "booking": "Welcome to AFCON360 Voice Booking! I can help you find and book accommodations. What are you looking for?",
            "search": "Hello! I can help you search for accommodations. Where would you like to stay?",
            "help": "Hi! I'm your voice assistant. How can I help you today?"
        }
        
        return welcome_messages.get(session_type, welcome_messages["booking"])
    
    def _get_voice_instructions(self) -> List[str]:
        """Get voice instructions"""
        return [
            "Speak clearly and naturally",
            "You can say things like 'Find hotels in Kampala for 2 people'",
            "I'll ask questions if I need more information",
            "Say 'help' anytime for assistance"
        ]
    
    def _add_to_conversation_history(self, text: str, command: VoiceCommand):
        """Add to conversation history"""
        
        if self.active_session:
            self.active_session["conversation_history"].append({
                "timestamp": datetime.now(),
                "user_input": text,
                "command": command
            })
    
    def _extract_search_params(self, entities: Dict) -> Dict:
        """Extract search parameters from entities"""
        
        return {
            "location": entities.get("location"),
            "check_in": entities.get("check_in"),
            "check_out": entities.get("check_out"),
            "guests": entities.get("guests", 2),
            "price_range": entities.get("price_range"),
            "property_type": entities.get("property_type"),
            "amenities": entities.get("amenities", [])
        }
    
    def _validate_search_params(self, params: Dict) -> Dict:
        """Validate search parameters"""
        
        missing_fields = []
        
        if not params.get("location"):
            missing_fields.append("location")
        
        if not params.get("check_in"):
            missing_fields.append("check_in date")
        
        if not params.get("check_out"):
            missing_fields.append("check_out date")
        
        return {
            "is_valid": len(missing_fields) == 0,
            "missing_fields": missing_fields
        }
    
    def _create_clarification_response(self, missing_fields: List[str]) -> VoiceResponse:
        """Create clarification response"""
        
        field_questions = {
            "location": "Where would you like to stay?",
            "check_in date": "When would you like to check in?",
            "check_out date": "When would you like to check out?",
            "guests": "How many guests will be staying?"
        }
        
        questions = [field_questions.get(field, f"What about {field}?") for field in missing_fields]
        
        response_text = f"I need a bit more information. {questions[0] if len(questions) == 1 else ' and '.join(questions)}"
        
        return VoiceResponse(
            text=response_text,
            audio_data=None,
            response_type="text",
            follow_up_questions=questions,
            actions_required=[]
        )
    
    async def _perform_voice_search(self, params: Dict) -> List[Dict]:
        """Perform voice search"""
        
        # Use existing search service
        from app.accommodation.services.search_service import search_service
        
        results = search_service.search_properties(
            city=params.get("location"),
            check_in=params.get("check_in"),
            check_out=params.get("check_out"),
            guests=params.get("guests", 2)
        )
        
        return results[:5]  # Return top 5 for voice
    
    def _generate_search_response(self, results: List[Dict], params: Dict) -> str:
        """Generate search response"""
        
        if not results:
            return f"I couldn't find any accommodations in {params.get('location', 'that location')}. Would you like to try different dates or a different location?"
        
        response = f"I found {len(results)} great options for you in {params.get('location')}. "
        
        # Describe top 3 results
        for i, result in enumerate(results[:3], 1):
            response += f"Option {i}: {result.get('name', 'Property')} at ${result.get('price', 0)} per night"
            if result.get("rating"):
                response += f" with a {result.get('rating')} star rating"
            response += ". "
        
        response += "Would you like to hear more about any of these, or would you like me to book one for you?"
        
        return response
    
    def _generate_search_follow_up(self, results: List[Dict]) -> List[str]:
        """Generate search follow-up questions"""
        
        if not results:
            return ["Would you like to try different dates?", "How about a different location?"]
        
        return [
            "Would you like more details about any property?",
            "Should I book one of these for you?",
            "Would you like to see more options?"
        ]
    
    def _extract_booking_params(self, entities: Dict) -> Dict:
        """Extract booking parameters"""
        
        return {
            "property_id": entities.get("property_id"),
            "check_in": entities.get("check_in"),
            "check_out": entities.get("check_out"),
            "guests": entities.get("guests", 2),
            "special_requests": entities.get("special_requests", [])
        }
    
    def _has_booking_context(self, params: Dict) -> bool:
        """Check if we have enough booking context"""
        
        required_fields = ["property_id", "check_in", "check_out", "guests"]
        return all(params.get(field) for field in required_fields)
    
    async def _validate_booking(self, params: Dict) -> Dict:
        """Validate booking parameters"""
        
        errors = []
        
        # Check property availability
        if params.get("property_id") and params.get("check_in") and params.get("check_out"):
            # In production, check actual availability
            pass
        
        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }
    
    def _create_booking_clarification_response(self, params: Dict) -> VoiceResponse:
        """Create booking clarification response"""
        
        missing = []
        if not params.get("property_id"):
            missing.append("Which property would you like to book?")
        if not params.get("check_in"):
            missing.append("What's your check-in date?")
        if not params.get("check_out"):
            missing.append("What's your check-out date?")
        
        response_text = f"I need a bit more information to complete your booking. {missing[0] if len(missing) == 1 else ' and '.join(missing)}"
        
        return VoiceResponse(
            text=response_text,
            audio_data=None,
            response_type="text",
            follow_up_questions=missing,
            actions_required=[]
        )
    
    def _create_booking_error_response(self, errors: List[str]) -> VoiceResponse:
        """Create booking error response"""
        
        response_text = f"I'm having trouble with your booking. {errors[0] if errors else 'Something went wrong'}"
        
        return VoiceResponse(
            text=response_text,
            audio_data=None,
            response_type="text",
            follow_up_questions=["Would you like to try again?", "Say 'help' for assistance"],
            actions_required=[]
        )
    
    def _generate_booking_response(self, booking_result: Dict) -> str:
        """Generate booking response"""
        
        if booking_result.get("success"):
            return f"Great! I've booked your accommodation. Your booking reference is {booking_result.get('reference', 'N/A')}. Is there anything else I can help you with?"
        else:
            return f"I'm sorry, I couldn't complete the booking. {booking_result.get('error', 'Please try again')}"
    
    def _create_error_response(self, error_message: str) -> VoiceResponse:
        """Create error response"""
        
        return VoiceResponse(
            text=f"I'm sorry, {error_message}. Please try again.",
            audio_data=None,
            response_type="text",
            follow_up_questions=["Would you like to try again?"],
            actions_required=[]
        )
    
    # Additional helper methods (simplified for demo)
    async def _process_modification(self, target: str, params: Dict) -> Dict:
        return {"success": True, "message": "Modification processed"}  # Mock data
    
    def _generate_modification_response(self, result: Dict) -> str:
        return "I've made the changes you requested."  # Mock data
    
    async def _process_cancellation(self, target: str, reason: str) -> Dict:
        return {"success": True, "message": "Cancellation processed"}  # Mock data
    
    def _generate_cancellation_response(self, result: Dict) -> str:
        return "I've cancelled your booking as requested."  # Mock data
    
    async def _get_voice_information(self, info_type: str, target: str) -> Dict:
        return {"info": "Information retrieved"}  # Mock data
    
    def _generate_info_response(self, info_result: Dict) -> str:
        return "Here's the information you requested."  # Mock data
    
    def _generate_info_follow_up(self, info_result: Dict) -> List[str]:
        return ["Would you like more details?", "Is there anything else?"]  # Mock data
    
    def _generate_help_response(self) -> str:
        return """I can help you with:
        - Finding accommodations
        - Making bookings
        - Getting property information
        - Modifying or cancelling bookings
        - Navigating the app
        
        Just tell me what you need in natural language!"""
    
    def _generate_navigation_response(self, destination: str) -> str:
        return f"I'll take you to {destination or 'the requested page'}."  # Mock data


class VoiceNLPProcessor:
    """Natural language processing for voice commands"""
    
    def process_command(self, text: str) -> VoiceCommand:
        """Process voice command text"""
        
        # Simple intent recognition (in production, use sophisticated NLP)
        text_lower = text.lower()
        
        if any(word in text_lower for word in ["find", "search", "look for", "show me"]):
            intent = VoiceIntent.SEARCH
        elif any(word in text_lower for word in ["book", "reserve", "confirm"]):
            intent = VoiceIntent.BOOK
        elif any(word in text_lower for word in ["change", "modify", "update"]):
            intent = VoiceIntent.MODIFY
        elif any(word in text_lower for word in ["cancel", "stop"]):
            intent = VoiceIntent.CANCEL
        elif any(word in text_lower for word in ["tell me", "what is", "information"]):
            intent = VoiceIntent.INFO
        elif any(word in text_lower for word in ["help", "assist"]):
            intent = VoiceIntent.HELP
        elif any(word in text_lower for word in ["go to", "navigate", "take me"]):
            intent = VoiceIntent.NAVIGATE
        else:
            intent = VoiceIntent.SEARCH  # Default
        
        # Extract entities (simplified)
        entities = self._extract_entities(text)
        
        return VoiceCommand(
            intent=intent,
            entities=entities,
            confidence=0.8,
            raw_text=text,
            processed_at=datetime.now()
        )
    
    def _extract_entities(self, text: str) -> Dict[str, Union[str, int, float, date]]:
        """Extract entities from text"""
        
        entities = {}
        text_lower = text.lower()
        
        # Location extraction
        cities = ["kampala", "nairobi", "jinja", "cairo", "entebbe"]
        for city in cities:
            if city in text_lower:
                entities["location"] = city.title()
                break
        
        # Number extraction
        import re
        numbers = re.findall(r'\b\d+\b', text)
        if numbers:
            if "guest" in text_lower or "person" in text_lower or "people" in text_lower:
                entities["guests"] = int(numbers[0])
            elif "night" in text_lower:
                entities["nights"] = int(numbers[0])
        
        # Date extraction (simplified)
        if "today" in text_lower:
            entities["check_in"] = date.today()
        elif "tomorrow" in text_lower:
            entities["check_in"] = date.today() + timedelta(days=1)
        
        # Price extraction
        price_match = re.search(r'\$(\d+)', text)
        if price_match:
            entities["price"] = float(price_match.group(1))
        
        return entities


class VoiceBookingProcessor:
    """Processor for voice-based bookings"""
    
    async def process_booking(self, params: Dict) -> Dict:
        """Process voice booking"""
        
        # Use existing booking service
        from app.accommodation.services.booking_service import BookingService
        
        try:
            booking, error = BookingService.create_booking(
                property_id=params["property_id"],
                guest_user_id=1,  # Would get from session
                host_user_id=1,  # Would get from property
                check_in=params["check_in"],
                check_out=params["check_out"],
                num_guests=params["guests"],
                guest_name="Voice User",
                guest_email="voice@example.com",
                special_requests=params.get("special_requests", "")
            )
            
            if booking:
                return {
                    "success": True,
                    "reference": booking.booking_reference,
                    "booking_id": booking.id
                }
            else:
                return {
                    "success": False,
                    "error": error
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


class VoiceConversationManager:
    """Manager for voice conversations"""
    
    def __init__(self):
        self.active_conversations = {}
    
    def start_conversation(self, user_id: int, session_id: str):
        """Start new conversation"""
        
        self.active_conversations[session_id] = {
            "user_id": user_id,
            "started_at": datetime.now(),
            "context": {},
            "history": []
        }
    
    def update_context(self, session_id: str, context_update: Dict):
        """Update conversation context"""
        
        if session_id in self.active_conversations:
            self.active_conversations[session_id]["context"].update(context_update)
    
    def get_context(self, session_id: str) -> Dict:
        """Get conversation context"""
        
        return self.active_conversations.get(session_id, {}).get("context", {})
