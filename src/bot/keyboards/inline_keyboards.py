"""Genesis Protocol - Inline Keyboards

Custom inline keyboard builders for Telegram bot.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


class DashboardKeyboard:
    """Inline keyboard for dashboard commands."""
    
    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        """Get main menu keyboard."""
        keyboard = [
            [InlineKeyboardButton("📊 Stats", callback_data="stats")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
            [InlineKeyboardButton("📚 Help", callback_data="help")],
            [InlineKeyboardButton("🔄 Reset", callback_data="reset")],
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def quick_actions() -> InlineKeyboardMarkup:
        """Get quick actions keyboard."""
        keyboard = [
            [
                InlineKeyboardButton("🔍 Search", callback_data="search"),
                InlineKeyboardButton("🖼️ Analyze", callback_data="analyze"),
            ],
            [
                InlineKeyboardButton("💬 Chat", callback_data="chat"),
                InlineKeyboardButton("🔧 Debug", callback_data="debug_toggle"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)


class SettingsKeyboard:
    """Inline keyboard for settings."""
    
    @staticmethod
    def main_settings() -> InlineKeyboardMarkup:
        """Get main settings keyboard."""
        keyboard = [
            [
                InlineKeyboardButton("🤖 AI Model", callback_data="model_menu"),
                InlineKeyboardButton("📝 Style", callback_data="style_menu"),
            ],
            [
                InlineKeyboardButton("🔊 Voice", callback_data="voice_toggle"),
                InlineKeyboardButton("🖼️ Images", callback_data="images_toggle"),
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="back")],
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def response_styles() -> InlineKeyboardMarkup:
        """Get response style options."""
        keyboard = [
            [
                InlineKeyboardButton("📏 Concise", callback_data="style_concise"),
                InlineKeyboardButton("📄 Detailed", callback_data="style_detailed"),
            ],
            [
                InlineKeyboardButton("💻 Technical", callback_data="style_technical"),
                InlineKeyboardButton("🔙 Back", callback_data="settings"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)


class ModelKeyboard:
    """Inline keyboard for AI model selection."""
    
    @staticmethod
    def model_selection() -> InlineKeyboardMarkup:
        """Get model selection keyboard."""
        keyboard = [
            [
                InlineKeyboardButton("⚡ Groq (Fast)", callback_data="model_groq"),
            ],
            [
                InlineKeyboardButton("🧠 OpenAI (Quality)", callback_data="model_openai"),
            ],
            [
                InlineKeyboardButton("🌟 Gemini (Context)", callback_data="model_gemini"),
            ],
            [
                InlineKeyboardButton("🤗 HuggingFace (Free)", callback_data="model_huggingface"),
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="settings")],
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def current_model(model: str) -> InlineKeyboardMarkup:
        """Get keyboard showing current model."""
        model_emojis = {
            "groq": "⚡",
            "openai": "🧠",
            "gemini": "🌟",
            "huggingface": "🤗",
        }
        emoji = model_emojis.get(model, "🤖")
        
        keyboard = [
            [InlineKeyboardButton(f"{emoji} Current: {model.title()}", callback_data="current_model")],
            [InlineKeyboardButton("🔄 Change Model", callback_data="model_menu")],
        ]
        return InlineKeyboardMarkup(keyboard)


class PaginationKeyboard:
    """Inline keyboard for pagination."""
    
    @staticmethod
    def paginate(current_page: int, total_pages: int, 
                 prefix: str = "page") -> InlineKeyboardMarkup:
        """Get pagination keyboard."""
        keyboard = []
        
        # Navigation row
        nav_row = []
        
        if current_page > 1:
            nav_row.append(InlineKeyboardButton("◀️", callback_data=f"{prefix}_{current_page-1}"))
        else:
            nav_row.append(InlineKeyboardButton(" ", callback_data="noop"))
        
        nav_row.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="noop"))
        
        if current_page < total_pages:
            nav_row.append(InlineKeyboardButton("▶️", callback_data=f"{prefix}_{current_page+1}"))
        else:
            nav_row.append(InlineKeyboardButton(" ", callback_data="noop"))
        
        keyboard.append(nav_row)
        
        return InlineKeyboardMarkup(keyboard)


class ConfirmationKeyboard:
    """Inline keyboard for confirmations."""
    
    @staticmethod
    def confirm(action: str) -> InlineKeyboardMarkup:
        """Get confirmation keyboard."""
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes", callback_data=f"confirm_{action}"),
                InlineKeyboardButton("❌ No", callback_data=f"cancel_{action}"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)