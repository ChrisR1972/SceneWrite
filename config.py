"""
Configuration management for MoviePrompterAI.
Handles API keys, model settings, and user preferences.
"""

import os
import json
import sys
from typing import Optional, Dict, Any

# Try to import keyring, but make it optional
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

def get_app_directory():
    """Get the directory where the application is located."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return os.path.dirname(sys.executable)
    else:
        # Running as script
        return os.path.dirname(os.path.abspath(__file__))


def get_stories_directory() -> str:
    """Return the default directory for saving/opening stories.

    Uses ``~/Documents/MoviePrompterAI Stories``.  The folder is created
    automatically if it does not already exist.
    """
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    stories_dir = os.path.join(docs, "MoviePrompterAI Stories")
    os.makedirs(stories_dir, exist_ok=True)
    return stories_dir

class Config:
    """Configuration manager for the application."""
    
    def __init__(self):
        self.app_name = "MoviePrompterAI"
        self.service_name = "OpenAI"
        
        # Get the app directory and set config file path
        app_dir = get_app_directory()
        self.config_file = os.path.join(app_dir, "config.json")
        
        # Load config file first
        self._config_data = self._load_config()
        
        # Default settings (overridden by saved config if present)
        self.default_model = self._config_data.get('model', "gpt-4")
        self.default_temperature = self._config_data.get('temperature', 0.7)
        self.default_max_tokens = self._config_data.get('max_tokens', 2000)
        self.auto_save_interval = self._config_data.get('auto_save_interval', 300)  # seconds
        
        # AI Provider settings
        self.ai_provider = self._config_data.get('ai_provider', "OpenAI")  # OpenAI, Anthropic, Local, Together AI, OpenRouter, Hugging Face, Custom
        self.base_url = self._config_data.get('base_url', None)  # For providers that need custom base URLs
        # Set default base_url for providers if not set
        if not self.base_url:
            _default_urls = {
                "OpenAI": "https://api.openai.com/v1",
                "Ollama Cloud": "https://ollama.com/api",
                "Anthropic": "https://api.anthropic.com",
                "Together AI": "https://api.together.xyz/v1",
                "OpenRouter": "https://openrouter.ai/api/v1",
                "Hugging Face": "https://api-inference.huggingface.co/v1/",
                "Local (Ollama/LM Studio)": "http://localhost:11434/v1",
                "Local": "http://localhost:11434/v1",
            }
            if self.ai_provider in _default_urls:
                self.base_url = _default_urls[self.ai_provider]
        
        # UI settings
        self.theme = self._config_data.get('theme', "light")  # light, dark
        self.font_size = self._config_data.get('font_size', 12)
        self.show_line_numbers = self._config_data.get('show_line_numbers', True)
    
    def get_openai_api_key(self) -> Optional[str]:
        """Get OpenAI API key from environment, keyring, or config file."""
        # First try environment variable
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            return api_key
            
        # Then try keyring if available
        if KEYRING_AVAILABLE:
            try:
                api_key = keyring.get_password(self.service_name, "api_key")
                if api_key:
                    return api_key
            except Exception:
                pass
        
        # Fallback to config file (less secure but functional)
        api_key = self._config_data.get('openai_api_key')
        if api_key:
            return api_key
        
        return None
    
    def set_openai_api_key(self, api_key: str) -> bool:
        """Store OpenAI API key securely. Tries keyring first, falls back to config file."""
        # First try keyring if available
        if KEYRING_AVAILABLE:
            try:
                keyring.set_password(self.service_name, "api_key", api_key)
                # Also save to config file as backup
                self._config_data['openai_api_key'] = api_key
                self._save_config()
                return True
            except Exception as e:
                # Keyring failed, fall back to config file
                try:
                    self._config_data['openai_api_key'] = api_key
                    self._save_config()
                    return True
                except Exception:
                    return False
        
        # Keyring not available, use config file
        try:
            self._config_data['openai_api_key'] = api_key
            self._save_config()
            return True
        except Exception:
            return False
    
    def get_model_settings(self) -> Dict[str, Any]:
        """Get AI model configuration.

        Note: ``supports_multishot`` and ``max_generation_duration_seconds``
        are now per-project settings stored in ``Screenplay.story_settings``.
        They are still returned here for backward compatibility but default
        to ``False`` / ``10``; prefer reading from the screenplay object.
        """
        return {
            "model": self.default_model,
            "temperature": self.default_temperature,
            "max_tokens": self.default_max_tokens,
            "provider": self.ai_provider,
            "base_url": self.base_url,
            "supports_multishot": self._config_data.get("supports_multishot", False),
            "max_generation_duration_seconds": self._config_data.get("max_generation_duration_seconds", 15),
        }
    
    def set_model_settings(self, model: str, temperature: float, max_tokens: int,
                           provider: str = None, base_url: Optional[str] = None,
                           supports_multishot: Optional[bool] = None,
                           max_generation_duration_seconds: Optional[int] = None):
        """Update AI model configuration and persist to file."""
        self.default_model = model
        self.default_temperature = temperature
        self.default_max_tokens = max_tokens
        if provider is not None:
            self.ai_provider = provider
        # Update base_url when provided; clear only when switching to a provider that doesn't use it
        providers_with_base_url = ("Local", "Ollama Cloud", "Anthropic", "Together AI", "OpenRouter", "Hugging Face", "Custom", "OpenAI")
        if base_url is not None:
            self.base_url = base_url if base_url else None
        elif self.ai_provider not in providers_with_base_url:
            self.base_url = None
        
        # Persist to config file
        self._config_data['model'] = model
        self._config_data['temperature'] = temperature
        self._config_data['max_tokens'] = max_tokens
        self._config_data['ai_provider'] = self.ai_provider
        self._config_data['base_url'] = self.base_url
        if supports_multishot is not None:
            self._config_data['supports_multishot'] = supports_multishot
        if max_generation_duration_seconds is not None:
            self._config_data['max_generation_duration_seconds'] = max_generation_duration_seconds
        self._save_config()
    
    def get_ai_provider_settings(self) -> Dict[str, Any]:
        """Get AI provider configuration."""
        return {
            "provider": self.ai_provider,
            "base_url": self.base_url
        }
    
    def set_ai_provider_settings(self, provider: str, base_url: Optional[str] = None):
        """Update AI provider configuration and persist to file."""
        self.ai_provider = provider
        self.base_url = base_url if base_url else None
        
        # Persist to config file
        self._config_data['ai_provider'] = provider
        self._config_data['base_url'] = self.base_url
        self._save_config()
    
    def get_ui_settings(self) -> Dict[str, Any]:
        """Get UI configuration."""
        return {
            "theme": self.theme,
            "font_size": self.font_size,
            "show_line_numbers": self.show_line_numbers,
            "auto_save_interval": self.auto_save_interval
        }
    
    def set_ui_settings(self, theme: str, font_size: int, show_line_numbers: bool, auto_save_interval: int):
        """Update UI configuration and persist to file."""
        self.theme = theme
        self.font_size = font_size
        self.show_line_numbers = show_line_numbers
        self.auto_save_interval = auto_save_interval
        
        # Persist to config file
        self._config_data['theme'] = theme
        self._config_data['font_size'] = font_size
        self._config_data['show_line_numbers'] = show_line_numbers
        self._config_data['auto_save_interval'] = auto_save_interval
        self._save_config()
    
    # -- Custom species / forms -----------------------------------------------

    def get_custom_species(self) -> list:
        """Return the list of user-defined custom species (sorted, deduped)."""
        return list(self._config_data.get("custom_species", []))

    def add_custom_species(self, species: str) -> bool:
        """Add a custom species to the persisted list if not already present.

        Returns True if the species was newly added, False if it was already
        present or invalid.
        """
        species = species.strip()
        if not species:
            return False
        existing = self._config_data.get("custom_species", [])
        lower_set = {s.lower() for s in existing}
        if species.lower() in lower_set:
            return False
        existing.append(species)
        existing.sort(key=str.lower)
        self._config_data["custom_species"] = existing
        self._save_config()
        return True

    def remove_custom_species(self, species: str):
        """Remove a custom species from the persisted list."""
        existing = self._config_data.get("custom_species", [])
        self._config_data["custom_species"] = [
            s for s in existing if s.lower() != species.strip().lower()
        ]
        self._save_config()

    # -- Recent files --------------------------------------------------------

    MAX_RECENT_FILES = 10

    def get_recent_files(self) -> list:
        """Return the list of recently-opened file paths (most recent first).

        Non-existent paths are silently pruned so stale entries don't linger.
        """
        paths = self._config_data.get("recent_files", [])
        # Filter out files that no longer exist
        valid = [p for p in paths if os.path.isfile(p)]
        # If we pruned anything, persist the cleaned list
        if len(valid) != len(paths):
            self._config_data["recent_files"] = valid
            self._save_config()
        return valid

    def add_recent_file(self, filepath: str):
        """Push *filepath* to the front of the recent-files list (deduped, capped)."""
        filepath = os.path.normpath(os.path.abspath(filepath))
        paths = self._config_data.get("recent_files", [])
        # Remove any existing occurrence (case-insensitive on Windows)
        paths = [p for p in paths if os.path.normcase(p) != os.path.normcase(filepath)]
        paths.insert(0, filepath)
        self._config_data["recent_files"] = paths[: self.MAX_RECENT_FILES]
        self._save_config()

    def clear_recent_files(self):
        """Remove all entries from the recent-files list."""
        self._config_data["recent_files"] = []
        self._save_config()

    # -- Persistence ---------------------------------------------------------

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}
    
    def _save_config(self):
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config_data, f, indent=2, ensure_ascii=False)
                # Ensure file is flushed to disk before closing
                f.flush()
                # Force write to disk (if supported)
                try:
                    if hasattr(f, 'fileno'):
                        os.fsync(f.fileno())
                except (OSError, AttributeError):
                    pass  # Some file objects don't support fsync
        except Exception:
            pass
    
    def reload_config(self):
        """Reload configuration from file (useful after external changes)."""
        self._config_data = self._load_config()
        # Update in-memory values from reloaded config
        self.default_model = self._config_data.get('model', "gpt-4")
        self.default_temperature = self._config_data.get('temperature', 0.7)
        self.default_max_tokens = self._config_data.get('max_tokens', 2000)
        self.ai_provider = self._config_data.get('ai_provider', "OpenAI")
        self.base_url = self._config_data.get('base_url', None)
        if not self.base_url:
            _default_urls = {
                "OpenAI": "https://api.openai.com/v1",
                "Ollama Cloud": "https://ollama.com/api",
                "Anthropic": "https://api.anthropic.com",
                "Together AI": "https://api.together.xyz/v1",
                "OpenRouter": "https://openrouter.ai/api/v1",
                "Hugging Face": "https://api-inference.huggingface.co/v1/",
                "Local (Ollama/LM Studio)": "http://localhost:11434/v1",
                "Local": "http://localhost:11434/v1",
            }
            if self.ai_provider in _default_urls:
                self.base_url = _default_urls[self.ai_provider]

# Global config instance
config = Config()

