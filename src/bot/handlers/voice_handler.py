"""Genesis Protocol - Voice Handler

Handles voice message processing and transcription.
"""

import io
from telegram import Update
from telegram.ext import ContextTypes

from genesis_protocol.bot.telegram_bot import TelegramBot
from genesis_protocol.models.message import Message, MessageType, MessageDirection
from genesis_protocol.memory.conversation_memory import ConversationMemory
from genesis_protocol.processors.voice_processor import VoiceProcessor
from genesis_protocol.utils.logger import get_logger

logger = get_logger("bot.handlers.voice")


class VoiceHandler:
    """
    Handles voice message processing.
    """
    
    def __init__(self, bot: TelegramBot):
        """Initialize voice handler."""
        self.bot = bot
        self.memory = ConversationMemory()
        self.voice_processor = VoiceProcessor()
    
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle incoming voice message.
        
        Args:
            update: Telegram update
            context: Handler context
        """
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        voice = update.message.voice
        
        logger.info(
            "Processing voice message",
            chat_id=chat_id,
            user_id=user_id,
            duration=voice.duration
        )
        
        # Notify user
        await self.bot.send_typing(chat_id)
        await self.bot.send_message(chat_id, "🎙️ Transcribing voice message...")
        
        try:
            # Download voice file
            voice_file = await context.bot.get_file(voice.file_id)
            
            # Download to memory
            file_bytes = await voice_file.download_as_bytearray()
            audio_stream = io.BytesIO(file_bytes)
            
            # Transcribe
            transcription = await self.voice_processor.transcribe(audio_stream)
            
            if not transcription:
                await self.bot.send_message(chat_id, "❌ Could not transcribe audio.")
                return
            
            # Create message
            message = Message(
                id=str(update.message.message_id),
                chat_id=chat_id,
                user_id=user_id,
                message_type=MessageType.VOICE,
                direction=MessageDirection.INCOMING,
                text=transcription,
            )
            
            await self.memory.add_message(chat_id, message)
            
            # Process transcription with AI
            from genesis_protocol.ai.provider_chain import get_provider_chain
            from genesis_protocol.ai.prompts import get_system_prompt, get_voice_context
            
            ai_chain = get_provider_chain()
            
            system_prompt = get_system_prompt(
                user_name=update.effective_user.first_name,
                chat_id=chat_id,
            ) + "\n\n" + get_voice_context()
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcription}
            ]
            
            result = await ai_chain.call(messages=messages)
            
            if result.success and result.response:
                response = result.response.content
                
                # Check if user wants voice response
                wants_voice = "respond with voice" in transcription.lower() or "speak" in transcription.lower()
                
                if wants_voice:
                    # Generate voice response
                    audio_response = await self.voice_processor.synthesize(response)
                    if audio_response:
                        await self.bot.send_voice(chat_id, audio_response)
                        return
                
                # Send text response
                await self.bot.send_message(chat_id, response, parse_mode="Markdown")
            else:
                await self.bot.send_message(chat_id, f"Transcribed: {transcription}")
            
            logger.info(
                "Voice message processed",
                transcription_length=len(transcription)
            )
            
        except Exception as e:
            logger.error(f"Voice processing failed: {e}")
            await self.bot.send_message(
                chat_id,
                "❌ Failed to process voice message. Please try again."
            )