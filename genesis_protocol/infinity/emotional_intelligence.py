"""
Emotional Intelligence Module - Genesis Protocol ∞

Emotional understanding and empathetic responses.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path


class Emotion:
    """Emotion representation"""
    
    EMOTIONS = {
        "happy": {"emoji": "😊", "weight": 1.0},
        "sad": {"emoji": "😢", "weight": -0.8},
        "angry": {"emoji": "😠", "weight": -0.9},
        "fear": {"emoji": "😨", "weight": -0.7},
        "surprise": {"emoji": "😲", "weight": 0.3},
        "love": {"emoji": "❤️", "weight": 0.9},
        "excited": {"emoji": "🎉", "weight": 0.9},
        "confused": {"emoji": "🤔", "weight": -0.2},
        "neutral": {"emoji": "😐", "weight": 0.0},
        "grateful": {"emoji": "🙏", "weight": 0.8},
        "anxious": {"emoji": "😰", "weight": -0.6},
        "hopeful": {"emoji": "🤞", "weight": 0.7},
    }
    
    def __init__(self, emotion_type: str, intensity: float = 0.5):
        self.type = emotion_type
        self.intensity = min(1.0, max(0.0, intensity))
        self.emoji = self.EMOTIONS.get(emotion_type, {}).get("emoji", "😐")
        self.weight = self.EMOTIONS.get(emotion_type, {}).get("weight", 0.0) * self.intensity
    
    def to_dict(self) -> Dict:
        return {
            "type": self.type,
            "intensity": self.intensity,
            "emoji": self.emoji,
            "weight": self.weight
        }


class EmotionalState:
    """User's emotional state over time"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.current_emotion = Emotion("neutral")
        self.emotion_history: List[Dict] = []
        self.average_valence = 0.0
        self.dominant_emotions: Dict[str, int] = {}
    
    def update(self, emotion: Emotion):
        """Update emotional state"""
        self.current_emotion = emotion
        
        self.emotion_history.append({
            "timestamp": datetime.now().isoformat(),
            "emotion": emotion.to_dict()
        })
        
        # Keep last 50 emotions
        if len(self.emotion_history) > 50:
            self.emotion_history = self.emotion_history[-50:]
        
        # Update average valence
        if self.emotion_history:
            self.average_valence = sum(
                e['emotion']['weight'] for e in self.emotion_history
            ) / len(self.emotion_history)
        
        # Update dominant emotions
        emotion_type = emotion.type
        self.dominant_emotions[emotion_type] = self.dominant_emotions.get(emotion_type, 0) + 1
    
    def to_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "current_emotion": self.current_emotion.to_dict(),
            "emotion_count": len(self.emotion_history),
            "average_valence": self.average_valence,
            "dominant_emotions": self.dominant_emotions
        }


class EmotionalEngine:
    """
    Genesis Protocol Emotional Intelligence Engine
    
    Features:
    - Emotion detection
    - Empathetic responses
    - User emotional tracking
    - Mood-appropriate responses
    """
    
    def __init__(self, storage_path: str = "data/infinity/emotions"):
        self.storage_path = storage_path
        Path(storage_path).mkdir(parents=True, exist_ok=True)
        
        # Emotion keywords for detection
        self.emotion_keywords = {
            "happy": ["happy", "joy", "glad", "pleased", "great", "awesome", "amazing", "wonderful", "good", "nice"],
            "sad": ["sad", "unhappy", "depressed", "down", "upset", "disappointed", "bad", "terrible", "awful"],
            "angry": ["angry", "mad", "furious", "annoyed", "irritated", "frustrated", "hate"],
            "fear": ["scared", "afraid", "worried", "nervous", "anxious", "terrified", "panic"],
            "surprise": ["wow", "surprise", "shocked", "unexpected", "amazing", "incredible"],
            "love": ["love", "adore", "like", "care", "heart", "miss", "appreciate"],
            "excited": ["excited", "thrilled", "pumped", "can't wait", "eager", "enthusiastic"],
            "confused": ["confused", "puzzled", "don't understand", "unclear", "lost", "what"],
            "grateful": ["thank", "thanks", "grateful", "appreciate", "blessed"],
            "anxious": ["anxious", "worried", "nervous", "stressed", "tense", "uneasy"],
            "hopeful": ["hope", "hopeful", "optimistic", "looking forward", "wish"],
        }
        
        # User emotional states
        self.user_states: Dict[str, EmotionalState] = {}
        
        # Response templates for emotions
        self.emotion_responses = {
            "happy": ["That's wonderful to hear! 😊", "I'm so happy for you!", "Great to see you in good spirits!"],
            "sad": ["I'm sorry you're feeling down. 😢", "That sounds tough. I'm here.", "I'm here if you need to talk."],
            "angry": ["I understand you're frustrated. 😠", "Let's work through this together.", "Take a deep breath, we'll figure it out."],
            "fear": ["I understand. Let's take it step by step.", "Don't worry, I'm here to help.", "We can work through your concerns."],
            "surprise": ["Wow, that's unexpected! 😲", "What an interesting situation!", "Tell me more about this!"],
            "love": ["That's so sweet! ❤️", "I appreciate your kind words!", "Thank you for sharing that!"],
            "excited": ["I'm excited too! 🎉", "That sounds amazing!", "Tell me more!"],
            "confused": ["I understand this is confusing.", "Let me help clarify.", "We can break it down together."],
            "grateful": ["You're welcome! 🙏", "Happy to help!", "It's my pleasure!"],
            "anxious": ["I understand your concern.", "Take it easy, we'll figure it out.", "I'm here to help."],
            "hopeful": ["I hope it works out for you! 🤞", "That sounds promising!", "Keep up the hope!"],
        }
        
        self._load()
    
    def _load(self):
        """Load saved emotional states"""
        states_file = os.path.join(self.storage_path, "user_states.json")
        if os.path.exists(states_file):
            try:
                with open(states_file, 'r') as f:
                    data = json.load(f)
                    for user_id, state_data in data.items():
                        state = EmotionalState(user_id)
                        state.emotion_history = state_data.get('emotion_history', [])
                        state.average_valence = state_data.get('average_valence', 0.0)
                        state.dominant_emotions = state_data.get('dominant_emotions', {})
                        if state.emotion_history:
                            last = state.emotion_history[-1]['emotion']
                            state.current_emotion = Emotion(last['type'], last['intensity'])
                        self.user_states[user_id] = state
            except Exception as e:
                print(f"Error loading emotional states: {e}")
    
    def _save(self):
        """Save emotional states"""
        states_data = {}
        for user_id, state in self.user_states.items():
            states_data[user_id] = {
                "emotion_history": state.emotion_history,
                "average_valence": state.average_valence,
                "dominant_emotions": state.dominant_emotions
            }
        
        states_file = os.path.join(self.storage_path, "user_states.json")
        with open(states_file, 'w') as f:
            json.dump(states_data, f, indent=2)
    
    def detect_emotion(self, text: str) -> Emotion:
        """
        Detect emotion from text
        
        Args:
            text: Text to analyze
        
        Returns:
            Detected Emotion
        """
        text_lower = text.lower()
        
        # Count emotion keywords
        emotion_scores: Dict[str, float] = {}
        
        for emotion, keywords in self.emotion_keywords.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                emotion_scores[emotion] = score
        
        if not emotion_scores:
            return Emotion("neutral")
        
        # Get highest scoring emotion
        top_emotion = max(emotion_scores.items(), key=lambda x: x[1])
        
        # Calculate intensity based on keyword count
        intensity = min(1.0, top_emotion[1] * 0.3 + 0.3)
        
        return Emotion(top_emotion[0], intensity)
    
    def analyze_and_respond(self, text: str, user_id: str = "default") -> Dict[str, Any]:
        """
        Analyze emotion and generate response
        
        Args:
            text: User input
            user_id: User identifier
        
        Returns:
            Dict with emotion analysis and response
        """
        emotion = self.detect_emotion(text)
        
        # Update user state
        if user_id not in self.user_states:
            self.user_states[user_id] = EmotionalState(user_id)
        
        self.user_states[user_id].update(emotion)
        self._save()
        
        # Generate empathetic response
        response = self._generate_empathetic_response(emotion)
        
        return {
            "detected_emotion": emotion.to_dict(),
            "empathetic_response": response,
            "emotional_state": self.user_states[user_id].to_dict()
        }
    
    def _generate_empathetic_response(self, emotion: Emotion) -> str:
        """Generate empathetic response based on emotion"""
        emotion_type = emotion.type
        
        if emotion_type in self.emotion_responses:
            responses = self.emotion_responses[emotion_type]
            # Weight selection by intensity
            if emotion.intensity > 0.7:
                return responses[0]  # More enthusiastic
            else:
                return responses[1] if len(responses) > 1 else responses[0]
        
        return "I understand. Tell me more."  # Default neutral response
    
    def get_user_emotion(self, user_id: str) -> Optional[EmotionalState]:
        """Get user's emotional state"""
        return self.user_states.get(user_id)
    
    def get_all_users(self) -> List[str]:
        """Get all tracked users"""
        return list(self.user_states.keys())
    
    def get_status(self) -> Dict:
        """Get emotional engine status"""
        return {
            "tracked_users": len(self.user_states),
            "emotion_keywords": sum(len(kw) for kw in self.emotion_keywords.values()),
            "emotion_templates": len(self.emotion_responses),
            "average_valence": sum(
                s.average_valence for s in self.user_states.values()
            ) / max(1, len(self.user_states))
        }


# Singleton instance
_instance = None

def get_emotional_engine() -> EmotionalEngine:
    """Get singleton instance"""
    global _instance
    if _instance is None:
        _instance = EmotionalEngine()
    return _instance
