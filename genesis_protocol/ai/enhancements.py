"""Genesis Protocol - AI Enhancements

Advanced features for Genesis Protocol:
- Multilingual support
- Emotional intelligence
- Data visualization
- Advanced NLP
- Automated learning
"""

import re
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class Language(Enum):
    ENGLISH = "en"
    HINDI = "hi"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    CHINESE = "zh"
    JAPANESE = "ja"
    UNKNOWN = "unknown"


class Emotion(Enum):
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    FEARFUL = "fearful"
    SURPRISED = "surprised"
    NEUTRAL = "neutral"
    EXCITED = "excited"
    CONFUSED = "confused"
    LOVING = "loving"
    WORRIED = "worried"


@dataclass
class AnalysisResult:
    language: Language
    emotions: Dict[Emotion, float]
    sentiment_score: float  # -1 to 1
    intent: str
    entities: List[str]
    context_importance: float  # 0 to 1


class MultilingualProcessor:
    """Handle multiple languages."""
    
    HINDI_PATTERNS = [
        r'[\u0900-\u097F]+',  # Hindi/Devanagari script
        r'\b(haan|nahi|kyun|kya|kaise|kaha|kaun|kab|kitna|bohot|thoda|sahi|galat|bilkul|bas|phir|lekin|aur|ya|to|hi|si|ji|jiye|jiyo)\b',
        r'(हाँ|नहीं|क्यों|क्या|कैसे|कहा|कौन|कब|कितना|बहुत|थोड़ा|सही|गलत|बिल्कुल|लेकिन|और|या|तो|ही)',
    ]
    
    SPANISH_PATTERNS = [
        r'\b(hola|gracias|si|no|como|que|cuando|donde|quien|cual|porque|bien|mal|muy|pero|y|o)\b',
    ]
    
    FRENCH_PATTERNS = [
        r'\b(bonjour|merci|oui|non|comment|que|pourquoi|quand|ou|qui|le|la|les|et|ou|mais|donc)\b',
    ]
    
    def detect_language(self, text: str) -> Language:
        """Detect language from text."""
        text_lower = text.lower()
        
        # Check Hindi
        for pattern in self.HINDI_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return Language.HINDI
        
        # Check Spanish
        if re.search(r'\b(hola|gracias|como|porque)\b', text_lower):
            return Language.SPANISH
        
        # Check French
        if re.search(r'\b(bonjour|merci|comment|pourquoi)\b', text_lower):
            return Language.FRENCH
        
        # Check German
        if re.search(r'\b(danke|guten|wie|warum|wann|wo|wer|ist|das|und|oder|aber)\b', text_lower):
            return Language.GERMAN
        
        # Check Chinese
        if re.search(r'[\u4e00-\u9fff]', text):
            return Language.CHINESE
        
        # Check Japanese
        if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text):
            return Language.JAPANESE
        
        return Language.ENGLISH
    
    def get_greeting(self, language: Language) -> str:
        """Get greeting in target language."""
        greetings = {
            Language.ENGLISH: "Hello! How can I help you?",
            Language.HINDI: "नमस्ते! मैं आपकी कैसे मदद कर सकता हूं?",
            Language.SPANISH: "¡Hola! ¿Cómo puedo ayudarte?",
            Language.FRENCH: "Bonjour! Comment puis-je vous aider?",
            Language.GERMAN: "Hallo! Wie kann ich Ihnen helfen?",
            Language.CHINESE: "你好！有什么我可以帮助你的吗？",
            Language.JAPANESE: "こんにちは！何かお手伝いできることはありますか？",
        }
        return greetings.get(language, greetings[Language.ENGLISH])


class EmotionalIntelligence:
    """Analyze emotions and sentiment."""
    
    POSITIVE_WORDS = {
        'happy', 'great', 'awesome', 'amazing', 'excellent', 'wonderful', 'fantastic',
        'love', 'good', 'best', 'beautiful', 'perfect', 'brilliant', 'lovely',
        'excited', 'thrilled', 'delighted', 'pleased', 'grateful', 'thankful',
        'उत्साहित', 'खुश', 'बढ़िया', 'शानदार', 'अद्भुत',
    }
    
    NEGATIVE_WORDS = {
        'sad', 'bad', 'terrible', 'awful', 'horrible', 'angry', 'upset',
        'disappointed', 'frustrated', 'annoyed', 'hate', 'worst', 'sucks',
        'depressed', 'anxious', 'scared', 'afraid', 'nervous',
        'निराश', 'उदास', 'परेशान', 'डर', 'गुस्सा', 'बुरा',
    }
    
    EMOTION_PATTERNS = {
        Emotion.HAPPY: ['happy', 'joy', 'glad', 'pleased', 'खुश', 'उत्साहित'],
        Emotion.SAD: ['sad', 'unhappy', 'depressed', 'down', 'उदास', 'निराश'],
        Emotion.ANGRY: ['angry', 'mad', 'furious', 'annoyed', 'गुस्सा', 'नाराज'],
        Emotion.EXCITED: ['excited', 'thrilled', 'pumped', 'awesome', 'जोश'],
        Emotion.CONFUSED: ['confused', 'puzzled', 'unclear', 'help', 'समझ नहीं आया'],
        Emotion.WORRIED: ['worried', 'anxious', 'concerned', 'fear', 'डर', 'चिंतित'],
        Emotion.LOVING: ['love', 'adore', 'care', 'miss', 'love', 'प्यार'],
        Emotion.SURPRISED: ['wow', 'surprised', 'shocked', 'unbelievable', 'वाह'],
    }
    
    def analyze_sentiment(self, text: str) -> float:
        """Return sentiment score from -1 to 1."""
        text_lower = text.lower()
        words = set(re.findall(r'\w+', text_lower))
        
        score = 0
        count = 0
        
        for word in words:
            if word in self.POSITIVE_WORDS:
                score += 0.3
                count += 1
            elif word in self.NEGATIVE_WORDS:
                score -= 0.3
                count += 1
        
        if count == 0:
            return 0.0
        
        return max(-1.0, min(1.0, score / max(count, 1)))
    
    def detect_emotions(self, text: str) -> Dict[Emotion, float]:
        """Detect emotions from text."""
        text_lower = text.lower()
        emotions = {}
        
        for emotion, patterns in self.EMOTION_PATTERNS.items():
            score = 0
            for pattern in patterns:
                if pattern in text_lower:
                    score += 0.5
            if score > 0:
                emotions[emotion] = min(1.0, score)
        
        if not emotions:
            emotions[Emotion.NEUTRAL] = 1.0
        
        return emotions
    
    def get_emotional_response(self, emotions: Dict[Emotion, float], sentiment: float) -> str:
        """Generate emotionally appropriate response prefix."""
        if Emotion.EXCITED in emotions or sentiment > 0.7:
            return "That's wonderful! 🎉"
        elif Emotion.HAPPY in emotions or sentiment > 0.3:
            return "I'm glad to hear that! 😊"
        elif Emotion.SAD in emotions or sentiment < -0.5:
            return "I'm sorry you're feeling that way. 💙"
        elif Emotion.ANGRY in emotions or sentiment < -0.7:
            return "I understand you're frustrated. Let me help."
        elif Emotion.WORRIED in emotions:
            return "Don't worry, I'm here to help! 🤗"
        elif Emotion.CONFUSED in emotions:
            return "Let me clarify that for you! 💡"
        return ""


class DataVisualizer:
    """Generate data visualizations."""
    
    @staticmethod
    def create_chart(data: Dict[str, float], chart_type: str = "bar") -> str:
        """Create ASCII chart from data."""
        if not data:
            return "No data to display."
        
        max_val = max(data.values())
        lines = []
        
        if chart_type == "bar":
            lines.append("📊 Bar Chart:")
            for label, value in sorted(data.items(), key=lambda x: x[1], reverse=True):
                bar_len = int((value / max_val) * 20)
                bar = "█" * bar_len
                lines.append(f"{label[:15]:15} │ {bar} {value:.1f}")
        
        elif chart_type == "pie":
            total = sum(data.values())
            lines.append("🥧 Pie Chart:")
            emojis = ["🔴", "🔵", "🟢", "🟡", "🟣", "🟠", "⚪"]
            for i, (label, value) in enumerate(data.items()):
                pct = (value / total) * 100
                emoji = emojis[i % len(emojis)]
                lines.append(f"{emoji} {label[:15]:15} │ {pct:.1f}%")
        
        return "\n".join(lines)
    
    @staticmethod
    def create_table(headers: List[str], rows: List[List[str]]) -> str:
        """Create ASCII table."""
        if not headers or not rows:
            return "No data to display."
        
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))
        
        def format_row(cells):
            return "│ " + " │ ".join(str(c).ljust(w) for c, w in zip(cells, col_widths)) + " │"
        
        separator = "├" + "┼".join("─" * (w + 2) for w in col_widths) + "┤"
        top = "┌" + "┬".join("─" * (w + 2) for w in col_widths) + "┐"
        bottom = "└" + "┴".join("─" * (w + 2) for w in col_widths) + "┘"
        
        lines = [top, format_row(headers), separator]
        for row in rows:
            lines.append(format_row(row))
        lines.append(bottom)
        
        return "\n".join(lines)


class NLPProcessor:
    """Advanced NLP processing."""
    
    INTENT_PATTERNS = {
        'greeting': ['hello', 'hi', 'hey', 'namaste', 'नमस्ते', 'hola', 'bonjour'],
        'question': ['what', 'how', 'why', 'when', 'where', 'who', 'which', 'kya', 'kaise', 'kyun'],
        'request': ['please', 'can you', 'could you', 'would you', 'i need', 'i want'],
        'thanks': ['thank', 'thanks', 'gracias', 'shukriya', 'धन्यवाद'],
        'goodbye': ['bye', 'goodbye', 'see you', 'later', 'take care'],
        'help': ['help', 'assist', 'support', 'guide', 'मदद'],
        'data_query': ['show', 'list', 'display', 'compare', 'analyze'],
        'create': ['create', 'make', 'generate', 'build', 'add', 'new'],
        'update': ['update', 'change', 'modify', 'edit', 'alter'],
        'delete': ['delete', 'remove', 'clear', 'drop'],
    }
    
    def extract_intent(self, text: str) -> str:
        """Extract user intent from text."""
        text_lower = text.lower()
        
        for intent, keywords in self.INTENT_PATTERNS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return intent
        
        return 'general'
    
    def extract_entities(self, text: str) -> List[str]:
        """Extract named entities (simple version)."""
        entities = []
        
        # Extract numbers
        numbers = re.findall(r'\d+(?:\.\d+)?', text)
        entities.extend([f"number:{n}" for n in numbers])
        
        # Extract capitalized words (potential names/places)
        capitals = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        entities.extend(capitals[:5])
        
        # Extract hashtags
        hashtags = re.findall(r'#\w+', text)
        entities.extend(hashtags)
        
        return entities[:10]
    
    def enhance_prompt(self, text: str, intent: str, emotion: str = "neutral") -> str:
        """Enhance prompt with context."""
        emotion_instruction = {
            'happy': "The user seems happy. Be enthusiastic and positive.",
            'sad': "The user seems sad. Be empathetic and supportive.",
            'angry': "The user seems frustrated. Be calm and helpful.",
            'worried': "The user seems concerned. Be reassuring.",
            'neutral': "Be helpful and clear."
        }.get(emotion, "Be helpful and clear.")
        
        intent_instruction = {
            'question': "Answer clearly and provide examples if helpful.",
            'request': "Try to fulfill the request or explain what you can do.",
            'greeting': "Greet warmly and ask how you can help.",
            'data_query': "Provide organized, structured information.",
        }.get(intent, "Provide a helpful response.")
        
        return f"{text}\n\n[Context: {emotion_instruction} {intent_instruction}]"


class AutomatedLearner:
    """Learn from interactions."""
    
    def __init__(self):
        self.learned_facts = {}
        self.preferred_style = {}
        self.user_preferences = {}
    
    def learn_from_interaction(self, user_id: int, query: str, response: str, rating: float = None):
        """Learn from user interaction."""
        if user_id not in self.learned_facts:
            self.learned_facts[user_id] = []
            self.user_preferences[user_id] = {}
        
        # Extract potential facts
        facts = self._extract_facts(query, response)
        self.learned_facts[user_id].extend(facts)
        
        # Track preferences
        if rating is not None:
            if rating > 0.7:
                self.user_preferences[user_id]['detailed'] = True
            elif rating < 0.3:
                self.user_preferences[user_id]['concise'] = True
    
    def _extract_facts(self, query: str, response: str) -> List[str]:
        """Extract facts from conversation."""
        facts = []
        
        # Simple fact extraction
        patterns = [
            r'I like (.+)',
            r'My name is (.+)',
            r'I am (.+) years old',
            r'I work as (.+)',
            r'I live in (.+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                facts.append(match.group(1).strip())
        
        return facts[:5]
    
    def get_knowledge(self, user_id: int) -> str:
        """Get learned knowledge for user."""
        if user_id not in self.learned_facts or not self.learned_facts[user_id]:
            return ""
        
        facts = self.learned_facts[user_id][-10:]
        if facts:
            return f"📚 I've learned about you: {', '.join(facts[-5:])}"
        return ""
    
    def update_knowledge(self, user_id: int, topic: str, value: str):
        """Update knowledge about a topic."""
        if user_id not in self.learned_facts:
            self.learned_facts[user_id] = []
        self.learned_facts[user_id].append(f"{topic}: {value}")


class SecurityFeatures:
    """Security and privacy features."""
    
    SENSITIVE_PATTERNS = [
        r'\b\d{16}\b',  # Credit card
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
        r'password\s*[:=]\s*\S+',
        r'api[_-]?key\s*[:=]\s*\S+',
        r'secret\s*[:=]\s*\S+',
    ]
    
    @staticmethod
    def detect_sensitive_data(text: str) -> List[str]:
        """Detect sensitive data in text."""
        detected = []
        for pattern in SecurityFeatures.SENSITIVE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            detected.extend(matches)
        return detected
    
    @staticmethod
    def mask_sensitive_data(text: str) -> str:
        """Mask sensitive data in text."""
        masked = text
        patterns = [
            (r'\b\d{16}\b', '****-****-****-****'),
            (r'\b\d{3}-\d{2}-\d{4}\b', '***-**-****'),
            (r'(password\s*[:=]\s*)\S+', r'\1*****'),
            (r'(api[_-]?key\s*[:=]\s*)\S+', r'\1*****'),
            (r'(secret\s*[:=]\s*)\S+', r'\1*****'),
        ]
        for pattern, replacement in patterns:
            masked = re.sub(pattern, replacement, masked, flags=re.IGNORECASE)
        return masked
    
    @staticmethod
    def get_privacy_tip() -> str:
        """Get privacy tip."""
        tips = [
            "🔒 Never share your passwords with anyone.",
            "🔒 Use unique passwords for each account.",
            "🔒 Enable two-factor authentication when possible.",
            "🔒 Be careful about what personal info you share online.",
            "🔒 Review app permissions regularly.",
        ]
        import random
        return random.choice(tips)


# Global instances
multilingual = MultilingualProcessor()
emotional = EmotionalIntelligence()
visualizer = DataVisualizer()
nlp = NLPProcessor()
learner = AutomatedLearner()
security = SecurityFeatures()


def analyze_message(text: str) -> AnalysisResult:
    """Analyze a message comprehensively."""
    language = multilingual.detect_language(text)
    emotions = emotional.detect_emotions(text)
    sentiment = emotional.analyze_sentiment(text)
    intent = nlp.extract_intent(text)
    entities = nlp.extract_entities(text)
    
    return AnalysisResult(
        language=language,
        emotions=emotions,
        sentiment_score=sentiment,
        intent=intent,
        entities=entities,
        context_importance=0.8 if intent in ['question', 'request'] else 0.5
    )


def generate_response(text: str, user_id: int = 0, analysis: AnalysisResult = None) -> str:
    """Generate enhanced response."""
    if analysis is None:
        analysis = analyze_message(text)
    
    # Get emotional prefix
    emotion_name = max(analysis.emotions.keys(), key=lambda e: analysis.emotions[e]).name.lower() if analysis.emotions else 'neutral'
    prefix = emotional.get_emotional_response(analysis.emotions, analysis.sentiment_score)
    
    # Get learned knowledge
    knowledge = learner.get_knowledge(user_id) if user_id else ""
    
    return f"{prefix}\n{knowledge}".strip()
