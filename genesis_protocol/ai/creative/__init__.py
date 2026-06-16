"""
Genesis Protocol - Creative AI Module
======================================
All-in-one creative AI capabilities:
- Image Generation (DALL-E, Stable Diffusion, Leonardo)
- Video Generation (Runway, Pika, Stable Video)
- Story Writing & Creative Content
- Music Generation (Suno, Udio)
- Character Design & Avatars
- 3D Model Generation
"""

import os
import json
import asyncio
import base64
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from datetime import datetime

from genesis_protocol.config import get_config

logger = logging.getLogger(__name__)


# ============================================================
# ENUMS & DATA CLASSES
# ============================================================

class ImageModel(Enum):
    """Available image generation models."""
    DALL_E_3 = "dall-e-3"
    DALL_E_2 = "dall-e-2"
    STABLE_DIFFUSION = "stable-diffusion"
    LEONARDO = "leonardo"
    MIDJOURNEY = "midjourney"


class VideoModel(Enum):
    """Available video generation models."""
    RUNWAY_GEN3 = "runway-gen3"
    PIKA = "pika"
    STABLE_VIDEO = "stable-video"
    KAIBER = "kaiber"


class MusicModel(Enum):
    """Available music generation models."""
    SUNO = "suno"
    UDIO = "udio"
    MUSICGEN = "musicgen"


class StoryGenre(Enum):
    """Story genres for creative writing."""
    FICTION = "fiction"
    SCIENCE_FICTION = "science_fiction"
    FANTASY = "fantasy"
    ROMANCE = "romance"
    HORROR = "horror"
    THRILLER = "thriller"
    COMEDY = "comedy"
    DRAMA = "drama"
    MYSTERY = "mystery"


@dataclass
class ImageResult:
    """Result of image generation."""
    success: bool
    image_url: Optional[str] = None
    image_base64: Optional[str] = None
    local_path: Optional[str] = None
    prompt: str = ""
    model: str = ""
    error: Optional[str] = None


@dataclass
class VideoResult:
    """Result of video generation."""
    success: bool
    video_url: Optional[str] = None
    local_path: Optional[str] = None
    prompt: str = ""
    model: str = ""
    duration: Optional[int] = None
    error: Optional[str] = None


@dataclass
class StoryResult:
    """Result of story generation."""
    success: bool
    title: str = ""
    content: str = ""
    genre: str = ""
    word_count: int = 0
    characters: List[str] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.characters is None:
            self.characters = []


@dataclass
class MusicResult:
    """Result of music generation."""
    success: bool
    audio_url: Optional[str] = None
    local_path: Optional[str] = None
    prompt: str = ""
    duration: Optional[int] = None
    lyrics: Optional[str] = None
    error: Optional[str] = None


# ============================================================
# IMAGE GENERATOR
# ============================================================

class ImageGenerator:
    """
    Generate images from text prompts using various AI models.
    
    Supported Models:
    - OpenAI DALL-E 3 (best quality)
    - OpenAI DALL-E 2
    - Stable Diffusion (via API)
    - Leonardo AI
    """
    
    def __init__(self):
        self.config = get_config()
        self.default_model = ImageModel.DALL_E_3
    
    async def generate(
        self,
        prompt: str,
        model: ImageModel = None,
        size: str = "1024x1024",
        quality: str = "standard",
        n: int = 1
    ) -> List[ImageResult]:
        """
        Generate images from text prompt.
        
        Args:
            prompt: Detailed description of desired image
            model: Which AI model to use
            size: Image size (1024x1024, 1024x1792, 1792x1024)
            quality: "standard" or "hd"
            n: Number of images to generate
        
        Returns:
            List of ImageResult objects
        """
        model = model or self.default_model
        results = []
        
        if model == ImageModel.DALL_E_3 or model == ImageModel.DALL_E_2:
            results = await self._generate_dalle(prompt, model, size, quality, n)
        elif model == ImageModel.STABLE_DIFFUSION:
            results = await self._generate_stable_diffusion(prompt)
        elif model == ImageModel.LEONARDO:
            results = await self._generate_leonardo(prompt)
        else:
            results = [ImageResult(success=False, error=f"Unknown model: {model}")]
        
        return results
    
    async def _generate_dalle(
        self,
        prompt: str,
        model: ImageModel,
        size: str,
        quality: str,
        n: int
    ) -> List[ImageResult]:
        """Generate using OpenAI DALL-E."""
        if not self.config.openai.is_configured():
            return [ImageResult(success=False, error="OpenAI API key not configured")]
        
        try:
            import openai
            client = openai.OpenAI(api_key=self.config.openai.api_key)
            
            model_name = "dall-e-3" if model == ImageModel.DALL_E_3 else "dall-e-2"
            
            response = client.images.generate(
                model=model_name,
                prompt=prompt,
                size=size,
                quality=quality,
                n=n
            )
            
            results = []
            for img in response.data:
                results.append(ImageResult(
                    success=True,
                    image_url=img.url,
                    prompt=prompt,
                    model=model_name
                ))
            
            return results
            
        except Exception as e:
            logger.error(f"DALL-E error: {e}")
            return [ImageResult(success=False, error=str(e), prompt=prompt)]
    
    async def _generate_stable_diffusion(self, prompt: str) -> List[ImageResult]:
        """Generate using Stable Diffusion API."""
        # Placeholder - would need Stability AI API key
        return [ImageResult(
            success=False,
            error="Stable Diffusion API not configured. Would need stabilityai API key.",
            prompt=prompt
        )]
    
    async def _generate_leonardo(self, prompt: str) -> List[ImageResult]:
        """Generate using Leonardo AI."""
        # Placeholder - would need Leonardo API key
        return [ImageResult(
            success=False,
            error="Leonardo AI API not configured. Would need leonardo API key.",
            prompt=prompt
        )]
    
    async def edit_image(
        self,
        image_path: str,
        mask_path: str,
        prompt: str
    ) -> ImageResult:
        """Edit specific parts of an image using DALL-E."""
        try:
            import openai
            client = openai.OpenAI(api_key=self.config.openai.api_key)
            
            response = client.images.edit(
                model="dall-e-2",
                image=open(image_path, "rb"),
                mask=open(mask_path, "rb"),
                prompt=prompt
            )
            
            return ImageResult(
                success=True,
                image_url=response.data[0].url,
                prompt=prompt,
                model="dall-e-2"
            )
        except Exception as e:
            return ImageResult(success=False, error=str(e))
    
    async def variations(
        self,
        image_path: str,
        n: int = 4
    ) -> List[ImageResult]:
        """Create variations of an existing image."""
        try:
            import openai
            client = openai.OpenAI(api_key=self.config.openai.api_key)
            
            response = client.images.create_variation(
                image=open(image_path, "rb"),
                n=n
            )
            
            results = []
            for img in response.data:
                results.append(ImageResult(
                    success=True,
                    image_url=img.url,
                    model="dall-e-2"
                ))
            
            return results
        except Exception as e:
            return [ImageResult(success=False, error=str(e))]


# ============================================================
# VIDEO GENERATOR
# ============================================================

class VideoGenerator:
    """
    Generate videos from text prompts or images.
    
    Supported Models:
    - Runway ML (Gen-3)
    - Pika Labs
    - Stable Video Diffusion
    """
    
    def __init__(self):
        self.config = get_config()
    
    async def generate_from_text(
        self,
        prompt: str,
        model: VideoModel = VideoModel.RUNWAY_GEN3,
        duration: int = 4
    ) -> VideoResult:
        """
        Generate video from text description.
        
        Args:
            prompt: Description of desired video
            model: Which AI model to use
            duration: Video duration in seconds (1-10)
        
        Returns:
            VideoResult object
        """
        if model == VideoModel.RUNWAY_GEN3:
            return await self._generate_runway(prompt, duration)
        elif model == VideoModel.PIKA:
            return await self._generate_pika(prompt)
        elif model == VideoModel.STABLE_VIDEO:
            return await self._generate_stable_video(prompt)
        else:
            return VideoResult(success=False, error=f"Unknown model: {model}")
    
    async def generate_from_image(
        self,
        image_path: str,
        prompt: str = "",
        model: VideoModel = VideoModel.PIKA
    ) -> VideoResult:
        """Animate an image to create video."""
        if model == VideoModel.PIKA:
            return await self._generate_pika_image(image_path, prompt)
        elif model == VideoModel.RUNWAY_GEN3:
            return await self._generate_runway_image(image_path, prompt)
        else:
            return VideoResult(success=False, error=f"Unknown model for image-to-video")
    
    async def _generate_runway(self, prompt: str, duration: int) -> VideoResult:
        """Generate using Runway ML."""
        # Would need Runway API key
        return VideoResult(
            success=False,
            error="Runway API not configured. Would need runway API key.",
            prompt=prompt,
            model="runway-gen3"
        )
    
    async def _generate_pika(self, prompt: str) -> VideoResult:
        """Generate using Pika Labs."""
        # Would need Pika API key
        return VideoResult(
            success=False,
            error="Pika API not configured. Would need pika API key.",
            prompt=prompt,
            model="pika"
        )
    
    async def _generate_stable_video(self, prompt: str) -> VideoResult:
        """Generate using Stable Video Diffusion."""
        return VideoResult(
            success=False,
            error="Stable Video requires local model deployment.",
            prompt=prompt,
            model="stable-video"
        )
    
    async def _generate_runway_image(self, image_path: str, prompt: str) -> VideoResult:
        """Generate video from image using Runway."""
        return VideoResult(
            success=False,
            error="Runway image-to-video not configured.",
            model="runway-gen3"
        )
    
    async def _generate_pika_image(self, image_path: str, prompt: str) -> VideoResult:
        """Generate video from image using Pika."""
        return VideoResult(
            success=False,
            error="Pika image-to-video not configured.",
            model="pika"
        )


# ============================================================
# STORY WRITER
# ============================================================

class StoryWriter:
    """
    Write creative stories, scripts, and narratives.
    
    Features:
    - Multi-genre story generation
    - Character development
    - Plot structuring
    - Dialogue writing
    - Script formatting
    """
    
    def __init__(self):
        self.config = get_config()
    
    async def write_story(
        self,
        prompt: str,
        genre: StoryGenre = StoryGenre.FICTION,
        word_count: int = 500,
        include_characters: bool = True
    ) -> StoryResult:
        """
        Write a complete story.
        
        Args:
            prompt: Story idea or plot description
            genre: Story genre
            word_count: Target word count
            include_characters: Whether to include character descriptions
        
        Returns:
            StoryResult with story content
        """
        # Create detailed prompt for the story
        story_prompt = f"""Write a {genre.value.replace('_', ' ')} story based on this idea:

{prompt}

Requirements:
- Word count: approximately {word_count} words
- Include vivid descriptions
- Develop compelling characters
- Create an engaging plot with beginning, middle, and end
- Use {genre.value.replace('_', ' ')} genre conventions

Format your response as:
TITLE: [Story Title]

[Story Content]

CHARACTERS:
- [Character 1]: [Brief description]
- [Character 2]: [Brief description]
"""
        
        try:
            content = await self._call_llm(story_prompt)
            
            # Parse response
            lines = content.split('\n')
            title = "Untitled Story"
            actual_content = content
            characters = []
            
            for i, line in enumerate(lines):
                if line.startswith('TITLE:'):
                    title = line.replace('TITLE:', '').strip()
                    actual_content = '\n'.join(lines[i+1:])
                elif line.startswith('CHARACTERS:'):
                    # Parse characters from remaining lines
                    for char_line in lines[i+1:]:
                        if char_line.startswith('-'):
                            characters.append(char_line.strip())
                    actual_content = '\n'.join(lines[:i])
            
            return StoryResult(
                success=True,
                title=title,
                content=actual_content,
                genre=genre.value,
                word_count=len(actual_content.split()),
                characters=characters
            )
            
        except Exception as e:
            logger.error(f"Story writing error: {e}")
            return StoryResult(success=False, error=str(e))
    
    async def write_script(
        self,
        concept: str,
        format: str = "short_film",
        duration: int = 5
    ) -> StoryResult:
        """
        Write a video/film script.
        
        Args:
            concept: Script concept or plot
            format: "short_film", "youtube_video", "tiktok", "movie"
            duration: Duration in minutes
        """
        script_prompt = f"""Write a {format.replace('_', ' ')} script.

Concept: {concept}
Duration: {duration} minutes

Format:
[Scene heading]
[Action description]
[Character]: [Dialogue]

Include:
- Clear scene transitions
- Realistic dialogue
- Visual descriptions
- Camera directions (if applicable)
"""
        
        try:
            content = await self._call_llm(script_prompt)
            
            return StoryResult(
                success=True,
                title=format.replace('_', ' ').title(),
                content=content,
                genre="script",
                word_count=len(content.split())
            )
        except Exception as e:
            return StoryResult(success=False, error=str(e))
    
    async def write_poem(
        self,
        theme: str,
        style: str = "modern",
        mood: str = "reflective"
    ) -> StoryResult:
        """
        Write a poem.
        
        Args:
            theme: Poem theme or subject
            style: "modern", "romantic", "haiku", "sonnet", "free_verse"
            mood: "happy", "sad", "reflective", "energetic", "dark"
        """
        poem_prompt = f"""Write a {style} poem.

Theme: {theme}
Mood: {mood}

Requirements:
- Evocative imagery
- Emotional depth
- Artistic merit
- Clear theme connection

Title your poem at the top.
"""
        
        try:
            content = await self._call_llm(poem_prompt)
            
            lines = content.split('\n')
            title = theme.title()
            
            if lines and not lines[0].startswith('TITLE'):
                title = lines[0].strip()
            
            return StoryResult(
                success=True,
                title=title,
                content=content,
                genre=f"poetry_{style}",
                word_count=len(content.split())
            )
        except Exception as e:
            return StoryResult(success=False, error=str(e))
    
    async def write_blog_post(
        self,
        topic: str,
        style: str = "informative",
        word_count: int = 800
    ) -> StoryResult:
        """Write a blog post or article."""
        blog_prompt = f"""Write a blog post on the following topic:

Topic: {topic}
Style: {style}
Target word count: {word_count}

Format:
1. Catchy title
2. Introduction hook
3. Main content (with subheadings)
4. Conclusion with call-to-action
"""
        
        try:
            content = await self._call_llm(blog_prompt)
            
            lines = content.split('\n')
            title = topic.title()
            if lines:
                title = lines[0].strip()
            
            return StoryResult(
                success=True,
                title=title,
                content=content,
                genre="blog",
                word_count=len(content.split())
            )
        except Exception as e:
            return StoryResult(success=False, error=str(e))
    
    async def _call_llm(self, prompt: str) -> str:
        """Call LLM for story generation."""
        # Try Groq first
        if self.config.groq.is_configured():
            return await self._call_groq(prompt)
        elif self.config.openai.is_configured():
            return await self._call_openai(prompt)
        else:
            raise Exception("No LLM provider configured")
    
    async def _call_groq(self, prompt: str) -> str:
        """Call Groq API."""
        from groq import Groq
        client = Groq(api_key=self.config.groq.api_key)
        
        response = client.chat.completions.create(
            model=self.config.groq.default_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=2048
        )
        
        return response.choices[0].message.content
    
    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API."""
        import openai
        client = openai.OpenAI(api_key=self.config.openai.api_key)
        
        response = client.chat.completions.create(
            model=self.config.openai.default_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=2048
        )
        
        return response.choices[0].message.content


# ============================================================
# MUSIC GENERATOR
# ============================================================

class MusicGenerator:
    """
    Generate music and songs from text descriptions.
    
    Supported:
    - Suno AI (best for full songs with lyrics)
    - Udio
    - MusicGen (local)
    """
    
    def __init__(self):
        self.config = get_config()
    
    async def generate_song(
        self,
        prompt: str,
        style: str = "pop",
        duration: int = 30,
        include_lyrics: bool = True
    ) -> MusicResult:
        """
        Generate a song with lyrics.
        
        Args:
            prompt: Song description or concept
            style: "pop", "rock", "hip-hop", "classical", "jazz", "electronic"
            duration: Duration in seconds (max 120 for most APIs)
            include_lyrics: Whether to generate lyrics
        
        Returns:
            MusicResult with audio URL
        """
        # Suno would be ideal for this
        # For now, return placeholder
        return MusicResult(
            success=False,
            error="Suno API not integrated. Would need suno API key.",
            prompt=prompt
        )
    
    async def generate_instrumental(
        self,
        prompt: str,
        style: str = "ambient"
    ) -> MusicResult:
        """Generate instrumental music without vocals."""
        return MusicResult(
            success=False,
            error="Music generation APIs not configured. Would need suno/udio API key.",
            prompt=prompt
        )


# ============================================================
# CHARACTER GENERATOR
# ============================================================

class CharacterGenerator:
    """
    Generate character designs and descriptions.
    
    Features:
    - Character concept art descriptions
    - Character profiles
    - Backstories
    - Personality traits
    """
    
    def __init__(self):
        self.config = get_config()
    
    async def create_character(
        self,
        concept: str,
        style: str = "anime"
    ) -> Dict[str, Any]:
        """
        Create a complete character profile.
        
        Args:
            concept: Character concept or description
            style: "anime", "realistic", "cartoon", "fantasy"
        
        Returns:
            Dictionary with character details
        """
        prompt = f"""Create a detailed character profile for:

Concept: {concept}
Art Style: {style}

Include:
1. NAME: [Character name]
2. APPEARANCE: [Physical description for artist]
3. PERSONALITY: [Traits and characteristics]
4. BACKSTORY: [Origin and history]
5. QUIRKS: [Unique habits or traits]
6. VOICE: [How they speak]
7. APPEARENCE PROMPT: [Detailed prompt for AI image generation]
"""
        
        try:
            content = await self._call_llm(prompt)
            
            # Parse into structured data
            character = {"raw": content}
            
            for line in content.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().lower().replace(' ', '_')
                    character[key] = value.strip()
            
            return character
            
        except Exception as e:
            return {"error": str(e)}
    
    async def generate_image_prompt(self, character_desc: str) -> str:
        """Generate detailed image prompt for character."""
        prompt = f"""Create a detailed image generation prompt for this character:

{character_desc}

Generate a prompt suitable for DALL-E or Midjourney.
Include:
- Art style
- Pose
- Expression
- Background
- Lighting
- Quality tags
"""
        try:
            return await self._call_llm(prompt)
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def _call_llm(self, prompt: str) -> str:
        """Call LLM."""
        if self.config.groq.is_configured():
            from groq import Groq
            client = Groq(api_key=self.config.groq.api_key)
            response = client.chat.completions.create(
                model=self.config.groq.default_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1024
            )
            return response.choices[0].message.content
        elif self.config.openai.is_configured():
            import openai
            client = openai.OpenAI(api_key=self.config.openai.api_key)
            response = client.chat.completions.create(
                model=self.config.openai.default_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1024
            )
            return response.choices[0].message.content
        else:
            raise Exception("No LLM configured")


# ============================================================
# 3D MODEL GENERATOR
# ============================================================

class Model3DGenerator:
    """
    Generate 3D models from text or 2D images.
    
    Supported:
    - Tripo3D
    - Meshy AI
    """
    
    def __init__(self):
        self.config = get_config()
    
    async def generate_from_text(self, prompt: str) -> Dict[str, Any]:
        """Generate 3D model from text description."""
        return {
            "success": False,
            "error": "3D model generation APIs not configured. Would need tripo3d or meshy API key.",
            "prompt": prompt
        }
    
    async def generate_from_image(self, image_path: str) -> Dict[str, Any]:
        """Generate 3D model from 2D image."""
        return {
            "success": False,
            "error": "3D model generation APIs not configured.",
            "input": image_path
        }


# ============================================================
# CREATIVE AI MANAGER (Main Class)
# ============================================================

class CreativeAIManager:
    """
    Unified interface for all creative AI capabilities.
    
    Usage:
        manager = CreativeAIManager()
        
        # Generate image
        images = await manager.generate_image("A beautiful sunset over mountains")
        
        # Write story
        story = await manager.write_story("A robot who learns to love", genre=StoryGenre.SCIENCE_FICTION)
        
        # Generate character
        char = await manager.create_character("A cyberpunk hacker with a heart of gold")
    """
    
    def __init__(self):
        self.config = get_config()
        
        # Initialize all generators
        self.image = ImageGenerator()
        self.video = VideoGenerator()
        self.story = StoryWriter()
        self.music = MusicGenerator()
        self.character = CharacterGenerator()
        self.model3d = Model3DGenerator()
    
    async def generate_image(
        self,
        prompt: str,
        model: str = "dalle3",
        **kwargs
    ) -> List[ImageResult]:
        """Generate image from text."""
        model_enum = ImageModel.DALL_E_3 if model == "dalle3" else ImageModel.DALL_E_2
        return await self.image.generate(prompt, model_enum, **kwargs)
    
    async def write_story(
        self,
        prompt: str,
        genre: str = "fiction",
        **kwargs
    ) -> StoryResult:
        """Write a story."""
        genre_enum = StoryGenre(genre) if genre in [g.value for g in StoryGenre] else StoryGenre.FICTION
        return await self.story.write_story(prompt, genre_enum, **kwargs)
    
    async def create_character(self, concept: str, **kwargs) -> Dict[str, Any]:
        """Create a character profile."""
        return await self.character.create_character(concept, **kwargs)
    
    async def generate_video(self, prompt: str, **kwargs) -> VideoResult:
        """Generate video from text."""
        return await self.video.generate_from_text(prompt, **kwargs)
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get all creative AI capabilities."""
        return {
            "image_generation": {
                "enabled": self.config.openai.is_configured(),
                "models": ["dall-e-3", "dall-e-2"],
                "dalle_status": "Ready" if self.config.openai.is_configured() else "Needs API key"
            },
            "video_generation": {
                "enabled": False,
                "models": ["runway", "pika", "stable-video"],
                "status": "Not configured"
            },
            "story_writing": {
                "enabled": self.config.groq.is_configured() or self.config.openai.is_configured(),
                "genres": [g.value for g in StoryGenre]
            },
            "music_generation": {
                "enabled": False,
                "models": ["suno", "udio"],
                "status": "Not configured"
            },
            "character_design": {
                "enabled": self.config.groq.is_configured() or self.config.openai.is_configured(),
                "styles": ["anime", "realistic", "cartoon", "fantasy"]
            },
            "3d_generation": {
                "enabled": False,
                "status": "Not configured"
            }
        }


# Export all classes
__all__ = [
    "ImageGenerator",
    "VideoGenerator", 
    "StoryWriter",
    "MusicGenerator",
    "CharacterGenerator",
    "Model3DGenerator",
    "CreativeAIManager",
    "ImageModel",
    "VideoModel",
    "MusicModel",
    "StoryGenre",
    "ImageResult",
    "VideoResult",
    "StoryResult",
    "MusicResult"
]