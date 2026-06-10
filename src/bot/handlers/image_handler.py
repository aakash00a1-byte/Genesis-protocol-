"""Genesis Protocol - Image Handler

Handles image processing and analysis.
"""

import io
from telegram import Update
from telegram.ext import ContextTypes

from genesis_protocol.bot.telegram_bot import TelegramBot
from genesis_protocol.models.message import Message, MessageType, MessageDirection
from genesis_protocol.memory.conversation_memory import ConversationMemory
from genesis_protocol.processors.image_processor import ImageProcessor
from genesis_protocol.utils.logger import get_logger

logger = get_logger("bot.handlers.image")


class ImageHandler:
    """
    Handles image message processing.
    """
    
    def __init__(self, bot: TelegramBot):
        """Initialize image handler."""
        self.bot = bot
        self.memory = ConversationMemory()
        self.image_processor = ImageProcessor()
    
    async def handle_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle incoming image.
        
        Args:
            update: Telegram update
            context: Handler context
        """
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        # Get the largest photo
        photo = update.message.photo[-1]
        
        logger.info(
            "Processing image",
            chat_id=chat_id,
            user_id=user_id,
            photo_id=photo.file_id
        )
        
        # Notify user
        await self.bot.send_typing(chat_id)
        await self.bot.send_message(chat_id, "🖼️ Analyzing image...")
        
        try:
            # Download image
            photo_file = await context.bot.get_file(photo.file_id)
            file_bytes = await photo_file.download_as_bytearray()
            image_stream = io.BytesIO(file_bytes)
            
            # Process image
            result = await self.image_processor.analyze(image_stream)
            
            if not result:
                await self.bot.send_message(chat_id, "❌ Could not analyze image.")
                return
            
            # Create message
            message = Message(
                id=str(update.message.message_id),
                chat_id=chat_id,
                user_id=user_id,
                message_type=MessageType.IMAGE,
                direction=MessageDirection.INCOMING,
                text=result.get("description", ""),
            )
            
            await self.memory.add_message(chat_id, message)
            
            # Get caption if present
            caption = update.message.caption or "What do you see in this image?"
            
            # Analyze with AI
            from genesis_protocol.ai.provider_chain import get_provider_chain
            from genesis_protocol.ai.prompts import get_system_prompt, get_image_context
            
            ai_chain = get_provider_chain()
            
            system_prompt = get_system_prompt(
                user_name=update.effective_user.first_name,
                chat_id=chat_id,
            ) + "\n\n" + get_image_context()
            
            # Include image in request
            import base64
            image_base64 = base64.b64encode(file_bytes).decode()
            
            vision_result = await ai_chain.call_with_vision(
                text=caption,
                image_base64=image_base64,
            )
            
            if vision_result.success and vision_result.response:
                response = vision_result.response.content
                
                # Format response
                response = f"📷 *Image Analysis*\n\n{response}"
                
                await self.bot.send_message(chat_id, response, parse_mode="Markdown")
            else:
                # Fallback to basic description
                await self.bot.send_message(
                    chat_id,
                    f"📷 *Image Description*\n\n{result.get('description', 'Could not analyze image.')}",
                    parse_mode="Markdown"
                )
            
            logger.info("Image processed successfully")
            
        except Exception as e:
            logger.error(f"Image processing failed: {e}")
            await self.bot.send_message(
                chat_id,
                "❌ Failed to process image. Please try again."
            )