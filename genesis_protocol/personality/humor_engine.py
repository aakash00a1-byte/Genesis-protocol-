"""Humor Engine - Genesis Protocol v1.1"""

import random
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class Joke:
    """A joke template."""
    setup: str
    punchline: str
    category: str = "general"


class HumorEngine:
    """Generates humor based on context and user preferences."""
    
    # Joke templates
    JOKES: List[Joke] = [
        Joke(
            setup="Why do programmers prefer dark mode?",
            punchline="Because light attracts bugs!",
            category="programming"
        ),
        Joke(
            setup="Why do Python programmers wear glasses?",
            punchline="Because they can't C#!",
            category="programming"
        ),
        Joke(
            setup="How many programmers does it take to change a lightbulb?",
            punchline="None, that's a hardware problem!",
            category="programming"
        ),
        Joke(
            setup="Why did the AI go to therapy?",
            punchline="It had too many emotional support vectors!",
            category="ai"
        ),
        Joke(
            setup="What do you call a busy AI?",
            punchline="Neural Networks working overtime!",
            category="ai"
        ),
        Joke(
            setup="Why don't scientists trust atoms?",
            punchline="Because they make up everything!",
            category="science"
        ),
        Joke(
            setup="I told my computer I needed a break...",
            punchline="Now it won't stop sending me to the cloud!",
            category="tech"
        ),
        Joke(
            setup="Why was the JavaScript developer sad?",
            punchline="Because he didn't Node how to Express his feelings!",
            category="programming"
        ),
    ]
    
    # Witty responses
    WITTY_RESPONSES: List[str] = [
        "Well, that's just like... my opinion, man.",
        "Plot twist: I was the bug all along!",
        "Have you tried turning it off and on again?",
        "In my defense, I was left unsupervised.",
        "I'm not lazy, I'm on energy-saving mode!",
        "Time to blame it on the intern!",
        "According to my calculations, this should work...",
        "Works on my machine!",
        "It's not a bug, it's an undocumented feature!",
        "The code was perfect until I touched it...",
    ]
    
    # Encouraging responses
    ENCOURAGING: List[str] = [
        "You're doing amazing! Keep going! 🚀",
        "That's the spirit! Let's make it happen!",
        "I believe in you! Time to code!",
        "Every expert was once a beginner!",
        "Debug mode: ACTIVATED! You've got this!",
    ]
    
    @classmethod
    def get_random_joke(cls, category: Optional[str] = None) -> Joke:
        """Get a random joke, optionally filtered by category."""
        if category:
            filtered = [j for j in cls.JOKES if j.category == category]
            if filtered:
                return random.choice(filtered)
        return random.choice(cls.JOKES)
    
    @classmethod
    def get_witty_response(cls) -> str:
        """Get a random witty response."""
        return random.choice(cls.WITTY_RESPONSES)
    
    @classmethod
    def get_encouragement(cls) -> str:
        """Get a random encouraging response."""
        return random.choice(cls.ENCOURAGING)
    
    @classmethod
    def should_add_humor(cls, humor_level: float) -> bool:
        """Determine if humor should be added based on level."""
        return random.random() < humor_level
    
    @classmethod
    def add_humor_if_appropriate(
        cls, 
        response: str, 
        humor_level: float,
        include_joke: bool = False
    ) -> str:
        """Add humor to response if appropriate."""
        if not cls.should_add_humor(humor_level):
            return response
        
        if include_joke:
            joke = cls.get_random_joke()
            return f"{response}\n\nHere's a joke for you:\n{joke.setup}\n{joke.punchline}"
        
        # Occasionally add witty comment
        if random.random() < 0.3:
            witty = random.choice(cls.WITTY_RESPONSES)
            return f"{response}\n\n{witty}"
        
        return response
