"""Tests for genesis_protocol.ai.enhancements module."""

import pytest
from genesis_protocol.ai.enhancements import (
    MultilingualProcessor, EmotionalIntelligence, DataVisualizer,
    NLPProcessor, AutomatedLearner, SecurityFeatures,
    analyze_message, Language, Emotion
)


class TestMultilingualProcessor:
    """Tests for multilingual support."""
    
    def test_detect_english(self):
        """Test English detection."""
        ml = MultilingualProcessor()
        assert ml.detect_language("Hello, how are you?") == Language.ENGLISH
    
    def test_detect_hindi(self):
        """Test Hindi detection."""
        ml = MultilingualProcessor()
        assert ml.detect_language("नमस्ते, कैसे हैं आप?") == Language.HINDI
        assert ml.detect_language("haan, mai theek hoon") == Language.HINDI
    
    def test_detect_spanish(self):
        """Test Spanish detection."""
        ml = MultilingualProcessor()
        assert ml.detect_language("Hola, como estas?") == Language.SPANISH
    
    def test_get_greeting(self):
        """Test greetings in different languages."""
        ml = MultilingualProcessor()
        assert "Hello" in ml.get_greeting(Language.ENGLISH)
        assert "नमस्ते" in ml.get_greeting(Language.HINDI)


class TestEmotionalIntelligence:
    """Tests for emotional intelligence."""
    
    def test_positive_sentiment(self):
        """Test positive sentiment detection."""
        ei = EmotionalIntelligence()
        score = ei.analyze_sentiment("I am so happy and excited today!")
        assert score > 0
    
    def test_negative_sentiment(self):
        """Test negative sentiment detection."""
        ei = EmotionalIntelligence()
        score = ei.analyze_sentiment("I am sad and angry about this.")
        assert score < 0
    
    def test_detect_happy_emotion(self):
        """Test happy emotion detection."""
        ei = EmotionalIntelligence()
        emotions = ei.detect_emotions("I'm so happy and excited!")
        assert Emotion.HAPPY in emotions or Emotion.EXCITED in emotions
    
    def test_detect_sad_emotion(self):
        """Test sad emotion detection."""
        ei = EmotionalIntelligence()
        emotions = ei.detect_emotions("I feel so sad and depressed.")
        assert Emotion.SAD in emotions
    
    def test_emotional_response_positive(self):
        """Test emotional response for positive."""
        ei = EmotionalIntelligence()
        response = ei.get_emotional_response({Emotion.HAPPY: 0.8}, 0.8)
        assert "glad" in response.lower() or "wonderful" in response.lower()


class TestDataVisualizer:
    """Tests for data visualization."""
    
    def test_create_bar_chart(self):
        """Test bar chart creation."""
        dv = DataVisualizer()
        data = {"A": 50, "B": 30, "C": 20}
        chart = dv.create_chart(data, "bar")
        assert "Bar Chart" in chart
        assert "A" in chart
        assert "B" in chart
    
    def test_create_pie_chart(self):
        """Test pie chart creation."""
        dv = DataVisualizer()
        data = {"A": 50, "B": 50}
        chart = dv.create_chart(data, "pie")
        assert "Pie Chart" in chart
    
    def test_empty_data(self):
        """Test empty data handling."""
        dv = DataVisualizer()
        chart = dv.create_chart({}, "bar")
        assert "No data" in chart


class TestNLPProcessor:
    """Tests for NLP processing."""
    
    def test_extract_intent_greeting(self):
        """Test greeting intent."""
        nlp = NLPProcessor()
        assert nlp.extract_intent("Hello there!") == "greeting"
    
    def test_extract_intent_question(self):
        """Test question intent."""
        nlp = NLPProcessor()
        assert nlp.extract_intent("What is AI?") == "question"
    
    def test_extract_intent_thanks(self):
        """Test thanks intent."""
        nlp = NLPProcessor()
        assert nlp.extract_intent("Thank you so much!") == "thanks"
    
    def test_extract_entities(self):
        """Test entity extraction."""
        nlp = NLPProcessor()
        entities = nlp.extract_entities("My name is John and I am 25 years old")
        assert len(entities) > 0
    
    def test_enhance_prompt(self):
        """Test prompt enhancement."""
        nlp = NLPProcessor()
        enhanced = nlp.enhance_prompt("Hello", "greeting", "happy")
        assert "Hello" in enhanced


class TestAutomatedLearner:
    """Tests for automated learning."""
    
    def test_learn_from_interaction(self):
        """Test learning from interaction."""
        learner = AutomatedLearner()
        learner.learn_from_interaction(123, "My name is John", "Hello John!", 0.8)
        assert 123 in learner.learned_facts
    
    def test_update_knowledge(self):
        """Test updating knowledge."""
        learner = AutomatedLearner()
        learner.update_knowledge(123, "favorite_color", "blue")
        assert "favorite_color" in str(learner.learned_facts.get(123, []))


class TestSecurityFeatures:
    """Tests for security features."""
    
    def test_detect_credit_card(self):
        """Test credit card detection."""
        sec = SecurityFeatures()
        detected = sec.detect_sensitive_data("My card is 1234567890123456")
        assert len(detected) > 0
    
    def test_detect_password(self):
        """Test password detection."""
        sec = SecurityFeatures()
        detected = sec.detect_sensitive_data("password = mysecretpass")
        assert len(detected) > 0
    
    def test_mask_credit_card(self):
        """Test credit card masking."""
        sec = SecurityFeatures()
        masked = sec.mask_sensitive_data("Card: 1234567890123456")
        assert "****" in masked
        assert "1234" not in masked


class TestAnalyzeMessage:
    """Tests for comprehensive message analysis."""
    
    def test_full_analysis(self):
        """Test full message analysis."""
        result = analyze_message("Hello! I'm so excited about AI!")
        assert result.language == Language.ENGLISH
        assert result.sentiment_score > 0
        assert result.intent == "greeting"
