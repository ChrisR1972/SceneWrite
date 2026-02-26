"""
AI generation for screenplay premises and storyboards.
Handles AI-powered content creation for screenplay writing.
Provider adapters support OpenAI-compatible APIs and Ollama Cloud (native API, no /v1).
"""

def _safe_print(*args, **kwargs):
    """Print that catches OSError [Errno 22] on Windows when stdout can't handle Unicode."""
    try:
        print(*args, **kwargs)
    except OSError:
        pass


import openai
import requests
from typing import Dict, List, Any, Optional, Union, Tuple

# Anthropic SDK (optional: only needed when Anthropic provider is selected)
try:
    import anthropic as _anthropic_module
    ANTHROPIC_AVAILABLE = True
except ImportError:
    _anthropic_module = None
    ANTHROPIC_AVAILABLE = False
import json
import re
import uuid
from datetime import datetime
from .screenplay_engine import Screenplay, StoryboardItem, SceneType, StoryAct, StoryScene
from .action_rules import fix_action_markup, get_effective_action_whitelist
from .sfx_rules import expand_sfx_markup, fix_sfx_markup, get_effective_sfx_whitelist
from .cinematic_grammar import enforce_cinematic_grammar, get_cinematic_grammar_prompt_text
from .storyboard_validator import (
    extract_paragraph_entities,
    extract_storyboard_entities,
    compare_entity_sets,
    validate_storyboard_against_paragraphs,
    extract_dominant_action,
    suggest_camera_framing,
)
from config import config


# --- Species detection / normalization ---

_SPECIES_DROPDOWN_OPTIONS = [
    "Human", "Elf", "Dwarf", "Orc", "Dragon", "Werewolf", "Vampire", "Angel",
    "Demon", "Fairy", "Giant", "Goblin", "Troll", "Centaur", "Mermaid / Merman",
    "Ghost / Spirit", "Robot / Android", "Alien", "Shapeshifter", "Animal",
]

def get_all_species_options() -> list:
    """Return the full species list: built-in options + user custom species.

    Custom species are inserted alphabetically before the 'Custom...' sentinel
    so they appear as regular dropdown entries.
    """
    from config import config
    custom = config.get_custom_species()
    builtin_lower = {s.lower() for s in _SPECIES_DROPDOWN_OPTIONS}
    extras = [s for s in custom if s.lower() not in builtin_lower]
    return _SPECIES_DROPDOWN_OPTIONS + extras


_SPECIES_KEYWORD_MAP = {
    "demon": "Demon", "devil": "Demon", "fiend": "Demon", "imp": "Demon",
    "dragon": "Dragon", "drake": "Dragon", "wyvern": "Dragon", "wyrm": "Dragon",
    "elf": "Elf", "elven": "Elf", "elvish": "Elf",
    "dwarf": "Dwarf", "dwarven": "Dwarf",
    "orc": "Orc", "orcish": "Orc",
    "vampire": "Vampire", "vampiric": "Vampire",
    "werewolf": "Werewolf", "lycanthrope": "Werewolf", "wolf-man": "Werewolf",
    "angel": "Angel", "angelic": "Angel", "seraph": "Angel", "seraphim": "Angel",
    "fairy": "Fairy", "fae": "Fairy", "faerie": "Fairy", "pixie": "Fairy",
    "giant": "Giant", "ogre": "Giant",
    "goblin": "Goblin", "gremlin": "Goblin",
    "troll": "Troll",
    "centaur": "Centaur",
    "mermaid": "Mermaid / Merman", "merman": "Mermaid / Merman", "merfolk": "Mermaid / Merman",
    "ghost": "Ghost / Spirit", "spirit": "Ghost / Spirit", "spectre": "Ghost / Spirit",
    "specter": "Ghost / Spirit", "phantom": "Ghost / Spirit", "wraith": "Ghost / Spirit",
    "apparition": "Ghost / Spirit", "poltergeist": "Ghost / Spirit",
    "robot": "Robot / Android", "android": "Robot / Android", "cyborg": "Robot / Android",
    "automaton": "Robot / Android", "droid": "Robot / Android", "mech": "Robot / Android",
    "alien": "Alien", "extraterrestrial": "Alien",
    "shapeshifter": "Shapeshifter", "changeling": "Shapeshifter", "metamorph": "Shapeshifter",
}


def normalize_species_label(raw: str) -> str:
    """Map a free-form species string from the AI to the closest dropdown option."""
    if not raw or not isinstance(raw, str):
        return "Human"
    raw = raw.strip()
    if not raw:
        return "Human"
    raw_lower = raw.lower()
    for opt in _SPECIES_DROPDOWN_OPTIONS:
        if opt.lower() == raw_lower:
            return opt
    for opt in get_all_species_options():
        if opt.lower() == raw_lower:
            return opt
    for keyword, label in _SPECIES_KEYWORD_MAP.items():
        if keyword in raw_lower:
            return label
    if raw_lower == "human":
        return "Human"
    return raw


def infer_species_from_text(outline: str, physical_appearance: str,
                            storyline_context: str = "",
                            character_name: str = "") -> str:
    """Scan outline/physical_appearance/storyline for species keywords as a fallback.

    Priority: physical_appearance > outline > storyline_context.
    For storyline_context, species keywords must be *directly associated* with the
    character (e.g. "the demon BOB", "a vampire named ELENA") to avoid false positives
    when other species are mentioned in the same sentence.
    """
    _NON_SPECIES_PHRASES = [
        "demon-hunting", "demon hunting", "demon hunter", "demon slayer", "demon lord hunter",
        "dragon-hunting", "dragon hunting", "dragon hunter", "dragon slayer", "dragon rider",
        "vampire-hunting", "vampire hunting", "vampire hunter", "vampire slayer",
        "ghost-hunting", "ghost hunting", "ghost hunter", "ghost guys", "ghost seekers",
        "ghost busters", "ghostbusters", "ghost buster", "ghost story", "ghost stories",
        "alien-hunting", "alien hunting", "alien hunter",
        "fairy tale", "fairy tales", "fairytale",
        "troll bridge", "troll farm",
        "angel investor", "angel investors", "angel food",
        "giant leap", "giant step", "giant screen",
    ]

    def _clean_and_search(text: str) -> Optional[str]:
        if not text or not text.strip():
            return None
        text_lower = text.lower()
        for phrase in _NON_SPECIES_PHRASES:
            text_lower = text_lower.replace(phrase, "")
        for keyword, label in sorted(_SPECIES_KEYWORD_MAP.items(), key=lambda x: -len(x[0])):
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, text_lower):
                return label
        return None

    result = _clean_and_search(physical_appearance)
    if result:
        return result
    result = _clean_and_search(outline)
    if result:
        return result
    if storyline_context and storyline_context.strip() and character_name:
        ctx_lower = storyline_context.lower()
        for phrase in _NON_SPECIES_PHRASES:
            ctx_lower = ctx_lower.replace(phrase, "")
        name_lower = character_name.strip().lower()
        name_parts = [p for p in name_lower.split() if len(p) > 1]
        for keyword, label in sorted(_SPECIES_KEYWORD_MAP.items(), key=lambda x: -len(x[0])):
            for np in name_parts:
                proximity_pat = (
                    r'\b' + re.escape(keyword) + r'\b.{0,20}\b' + re.escape(np) + r'\b'
                    + r'|'
                    + r'\b' + re.escape(np) + r'\b.{0,20}\b' + re.escape(keyword) + r'\b'
                )
                if re.search(proximity_pat, ctx_lower):
                    return label
    return "Human"


# --- Provider adapters: normalize all responses to choices[0].message.content ---

def _normalized_response(content: str, finish_reason: str = "stop"):
    """Build a response object compatible with OpenAI shape: response.choices[0].message.content."""
    class Message:
        def __init__(self, content):
            self.content = content
    class Choice:
        def __init__(self, message, finish_reason="stop"):
            self.message = message
            self.finish_reason = finish_reason
    msg = Message(content or "")
    choice = Choice(msg, finish_reason)
    class Response:
        choices = [choice]
    return Response()


class _OpenAIAdapter:
    """OpenAI-compatible provider: uses OpenAI client as-is; base_url used as provided (no /v1 forced)."""
    def __init__(self, client):
        self.client = client

    def chat_completion(self, *, messages, model, temperature=0.7, max_tokens=2000, **kwargs):
        return self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )


class _AnthropicAdapter:
    """Anthropic provider: uses the Anthropic Python SDK for Claude models.

    Converts OpenAI-style messages (with role 'system') into the Anthropic
    format where the system prompt is a separate top-level parameter.
    Uses streaming to avoid read-timeout on long screenplay generations.
    """

    def __init__(self, client):
        self.client = client

    def chat_completion(self, *, messages, model, temperature=0.7, max_tokens=2000, **kwargs):
        # Separate system messages from user/assistant messages
        system_parts: list[str] = []
        filtered_messages: list[dict] = []
        for msg in messages:
            if msg.get("role") == "system":
                text = msg.get("content", "")
                if text:
                    system_parts.append(text)
            else:
                filtered_messages.append({"role": msg["role"], "content": msg.get("content", "")})

        # Anthropic requires at least one non-system message
        if not filtered_messages:
            filtered_messages = [{"role": "user", "content": "Hello"}]

        system_text = "\n\n".join(system_parts) if system_parts else ""

        api_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": filtered_messages,
        }
        if system_text:
            api_kwargs["system"] = system_text
        # Only pass temperature if it's > 0 (Anthropic doesn't accept exactly 0 well in some versions)
        if temperature is not None:
            api_kwargs["temperature"] = temperature

        # Stream to keep the connection alive during long generations
        content_parts: list[str] = []
        with self.client.messages.stream(**api_kwargs) as stream:
            for text in stream.text_stream:
                if text:
                    content_parts.append(text)

        content = "".join(content_parts)
        return _normalized_response(content, "stop")


def _ollama_api_path(base_url: str, endpoint: str) -> str:
    """Build full URL for an Ollama API endpoint. Handles base URLs that already end with /api (e.g. https://ollama.com/api)."""
    base = base_url.rstrip("/")
    if base.endswith("/api"):
        return f"{base}/{endpoint}"
    return f"{base}/api/{endpoint}"


class _OllamaCloudAdapter:
    """Ollama Cloud / native Ollama API: POST {base_url}/api/chat (or .../chat if base ends with /api).

    Uses streaming so that long generations don't hit a read-timeout.
    Each streamed chunk resets the socket read timer, keeping the connection alive
    even when the model takes minutes to produce a full response.
    """
    def __init__(self, base_url: str, model: str, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def chat_completion(self, *, messages, model=None, temperature=0.7, max_tokens=2000, **kwargs):
        url = _ollama_api_path(self.base_url, "chat")
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": True,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # connect timeout 30s, read timeout 60s per chunk (reset on every chunk)
        resp = requests.post(url, json=payload, headers=headers,
                             timeout=(30, 60), stream=True)
        resp.raise_for_status()

        # Accumulate streamed content chunks
        content_parts = []
        finish_reason = "stop"
        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                # Each chunk: {"message": {"role": "assistant", "content": "..."}, "done": false}
                msg = chunk.get("message") or {}
                piece = msg.get("content", "")
                if piece:
                    content_parts.append(piece)
                if chunk.get("done"):
                    break
        finally:
            resp.close()

        content = "".join(content_parts)
        return _normalized_response(content, finish_reason)

class AIGenerator:
    """Handles AI-powered screenplay generation using OpenAI API."""
    
    def __init__(self, quota_callback=None):
        self.client = None
        self._adapter = None
        self.model_settings = config.get_model_settings()
        self.quota_callback = quota_callback
        self._initialize_client()
    
    def reload_settings(self):
        """Reload settings and reinitialize client (useful after settings change)."""
        # Reload config from file to ensure we have the latest settings
        config.reload_config()
        # Reload model settings from config
        self.model_settings = config.get_model_settings()
        # Reinitialize client with new settings
        self._initialize_client()
        # Verify client was initialized successfully
        if not self._adapter:
            # Try one more time - sometimes config needs a moment to update
            import time
            time.sleep(0.2)  # Slightly longer pause to ensure config is written
            config.reload_config()  # Reload again
            self.model_settings = config.get_model_settings()
            self._initialize_client()
    
    def _initialize_client(self):
        """Initialize provider adapter. OpenAI-compatible providers use OpenAI client; Ollama Cloud uses direct HTTP; Anthropic uses the Anthropic SDK."""
        model_settings = config.get_model_settings()
        provider = model_settings.get("provider", "OpenAI")
        base_url = model_settings.get("base_url")
        model = model_settings.get("model", "gpt-4")

        # Ollama Cloud: native API, base_url as-is (do not append /v1)
        if provider == "Ollama Cloud":
            if not base_url or not base_url.strip():
                self.client = None
                self._adapter = None
                return
            api_key = config.get_openai_api_key()
            try:
                self._adapter = _OllamaCloudAdapter(
                    base_url=base_url.strip().rstrip("/"),
                    model=model,
                    api_key=api_key or None
                )
                self.client = None  # Not used for Ollama Cloud
            except Exception:
                self.client = None
                self._adapter = None
            return

        # Anthropic: uses Anthropic Python SDK
        if provider == "Anthropic":
            api_key = config.get_openai_api_key()
            if not api_key:
                self.client = None
                self._adapter = None
                return
            if not ANTHROPIC_AVAILABLE:
                self.client = None
                self._adapter = None
                return
            try:
                anthropic_kwargs = {"api_key": api_key}
                # Allow custom base URL for Anthropic-compatible proxies
                if base_url and base_url.strip():
                    anthropic_kwargs["base_url"] = base_url.strip().rstrip("/")
                client = _anthropic_module.Anthropic(**anthropic_kwargs)
                self._adapter = _AnthropicAdapter(client)
                self.client = None  # Not used for Anthropic
            except Exception:
                self.client = None
                self._adapter = None
            return

        # OpenAI-compatible providers: base_url used as provided (no automatic /v1)
        needs_base_url = provider in ["Local", "Together AI", "OpenRouter", "Hugging Face", "Custom", "OpenAI"]
        if provider == "OpenAI" and not base_url:
            base_url = "https://api.openai.com/v1"

        if needs_base_url and base_url:
            api_key = config.get_openai_api_key() or ("not-needed" if provider == "Local" else None)
            if api_key or provider == "Local":
                try:
                    self.client = openai.OpenAI(
                        api_key=api_key or "not-needed",
                        base_url=base_url
                    )
                    self._adapter = _OpenAIAdapter(self.client)
                except Exception:
                    self.client = None
                    self._adapter = None
            else:
                self.client = None
                self._adapter = None
        else:
            api_key = config.get_openai_api_key()
            if api_key:
                try:
                    self.client = openai.OpenAI(api_key=api_key)
                    self._adapter = _OpenAIAdapter(self.client)
                except Exception:
                    self.client = None
                    self._adapter = None
            else:
                self.client = None
                self._adapter = None

    def _chat_completion(self, *, messages, model=None, temperature=0.7, max_tokens=2000, **kwargs):
        """Single entry point for chat completions; delegates to provider adapter. Returns response with .choices[0].message.content."""
        if not self._adapter:
            raise Exception("AI client not initialized. Please configure your API key or AI server in settings.")
        model = model or self.model_settings.get("model", "gpt-4")
        return self._adapter.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

    def generate_premise(self, genres: List[str], atmosphere: str, return_raw: bool = False, workflow_profile=None, brand_context=None) -> str:
        """Generate a story premise from genre and atmosphere selections.
        
        Args:
            genres: List of genre strings
            atmosphere: Atmosphere/tone string
            return_raw: Whether to return raw AI output
            workflow_profile: WorkflowProfile enum (NARRATIVE, PROMOTIONAL, etc.)
            brand_context: BrandContext object for promotional workflows
        """
        
        if not self._adapter:
            raise Exception("AI client not initialized. Please configure your API key or local AI server in settings.")
        
        # Import workflow profile
        from core.workflow_profile import WorkflowProfile
        
        # Default to NARRATIVE if not provided
        if workflow_profile is None:
            workflow_profile = WorkflowProfile.NARRATIVE
        
        genre_text = ", ".join(genres) if genres else "General"
        
        # Conditional prompt based on workflow profile
        if workflow_profile == WorkflowProfile.PROMOTIONAL:
            # Build brand context section
            brand_info = ""
            if brand_context:
                brand_info = f"""
BRAND / PRODUCT CONTEXT (REQUIRED - USE THIS INFORMATION):

"""
                if brand_context.brand_name:
                    brand_info += f"Brand Name: {brand_context.brand_name}\n"
                if brand_context.product_name:
                    brand_info += f"Product Name: {brand_context.product_name}\n"
                if brand_context.product_description:
                    brand_info += f"Product Description: {brand_context.product_description}\n"
                if brand_context.core_benefit:
                    brand_info += f"Core Benefit / Promise: {brand_context.core_benefit}\n"
                if brand_context.target_audience:
                    brand_info += f"Target Audience: {brand_context.target_audience}\n"
                if brand_context.brand_personality:
                    brand_info += f"Brand Personality: {', '.join(brand_context.brand_personality)}\n"
                if brand_context.mandatory_elements:
                    brand_info += f"Mandatory Inclusions: {', '.join(brand_context.mandatory_elements)}\n"
                
                brand_info += "\n"
            else:
                brand_info = "\nNOTE: No specific brand/product context provided. Generate a generic brand concept.\n"
            
            # Brand concept prompt for promotional content
            prompt = f"""
You are a professional brand strategist and creative director. Generate a concise brand concept for a promotional video based on the following:

Category: {genre_text if genre_text != "General" else "Brand Content"}
Brand Tone: {atmosphere}
{brand_info}
Output EXACTLY ONE brand concept. Do not provide multiple options, alternatives, or variations (no "Option 1/2", "Alternatively", "Or:", etc.). Give only the single concept you choose.

Create a brand concept that:
- Is 1-3 sentences long
- Focuses on VISUAL IDEA and EMOTIONAL TONE
- Explicitly references the product/brand and its core benefit (if provided above)
- Includes a CORE MESSAGE or brand value
- Is suitable for visual storytelling (no dialogue-heavy concepts)
- Captures the {atmosphere} brand tone
- Does NOT include character arcs, narrative conflict, or story elements
- Is designed for advertisement, brand film, or promotional content
- If mandatory elements are specified, incorporate them naturally

DO NOT generate:
- Character development arcs
- Narrative conflicts or plot
- Story conclusions
- Character relationships
- Generic brand concepts (if product/brand context is provided, USE IT)

DO generate:
- Visual concept or imagery that showcases the product/brand
- Emotional tone and mood that aligns with the brand personality
- Core brand message or value proposition (explicitly reference the core benefit)
- Optional call-to-action suggestion
- Product presence and brand payoff in the visual concept

Example format (with product context):
"A [visual concept featuring the product] that [emotional tone], conveying [core message about the product's benefit]. [Optional: call-to-action]"

Example format (without product context):
"A [visual concept] that [emotional tone], conveying [core message]. [Optional: call-to-action]"
"""
        elif workflow_profile == WorkflowProfile.EXPERIMENTAL:
            # Experimental/abstract concept prompt
            prompt = f"""
You are a professional experimental filmmaker and visual artist. Generate an abstract, non-narrative visual concept based on the following:

Themes: {genre_text if genre_text != "General" else "Abstract"}
Mood: {atmosphere}

Output EXACTLY ONE concept. Do not provide multiple options or alternatives. Give only the single concept you choose.

Create an experimental concept that:
- Is 1-3 sentences long
- Focuses on VISUAL THEMES and MOOD PROGRESSION
- Is non-linear and abstract
- Emphasizes imagery, symbolism, and emotional resonance
- Does NOT require traditional narrative structure
- Captures the {atmosphere} mood

DO NOT generate:
- Character arcs
- Linear plot progression
- Traditional story elements

DO generate:
- Visual themes and motifs
- Mood and atmosphere progression
- Abstract or symbolic concepts
"""
        else:
            # Narrative premise prompt (default)
            # Determine if single or multiple genres
            is_single_genre = len(genres) == 1 if genres else False
            
            # Build genre adherence instructions
            if is_single_genre:
                genre_instruction = f"""
CRITICAL GENRE ADHERENCE - SINGLE GENRE SELECTED:
- You have selected ONLY ONE genre: {genres[0]}
- You MUST stick to traditional themes and elements of the {genres[0]} genre ONLY
- DO NOT mix in elements from other genres (no fantasy elements like magic, artifacts, powers, supernatural abilities, etc. unless {genres[0]} is Fantasy)
- DO NOT mix in sci-fi elements (no advanced technology, aliens, time travel, etc. unless {genres[0]} is Science Fiction)
- Focus on realistic, genre-appropriate conflicts and situations
- Examples:
  * If genre is "War": focus on military conflict, soldiers, battles, strategy, survival, camaraderie, loss - NO magic, NO artifacts with powers, NO supernatural elements
  * If genre is "Crime": focus on criminals, police, investigations, heists, justice - NO magic, NO sci-fi technology
  * If genre is "Romance": focus on relationships, love, emotional conflicts - NO fantasy elements
  * If genre is "Horror": focus on fear, psychological terror, monsters (realistic or supernatural within horror tradition) - NO sci-fi technology unless it's sci-fi horror
"""
            else:
                genre_instruction = f"""
GENRE MIXING - MULTIPLE GENRES SELECTED:
- You have selected multiple genres: {genre_text}
- You MAY blend themes and elements from all selected genres
- Mixing genres is appropriate and encouraged
- Combine elements creatively while maintaining coherence
"""
            
            prompt = f"""
You are a professional screenwriter and story creator. Generate a compelling, cinematic story premise based on the following:

Genres: {genre_text}
Atmosphere/Tone: {atmosphere}

{genre_instruction}

Create a story premise that:
- Is 1-3 sentences long
- Is engaging and suitable for visual storytelling
- Clearly establishes a central conflict or situation
- Is cinematic and would work well as a video storyboard
- Captures the {atmosphere} atmosphere
- Follows the genre adherence rules above

CRITICAL FORMATTING REQUIREMENTS - YOU MUST FOLLOW THESE EXACTLY:

Output EXACTLY ONE premise. Do not provide multiple options, alternatives, or variations (no "Option 1/2", "Alternatively", "Or:", "Another premise", "Premise 2", etc.). Give only the single premise you choose.

Your ENTIRE response must be EXACTLY in this format:
FINAL PREMISE: [Your complete premise here, 1-3 sentences]

DO NOT include:
- Any reasoning (e.g., "An island seems like a good setting", "Instead of a typical monster, perhaps")
- Any suggestions (e.g., "Adding some immediate danger", "A countdown or limited timeframe")
- Any explanations or analysis
- Any text before "FINAL PREMISE:"
- Any text after the premise
- Multiple premises or alternatives (only one FINAL PREMISE block)

CORRECT Example:
FINAL PREMISE: A team of scientists discovers a portal to another dimension, but when they send a probe through, it returns with a deadly alien entity that begins to infect their research facility.

INCORRECT Examples (DO NOT DO THIS):
❌ An island seems like a good setting—it's inherently isolated. Instead of a typical monster, perhaps something more psychological or elusive.
❌ Adding some immediate danger can heighten suspense—like time running out for the protagonist.
❌ A countdown or limited timeframe creates urgency.

Your response format:
Line 1: FINAL PREMISE: [premise sentence 1]
Line 2: [premise sentence 2 if needed]
Line 3: [premise sentence 3 if needed]

That's it. Nothing else.
"""
        
        try:
            # Ensure client is initialized before making request
            if not self._adapter:
                # Try to reinitialize client in case settings were updated
                # First reload config to get latest settings
                config.reload_config()
                self.model_settings = config.get_model_settings()
                self._initialize_client()
                if not self._adapter:
                    api_key = config.get_openai_api_key()
                    if not api_key:
                        raise Exception("AI client not initialized. No API key found. Please configure your API key in settings.")
                    else:
                        raise Exception(f"AI client not initialized. API key is set but client creation failed. Please check your settings. Provider: {self.model_settings.get('provider', 'Unknown')}")
            
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You are a professional screenwriter specializing in creating compelling, cinematic story premises."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=1000  # Increased to allow for reasoning models that output longer responses
            )
            
            # Debug: Save raw response to file for troubleshooting
            try:
                import os
                debug_file = "debug_premise_response.json"
                debug_data = {
                    "response_type": str(type(response)),
                    "has_choices": hasattr(response, 'choices'),
                    "choices_count": len(response.choices) if hasattr(response, 'choices') and response.choices else 0,
                    "raw_response": str(response) if response else None
                }
                if hasattr(response, 'choices') and response.choices:
                    choice = response.choices[0]
                    debug_data["choice_type"] = str(type(choice))
                    debug_data["has_message"] = hasattr(choice, 'message')
                    if hasattr(choice, 'message'):
                        debug_data["message_type"] = str(type(choice.message))
                        debug_data["has_content"] = hasattr(choice.message, 'content')
                        if hasattr(choice.message, 'content'):
                            debug_data["content_type"] = str(type(choice.message.content))
                            debug_data["content_value"] = str(choice.message.content)[:500]  # First 500 chars
                with open(debug_file, 'w', encoding='utf-8') as f:
                    import json
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
            except Exception as debug_error:
                # Don't fail if debug logging fails
                pass
            
            # Check if response is valid
            if not response:
                raise Exception("AI returned None response. Please check your AI settings and try again.")
            
            if not hasattr(response, 'choices') or not response.choices or len(response.choices) == 0:
                raise Exception("AI returned an empty response (no choices). Please check your AI settings and try again.")
            
            # Get the content - handle different response structures
            choice = response.choices[0]
            if not hasattr(choice, 'message') or not choice.message:
                raise Exception("AI response has invalid structure (no message). Please check your AI settings.")
            
            # Check if response was truncated
            finish_reason = getattr(choice, 'finish_reason', None)
            if finish_reason == 'length':
                # Response was cut off due to max_tokens limit
                # This will be noted in the raw output display
                pass
            
            # Capture raw output for display
            raw_content = ""
            raw_reasoning = ""
            
            # Try to get content - handle different attribute names and response structures
            content = None
            
            # Standard OpenAI format - try to get the actual answer first
            if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                raw_content = choice.message.content or ""
                content = choice.message.content
                # If content exists and is not empty, use it (this is the actual premise, not reasoning)
                if content and content.strip():
                    # Check if content contains "FINAL PREMISE:" marker - extract just the premise (first one only)
                    final_premise_match = re.search(r'FINAL PREMISE[:\s]+(.+?)(?:\s*(?:FINAL PREMISE|$))', content, re.IGNORECASE | re.DOTALL)
                    if final_premise_match:
                        content = final_premise_match.group(1).strip()
                        # If model still returned multiple options, keep only the first premise (truncate at alternatives)
                        for stop in (r'\s+Alternatively\b', r'\s+Option\s+[2-9]', r'\s+Or:\s*', r'\s+Another\s+premise\s*',
                                    r'\s+Premise\s+[2-9]\s*', r'\s+Alternative\s*', r'\s+Variation\s+[2-9]\s*',
                                    r'\n\s*[2-9]\.\s+[A-Z]'):
                            m = re.search(stop, content, re.IGNORECASE)
                            if m:
                                content = content[:m.start()].strip()
                                break
                    # Content is the final answer, use it directly
                    pass
                else:
                    content = None
            
            # Capture reasoning if available
            if hasattr(choice, 'message') and hasattr(choice.message, 'reasoning'):
                raw_reasoning = choice.message.reasoning or ""
            
            # For reasoning models (like deepseek-r1), content may be empty but the FINAL answer is at the end of reasoning
            # We need to extract ONLY the final premise/result, not the reasoning process
            if (not content or not content.strip()) and hasattr(choice, 'message') and hasattr(choice.message, 'reasoning'):
                reasoning = choice.message.reasoning
                if reasoning and reasoning.strip():
                    # For reasoning models, we want ONLY the final premise/result, not the reasoning steps
                    # The final answer is usually at the very end of the reasoning, after all the thinking
                    
                    # Strategy 1: Look for premise markers that indicate the final conclusion
                    premise_markers = [
                        r'So putting it all together[:\s]+',
                        r'putting it all together[:\s]+',
                        r'Therefore[:\s]+',
                        r'Final premise[:\s]+',
                        r'Premise[:\s]+',
                        r'Conclusion[:\s]+',
                        r'So[:\s]+',
                    ]
                    
                    for marker in premise_markers:
                        # Extract text after the marker - this should be the final premise (not reasoning)
                        # For "FINAL PREMISE:" marker, extract more text (up to 800 chars) to get the complete premise
                        max_chars = 800 if 'FINAL PREMISE' in marker.upper() else 1000
                        # Stop at meta-commentary or reasoning indicators
                        stop_pattern = r'(?:\s*(?:The user|so vivid|visual and cinematic|storyboard|vivid imagery|is key|mentioned|should work|is clear|engaging for|sets up|Adding some|can heighten|creates urgency|like time|A countdown|FINAL PREMISE|\.\.\.)|"|$)'
                        match = re.search(marker + r'(.{50,' + str(max_chars) + r'}?)' + stop_pattern, reasoning, re.IGNORECASE | re.DOTALL)
                        if match:
                            extracted = match.group(1).strip()
                            extracted = extracted.rstrip('"').strip()
                            extracted = re.sub(r'\.\.\..*$', '', extracted).strip()
                            
                            # Filter out reasoning/suggestion patterns
                            # Remove sentences that are suggestions, not the actual premise
                            suggestion_patterns = [
                                r'Adding some.*',
                                r'can heighten.*',
                                r'creates urgency.*',
                                r'like time.*',
                                r'A countdown.*',
                                r'limited timeframe.*',
                                r'can.*',
                                r'should.*',
                                r'could.*',
                                r'might.*',
                                r'would.*',
                            ]
                            for pattern in suggestion_patterns:
                                extracted = re.sub(pattern, '', extracted, flags=re.IGNORECASE)
                            
                            # Extract complete sentences (premises are usually 1-3 sentences)
                            sentences = re.findall(r'([A-Z][^.!?]{20,}[.!?])', extracted)
                            if sentences:
                                filtered_sentences = []
                                meta_keywords = ['visual and cinematic', 'user mentioned', 'should work', 'storyboard', 'vivid imagery', 'is key', 'is clear', 'mentioned it', 'visual storytelling', 'cinematic feel', 'engaging for', 'sets up']
                                thinking_words = ['So', 'Therefore', 'Hmm', 'Wait', 'Maybe', 'Perhaps', 'If', 'When', 'Who', 'Alright', 'Let me', 'I need', 'They want', 'combining', 'suspenseful', 'implies', 'I think', 'I believe']
                                suggestion_starters = ['Adding', 'can heighten', 'creates', 'creates urgency', 'like time', 'A countdown', 'limited timeframe', 'can', 'should', 'could', 'might', 'would']
                                reasoning_starters = ['An island seems', 'Instead of', 'Perhaps', 'Maybe', 'It seems', 'seems like', 'inherently', 'Instead of a', 'perhaps something', 'or perhaps', 'could be', 'might be']
                                
                                for sent in sentences:
                                    sent_lower = sent.lower()
                                    sent_stripped = sent.strip()
                                    
                                    # Skip if it's a suggestion, not a premise
                                    if any(sent_stripped.startswith(starter) for starter in suggestion_starters):
                                        continue
                                    # Skip reasoning sentences (e.g., "An island seems like a good setting", "Instead of a typical monster")
                                    if any(sent_stripped.startswith(starter) for starter in reasoning_starters):
                                        continue
                                    # Skip sentences that contain reasoning patterns
                                    if any(phrase in sent_lower for phrase in ['seems like', 'inherently', 'instead of', 'perhaps something', 'or perhaps', 'could be', 'might be', 'would be']):
                                        continue
                                    # Stop at meta-commentary
                                    if any(keyword in sent_lower for keyword in meta_keywords):
                                        break
                                    # Skip thinking/reasoning sentences
                                    if any(sent_stripped.startswith(word) for word in thinking_words):
                                        continue
                                    filtered_sentences.append(sent)
                                    if len(filtered_sentences) >= 3:
                                        break
                                
                                if filtered_sentences:
                                    premise_text = ' '.join(filtered_sentences).strip()
                                    if len(premise_text) > 30:
                                        content = premise_text
                                        break
                    
                    # Strategy 2: Get the LAST sentences from reasoning (the final conclusion, not reasoning steps)
                    if not content or not content.strip():
                        # Get the last 800 characters where the final answer usually is
                        last_part = reasoning[-800:] if len(reasoning) > 800 else reasoning
                        
                        # Find all complete sentences
                        all_sentences = re.findall(r'([A-Z][^.!?]{30,}[.!?])', last_part)
                        if all_sentences:
                            # Filter to get ONLY premise sentences (skip reasoning steps)
                            premise_sentences = []
                            meta_keywords = ['visual and cinematic', 'user mentioned', 'should work', 'storyboard', 'vivid imagery', 'is key', 'is clear', 'mentioned it', 'visual storytelling', 'cinematic feel', 'engaging for', 'sets up']
                            thinking_words = ['So', 'Therefore', 'Hmm', 'Wait', 'Maybe', 'Perhaps', 'If', 'When', 'Who', 'Alright', 'Let me', 'I need', 'They want', 'combining', 'suspenseful', 'implies', 'I think', 'I believe', 'Perhaps', 'Maybe']
                            
                            # Go through sentences in reverse (from end to start) to find the final premise
                            suggestion_starters = ['Adding', 'can heighten', 'creates', 'creates urgency', 'like time', 'A countdown', 'limited timeframe', 'can', 'should', 'could', 'might', 'would']
                            reasoning_starters = ['An island seems', 'Instead of', 'Perhaps', 'Maybe', 'It seems', 'seems like', 'inherently', 'Instead of a', 'perhaps something', 'or perhaps', 'could be', 'might be']
                            
                            for sent in reversed(all_sentences):
                                sent_lower = sent.lower()
                                sent_stripped = sent.strip()
                                
                                # Skip suggestion sentences (not actual premises)
                                if any(sent_stripped.startswith(starter) for starter in suggestion_starters):
                                    continue
                                # Skip reasoning sentences (e.g., "An island seems like a good setting", "Instead of a typical monster")
                                if any(sent_stripped.startswith(starter) for starter in reasoning_starters):
                                    continue
                                # Skip sentences that contain reasoning patterns
                                if any(phrase in sent_lower for phrase in ['seems like', 'inherently', 'instead of', 'perhaps something', 'or perhaps', 'could be', 'might be', 'would be']):
                                    continue
                                # Skip meta-commentary
                                if any(keyword in sent_lower for keyword in meta_keywords):
                                    continue
                                # Skip thinking/reasoning sentences
                                if any(sent_stripped.startswith(word) for word in thinking_words):
                                    continue
                                # Skip questions
                                if sent_stripped.endswith('?'):
                                    continue
                                # Look for sentences that describe a story (start with A, The, In, When, After, etc.)
                                if re.match(r'^(A|The|In|When|After|A group|A team|A character|A scientist|A detective)', sent, re.IGNORECASE):
                                    premise_sentences.insert(0, sent)  # Add to beginning to maintain order
                                    if len(premise_sentences) >= 3:
                                        break
                            
                            if premise_sentences:
                                premise_text = ' '.join(premise_sentences).strip()
                                if len(premise_text) > 30:
                                    content = premise_text
                    
                    # If we found a partial premise (starts with "The central conflict" or similar), try to get the full premise
                    if content and (content.startswith("The central conflict") or content.startswith("central conflict") or "might involve" in content.lower()):
                        # This is likely a fragment - try to find the complete premise
                        for marker in premise_markers:
                            # Get more text after the marker
                            match = re.search(marker + r'(.{100,800}?)(?:\s*(?:The user|so vivid|visual and cinematic|storyboard|vivid imagery|is key|mentioned|should work|is clear|\.\.\.)|"|$)', reasoning, re.IGNORECASE | re.DOTALL)
                            if match:
                                extracted = match.group(1).strip()
                                # Find all sentences
                                all_sentences = re.findall(r'([A-Z][^.!?]{20,}[.!?])', extracted)
                                if all_sentences:
                                    # Take sentences that form the premise (usually 1-3 sentences)
                                    # Skip meta-commentary and thinking sentences
                                    premise_sentences = []
                                    meta_keywords = ['visual and cinematic', 'user mentioned', 'should work', 'storyboard', 'vivid imagery', 'is key', 'is clear', 'mentioned it', 'visual storytelling', 'cinematic feel', 'engaging for', 'sets up']
                                    
                                    for sent in all_sentences:
                                        sent_lower = sent.lower()
                                        if any(keyword in sent_lower for keyword in meta_keywords):
                                            break  # Stop at meta-commentary
                                        if re.match(r'^(So|Therefore|Hmm|Wait|Maybe|Perhaps|If|When|Who|Alright|Let me|I need|They want|combining|suspenseful|implies)', sent, re.IGNORECASE):
                                            continue
                                        premise_sentences.append(sent)
                                        # Stop if we have 3 sentences (premises are usually 1-3 sentences)
                                        if len(premise_sentences) >= 3:
                                            break
                                    
                                    if premise_sentences:
                                        full_premise = ' '.join(premise_sentences).strip()
                                        if len(full_premise) > len(content):
                                            content = full_premise
                                            break
                    
                    # If still no content, try a different approach: find the last complete sentence that looks like a premise
                    if not content or not content.strip():
                        # Look for sentences that start with story-like patterns
                        story_patterns = [
                            r'(A [^.!?]{30,}[.!?])',
                            r'(The [^.!?]{30,}[.!?])',
                            r'(In [^.!?]{30,}[.!?])',
                            r'(When [^.!?]{30,}[.!?])',
                            r'(After [^.!?]{30,}[.!?])',
                        ]
                        
                        # Check the last 500 characters of reasoning
                        last_part = reasoning[-500:] if len(reasoning) > 500 else reasoning
                        
                        for pattern in story_patterns:
                            matches = list(re.finditer(pattern, last_part, re.IGNORECASE))
                            if matches:
                                # Take the last match that doesn't contain meta-commentary
                                for match in reversed(matches):
                                    sentence = match.group(1).strip()
                                    meta_keywords = ['visual and cinematic', 'user mentioned', 'should work', 'storyboard', 'vivid imagery', 'is key', 'is clear', 'mentioned it', 'visual storytelling', 'cinematic feel', 'engaging for', 'sets up', 'central conflict']
                                    if not any(keyword in sentence.lower() for keyword in meta_keywords):
                                        # Check if it's not a thinking sentence
                                        if not re.match(r'^(So|Therefore|Hmm|Wait|Maybe|Perhaps|If|When|Who|Alright|Let me|I need|They want|combining|suspenseful|implies)', sentence, re.IGNORECASE):
                                            if len(sentence) > 40:
                                                content = sentence
                                                # Try to get 2 sentences if available
                                                idx = last_part.rfind(sentence)
                                                if idx > 0:
                                                    before = last_part[:idx]
                                                    prev_sentence = re.search(r'([A-Z][^.!?]{30,}[.!?])\s*$', before)
                                                    if prev_sentence:
                                                        prev = prev_sentence.group(1).strip()
                                                        if not any(keyword in prev.lower() for keyword in meta_keywords):
                                                            if not re.match(r'^(So|Therefore|Hmm|Wait|Maybe|Perhaps|If|When|Who|Alright|Let me|I need|They want)', prev, re.IGNORECASE):
                                                                content = prev + ' ' + content
                                                break
                                if content:
                                    break
                            if content:
                                break
                    
                    # If no pattern match, try to get the last complete sentence(s) that form a premise
                    if not content or not content.strip():
                        # Split reasoning into sentences
                        sentences = re.split(r'([.!?]+\s+)', reasoning)
                        # Reconstruct complete sentences
                        complete_sentences = []
                        for i in range(0, len(sentences)-1, 2):
                            if i+1 < len(sentences):
                                sentence = (sentences[i] + sentences[i+1]).strip()
                                if len(sentence) > 30:
                                    complete_sentences.append(sentence)
                        
                        # Look for the actual premise - usually the last 1-2 sentences that:
                        # 1. Don't start with thinking words (So, Therefore, Hmm, Wait, Maybe, Perhaps, If, When, Who)
                        # 2. Don't contain meta-commentary (user mentioned, should work, visual and cinematic, storyboard, vivid imagery)
                        # 3. Are complete sentences describing a story
                        thinking_words = r'^(So|Therefore|Hmm|Wait|Maybe|Perhaps|If|When|Who|Alright|Let me|I need|They want|combining|suspenseful|implies|Maybe|Perhaps|Who would)'
                        meta_keywords = r'(user mentioned|should work|visual and cinematic|storyboard|vivid imagery|is key|The user|mentioned it)'
                        
                        # Check last 3-5 sentences
                        for sentence in reversed(complete_sentences[-5:]):
                            sentence_lower = sentence.lower()
                            # Skip if it contains meta-commentary
                            if not re.search(meta_keywords, sentence_lower, re.IGNORECASE):
                                # Skip if it starts with thinking words
                                if not re.match(thinking_words, sentence, re.IGNORECASE):
                                    # Check if it looks like a story premise (starts with "A", "The", "In", etc. or describes a situation)
                                    if re.match(r'^[A-Z]', sentence) and len(sentence) > 40:
                                        content = sentence
                                        # Try to get 1-2 sentences if available
                                        idx = complete_sentences.index(sentence)
                                        if idx > 0 and len(complete_sentences) > idx:
                                            # Check if previous sentence is also a premise
                                            prev_sentence = complete_sentences[idx-1]
                                            if not re.search(meta_keywords, prev_sentence.lower(), re.IGNORECASE) and not re.match(thinking_words, prev_sentence, re.IGNORECASE):
                                                if len(prev_sentence) > 30:
                                                    content = prev_sentence + " " + content
                                        break
                    
                    # Last resort: extract from the end of reasoning, but filter out meta-commentary
                    if not content or not content.strip():
                        # Get the last 400 characters
                        last_part = reasoning[-400:].strip()
                        # Try to find complete sentences, excluding meta-commentary
                        sentences = re.findall(r'([A-Z][^.!?]{30,}[.!?])', last_part)
                        if sentences:
                            # Take sentences that don't contain meta-commentary
                            for sentence in reversed(sentences):
                                if not re.search(r'(user mentioned|should work|visual and cinematic|storyboard|vivid imagery|is key|The user|mentioned it)', sentence, re.IGNORECASE):
                                    if len(sentence) > 40:
                                        content = sentence.strip()
                                        break
                        
                        # If still nothing, try to extract from "So putting it all together" pattern more broadly
                        if not content or not content.strip():
                            broad_match = re.search(r'(?:So putting it all together|putting it all together|Therefore|So)[:\s]+(.{50,300}?)(?:\s*(?:The protagonist|The user|so vivid|visual|cinematic|storyboard|vivid imagery|is key|mentioned|should work))', reasoning, re.IGNORECASE | re.DOTALL)
                            if broad_match:
                                extracted = broad_match.group(1).strip()
                                # Clean up
                                extracted = re.sub(r'\s*(?:The protagonist|The user|so vivid|visual|cinematic|storyboard|vivid imagery|is key|mentioned|should work).*$', '', extracted, flags=re.IGNORECASE).strip()
                                # Get last complete sentence
                                last_sentence = re.search(r'([^.!?]+[.!?])', extracted)
                                if last_sentence:
                                    content = last_sentence.group(1).strip()
                                else:
                                    content = extracted[:200].strip()
            
            # Alternative format: direct text attribute
            if (not content or not content.strip()) and hasattr(choice, 'text'):
                content = choice.text
            # Alternative format: message.text
            elif (not content or not content.strip()) and hasattr(choice, 'message') and hasattr(choice.message, 'text'):
                content = choice.message.text
            # Try to get from delta (streaming responses)
            elif (not content or not content.strip()) and hasattr(choice, 'delta') and hasattr(choice.delta, 'content'):
                content = choice.delta.content
            # Last resort: try to extract from string representation
            elif not content or not content.strip():
                # Try to find content in the response object
                response_dict = {}
                if hasattr(choice.message, '__dict__'):
                    response_dict = choice.message.__dict__
                elif hasattr(choice, '__dict__'):
                    response_dict = choice.__dict__
                elif hasattr(response, '__dict__'):
                    response_dict = response.__dict__
                
                # Look for any field that might contain text (reasoning, content, text, etc.)
                for key, value in response_dict.items():
                    if isinstance(value, str) and len(value) > 20:
                        # Prefer fields that sound like they contain the answer
                        if key.lower() in ['reasoning', 'content', 'text', 'message']:
                            content = value
                            break
                
                # If still no content, look for any string field
                if not content or not content.strip():
                    for key, value in response_dict.items():
                        if isinstance(value, str) and len(value) > 20:
                            content = value
                            break
                
                if not content or not content.strip():
                    # Try to extract from string representation
                    response_str = str(response)
                    # Look for quoted text that might be the premise
                    text_matches = re.findall(r'["\']([^"\']{20,200})["\']', response_str)
                    if text_matches:
                        # Take the longest match as it's likely the premise
                        content = max(text_matches, key=len)
            
            if content is None:
                # Try to get any text from the response
                response_str = str(response)
                if hasattr(choice.message, '__dict__'):
                    response_str += f"\nMessage attributes: {choice.message.__dict__}"
                raise Exception(f"AI returned None for content. Response structure may be different. Please check your AI settings. Debug info saved to debug_premise_response.json")
            
            premise = str(content).strip()
            # If model returned multiple options, keep only the first premise (all branches)
            for stop in (r'\s+Alternatively\b', r'\s+Option\s+[2-9]', r'\s+Or:\s*', r'\s+Another\s+(?:premise|concept|option)\s*',
                        r'\s+Premise\s+[2-9]\s*', r'\s+Alternative\s*', r'\s+Variation\s+[2-9]\s*',
                        r'\n\s*[2-9]\.\s+[A-Z]'):
                m = re.search(stop, premise, re.IGNORECASE)
                if m:
                    premise = premise[:m.start()].strip()
                    break

            # Check if we got the response object string instead of actual content
            if premise.startswith("ChatCompletion") or premise.startswith("choices=[Choice"):
                # This means we got the string representation of the response object
                # Try to extract from reasoning if available
                if hasattr(choice, 'message') and hasattr(choice.message, 'reasoning'):
                    reasoning = choice.message.reasoning
                    if reasoning:
                        # Extract premise from reasoning
                        match = re.search(r'So putting it all together[:\s]+([^"]{20,300}?)(?:\s*The protagonist|"|$)', reasoning, re.IGNORECASE | re.DOTALL)
                        if match:
                            premise = match.group(1).strip()
                            premise = re.sub(r'\s*The protagonist.*$', '', premise, flags=re.IGNORECASE).strip()
                        else:
                            # Get last complete sentence
                            sentence_match = re.search(r'([A-Z][^.!?]{30,}[.!?])', reasoning[-300:])
                            if sentence_match:
                                premise = sentence_match.group(1).strip()
                            else:
                                raise Exception(f"Could not extract premise from reasoning. Debug info saved to debug_premise_response.json")
                else:
                    raise Exception(f"AI returned response object string instead of content. Please check your AI settings. Debug info saved to debug_premise_response.json")
            
            # If still empty after stripping, raise error with more info
            if not premise:
                # Try to extract from the full response as a last resort
                response_str = str(response)
                # Look for any text that might be the premise
                text_match = re.search(r'["\']([^"\']{20,})["\']', response_str)
                if text_match:
                    premise = text_match.group(1).strip()
                    if premise and len(premise) > 10:
                        # Found something that looks like a premise
                        pass
                    else:
                        raise Exception(f"AI returned empty content after stripping. Original content type: {type(content)}, value: '{content[:100]}'. Debug info saved to debug_premise_response.json")
                else:
                    raise Exception(f"AI returned empty content after stripping. Original content type: {type(content)}, value: '{content[:100]}'. Debug info saved to debug_premise_response.json")
            
            # Save original for fallback
            original_premise = premise
            
            # Remove markdown code blocks if present (preserve content inside)
            premise = re.sub(r'```[a-z]*\s*\n?', '', premise)
            premise = re.sub(r'\n?\s*```', '', premise)
            premise = premise.strip()
            
            # If empty after removing markdown, restore original
            if not premise:
                premise = original_premise
            
            # Clean up surrounding quotes only (keep quotes in the middle of text)
            if len(premise) > 2:
                if (premise.startswith('"') and premise.endswith('"')) or (premise.startswith("'") and premise.endswith("'")):
                    premise = premise[1:-1].strip()
            
            # Remove common prefixes that AI might add (but be conservative)
            prefixes_to_remove = [
                "Premise:",
                "Story Premise:",
                "Here's a premise:",
                "Here is a premise:",
                "The premise is:",
                "Story:",
                "Here's the story:",
            ]
            for prefix in prefixes_to_remove:
                if premise.lower().startswith(prefix.lower()):
                    premise = premise[len(prefix):].strip()
                    # Remove colon if present
                    if premise.startswith(":"):
                        premise = premise[1:].strip()
                    break  # Only remove one prefix
            
            # Don't remove standalone "Premise" - it might be part of the actual text
            # Only remove "Premise:" with colon
            if premise.lower().startswith("premise:"):
                premise = premise[8:].strip()
            
            # Remove leading/trailing punctuation (but be conservative)
            premise = premise.strip('.,;:!?')
            premise = premise.strip()
            
            # Filter out meta-commentary and reasoning fragments that might have slipped through
            meta_phrases = [
                r'that\'?s visual and cinematic',
                r'user mentioned',
                r'should work',
                r'video storyboard',
                r'vivid imagery',
                r'is key',
                r'is clear',
                r'is clear about',
                r'mentioned it',
                r'visual storytelling',
                r'cinematic feel',
                r'engaging for',
                r'sets up',
                r'central conflict',
            ]
            for phrase in meta_phrases:
                # Remove phrases that are clearly meta-commentary
                premise = re.sub(r'\s*' + phrase + r'[^.!?]*[.!?]?\s*', ' ', premise, flags=re.IGNORECASE)
                premise = premise.strip()
            
            # Remove reasoning sentences that might have slipped through
            # Split premise into sentences and filter out reasoning ones
            premise_sentences = re.split(r'([.!?]+\s+)', premise)
            filtered_premise_sentences = []
            reasoning_patterns = [
                r'^An island seems',
                r'^Instead of',
                r'^Perhaps',
                r'^Maybe',
                r'^It seems',
                r'seems like',
                r'inherently',
                r'or perhaps',
                r'could be',
                r'might be',
                r'would be',
                r'^Adding',
                r'can heighten',
                r'creates',
            ]
            
            for i in range(0, len(premise_sentences)-1, 2):
                if i+1 < len(premise_sentences):
                    sentence = (premise_sentences[i] + premise_sentences[i+1]).strip()
                    sentence_lower = sentence.lower()
                    # Skip if it's a reasoning sentence
                    is_reasoning = False
                    for pattern in reasoning_patterns:
                        if re.match(pattern, sentence, re.IGNORECASE) or pattern.lower() in sentence_lower:
                            is_reasoning = True
                            break
                    if not is_reasoning:
                        filtered_premise_sentences.append(sentence)
            
            if filtered_premise_sentences:
                premise = ' '.join(filtered_premise_sentences).strip()
            else:
                # If all sentences were filtered, keep original but try to clean it
                premise = premise.strip()
            
            # Check if premise is a fragment (doesn't start properly or is too short)
            if premise:
                # A valid premise should start with a capital letter followed by a word
                if not re.match(r'^[A-Z][a-z]+', premise):
                    # Doesn't start properly, try to find the actual start
                    match = re.search(r'([A-Z][a-z]+[^.!?]{20,}[.!?])', premise)
                    if match:
                        premise = match.group(1).strip()
                    else:
                        premise = ""
                
                # Check if it's just a fragment (ends with incomplete words or is too short)
                if len(premise) < 30 or not premise.endswith(('.', '!', '?')):
                    # Try to extract complete sentences only
                    sentences = re.findall(r'([A-Z][^.!?]{30,}[.!?])', premise)
                    if sentences:
                        premise = ' '.join(sentences).strip()
                    else:
                        premise = ""
            
            # If the premise is still meta-commentary or a fragment, try to extract the actual premise from reasoning again
            if not premise or len(premise) < 30 or any(phrase in premise.lower() for phrase in ['visual and cinematic', 'user mentioned', 'should work', 'storyboard', 'vivid imagery', 'is key', 'is clear', 'is clear about']):
                # This is likely still meta-commentary or a fragment, try to get the actual premise
                if hasattr(choice, 'message') and hasattr(choice.message, 'reasoning'):
                    reasoning = choice.message.reasoning
                    # Look for the actual story premise - usually starts with "A" or "The" and describes a situation
                    # Try multiple patterns to find the actual premise
                    story_patterns = [
                        r'(?:So putting it all together|putting it all together|Therefore|So)[:\s]+((?:A|The|In|When|After)[^.!?]{40,}[.!?])',
                        r'((?:A|The)[^.!?]{40,}(?:opens|discovers|finds|creates|builds|destroys|saves|stops|starts|begins|ends|meets|fights|escapes|returns|leaves|arrives|finds|loses|gains|learns|realizes|decides|chooses|tries|succeeds|fails)[^.!?]{10,}[.!?])',
                    ]
                    
                    for pattern in story_patterns:
                        match = re.search(pattern, reasoning, re.IGNORECASE | re.DOTALL)
                        if match:
                            extracted = match.group(1).strip()
                            # Clean it
                            extracted = re.sub(r'\s*(?:The protagonist|The user|so vivid|visual|cinematic|storyboard|vivid imagery|is key|mentioned|should work|is clear|is clear about).*$', '', extracted, flags=re.IGNORECASE).strip()
                            # Ensure it's a complete sentence
                            if extracted.endswith(('.', '!', '?')) and len(extracted) > 40:
                                if not any(phrase in extracted.lower() for phrase in ['visual and cinematic', 'user mentioned', 'should work', 'storyboard', 'vivid imagery', 'is key', 'is clear', 'is clear about']):
                                    premise = extracted
                                    break
                    
                    # Last resort: find the longest complete sentence that looks like a story
                    if not premise or len(premise) < 30:
                        all_sentences = re.findall(r'([A-Z][^.!?]{40,}[.!?])', reasoning)
                        for sent in reversed(all_sentences):
                            sent_lower = sent.lower()
                            # Must not contain meta-commentary
                            if not any(phrase in sent_lower for phrase in ['visual and cinematic', 'user mentioned', 'should work', 'storyboard', 'vivid imagery', 'is key', 'is clear', 'is clear about', 'mentioned it']):
                                # Must not start with thinking words
                                if not re.match(r'^(So|Therefore|Hmm|Wait|Maybe|Perhaps|If|When|Who|Alright|Let me|I need|They want|combining|suspenseful|implies)', sent, re.IGNORECASE):
                                    # Should describe a story situation
                                    if re.match(r'^(A|The|In|When|After)', sent, re.IGNORECASE):
                                        premise = sent.strip()
                                        break
            
            # Validate premise is not empty after cleaning
            if not premise:
                # Last resort: use original with minimal cleaning
                premise = str(content).strip()
                # Only remove markdown and outer quotes
                premise = re.sub(r'```[a-z]*\s*\n?', '', premise)
                premise = re.sub(r'\n?\s*```', '', premise)
                premise = premise.strip()
                if len(premise) > 2 and ((premise.startswith('"') and premise.endswith('"')) or (premise.startswith("'") and premise.endswith("'"))):
                    premise = premise[1:-1].strip()
                premise = premise.strip()
                
                if not premise:
                    raise Exception(f"AI generated an empty premise after processing. Original content: '{original_premise[:200]}'. Debug info saved to debug_premise_response.json")
            
            # Ensure premise is reasonable length (at least 10 characters)
            if len(premise) < 10:
                raise Exception(f"AI generated a premise that is too short ({len(premise)} characters): '{premise}'. Original: '{original_premise[:200]}'. Debug info saved to debug_premise_response.json")
            
            # If return_raw is True, return the raw content before processing
            if return_raw:
                # Build comprehensive raw output display
                raw_output = "=== RAW AI OUTPUT ===\n\n"
                
                # Check if response was truncated
                finish_reason = getattr(choice, 'finish_reason', None)
                if finish_reason == 'length':
                    raw_output += "⚠️ WARNING: Response was truncated due to max_tokens limit!\n\n"
                
                # Add content field if available
                if raw_content:
                    raw_output += f"CONTENT FIELD:\n{raw_content}\n\n"
                
                # Add reasoning field if available
                if raw_reasoning:
                    raw_output += f"REASONING FIELD:\n{raw_reasoning}\n\n"
                
                # Add full response string if no content/reasoning
                if not raw_content and not raw_reasoning:
                    raw_output += f"FULL RESPONSE:\n{str(response)}\n\n"
                
                # Add finish reason info
                if finish_reason:
                    raw_output += f"FINISH REASON: {finish_reason}\n\n"
                
                # Add processed premise
                raw_output += f"=== PROCESSED PREMISE ===\n\n{premise}"
                
                return raw_output
            
            return premise
                
        except openai.APIConnectionError as e:
            # Connection error - provide more helpful message
            error_message = str(e)
            raise Exception(f"Failed to generate premise: Connection error. Please check your internet connection and API settings. Details: {error_message}")
        except openai.APIError as e:
            # API error - provide more helpful message
            error_message = str(e)
            raise Exception(f"Failed to generate premise: API error. Please check your API key and settings. Details: {error_message}")
        except Exception as e:
            error_message = str(e)
            # Check if it's a connection-related error
            if "connection" in error_message.lower() or "connect" in error_message.lower():
                raise Exception(f"Failed to generate premise: Connection error. Please check your internet connection and API settings. Details: {error_message}")
            raise Exception(f"Failed to generate premise: {error_message}")
    
    def generate_story_outline(self, premise: str, genres: List[str], atmosphere: str, title: str = "", workflow_profile=None, character_count: Optional[int] = None, length: str = "medium") -> Dict[str, Any]:
        """Generate a comprehensive story outline with subplots, character outlines, character growth arcs, and conclusion.
        
        Args:
            premise: Story premise
            genres: List of genres
            atmosphere: Atmosphere/tone
            title: Story title
            workflow_profile: WorkflowProfile enum (NARRATIVE, PROMOTIONAL, etc.)
            character_count: For NARRATIVE, exact number of characters to declare and use (must generate EXACTLY this many).
            length: Story length (micro, short, medium, long). Micro narratives skip subplots and character outlines/arcs.
        """
        
        if not self._adapter:
            raise Exception("AI client not initialized. Please configure your API key or local AI server in settings.")
        
        # Import workflow profile
        from core.workflow_profile import WorkflowProfile
        
        # Default to NARRATIVE if not provided
        if workflow_profile is None:
            workflow_profile = WorkflowProfile.NARRATIVE
        
        genre_text = ", ".join(genres) if genres else "General"
        title_text = f"Title: {title}\n" if title else "Title: (none provided — you MUST generate an original, evocative title for this story)\n"
        n_characters = character_count if (character_count is not None and character_count > 0) else None
        
        # Conditional prompt based on workflow profile
        if workflow_profile == WorkflowProfile.PROMOTIONAL:
            # Promotional outline prompt
            prompt = f"""
You are a professional brand strategist and creative director. Create a promotional content structure based on this brand concept:

{title_text}Brand Concept: {premise}
Category: {genre_text}
Brand Tone: {atmosphere}

Create a promotional content structure that includes:

1. CORE MESSAGE:
   - The central brand message or value proposition
   - What the brand wants to communicate
   - Should be 2-3 sentences, clear and concise

2. EMOTIONAL BEAT PROGRESSION:
   - 3-5 emotional beats that progress the mood and message
   - Each beat should describe the emotional tone and visual progression
   - Format as a single continuous text string
   - Example: "Beat 1: Opening establishes [mood]. Beat 2: Builds to [emotion]. Beat 3: Climax reveals [message]..."

3. VISUAL MOTIFS / IMAGERY THEMES:
   - Key visual elements, imagery, and motifs to emphasize
   - What visual elements should appear throughout
   - Should be 3-5 sentences describing visual themes

4. CALL TO ACTION (Optional):
   - Optional call-to-action or next step for the audience
   - Can be empty if not applicable

CRITICAL: This is PROMOTIONAL CONTENT, not a narrative story.
- DO NOT create subplots, character arcs, or narrative conclusions
- Focus on brand message, emotional progression, and visual themes
- Characters are optional visual elements, not narrative agents

CRITICAL: You MUST return ONLY valid JSON. No markdown, no explanations, no code blocks.

Format your response as a JSON object with this EXACT structure:
{{
    "main_storyline": "Core Message: [2-3 sentences describing the central brand message or value proposition]",
    "subplots": "",
    "conclusion": "",
    "core_message": "The central brand message or value proposition (2-3 sentences)",
    "emotional_beats": "3-5 emotional beats that progress the mood and message, formatted as a single continuous text string",
    "visual_motifs": "Key visual elements, imagery, and motifs to emphasize (3-5 sentences)",
    "call_to_action": "Optional call-to-action or next step for the audience (can be empty)"
}}
"""
        elif workflow_profile == WorkflowProfile.EXPERIMENTAL:
            # Experimental outline prompt
            prompt = f"""
You are a professional experimental filmmaker. Create an experimental content structure based on this concept:

{title_text}Concept: {premise}
Themes: {genre_text}
Mood: {atmosphere}

Create an experimental content structure that includes:

1. CONCEPT:
   - The core experimental concept
   - What the piece explores visually and thematically
   - Should be 3-5 sentences

2. VISUAL THEMES:
   - Key visual themes and motifs
   - Imagery and symbolic elements
   - Should be 3-5 sentences

3. MOOD PROGRESSION:
   - How the mood and atmosphere progress
   - Emotional or thematic progression
   - Should be 3-5 sentences

CRITICAL: This is EXPERIMENTAL/ABSTRACT CONTENT, not a narrative story.
- DO NOT create subplots, character arcs, or narrative conclusions
- Focus on visual themes, mood, and abstract concepts

CRITICAL: You MUST return ONLY valid JSON. No markdown, no explanations, no code blocks.

Format your response as a JSON object with this EXACT structure:
{{
    "main_storyline": "Concept: [3-5 sentences describing the core experimental concept]",
    "subplots": "",
    "conclusion": "",
    "concept": "The core experimental concept (3-5 sentences)",
    "visual_themes": "Key visual themes and motifs (3-5 sentences)",
    "mood_progression": "How the mood and atmosphere progress (3-5 sentences)"
}}
"""
        else:
            # Narrative outline prompt (default)
            is_micro_narrative = (length == "micro" and workflow_profile == WorkflowProfile.NARRATIVE)
            char_count_block = ""
            char_json_block = ""
            if n_characters is not None:
                if is_micro_narrative:
                    char_count_block = f"""
MAIN CHARACTERS (UP TO {n_characters}):
- Generate UP TO {n_characters} main characters. Only create as many as the story naturally needs — do not force characters.
- This is a MICRO story (very short). Characters need ONLY a name and physical_appearance. Do NOT generate outline or growth_arc."""
                else:
                    char_count_block = f"""
MAIN CHARACTERS (UP TO {n_characters}):
- Generate UP TO {n_characters} main characters. Main characters are the protagonist, their companions, and the antagonist.
- Only create as many main characters as the story naturally needs — do not force characters to reach {n_characters}. You may generate fewer if the story works better with fewer.
- These main characters will be used in Character Details and must NOT be replaced by any other characters.
- Use FULL CAPITAL LETTERS for main character names (e.g. MAYA RIVERA, ELIAS CROSS, SARAH CHEN).
- Each main character must have a unique, human, plausible name. Use simple first and last names for most. Use First 'Nickname' Last sparingly.
- CRITICAL: If a character is REBECCA 'REX' STERN, referring to them as REX is the SAME character — never extract or list them twice. One person = one character entry. Nickname-only references (REX) and full-name references (REBECCA 'REX' STERN) are the same character.

MAIN CHARACTERS MUST BE THE FIRST MENTIONED IN THE MAIN STORYLINE:
- In the expanded main_storyline, introduce and mention ALL main characters FIRST, in order of appearance, before any minor characters.
- The "characters" array MUST contain ONLY the main characters mentioned in the main storyline (in order of first mention). No other characters get outlines.
- The main storyline must lead with these main characters. Minor characters may appear later but must NOT be in the characters array.

STRUCTURAL REQUIREMENT — PROTAGONIST FIRST:
- Never list the same character twice (e.g. LYRA DAVIS appearing twice = invalid).
- Character #1 MUST be the protagonist (the central character who drives the story). The FIRST SENTENCE of main_storyline MUST name the protagonist by their full name (FULL CAPS).
- ALL main characters MUST appear by full name in the main_storyline. All must also be mentioned by name in the subplots (each subplot should reference at least one main character).
- In the "characters" JSON array, each character appears ONCE. Never duplicate (LYRA DAVIS + LYRA DAVIS = error; LYRA + LYRA DAVIS = same person, use full name once).

CHARACTER OUTLINES (MANDATORY — for main characters only):
- For EACH main character, you must provide:
  1. "outline": a DETAILED paragraph (6-10 sentences) covering backstory, motivation, flaws, relationships, and role. Be substantial — avoid brief or shallow descriptions. DO NOT include physical appearance (height, hair, eyes, age, etc.) — that belongs ONLY in physical_appearance.
  2. "growth_arc": a DETAILED paragraph (6-10 sentences) describing their journey from starting state to end state — key challenges, how they change, and transformation. Be substantial — avoid brief or shallow descriptions.
  3. "physical_appearance": 2-4 sentences describing ONLY physical traits (see PHYSICAL APPEARANCE RULES below).
- One outline per main character, one growth arc per main character. No shared or merged outlines.

PHYSICAL APPEARANCE (PERSISTENT) — MANDATORY for each character:
- "physical_appearance" MUST include: gender, height, age or age range (extract from outline/storyline if mentioned — e.g. "22 years old", "in his early thirties"), face structure, hair color/style, eye color, skin tone, body build/silhouette, permanent features (scars, tattoos, glasses if permanent).
- MUST NOT include: the character's name (omit it — the name is stored separately), clothing, accessories (hat, cap, earbuds, jewelry), armor, uniforms, scene-specific condition (dirty, wet, damaged).
- These traits are GLOBAL and immutable across the story. Clothing belongs in scene wardrobe.
- Use ENTITY MARKUP in outline and growth_arc: Characters = FULL CAPS. Locations = _underlined_ (including vehicle interiors like _Common Area_, _Bridge_ — "the ship's X" = location). Objects = [brackets]. Vehicles = {{braces}} (exterior only).
- If a character OWNS a place, vehicle, or object, state it explicitly (e.g. "MAYA owns the {{motorcycle}}", "ELIAS owns _The Warehouse_"). OWNERSHIP is strictly enforced throughout the story.

MAIN CHARACTERS CANNOT BE REPLACED:
- The main characters in the "characters" array are the ONLY ones with outline and growth arc. They MUST appear in the story and in Character Details.
- Do NOT replace or overshadow main characters with newly introduced characters. Main characters drive the story.

MINOR CHARACTERS (allowed in storyline and subplots):
- You MAY introduce minor characters in main_storyline and subplots by name and what they do (e.g. "the bartender JACK", "the detective MORALES").
- Minor characters do NOT get outline or growth arc. They appear only in the narrative text.
- Minor characters support the story but must NOT replace the main characters as the focus.
- The "characters" JSON array contains ONLY the main characters. Do NOT add minor characters to the characters array.

AI / SYNTHETIC ENTITIES (e.g. AEON, computer systems):
- If the story includes an AI, computer, or synthetic entity, ALWAYS refer to it as "the AI AEON" or "AI AEON" — never as a standalone name in FULL CAPS like "AEON".
- Writing "the AI AEON" or "AI AEON" ensures it is NOT extracted as a human character. AI entities are systems, not main characters.
- Do NOT put AI/system names in the characters array. They may appear in the storyline text when prefixed with "AI" or "the AI".

MANDATORY: MAIN CHARACTERS MUST BE NAMED IN THE MAIN STORYLINE:
- The main characters in the characters array MUST each be explicitly NAMED in the expanded main_storyline.
- Every main character must appear by name in the main_storyline text. Do NOT omit any.
- The main_storyline must mention all main characters by their exact names. No exceptions.

CORPORATION / ORGANIZATION VS CHARACTER (MANDATORY):
- If the antagonist is a corporation, franchise, or brand, the character must be the PERSON (e.g. LUCILLE MAYFIELD, the CEO). Use the human's actual name.
- NEVER put a corporation, company, franchise, brand, organization, group, team, or agency name in the characters array. Use the human's actual name.
- NEVER write organizations, groups, teams, companies, brands, or agencies in FULL CAPS in the storyline. Write them in Title Case only (e.g. "the Ghost Guys Paranormal Investigators", "Neurotech Industries", "Big Bite Franchise"). FULL CAPS is exclusively for individual character names (human or non-human).
- When one person is referred to by title (e.g. "Dr. Mayfield"), use their full name (e.g. LUCILLE MAYFIELD) and do NOT add a separate entry for the surname alone.

CRITICAL — DO NOT INVENT CHARACTERS:
- When extracting or listing characters, ONLY include characters that EXPLICITLY appear in the main_storyline and subplots.
- NEVER add a character to the characters array who is not named in the story content.
- NEVER make up or invent character names. Every character in the array MUST appear by name in the main_storyline.

CHARACTER NAME UNIQUENESS (MANDATORY):
- Every character MUST have a completely unique name that does NOT share any part (first name, last name, title, or nickname) with any other character.
- NEVER give two characters the same first name, last name, or title even if the full names differ (e.g. QUEEN SERAPHINA and SERAPHINA LIGHTBRINGER is FORBIDDEN because they share "SERAPHINA").
- NEVER create names that sound similar or could be confused (e.g. MARCUS / MARCIUS, ELENA / ELANA, THERON / THERON'S).
- If the premise or concept mentions similar names, change one to be completely distinct before writing the storyline.
- This rule applies to ALL characters — main, minor, and any characters mentioned in the storyline, subplots, or conclusion.
"""
                if is_micro_narrative:
                    char_json_block = f''',
    "characters": [{{"name": "FULL CAPS NAME 1", "role": "main", "species": "Human or species/form (e.g. Demon, Dragon, Elf, Vampire, Robot, Ghost, Alien, Animal — use the EXACT species/form; default Human for ordinary people)", "physical_appearance": "Gender and height (MANDATORY), age when known (MANDATORY), face structure, hair color/style, eye color, skin tone, body build, permanent features. Do NOT include the character name. NO clothing, accessories, armor, uniforms. For non-human species describe species-appropriate anatomy (horns, scales, wings, fur, etc.)."}}, ... up to {n_characters} objects]'''
                else:
                    char_json_block = f''',
    "characters": [{{"name": "FULL CAPS NAME 1", "role": "main", "species": "Human or species/form (e.g. Demon, Dragon, Elf, Vampire, Robot, Ghost, Alien, Animal — use the EXACT species/form; default Human for ordinary people)", "outline": "A detailed 6-10 sentence paragraph: backstory, motivation, flaws, relationships, role. NO physical appearance (height, hair, eyes, age, etc.) — that goes in physical_appearance only. Use ENTITY MARKUP (Characters FULL CAPS, locations _underlined_, objects [brackets], vehicles {{braces}}). If character owns a place/vehicle/object, state it (e.g. owns _The Warehouse_). Be specific and substantial.", "growth_arc": "A detailed 6-10 sentence paragraph: starting state, key challenges faced, how they respond and change, ending state. Use ENTITY MARKUP. Be specific and substantial.", "physical_appearance": "Gender and height (MANDATORY), age when known (MANDATORY), face structure, hair color/style, eye color, skin tone, body build, permanent features. Do NOT include the character name. NO clothing, accessories (hat, cap, earbuds), armor, uniforms. For non-human species describe species-appropriate anatomy (horns, scales, wings, fur, etc.)."}}, ... up to {n_characters} objects]'''
            
            # Build subplots section (skipped for micro narratives)
            if is_micro_narrative:
                subplots_section = ""
                subplots_json = ""
            else:
                subplots_section = f"""
2. SUBPLOTS AND SECONDARY STORYLINES:
   - Identify 2-4 DISTINCT subplots that complement the main story
   - MANDATORY: Each subplot must mention at least one of the {n_characters if n_characters else 'main'} main characters by name. All main characters should appear across main_storyline + subplots.
   - These are SECONDARY storylines, completely separate from the main storyline
   - Main characters should drive or appear in subplots where relevant. Minor characters (by name and role) may also appear
   - Describe how each subplot relates to the main narrative
   - Explain how subplots will be resolved or integrated
   - Each subplot should be 2-3 sentences with specific details
   - DO NOT repeat the main storyline here - these are additional storylines
   - CRITICAL: You MUST provide subplots - this field cannot be empty
"""
                subplots_json = """
    "subplots": "Detailed description of 2-4 SUBPLOTS and secondary storylines that are SEPARATE from the main storyline. Each subplot should be 2-3 sentences. Explain how they relate to the main narrative and how they will be resolved. Format as a SINGLE STRING, not an array. DO NOT repeat the main storyline here.","""
            
            conclusion_number = "2" if is_micro_narrative else "3"
            
            prompt = f"""
You are a professional screenwriter and story structure expert. Expand the following story premise into a comprehensive story outline:

{title_text}Premise: {premise}
Genres: {genre_text}
Atmosphere/Tone: {atmosphere}
{char_count_block}

Create a detailed story outline that includes:

1. MAIN STORYLINE:
   - EXPAND the premise into a detailed main story arc - DO NOT just repeat the premise
   - MANDATORY: Introduce and mention the main characters (from the characters array) FIRST, before any minor characters
   - Describe the primary narrative journey from beginning to end with specific plot progression
   - Include key plot points, conflicts, and story beats
   - Should be 5-8 sentences describing the core story progression in detail
   - This is the PRIMARY story, not a subplot
   - CRITICAL: This must be a SUBSTANTIAL expansion of the premise, not a brief summary
{subplots_section}
{conclusion_number}. FINAL CONCLUSION:
   - Describe how the main story resolves in detail
   - Explain how key conflicts are resolved
   - Describe the final state of the world/characters
   - Include any themes or messages that are conveyed
   - Should be 4-6 sentences with specific details
   - CRITICAL: You MUST provide a conclusion - this field cannot be empty

CRITICAL: You MUST return ONLY valid JSON. No markdown, no explanations, no code blocks.

Format your response as a JSON object with this EXACT structure:
{{
    "main_storyline": "Detailed expansion of the premise into the main story arc. Describe the primary narrative journey from beginning to end, including key plot points, conflicts, and story beats (5-8 sentences). This is the PRIMARY story.",{subplots_json}
    "conclusion": "Final conclusion describing story resolution, conflict resolution, final state, and themes (4-6 sentences)."{char_json_block}
}}

ENTITY MARKUP RULES (MANDATORY):
- HUMAN CHARACTERS: Write in FULL CAPITAL LETTERS. Example: MAYA RIVERA, ELIAS CROSS. Use First 'Nickname' Last sparingly (e.g. HENRY 'HANK' THOMPSON).
- LOCATIONS / ENVIRONMENTS: Write in Title Case and UNDERLINE them. Example: _Midnight Falls_, _City Hall_, _Abandoned Chapel_. Interior spaces within vehicles (e.g. "the ship's Common Area", "Bridge", "Cockpit") are locations — use _underscores_, NOT {{braces}}. Example: "The crew gathers in the ship's _Common Area_." Only the vehicle itself uses {{braces}}.
- ORGANIZATIONS, GROUPS, TEAMS, AGENCIES, COMPANIES, BRANDS: Write in Title Case (e.g. Ghost Guys Paranormal Investigators, Neurotech Industries, The Silver Foxes). NEVER in FULL CAPS — FULL CAPS is strictly reserved for individual character names only (human or non-human).
- EMPHASIS, CODENAMES, PROTOCOLS, OPERATIONS, PROGRAMS, LABELS, WARNINGS, SIGNS, DOCUMENT TITLES: Write in Title Case or normal case. NEVER use FULL CAPS for emphasis or to highlight non-character phrases (e.g. write "Terminal Sanction" not "TERMINAL SANCTION"; "Project Genesis" not "PROJECT GENESIS").
- No other entities may use character markup (FULL CAPS) or location markup (_underlines_). Objects, vehicles, and organizations use plain Title Case.

LOCATION MARKING SCOPE: Towns, cities, buildings, rooms, interior spaces (including vehicle interiors like Common Area, Bridge, Cockpit), and distinct environments where scenes occur. Underline every location on every mention.

NARRATIVE GENERATION CONSTRAINT:
- All locations MUST be underlined on every mention (e.g. _Midnight Falls_, _City Hall_).
- Characters must NEVER be underlined. Use FULL CAPS for individual character names only (human or non-human).
- Locations must NEVER be in FULL CAPS. Use Title Case + underlining only.
- Organizations, groups, teams, companies, and brands must NEVER be in FULL CAPS. Use Title Case only (e.g. "the Ghost Guys Paranormal Investigators", "Neurotech Industries").
- Example correct: MAYA RIVERA walks through _Midnight Falls_. She hires the Ghost Guys Paranormal Investigators.
- Example incorrect: GHOST GUYS PARANORMAL INVESTIGATORS (organization must not be in full caps). Or MIDNIGHT FALLS (locations must not be full caps).

CRITICAL REQUIREMENTS FOR ALL FIELDS:
- "main_storyline": MUST be 5-8 sentences expanding the premise into a detailed story arc. DO NOT just repeat the premise - EXPAND it with plot points, conflicts, and story beats.
- "subplots": MUST contain 2-4 distinct subplots, each 2-3 sentences. This field MUST NOT be empty. Write all subplots as a single continuous text string (not an array).
- "conclusion": MUST be 4-6 sentences describing how the story resolves. This field MUST NOT be empty.

CRITICAL: The "subplots" field MUST be a STRING, not an array. Write all subplots as a single continuous text string.

IMPORTANT JSON RULES:
- Every property must be followed by a comma EXCEPT the last property in an object
- All string values must be properly quoted and escaped
- No trailing commas before closing braces or brackets
- Ensure proper nesting of all brackets and braces
- All text fields should be comprehensive and detailed
- DO NOT leave any field empty - all fields (main_storyline, subplots, conclusion) MUST have substantial content
"""
        
        try:
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You are a professional screenwriter and story structure expert. All fields (main_storyline, subplots, conclusion) must be fully populated. CHARACTER OUTLINES AND GROWTH ARCS: Each must be 6-10 sentences — substantial and detailed. Avoid brief or shallow descriptions. ENTITY MARKUP: Individual characters (human or non-human) = FULL CAPS only (e.g. MAYA RIVERA, SHADOWFANG). Locations = Title Case + UNDERLINED (e.g. _Midnight Falls_, _City Hall_, _Common Area_). Vehicle interiors (the ship's Common Area, Bridge, Cockpit) are locations — use _underscores_, NOT curly braces. Only the vehicle itself uses curly braces. All locations must be underlined on every mention; characters never underlined. Locations never in full caps. ORGANIZATIONS/GROUPS/TEAMS/COMPANIES/BRANDS: NEVER in FULL CAPS — always Title Case (e.g. Ghost Guys Paranormal Investigators, Neurotech Industries). FULL CAPS is strictly reserved for individual character names. AI/SYNTHETIC ENTITIES: When the story includes an AI or computer system (e.g. AEON), always write 'the AI AEON' or 'AI AEON' — never just 'AEON' in full caps. AI entities are not human characters. MAIN CHARACTERS: The main characters in the characters array MUST each be explicitly named in the main_storyline. All must appear by name. CRITICAL: Do NOT invent characters — every character in the array MUST appear by name in the main_storyline. Never add made-up characters. NON-HUMAN CHARACTERS: Characters can be any species (dragons, elves, robots, animals, etc.). They still use FULL CAPS for their names and follow the same markup rules as human characters. NAME UNIQUENESS: Every character must have a completely unique name. No two characters may share any part of their name (first name, last name, title, or nickname). For example, QUEEN SERAPHINA and SERAPHINA LIGHTBRINGER is forbidden because both share SERAPHINA."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=max(self.model_settings["max_tokens"], 8000)  # Allow for detailed outline + long character outlines/growth arcs (6-10 sentences each)
            )
            
            content = response.choices[0].message.content
            
            # Validate content
            if content is None:
                raise Exception("AI returned None response. Please check your AI settings and try again.")
            
            if not isinstance(content, str):
                content = str(content)
            
            if not content.strip():
                raise Exception("AI returned an empty response. Please check your AI settings and try again.")
            
            # Extract and parse JSON
            try:
                outline_data = self._extract_and_parse_json(content)
            except Exception as e:
                # Save the raw response for debugging
                import os
                debug_file = "debug_outline_response.txt"
                try:
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        f.write(f"Response length: {len(content)}\n")
                        f.write(f"Response preview (first 500 chars):\n{content[:500]}\n\n")
                        f.write(f"Full response:\n{content}\n")
                except:
                    pass
                # Re-raise with more context
                error_msg = str(e)
                if os.path.exists(debug_file):
                    error_msg += f"\n\nFull AI response saved to: {debug_file}"
                raise Exception(error_msg)
            
            # Validate and normalize structure
            if "main_storyline" not in outline_data:
                outline_data["main_storyline"] = ""
            else:
                # Ensure main_storyline is a string
                if not isinstance(outline_data["main_storyline"], str):
                    outline_data["main_storyline"] = str(outline_data["main_storyline"]) if outline_data["main_storyline"] else ""
                # Check if main_storyline is too short (just repeating premise)
                main_storyline_text = outline_data["main_storyline"].strip()
                if len(main_storyline_text) < 100 or main_storyline_text.lower() == premise.lower()[:len(main_storyline_text)]:
                    # Main storyline is too short or just repeats premise - expand it
                    # Use the premise as base but expand it significantly
                    expanded = f"{premise} The story unfolds as the characters face escalating challenges and conflicts. Key plot points include the inciting incident that sets everything in motion, the rising action where tensions build, major turning points that change the course of events, and the climax where the central conflict reaches its peak. Throughout the narrative, characters must overcome obstacles, make difficult choices, and grow as individuals. The story explores themes of {', '.join(genres) if genres else 'human nature'} within a {atmosphere} atmosphere, ultimately leading to a resolution that addresses the core conflicts established in the premise."
                    outline_data["main_storyline"] = expanded
            
            if "subplots" not in outline_data:
                outline_data["subplots"] = ""
            else:
                # Handle both string and array formats for subplots
                subplots = outline_data["subplots"]
                if isinstance(subplots, list):
                    # Convert array of objects to string format
                    subplot_strings = []
                    for subplot in subplots:
                        if isinstance(subplot, dict):
                            title = subplot.get("title", "")
                            desc = subplot.get("description", "")
                            if title and desc:
                                subplot_strings.append(f"{title}: {desc}")
                            elif desc:
                                subplot_strings.append(desc)
                        elif isinstance(subplot, str):
                            subplot_strings.append(subplot)
                    # Join with double newlines for better readability
                    outline_data["subplots"] = "\n\n".join(subplot_strings) if subplot_strings else ""
                elif not isinstance(subplots, str):
                    outline_data["subplots"] = str(subplots) if subplots else ""
            
            # Character list: when character_count was requested, use extraction as source of truth
            # Extraction from main_storyline (and subplots if needed) ensures protagonist is included
            if n_characters is not None and n_characters > 0:
                raw_chars = outline_data.get("characters")
                if not isinstance(raw_chars, list):
                    raw_chars = []
                # Post-processing: use extraction as source of truth, merge outlines from AI where names match
                main_storyline_text = (outline_data.get("main_storyline") or "").strip()
                subplots_text = (outline_data.get("subplots") or "").strip()
                extracted_names = []
                if main_storyline_text:
                    extracted_names = self._extract_first_n_characters_from_main_storyline(
                        main_storyline_text, n_characters
                    )
                # If main_storyline yielded fewer than needed, supplement from subplots (preserve main order first)
                if len(extracted_names) < n_characters and subplots_text:
                    combined = f"{main_storyline_text}\n\n{subplots_text}"
                    supplemental = self._extract_first_n_characters_from_main_storyline(
                        combined, n_characters
                    )
                    seen = {n.lower() for n in extracted_names}
                    for name in supplemental:
                        if name and name.lower() not in seen:
                            extracted_names.append(name)
                            seen.add(name.lower())
                        if len(extracted_names) >= n_characters:
                            break
                extracted_names = extracted_names[:n_characters]
                # Build declared_map from AI's raw_chars for merging outlines
                declared_map = {}
                for c in raw_chars:
                    if isinstance(c, dict) and c.get("name"):
                        nm = str(c["name"]).strip()
                        declared_map[nm.lower()] = c
                # If extraction succeeded, use it as source of truth; merge outlines from AI
                if extracted_names:
                    merged_chars = []
                    for name in extracted_names:
                        norm = str(name).strip()
                        match = declared_map.get(norm.lower()) if norm else None
                        phys = (match.get("physical_appearance", "") or "").strip() if match else ""
                        if phys:
                            phys = self._strip_character_name_from_physical_appearance(phys, norm)
                        merged_chars.append({
                            "name": norm,
                            "outline": (match.get("outline", "") or "") if match else "",
                            "growth_arc": (match.get("growth_arc", "") or "") if match else "",
                            "physical_appearance": phys,
                            "species": (match.get("species", "Human") or "Human") if match else "Human"
                        })
                    raw_chars = merged_chars
                # Normalize to list of dicts with at least "name"; deduplicate by name (keep first occurrence)
                chars = []
                seen_names = set()
                for c in raw_chars:
                    if isinstance(c, dict) and c.get("name"):
                        name = str(c["name"]).strip()
                        key = name.lower()
                        if key in seen_names:
                            continue  # Skip duplicate character (e.g. LUCIEN appearing twice)
                        seen_names.add(key)
                        phys = str(c.get("physical_appearance", "") or "").strip()
                        phys = self._strip_character_name_from_physical_appearance(phys, name)
                        raw_species = str(c.get("species", "Human") or "Human").strip()
                        chars.append({
                            "name": name,
                            "outline": c.get("outline", ""),
                            "growth_arc": c.get("growth_arc", ""),
                            "physical_appearance": phys,
                            "species": raw_species
                        })
                    elif isinstance(c, str) and c.strip():
                        name = c.strip()
                        key = name.lower()
                        if key not in seen_names:
                            seen_names.add(key)
                            chars.append({"name": name, "outline": "", "growth_arc": "", "physical_appearance": "", "species": "Human"})
                # Final deduplication to catch any remaining duplicates (e.g. LYRA DAVIS twice)
                chars = self.sanitize_character_list_for_registry(chars)
                # Trim to maximum (n_characters is an upper bound, not an exact count)
                outline_data["characters"] = chars[:n_characters]
                final_count = len(outline_data["characters"])
                import logging
                logging.getLogger(__name__).info(
                    "Wizard character validation: generated %s main characters (max was %s).",
                    final_count, n_characters
                )
                # Tag all wizard-generated characters as main and normalize species
                main_storyline_text_for_species = str(outline_data.get("main_storyline", "") or "")
                for c in outline_data["characters"]:
                    if isinstance(c, dict) and "role" not in c:
                        c["role"] = "main"
                    if isinstance(c, dict):
                        raw_sp = str(c.get("species", "Human") or "Human").strip()
                        normalized = normalize_species_label(raw_sp)
                        if normalized == "Human" or not normalized:
                            char_name = str(c.get("name", "")).strip()
                            char_context = ""
                            for seg in main_storyline_text_for_species.split(". "):
                                if char_name.upper() in seg.upper():
                                    char_context += seg + ". "
                            inferred = infer_species_from_text(
                                str(c.get("outline", "") or ""),
                                str(c.get("physical_appearance", "") or ""),
                                char_context,
                                char_name
                            )
                            c["species"] = inferred
                        else:
                            c["species"] = normalized
            else:
                outline_data["characters"] = []
            if "conclusion" not in outline_data:
                outline_data["conclusion"] = ""
            else:
                # Ensure conclusion is a string and not empty
                if not isinstance(outline_data["conclusion"], str):
                    outline_data["conclusion"] = str(outline_data["conclusion"]) if outline_data["conclusion"] else ""
                # If conclusion is empty or too short, it needs to be generated
                if not outline_data["conclusion"].strip() or len(outline_data["conclusion"].strip()) < 50:
                    # Conclusion is missing or too short - generate it
                    try:
                        conclusion = self.regenerate_conclusion(
                            premise, genres, atmosphere, title,
                            outline_data.get("main_storyline", ""),
                            outline_data.get("subplots", ""),
                            outline_data.get("characters", [])
                        )
                        outline_data["conclusion"] = conclusion
                    except Exception as e:
                        # If regeneration fails, at least ensure it's not empty
                        outline_data["conclusion"] = "The story concludes with the resolution of key conflicts and character arcs."
            
            # Validate that subplots are not empty (skip for micro narratives — no subplots)
            if is_micro_narrative:
                outline_data["subplots"] = ""
            elif not outline_data.get("subplots", "").strip() or len(outline_data.get("subplots", "").strip()) < 50:
                # Subplots are missing or too short - try to generate them
                try:
                    subplots = self.regenerate_subplots(
                        premise, genres, atmosphere, title,
                        outline_data.get("main_storyline", ""),
                        outline_data.get("characters", [])
                    )
                    outline_data["subplots"] = subplots
                except Exception as e:
                    # If regeneration fails, at least ensure it's not empty
                    outline_data["subplots"] = "Additional subplots will be developed to complement the main storyline."
            
            # Characters will be generated later by the UI after conclusion is finalized
            # This ensures characters have complete story context for better profiles
            
            # Location registry (optional): compile unique underlined locations for downstream use
            combined_narrative = "\n\n".join([
                str(outline_data.get("main_storyline", "")),
                str(outline_data.get("subplots", "")),
                str(outline_data.get("conclusion", "")),
            ])
            outline_data["locations"] = self._extract_locations_from_text(combined_narrative, max_locations=50)
            
            # Validation pass (required): no FULL CAPS underlined, no underlined FULL CAPS
            passed, issues = self._validate_entity_markup(combined_narrative)
            if not passed and issues:
                import logging
                logging.getLogger(__name__).warning(
                    "Wizard entity markup validation failed: %s", "; ".join(issues)
                )
            
            return outline_data
                
        except Exception as e:
            error_message = str(e)
            raise Exception(f"Failed to generate story outline: {error_message}")
    
    def _extract_character_names_from_text(self, text: str, max_names: Optional[int] = 10) -> List[str]:
        """Extract character names from Wizard narrative text.
        
        FULL CAPS are reserved exclusively for individual characters (human or non-human). ONLY extract entities that:
        - Appear in FULL CAPITAL LETTERS in the text, AND
        - Are explicitly individual characters (not locations, organizations, or concepts).
        If an ALL-CAPS phrase is preceded by a location indicator (e.g. "town of", "city of",
        "village of", "located in", "inside the"), it is classified as environment and NOT extracted.
        Locations, towns, buildings, environments must never be in full caps in narrative;
        only human character names use FULL CAPS.
        
        Args:
            text: Text to extract character names from (main storyline, subplots, conclusion)
            max_names: Maximum names to return (None = no limit). Default 10.
            
        Returns:
            List of character names found (as written in full caps in the text)
        """
        if not text or not text.strip():
            return []
        
        # ONLY extract phrases that appear in FULL CAPITAL LETTERS (Wizard: character candidates only).
        # UNDERLINED text (_..._) = location candidates only; MUST NOT be treated as character.
        # Build spans of underlined regions: any ALL-CAPS inside _..._ is a location, not a character.
        underlined_spans = []
        for um in re.finditer(r'_[^_]+_', text):
            underlined_spans.append((um.start(), um.end()))
        def inside_underlined(pos: int) -> bool:
            return any(s <= pos < e for s, e in underlined_spans)
        location_indicators = (
            "town of", "city of", "village of", "located in", "inside the",
            "the town of", "the city of", "the village of",
        )
        potential_names = set()
        _hon = r"(?:(?:MRS?|MS|DR|MME|PROF|SGT|CPT|LT|GEN|COL|REV|CMDR|CAPT)\.\s+)?"
        _nw = r"[A-Z][A-Z0-9]*(?:'[A-Z][A-Z0-9]*)?"
        all_caps_pattern = re.compile(
            rf"\b({_hon}{_nw}(?:[ \t]+(?:{_nw}|\"[^\"]*\"|'[^']*'))*)\b"
        )
        for match in all_caps_pattern.finditer(text):
            phrase = match.group(1).strip()
            if len(phrase) < 2:
                continue
            # If this ALL-CAPS phrase is inside underlined region → location, not character
            if inside_underlined(match.start()):
                continue
            # If this ALL-CAPS phrase is preceded by a location indicator → environment, not character
            start = match.start()
            preceding = text[max(0, start - 80):start].lower().rstrip()
            if any(preceding.endswith(ind) for ind in location_indicators):
                continue
            # If preceded by "the AI " or "AI " → AI/synthetic entity, not a human character
            if preceding.endswith("the ai ") or preceding.endswith("ai "):
                continue
            # If preceded by "corporation", "company", "franchise", "brand", etc. → org name, not a character
            org_indicators = (
                "corporation ", "company ", "the corporation ", "the company ",
                "franchise ", "the franchise ", "brand ", "the brand ",
                "chain ", "the chain ", "restaurant ", "the restaurant ",
            )
            if any(preceding.endswith(ind) for ind in org_indicators):
                continue
            # If followed by ", led by" or ", a franchise" etc. → org name (e.g. "BIG BITE, led by CEO X")
            following = text[match.end():min(match.end() + 60, len(text))].lower()
            org_following = (", led by", ", led by the", ", a franchise", ", a corporate", ", the franchise")
            if any(following.startswith(s) for s in org_following):
                continue
            words = re.split(r'\s+', phrase)
            words_clean = [w.strip('"') for w in words if w and (not w.startswith('"') or w.endswith('"'))]
            if not words_clean:
                continue
            if all(len(w) >= 2 and w.isalpha() for w in words_clean if w.isalpha()):
                potential_names.add(phrase)
        
        # Blocklist: narrative transitions, acronyms, and non-character ALL-CAPS (never treat as characters)
        non_character_all_caps = {
            "MEANWHILE", "SUDDENLY", "FINALLY", "THEN", "NOW", "AFTERWARD", "AFTERWARDS",
            "BEFORE", "AFTER", "FIRST", "LAST", "THE END", "CUT TO", "FADE IN", "FADE OUT",
            "INT", "EXT", "DISSOLVE", "CITY HALL", "METRO STATION", "CENTRAL HUB",
            "THE GUARDIANS", "THE TEAM", "THE CREW", "THE SQUAD", "THE FORCE",
            "TV", "DVD", "CD", "PC", "FBI", "CIA", "NASA", "USA", "UK", "GPS", "CEO",
            "MVP", "API", "UFO", "HIV", "ATM", "DNA", "RNA", "HQ", "VIP", "DIY", "FAQ",
            "PR", "HR", "VP", "PM", "AM", "FM", "DC", "AC", "AD", "BC",
        }
        # AI/synthetic entity names (systems, not human characters) — do not extract as characters
        ai_entity_names = {"AEON", "NEXUS", "ORACLE", "SYNAPSE", "CORTEX", "PRIME", "OMNI"}
        filtered_names = []
        for name in potential_names:
            name_upper = name.upper()
            if name_upper in non_character_all_caps:
                continue
            if name_upper in ai_entity_names:
                continue
            # Drop locations, events, companies, roles (use existing heuristics; pass title-case for consistency)
            name_for_check = name.title() if name.isupper() else name
            if self._is_place_or_region_entity(name_for_check) or self._is_event_entity(name_for_check):
                continue
            if self._is_company_or_concept_entity(name_for_check) or self._is_role_or_title_only(name_for_check):
                continue
            if self._is_group_or_team(name_for_check) or self._is_building_or_location(name_for_check):
                continue
            if self._is_narrative_transition(name_for_check):
                continue
            filtered_names.append(name)
        
        # Deduplicate: exact match, first name, and nickname (REBECCA 'REX' STERN + REX = same character)
        unique = self.normalize_and_dedupe_character_names(filtered_names)
        limit = max_names if max_names is not None else len(unique)
        return unique[:limit]
    
    def _extract_first_n_characters_from_main_storyline(self, main_storyline: str, n: int) -> List[str]:
        """Extract the first N character names from main storyline in order of first mention.
        
        Main characters MUST be the first N characters mentioned in the main storyline.
        No other characters (from subplots, conclusion, etc.) get character outlines.
        Uses same filtering as _extract_character_names_from_text but preserves order of first appearance.
        """
        if not main_storyline or not main_storyline.strip() or n <= 0:
            return []
        # Build protected spans: underlined, bracketed, and braced markup regions
        markup_spans = []
        for um in re.finditer(r'_[^_]+_', main_storyline):
            markup_spans.append((um.start(), um.end()))
        for bm in re.finditer(r'\[[^\]]+\]', main_storyline):
            markup_spans.append((bm.start(), bm.end()))
        for cm in re.finditer(r'\{[^}]+\}', main_storyline):
            markup_spans.append((cm.start(), cm.end()))
        for am in re.finditer(r'\*[^*]+\*', main_storyline):
            markup_spans.append((am.start(), am.end()))
        def inside_markup(pos: int) -> bool:
            return any(s <= pos < e for s, e in markup_spans)
        location_indicators = (
            "town of", "city of", "village of", "located in", "inside the",
            "the town of", "the city of", "the village of",
        )
        non_character_all_caps = {
            "MEANWHILE", "SUDDENLY", "FINALLY", "THEN", "NOW", "AFTERWARD", "AFTERWARDS",
            "BEFORE", "AFTER", "FIRST", "LAST", "THE END", "CUT TO", "FADE IN", "FADE OUT",
            "INT", "EXT", "DISSOLVE", "CITY HALL", "METRO STATION", "CENTRAL HUB",
            "THE GUARDIANS", "THE TEAM", "THE CREW", "THE SQUAD", "THE FORCE",
            "DR", "MR", "MRS", "MS", "SIR", "LORD", "LADY", "CAPTAIN", "JUDGE", "GENERAL",
            "COLONEL", "MAJOR", "LIEUTENANT", "ADMIRAL", "PROFESSOR", "DOCTOR",
            "TV", "DVD", "CD", "PC", "FBI", "CIA", "NASA", "USA", "UK", "GPS", "CEO",
            "MVP", "API", "UFO", "HIV", "ATM", "DNA", "RNA", "HQ", "VIP", "DIY", "FAQ",
            "PR", "HR", "VP", "PM", "AM", "FM", "DC", "AC", "AD", "BC",
            "AI", "AR", "VR", "EMF", "LED", "LCD", "USB", "PDF", "URL", "ID", "OK",
            "SFX", "FX", "CGI", "HD", "UHD",
        }
        ai_entity_names = {"AEON", "NEXUS", "ORACLE", "SYNAPSE", "CORTEX", "PRIME", "OMNI"}
        _hon = r"(?:(?:MRS?|MS|DR|MME|PROF|SGT|CPT|LT|GEN|COL|REV|CMDR|CAPT)\.\s+)?"
        _nw = r"[A-Z][A-Z0-9]*(?:'[A-Z][A-Z0-9]*)?"
        all_caps_pattern = re.compile(
            rf"\b({_hon}{_nw}(?:[ \t]+(?:{_nw}|\"[^\"]*\"|'[^']*'))*)\b"
        )
        seen_lower = set()
        unique_ordered = []
        for match in all_caps_pattern.finditer(main_storyline):
            phrase = match.group(1).strip()
            if len(phrase) < 2:
                continue
            if inside_markup(match.start()):
                continue
            start = match.start()
            preceding = main_storyline[max(0, start - 80):start].lower().rstrip()
            if any(preceding.endswith(ind) for ind in location_indicators):
                continue
            words = re.split(r'\s+', phrase)
            words_clean = [w.strip('"') for w in words if w and (not w.startswith('"') or w.endswith('"'))]
            if not words_clean or not all(len(w) >= 2 and w.isalpha() for w in words_clean if w.isalpha()):
                continue
            if phrase.upper() in non_character_all_caps:
                continue
            if phrase.upper() in ai_entity_names:
                continue
            # If preceded by "the AI " or "AI " → AI/synthetic entity, not a human character
            start = match.start()
            preceding = main_storyline[max(0, start - 80):start].lower().rstrip()
            if preceding.endswith("the ai ") or preceding.endswith("ai "):
                continue
            # If preceded by "corporation", "company", "franchise", "brand", etc. → org name, not a character
            org_indicators = (
                "corporation ", "company ", "the corporation ", "the company ",
                "franchise ", "the franchise ", "brand ", "the brand ",
                "chain ", "the chain ", "restaurant ", "the restaurant ",
            )
            if any(preceding.endswith(ind) for ind in org_indicators):
                continue
            # If followed by ", led by" or ", a franchise" etc. → org name (e.g. "BIG BITE, led by CEO X")
            following = main_storyline[match.end():min(match.end() + 60, len(main_storyline))].lower()
            org_following = (", led by", ", led by the", ", a franchise", ", a corporate", ", the franchise")
            if any(following.startswith(s) for s in org_following):
                continue
            # If followed by "show", "series", "program", "network" → acronym (e.g. TV show), not a character
            following = main_storyline[match.end():min(match.end() + 30, len(main_storyline))].lower()
            if re.match(r'^\s*(show|series|program|network|station|movie|film)\b', following):
                if len(phrase) <= 4 and phrase.isupper():
                    continue
            name_for_check = phrase.title() if phrase.isupper() else phrase
            if self._is_place_or_region_entity(name_for_check) or self._is_event_entity(name_for_check):
                continue
            if self._is_company_or_concept_entity(name_for_check) or self._is_role_or_title_only(name_for_check):
                continue
            if self._is_group_or_team(name_for_check) or self._is_building_or_location(name_for_check):
                continue
            if self._is_narrative_transition(name_for_check):
                continue
            key = phrase.lower().strip()
            if key in ("narrator", "story", "character"):
                continue
            if key in seen_lower:
                continue

            # --- Partial-name deduplication (any word count) ---
            # Skip if this phrase is a subset of an already-extracted name
            # e.g. "SIR REGINALD" or "SIR REG" when we already have
            # "SIR REGINALD 'REG' BARTLETT"
            phrase_words_lower = {w.lower().strip("'\"") for w in words if len(w) >= 2}
            is_partial_of_existing = False
            for existing in unique_ordered:
                existing_words_lower = {
                    w.lower().strip("'\"") for w in existing.split() if len(w) >= 2
                }
                existing_nick = self._extract_nickname_from_full_name(existing)
                if existing_nick:
                    existing_words_lower.add(existing_nick.lower())
                if phrase_words_lower and phrase_words_lower <= existing_words_lower:
                    is_partial_of_existing = True
                    break
            if is_partial_of_existing:
                continue

            # Skip single-word forms: first name, last name, or nickname of an existing entry
            if len(words) == 1:
                is_nickname_dup = any(
                    self._extract_nickname_from_full_name(existing) and
                    self._extract_nickname_from_full_name(existing).lower() == key
                    for existing in unique_ordered
                )
                if is_nickname_dup:
                    continue
                is_lastname_dup = any(
                    (e.split()[-1] if " " in e else "").lower() == key
                    for e in unique_ordered
                )
                if is_lastname_dup:
                    continue
                is_nickname_for_first = any(
                    self._is_nickname_of_first_name(phrase, existing)
                    for existing in unique_ordered
                )
                if is_nickname_for_first:
                    continue

            # Replace existing if this is a longer form containing all words of a shorter entry
            existing_idx = None
            for i, existing in enumerate(unique_ordered):
                ex_words_lower = {
                    w.lower().strip("'\"") for w in existing.split() if len(w) >= 2
                }
                ex_nick = self._extract_nickname_from_full_name(existing)
                if ex_nick:
                    ex_words_lower.add(ex_nick.lower())
                if ex_words_lower and ex_words_lower < phrase_words_lower:
                    existing_idx = i
                    break
            if existing_idx is not None:
                old = unique_ordered[existing_idx]
                unique_ordered[existing_idx] = phrase
                seen_lower.discard(old.lower())
                seen_lower.add(key)
            elif key not in seen_lower:
                seen_lower.add(key)
                unique_ordered.append(phrase)
            if len(unique_ordered) >= n:
                break
        return unique_ordered[:n]
    
    def _extract_locations_from_text(self, text: str, max_locations: Optional[int] = 50) -> List[str]:
        """Extract location names from Wizard narrative text.
        
        UNDERLINED text (_..._) is reserved for locations only. Extract every phrase
        between underscores; do NOT treat FULL CAPS as locations.
        
        Args:
            text: Text to extract from (main storyline, subplots, conclusion)
            max_locations: Maximum locations to return (None = no limit). Default 50.
            
        Returns:
            List of unique location names (strip underscores, title-case preserved).
        """
        if not text or not text.strip():
            return []
        # Strip SFX tags before scanning — underscores inside e.g. (distant_rumble)
        # would otherwise be treated as location delimiters by the _.._ regex.
        cleaned_text = re.sub(r'\([a-z]+(?:_[a-z]+)*\)', '', text)
        # Location qualifier words that may appear immediately after the closing
        # underscore (e.g. "_Highspire Keep_ library" → "Highspire Keep library").
        _LOCATION_QUALIFIERS = frozenset({
            "library", "tower", "hall", "chamber", "room", "courtyard", "garden",
            "square", "plaza", "bridge", "gate", "gates", "entrance", "exit",
            "quarter", "district", "market", "bazaar", "cathedral", "chapel",
            "temple", "shrine", "tavern", "inn", "pub", "saloon", "bar",
            "palace", "castle", "fortress", "citadel", "keep", "dungeon",
            "cellar", "basement", "attic", "rooftop", "balcony", "terrace",
            "pier", "dock", "docks", "harbor", "harbour", "port", "wharf",
            "alley", "alleyway", "lane", "road", "path", "trail", "passage",
            "corridor", "tunnel", "cavern", "cave", "mine", "quarry",
            "arena", "colosseum", "amphitheater", "amphitheatre", "stadium",
            "academy", "school", "university", "archive", "archives",
            "vault", "treasury", "armory", "armoury", "forge", "workshop",
            "laboratory", "lab", "observatory", "sanctum", "sanctuary",
            "crypt", "tomb", "mausoleum", "graveyard", "cemetery",
            "outpost", "camp", "encampment", "barracks", "headquarters",
            "office", "study", "parlor", "parlour", "lounge", "kitchen",
            "bedroom", "ward", "wing", "annex", "ruins", "interior",
            "exterior", "grounds", "courtyard", "cloister", "promenade",
            "summit", "peak", "ridge", "cliff", "overlook", "lookout",
            "clearing", "grove", "glade", "meadow", "field", "valley",
            "gorge", "canyon", "ravine", "riverbank", "shore", "beach",
            "station", "depot", "terminal", "platform", "bay", "deck",
            "bridge", "cockpit", "hold", "cabin", "quarters",
        })

        seen = set()
        unique = []
        for m in re.finditer(r'_([^_]+)_', cleaned_text):
            name = m.group(1).strip()
            if not name or len(name) < 2:
                continue
            # Reject matches that span prose (sentence fragments, punctuation runs)
            if any(ch in name for ch in '()[]{}*"'):
                continue
            # Absorb trailing qualifier words that sit outside the underscores
            rest = cleaned_text[m.end():]
            trail_match = re.match(r'^(\s+[A-Za-z]+(?:\s+[A-Za-z]+)?)', rest)
            if trail_match:
                trailing = trail_match.group(1).strip().lower().split()
                absorbed = []
                for tw in trailing:
                    if tw in _LOCATION_QUALIFIERS:
                        absorbed.append(tw)
                    else:
                        break
                if absorbed:
                    name = name + " " + " ".join(absorbed).title()
            # Normalize for dedup: "The French Quarter" and "French Quarter" = same location
            key = re.sub(r'^the\s+', '', name.lower()).strip()
            if key not in seen:
                seen.add(key)
                unique.append(name)
            if max_locations is not None and len(unique) >= max_locations:
                break
        return unique[:max_locations] if max_locations else unique
    
    def _scene_markup_has_interaction(self, text: str, entity_name: str, entity_type: str) -> bool:
        """Check if entity appears near interaction verbs (use/pick up/activate/drive/enter/operate).
        Objects and vehicles must ONLY be marked if a character interacts with them.
        Checks ALL occurrences of the entity, not just the first."""
        if not text or not entity_name:
            return False
        text_lower = text.lower()
        name_lower = entity_name.lower()
        if entity_type == "object":
            interaction_verbs = (
                # Core manipulation
                "picks up", "pick up", "picked up", "uses", "use", "used", "activates", "activate",
                "activated", "grabs", "grab", "grabbed", "takes", "take", "took", "holds", "hold",
                "held", "manipulates", "manipulate", "presses", "press", "pressed", "touches",
                "touch", "touched", "reaches for", "reaches", "reached", "inserts", "insert",
                "swipes", "swipe", "swiped", "opens with", "unlocks with", "unlock with",
                # Physical contact / support (OBJECT INTERACTION EXPANSION)
                "sits on", "sit on", "sat on", "sits in", "sit in", "sat in", "sits", "sit", "sat",
                "perches on", "perch on", "perched on", "perches", "perch", "perched",
                "leans on", "lean on", "leaned on", "leans against", "lean against", "leaned against",
                "leans back in", "lean back in", "leaned back in", "leans", "lean", "leaned",
                "rests on", "rest on", "rested on", "rests feet on", "rest feet on", "rested feet on",
                "rests against", "rest against", "rested against", "rests", "rest", "rested",
                "propped on", "prop on", "propped up on", "props", "prop", "propped",
                "boots propped", "feet propped", "propped up",
                "places on", "place on", "placed on", "places", "place", "placed",
                "grips", "grip", "gripped",
                # Movement / direction verbs commonly used with objects
                "adjusts", "adjust", "adjusted", "adjusting",
                "taps", "tap", "tapped", "tapping",
                "points", "point", "pointed", "pointing",
                "waves", "wave", "waved", "waving",
                "aims", "aim", "aimed", "aiming",
                "pulls out", "pull out", "pulled out", "pulling out",
                "pushes", "push", "pushed", "pushing",
                "lifts", "lift", "lifted", "lifting",
                "lowers", "lower", "lowered", "lowering",
                "raises", "raise", "raised", "raising",
                "swings", "swing", "swung", "swinging",
                "tosses", "toss", "tossed", "tossing",
                "throws", "throw", "threw", "throwing",
                "catches", "catch", "caught", "catching",
                "flips", "flip", "flipped", "flipping",
                "flicks", "flick", "flicked", "flicking",
                "turns on", "turn on", "turned on",
                "turns off", "turn off", "turned off",
                "sets down", "set down", "puts down", "put down",
                "straps", "strap", "strapped", "strapping",
                "opens", "open", "opened", "opening",
                "closes", "close", "closed", "closing",
                "examines", "examine", "examined", "examining",
                "inspects", "inspect", "inspected", "inspecting",
                "reads", "read", "reading",
                "types", "type", "typed", "typing",
                "clicks", "click", "clicked", "clicking",
                "squeezes", "squeeze", "squeezed", "squeezing",
                "thrusts", "thrust", "thrusting",
                "fires", "fire", "fired", "firing",
                "draws", "draw", "drew", "drawing",
                "sheathes", "sheathe", "sheathed",
                "checks", "check", "checked", "checking",
                "fumbles", "fumble", "fumbled", "fumbling",
                "clutches", "clutch", "clutched", "clutching",
                "snatches", "snatch", "snatched", "snatching",
                "carries", "carry", "carried", "carrying",
                "drags", "drag", "dragged", "dragging",
                "drops", "drop", "dropped", "dropping",
                # Possessive interaction: "in her hands", "from his belt"
                "in her hands", "in his hands", "in their hands",
                "from her belt", "from his belt", "from his pocket", "from her pocket",
            )
        else:
            interaction_verbs = (
                "drives", "drive", "drove", "enters", "enter", "entered", "operates", "operate",
                "operated", "rides", "ride", "rode", "boards", "board", "boarded", "gets into",
                "get into", "got into", "climbs into", "climb into", "starts the", "start the",
                "revs", "rev", "parked", "park", "mounts", "mount", "mounted"
            )
        # Check ALL occurrences of the entity, not just the first
        pos = 0
        while True:
            pos = text_lower.find(name_lower, pos)
            if pos < 0:
                break
            start = max(0, pos - 200)
            end = min(len(text), pos + len(entity_name) + 200)
            window = text_lower[start:end]
            if any(v in window for v in interaction_verbs):
                return True
            pos += 1
        return False
    
    def _extract_objects_from_scene_markup(self, text: str, require_interaction: bool = True) -> List[str]:
        """Extract object names from [bracket] markup. Only return if interaction present when require_interaction=True."""
        if not text or not text.strip():
            return []
        seen = set()
        unique = []
        for m in re.finditer(r'\[([^\]]+)\]', text):
            name = m.group(1).strip()
            if not name or len(name) < 2:
                continue
            key = name.lower()
            if key in seen:
                continue
            if require_interaction and not self._scene_markup_has_interaction(text, name, "object"):
                continue
            seen.add(key)
            unique.append(name)
        return unique
    
    def _extract_vehicles_from_scene_markup(self, text: str, require_interaction: bool = True) -> List[str]:
        """Extract vehicle names from {brace} markup. Only return if interaction present when require_interaction=True."""
        if not text or not text.strip():
            return []
        seen = set()
        unique = []
        # Reject common words mistakenly in braces (e.g. {the})
        INVALID_ENTITY_WORDS = frozenset({"the", "a", "an", "this", "that", "it", "his", "her", "their"})
        for m in re.finditer(r'\{([^{}]+)\}', text):
            name = m.group(1).strip()
            if not name or len(name) < 2:
                continue
            key = name.lower()
            if key in INVALID_ENTITY_WORDS:
                continue
            if key in seen:
                continue
            if require_interaction and not self._scene_markup_has_interaction(text, name, "vehicle"):
                continue
            seen.add(key)
            unique.append(name)
        return unique
    
    def _parse_vehicle_interior_from_environment_name(self, environment_name: str) -> Optional[str]:
        """If environment name implies a vehicle interior (e.g. 'Starfall Cruiser – Bridge'), return the vehicle name.
        Vehicle interiors are ALWAYS ENVIRONMENTS with parent_vehicle set. Exterior is VEHICLE.
        Returns vehicle name to use as parent_vehicle, or None if not a vehicle interior.
        """
        if not environment_name or not isinstance(environment_name, str):
            return None
        name = environment_name.strip()
        if len(name) < 4:
            return None
        # Pattern: "Vehicle – Space" or "Vehicle - Space" (dash with spaces)
        for sep in (" – ", " - ", " — "):
            if sep in name:
                parts = name.split(sep, 1)
                if len(parts) == 2:
                    vehicle_part = parts[0].strip()
                    space_part = parts[1].strip().lower()
                    if vehicle_part and space_part:
                        # Interior keywords (common spaces inside vehicles)
                        interior_keywords = (
                            "bridge", "cockpit", "cabin", "cargo", "hold", "deck", "quarters",
                            "galley", "engine room", "medbay", "bay", "interior", "corridor",
                            "hallway", "lounge", "bridge"
                        )
                        if any(kw in space_part for kw in interior_keywords) or len(space_part) <= 30:
                            return vehicle_part
        # Pattern: "Space of Vehicle" (e.g. "Bridge of Starfall Cruiser")
        of_match = re.search(r"\s+of\s+(.+)$", name, re.IGNORECASE)
        if of_match:
            vehicle_part = of_match.group(1).strip()
            if vehicle_part and len(vehicle_part) >= 2:
                return vehicle_part
        return None
    
    def _validate_scene_markup(self, text: str, screenplay: Optional[Screenplay] = None) -> Tuple[bool, List[str]]:
        """Validate scene markup: every Wizard character has FULL CAPS, markup follows standard, no entity uses multiple types.
        Returns (passed, list of issue descriptions)."""
        issues = []
        if not text or not text.strip():
            return (True, [])
        # Check: no FULL CAPS inside underlined (no overlap)
        underlined_spans = [(m.start(), m.end()) for m in re.finditer(r'_[^_]+_', text)]
        _hon = r"(?:(?:MRS?|MS|DR|MME|PROF|SGT|CPT|LT|GEN|COL|REV|CMDR|CAPT)\.\s+)?"
        _nw = r"[A-Z][A-Z0-9]*(?:'[A-Z][A-Z0-9]*)?"
        all_caps_pattern = re.compile(
            rf"\b({_hon}{_nw}(?:[ \t]+(?:{_nw}|\"[^\"]*\"|'[^']*'))*)\b"
        )
        for match in all_caps_pattern.finditer(text):
            if len(match.group(1).strip()) < 2:
                continue
            if any(s <= match.start() < e for s, e in underlined_spans):
                issues.append(f"FULL CAPS entity inside underlined region: '{match.group(1).strip()}'")
                break
        # Check: underlined content must not be FULL CAPS (locations = title case)
        for um in re.finditer(r'_([^_]+)_', text):
            content = um.group(1).strip()
            if content and len(content) >= 2 and content.isupper():
                issues.append(f"Underlined entity must be title case, not FULL CAPS: '{content}'")
        # If screenplay has Wizard registry, every character in registry mentioned in text should appear in FULL CAPS at least once
        if screenplay and getattr(screenplay, "character_registry_frozen", False):
            registry = getattr(screenplay, "character_registry", None) or []
            text_upper = text.upper()
            for canonical in registry:
                if not canonical or not isinstance(canonical, str):
                    continue
                c = canonical.strip()
                # Check if any part of canonical name appears in text (case-insensitive)
                parts = set(re.split(r"[\s\"']+", c.lower())) - {""}
                mentioned = any(part in text.lower() for part in parts if len(part) >= 2)
                if not mentioned:
                    continue
                # Check if full canonical appears in FULL CAPS in text
                if c.upper() not in text_upper and not any(
                    re.search(r'\b' + re.escape(p.upper()) + r'\b', text) for p in parts if len(p) >= 2
                ):
                    issues.append(f"Wizard character '{c}' mentioned but not in FULL CAPS — must appear in FULL CAPS at least once")
                    break
        return (len(issues) == 0, issues)
    
    def _repair_sentence_integrity(self, content: str) -> Tuple[str, List[str]]:
        """
        Detect and repair incomplete/broken sentences caused by AI word-dropping.
        
        Uses heuristic detection followed by AI-powered repair.
        Returns (repaired_content, list_of_warning_strings).
        """
        from .sentence_integrity import detect_sentence_issues, build_repair_prompt, format_issues_summary
        
        if not content or not content.strip():
            return content, []
        
        issues = detect_sentence_issues(content)
        if not issues:
            return content, []
        
        warnings = [f"Sentence integrity: {len(issues)} broken sentence(s) detected"]
        print(f"SENTENCE INTEGRITY: {format_issues_summary(issues)}")
        
        # If no AI adapter, return with warnings only (can't repair)
        if not self._adapter:
            for issue in issues:
                warnings.append(f"  - [{issue.issue_type}] {issue.description}")
            return content, warnings
        
        # Build repair prompt and call AI
        repair_prompt = build_repair_prompt(content, issues)
        
        try:
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": (
                        "You are a screenplay content repair tool. Fix ONLY the broken/incomplete "
                        "sentences identified. Add the MINIMUM words needed. Preserve ALL existing "
                        "markup (*action*, (sfx), [objects], _locations_, {{vehicles}}, \"dialogue\", "
                        "CHARACTER NAMES). When adding verbs, wrap in *asterisks*. When adding sounds, "
                        "use (lowercase_underscore) format. Return the full corrected content only."
                    )},
                    {"role": "user", "content": repair_prompt}
                ],
                temperature=0.3,
                max_tokens=max(self.model_settings.get("max_tokens", 2000), 3000)
            )
            
            repaired = response.choices[0].message.content
            if repaired and isinstance(repaired, str) and repaired.strip():
                repaired = repaired.strip()
                
                # Remove markdown code blocks if present
                if repaired.startswith("```"):
                    lines = repaired.split("\n")
                    if len(lines) > 1:
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    repaired = "\n".join(lines).strip()
                
                # Verify the repair didn't lose too much content (sanity check)
                orig_lines = [l for l in content.split('\n') if l.strip()]
                repair_lines = [l for l in repaired.split('\n') if l.strip()]
                
                # Allow some variance but not major content loss
                if len(repair_lines) >= len(orig_lines) * 0.8:
                    # Re-check for remaining issues
                    remaining = detect_sentence_issues(repaired)
                    fixed_count = len(issues) - len(remaining)
                    
                    if fixed_count > 0:
                        warnings.append(f"Sentence integrity: repaired {fixed_count}/{len(issues)} issues")
                        if remaining:
                            warnings.append(f"Sentence integrity: {len(remaining)} issue(s) could not be auto-repaired")
                        print(f"SENTENCE INTEGRITY: Repaired {fixed_count}/{len(issues)} issues")
                        return repaired, warnings
                    else:
                        warnings.append("Sentence integrity: AI repair did not resolve issues")
                        print("SENTENCE INTEGRITY: AI repair did not resolve issues")
                else:
                    warnings.append("Sentence integrity: AI repair rejected (too much content lost)")
                    print(f"SENTENCE INTEGRITY: Repair rejected — original {len(orig_lines)} lines, repair {len(repair_lines)} lines")
        except Exception as e:
            warnings.append(f"Sentence integrity: repair failed — {str(e)}")
            print(f"SENTENCE INTEGRITY: Repair failed — {e}")
        
        return content, warnings
    
    def _validate_held_object_continuity(self, content: str) -> List[str]:
        """Detect held-object continuity violations in scene content.
        
        Tracks which objects each character is holding/using paragraph by paragraph.
        Flags when a character interacts with a new hand-held object without
        releasing the previous one.
        
        Returns list of warning strings (empty if no violations).
        """
        if not content or not content.strip():
            return []
        
        warnings = []
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        
        # Track: character_name (upper) -> set of object names they're currently holding
        held_objects: dict = {}  # e.g. {"CHLOE BAXTER": {"Ecto-Detector 3000"}}
        
        # Verbs that indicate ACQUIRING / HOLDING an object
        acquire_verbs = re.compile(
            r'\b(?:holds?|held|holding|grabs?|grabbed|grabbing|'
            r'picks?\s+up|picked\s+up|picking\s+up|'
            r'pulls?\s+out|pulled\s+out|pulling\s+out|'
            r'takes?|took|taking|draws?|drew|drawing|'
            r'raises?|raised|raising|lifts?|lifted|lifting|'
            r'clutches?|clutched|clutching|snatches?|snatched|'
            r'carries?|carried|carrying|wields?|wielded|wielding)\b',
            re.IGNORECASE
        )
        
        # Verbs that indicate RELEASING / PUTTING DOWN an object
        release_verbs = re.compile(
            r'\b(?:puts?\s+down|put\s+down|putting\s+down|'
            r'sets?\s+down|set\s+down|setting\s+down|'
            r'drops?|dropped|dropping|'
            r'places?\s+(?:on|down|aside|back)|placed\s+(?:on|down|aside|back)|'
            r'tucks?|tucked|tucking|'
            r'holsters?|holstered|holstering|'
            r'pockets?|pocketed|pocketing|'
            r'slings?|slung|slinging|'
            r'clips?\s+(?:to|on|onto)|clipped\s+(?:to|on|onto)|'
            r'sheathes?|sheathed|sheathing|'
            r'stows?|stowed|stowing|'
            r'releases?|released|releasing|'
            r'lowers?|lowered|lowering|'
            r'rests?\s+(?:on|against|down))\b',
            re.IGNORECASE
        )
        
        # Verbs that indicate USING a hand-held object (implies holding it)
        use_verbs = re.compile(
            r'\b(?:waves?|waved|waving|'
            r'points?|pointed|pointing|'
            r'aims?|aimed|aiming|'
            r'taps?|tapped|tapping|'
            r'adjusts?|adjusted|adjusting|'
            r'checks?|checked|checking|'
            r'fires?|fired|firing|'
            r'swings?|swung|swinging|'
            r'thrusts?|thrusting|'
            r'presses?|pressed|pressing|'
            r'squeezes?|squeezed|squeezing|'
            r'flips?|flipped|flipping|'
            r'clicks?|clicked|clicking)\b',
            re.IGNORECASE
        )
        
        # Possessive holding phrases
        possessive_hold = re.compile(
            r'in\s+(?:her|his|their|its)\s+hands?',
            re.IGNORECASE
        )
        
        # Objects that are small enough to hold simultaneously with another small object
        small_objects = {'phone', 'key', 'keycard', 'badge', 'coin', 'token',
                         'flashlight', 'torch', 'lighter', 'pen', 'pencil',
                         'card', 'note', 'letter', 'remote', 'walkie-talkie'}
        
        def is_small(obj_name: str) -> bool:
            return obj_name.lower() in small_objects or len(obj_name) <= 6
        
        # Extract character name from context around an object mention
        def find_character_for_object(text: str, obj_start: int) -> str:
            """Find which character is interacting with the object at obj_start position."""
            # Look backwards for the nearest FULL CAPS character name
            before = text[:obj_start]
            # Find ALL-CAPS names in the text before the object
            _nw_obj = r"[A-Z](?:[A-Z]+|'[A-Z]+)"
            char_matches = list(re.finditer(rf'\b({_nw_obj}(?:\s+{_nw_obj})*)\b', before))
            if char_matches:
                return char_matches[-1].group(1).strip()
            return ""
        
        for para in paragraphs:
            # Skip dialogue-only paragraphs
            if para.startswith('"') or (len(para.split('\n')) >= 2 and para.split('\n')[-1].strip().startswith('"')):
                continue
            
            para_lower = para.lower()
            
            # Find all [object] mentions in this paragraph
            for obj_match in re.finditer(r'\[([^\]]+)\]', para):
                obj_name = obj_match.group(1).strip()
                obj_pos = obj_match.start()
                
                # Determine which character is interacting
                char_name = find_character_for_object(para, obj_pos)
                if not char_name:
                    continue
                
                # Get the context around this object mention (100 chars before, 50 after)
                ctx_start = max(0, obj_pos - 100)
                ctx_end = min(len(para), obj_pos + len(obj_name) + 50)
                context = para[ctx_start:ctx_end]
                
                # Check if this is a RELEASE action
                if release_verbs.search(context):
                    if char_name in held_objects:
                        held_objects[char_name].discard(obj_name)
                    continue
                
                # Check if this is an ACQUIRE or USE action (implies holding)
                is_acquiring = bool(acquire_verbs.search(context))
                is_using = bool(use_verbs.search(context))
                is_possessive_hold = bool(possessive_hold.search(context))
                
                if is_acquiring or is_using or is_possessive_hold:
                    current_held = held_objects.get(char_name, set())
                    
                    if obj_name not in current_held and current_held:
                        # Character is already holding something — check for conflict
                        all_small = all(is_small(o) for o in current_held) and is_small(obj_name)
                        already_one_item = len(current_held) == 1
                        
                        if not (all_small and already_one_item):
                            held_list = ", ".join(f"[{o}]" for o in sorted(current_held))
                            warnings.append(
                                f"Held-object continuity: {char_name} interacts with [{obj_name}] "
                                f"but is still holding {held_list} — "
                                f"needs to put down/stow the previous object first"
                            )
                    
                    # Track this object as held
                    if char_name not in held_objects:
                        held_objects[char_name] = set()
                    held_objects[char_name].add(obj_name)
        
        return warnings

    def _validate_screenplay_style(self, content: str) -> Tuple[bool, List[str]]:
        """Validate that scene content follows screenplay style (no internal thoughts, metaphor, or abstract emotion).
        Returns (passed, list of issue descriptions)."""
        issues = []
        if not content or not content.strip():
            return (True, [])
        
        text_lower = content.lower()
        
        # Internal thought cues (indicating internal state without visible action)
        internal_thought_patterns = [
            (r'\b(feels?|feeling|felt)\s+(like|that|the|a|an|overwhelmed|consumed|conflicted)', 'internal feeling'),
            (r'\b(thinks?|thinking|thought)\s+(about|that|of|to himself|to herself)', 'internal thinking'),
            (r'\b(wonders?|wondering|wondered)\s+(if|whether|about|how|why)', 'internal wondering'),
            (r'\b(realizes?|realizing|realized)\s+(that|how|what)', 'internal realization'),
            (r'\b(knows?|knowing|knew)\s+that\b', 'internal knowledge'),
            (r'\bhesitates?,\s+(feeling|sensing|knowing|thinking)', 'hesitation with internal state'),
            (r'\b(mind|heart)\s+(races?|sank|sinks|pounds)', 'internal physical metaphor'),
            (r'\bweight of (his|her|their)\s+\w+', 'metaphorical weight'),
        ]
        
        for pattern, desc in internal_thought_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            if matches:
                issues.append(f"Internal thought detected ({desc}): avoid describing what character thinks/feels internally")
                break  # Only report first type found to avoid overwhelming
        
        # Metaphor and poetic language
        metaphor_patterns = [
            (r'\b(like|as)\s+a\s+\w+\s+(of|in|on)', 'simile/metaphor'),
            (r'\b(storm|ocean|sea|river|wave)\s+of\s+(emotions?|grief|fear|anger|joy)', 'emotional metaphor'),
            (r'\bshadow of\s+(doubt|fear|guilt|shame)', 'shadow metaphor'),
            (r'\bconsumed by\s+(fear|rage|grief|guilt)', 'consumed-by emotion'),
            (r'\boverwhelmed (by|with)\s+(emotion|grief|fear|joy)', 'overwhelmed-by emotion'),
        ]
        
        for pattern, desc in metaphor_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            if matches:
                issues.append(f"Metaphorical/poetic language detected ({desc}): use only literal, visible description")
                break
        
        # Abstract emotion without visible behavior
        abstract_emotion_patterns = [
            r'\b(conflicted|tormented|anguished|despairing|elated|euphoric)\b(?!\s+(expression|look|face|eyes))',
        ]
        
        for pattern in abstract_emotion_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                issues.append("Abstract emotion without visible behavior: show emotion through action/expression, not abstract terms")
                break
        
        return (len(issues) == 0, issues)
    
    # Common object nouns that require [brackets] when physically interacted with (chair, stool, console, etc.)
    _PHYSICAL_OBJECT_NOUNS = (
        "chair", "stool", "console", "table", "desk", "bench", "couch", "sofa", "armchair",
        "ottoman", "crate", "box", "barrel", "counter", "railing", "ledge", "shelf", "seat",
        # Additional common interactable objects
        "journal", "book", "notebook", "diary", "map", "letter", "note", "scroll",
        "flashlight", "torch", "lantern", "lamp", "candle",
        "phone", "tablet", "laptop", "radio", "walkie-talkie", "camera", "binoculars",
        "key", "keycard", "badge", "card", "token", "coin",
        "gun", "pistol", "rifle", "shotgun", "sword", "knife", "blade", "dagger", "axe",
        "bag", "backpack", "suitcase", "briefcase", "purse", "satchel",
        "bottle", "flask", "cup", "mug", "glass", "jar", "vial",
        "rope", "chain", "wire", "cable",
        "wrench", "screwdriver", "hammer", "crowbar", "tool",
        "helmet", "mask", "goggles", "headset",
        "remote", "switch", "lever", "button", "dial", "knob",
        "device", "gadget", "meter", "detector", "scanner",
        "board", "planchette",
    )
    _PHYSICAL_INTERACTION_VERB_PATTERN = re.compile(
        r"\b(sits?|sat|perches?|perched|leans?|leaned|rests?|rested|props?|propped|holds?|held|"
        r"touches?|touched|places?|placed|grips?|gripped|propped up|boots propped|feet propped|"
        # Additional interaction verbs for general object handling
        r"pulls?\s+out|pulled\s+out|lifts?|lifted|opens?|opened|closes?|closed|"
        r"grabs?|grabbed|takes?|took|picks?\s+up|picked\s+up|puts?\s+down|put\s+down|"
        r"flicks?|flicked|taps?|tapped|presses?|pressed|pushes?|pushed|"
        r"adjusts?|adjusted|straps?|strapped|aims?|aimed|points?|pointed|"
        r"raises?|raised|lowers?|lowered|waves?|waved|swings?|swung|"
        r"sets?\s+down|set\s+down|tosses?|tossed|throws?|threw|catches?|caught|"
        r"reads?|reading|writes?|writing|types?|typing|"
        r"activates?|activated|turns?\s+on|turned\s+on|turns?\s+off|turned\s+off|"
        r"fumbles?|fumbled|clutches?|clutched|snatches?|snatched|"
        r"inserts?|inserted|removes?|removed|attaches?|attached|detaches?|detached|"
        r"wears?|wore|wearing|puts?\s+on|put\s+on|takes?\s+off|took\s+off|"
        r"carries?|carried|carrying|drags?|dragged|dragging|"
        r"examines?|examined|inspects?|inspected|studies?|studied)\b",
        re.IGNORECASE
    )
    
    def _fix_dialogue_quotes(self, text: str) -> str:
        """Ensure dialogue in scene content is enclosed in double quotes.
        - Lines following a CHARACTER NAME (FULL CAPS) that aren't quoted → wrap in "
        - Single-quoted dialogue '...' → replace with "..."
        """
        if not text or not text.strip():
            return text
        lines = text.split("\n")
        result = []
        for i, line in enumerate(lines):
            orig = line
            stripped = line.strip()
            # Replace whole-line single-quoted dialogue with double-quoted
            if stripped.startswith("'") and stripped.endswith("'") and len(stripped) >= 3:
                # Whole line is single-quoted - convert to double
                inner = stripped[1:-1].replace('"', '\\"')
                indent = line[:len(line) - len(line.lstrip())]
                line = indent + '"' + inner + '"'
            # Line after character name (FULL CAPS) - wrap unquoted dialogue
            # Skip if line has action/object markup (* or [) - those are action lines, not dialogue
            if (i > 0 and stripped and not stripped.startswith(('"', '*', '[', '_', '(', '-')) and
                    '*' not in stripped and '[' not in stripped):
                prev = lines[i - 1].strip()
                # Prev line is character name: all caps, 1-5 words, no markup
                if prev and len(prev) <= 50:
                    words = prev.split()
                    caps_ratio = sum(1 for w in words if w.isupper() and len(w) > 1) / max(1, len(words))
                    is_char_name = (
                        caps_ratio >= 0.7 and
                        not prev.startswith(('_', '[', '(', '*')) and
                        not prev.endswith('_') and
                        1 <= len(words) <= 6
                    )
                    if is_char_name and not stripped.startswith('"'):
                        # This line is likely dialogue - wrap in double quotes
                        indent = line[:len(line) - len(line.lstrip())]
                        inner = stripped.replace('"', '\\"')
                        line = indent + '"' + inner + '"'
            result.append(line)
        return "\n".join(result)

    def _strip_markup_from_dialogue(self, text: str) -> str:
        """Remove all cinematic markup from within dialogue (text inside double quotes).
        
        Dialogue is spoken words — cinematic markup (_underscores_, [brackets],
        {braces}, *asterisks*) must not appear inside " ".
        """
        if not text or not text.strip():
            return text
        import re

        def _clean_dialogue(match: re.Match) -> str:
            raw = match.group(0)
            # Preserve the surrounding double quotes
            inner = raw[1:-1]
            # Strip environment markup: _Location Name_ → Location Name
            inner = re.sub(r'_([^_]+)_', r'\1', inner)
            # Strip object markup: [object] → object
            inner = re.sub(r'\[([^\]]+)\]', r'\1', inner)
            # Strip vehicle markup: {vehicle} or {{vehicle}} → vehicle
            inner = re.sub(r'\{+([^}]+)\}+', r'\1', inner)
            # Strip action markup: *action* → action
            inner = re.sub(r'\*([^*]+)\*', r'\1', inner)
            return '"' + inner + '"'

        # Match quoted dialogue strings (non-greedy, same-line)
        return re.sub(r'"[^"\n]+"', _clean_dialogue, text)

    def _fix_physical_interaction_object_markup(self, text: str) -> str:
        """Auto-correct scene text: wrap unmarked object nouns in [brackets] when they appear in
        physical-interaction contexts. Covers both prepositional patterns (sits on the chair)
        and direct-object patterns (pulls out a journal, holds up the flashlight).
        Only modifies sentences that contain a physical-interaction verb."""
        if not text or not text.strip():
            return text
        nouns = "|".join(re.escape(n) for n in self._PHYSICAL_OBJECT_NOUNS)
        # Pattern 1: prep (article) <noun> — e.g. "in the chair", "on his desk"
        prep_pattern = re.compile(
            rf"(in|on|against|onto)\s+(a|an|the|his|her|their)\s+(?!\[)({nouns})\b",
            re.IGNORECASE
        )
        # Pattern 2: (article) <noun> after any verb — e.g. "pulls out a journal", "holds the flashlight"
        direct_pattern = re.compile(
            rf"(?<!\[)\b(a|an|the|his|her|their)\s+(?!\[)({nouns})\b",
            re.IGNORECASE
        )
        # Run only in sentences that contain a physical-interaction verb; preserve paragraph breaks
        paragraphs = text.split("\n\n")
        out_paras = []
        for para in paragraphs:
            sentences = re.split(r'(?<=[.!?])\s+', para)
            out_sents = []
            for sent in sentences:
                if self._PHYSICAL_INTERACTION_VERB_PATTERN.search(sent):
                    sent = prep_pattern.sub(r"\1 \2 [\3]", sent)
                    sent = direct_pattern.sub(r"\1 [\2]", sent)
                out_sents.append(sent)
            out_paras.append(" ".join(out_sents))
        return "\n\n".join(out_paras)
    
    def _extract_all_wizard_characters_from_scene(self, scene_text: str, screenplay: Screenplay) -> List[str]:
        """Extract ALL Wizard characters mentioned in scene text with ZERO selectivity.
        
        MANDATORY: Complete and deterministic character extraction.
        - Scan entire scene for FULL CAPS mentions AND Title Case name variants
        - Match against Wizard Character Registry
        - Extract EVERY match (no filtering by importance/screen time/action/dialogue)
        - Return canonical names from registry
        
        ZERO SELECTIVITY RULE: If a character is mentioned, they MUST be extracted.
        Even if they appear briefly, are passive, do not speak, or are off to the side.
        Presence equals extraction.
        
        Args:
            scene_text: Full scene content to scan
            screenplay: Screenplay with character registry
            
        Returns:
            List of canonical character names (from Wizard registry) found in scene.
            Deduplicated but complete - no character mentioned is omitted.
        """
        if not scene_text or not scene_text.strip():
            return []
        
        if not screenplay or not getattr(screenplay, "character_registry_frozen", False):
            return []
        
        registry = getattr(screenplay, "character_registry", None)
        if not registry or not isinstance(registry, list):
            return []
        
        found_canonical = []
        seen_lower = set()
        
        def add_if_new(canonical: str):
            key = canonical.lower()
            if key not in seen_lower:
                seen_lower.add(key)
                found_canonical.append(canonical)
        
        # Wizard markup: _underlined_ = locations/environments, NOT characters.
        underlined_spans = [(m.start(), m.end()) for m in re.finditer(r'_[^_]+_', scene_text)]
        def inside_underlined(pos: int) -> bool:
            return any(s <= pos < e for s, e in underlined_spans)
        
        # METHOD 1: Find ALL FULL CAPS phrases in scene text (Wizard markup)
        # Supports honorifics (MRS., DR., MME.) and apostrophe names (O'MALLEY)
        _hon = r"(?:(?:MRS?|MS|DR|MME|PROF|SGT|CPT|LT|GEN|COL|REV|CMDR|CAPT)\.\s+)?"
        _nw = r"[A-Z][A-Z0-9]*(?:'[A-Z][A-Z0-9]*)?"
        all_caps_pattern = re.compile(
            rf"\b({_hon}{_nw}(?:[ \t]+(?:{_nw}|\"[^\"]*\"|'[^']*'))*)\b"
        )
        for match in all_caps_pattern.finditer(scene_text):
            phrase = match.group(1).strip()
            if len(phrase) < 2:
                continue
            if inside_underlined(match.start()):
                continue  # Inside _..._ = location, not character
            canonical = screenplay.resolve_character_to_canonical(phrase)
            if canonical is not None:
                add_if_new(canonical)
        
        # METHOD 2: Scan for Title Case mentions (generated scene content may not use FULL CAPS)
        # For each registry character, build searchable variants (first name, last name, nickname)
        for canonical in registry:
            if not canonical or not isinstance(canonical, str):
                continue
            c = canonical.strip()
            if not c:
                continue
            # Already found via FULL CAPS
            if c.lower() in seen_lower:
                continue
            # Extract name parts: "HENRY 'HANK' THOMPSON" → ["henry", "hank", "thompson"]
            parts = set(re.split(r"[\s\"']+", c.lower())) - {""}
            # Also create Title Case variants for searching
            # Search for canonical (title case version)
            c_title = c.title().replace("'S", "'s")  # Handle possessives
            if c_title.lower() in scene_text.lower():
                add_if_new(c)
                continue
            # Search for individual parts (first name, last name, nickname)
            for part in parts:
                if len(part) < 2:
                    continue
                # Use word boundary search for Title Case version
                part_title = part.title()
                pattern = re.compile(r'\b' + re.escape(part_title) + r'\b')
                if pattern.search(scene_text):
                    add_if_new(c)
                    break
        
        # METHOD 3: Find all capitalized words and check against registry
        # This catches any remaining Title Case names in scene content
        title_case_pattern = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b')
        for match in title_case_pattern.finditer(scene_text):
            phrase = match.group(1).strip()
            if len(phrase) < 2:
                continue
            if inside_underlined(match.start()):
                continue  # Inside _..._ = location, not character
            # Skip common non-name words
            if phrase.lower() in {"the", "this", "that", "with", "from", "into", "through", "meanwhile", "suddenly", "finally"}:
                continue
            canonical = screenplay.resolve_character_to_canonical(phrase)
            if canonical is not None:
                add_if_new(canonical)
        
        # --- Post-processing: clean the character list ---
        # Filter non-person entities, fold body parts, strip articles (same as _extract_all_characters_named_in_scene)
        cleaned = []
        cleaned_lower_set = set()
        for name in found_canonical:
            if self._is_company_or_concept_entity(name):
                continue
            parts = self._split_possessive_body_part(name)
            if parts:
                name = self._normalize_character_name_for_identity(parts[0]) or parts[0]
            else:
                name = self._normalize_character_name_for_identity(name) or name
            if name.lower() not in cleaned_lower_set:
                cleaned.append(name)
                cleaned_lower_set.add(name.lower())
        
        return cleaned
    
    def _extract_all_characters_named_in_scene(self, scene_text: str, screenplay: Optional[Screenplay] = None) -> List[str]:
        """Extract ALL characters named in scene content for identity block creation.
        
        Characters named in scene content MUST get identity blocks. Registry characters
        get canonical names; scene-only characters (not in registry) use the name as written.
        Scene-only characters do not get character outlines or growth arcs — those apply
        only to story-outline/registry characters.
        
        Returns:
            List of character names (canonical when in registry, as-written otherwise).
            Deduplicated.
        """
        if not scene_text or not scene_text.strip():
            return []
        
        # Common FULL CAPS that are not character names (acronyms, screenplay terms, sound/action words)
        NON_CHARACTER_CAPS = frozenset({
            # Acronyms / abbreviations
            "a", "i", "the", "usa", "fbi", "cia", "fda", "tv", "fm", "am", "dc", "ac",
            "bc", "ad", "ce", "ie", "eg", "etc", "ok", "no", "yes", "id", "mr", "mrs",
            "ms", "dr", "sr", "jr", "st", "ave", "blvd", "rd", "inc", "llc", "corp",
            "int", "ext", "cut", "fade", "dissolve", "close", "open", "end",
            # Screenplay / film terms
            "cut", "fade", "dissolve", "close", "open", "pan", "zoom", "dolly",
            "camera", "scene", "act", "flashback", "voiceover", "vo", "os", "oc",
            "continuation", "cont'd", "contd",
            # Camera / shot directions (never character names)
            "extreme", "medium", "wide", "tight", "angle", "shot", "insert",
            "intercut", "montage", "push", "pull", "tracking", "establishing",
            "overhead", "aerial", "pov", "reverse", "two-shot", "master",
            # Time / continuity descriptors
            "continuous", "later", "morning", "evening", "afternoon", "night", "day",
            "dawn", "dusk", "moments", "same",
            # Sound effects and onomatopoeia
            "crack", "moan", "bang", "boom", "crash", "whoosh", "thud", "snap",
            "creak", "splash", "click", "pop", "buzz", "hum", "ring", "ding",
            "slam", "clang", "clatter", "rumble", "roar", "scream", "shriek",
            "whisper", "murmur", "groan", "sob", "wail", "sigh", "gasp",
            # Emphasis / action adverbs that may appear in caps
            "suddenly", "slowly", "quickly", "silently", "loudly", "softly",
            "finally", "again", "still", "always", "never", "then", "now",
            # Common non-name words that appear in emphasis caps or labels
            "warning", "alert", "danger", "caution", "notice", "attention",
            "classified", "restricted", "authorized", "denied", "approved",
            "emergency", "critical", "protocol", "code", "operation",
            "project", "mission", "directive", "status", "report",
            "terminal", "breach", "lockdown", "shutdown", "override",
            "sequence", "procedure", "system", "error", "failure",
            "access", "control", "program", "signal", "response",
            "initiate", "activate", "deactivate", "engage", "disengage",
            "commence", "abort", "complete", "confirmed", "negative",
            "affirmative", "copy", "roger", "over", "out",
        })
        
        # Body-part words that should never be character names on their own
        _BODY_PART_CAPS = frozenset({
            "hands", "hand", "face", "faces", "eyes", "eye", "fingers", "finger",
            "arm", "arms", "leg", "legs", "feet", "foot", "head", "hair",
            "mouth", "lips", "voice", "body", "back", "shoulder", "shoulders",
            "fist", "fists", "palm", "palms", "grip", "silhouette", "shadow",
            "reflection", "gaze", "profile", "figure", "torso",
        })
        
        found = []
        seen_lower = set()
        
        def add_name(name: str):
            key = name.strip().lower()
            if key and key not in seen_lower:
                seen_lower.add(key)
                found.append(name.strip())
        
        # Wizard entity markup: _underlined_ = locations/environments, NOT characters.
        # Skip any ALL-CAPS phrase inside underlined regions.
        underlined_spans = []
        for um in re.finditer(r'_[^_]+_', scene_text):
            underlined_spans.append((um.start(), um.end()))
        def inside_underlined(pos: int) -> bool:
            return any(s <= pos < e for s, e in underlined_spans)
        
        # Find ALL FULL CAPS phrases (screenplay character markup)
        # Supports honorifics (MRS., DR., MME.) and apostrophe names (O'MALLEY)
        _hon = r"(?:(?:MRS?|MS|DR|MME|PROF|SGT|CPT|LT|GEN|COL|REV|CMDR|CAPT)\.\s+)?"
        _nw = r"[A-Z][A-Z0-9]*(?:'[A-Z][A-Z0-9]*)?"
        all_caps_pattern = re.compile(
            rf"\b({_hon}{_nw}(?:[ \t]+(?:{_nw}|\"[^\"]*\"|'[^']*'))*)\b"
        )
        for match in all_caps_pattern.finditer(scene_text):
            phrase = match.group(1).strip()
            if len(phrase) < 2:
                continue
            # Skip possessive fragments: if the character immediately before
            # the match is an apostrophe, this is a leftover from "NAME'S BODY"
            # e.g. FILMMAKER'S HANDS → regex captures "S HANDS" after the apostrophe
            match_start = match.start()
            if match_start > 0 and scene_text[match_start - 1] in "'\u2019\u2018":
                continue
            # Skip ALL-CAPS inside _underlined_ regions (environments/locations, not characters)
            if inside_underlined(match_start):
                continue
            # Skip obvious non-character words (acronyms, camera directions, sounds)
            phrase_lower = phrase.lower()
            if phrase_lower in NON_CHARACTER_CAPS:
                continue
            # Skip phrases where ALL words are non-character terms or body parts
            words = phrase.split()
            all_words_non_char = all(
                w.lower() in NON_CHARACTER_CAPS or w.lower() in _BODY_PART_CAPS
                for w in words
            )
            if all_words_non_char:
                continue
            # Reject phrases that are stage directions (e.g. "JERMY SITTING ALONE") not character names
            ACTION_DESCRIPTOR_WORDS = frozenset({
                "sitting", "standing", "walking", "alone", "quietly", "slowly", "quickly",
                "silently", "still", "motionless", "waiting", "watching", "looking", "leaning",
                "lying", "kneeling", "crouching", "running", "entering", "exiting"
            })
            if len(words) >= 2:
                # If 2nd+ word is an action/descriptor, this is likely "NAME SITTING ALONE" - not a name
                if any(w.lower() in ACTION_DESCRIPTOR_WORDS for w in words[1:]):
                    continue
            # Single short tokens that are likely acronyms
            if len(words) == 1 and len(phrase) <= 3:
                continue
            # --- Contextual filter: skip CAPS phrases preceded by label indicators ---
            # Phrases like "protocol: TERMINAL SANCTION" or "codename PHOENIX" are labels, not characters
            _LABEL_INDICATORS = re.compile(
                r'(?:protocol|codename|code\s*name|operation|project|program|initiative|'
                r'directive|order|mission|designation|classification|file|alert|warning|'
                r'signal|plan|phase|stage|level|status|mode|procedure|system|'
                r'clearance|authorization|condition|report|dossier|case)\s*[:\-—–]\s*$',
                re.IGNORECASE
            )
            pre_text = scene_text[max(0, match_start - 80):match_start]
            if _LABEL_INDICATORS.search(pre_text):
                continue
            # --- Common-word filter: reject multi-word CAPS phrases where every word is
            # a common English word (not a plausible proper name) ---
            _COMMON_NON_NAME_WORDS = frozenset({
                "terminal", "sanction", "human", "population", "control", "access",
                "denied", "granted", "approved", "rejected", "classified", "restricted",
                "authorized", "emergency", "critical", "maximum", "minimum", "total",
                "final", "primary", "secondary", "active", "inactive", "standard",
                "special", "advanced", "basic", "global", "local", "central",
                "national", "federal", "general", "public", "private", "internal",
                "external", "upper", "lower", "high", "low", "top", "bottom",
                "level", "phase", "stage", "code", "data", "file", "system",
                "network", "protocol", "program", "project", "operation", "mission",
                "target", "status", "report", "signal", "alert", "warning",
                "breach", "lockdown", "shutdown", "override", "sequence", "procedure",
                "response", "defense", "attack", "strike", "force", "power",
                "energy", "sector", "zone", "unit", "division", "command",
                "council", "order", "directive", "initiative", "contingency",
                "elimination", "termination", "extermination", "extraction",
                "containment", "quarantine", "purge", "cleanse", "reset",
                "absolute", "ultimate", "supreme", "omega", "alpha", "delta",
                "gamma", "sigma", "echo", "bravo", "tango", "foxtrot",
            })
            if len(words) >= 2:
                if all(w.lower() in _COMMON_NON_NAME_WORDS for w in words):
                    continue
            # Use canonical name if in registry; otherwise use as-written
            if screenplay and getattr(screenplay, "character_registry_frozen", False):
                canonical = screenplay.resolve_character_to_canonical(phrase)
                add_name(canonical if canonical is not None else phrase)
            else:
                add_name(phrase)
        
        # --- Post-processing: clean the character list ---
        # 1. Filter non-person entities (software UI, abstract visuals, etc.)
        found = [n for n in found if not self._is_company_or_concept_entity(n)]
        
        # 2. Fold body-part possessives ("filmmaker's hands" → "filmmaker")
        cleaned = []
        cleaned_lower = set()
        for name in found:
            parts = self._split_possessive_body_part(name)
            if parts:
                owner = parts[0]
                # Strip leading article from owner ("A filmmaker" → "filmmaker")
                owner = self._normalize_character_name_for_identity(owner)
                name = owner
            else:
                # Strip leading article ("A FILMMAKER" → "FILMMAKER")
                name = self._normalize_character_name_for_identity(name) or name
            
            if name.lower() not in cleaned_lower:
                cleaned.append(name)
                cleaned_lower.add(name.lower())
        
        return cleaned
    
    def _validate_scene_character_identity_blocks(
        self, scene_text: str, screenplay: Screenplay, identity_blocks: List[str]
    ) -> Tuple[bool, List[str]]:
        """Validate that ALL characters named in scene have identity blocks.
        
        REQUIRED validation pass: ensures no character is omitted.
        Includes both registry (Wizard) and scene-only characters.
        
        Args:
            scene_text: Full scene content
            screenplay: Screenplay with character registry
            identity_blocks: List of identity block strings generated for the scene
            
        Returns:
            (passed, list of missing canonical names). passed is True if all characters have blocks.
        """
        if not scene_text or not screenplay:
            return (True, [])
        
        # Extract ALL characters named in scene (registry + scene-only)
        mentioned = self._extract_all_characters_named_in_scene(scene_text, screenplay)
        if not mentioned:
            return (True, [])
        
        # Build set of canonical names that have identity blocks
        # Identity blocks contain the name at the start or in a "name:" field
        covered = set()
        for block in identity_blocks:
            if not block or not isinstance(block, str):
                continue
            block_lower = block.lower()
            for canonical in mentioned:
                if canonical.lower() in block_lower:
                    covered.add(canonical.lower())
                # Also check for partial name matches (first name, last name)
                parts = set(re.split(r"[\s\"']+", canonical.lower())) - {""}
                for part in parts:
                    if len(part) >= 3 and part in block_lower:
                        covered.add(canonical.lower())
                        break
        
        # Find missing characters
        missing = [c for c in mentioned if c.lower() not in covered]
        
        return (len(missing) == 0, missing)
    
    def _validate_entity_markup(self, text: str) -> Tuple[bool, List[str]]:
        """Validate Wizard entity markup: no FULL CAPS underlined, no underlined FULL CAPS.
        
        Returns:
            (passed, list of issue descriptions). passed is True if no violations.
        """
        issues = []
        # Find underlined spans and their content
        for um in re.finditer(r'_([^_]+)_', text):
            content = um.group(1).strip()
            if not content:
                continue
            # Underlined entity must NOT be FULL CAPS (locations = title case only)
            if content.isupper() and len(content) >= 2:
                issues.append(f"Underlined entity is FULL CAPS (must be title case): '{content}'")
        # Check no FULL CAPS phrase is inside an underlined region (already excluded in extraction)
        underlined_spans = [(m.start(), m.end()) for m in re.finditer(r'_[^_]+_', text)]
        _hon_v = r"(?:(?:MRS?|MS|DR|MME|PROF|SGT|CPT|LT|GEN|COL|REV|CMDR|CAPT)\.\s+)?"
        _nw_v = r"[A-Z][A-Z0-9]*(?:'[A-Z][A-Z0-9]*)?"
        all_caps_pattern = re.compile(
            rf"\b({_hon_v}{_nw_v}(?:[ \t]+(?:{_nw_v}|\"[^\"]*\"|'[^']*'))*)\b"
        )
        for match in all_caps_pattern.finditer(text):
            if len(match.group(1).strip()) < 2:
                continue
            if any(s <= match.start() < e for s, e in underlined_spans):
                issues.append(f"FULL CAPS entity inside underlined region (must not overlap): '{match.group(1).strip()}'")
                break  # one report per overlap type
        return (len(issues) == 0, issues)
    
    def regenerate_conclusion(self, premise: str, genres: List[str], atmosphere: str, title: str = "", main_storyline: str = "", subplots: str = "", characters: List[Dict[str, Any]] = None) -> str:
        """Regenerate just the conclusion based on the premise, main storyline, subplots, and characters."""
        
        if not self._adapter:
            raise Exception("AI client not initialized. Please configure your API key or local AI server in settings.")
        
        genre_text = ", ".join(genres) if genres else "General"
        title_text = f"Title: {title}\n" if title else ""
        
        # Build character summary
        character_summary = ""
        if characters:
            char_names = [char.get("name", "Unnamed") for char in characters if isinstance(char, dict)]
            if char_names:
                character_summary = f"\nMain Characters: {', '.join(char_names)}"
        
        main_storyline_text = f"\nMain Storyline: {main_storyline}" if main_storyline else ""
        subplots_text = f"\nSubplots: {subplots}" if subplots else ""
        
        prompt = f"""
You are a professional screenwriter and story structure expert. Generate a comprehensive final conclusion for this story:

{title_text}Premise: {premise}
Genres: {genre_text}
Atmosphere/Tone: {atmosphere}{main_storyline_text}{character_summary}{subplots_text}

Create a detailed final conclusion (4-6 sentences) that:
- Describes how the main story resolves
- Explains how key conflicts are resolved
- Describes the final state of the world/characters
- Includes any themes or messages that are conveyed
- Provides a satisfying and meaningful ending

ENTITY MARKUP (MANDATORY): Characters = FULL CAPS only (e.g. MAYA RIVERA, ELIAS CROSS). Use First 'Nickname' Last sparingly. Locations = Title Case + UNDERLINED (e.g. _Midnight Falls_, _City Hall_). All locations MUST be underlined on every mention. Characters must NEVER be underlined. Locations must NEVER be in full caps.

Return ONLY the conclusion text, no additional formatting, no quotes, no labels.
"""
        
        try:
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You are a professional screenwriter. ENTITY MARKUP: Characters = FULL CAPS only. Locations = Title Case + UNDERLINED (_Midnight Falls_, _City Hall_). All locations underlined on every mention; characters never underlined."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            content = response.choices[0].message.content.strip()
            
            # Clean up any quotes or formatting
            content = content.strip('"').strip("'").strip()
            
            # Remove any labels like "Conclusion:" or "Final Conclusion:"
            content = re.sub(r'^(Final\s+)?Conclusion:?\s*', '', content, flags=re.IGNORECASE)
            
            return content
                
        except Exception as e:
            error_message = str(e)
            raise Exception(f"Failed to regenerate conclusion: {error_message}")
    
    def regenerate_subplots(self, premise: str, genres: List[str], atmosphere: str, title: str = "", main_storyline: str = "", characters: List[Dict[str, Any]] = None) -> str:
        """Regenerate just the subplots based on the premise, main storyline, and characters."""
        
        if not self._adapter:
            raise Exception("AI client not initialized. Please configure your API key or local AI server in settings.")
        
        genre_text = ", ".join(genres) if genres else "General"
        title_text = f"Title: {title}\n" if title else ""
        
        # Build character summary
        character_summary = ""
        if characters:
            char_names = [char.get("name", "Unnamed") for char in characters if isinstance(char, dict)]
            if char_names:
                character_summary = f"\nMain Characters: {', '.join(char_names)}"
        
        main_storyline_text = f"\nMain Storyline: {main_storyline}" if main_storyline else ""
        
        prompt = f"""
You are a professional screenwriter and story structure expert. Generate subplots and secondary storylines for this story:

{title_text}Premise: {premise}
Genres: {genre_text}
Atmosphere/Tone: {atmosphere}{main_storyline_text}{character_summary}

Create 2-4 subplots and secondary storylines that:
- Are SEPARATE from the main storyline (do not repeat the main story)
- Complement and enhance the main narrative
- Relate to the main story in meaningful ways
- Each subplot should be 2-3 sentences
- Explain how each subplot relates to the main narrative
- Explain how subplots will be resolved or integrated

ENTITY MARKUP (MANDATORY): Characters = FULL CAPS only (e.g. MAYA RIVERA, ELIAS CROSS). Use First 'Nickname' Last sparingly. Locations = Title Case + UNDERLINED (e.g. _Midnight Falls_, _City Hall_). All locations MUST be underlined on every mention. Characters must NEVER be underlined. Locations must NEVER be in full caps.

Format as a single continuous text string. Each subplot should be clearly separated (use line breaks or numbering).

Return ONLY the subplots text, no additional formatting, no quotes, no labels like "Subplots:".
"""
        
        try:
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You are a professional screenwriter. ENTITY MARKUP: Characters = FULL CAPS only. Locations = Title Case + UNDERLINED (_Midnight Falls_, _City Hall_). All locations underlined on every mention; characters never underlined."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=800
            )
            
            content = response.choices[0].message.content.strip()
            
            # Clean up any quotes or formatting
            content = content.strip('"').strip("'").strip()
            
            # Remove any labels like "Subplots:" or "Secondary Storylines:"
            content = re.sub(r'^(Subplots?|Secondary\s+Storylines?):?\s*', '', content, flags=re.IGNORECASE)
            
            return content
                
        except Exception as e:
            error_message = str(e)
            raise Exception(f"Failed to regenerate subplots: {error_message}")
    
    def regenerate_character_details(self, premise: str, genres: List[str], atmosphere: str, title: str = "", 
                                     main_storyline: str = "", character_name: str = "", 
                                     regenerate_type: str = "both", existing_characters: List[Dict[str, Any]] = None,
                                     character_outline: str = "", species: str = "Human") -> Dict[str, str]:
        """
        Regenerate character outline and/or growth arc.
        
        Args:
            premise: Story premise
            genres: List of genres
            atmosphere: Story atmosphere/tone
            title: Story title
            main_storyline: Main storyline
            character_name: Name of the character
            regenerate_type: "outline", "growth_arc", or "both"
            existing_characters: List of existing character dicts with "name" and "outline" keys to avoid role duplication
            character_outline: Optional outline for THIS character (used when regenerating physical_appearance to extract age)
            species: The character's species/form (e.g. "Human", "Dragon", "Elf")
        
        Returns:
            Dict with "outline", "growth_arc", and optionally "name" keys
        """
        if not self._adapter:
            raise Exception("AI client not initialized. Please configure your API key or local AI server in settings.")
        
        def _strip_character_label_prefix(text: str) -> str:
            """Remove leading 'Character1:', 'Character 1:', 'NewCharacter1:', etc. from text."""
            if not text or not isinstance(text, str):
                return text
            text = text.strip()
            stripped = re.sub(r'^(?:Character\s*\d+|NewCharacter\d+)\s*:\s*', '', text, flags=re.IGNORECASE)
            return stripped.strip() if stripped != text else text
        
        def _normalize_character_name(name: str) -> str:
            """Return display name only (no 'Character1: Name' prefix)."""
            if not name or not isinstance(name, str):
                return name or ""
            name = name.strip()
            stripped = re.sub(r'^(?:Character\s*\d+|NewCharacter\d+)\s*:\s*', '', name, flags=re.IGNORECASE)
            return stripped.strip() if stripped else name
        
        genre_text = ", ".join(genres) if genres else "General"
        title_text = f"Title: {title}\n" if title else ""
        main_storyline_text = f"\nMain Storyline: {main_storyline}" if main_storyline else ""
        is_human = (not species or species.strip().lower() in ("human", ""))
        species_label = species.strip() if species and species.strip() else "Human"
        
        # Build species-aware physical appearance instructions
        if is_human:
            phys_instructions = (
                "Physical Appearance (Persistent): 2-4 sentences describing. MUST include gender, height, and age (when known). "
                "Do NOT mention the character's name.\n"
                "- Gender and height (MANDATORY — e.g. \"female, 5'6\\\"\", \"male, 6'2\\\"\")\n"
                "- Age or age range (MANDATORY when mentioned in context — e.g. \"22 years old\", \"in his early thirties\")\n"
                "- Face structure, hair color and style, eye color\n"
                "- Skin tone, body build\n"
                "- Permanent features only: scars, tattoos, glasses (if permanent)\n"
                "MUST NOT include: the character's name, clothing, accessories (hat, cap, earbuds, jewelry), armor, uniforms, scene-specific conditions (dirty, wet, damaged)."
            )
            phys_json_hint = (
                "Gender and height (MANDATORY), age when known (MANDATORY), face, hair, eyes, skin, build, permanent features. "
                "Do NOT include the character name. NO clothing, accessories (hat, cap, earbuds), armor, uniforms."
            )
        elif species_label.lower() == "dragon":
            phys_instructions = (
                f"Physical Appearance (Persistent): 2-4 sentences describing this {species_label}. "
                "Do NOT mention the character's name.\n"
                "- Size category (e.g. \"massive, 40-foot wingspan\", \"small, cat-sized\")\n"
                "- Scale colour, texture, and pattern (MANDATORY)\n"
                "- Eye colour and pupil shape\n"
                "- Horn/crest/ridge shape and colour\n"
                "- Wing shape, span, membrane colour\n"
                "- Body build, tail features, claw details\n"
                "- Distinguishing marks: scars, missing scales, unusual colouring\n"
                "MUST NOT include: the character's name, any rider or saddle, scene-specific conditions."
            )
            phys_json_hint = (
                f"Size, scale colour/texture/pattern, eye colour, horn/crest shape, wing details, body build, tail, claws, "
                "distinguishing marks. Do NOT include the character name. NO rider or saddle."
            )
        elif species_label.lower() in ("robot / android", "robot", "android"):
            phys_instructions = (
                f"Physical Appearance (Persistent): 2-4 sentences describing this {species_label}. "
                "Do NOT mention the character's name.\n"
                "- Height and build (MANDATORY)\n"
                "- Chassis/plating material and colour\n"
                "- Eye/sensor type, colour, and glow\n"
                "- Degree of humanoid resemblance\n"
                "- Distinguishing marks, serial numbers, damage\n"
                "MUST NOT include: the character's name, detachable accessories, scene-specific conditions."
            )
            phys_json_hint = (
                f"Height, build, chassis design, plating colour, sensor/eye style, humanoid features, distinguishing marks. "
                "Do NOT include the character name."
            )
        elif species_label.lower() in ("ghost / spirit", "ghost", "spirit"):
            phys_instructions = (
                f"Physical Appearance (Persistent): 2-4 sentences describing this {species_label}. "
                "Do NOT mention the character's name.\n"
                "- Apparition form and translucency level\n"
                "- Glow or aura colour\n"
                "- Visible features: face, hair, build (as they appeared in life or in death)\n"
                "- Distinguishing marks, wounds, or ethereal features\n"
                "MUST NOT include: the character's name, clothing (unless fused to their ghostly form), scene-specific conditions."
            )
            phys_json_hint = (
                f"Apparition form, translucency, glow colour, visible features (face, hair, build), distinguishing marks. "
                "Do NOT include the character name."
            )
        elif species_label.lower() == "animal":
            phys_instructions = (
                f"Physical Appearance (Persistent): 2-4 sentences describing this animal character. "
                "Do NOT mention the character's name.\n"
                "- Animal type/breed (MANDATORY)\n"
                "- Size and build\n"
                "- Fur/feather/scale colour and pattern\n"
                "- Eye colour\n"
                "- Distinguishing marks, scars, unique features\n"
                "MUST NOT include: the character's name, collars, saddles, or accessories, scene-specific conditions."
            )
            phys_json_hint = (
                "Animal type, size, fur/feather/scale colour, eye colour, build, distinguishing marks. "
                "Do NOT include the character name. NO collars or accessories."
            )
        else:
            phys_instructions = (
                f"Physical Appearance (Persistent): 2-4 sentences describing this {species_label}. "
                f"This character is a {species_label}, NOT a human. Describe their species-appropriate anatomy. "
                "Do NOT mention the character's name.\n"
                "- Size and build (MANDATORY)\n"
                "- Skin/scale/fur/feather colour and texture\n"
                "- Eye colour and distinctive facial/head features\n"
                "- Any species-specific anatomy (wings, tail, horns, pointed ears, fangs, etc.)\n"
                "- Distinguishing marks or unique features\n"
                "MUST NOT include: the character's name, clothing or accessories, scene-specific conditions."
            )
            phys_json_hint = (
                f"Size, build, skin/scale/fur colour, eye colour, species-specific features "
                f"(wings, tail, horns, fangs, pointed ears, etc.), distinguishing marks. "
                "Do NOT include the character name. NO clothing or accessories."
            )
        
        species_context_line = f"\nCharacter Species/Form: {species_label}" if not is_human else ""
        
        # Build existing characters context to avoid role and name duplication
        existing_chars_context = ""
        if existing_characters:
            other_characters = [char for char in existing_characters if isinstance(char, dict) and char.get("name", "").lower() != character_name.lower()]
            if other_characters:
                existing_chars_context = "\n\nEXISTING CHARACTERS (DO NOT duplicate their roles, backgrounds, or any part of their names):\n"
                for char in other_characters:
                    char_name = char.get("name", "")
                    char_outline = char.get("outline", "")
                    if char_name and char_outline:
                        existing_chars_context += f"- {char_name}: {char_outline[:200]}...\n"
        
        # Detect if character_name is a placeholder (NewCharacter1, Character 1, etc.)
        char_name_stripped = (character_name or "").strip()
        is_placeholder_name = bool(re.match(r"^(?:NewCharacter\d+|Character\s*\d+)$", char_name_stripped, re.IGNORECASE))
        
        name_consistency_line = f'\nNAME CONSISTENCY: You MUST refer to this character ONLY by the exact name above ("{character_name}") in the outline and growth arc. Do NOT substitute a different name (e.g. if the name is "Chuckles", do not use "Jasper" or any other name).\n'
        
        if regenerate_type == "outline":
            prompt = f"""
You are a professional screenwriter and character development expert. Generate a detailed character outline for this character based on their role in the story.

{title_text}Premise: {premise}
Genres: {genre_text}
Atmosphere/Tone: {atmosphere}{main_storyline_text}{existing_chars_context}

Character Name: {character_name}{species_context_line}
{name_consistency_line}
CRITICAL — DO NOT MAKE UP CHARACTERS: {character_name} MUST be a character that EXPLICITLY APPEARS in the main_storyline, subplots, or conclusion above. Only develop outlines for characters that are already named in the story content. Do NOT invent or create new character names — if the character is not in the story text, you are generating for the wrong character.

IMPORTANT: Look at the storyline above and identify what role {character_name} plays. Base your character development on their actions and relationships described in the storyline.

CRITICAL: Review the existing characters listed above. DO NOT duplicate their roles, backgrounds, or key story functions. {character_name} must have a UNIQUE role and contribution that doesn't overlap with existing characters.

Create a detailed character outline (6-10 sentences, or 2-3 paragraphs) that includes:
- Role in the story and relationship to main plot (MUST be unique, not duplicating existing characters)
- Background, profession, or key characteristics (MUST be distinct from existing characters)
- Personality traits and motivations
- Relationships with other characters
- What drives them and their goals in the story
- How they contribute to the narrative (MUST be a unique contribution)

DO NOT include physical appearance — that belongs ONLY in the physical_appearance field, not in the outline.

Be specific and detailed. Do not use generic or placeholder language. Base everything on the story context provided. Ensure this character's role and background are DISTINCT from all existing characters.

ENTITY MARKUP (MANDATORY): Character names = FULL CAPS in all text (e.g. SARAH CHEN, MARCUS WEBB). Locations = _underlined_ (including vehicle interiors like _Common Area_, _Bridge_ — "the ship's X" is a location). Objects = [brackets]. Vehicles = {{braces}} (exterior only). Never use Title Case for character names — use FULL CAPS to match the story format. If this character OWNS a place, vehicle, or object, state it explicitly (e.g. "owns the {{motorcycle}}", "owns _The Warehouse_"). Ownership will be strictly enforced throughout the story.

FORMATTING: Do NOT prefix the outline with labels like "Character1:", "Character 1:", or "NewCharacter1:". Write using the character's name directly (e.g. "Sarah is..." or "Marcus serves...").

Return ONLY the character outline text, no additional formatting, no quotes, no labels like "Character Outline:".
"""
        elif regenerate_type == "growth_arc":
            prompt = f"""
You are a professional screenwriter and character development expert. Generate a detailed character growth arc for this character based on their journey in the story.

{title_text}Premise: {premise}
Genres: {genre_text}
Atmosphere/Tone: {atmosphere}{main_storyline_text}{existing_chars_context}

Character Name: {character_name}{species_context_line}
{name_consistency_line}
CRITICAL — DO NOT MAKE UP CHARACTERS: {character_name} MUST be a character that EXPLICITLY APPEARS in the main_storyline, subplots, or conclusion above. Only develop growth arcs for characters already named in the story content. Do NOT invent new character names.

IMPORTANT: Look at the storyline above and identify {character_name}'s journey throughout the story. Base their growth arc on the events and challenges described in the storyline.

CRITICAL: Review the existing characters listed above. Ensure {character_name}'s growth arc is unique and doesn't duplicate the development paths of existing characters.

Create a detailed character growth arc (6-10 sentences, or 2-3 paragraphs) that includes:
- Who they are at the beginning of the story
- Key challenges, conflicts, or obstacles they face (MUST be distinct from existing characters' challenges)
- How they respond to these challenges
- What they learn or how they change (MUST be a unique transformation)
- How they grow or develop throughout the story  
- Who they become by the end of the narrative

Be specific and detailed. Do not use generic or placeholder language. Base everything on the story context and their actual journey in the narrative. Ensure this character's growth arc is DISTINCT from all existing characters.

ENTITY MARKUP (MANDATORY): Character names = FULL CAPS in all text (e.g. SARAH CHEN, MARCUS WEBB). Locations = _underlined_ (vehicle interiors like _Common Area_ use underscores, not braces). Objects = [brackets]. Vehicles = {{braces}} (exterior only). If this character owns a place, vehicle, or object, use markup and state ownership explicitly. Ownership will be strictly enforced throughout the story.

FORMATTING: Do NOT prefix the growth arc with labels like "Character1:", "Character 1:", or "NewCharacter1:". Write using the character's name directly (e.g. "Sarah begins..." or "Marcus evolves...").

Return ONLY the growth arc text, no additional formatting, no quotes, no labels like "Growth Arc:".
"""
        elif regenerate_type == "physical_appearance":
            character_outline_text = ""
            if character_outline and character_outline.strip():
                character_outline_text = f"\n\nTHIS CHARACTER'S OUTLINE (extract age from here if mentioned):\n{character_outline.strip()[:500]}"
            age_line = (
                '\nAGE IS MANDATORY: If the storyline, outline, or any context above mentions this character\'s age '
                '(e.g. "22 years old", "teenager", "in his thirties"), you MUST include it in physical_appearance.\n'
                if is_human else ""
            )
            prompt = f"""
You are a professional screenwriter and character development expert. Generate a physical appearance description for this character based on their role in the story. Include ONLY persistent physical traits — NO clothing, accessories, armor, or uniforms.

{title_text}Premise: {premise}
Genres: {genre_text}
Atmosphere/Tone: {atmosphere}{main_storyline_text}{existing_chars_context}{character_outline_text}

Character Name: {character_name}{species_context_line}
{name_consistency_line}
CRITICAL — DO NOT MAKE UP CHARACTERS: {character_name} MUST be a character that EXPLICITLY APPEARS in the main_storyline, subplots, or conclusion above.
{age_line}
{phys_instructions}

Return ONLY the physical appearance text, no additional formatting, no quotes, no labels like "Physical Appearance:".
"""
        else:  # both
            name_rule_species = (
                "NAME RULE: The \"name\" field MUST be a proper name. Use simple first and last names (e.g. Sarah Chen, Marcus Webb) for humanoid characters. "
                "For non-human characters (dragons, animals, etc.), a single name or title is acceptable (e.g. SMAUG, SHADOWFANG). "
                "Use the First 'Nickname' Last format sparingly. NEVER use a job title, role, or description."
                if not is_human else
                "NAME RULE: The \"name\" field MUST be a person's proper name. Use simple first and last names (e.g. Sarah Chen, Marcus Webb). "
                "Use the First 'Nickname' Last format sparingly. NEVER use a job title, role, or description "
                "(e.g. \"Former Park Employee\", \"The Detective\", \"Park Ranger\", \"Security Guard\"). Every character must have a real first and last name."
            )
            char_name_instruction = (
                "The character's name is already '" + character_name + "'. Use this EXACT name in the 'name' field and in all outline/growth_arc text. Do NOT replace it with a different name. Use FULL CAPS for the name (e.g. SARAH CHEN) to match the story markup."
                if not is_placeholder_name
                else 'You MUST use a character name that EXPLICITLY APPEARS in the main_storyline, subplots, or conclusion above. Do NOT invent or make up a new name. Pick one of the characters already named in FULL CAPS in the story content. The "name" field must be that character\'s name in FULL CAPS (e.g. "SARAH CHEN", "MARCUS WEBB"). Never use placeholders (Character1, NewCharacter1) or job titles. Never invent a character not in the story.'
            )
            prompt = f"""
You are a professional screenwriter and character development expert. Generate detailed character details for this character based on their role in the story.

{title_text}Premise: {premise}
Genres: {genre_text}
Atmosphere/Tone: {atmosphere}{main_storyline_text}{existing_chars_context}

Character Name: {character_name}{species_context_line}
{name_consistency_line}
CRITICAL — DO NOT MAKE UP CHARACTERS: {character_name} MUST be a character that EXPLICITLY APPEARS in the main_storyline, subplots, or conclusion above. Only develop profiles for characters already named in the story content. Do NOT invent or create new character names.

IMPORTANT: Look at the storyline above and identify what role {character_name} plays in the story. Base your character development on their actions and relationships described in the storyline.

CRITICAL: Review the existing characters listed above. DO NOT duplicate their roles, backgrounds, or key story functions. {character_name} must have a UNIQUE role and contribution that doesn't overlap with existing characters.

Create:
1. {phys_instructions}

2. CHARACTER OUTLINE (6-10 detailed sentences, or 2-3 paragraphs):
   - Role in the story and relationship to main plot (MUST be unique, not duplicating existing characters)
   - Background, profession, or key characteristics (MUST be distinct from existing characters)
   - Personality traits and motivations
   - Relationships with other characters
   - What drives them and their goals in the story
   - How they contribute to the narrative (MUST be a unique contribution)
   - DO NOT include physical appearance details — that belongs ONLY in physical_appearance.

3. CHARACTER GROWTH ARC (6-10 detailed sentences, or 2-3 paragraphs):
   - Who they are at the beginning of the story
   - Key challenges, conflicts, or obstacles they face
   - How they respond to these challenges
   - What they learn or how they change
   - How they grow or develop throughout the story
   - Who they become by the end of the narrative

CRITICAL: Each section must be substantial and detailed. Do not use generic or placeholder language. Base everything on the specific story context provided. Ensure this character's role and background are DISTINCT from all existing characters.

ENTITY MARKUP (MANDATORY): Character names = FULL CAPS in all text (e.g. SARAH CHEN, MARCUS WEBB). Locations = _underlined_ (vehicle interiors like _Common Area_, _Bridge_ use underscores — "the ship's X" is a location). Objects = [brackets]. Vehicles = {{braces}} (exterior only). Never use Title Case for character names. If this character OWNS a place, vehicle, or object, state it explicitly (e.g. "owns the {{motorcycle}}", "owns _The Warehouse_"). Ownership will be strictly enforced throughout the story — no other character may use or claim that entity unless ownership is explicitly transferred.

CHARACTER NAME: {char_name_instruction}

{name_rule_species}

FORMATTING: Do NOT prefix the outline or growth_arc text with labels like "Character1:", "Character 1:", or "NewCharacter1:". Write using the character's name directly (e.g. "Sarah is..." or "Marcus serves...").

Return ONLY valid JSON with this EXACT structure:
{{
    "name": "Character name in FULL CAPS — MUST be a name that appears in the story content above. Do NOT invent new names.",
    "physical_appearance": "{phys_json_hint}",
    "outline": "Detailed character outline (6-10 sentences: role, background, personality, relationships, contribution. NO physical appearance — that goes in physical_appearance only. Be substantial.)",
    "growth_arc": "Detailed character growth arc (6-10 sentences describing their journey, challenges, development, and transformation throughout the story. Be substantial.)"
}}

No markdown, no explanations, no code blocks. Just the JSON object.
"""
        
        try:
            system_message = "You are a professional screenwriter specializing in character development. Do NOT invent or make up characters — only develop characters that EXPLICITLY appear in the story content. Character names must use FULL CAPS markup."
            if regenerate_type == "both":
                system_message = "You are a professional screenwriter specializing in character development. Do NOT invent or make up characters — only develop characters that EXPLICITLY appear in the story content. Character names must use FULL CAPS. Return ONLY valid JSON, no markdown, no explanations."
            
            # Scale max_tokens: outline + growth_arc can be 6-10 sentences each (~150-250 tokens per field)
            total_chars = 1 + len(existing_characters or [])
            char_max_tokens = max(2500, 2000 + 300 * total_chars)  # More headroom for longer outlines/arcs
            char_max_tokens = max(char_max_tokens, self.model_settings.get("max_tokens", 2000))
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=char_max_tokens
            )
            
            content = response.choices[0].message.content.strip()
            
            if regenerate_type == "both":
                # Try to parse as JSON
                try:
                    # Remove markdown code blocks if present
                    original_content = content
                    content = re.sub(r'```json\s*', '', content)
                    content = re.sub(r'```\s*', '', content)
                    content = content.strip()
                    
                    # Try to find JSON object in the content
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        content = json_match.group(0)
                    
                    result = json.loads(content)
                    if not isinstance(result, dict):
                        raise ValueError("Result is not a dictionary")
                    
                    # Validate that we have content
                    outline = result.get("outline", "").strip()
                    growth_arc = result.get("growth_arc", "").strip()
                    physical_appearance = result.get("physical_appearance", "").strip()
                    # Strip "Character1:" etc. from start of outline and growth_arc
                    outline = _strip_character_label_prefix(outline)
                    growth_arc = _strip_character_label_prefix(growth_arc)
                    physical_appearance = _strip_character_label_prefix(physical_appearance)
                    physical_appearance = self._strip_character_name_from_physical_appearance(physical_appearance, character_name)
                    
                    if not outline or not growth_arc:
                        _safe_print(f"    JSON parsed but content missing - outline: {len(outline)} chars, growth_arc: {len(growth_arc)} chars")
                        if not outline:
                            _safe_print("    Missing outline, trying text extraction...")
                        if not growth_arc:
                            _safe_print("    Missing growth_arc, trying text extraction...")
                        raise ValueError("JSON missing required content")
                    
                    # Normalize and include name: prefer input name when not a placeholder
                    if not is_placeholder_name:
                        result["name"] = _normalize_character_name(char_name_stripped)
                    else:
                        name_val = result.get("name", "").strip()
                        if name_val:
                            result["name"] = _normalize_character_name(name_val)
                    # Enforce person names: reject job titles/roles (e.g. "Former Park Employee")
                    if self._is_role_or_title_only(result.get("name", "")):
                        name_fix_prompt = f"""This character was incorrectly given a job title as their name. The outline is: {outline[:300]}...

Return ONLY a JSON object with one field "name" set to a proper person's name (first and last name, e.g. "Sarah Chen" or "Marcus Webb"). Do NOT use job titles, roles, or descriptions like "Former Park Employee" or "Park Ranger"."""
                        try:
                            fix_resp = self._chat_completion(
                                model=self.model_settings["model"],
                                messages=[
                                    {"role": "system", "content": "You return only a JSON object with a 'name' field containing a person's full name. No job titles."},
                                    {"role": "user", "content": name_fix_prompt}
                                ],
                                temperature=0.3,
                                max_tokens=80
                            )
                            fix_content = fix_resp.choices[0].message.content.strip()
                            fix_content = re.sub(r'```\w*\s*', '', fix_content).strip()
                            fix_match = re.search(r'\{[^}]*"name"\s*:\s*"([^"]+)"', fix_content)
                            if fix_match:
                                fixed_name = _normalize_character_name(fix_match.group(1).strip())
                                if fixed_name and not self._is_role_or_title_only(fixed_name):
                                    result["name"] = fixed_name
                        except Exception:
                            pass
                        if self._is_role_or_title_only(result.get("name", "")):
                            n = len(existing_characters) + 1 if existing_characters else 1
                            result["name"] = f"Character{n}"
                    result["outline"] = outline
                    result["growth_arc"] = growth_arc
                    result["physical_appearance"] = physical_appearance
                    raw_sp = str(result.get("species", species or "Human") or "Human").strip()
                    result["species"] = normalize_species_label(raw_sp)
                    if result["species"] == "Human" and not is_human:
                        result["species"] = infer_species_from_text(outline, physical_appearance, "", character_name)
                    
                    return result
                except (json.JSONDecodeError, ValueError) as e:
                    _safe_print(f"    JSON parsing failed for character generation: {e}")
                    _safe_print(f"    Raw response length: {len(content)} chars")
                    
                    # Fallback: try to extract outline, growth_arc, and physical_appearance from text
                    outline_patterns = [
                        r'(?:outline|character\s+outline)[:\s]+(.+?)(?:\n\s*(?:2\.|growth|arc|physical)|$)',
                        r'1\.\s*(?:character\s+outline[:\s]*)?(.+?)(?:\n\s*2\.|$)',
                        r'"outline"[:\s]*"((?:[^"\\]|\\.)*)"'
                    ]
                    growth_patterns = [
                        r'(?:growth\s+arc|character\s+growth)[:\s]+(.+?)(?:\n\s*(?:3\.|physical|appearance)|$)',
                        r'2\.\s*(?:character\s+growth\s+arc[:\s]*)?(.+?)(?:\n\s*3\.|$)',
                        r'"growth_arc"[:\s]*"((?:[^"\\]|\\.)*)"'
                    ]
                    physical_patterns = [
                        r'"physical_appearance"[:\s]*"((?:[^"\\]|\\.)*)"',
                        r'(?:physical\s+appearance|physical_appearance)[:\s]+(.+?)(?=\n\s*(?:"outline"|"name"|\}|\Z))',
                        r'3\.\s*(?:physical\s+appearance[:\s]*)?(.+?)(?=\s*\n|$)'
                    ]
                    
                    outline_text = ""
                    growth_text = ""
                    physical_text = ""
                    
                    for pattern in outline_patterns:
                        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
                        if match:
                            outline_text = match.group(1).strip()
                            if outline_text:
                                break
                    
                    for pattern in growth_patterns:
                        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
                        if match:
                            growth_text = match.group(1).strip()
                            if growth_text:
                                break
                    
                    for pattern in physical_patterns:
                        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
                        if match:
                            physical_text = match.group(1).strip()
                            if physical_text and len(physical_text) >= 30:
                                physical_text = _strip_character_label_prefix(physical_text)
                                physical_text = self._strip_character_name_from_physical_appearance(physical_text, character_name)
                                break
                    
                    _safe_print(f"    Text extraction results - outline: {len(outline_text)} chars, growth_arc: {len(growth_text)} chars, physical: {len(physical_text)} chars")
                    outline_text = _strip_character_label_prefix(outline_text)
                    growth_text = _strip_character_label_prefix(growth_text)
                    fallback_species = infer_species_from_text(outline_text, physical_text or "", "", character_name)
                    return {
                        "outline": outline_text,
                        "growth_arc": growth_text,
                        "physical_appearance": physical_text or "",
                        "species": fallback_species
                    }
            else:
                # Single field - clean up and return (strip Character1: etc. from start)
                content = content.strip('"').strip("'").strip()
                content = re.sub(r'^(Character\s+Outline|Growth\s+Arc|Character\s+Growth\s+Arc|Physical\s+Appearance):?\s*', '', content, flags=re.IGNORECASE)
                content = _strip_character_label_prefix(content)
                
                if regenerate_type == "outline":
                    return {"outline": content, "growth_arc": ""}
                elif regenerate_type == "physical_appearance":
                    phys_content = self._strip_character_name_from_physical_appearance(content, character_name)
                    return {"physical_appearance": phys_content}
                else:
                    return {"outline": "", "growth_arc": content}
                    
        except Exception as e:
            error_message = str(e)
            raise Exception(f"Failed to regenerate character details: {error_message}")
    
    def _get_intent_guidance(self, intent: str) -> str:
        """Get intent-specific guidance for story generation."""
        intent_guidance_map = {
            "Advertisement / Brand Film": """
INTENT-SPECIFIC GUIDANCE — STRUCTURED COMMERCIAL MODE:
This is a PRODUCED COMMERCIAL, not a short film or narrative story.

TONE:
- Visually driven: every beat is a cinematic moment, not a story scene
- NO long exposition, NO unnecessary dialogue, NO novelistic narration
- Focus on CINEMATIC BEATS: camera, motion, light, product presence
- Dialogue must be minimal and purposeful (tagline or single line max)
- If output resembles narrative storytelling instead of a commercial script, it is WRONG

STRUCTURE (6-beat micro template):
1. Hook — Immediate visual intrigue, no exposition
2. Pain/Desire — Relatable problem or aspiration
3. Product Reveal — Product framed as hero, clear reveal moment
4. Feature Demo — Features VISUALIZED through action, not narrated
5. Emotional Payoff — Transformation/empowerment, escalates from earlier
6. Brand Moment — Logo, tagline, CTA, clean and polished

ESCALATION RULE:
Each beat MUST increase in at least one of: visual scale, emotional intensity,
energy, motion, or cinematic dominance of the product.
NO flat sequential feature stacking.

NARRATIVE LIMITS:
- Max 1 primary character, 1-2 environments
- NO subplots, NO character growth arcs, NO multi-location wandering
- Product is the true hero, character is the vehicle

CAMERA AND PACING:
- Dynamic camera movements (tracking, dolly, crane, gimbal)
- Fast or Medium pacing for all beats
- Fewer, more impactful beats rather than many small ones
""",
            "Social Media / Short-form": """
INTENT-SPECIFIC GUIDANCE — SHORT-FORM PLATFORM CONTENT:
- Hook-first: The opening storyboard item MUST grab attention instantly (first 2 seconds)
- High visual density: More action per second, fewer quiet or static beats
- Single narrative thread: ONE clear storyline, NO subplots or tangents
- Punchy pacing: Default to Fast pacing; avoid Slow pacing entirely
- Limited cast: 1-2 characters maximum for clarity in short format
- Strong payoff: End with a clear, satisfying conclusion or twist — completion matters
- Camera energy: Dynamic camera work throughout (tracking, dolly, close-ups)
- Minimal dialogue: Visuals carry the story; dialogue only for impact moments
- Front-loaded conflict: Establish stakes immediately, no slow build-up
""",
            "Visual Art / Abstract": """
INTENT-SPECIFIC GUIDANCE:
- Non-linear: Scenes can be out of chronological order
- Artistic focus: Prioritize visual and thematic elements
- Unconventional structure: Break traditional narrative rules
- Varied pacing: Mix of all pacing types for rhythm
- Symbolic elements: Use visual metaphors and symbols
- Minimal dialogue: Let visuals convey meaning
- Abstract concepts: Focus on themes and emotions over plot
- Seamless transitions: Scenes should flow into each other naturally
- Atmospheric focus: Prioritize mood and imagery over plot
""",
            "General Story": """
INTENT-SPECIFIC GUIDANCE:
- Balanced approach: Mix of pacing, dialogue, and visual elements
- Traditional structure: Follow standard narrative conventions
- Character development: Focus on character arcs and growth
- Plot progression: Clear beginning, middle, and end
- Varied pacing: Appropriate pacing for each scene type
- Balanced dialogue: Mix of dialogue and action scenes
"""
        }
        return intent_guidance_map.get(intent, intent_guidance_map["General Story"])
    
    def _get_ad_storyboard_guidance(self, screenplay: 'Screenplay', scene) -> str:
        """Build advertisement-specific storyboard guidance for a scene."""
        from core.ad_framework import (
            build_ad_storyboard_guidance, get_brand_visual_style
        )
        bc = screenplay.brand_context
        if not bc:
            return ""
        emotional_anchor = getattr(bc, "emotional_anchor", "") or ""
        personality = getattr(bc, "brand_personality", []) or []
        visual_style = get_brand_visual_style(personality)
        ad_beat_type = getattr(scene, "ad_beat_type", "") or ""
        is_reveal = getattr(scene, "is_product_reveal", False)
        is_brand = getattr(scene, "is_brand_hero_shot", False)
        return build_ad_storyboard_guidance(
            brand_context=bc,
            emotional_anchor=emotional_anchor,
            visual_style=visual_style,
            ad_beat_type=ad_beat_type,
            is_product_reveal=is_reveal,
            is_brand_hero_shot=is_brand,
        )
    
    def _calculate_render_cost(self, item: 'StoryboardItem') -> tuple[str, Dict[str, Any]]:
        """Calculate render cost for a storyboard item based on complexity factors.
        
        Returns:
            Tuple of (cost_level, factors_dict) where cost_level is "easy", "moderate", or "expensive"
        """
        import re
        
        factors = {
            "motion_complexity": 0,
            "character_count": 0,
            "environmental_chaos": 0,
            "camera_movement": 0,
            "special_effects": 0
        }
        
        # Combine all text for analysis
        text = f"{item.prompt} {item.image_prompt} {item.camera_notes} {item.visual_description}".lower()
        
        # Motion complexity (action verbs, movement)
        motion_verbs = ['running', 'jumping', 'flying', 'falling', 'dancing', 'fighting', 'chasing', 
                       'climbing', 'swimming', 'diving', 'rolling', 'spinning', 'tumbling', 'sprinting']
        motion_count = sum(1 for verb in motion_verbs if verb in text)
        factors["motion_complexity"] = min(motion_count * 2, 10)  # Cap at 10
        
        # Character count (estimate from text)
        character_indicators = ['character', 'person', 'people', 'crowd', 'group', 'audience', 'mob']
        char_count = sum(1 for ind in character_indicators if ind in text)
        # Look for numbers
        number_match = re.search(r'(\d+)\s*(?:people|characters|persons)', text)
        if number_match:
            char_count = max(char_count, int(number_match.group(1)))
        factors["character_count"] = min(char_count * 2, 10)  # Cap at 10
        
        # Environmental chaos (weather, particles, effects)
        chaos_indicators = ['rain', 'snow', 'fire', 'smoke', 'explosion', 'debris', 'dust', 'particles',
                           'storm', 'wind', 'lightning', 'fog', 'mist', 'sparks', 'embers', 'flames']
        chaos_count = sum(1 for ind in chaos_indicators if ind in text)
        factors["environmental_chaos"] = min(chaos_count * 3, 10)  # Cap at 10
        
        # Camera movement (dynamic camera)
        camera_movements = ['tracking', 'dolly', 'crane', 'pan', 'tilt', 'zoom', 'following', 'orbiting',
                          'rotating', 'moving', 'sweeping', 'gliding', 'circling']
        camera_count = sum(1 for move in camera_movements if move in text)
        factors["camera_movement"] = min(camera_count * 2, 10)  # Cap at 10
        
        # Special effects
        effects_indicators = ['magic', 'glow', 'sparkle', 'shimmer', 'transformation', 'morphing',
                             'teleport', 'portal', 'energy', 'beam', 'laser', 'hologram', 'projection']
        effects_count = sum(1 for ind in effects_indicators if ind in text)
        factors["special_effects"] = min(effects_count * 3, 10)  # Cap at 10
        
        # Multi-shot cluster surcharge
        cluster_id = getattr(item, "cluster_id", None)
        if cluster_id:
            factors["transition_complexity"] = 0
            try:
                from core.multishot_engine import TRANSITION_COMPLEXITY_MAP
                scene = None
                # Locate the parent scene that holds this item
                for act in getattr(self, '_current_screenplay', None) and [] or []:
                    for sc in act.scenes:
                        if any(si.item_id == item.item_id for si in sc.storyboard_items):
                            scene = sc
                            break
                if scene:
                    for cl in getattr(scene, "multishot_clusters", []):
                        if cl.cluster_id == cluster_id:
                            t_scores = [
                                TRANSITION_COMPLEXITY_MAP.get(t.transition_type, 2)
                                for t in cl.transitions
                            ]
                            factors["transition_complexity"] = int(
                                round(sum(t_scores) / max(len(t_scores), 1))
                            )
                            break
            except Exception:
                pass

        # Calculate total score
        total_score = sum(factors.values())
        
        # Determine cost level
        if total_score <= 10:
            cost_level = "easy"
        elif total_score <= 25:
            cost_level = "moderate"
        else:
            cost_level = "expensive"
        
        return cost_level, factors
    
    # ── CINEMATIC BEAT DENSITY — validation and splitting ──────────────────

    def _count_bracketed_objects(self, text: str) -> List[str]:
        """Count [bracketed] object introductions in text."""
        if not text:
            return []
        return re.findall(r'\[([^\]]+)\]', text)
    
    def _count_asterisk_actions(self, text: str) -> List[str]:
        """Count *asterisk* actions in text."""
        if not text:
            return []
        return re.findall(r'\*([^*]+)\*', text)
    
    def _count_primary_action_verbs(self, text: str) -> int:
        """Count distinct primary action verbs in a storyline.
        
        Returns the number of independent primary actions detected.
        """
        if not text:
            return 0
        # Primary action verbs that indicate distinct visual beats
        action_patterns = [
            r'\b(?:steps?|walks?|runs?|enters?|exits?|moves?|approaches?)\b',
            r'\b(?:picks?\s+up|grabs?|pulls?\s+out|reaches?\s+for|takes?|lifts?)\b',
            r'\b(?:opens?|closes?|pushes?|activates?|turns?\s+on|switches?)\b',
            r'\b(?:looks?\s+at|examines?|inspects?|reads?|studies?)\b',
            r'\b(?:speaks?|says?|shouts?|whispers?|calls?)\b',
            r'\b(?:reveals?|discovers?|notices?|spots?|sees?|finds?)\b',
            r'\b(?:adjusts?|twists?|turns?|rotates?|flips?)\b',
            r'\b(?:sits?\s+down|stands?\s+up|kneels?|crouches?|ducks?)\b',
            r'\b(?:throws?|drops?|places?|sets?\s+down|puts?\s+down)\b',
            r'\b(?:reacts?|flinches?|freezes?|gasps?|stumbles?)\b',
        ]
        count = 0
        text_lower = text.lower()
        for pat in action_patterns:
            if re.search(pat, text_lower):
                count += 1
        return count

    def _detect_beat_density_violations(self, storyline: str) -> Dict[str, Any]:
        """Detect cinematic beat density violations in a single storyboard item.
        
        Returns a dict with violation details:
            - 'multi_object': list of bracketed objects if >1
            - 'multi_action': list of asterisk actions if >1
            - 'action_verb_count': number of primary action verbs
            - 'needs_split': True if item should be split
            - 'split_reason': description of why splitting is needed
        """
        result = {
            'multi_object': [],
            'multi_action': [],
            'action_verb_count': 0,
            'needs_split': False,
            'split_reason': ''
        }
        
        if not storyline:
            return result
        
        # Check bracketed objects
        objects = self._count_bracketed_objects(storyline)
        if len(objects) > 1:
            result['multi_object'] = objects
            result['needs_split'] = True
            result['split_reason'] = f"Multiple objects introduced: {', '.join(objects)}"
        
        # Check asterisk actions
        actions = self._count_asterisk_actions(storyline)
        if len(actions) > 1:
            result['multi_action'] = actions
            result['needs_split'] = True
            reason = f"Multiple *actions*: {', '.join(actions)}"
            result['split_reason'] = f"{result['split_reason']}; {reason}" if result['split_reason'] else reason
        
        # Check primary action verb density
        verb_count = self._count_primary_action_verbs(storyline)
        result['action_verb_count'] = verb_count
        if verb_count >= 3 and not result['needs_split']:
            result['needs_split'] = True
            result['split_reason'] = f"High action density ({verb_count} primary verbs)"
        
        # Check for mixed focus: object + action in same item
        if len(objects) >= 1 and verb_count >= 2:
            if not result['needs_split']:
                result['needs_split'] = True
                result['split_reason'] = "Mixed focus: object introduction + multiple character actions"
        
        return result
    
    def _split_storyline_into_beats(self, storyline: str, violations: Dict[str, Any]) -> List[str]:
        """Split a multi-beat storyline into individual visual beats.
        
        Uses sentence boundaries and violation context to determine split points.
        Each returned string represents one dominant visual beat.
        """
        if not storyline:
            return [storyline]
        
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', storyline)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) <= 1:
            # Can't split single sentence further — return as-is
            return [storyline]
        
        # Strategy 1: If multiple bracketed objects, group sentences by object
        if violations.get('multi_object') and len(violations['multi_object']) > 1:
            beats = []
            current_beat = []
            for sent in sentences:
                objs_in_sent = self._count_bracketed_objects(sent)
                if objs_in_sent and current_beat:
                    # New object starts a new beat
                    beats.append(' '.join(current_beat))
                    current_beat = [sent]
                else:
                    current_beat.append(sent)
            if current_beat:
                beats.append(' '.join(current_beat))
            if len(beats) > 1:
                return beats
        
        # Strategy 2: If multiple asterisk actions, each action = one beat
        if violations.get('multi_action') and len(violations['multi_action']) > 1:
            beats = []
            current_beat = []
            for sent in sentences:
                actions_in_sent = self._count_asterisk_actions(sent)
                if actions_in_sent and current_beat:
                    beats.append(' '.join(current_beat))
                    current_beat = [sent]
                else:
                    current_beat.append(sent)
            if current_beat:
                beats.append(' '.join(current_beat))
            if len(beats) > 1:
                return beats
        
        # Strategy 3: High action density — split on sentence boundaries
        # Each sentence gets its own beat (if it has meaningful content)
        if violations.get('action_verb_count', 0) >= 3:
            return [s for s in sentences if len(s) > 10]
        
        # Fallback: split on sentence boundaries
        return [s for s in sentences if len(s) > 10]
    
    def _validate_and_split_beat_density(
        self,
        items: List['StoryboardItem'],
        screenplay: 'Screenplay'
    ) -> Optional[List['StoryboardItem']]:
        """Validate all storyboard items against beat density rules and split violations.
        
        Returns:
            None if no changes needed, or a new list of StoryboardItem objects
            with multi-beat items split into separate items.
        """
        if not items:
            return None
        
        any_split = False
        result_items = []
        
        for item in items:
            violations = self._detect_beat_density_violations(item.storyline)
            
            if not violations['needs_split']:
                result_items.append(item)
                continue
            
            # Item needs splitting
            any_split = True
            print(f"BEAT DENSITY VIOLATION in item {item.sequence_number}: {violations['split_reason']}")
            
            beat_texts = self._split_storyline_into_beats(item.storyline, violations)
            
            if len(beat_texts) <= 1:
                # Could not split further — keep as-is
                result_items.append(item)
                continue
            
            # Create new items from split beats
            for beat_idx, beat_text in enumerate(beat_texts):
                import uuid as _uuid
                new_item = StoryboardItem(
                    item_id=str(_uuid.uuid4()),
                    sequence_number=0,  # Will be re-numbered later
                    duration=3,  # Split items get shorter durations
                    storyline=beat_text.strip(),
                    image_prompt=item.image_prompt if beat_idx == 0 else "",
                    prompt=item.prompt if beat_idx == 0 else "",
                    visual_description="",
                    dialogue=item.dialogue if beat_idx == 0 else "",
                    scene_type=item.scene_type,
                    camera_notes=item.camera_notes if beat_idx == 0 else ""
                )
                # Copy over render cost and drift warnings from original
                new_item.render_cost = item.render_cost
                new_item.render_cost_factors = item.render_cost_factors or {}
                new_item.identity_drift_warnings = item.identity_drift_warnings or []
                result_items.append(new_item)
            
            print(f"  → Split into {len(beat_texts)} items: {[bt[:50] + '...' for bt in beat_texts]}")
        
        if not any_split:
            return None
        
        return result_items
    
    def _detect_identity_drift(self, item: 'StoryboardItem', screenplay: 'Screenplay') -> List[str]:
        """Detect identity inconsistencies by comparing prompts against identity blocks.
        
        Returns:
            List of warning messages about identity drift
        """
        warnings = []
        
        if not screenplay:
            return warnings
        
        # Get approved identity blocks
        approved_blocks = screenplay.get_approved_identity_blocks()
        if not approved_blocks:
            return warnings
        
        # Combine all text for analysis
        text = f"{item.prompt} {item.image_prompt} {item.visual_description}".lower()
        
        # Check each identity block for inconsistencies
        for block_data in approved_blocks:
            entity_id = block_data.get("entity_id", "")
            entity_name = block_data.get("name", "")
            entity_type = block_data.get("type", "")
            identity_block = block_data.get("identity_block", "")
            
            if not identity_block or entity_type != "character":
                continue  # Only check character identity blocks for now
            
            # Extract key attributes from identity block
            identity_lower = identity_block.lower()
            
            # Check for hair color
            hair_colors = ['blonde', 'blond', 'brown', 'black', 'red', 'auburn', 'gray', 'grey', 'white', 'silver']
            identity_hair = None
            for color in hair_colors:
                if color in identity_lower:
                    identity_hair = color
                    break
            
            if identity_hair:
                # Check if prompt mentions different hair color
                text_hair_colors = [c for c in hair_colors if c in text and c != identity_hair]
                if text_hair_colors:
                    warnings.append(f"Possible hair color change for {entity_name}: identity block says '{identity_hair}', but prompt mentions '{text_hair_colors[0]}'")
            
            # Check for clothing inconsistencies (basic check)
            # Look for clothing descriptions in identity block
            clothing_keywords = ['wearing', 'dressed', 'clothing', 'shirt', 'dress', 'jacket', 'pants', 'suit']
            identity_clothing = [kw for kw in clothing_keywords if kw in identity_lower]
            
            if identity_clothing:
                # This is a basic check - could be enhanced
                # For now, just note if character is mentioned but clothing context seems different
                if entity_name.lower() in text:
                    # Character is mentioned - could add more sophisticated checking here
                    pass
            
            # Check for age drift (look for age indicators)
            age_indicators = ['young', 'old', 'elderly', 'teen', 'adult', 'child', 'middle-aged']
            identity_age = [ind for ind in age_indicators if ind in identity_lower]
            
            if identity_age:
                text_age = [ind for ind in age_indicators if ind in text and ind not in identity_age]
                if text_age:
                    warnings.append(f"Possible age description change for {entity_name}: identity suggests '{identity_age[0]}', but prompt mentions '{text_age[0]}'")
            
            # Check for height discrepancies
            height_patterns = [r"(\d+)\s*(?:feet|ft|')\s*(\d+)\s*(?:inches|in|\")", r"(\d+)\s*cm", r"tall|short|height"]
            identity_height = None
            for pattern in height_patterns:
                import re
                match = re.search(pattern, identity_lower)
                if match:
                    identity_height = match.group(0)
                    break
            
            # Basic facial feature check (eye color, etc.)
            eye_colors = ['blue', 'brown', 'green', 'hazel', 'gray', 'grey']
            identity_eyes = None
            for color in eye_colors:
                if color in identity_lower and ('eye' in identity_lower or 'eyes' in identity_lower):
                    identity_eyes = color
                    break
            
            if identity_eyes:
                text_eye_colors = [c for c in eye_colors if c in text and c != identity_eyes and ('eye' in text or 'eyes' in text)]
                if text_eye_colors:
                    warnings.append(f"Possible eye color change for {entity_name}: identity block says '{identity_eyes}', but prompt mentions '{text_eye_colors[0]}'")
        
        return warnings
    
    def _extract_allowed_entities_from_summary(self, scene_summary: str) -> Tuple[List[str], List[str]]:
        """Extract present vs referenced-only entities from scene summary for presence validation.
        
        Returns (present_list, referenced_only_list). Heuristic: plan/target/discuss objects -> referenced_only;
        subject of action or clearly in-scene -> present. Unclear defaults to present to avoid over-restriction.
        """
        if not scene_summary or not scene_summary.strip():
            return ([], [])
        summary_lower = scene_summary.lower()
        referenced_only = []
        present = []
        # Patterns where an entity is the TARGET of a plan/discussion (not present in scene)
        referenced_patterns = [
            r'\bplan\s+to\s+(?:steal|find|rescue|get|take|kidnap|free|capture)\s+([A-Za-z]+)',
            r'\bplanning\s+to\s+(?:steal|find|rescue|get|take|kidnap|free|capture)\s+([A-Za-z]+)',
            r'\bto\s+(?:steal|find|rescue|get|take|kidnap|free|capture)\s+([A-Za-z]+)',
            r'\bobjective\s+is\s+([A-Za-z]+)',
            r'\btarget\s+(?:is\s+)?([A-Za-z]+)',
            r'\bdiscuss\s+([A-Za-z]+)',
            r'\b(?:talk|speak)\s+about\s+([A-Za-z]+)',
            r'\babout\s+([A-Za-z]+)\s+(?:\.|,)',
        ]
        for pat in referenced_patterns:
            for m in re.finditer(pat, scene_summary, re.IGNORECASE):
                name = m.group(1).strip()
                if len(name) > 1 and name.lower() not in ('the', 'a', 'an'):
                    referenced_only.append(name)
        # Patterns where an entity is clearly PRESENT (subject of action or in scene)
        present_patterns = [
            r'\b([A-Z][a-z]+)\s+enters?\b',
            r'\b([A-Z][a-z]+)\s+is\s+(?:in|here|present)',
            r'\b([A-Z][a-z]+)\s+(?:sits|stands|walks|arrives)\b',
            r'\b(?:in\s+the\s+room\s+with|with)\s+([A-Z][a-z]+)\b',
        ]
        for pat in present_patterns:
            for m in re.finditer(pat, scene_summary):
                name = m.group(1).strip()
                if len(name) > 1 and name not in ('The', 'A', 'An'):
                    present.append(name)
        # All other capitalized words (likely character/object names) -> default to present
        all_caps = set(re.findall(r'\b([A-Z][a-z]+)\b', scene_summary))
        skip = {'The', 'She', 'He', 'They', 'It', 'We', 'I', 'A', 'An', 'In', 'To', 'Is', 'As'}
        for name in all_caps:
            if name in skip:
                continue
            if name in referenced_only:
                continue
            if name not in present:
                present.append(name)
        # Deduplicate and remove referenced from present
        referenced_only = list(dict.fromkeys(r for r in referenced_only if r))
        present = [p for p in dict.fromkeys(present) if p and p not in referenced_only]
        return (present, referenced_only)
    
    # Forbidden example names from prompt templates - must NEVER appear in generated content
    # (they are from other stories and cause consistency drift when AI copies them)
    FORBIDDEN_EXAMPLE_LOCATIONS = {
        "midnight falls", "nighttime diner", "city hall", "the warehouse", "abandoned chapel",
        "techno_cave", "the old theater"  # Common AI drifts; never invent these—use story's actual locations
    }
    FORBIDDEN_EXAMPLE_CHARACTERS = {"lucas", "henry", "kaira lin", "alexis", "timmons", "luca", "julia"}

    # Common character name typos/alternates seen in AI output (wrong -> correct)
    CHARACTER_TYPO_MAP = [
        ("Layra", "Lyra"),
        ("Layra's", "Lyra's"),
        ("Lira", "Lyra"),
        ("Timmons", "Timothy"),
        ("TIMMONS", "TIMOTHY"),
    ]

    def _fix_character_typos_in_text(self, text: str, character_names: list) -> str:
        """Fix common character name typos in text (e.g. Layra -> Lyra) when character is in story."""
        if not text or not character_names:
            return text
        # Build set of first names from character registry for validation
        first_names = set()
        for name in character_names:
            parts = (name or "").strip().split()
            if parts:
                first_names.add(parts[0].lower())
        result = text
        for typo, correct in self.CHARACTER_TYPO_MAP:
            if correct.lower() in first_names and typo in result:
                result = re.sub(r'\b' + re.escape(typo) + r'\b', correct, result)
        return result

    def _fix_location_names_in_framework(self, text: str, outline_locations: List[str], story_outline: Dict[str, Any] = None) -> str:
        """Fix non-canonical location names in framework scene descriptions.

        Detects location-like proper nouns in the text that are NOT in the outline's location list
        and attempts to map them to the closest canonical location. For example, if the outline has
        'Abandoned Mill' but the framework says 'Pendergast Mansion', we flag it. We cannot always
        auto-correct (ambiguous), but we CAN catch cases where the invented name shares a surname
        with a character (e.g. 'Pendergast Mansion' for the Pendergast family) and the outline has
        a clear building/place alternative.

        This is a best-effort heuristic fix.
        """
        if not text or not outline_locations:
            return text

        # Build a set of canonical location names (lowered) and their word sets
        canon_lower = {loc.strip().lower() for loc in outline_locations if loc.strip()}

        # Find capitalized multi-word phrases that look like locations (contain a building keyword)
        building_kw = (
            "mansion", "house", "building", "mill", "library", "emporium", "store", "shop",
            "lab", "laboratory", "warehouse", "station", "hub", "apartment", "tower", "castle",
            "palace", "temple", "church", "cathedral", "hospital", "school", "museum", "bar",
            "tavern", "inn", "hotel", "ranch", "farm", "mine", "cave", "cabin", "lodge",
            "prison", "jail", "ruins", "bunker", "base", "camp", "barn", "arena", "stadium",
            "theater", "theatre", "garage", "shed", "cottage", "resort",
        )
        # Pattern: 1+ Title Case words ending with a building keyword
        loc_pattern = re.compile(
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:' + "|".join(re.escape(k) for k in building_kw) + r'))\b',
            re.IGNORECASE,
        )
        result = text
        for m in loc_pattern.finditer(text):
            found_loc = m.group(1).strip()
            if found_loc.lower() in canon_lower:
                continue  # Already canonical
            # Try to find a canonical location with the same building keyword
            found_words = set(found_loc.lower().split())
            found_building_words = found_words & set(building_kw)
            for canon_loc in outline_locations:
                canon_words = set(canon_loc.strip().lower().split())
                canon_building_words = canon_words & set(building_kw)
                if found_building_words & canon_building_words:
                    # Same type of building — replace
                    result = result.replace(found_loc, canon_loc.strip())
                    break
        return result

    def _validate_forbidden_example_names(self, generated_content: str, allowed_locations: set, allowed_characters: set) -> List[str]:
        """Check for forbidden example names that cause drift (AI copying from prompt examples)."""
        warnings = []
        content_lower = generated_content.lower()
        # Check underlined locations in content
        underlined = set(re.findall(r'_([^_]+)_', generated_content))
        for loc in underlined:
            loc_norm = loc.strip().lower()
            if loc_norm in self.FORBIDDEN_EXAMPLE_LOCATIONS and (not allowed_locations or loc_norm not in {a.lower() for a in allowed_locations}):
                warnings.append(f"Forbidden example location detected: _{loc}_ (use location from scene description)")
        # Check FULL CAPS character names (simple word boundary)
        content_upper = generated_content.upper()
        for forbid in self.FORBIDDEN_EXAMPLE_CHARACTERS:
            # Match LUCAS, HENRY as standalone (preceded/followed by non-letter or at boundary)
            pattern = r'\b' + re.escape(forbid.upper()) + r'\b'
            if re.search(pattern, content_upper):
                if not allowed_characters or forbid.upper() not in {a.upper() for a in allowed_characters}:
                    warnings.append(f"Forbidden example character detected: {forbid.upper()} (use characters from scene)")
        return warnings

    def _validate_scene_against_summary(self, scene_summary: str, generated_content: str,
                                        allowed_locations: set = None, allowed_characters: set = None) -> Tuple[bool, List[str]]:
        """Heuristic validation: detect possible new plot elements in generated content vs summary.
        
        Returns (is_consistent, list_of_warnings). Keyword/entity comparison only.
        """
        warnings = []
        if not scene_summary or not generated_content:
            return (True, warnings)
        summary_lower = scene_summary.lower()
        content_lower = generated_content.lower()
        # Check for forbidden example names first (high-priority drift)
        forbid_warnings = self._validate_forbidden_example_names(
            generated_content,
            allowed_locations or set(),
            allowed_characters or set()
        )
        warnings.extend(forbid_warnings)
        # Extract locations from scene summary (_underlined_)
        summary_locations = {m.strip().lower() for m in re.findall(r'_([^_]+)_', scene_summary)}
        # Extract capitalized words (likely names) from summary
        summary_caps = set(re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', scene_summary))
        # Check for locations in content that aren't in summary
        content_underlined = set(re.findall(r'_([^_]+)_', generated_content))
        for loc in content_underlined:
            loc_norm = loc.strip().lower()
            if loc_norm not in summary_locations and (not allowed_locations or loc_norm not in {a.lower() for a in (allowed_locations or set())}):
                if loc_norm not in ("common area", "bridge", "cockpit", "medbay"):  # Generic vehicle interiors
                    warnings.append(f"Location _{loc}_ not in scene description — use only locations from scene summary")
        # Check for FULL CAPS character names in content (screenplay format)
        content_caps = set(re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', generated_content))
        for name in content_caps:
            if name not in summary_caps and name.lower() not in summary_lower:
                if len(name) > 2 and name not in ("The", "She", "He", "They", "It", "We", "I"):
                    if not allowed_characters or name.upper() not in {a.upper() for a in (allowed_characters or set())}:
                        warnings.append(f"Generated content may introduce name/entity not in summary: \"{name}\"")
                        break
        # Simple check: very long content with many more sentences than summary might have drift
        summary_sentences = len(re.findall(r'[.!?]+', scene_summary))
        content_sentences = len(re.findall(r'[.!?]+', generated_content))
        if summary_sentences > 0 and content_sentences > summary_sentences * 8:
            warnings.append("Generated content is much longer than summary; review for narrative drift.")
        return (len(warnings) == 0, warnings)
    
    EXTRAS_KEYWORDS = [
        "guests", "crowd", "audience", "civilians", "passersby", "background people",
        "bystanders", "patrons", "onlookers", "pedestrians", "crowds", "spectators"
    ]

    def _scene_requires_extras(self, scene_summary: str, scene_content: str) -> bool:
        """Determine if scene requires MODE B (environment with extras) from summary and content.
        
        Extras = background-only people (guests, crowd, audience, etc.). If any such reference
        appears, return True so environment uses MODE B; otherwise MODE A (empty).
        """
        text = f"{scene_summary or ''}\n{scene_content or ''}".lower()
        return any(kw in text for kw in self.EXTRAS_KEYWORDS)

    def _is_extras_entity(self, name: str, description: str, entity_type: str) -> bool:
        """True if this entity is an extra (background-only people). Extras must NOT be character blocks."""
        if entity_type and entity_type.lower() != "character":
            return False
        text = f"{name or ''} {description or ''}".lower()
        return any(kw in text for kw in self.EXTRAS_KEYWORDS)
    
    def _is_vehicle_entity(self, name: str, description: str) -> bool:
        """Detect if an entity is a vehicle based on keywords.
        
        Used for validation and reclassification to prevent vehicles from being misclassified as objects.
        """
        text = f"{name} {description}".lower()
        vehicle_keywords = [
            "car", "bike", "bicycle", "motorcycle", "truck", "van", "bus",
            "train", "ship", "boat", "yacht", "aircraft", "plane", "helicopter",
            "spaceship", "starship", "vehicle", "transport", "scooter", "cycle"
        ]
        return any(kw in text for kw in vehicle_keywords)
    
    def _is_location_entity(self, name: str, description: str) -> bool:
        """Detect if an entity is a location/environment based on keywords.
        
        Used for validation and reclassification to prevent locations from being misclassified
        as objects or characters.
        """
        text = f"{name} {description}".lower()
        location_keywords = [
            "room", "apartment", "house", "building", "office", "facility",
            "warehouse", "station", "hub", "lab", "laboratory", "chamber",
            "corridor", "hallway", "lobby", "street", "avenue", "alley",
            "plaza", "square", "park", "bridge", "dock", "port", "terminal",
            "interior", "exterior", "space", "area", "zone",
            # Additional building/place words that were missing
            "mansion", "mill", "library", "emporium", "store", "shop",
            "tower", "castle", "palace", "temple", "church", "cathedral",
            "hospital", "school", "university", "museum", "restaurant",
            "bar", "tavern", "inn", "hotel", "motel", "ranch", "farm",
            "mine", "cave", "forest", "woods", "cabin", "lodge", "resort",
            "prison", "jail", "cemetery", "ruins", "bunker", "base", "camp",
            "barn", "shed", "cottage", "garage", "arena", "stadium",
            "theater", "theatre", "cinema",
        ]
        return any(kw in text for kw in location_keywords)
    
    def _is_place_or_region_entity(self, name: str) -> bool:
        """Detect if a name suggests a place or region (not a character).
        
        Used to filter out region/place names (e.g. Wild West, Downtown) from character extraction.
        """
        text = (name or "").lower()
        place_region_keywords = [
            "west", "east", "north", "south", "region", "district", "downtown",
            "country", "valley", "desert", "frontier", "territory", "town",
            "county", "province", "state", "land", "realm"
        ]
        return any(kw in text for kw in place_region_keywords)
    
    def _is_event_entity(self, name: str) -> bool:
        """Detect if a name suggests an event (not a character).
        
        Used to filter out event names (e.g. Wild West Expo, Festival) from character extraction.
        """
        text = (name or "").lower()
        event_keywords = [
            "expo", "festival", "conference", "convention", "fair", "show",
            "tournament", "competition", "ceremony", "gala", "summit", "rally",
            "carnival", "parade", "exhibition", "symposium", "forum"
        ]
        return any(kw in text for kw in event_keywords)

    def _is_company_or_concept_entity(self, name: str) -> bool:
        """Detect if a name is a company, department, concept, brand, or AI/system (NOT a human character).
        
        Characters must be people. Company names, departments, concepts, brands, and AI/synthetic
        entities (e.g. AEON) must NOT be extracted as CHARACTERS. Used to reject e.g. 'Solutions'
        or 'AEON' as a character.
        """
        if not name or not isinstance(name, str):
            return True
        text = (name or "").strip().lower()
        # AI/synthetic entity names (systems, not human characters)
        ai_entity_names = {"aeon", "nexus", "oracle", "synapse", "cortex", "prime", "omni"}
        if text in ai_entity_names:
            return True
        # Common acronyms (TV show, DVD, etc.) - never character names
        acronyms = {"tv", "dvd", "cd", "pc", "fbi", "cia", "nasa", "usa", "uk", "gps", "ceo",
                    "mvp", "api", "ufo", "hiv", "atm", "dna", "rna", "hq", "vip", "diy", "faq",
                    "pr", "hr", "vp", "pm", "am", "fm", "dc", "ac", "ad", "bc", "id", "os", "vo"}
        if text in acronyms:
            return True
        if len(text) < 2:
            return True
        # Tech-style company names (single word: neurotech, biotech, etc.)
        if " " not in text and (text.endswith("tech") or text.endswith("corp")):
            return True
        tech_company_names = {"neurotech", "synthtech", "biotech", "nanotech", "infotech", "medtech"}
        if text in tech_company_names:
            return True
        # Company / department / org keywords
        company_keywords = [
            "solutions", "systems", "technologies", "industries", "ventures", "group",
            "corp", "corporation", "inc", "llc", "ltd", "co.", "company", "department",
            "division", "team", "unit", "marketing", "sales", "legal", "hr", "finance",
            "operations", "research", "development", "support", "services", "agency",
            "committee", "board", "bureau", "office", "branch"
        ]
        if any(kw in text or text == kw for kw in company_keywords):
            return True
        # Abstract concepts often used as "names" in error
        concept_keywords = [
            "hope", "justice", "freedom", "destiny", "fate", "truth", "honor",
            "victory", "legacy", "future", "past", "present"
        ]
        if text in concept_keywords:
            return True
        # Single word that is clearly not a first name (common false positives)
        if " " not in text and text in ("solutions", "systems", "services", "solutions"):
            return True
        # Software, UI, visual-production, and abstract visual entities — never human characters.
        # Safe in both narrative and advertisement modes because these are never person names.
        # Check against the LAST word of the name (or the full name for multi-word phrases)
        # to avoid false positives like "James Frame" matching "frame".
        _nonperson_tail_words = {
            "interface", "display", "screen", "dashboard", "ui", "gui",
            "sequence", "montage", "animation", "animatic", "graphic", "graphics",
            "logo", "tagline", "subtitle",
            "storyboard", "infographic",
            "webpage", "website", "browser", "notification", "popup",
            "hologram", "projection", "readout", "hud",
        }
        _nonperson_phrases = {
            "title card", "text overlay", "pop-up",
        }
        words = text.split()
        last_word = words[-1] if words else ""
        if last_word in _nonperson_tail_words:
            return True
        if text in _nonperson_phrases:
            return True
        return False

    def _is_narrative_transition(self, name: str) -> bool:
        """Detect if a name is a narrative transition (NOT a character).
        
        Wizard must reject these as characters. Only individual humans may be characters.
        """
        if not name or not isinstance(name, str):
            return True
        text = (name or "").strip().lower()
        transition_keywords = [
            "meanwhile", "suddenly", "later", "then", "finally", "eventually",
            "afterward", "before", "after", "now", "soon", "next", "first", "last"
        ]
        return text in transition_keywords

    def _is_group_or_team(self, name: str) -> bool:
        """Detect if a name is a group, team, or organization (NOT an individual character).
        
        Wizard must reject e.g. 'The City Guardians', 'Ghost Guys Paranormal Investigators'.
        """
        if not name or not isinstance(name, str):
            return True
        text = (name or "").strip().lower()
        group_keywords = [
            "guardians", "team", "crew", "squad", "unit", "force", "band",
            "group", "gang", "circle", "council", "guard", "guards", "troops",
            "investigators", "investigation", "agency", "services", "associates",
            "society", "club", "organization", "organisation", "foundation",
            "institute", "collective", "alliance", "league", "federation",
            "syndicate", "cartel", "network", "guild", "order", "brotherhood",
            "sisterhood", "fraternity", "sorority", "coalition", "union",
            "patrol", "militia", "regiment", "division", "corps", "department",
            "bureau", "commission", "committee", "board", "authority",
        ]
        # Check with "the " prefix
        if text.startswith("the "):
            rest = text[4:].strip()
            if any(rest == w or rest.endswith(" " + w) for w in group_keywords):
                return True
        # Check without "the " prefix (e.g. "GHOST GUYS PARANORMAL INVESTIGATORS")
        if any(text == w or text.endswith(" " + w) for w in group_keywords):
            return True
        # Multi-word names containing group-indicating words anywhere
        words = set(text.split())
        if words & {"guys", "boys", "girls", "brothers", "sisters", "sons", "daughters", "friends", "fellows"}:
            if len(text.split()) >= 3:
                return True
        return False

    def _is_building_or_location(self, name: str) -> bool:
        """Detect if a name is a building or location (NOT a character).
        
        Wizard must reject e.g. 'City Hall', 'The Tower', 'Main Street'.
        """
        if not name or not isinstance(name, str):
            return True
        text = (name or "").strip().lower()
        building_location_keywords = [
            "hall", "tower", "street", "avenue", "road", "building", "house",
            "plaza", "square", "center", "centre", "station", "terminal",
            "city hall", "town hall", "main street", "the tower", "the hall"
        ]
        if any(kw in text or text == kw for kw in building_location_keywords):
            return True
        if text.endswith(" hall") or text.endswith(" tower") or text.endswith(" street"):
            return True
        return False

    def _is_role_or_title_only(self, name: str) -> bool:
        """Detect if a string is a job title/role/description rather than a person's name.

        Characters must have actual names (e.g. Sarah Chen, Marcus Webb). Reject role-only
        strings like 'Former Park Employee', 'The Detective', 'Park Ranger', 'Security Guard'.
        """
        if not name or not isinstance(name, str):
            return True
        text = (name or "").strip()
        if len(text) < 2:
            return True
        lower = text.lower()
        # Prefixes that indicate a role/description, not a name
        if lower.startswith("former ") or lower.startswith("ex ") or lower.startswith("retired "):
            return True
        if lower.startswith("the ") and len(text) > 6:
            # "The Detective", "The Manager" = role; "The Beatles" could be band, reject as person
            rest = lower[4:].strip()
            if rest in ("detective", "manager", "guard", "ranger", "stranger", "captain", "doctor", "nurse", "chief"):
                return True
        # Job/role keywords - if the "name" is or ends with these, it's a title not a person name
        role_keywords = [
            " employee", " ranger", " guard", " manager", " detective", " officer",
            " worker", " assistant", " director", " supervisor", " clerk", " agent",
            " attendant", " keeper", " guide", " driver", " pilot", " nurse",
            " doctor", " captain", " chief", " sergeant", " lieutenant", " park employee",
            " security guard", " park ranger", " maintenance worker"
        ]
        if any(lower.endswith(kw) or lower == kw.strip() for kw in role_keywords):
            return True
        # Multi-word phrases that are clearly roles (e.g. "Park Employee", "Security Guard")
        role_phrases = [
            "park employee", "security guard", "park ranger", "maintenance worker",
            "security officer", "park attendant", "former park", "ex employee"
        ]
        if any(rp in lower for rp in role_phrases):
            return True
        return False

    # Common nickname -> full first name (for merging TIM + TIMOTHY + PARKER into one character)
    _NICKNAME_TO_FIRST = {
        "tim": "timothy", "bill": "william", "bob": "robert", "jim": "james", "mike": "michael",
        "dick": "richard", "rick": "richard", "tom": "thomas", "dan": "daniel", "matt": "matthew",
        "chris": "christopher", "steve": "steven", "dave": "david", "joe": "joseph", "tony": "anthony",
        "nick": "nicholas", "sam": "samuel", "ben": "benjamin", "alex": "alexander", "max": "maxwell",
        "jake": "jacob", "will": "william", "ed": "edward", "fred": "frederick",
        "liz": "elizabeth", "beth": "elizabeth", "lisa": "elizabeth", "kate": "katherine", "kathy": "katherine",
        "sue": "susan", "jen": "jennifer", "jenny": "jennifer", "meg": "margaret", "peggy": "margaret",
    }

    def _is_nickname_of_first_name(self, single_word: str, full_first_name: str) -> bool:
        """Return True if single_word is a known nickname for full_first_name (e.g. TIM for TIMOTHY)."""
        if not single_word or not full_first_name or " " in single_word:
            return False
        sw = single_word.lower().strip()
        ffn = full_first_name.split()[0].lower() if full_first_name else ""
        if sw == ffn:
            return True
        return self._NICKNAME_TO_FIRST.get(sw) == ffn

    def _extract_nickname_from_full_name(self, name: str) -> Optional[str]:
        """Extract quoted nickname from First 'Nickname' Last format, e.g. REBECCA 'REX' STERN -> REX.
        Also supports legacy \"Nickname\" format."""
        if not name or not isinstance(name, str):
            return None
        m = re.search(r'["\']([^"\']+)["\']', name)
        return m.group(1).strip() if m else None

    def _normalize_character_name_for_identity(self, name: str) -> str:
        """Normalize character name for identity matching: strip prefixes like 'A', 'As', 'The', titles.
        
        One human = one CHARACTER identity. 'Victor', 'As Victor', 'Victor Kane' should map
        to the same character. Returns stripped name for matching; full-name matching should
        be done by caller (prefer longest/full name as canonical).
        """
        if not name or not isinstance(name, str):
            return (name or "").strip()
        s = name.strip()
        # Strip leading "As " (e.g. "As Victor" -> "Victor")
        s = re.sub(r"^\s*As\s+", "", s, flags=re.IGNORECASE).strip()
        # Strip leading "The " when it's not "The Something" as a title
        s = re.sub(r"^\s*The\s+", "", s, flags=re.IGNORECASE).strip()
        # Strip leading article "A " (e.g. "A Filmmaker" -> "Filmmaker")
        s = re.sub(r"^\s*A\s+", "", s, flags=re.IGNORECASE).strip()
        # Strip common titles (keep the name part)
        s = re.sub(
            r"^(?:Dr\.|Mr\.|Mrs\.|Ms\.|Miss|Captain|Professor|Prof\.|Lieutenant|Lt\.|"
            r"Sergeant|Sgt\.|General|Gen\.|Colonel|Col\.|Major|Commander|Admiral)\s+",
            "",
            s,
            flags=re.IGNORECASE,
        ).strip()
        return s if s else name.strip()

    def _is_person_name(self, name: str) -> bool:
        """Heuristic: does this look like a human character name (not a location/event/company)?
        
        Used to reclassify: if something was extracted as 'environment' but the name
        looks like a person (e.g. 'Victor Kane'), reclassify to character.
        """
        if not name or not isinstance(name, str):
            return False
        n = name.strip()
        if self._is_place_or_region_entity(n) or self._is_event_entity(n) or self._is_company_or_concept_entity(n):
            return False
        # Reject if any word is a building/place indicator (e.g. "PENDERGAST MANSION")
        if self._is_location_entity(n, ""):
            return False
        # Two words, both capitalized (First Last) is strong signal
        parts = n.split()
        if len(parts) >= 2 and all(p and p[0].isupper() for p in parts if p):
            return True
        # Single word that could be a first name (simple heuristic: not a known non-name)
        if len(parts) == 1 and len(n) > 1 and n[0].isupper():
            return True
        return False

    def _entity_has_interaction_in_text(self, entity_name: str, entity_type: str, text: str) -> bool:
        """Return True if the text shows a character explicitly interacting with this entity.
        
        OBJECT: only when character uses, picks up, activates, breaks, drives, enters, manipulates.
        VEHICLE: only when character enters, drives, rides, or operates the vehicle.
        Used to drop objects/vehicles that are merely described or background.
        """
        if not text or not entity_name or not isinstance(text, str):
            return False
        text_lower = text.lower()
        name_lower = entity_name.strip().lower()
        # Key words from entity name (last 1-2 words often the noun, e.g. "alien artifact", "John's motorcycle")
        name_words = [w for w in re.split(r"[\s']+", name_lower) if len(w) > 1]
        if not name_words:
            return False
        # Use last word or last two words as the referent in the text
        key = name_words[-1] if name_words else ""
        key_two = " ".join(name_words[-2:]) if len(name_words) >= 2 else key
        if entity_type == "object":
            interaction_phrases = [
                "picks up", "picks up the", "uses the", "uses a", "uses his", "uses her",
                "activates", "grabs", "holds the", "holds a", "breaks", "manipulates",
                "grabs the", "takes the", "reaches for", "picks up a", "drops the",
                "in hand", "in his hand", "in her hand"
            ]
        else:
            # vehicle
            interaction_phrases = [
                "drives the", "drives a", "enters the", "enters a", "rides the", "rides a",
                "operates the", "boards the", "boarded the", "gets in the", "gets into the",
                "in the car", "in the truck", "in the vehicle", "on the bike", "on the motorcycle"
            ]
        for phrase in interaction_phrases:
            idx = text_lower.find(phrase)
            if idx == -1:
                continue
            # Check if entity key appears within ~60 chars before or after the phrase
            span = text_lower[max(0, idx - 60) : idx + len(phrase) + 60]
            if key in span or key_two in span:
                return True
        # Also allow entity name (or key) immediately after verb, e.g. "picks up the artifact"
        if entity_type == "object":
            for verb in ["picks up", "uses", "grabs", "holds", "activates", "breaks"]:
                if verb in text_lower and (key in text_lower or key_two in text_lower):
                    return True
        if entity_type == "vehicle":
            for verb in ["drives", "enters", "rides", "boards", "operates"]:
                if verb in text_lower and (key in text_lower or key_two in text_lower):
                    return True
        return False

    # Body-part words that indicate a possessive fragment, not a separate character
    _BODY_PART_WORDS = frozenset({
        "hands", "hand", "face", "eyes", "eye", "fingers", "finger",
        "arm", "arms", "leg", "legs", "feet", "foot", "head", "hair",
        "mouth", "lips", "voice", "body", "back", "shoulder", "shoulders",
        "fist", "fists", "palm", "palms", "grip", "silhouette", "shadow",
        "reflection", "gaze", "profile", "figure", "torso",
    })

    @classmethod
    def _split_possessive_body_part(cls, name: str):
        """If *name* matches ``<owner>'s <body-part>``, return ``(owner, body-part)``.

        Returns ``None`` when the pattern doesn't match.  Works for names like
        ``filmmaker's hands``, ``JAMES'S FACE``, etc.
        """
        m = re.match(r"^(.+?)[''\u2019]s?\s+(\S+)$", name.strip(), re.IGNORECASE)
        if not m:
            return None
        owner, part = m.group(1).strip(), m.group(2).strip().lower()
        if part in cls._BODY_PART_WORDS:
            return (owner, part)
        return None

    def _deduplicate_character_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge duplicate character identities: one human = one CHARACTER block.
        
        Strip prefixes (As, The, titles). Normalize by full-name matching: if 'Victor'
        and 'Victor Kane' exist, keep one entity with the full name. Variations in wording
        must map to the same character.

        Also merges body-part references (``X's hands``) into the parent character ``X``.
        """
        if not entities:
            return entities
        characters = [e for e in entities if isinstance(e, dict) and (e.get("type") or "").lower() == "character"]
        non_characters = [e for e in entities if not (isinstance(e, dict) and (e.get("type") or "").lower() == "character")]
        if not characters:
            return entities

        # --- Phase 0: fold body-part entries into their parent character ------
        # e.g. "filmmaker's hands" → parent "filmmaker"
        body_part_entities = []
        real_characters = []
        for e in characters:
            name = (e.get("name") or "").strip()
            parts = self._split_possessive_body_part(name)
            if parts:
                body_part_entities.append((e, parts[0]))  # (entity, owner_name)
            else:
                real_characters.append(e)

        # Ensure the parent character exists; if not, promote the body-part
        # entry as the parent (using the owner name).
        for bp_entity, owner in body_part_entities:
            owner_norm = self._normalize_character_name_for_identity(owner).lower()
            parent_found = any(
                self._normalize_character_name_for_identity((rc.get("name") or "")).lower() == owner_norm
                for rc in real_characters
            )
            if parent_found:
                try:
                    with open("debug_entity_extraction.log", "a", encoding="utf-8") as f:
                        f.write(f"DEDUPE-BODY: merged '{bp_entity.get('name')}' into parent '{owner}'\n")
                except Exception:
                    pass
            else:
                # Promote: rewrite name to the owner (strip the body part)
                bp_entity["name"] = owner
                real_characters.append(bp_entity)
                try:
                    with open("debug_entity_extraction.log", "a", encoding="utf-8") as f:
                        f.write(f"DEDUPE-BODY: promoted '{owner}' from body-part entry (no parent found)\n")
                except Exception:
                    pass

        characters = real_characters
        # --- end body-part fold -----------------------------------------------

        # Normalize each character name for matching
        def norm(n: str) -> str:
            return self._normalize_character_name_for_identity(n or "").lower().strip()
        def first_name(full: str) -> str:
            p = (full or "").strip().split()
            return p[0].lower() if p else ""
        # Group by: same normalized name, or one is first name of another
        kept = []
        # Prefer full names: sort by length descending so we keep "Victor Kane" over "Victor"
        chars_sorted = sorted(characters, key=lambda e: (-len((e.get("name") or "").strip()), (e.get("name") or "")))
        for entity in chars_sorted:
            name = (entity.get("name") or "").strip()
            n = norm(name)
            if not n:
                kept.append(entity)
                continue
            # Already have this person? (exact match, first name, or nickname of full name)
            is_dup = False
            for k in kept:
                kname = (k.get("name") or "").strip()
                kn = norm(kname)
                if n == kn:
                    is_dup = True
                    break
                if first_name(kname) == n or first_name(name) == kn:
                    is_dup = True
                    break
                if n in kn or kn in n:
                    is_dup = True
                    break
                # Nickname match: REBECCA 'REX' STERN and REX are the same character
                nick = self._extract_nickname_from_full_name(kname)
                if nick and nick.lower() == n and len(name.split()) == 1:
                    is_dup = True
                    break
            if is_dup:
                try:
                    with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                        debug_file.write(f"DEDUPE: merged character '{name}' into existing\n")
                except Exception:
                    pass
                continue
            kept.append(entity)
        return kept + non_characters

    def normalize_and_dedupe_character_names(self, names: List[str]) -> List[str]:
        """Normalize and deduplicate character names: one human = one identity.
        
        Strip prefixes (As, The, titles). If 'Victor', 'As Victor', and 'Victor Kane' appear,
        return a single canonical name (prefer full name 'Victor Kane'). REBECCA 'REX' STERN
        and REX are the SAME character — keep the full name, drop the nickname. Used by outline step.
        """
        if not names:
            return []
        def norm(n: str) -> str:
            return self._normalize_character_name_for_identity(n or "").lower().strip()
        def first_name(full: str) -> str:
            p = (full or "").strip().split()
            return p[0].lower() if p else ""
        def has_quoted_nickname(s: str) -> bool:
            return bool(re.search(r'["\'][^"\']+["\']', s or ""))
        # Sort: prefer full names (with quoted nickname) first, then by length descending
        # This ensures REBECCA 'REX' STERN is kept and REX is dropped as duplicate
        sorted_names = sorted(
            [n.strip() for n in names if n and isinstance(n, str)],
            key=lambda x: (0 if has_quoted_nickname(x) else 1, -len(x), x)
        )
        result = []
        seen_normalized = set()
        for name in sorted_names:
            n = norm(name)
            if not n:
                continue
            is_dup = False
            for kept in result:
                kn = norm(kept)
                if n == kn or first_name(name) == first_name(kept) or n in kn or kn in n:
                    is_dup = True
                    break
                # Nickname match: single word matches quoted nickname in full name (e.g. REX vs REBECCA 'REX' STERN)
                nick = self._extract_nickname_from_full_name(kept)
                if nick and nick.lower() == n and len(name.split()) == 1:
                    is_dup = True
                    break
                # Nickname expansion: single word is known nickname for kept's first name (e.g. TIM vs TIMOTHY or TIMOTHY PARKER)
                if len(name.split()) == 1 and self._is_nickname_of_first_name(name, kept):
                    is_dup = True
                    break
            if not is_dup:
                result.append(name)
        return result

    def sanitize_character_list_for_registry(self, characters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove corporations and merge surname-only duplicates from the character list.
        
        Used before freezing the registry to fix common extraction errors:
        - NEUROTECH (corporation) should not be a character
        - MAYFIELD (surname only) should merge with LUCILLE MAYFIELD
        """
        if not characters or not isinstance(characters, list):
            return list(characters) if characters else []
        # Filter out corporations and non-person entities
        filtered = []
        for c in characters:
            if not isinstance(c, dict) or not c.get("name"):
                continue
            name = str(c.get("name", "")).strip()
            if self._is_company_or_concept_entity(name):
                continue
            filtered.append(c)
        # Sort by name length descending: prefer full names (LUCILLE MAYFIELD before MAYFIELD)
        filtered.sort(key=lambda x: -len(str(x.get("name", "")).strip()))
        result = []
        kept_names = []  # Full names we've kept (for last-name dup check)
        skipped_as_nickname = []  # Names we skipped because they were nickname dups (e.g. TIM)
        for c in filtered:
            name = str(c.get("name", "")).strip()
            key = name.lower()
            if key in (k.lower() for k in kept_names):
                continue
            # Skip if this is surname-only, first-name-only, or nickname duplicate of an existing entry
            words = name.split()
            if len(words) == 1:
                is_surname_dup = any(
                    (k.split()[-1] if " " in k else "").lower() == key
                    for k in kept_names
                )
                if is_surname_dup:
                    continue
                # First-name-only dup: TIMOTHY when we have TIMOTHY PARKER or TIMOTHY 'TIM' PARKER
                first_of_kept = [(k.split()[0] if k.split() else "").lower() for k in kept_names]
                if key in first_of_kept:
                    continue
                # Nickname dup: TIM when we have TIMOTHY or TIMOTHY PARKER (TIM is nickname for TIMOTHY)
                is_nickname_dup = any(
                    self._is_nickname_of_first_name(name, k) for k in kept_names
                )
                if is_nickname_dup:
                    skipped_as_nickname.append((name, c))
                    continue
            kept_names.append(name)
            result.append(c)
        # Merge FIRST + LAST when we dropped a nickname linking them (TIMOTHY, PARKER + skipped TIM -> TIMOTHY PARKER)
        if len(result) >= 2 and skipped_as_nickname:
            single_word_results = [(i, r) for i, r in enumerate(result) if len(str(r.get("name", "")).split()) == 1]
            if len(single_word_results) == 2:
                (i1, r1), (i2, r2) = single_word_results
                n1, n2 = str(r1.get("name", "")).strip(), str(r2.get("name", "")).strip()
                for skipped_name, skipped_dict in skipped_as_nickname:
                    if self._is_nickname_of_first_name(skipped_name, n1) or self._is_nickname_of_first_name(skipped_name, n2):
                        merged_name = f"{n1} {n2}" if i1 < i2 else f"{n2} {n1}"
                        merged = {
                            "name": merged_name,
                            "outline": (r1.get("outline") or "") or (r2.get("outline") or ""),
                            "growth_arc": (r1.get("growth_arc") or "") or (r2.get("growth_arc") or ""),
                            "physical_appearance": (r1.get("physical_appearance") or "") or (r2.get("physical_appearance") or ""),
                        }
                        result = [r for j, r in enumerate(result) if j not in (i1, i2)]
                        result.append(merged)
                        break
        # Final pass: detect characters with overlapping name parts (e.g. QUEEN SERAPHINA / SERAPHINA LIGHTBRINGER)
        result = self._merge_similar_named_characters(result)
        return result

    @staticmethod
    def _names_share_word(name_a: str, name_b: str) -> bool:
        """Return True if two character names share any significant word (3+ chars)."""
        if not name_a or not name_b:
            return False
        # Strip quotes/apostrophes from nickname parts
        clean_a = re.sub(r"['\"]", " ", name_a).upper().split()
        clean_b = re.sub(r"['\"]", " ", name_b).upper().split()
        # Filter out short words (titles like "OF", "THE") and very short tokens
        words_a = {w for w in clean_a if len(w) >= 3}
        words_b = {w for w in clean_b if len(w) >= 3}
        return bool(words_a & words_b)

    def _merge_similar_named_characters(self, characters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect characters with overlapping name parts and keep only the longer/more complete one.
        
        For example, given QUEEN SERAPHINA and SERAPHINA LIGHTBRINGER, both share SERAPHINA.
        This keeps only the first one encountered (preserving original order) and prints a warning.
        """
        if not characters or len(characters) < 2:
            return list(characters) if characters else []
        result = []
        for char in characters:
            if not isinstance(char, dict) or not char.get("name"):
                continue
            name = str(char.get("name", "")).strip()
            is_dup = False
            for kept in result:
                kept_name = str(kept.get("name", "")).strip()
                if self._names_share_word(name, kept_name):
                    print(f"  [name collision] '{name}' shares a name part with '{kept_name}' — skipping '{name}'")
                    is_dup = True
                    break
            if not is_dup:
                result.append(char)
        return result

    def canonicalize_character_names_for_registry(self, names: List[str]) -> List[str]:
        """Canonicalize character names for the Wizard Character Registry: one entry per person.
        
        Merges full name, first name only, last name only, nicknames in quotes, and narrative
        prefixes (e.g. 'As Hank') into a single canonical form. Prefers simpler names (first + last
        without nickname) when both exist; use First 'Nickname' Last sparingly.
        """
        if not names:
            return []
        cleaned = [self._normalize_character_name_for_identity(n or "").strip() for n in names if n and isinstance(n, str)]
        cleaned = [n for n in cleaned if n]
        if not cleaned:
            return []
        # Prefer simpler names (no nickname in quotes) when merging; use nickname format sparingly
        def has_quoted_nickname(s: str) -> bool:
            return bool(re.search(r"[\"'].+[\"']", s))
        def tokenize_for_match(s: str) -> set:
            s_lower = s.lower()
            parts = set(re.split(r"[\s'\"]+", s_lower)) - {""}
            return parts
        # Sort: names WITH quoted nickname first (full form e.g. REBECCA 'REX' STERN), then by length
        # So we keep REBECCA 'REX' STERN and drop REX as duplicate
        sorted_names = sorted(
            cleaned,
            key=lambda x: (0 if has_quoted_nickname(x) else 1, -len(x), x)
        )
        result = []
        for name in sorted_names:
            n_tokens = tokenize_for_match(name)
            if not n_tokens:
                continue
            is_dup = False
            for kept in result:
                k_tokens = tokenize_for_match(kept)
                if n_tokens <= k_tokens or k_tokens <= n_tokens:
                    is_dup = True
                    break
                # Shared significant word (3+ chars) means name collision
                significant_shared = {w for w in (n_tokens & k_tokens) if len(w) >= 3}
                if significant_shared:
                    print(f"  [name collision] '{name}' shares word(s) {significant_shared} with '{kept}' — skipping '{name}'")
                    is_dup = True
                    break
                # Single-word name: check first-name, last-name, nickname match
                if len(name.split()) == 1:
                    n_lower = name.lower()
                    kept_parts = kept.split()
                    if kept_parts and kept_parts[0].lower() == n_lower:
                        is_dup = True
                        break
                    if len(kept_parts) > 1 and kept_parts[-1].lower() == n_lower:
                        is_dup = True
                        break
                    if self._is_nickname_of_first_name(name, kept):
                        is_dup = True
                        break
            if not is_dup:
                result.append(name)
        return result

    def _detect_premise_contradiction(self, premise: str, scene_content: str) -> bool:
        """Heuristic: does scene content suggest an alternate origin or explanation contradicting the premise?
        
        If the Premise states how something works (e.g. origin of powers), the scene must not
        introduce a different origin, cause, or explanation. Returns True if contradiction likely.
        """
        if not premise or not scene_content or not premise.strip():
            return False
        content_lower = scene_content.lower()
        contradiction_phrases = [
            "actually came from", "instead of the", "different origin", "real reason was",
            "wasn't really", "contrary to", "alternative explanation", "another source",
            "came from something else", "not from the", "originated from a different",
            "the real cause", "in fact it was", "turned out to be", "had nothing to do with",
            "despite what", "unlike the", "rather than the", "instead came from"
        ]
        if any(p in content_lower for p in contradiction_phrases):
            return True
        return False

    def _validate_presence_in_scene(self, generated_content: str, allowed_present: List[str], 
                                    referenced_only: List[str]) -> Tuple[bool, List[str]]:
        """Heuristic: detect entities that appear visually in content but are not allowed (referenced-only).
        
        Returns (is_consistent, list_of_warnings). If a referenced_only entity appears in a visual/physical
        context (e.g. 'Cap stood', 'the cage held Cap'), add a warning.
        """
        warnings = []
        if not generated_content or not referenced_only:
            return (True, warnings)
        content_lower = generated_content.lower()
        # Visual/presence indicators: entity appears as subject of action or in a physical description
        for ref in referenced_only:
            ref_lower = ref.lower()
            # Pattern: "Ref stood", "Ref is in", "Ref in the", "the Ref", "Ref's cage" etc
            patterns = [
                rf'\b{re.escape(ref)}\s+(?:stood|stands|sits|sat|walks|walked|enters|entered|is\s+in|was\s+in)\b',
                rf'\b(?:the\s+)?{re.escape(ref)}\s+in\s+(?:the|a)\b',
                rf'\b(?:in|inside)\s+(?:the\s+)?\w*\s*{re.escape(ref)}\b',
                rf'\b(?:cage|room|cell)\s+(?:held|holds|contained)\s+{re.escape(ref)}\b',
            ]
            for pat in patterns:
                if re.search(pat, content_lower, re.IGNORECASE):
                    warnings.append(f"Entity '{ref}' (target of plan / referenced only) appears visually in scene. Do not depict referenced-only entities.")
                    break
        return (len(warnings) == 0, warnings)
    
    def _normalize_scene_beats(self, scene: 'StoryScene') -> List[str]:
        """Normalize scene content into a list of beats/paragraphs.
        
        This method extracts all meaningful paragraphs/beats from either:
        - scene.metadata.get("generated_content") if available
        - scene.description as fallback
        
        Rules:
        - Split by double newlines first (paragraph breaks)
        - If no double newlines, try single newlines
        - Also check for numbered paragraphs (1., 2., etc.) or bullet points
        - Trim empty blocks
        - Preserve original ordering
        - Handle truncated/summarized content by reconstructing from existing storyboard items
        
        Args:
            scene: The scene to normalize
            
        Returns:
            List of beat strings, each representing a paragraph/beat
        """
        # Try generated_content first
        content = ""
        if scene.metadata and isinstance(scene.metadata, dict):
            content = scene.metadata.get("generated_content", "")
        
        # Check if content is truncated or summarized
        is_summary = False
        if content:
            # Check if it's a summary (starts with scene title + colon, or very short with "...")
            if scene.title and content.startswith(scene.title + ":"):
                is_summary = True
            elif len(content) < 200 and "..." in content:
                is_summary = True
            # Also check if it ends with "..." which indicates truncation
            elif content.strip().endswith("..."):
                is_summary = True
        
        # If summary/truncated, try to reconstruct from existing storyboard items
        if is_summary and scene.storyboard_items and len(scene.storyboard_items) > 0:
            reconstructed = []
            for item in scene.storyboard_items:
                if item.storyline and item.storyline.strip():
                    reconstructed.append(item.storyline.strip())
            if reconstructed:
                content = "\n\n".join(reconstructed)
                print(f"DEBUG: Reconstructed content from {len(reconstructed)} existing storyboard items")
        
        # Fallback to description if no generated_content (or reconstruction failed)
        if not content or not content.strip():
            content = scene.description if scene.description else ""
        
        if not content or not content.strip():
            return []
        
        # Normalize line endings
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # First, try splitting by double newlines (paragraph breaks)
        beats = [b.strip() for b in content.split('\n\n') if b.strip()]
        
        # If we got multiple beats from double newlines, use those
        if len(beats) > 1:
            # Filter out very short beats (likely formatting artifacts), but be lenient
            beats = [b for b in beats if len(b) > 5]
            if len(beats) > 0:
                print(f"Extracted {len(beats)} beats from scene using double newline separation")
                return beats
        
        # If no double newlines or only one beat, try single newlines
        beats = [b.strip() for b in content.split('\n') if b.strip()]
        
        # Check if we have numbered paragraphs (1., 2., etc.) or bullet points
        numbered_pattern = r'^\s*\d+[\.\)]\s+'
        bullet_pattern = r'^\s*[-•*]\s+'
        
        # If we find numbered or bulleted items, split on those
        numbered_beats = []
        current_beat = ""
        for line in beats:
            import re
            if re.match(numbered_pattern, line) or re.match(bullet_pattern, line):
                if current_beat:
                    numbered_beats.append(current_beat.strip())
                current_beat = line
            else:
                if current_beat:
                    current_beat += " " + line
                else:
                    current_beat = line
        
        if current_beat:
            numbered_beats.append(current_beat.strip())
        
        if len(numbered_beats) > 1:
            # Filter out very short beats
            numbered_beats = [b for b in numbered_beats if len(b) > 5]
            if len(numbered_beats) > 0:
                print(f"Extracted {len(numbered_beats)} beats from scene using numbered/bullet pattern")
                return numbered_beats
        
        # Fallback: use single newline splits, but filter more aggressively
        # Group consecutive short lines together as they might be part of the same paragraph
        final_beats = []
        current_group = []
        for line in beats:
            if len(line) > 50:  # Substantial line - likely a complete paragraph
                if current_group:
                    final_beats.append(" ".join(current_group).strip())
                    current_group = []
                final_beats.append(line)
            else:  # Short line - might be part of a paragraph
                current_group.append(line)
                # If group gets long enough, treat as a beat
                if len(" ".join(current_group)) > 50:
                    final_beats.append(" ".join(current_group).strip())
                    current_group = []
        
        # Add any remaining group
        if current_group:
            final_beats.append(" ".join(current_group).strip())
        
        # Filter out very short beats
        final_beats = [b for b in final_beats if len(b) > 10]
        
        if len(final_beats) > 0:
            print(f"Extracted {len(final_beats)} beats from scene using line grouping")
            return final_beats
        
        # Last resort: return the entire content as a single beat
        if content.strip():
            print(f"Scene content treated as single beat (could not split into multiple beats)")
            return [content.strip()]
        
        return []
    
    def _determine_compression_strategy(self, scene: 'StoryScene', screenplay: 'Screenplay') -> str:
        """Determine the compression strategy for breaking down a scene into storyboard items.
        
        Strategy options:
        - "montage": Fewer, richer prompts (for fast-paced action or transitions)
        - "beat_by_beat": Many micro-actions (for detailed scenes with dialogue or complex action)
        - "atmospheric_hold": Single extended shot (for slow, atmospheric scenes)
        
        Args:
            scene: The scene to analyze
            screenplay: The screenplay containing the scene
            
        Returns:
            Compression strategy string: "montage", "beat_by_beat", or "atmospheric_hold"
        """
        # Get scene properties
        pacing = scene.pacing.lower() if scene.pacing else "medium"
        plot_point = scene.plot_point.lower() if scene.plot_point else ""
        description = scene.description.lower() if scene.description else ""
        
        # Get screenplay intent
        intent = screenplay.intent.lower() if hasattr(screenplay, 'intent') and screenplay.intent else ""
        
        # Determine strategy based on pacing
        if pacing == "fast":
            # Fast pacing = montage style (fewer, richer prompts)
            return "montage"
        elif pacing == "slow":
            # Slow pacing = atmospheric hold (single extended shot)
            return "atmospheric_hold"
        
        # For medium pacing, check other factors
        
        # Check plot point - transitions and establishing shots often work better as montage
        if any(keyword in plot_point for keyword in ["transition", "establishing", "montage"]):
            return "montage"
        
        # Check description for dialogue-heavy scenes
        dialogue_indicators = ["says", "speaks", "talks", "conversation", "dialogue", "discusses", "asks", "replies"]
        has_dialogue = any(indicator in description for indicator in dialogue_indicators)
        
        # Check for action-heavy scenes
        action_indicators = ["runs", "fights", "chases", "jumps", "attacks", "escapes", "battles", "combat"]
        has_action = any(indicator in description for indicator in action_indicators)
        
        if "advertisement" in intent or "brand film" in intent:
            return "montage"
        
        if "visual art" in intent or "abstract" in intent:
            return "atmospheric_hold"
        
        if "social media" in intent or "short-form" in intent:
            return "montage"
        
        # Default logic for medium pacing
        if has_dialogue and not has_action:
            # Dialogue-heavy scenes = beat by beat (many micro-actions)
            return "beat_by_beat"
        elif has_action and not has_dialogue:
            # Action-heavy scenes = montage (fewer, richer prompts)
            return "montage"
        else:
            # Mixed or unclear = default to beat_by_beat for detailed breakdown
            return "beat_by_beat"
    
    def analyse_novel_text(self, text: str, length: str = "medium", progress_callback=None) -> Dict[str, Any]:
        """Analyse novel/story text and extract cinematic elements for screenplay conversion.

        For short texts (under ~5000 words), sends entire text in one LLM call.
        For longer texts, processes chunks with rolling summaries then synthesises.

        Args:
            text: The full novel/story text.
            length: Target story length (micro, short, medium, long).
            progress_callback: Optional callable(stage_description: str) for progress updates.

        Returns:
            Dict with keys: title, premise, characters (list of dicts), locations (list),
            genres (list), atmosphere, plot_summary.
        """
        if not self._adapter:
            raise Exception("AI client not initialized. Please configure your API key or local AI server in settings.")

        from core.novel_importer import chunk_text, LENGTH_CHARACTER_CAPS, LENGTH_DURATION_LABELS

        max_chars = LENGTH_CHARACTER_CAPS.get(length, 5)
        duration_label = LENGTH_DURATION_LABELS.get(length, "1-3 minutes")
        chunks = chunk_text(text)

        synthesis_prompt = f"""You are a professional screenwriter adapting written fiction for AI-generated video.
Analyse the following text and extract the elements needed for a cinematic screenplay adaptation.

Focus on what is VISUAL and FILMABLE. Omit internal monologue, abstract themes, and literary devices that cannot be shown on screen.
Condense the story to fit a {length} format ({duration_label}).

Extract:
1. A suggested TITLE for the screenplay adaptation
2. A cinematic PREMISE (2-3 sentences focused on visual storytelling — what we SEE happen)
3. Up to {max_chars} MAIN CHARACTERS — for each: name, physical appearance (hair, build, age, clothing), role in the story, and their arc
4. Key LOCATIONS/ENVIRONMENTS — for each: name and brief visual description
5. GENRES that best fit this story (1-3 genres from: Action, Adventure, Comedy, Drama, Fantasy, Horror, Mystery, Romance, Sci-Fi, Thriller, Western, Crime, War, Superhero)
6. ATMOSPHERE/TONE (one word from: Suspenseful, Lighthearted, Dark, Mysterious, Epic, Intimate, Tense, Whimsical, Melancholic, Energetic, Somber, Playful, Gritty, Ethereal, Realistic)
7. PLOT SUMMARY — the major plot beats in chronological order (5-10 beats)

CRITICAL: You MUST return ONLY valid JSON. No markdown, no code blocks, no explanations.

Return this EXACT JSON structure:
{{
    "title": "Suggested screenplay title",
    "premise": "2-3 sentence cinematic premise",
    "characters": [
        {{
            "name": "Character Name",
            "description": "Physical appearance and key traits",
            "role": "Protagonist / Antagonist / Supporting",
            "arc": "Brief character arc description"
        }}
    ],
    "locations": [
        {{
            "name": "Location Name",
            "description": "Brief visual description"
        }}
    ],
    "genres": ["Genre1", "Genre2"],
    "atmosphere": "One-word atmosphere",
    "plot_summary": "5-10 sentence plot summary covering major beats"
}}"""

        if len(chunks) == 1:
            if progress_callback:
                progress_callback("Analysing text...")

            messages = [
                {"role": "system", "content": synthesis_prompt},
                {"role": "user", "content": f"Here is the full text to analyse:\n\n{chunks[0]}"},
            ]
            response = self._chat_completion(messages=messages, temperature=0.4, max_tokens=4000)
            raw = response.choices[0].message.content.strip()
        else:
            # Multi-chunk: rolling summary approach
            running_summary = ""
            for i, chunk in enumerate(chunks):
                if progress_callback:
                    progress_callback(f"Analysing text... (section {i + 1}/{len(chunks)})")

                if i == 0:
                    chunk_prompt = f"""Summarise this section of a longer story, noting:
- Characters introduced (name, appearance, role)
- Locations/settings described
- Key events and plot developments
- Tone and genre indicators

Be thorough but concise. This summary will be used to build a complete screenplay adaptation.

TEXT SECTION {i + 1}/{len(chunks)}:
{chunk}"""
                else:
                    chunk_prompt = f"""Continue analysing the next section of this story.

RUNNING SUMMARY SO FAR:
{running_summary}

Now analyse this next section. Update the running summary with any new characters, locations, events, and developments. Note how the story progresses from what came before.

TEXT SECTION {i + 1}/{len(chunks)}:
{chunk}"""

                messages = [
                    {"role": "system", "content": "You are a story analyst extracting key narrative elements for screenplay adaptation. Return a concise running summary."},
                    {"role": "user", "content": chunk_prompt},
                ]
                response = self._chat_completion(messages=messages, temperature=0.3, max_tokens=3000)
                running_summary = response.choices[0].message.content.strip()

            # Final synthesis pass
            if progress_callback:
                progress_callback("Synthesising analysis...")

            messages = [
                {"role": "system", "content": synthesis_prompt},
                {"role": "user", "content": f"Here is a comprehensive summary of the entire story:\n\n{running_summary}"},
            ]
            response = self._chat_completion(messages=messages, temperature=0.4, max_tokens=4000)
            raw = response.choices[0].message.content.strip()

        # Parse JSON response
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            json_match = re.search(r"\{[\s\S]*\}", raw)
            if json_match:
                result = json.loads(json_match.group())
            else:
                raise Exception("AI returned invalid JSON during text analysis. Please try again.")

        # Validate and fill defaults
        result.setdefault("title", "Untitled Import")
        result.setdefault("premise", "")
        result.setdefault("characters", [])
        result.setdefault("locations", [])
        result.setdefault("genres", ["Drama"])
        result.setdefault("atmosphere", "Realistic")
        result.setdefault("plot_summary", "")

        # Cap character count
        if len(result["characters"]) > max_chars:
            result["characters"] = result["characters"][:max_chars]

        return result

    def generate_story_framework(self, premise: str, title: str = "", length: str = "medium", atmosphere: str = "", genres: List[str] = None, story_outline: Dict[str, Any] = None, intent: str = "General Story", brand_context=None) -> Screenplay:
        """Generate a complete story framework with acts and scenes (Phase 1)."""
        
        if not self._adapter:
            raise Exception("AI client not initialized. Please configure your API key or local AI server in settings.")
        
        # Import workflow profile
        from core.workflow_profile import WorkflowProfileManager, WorkflowProfile
        
        # Get workflow profile
        workflow_profile = WorkflowProfileManager.get_profile(length, intent)
        framework_structure = WorkflowProfileManager.get_framework_structure(workflow_profile, length)
        
        genres = genres or []
        genre_text = ", ".join(genres) if genres else "General"
        atmosphere_text = f"\nAtmosphere/Tone: {atmosphere}" if atmosphere else ""
        
        # Build brand context section for promotional workflows
        brand_info = ""
        if workflow_profile == WorkflowProfile.PROMOTIONAL and brand_context:
            brand_info = "\n\nBRAND / PRODUCT CONTEXT (REQUIRED - USE THIS INFORMATION):\n"
            if brand_context.brand_name:
                brand_info += f"Brand Name: {brand_context.brand_name}\n"
            if brand_context.product_name:
                brand_info += f"Product Name: {brand_context.product_name}\n"
            if brand_context.product_description:
                brand_info += f"Product Description: {brand_context.product_description}\n"
            if brand_context.core_benefit:
                brand_info += f"Core Benefit / Promise: {brand_context.core_benefit}\n"
            if brand_context.target_audience:
                brand_info += f"Target Audience: {brand_context.target_audience}\n"
            if brand_context.brand_personality:
                brand_info += f"Brand Personality: {', '.join(brand_context.brand_personality)}\n"
            if brand_context.mandatory_elements:
                brand_info += f"Mandatory Inclusions: {', '.join(brand_context.mandatory_elements)}\n"
            brand_info += "\nCRITICAL: All visual beats MUST reference the product/brand and incorporate the core benefit. Ensure product presence is consistent throughout.\n"
        
        # Extract location information from story outline for validation
        location_info = ""
        outline_locations = []
        if story_outline and isinstance(story_outline, dict):
            outline_locations = [loc for loc in (story_outline.get("locations", []) or []) if isinstance(loc, str) and loc.strip()]
            if outline_locations:
                location_info = "\n\nCANONICAL LOCATIONS (MUST USE THESE EXACT LOCATIONS):\n"
                for loc in outline_locations:
                    location_info += f"- {loc.strip()}\n"
                location_info += "\nCRITICAL: Scene descriptions MUST use ONLY these locations. Do NOT invent new place names, rename existing locations, or use variants (e.g. do NOT say 'Pendergast Mansion' when the canonical location is 'Abandoned Mill'). Use the EXACT location names listed above."

        # Extract character information from story outline if provided (only for narrative)
        character_info = ""
        if story_outline and isinstance(story_outline, dict):
            characters = story_outline.get("characters", [])
            if characters and isinstance(characters, list):
                character_info = "\n\nCHARACTER DETAILS (MUST USE THESE EXACT CHARACTERS):\n"
                for char in characters:
                    if isinstance(char, dict):
                        char_name = char.get("name", "Unnamed Character")
                        char_outline = char.get("outline", "")
                        char_growth = char.get("growth_arc", "")
                        
                        character_info += f"\n{char_name}:\n"
                        if char_outline:
                            character_info += f"  Character Outline: {char_outline}\n"
                        if char_growth:
                            character_info += f"  Growth Arc: {char_growth}\n"
                
                character_info += "\nCRITICAL: These are MAIN characters with outline and growth arc. You MUST incorporate these exact characters and their development arcs into the story framework. Use their names, backgrounds, motivations, and growth arcs as specified above. Do not replace them with other characters. character_focus in each scene must list only these main characters (when featured). Minor characters may appear in scene descriptions by name and role but do NOT belong in character_focus."
                character_info += "\nOWNERSHIP RULE: If a character is established as the owner of a location (_underlined_), vehicle ({{braces}}), or object ([brackets]), this MUST be strictly enforced throughout the story. No other character may use, operate, or claim ownership of that entity unless the story explicitly transfers ownership."
        
        # Use framework structure from workflow profile
        act_count = framework_structure["act_count"]
        scene_type = framework_structure["scene_type"]
        focus_areas = framework_structure["focus"]
        characters_optional = framework_structure["characters_optional"]
        
        # Calculate scenes per act based on length and profile
        if workflow_profile == WorkflowProfile.PROMOTIONAL:
            scenes_per_act = "3-5" if length == "micro" else "5-8"
            total_scenes = "3-5" if length == "micro" else "5-8"
            description = f"Promotional content ({total_scenes} visual beats, {act_count} act)"
        elif workflow_profile == WorkflowProfile.EXPERIMENTAL:
            scenes_per_act = "3-5" if length == "micro" else "5-8"
            total_scenes = "3-5" if length == "micro" else "5-8"
            description = f"Experimental content ({total_scenes} visual themes, {act_count} act)"
        else:
            # Narrative structure
            length_map = {
                "micro": {"scenes_per_act": "1-5", "total_scenes": "1-5", "description": "Micro story (1-5 scenes, 1 act)"},
                "short": {"scenes_per_act": "3-5", "total_scenes": "9-15", "description": "Short story (9-15 scenes, 3 acts)"},
                "medium": {"scenes_per_act": "5-8", "total_scenes": "15-24", "description": "Medium story (15-24 scenes, 3 acts)"},
                "long": {"scenes_per_act": "6-10", "total_scenes": "30-50", "description": "Long story (30-50 scenes, 5 acts)"}
            }
            length_info = length_map.get(length.lower(), length_map["medium"])
            scenes_per_act = length_info["scenes_per_act"]
            total_scenes = length_info["total_scenes"]
            description = length_info["description"]
        
        # Intent-aware adjustments
        intent_guidance = self._get_intent_guidance(intent)
        
        # Conditional prompt based on workflow profile
        if workflow_profile == WorkflowProfile.PROMOTIONAL:
            # Check if this is structured advertisement mode (micro + advertisement)
            from core.ad_framework import (
                is_advertisement_mode, build_ad_framework_prompt,
                get_brand_visual_style
            )
            if is_advertisement_mode(length, intent) and brand_context:
                # Structured 6-beat micro advertisement mode
                emotional_anchor = getattr(brand_context, "emotional_anchor", "") or ""
                personality = getattr(brand_context, "brand_personality", []) or []
                visual_style = get_brand_visual_style(personality)
                prompt = build_ad_framework_prompt(
                    premise=premise,
                    title=title,
                    atmosphere=atmosphere,
                    brand_context=brand_context,
                    emotional_anchor=emotional_anchor,
                    visual_style=visual_style,
                    story_outline=story_outline,
                )
            else:
                # Generic promotional framework prompt (non-micro or non-advertisement)
                prompt = f"""
You are a professional brand strategist and creative director. Create a visual beat framework for promotional content based on this brand concept:

Brand Concept: {premise}
Title: {title if title else "(none provided — you MUST generate an original, compelling title)"}
Category: {genre_text}
Brand Tone: {atmosphere}
Story Intent: {intent}
{brand_info}
{intent_guidance}

Create a framework with {act_count} act, containing {total_scenes} visual beats.

CRITICAL: This is PROMOTIONAL CONTENT, not a narrative story.
- Focus on VISUAL ACTION and MOOD PROGRESSION
- Each beat should be a visual moment, not a story scene
- Emphasize brand reveal or payoff
- Characters are optional visual elements, not narrative agents
- DO NOT create character arcs, plot progression, or story conflicts
- DO create visual beats that progress emotion and message
- If brand/product context is provided above, ALL visual beats MUST reference the product/brand and incorporate the core benefit
- Ensure product presence is consistent throughout all visual beats
- If mandatory elements are specified, incorporate them naturally into the visual beats

For each visual beat, provide:
1. Beat title
2. Visual description (what the audience sees - 2-3 sentences) - MUST reference product/brand if context provided
3. Emotional tone/mood for this beat
4. Visual action (what happens visually) - MUST showcase product/brand if context provided
5. Pacing: "Fast", "Medium", or "Slow"
6. Estimated duration: 15-30 seconds per beat

CRITICAL: You MUST return ONLY valid JSON. No markdown, no explanations, no code blocks.

TITLE (MANDATORY): The "title" field MUST contain an original, compelling title. If the user provided one, use it. If not, you MUST generate one — NEVER use "Untitled" or leave it blank.

Format your response as a JSON object with this EXACT structure:
{{
    "title": "An original, compelling title (MANDATORY — never 'Untitled')",
    "story_structure": {{
        "core_message": "The central brand message or value proposition",
        "visual_themes": ["Theme 1", "Theme 2"]
    }},
    "acts": [
        {{
            "act_number": 1,
            "title": "Act Title",
            "description": "Description of visual progression in this act",
            "pacing_notes": "Pacing description for this act",
            "scenes": [
                {{
                    "scene_number": 1,
                    "title": "Visual Beat Title",
                    "description": "2-3 sentence visual description of what the audience sees",
                    "plot_point": null,
                    "character_focus": [],
                    "pacing": "Medium",
                    "estimated_duration": 20
                }}
            ]
        }}
    ]
}}
"""
        elif workflow_profile == WorkflowProfile.EXPERIMENTAL:
            # Experimental framework prompt
            prompt = f"""
You are a professional experimental filmmaker. Create a visual theme framework for experimental content based on this concept:

Concept: {premise}
Title: {title if title else "(none provided — you MUST generate an original, compelling title)"}
Themes: {genre_text}
Mood: {atmosphere}

{intent_guidance}

Create a framework with {act_count} act, containing {total_scenes} visual themes.

CRITICAL: This is EXPERIMENTAL/ABSTRACT CONTENT, not a narrative story.
- Focus on MOOD, IMAGERY, and ABSTRACT CONCEPTS
- Each theme should be a visual/mood moment, not a story scene
- Non-linear structure is acceptable
- Characters are optional visual elements
- DO NOT create character arcs, plot progression, or story conflicts
- DO create visual themes that progress mood and atmosphere

For each visual theme, provide:
1. Theme title
2. Visual/mood description (2-3 sentences)
3. Imagery and symbolic elements
4. Pacing: "Fast", "Medium", or "Slow"
5. Estimated duration: 15-30 seconds per theme

TITLE (MANDATORY): The "title" field MUST contain an original, compelling title. If the user provided one, use it. If not, you MUST generate one — NEVER use "Untitled" or leave it blank.

CRITICAL: You MUST return ONLY valid JSON. No markdown, no explanations, no code blocks.

Format your response as a JSON object with this EXACT structure:
{{
    "title": "An original, compelling title (MANDATORY — never 'Untitled')",
    "story_structure": {{
        "concept": "Brief overview of the experimental concept",
        "visual_themes": ["Theme 1", "Theme 2"]
    }},
    "acts": [
        {{
            "act_number": 1,
            "title": "Act Title",
            "description": "Description of mood progression in this act",
            "pacing_notes": "Pacing description for this act",
            "scenes": [
                {{
                    "scene_number": 1,
                    "title": "Visual Theme Title",
                    "description": "2-3 sentence visual/mood description",
                    "plot_point": null,
                    "character_focus": [],
                    "pacing": "Medium",
                    "estimated_duration": 20
                }}
            ]
        }}
    ]
}}
"""
        else:
            # Narrative framework prompt (default)
            prompt = f"""
You are a professional screenwriter and story structure expert. Create a complete story framework for a screenplay based on this premise:

Premise: {premise}
Title: {title if title else "(none provided — you MUST generate an original, evocative title)"}
Genres: {genre_text}
Length: {description}
Story Intent: {intent}{atmosphere_text}{character_info}{location_info}

{intent_guidance}

Create a story framework with {act_count} acts, containing approximately {scenes_per_act} scenes per act (total: {total_scenes} scenes).

For each act, provide:
1. Act title and description
2. Key plot points in this act (e.g., "Inciting Incident", "First Plot Point", "Midpoint", "Climax", "Resolution")
3. Character arcs and development in this act (MUST align with the character growth arcs provided above if characters were specified)
4. Pacing notes (Fast/Medium/Slow)

For each scene within each act, provide:
1. Scene title
2. Scene description (3-5 sentences covering: plot progression, character development, key events)
   - When characters are featured, use their EXACT names as spelled in character details (e.g. Lyra not Layra; Maya not Mya). Reflect their backgrounds, motivations, and growth arcs as specified above.
   - CINEMATIC MARKUP IN SCENE DESCRIPTIONS (MANDATORY):
     * Characters: FULL CAPS on every mention (e.g. CHLOE BAXTER, MARCUS REED — never "Chloe" or "Marcus"). FULL CAPS are EXCLUSIVELY for individual character names — NEVER use FULL CAPS for emphasis, codenames, protocols, operations, programs, labels, warnings, signs, or any non-character phrase. Write these in Title Case instead (e.g. "Terminal Sanction" not "TERMINAL SANCTION").
     * Locations / Environments: _underscored_ on every mention (e.g. _Blackwood Manor_, _Foyer_, _Study_). Rooms within buildings are separate environments.
     * Objects: [brackets] when a character directly interacts with them (e.g. [Ecto-Detector 3000], [phone])
     * Vehicles: {{braces}} when referring to the vehicle exterior (e.g. {{motorcycle}})
   - The scene description must explicitly name the ENVIRONMENT/LOCATION where the scene takes place using _underscored_ markup.
3. Plot point (if applicable): "Inciting Incident", "First Plot Point", "Midpoint", "Climax", "Resolution", or null
4. Character focus: List of MAIN characters (from the character details above) featured in this scene. Use ONLY their exact names (correct spelling). Do NOT add minor/supporting characters here — character_focus is for main characters only.
5. Pacing: "Fast", "Medium", or "Slow"
6. Estimated duration: CRITICAL - Approximate seconds this scene should take (MUST be provided, typically 30-180 seconds)
   - Simple scenes with minimal action: 30-60 seconds
   - Medium complexity scenes with dialogue: 60-120 seconds
   - Complex scenes with multiple events: 120-180 seconds
   - Key dramatic moments: 90-150 seconds
   - This duration is essential for determining how many storyboard items to generate

CRITICAL: You MUST return ONLY valid JSON. No markdown, no explanations, no code blocks.

STORY TITLE (MANDATORY): The "title" field MUST contain an original, evocative title for the story. If the user provided a title, use it exactly. If no title was provided, you MUST generate one — NEVER use "Untitled", "Untitled Story", or leave it blank. The title should be compelling and reflect the story's genre, tone, and central conflict.

Format your response as a JSON object with this EXACT structure:
{{
    "title": "An original, compelling story title (MANDATORY — never 'Untitled')",
    "story_structure": {{
        "overall_plot": "Brief overview of the entire story arc",
        "themes": ["Theme 1", "Theme 2"],
        "character_arcs": {{
            "Character Name": "Brief description of their arc throughout the story"
        }}
    }},
    "acts": [
        {{
            "act_number": 1,
            "title": "Act 1 Title",
            "description": "Description of what happens in this act",
            "plot_points": ["Plot point 1", "Plot point 2"],
            "character_arcs": {{
                "Character Name": "Their development in this act"
            }},
            "pacing_notes": "Pacing description for this act",
            "scenes": [
                {{
                    "scene_number": 1,
                    "title": "Scene Title",
                    "description": "3-5 sentence description with cinematic markup: CHARACTER NAMES IN CAPS, _locations underscored_, [objects in brackets], {{vehicles in braces}}",
                    "plot_point": "Inciting Incident" or null,
                    "character_focus": ["Character 1", "Character 2"],
                    "pacing": "Medium",
                    "estimated_duration": 60
                }}
            ]
        }}
    ]
}}

IMPORTANT JSON RULES:
- Every property must be followed by a comma EXCEPT the last property in an object
- Every array item must be followed by a comma EXCEPT the last item
- All string values must be properly quoted and escaped
- No trailing commas before closing braces or brackets
- Ensure proper nesting of all brackets and braces
- Use null (not "null" as string) for optional plot_point when not applicable

CRITICAL REQUIREMENT FOR ESTIMATED DURATION:
- EVERY scene MUST have an "estimated_duration" field with a positive integer value (typically 30-180 seconds)
- This duration is ESSENTIAL for storyboard generation - it determines how many storyboard items will be created
- DO NOT set estimated_duration to 0 or omit it
- Base the duration on:
  * Scene complexity (simple = 30-60s, complex = 90-180s)
  * Amount of dialogue (more dialogue = longer duration)
  * Pacing (fast = shorter, slow = longer)
  * Number of events in the scene (more events = longer duration)
- Examples: Simple establishing shot = 30-45s, Dialogue scene = 60-90s, Action sequence = 90-120s, Climactic scene = 120-180s

Create a complete, well-structured story framework that tells the story from beginning to end.
Make sure scenes flow naturally and build toward key plot points.
Ensure EVERY scene has a valid estimated_duration value.
"""
        
        try:
            # Use higher max_tokens for framework generation (framework can be very long)
            framework_max_tokens = max(self.model_settings["max_tokens"], 8000)
            
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You are a professional screenwriter and story structure expert specializing in creating detailed story frameworks with acts, scenes, plot points, and character arcs."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.model_settings["temperature"],
                max_tokens=framework_max_tokens
            )
            
            content = response.choices[0].message.content
            
            # Check if response was truncated
            finish_reason = response.choices[0].finish_reason if hasattr(response.choices[0], 'finish_reason') else None
            if finish_reason == 'length':
                # Response was truncated - try to extract what we can
                print(f"Warning: AI response was truncated (max_tokens: {framework_max_tokens}). Consider increasing max_tokens in settings.")
            
            # Try to extract and parse JSON from the response
            framework_data = self._extract_and_parse_json(content)
            
            # Create Screenplay object — prefer AI-generated title, then user title, then premise-derived
            ai_title = framework_data.get("title", "")
            _untitled = {"untitled", "untitled story", "untitled brand content", "untitled experimental"}
            if ai_title and ai_title.strip().lower() not in _untitled:
                final_title = ai_title.strip()
            elif title and title.strip():
                final_title = title.strip()
            else:
                final_title = premise[:60].strip().rstrip(".") if premise else "My Story"
            screenplay = Screenplay(
                title=final_title,
                premise=premise
            )
            screenplay.genre = genres
            screenplay.atmosphere = atmosphere
            screenplay.intent = intent
            screenplay.story_length = length
            screenplay.story_structure = framework_data.get("story_structure", {})
            screenplay.framework_complete = True
            
            # Preserve story_outline if provided (don't overwrite it)
            if story_outline and isinstance(story_outline, dict):
                screenplay.story_outline = story_outline.copy()  # Make a copy to preserve original
            
            # Create acts and scenes
            for act_data in framework_data.get("acts", []):
                act = StoryAct(
                    act_number=act_data["act_number"],
                    title=act_data.get("title", f"Act {act_data['act_number']}"),
                    description=act_data.get("description", ""),
                    plot_points=act_data.get("plot_points", []),
                    character_arcs=act_data.get("character_arcs", {}),
                    pacing_notes=act_data.get("pacing_notes", "")
                )
                
                # Create scenes for this act
                for scene_data in act_data.get("scenes", []):
                    # Get estimated duration and validate it
                    estimated_duration = scene_data.get("estimated_duration", 0)
                    # If duration is 0 or invalid, estimate based on pacing and scene description
                    if estimated_duration <= 0:
                        # Estimate based on pacing
                        pacing = scene_data.get("pacing", "Medium")
                        if pacing == "Fast":
                            estimated_duration = 45  # Fast scenes are shorter
                        elif pacing == "Slow":
                            estimated_duration = 90  # Slow scenes are longer
                        else:
                            estimated_duration = 60  # Medium scenes default to 60 seconds
                        
                        # Adjust based on description length (more description = more complex = longer)
                        description = scene_data.get("description", "")
                        if len(description) > 300:  # Long description suggests complex scene
                            estimated_duration = int(estimated_duration * 1.5)
                        elif len(description) < 100:  # Short description suggests simple scene
                            estimated_duration = int(estimated_duration * 0.75)
                    
                    # Ensure duration is reasonable (between 30 and 180 seconds)
                    estimated_duration = max(30, min(180, estimated_duration))
                    
                    description = scene_data.get("description", "")
                    title = scene_data.get("title", f"Scene {scene_data['scene_number']}")
                    char_focus = scene_data.get("character_focus", [])
                    # Fix character name typos in description/title/character_focus (e.g. Layra -> Lyra)
                    if story_outline and isinstance(story_outline, dict):
                        chars = story_outline.get("characters", []) or []
                        char_names = [c.get("name", "") for c in chars if isinstance(c, dict) and c.get("name")]
                        description = self._fix_character_typos_in_text(description, char_names)
                        title = self._fix_character_typos_in_text(title, char_names)
                        char_focus = [self._fix_character_typos_in_text(n or "", char_names).strip() or n for n in (char_focus or [])]
                    
                    # Fix location names in scene descriptions (e.g. "Pendergast Mansion" -> "Abandoned Mill")
                    if outline_locations:
                        description = self._fix_location_names_in_framework(description, outline_locations, story_outline)
                        title = self._fix_location_names_in_framework(title, outline_locations, story_outline)
                    scene = StoryScene(
                        scene_id=str(uuid.uuid4()),
                        scene_number=scene_data["scene_number"],
                        title=title,
                        description=description,
                        plot_point=scene_data.get("plot_point"),
                        character_focus=char_focus,
                        pacing=scene_data.get("pacing", "Medium"),
                        estimated_duration=estimated_duration
                    )
                    # Advertisement mode fields
                    if scene_data.get("ad_beat_type"):
                        scene.ad_beat_type = scene_data["ad_beat_type"]
                    if scene_data.get("is_product_reveal"):
                        scene.is_product_reveal = bool(scene_data["is_product_reveal"])
                    if scene_data.get("is_brand_hero_shot"):
                        scene.is_brand_hero_shot = bool(scene_data["is_brand_hero_shot"])
                    act.add_scene(scene)
                
                screenplay.add_act(act)
            
            # Validate that all scenes have valid estimated durations
            all_scenes = screenplay.get_all_scenes()
            scenes_without_duration = [s for s in all_scenes if s.estimated_duration <= 0]
            if scenes_without_duration:
                # Fix any scenes that still have 0 duration
                for scene in scenes_without_duration:
                    # Estimate based on pacing
                    if scene.pacing == "Fast":
                        scene.estimated_duration = 45
                    elif scene.pacing == "Slow":
                        scene.estimated_duration = 90
                    else:
                        scene.estimated_duration = 60
                    
                    # Adjust based on description length
                    if len(scene.description) > 300:
                        scene.estimated_duration = int(scene.estimated_duration * 1.5)
                    elif len(scene.description) < 100:
                        scene.estimated_duration = int(scene.estimated_duration * 0.75)
                    
                    # Ensure reasonable bounds
                    scene.estimated_duration = max(30, min(180, scene.estimated_duration))
            
            # ── Advertisement mode: post-generation validation ──
            if screenplay.is_advertisement_mode():
                from core.ad_framework import validate_pre_generation
                ad_result = validate_pre_generation(all_scenes)
                if ad_result.warnings:
                    screenplay.metadata["ad_validation_warnings"] = ad_result.warnings
                if not ad_result.passed:
                    screenplay.metadata["ad_validation_errors"] = ad_result.errors
            
            return screenplay
                
        except Exception as e:
            error_message = str(e)
            raise Exception(f"Failed to generate story framework: {error_message}")
    
    def _build_story_settings_directives(self, screenplay: Screenplay) -> str:
        """Build prompt directives from per-project story_settings."""
        ss = getattr(screenplay, "story_settings", None)
        if not ss:
            return ""

        parts: list[str] = []

        # --- Cinematic controls ---
        aspect = ss.get("aspect_ratio", "16:9")
        parts.append(f"TARGET ASPECT RATIO: {aspect}. Frame all compositions for a {aspect} canvas.")

        density = ss.get("cinematic_beat_density", "balanced")
        density_map = {
            "sparse": "Use SPARSE beat density: fewer story beats per scene, longer contemplative moments, slow pacing.",
            "balanced": "Use BALANCED beat density: standard cinematic rhythm with a natural mix of action and pause.",
            "dense": "Use DENSE beat density: rapid-fire beats, trailer-like pacing, minimal pause between actions.",
        }
        parts.append(density_map.get(density, density_map["balanced"]))

        cam = ss.get("camera_movement_intensity", "subtle")
        cam_map = {
            "static": "CAMERA MOVEMENT: Static / locked-off. Prefer tripod-locked compositions with minimal movement.",
            "subtle": "CAMERA MOVEMENT: Subtle. Gentle push-ins, slow pans, restrained dollies.",
            "dynamic": "CAMERA MOVEMENT: Dynamic. Tracking shots, crane moves, sweeping orbits.",
            "frenetic": "CAMERA MOVEMENT: Frenetic. Handheld energy, whip-pans, rapid repositioning.",
        }
        parts.append(cam_map.get(cam, cam_map["subtle"]))

        lock = ss.get("identity_lock_strength", "standard")
        lock_map = {
            "relaxed": "IDENTITY LOCK: Relaxed. Maintain broad consistency but allow creative variation in character and entity descriptions.",
            "standard": "IDENTITY LOCK: Standard. Reproduce identity block descriptions faithfully with minor adaptive phrasing.",
            "strict": "IDENTITY LOCK: Strict. Reproduce identity block descriptions VERBATIM. Zero creative deviation.",
        }
        parts.append(lock_map.get(lock, lock_map["standard"]))

        fmt = ss.get("prompt_output_format", "cinematic_script")
        fmt_map = {
            "cinematic_script": "PROMPT FORMAT: Cinematic script -- rich prose-style direction with descriptive detail.",
            "shot_list": "PROMPT FORMAT: Shot list -- concise numbered shot breakdowns with technical cues.",
            "director_notes": "PROMPT FORMAT: Director notes -- terse, technical directions only.",
        }
        parts.append(fmt_map.get(fmt, fmt_map["cinematic_script"]))

        # --- Audio settings ---
        audio = ss.get("audio_settings", {})

        dlg = audio.get("dialogue_generation_mode", "generate")
        if dlg == "disabled":
            parts.append("DIALOGUE: DISABLED. Do NOT generate any spoken dialogue lines. Visual-only scenes.")
        elif dlg == "script_only":
            parts.append("DIALOGUE: Script only. Write dialogue text but do NOT include audio direction cues.")

        sfx = audio.get("sfx_density", "cinematic")
        sfx_map = {
            "minimal": "SFX DENSITY: Minimal. Only essential sound effects (impacts, doors, engines).",
            "cinematic": "SFX DENSITY: Cinematic. Layer environmental ambience and interaction SFX naturally.",
            "high_impact": "SFX DENSITY: High-impact. Dense SFX layering for trailer-style intensity.",
        }
        parts.append(sfx_map.get(sfx, sfx_map["cinematic"]))

        music = audio.get("music_strategy", "ambient")
        music_map = {
            "none": "MUSIC: None. Do NOT inject any music direction cues.",
            "ambient": "MUSIC: Ambient bed. Include low-intensity background tone direction where appropriate.",
            "thematic": "MUSIC: Thematic score. Include recurring musical motif cues tied to story themes.",
            "full_cinematic": "MUSIC: Full cinematic score. Include dynamic music cue progression aligned with beat density.",
        }
        parts.append(music_map.get(music, music_map["ambient"]))

        return "\n\nSTORY SETTINGS DIRECTIVES (apply to ALL items):\n" + "\n".join(f"- {p}" for p in parts) + "\n"

    # ── CHUNKED STORYBOARD HELPERS ──────────────────────────────────────

    def _build_storyboard_chunk_prompt(
        self,
        scene_beats: list,
        chunk_start: int,
        chunk_end: int,
        total_beat_count: int,
        num_items: int,
        shared_ctx: dict,
        is_chunked: bool,
    ) -> str:
        """Build the AI prompt for a single chunk of scene beats.

        When the scene has more beats than STORYBOARD_CHUNK_SIZE, the caller
        splits the beats into chunks and calls this once per chunk.  The prompt
        includes only the beats in [chunk_start, chunk_end) and asks for
        exactly (chunk_end - chunk_start) items.

        When *is_chunked* is False the prompt is identical to the original
        monolithic prompt (all beats included).
        """
        chunk_beat_count = chunk_end - chunk_start

        if is_chunked and scene_beats:
            chunk_beats = scene_beats[chunk_start:chunk_end]
            beat_sections = []
            for i, beat in enumerate(chunk_beats):
                global_idx = chunk_start + i + 1
                beat_sections.append(f"BEAT {global_idx}:\n{beat}\n")
            scene_reference_block = (
                f"\nScene Content (Source Material — BEATS {chunk_start + 1}–{chunk_end} of {total_beat_count}):\n\n"
                + chr(10).join(beat_sections)
                + f"\nScene Summary: {shared_ctx.get('scene_reference_full', '').split('Scene Summary:')[-1].strip() if 'Scene Summary:' in shared_ctx.get('scene_reference_full', '') else ''}\n"
            )
            item_count_for_prompt = chunk_beat_count
            mapping_note = (
                f"This is chunk {chunk_start // (chunk_end - chunk_start) + 1}: "
                f"beats {chunk_start + 1}–{chunk_end} of the full {total_beat_count}-beat scene.\n"
                f"Create EXACTLY {chunk_beat_count} storyboard items for these beats.\n"
                f"Sequence numbers MUST start at {chunk_start + 1} and end at {chunk_end}.\n"
            )
        else:
            scene_reference_block = shared_ctx["scene_reference_full"]
            item_count_for_prompt = num_items if total_beat_count == 0 else total_beat_count
            mapping_note = ""

        ctx = shared_ctx
        atmosphere = ctx["atmosphere"]
        has_brand = ctx["has_brand"]
        dialogue_disabled = ctx["dialogue_disabled"]
        has_scene_content = ctx["has_scene_content"]
        estimated_duration = ctx["estimated_duration"]

        storyline_guidance = ""
        if total_beat_count > 0:
            storyline_guidance = (
                f"⚠️ CRITICAL: STRICT 1:1 MAPPING. "
                f"For each BEAT N in the SCENE CONTENT above, create one storyboard item with sequence_number = N. "
                f"Extract ONLY the dialogue, actions, and descriptions from that beat. "
                f"Convert to present-tense cinematic action. "
                f"EXACTLY {chunk_beat_count} items required. "
                f"Reference ONLY entities from the corresponding paragraph. "
            )
        elif has_scene_content:
            storyline_guidance = (
                "⚠️ CRITICAL: The storyline MUST be based EXCLUSIVELY on the FULL SCENE CONTENT provided above. "
                "Include ONLY the exact dialogue from the full scene content if characters are speaking in this moment. "
                "DO NOT add dialogue that isn't in the provided content. DO NOT add actions or events that aren't explicitly described. "
                "DO NOT create generic storylines - use the actual content from the full scene. "
                "MOST IMPORTANTLY: Preserve EXACT details from the scene content. "
                "DO NOT substitute, change, or alter specific objects, items, or details mentioned in the scene content. "
            )
        else:
            storyline_guidance = 'Example: "The protagonist enters the dimly lit room, cautiously looking around."'

        video_prompt_guidance = ""
        if total_beat_count > 0:
            video_prompt_guidance = (
                f"⚠️ CRITICAL: STRICT 1:1 MAPPING. For each item, extract ONLY actions, dialogue, descriptions "
                f"from its corresponding BEAT. Reference ONLY entities visible in that paragraph — no cross-paragraph contamination. "
            )
        elif has_scene_content:
            video_prompt_guidance = (
                "⚠️ CRITICAL: Reference ONLY the FULL SCENE CONTENT provided above. "
                "CRITICAL FOR CONTINUITY: Use the EXACT same objects, items, and details mentioned in the scene content. "
                "DO NOT add any actions, movements, or events that aren't explicitly described in the provided scene content. "
            )

        brand_image_note = (
            "CRITICAL: If brand/product context is provided above, the image prompt should describe the scene BEFORE the product/brand appears (if it's a reveal)."
            if has_brand else ""
        )
        brand_video_note = (
            "CRITICAL: If brand/product context is provided above, the video prompt MUST showcase the product/brand in action."
            if has_brand else ""
        )
        dialogue_note = (
            " (SKIP — dialogue generation is DISABLED for this project; set dialogue to empty string)"
            if dialogue_disabled else ""
        )

        beat_mapping_block = ""
        if total_beat_count > 0:
            beat_mapping_block = (
                f"\n⚠️ STRICT 1:1 PARAGRAPH MAPPING ⚠️\n"
                f"Create EXACTLY {chunk_beat_count} storyboard items.\n"
                f"Each item references ONLY entities from its source paragraph.\n"
            )

        # Visual Art mode guidance (looping vs progressive)
        visual_art_guidance = ""
        if ctx.get("is_visual_art"):
            va_style = ctx.get("visual_art_style", "progressive")
            if va_style == "looping":
                visual_art_guidance = """
VISUAL ART MODE — SEAMLESS LOOP:
This is an abstract visual art piece designed to loop seamlessly.
- The FINAL frame must visually return to the OPENING state so the video can repeat without a visible cut.
- Plan motion as a cycle: the environment, lighting, and atmosphere must transition back to their starting conditions by the end.
- Avoid linear progression that ends in a different state — instead use circular or oscillating motion (e.g. light fading then returning, elements drifting then resettling, camera orbiting back to its origin).
- The video prompt MUST explicitly describe the return to the starting state (e.g. "...gradually returning to the initial soft amber glow as the mist resettles").
- No dialogue. No characters. Focus on environment, light, texture, and mood.
"""
            else:
                visual_art_guidance = """
VISUAL ART MODE — PROGRESSIVE:
This is an abstract visual art piece that evolves and transforms over its duration.
- The visual should progress through a mood or atmospheric arc — a clear transformation from the opening state to a different ending state.
- Build a sense of visual journey: shifting light, evolving textures, emerging or dissolving elements, changing colour temperature.
- Each storyboard item should advance the transformation, not repeat the same static frame.
- No dialogue. No characters. Focus on environment, light, texture, and mood.
"""

        prompt = f"""
You are a professional storyboard artist and screenwriter. Create detailed storyboard items for this scene.

SOURCE OF TRUTH: Hierarchy is (1) Premise, (2) Story Structure, (3) Scene Content, (4) Storyboard. Lower layers must not contradict higher layers. Do not invent new story content.

Scene: {ctx["scene_title"]}
{scene_reference_block}{ctx["instructions_section"]}Plot Point: {ctx["plot_point"]}
Character Focus: {ctx["character_focus"]}
Pacing: {ctx["pacing"]}
Estimated Duration: {estimated_duration} seconds
Genres: {ctx["genre_text"]}{ctx["atmosphere_text"]}{ctx["brand_info"]}{ctx["story_settings_text"]}
{ctx["ad_guidance"]}{visual_art_guidance}
Context (previous scenes):
{ctx["context_text"]}

{ctx["requirement_section"]}

{mapping_note}ABSOLUTELY CRITICAL — STRICT 1:1 PARAGRAPH MAPPING:
{f'- The "storyboard_items" array MUST contain EXACTLY {item_count_for_prompt} items (one per paragraph).' if total_beat_count > 0 else f'- The "storyboard_items" array MUST contain AT LEAST {item_count_for_prompt} items.'}
- Each item references ONLY entities from its corresponding paragraph
- Items MUST progress chronologically through the scene
- NO DUPLICATE ITEMS — each item must be distinct and correspond to its paragraph
- Do NOT introduce entities from other paragraphs (cross-paragraph contamination is forbidden)

For each storyboard item, you must:
1. Choose the optimal duration in whole seconds (1-30) based on content:
   - Quick cuts, reaction shots, transitions = 2-3 seconds
   - Fast action beats = 3-5 seconds
   - Standard action or dialogue = 5-8 seconds
   - Complex scenes with extended dialogue = 8-12 seconds
   - Key dramatic moments, reveals = 6-10 seconds
   - Establishing/atmospheric shots = 3-6 seconds

2. Create a STORYLINE description (1-3 sentences):
   - ONE action, ONE reveal, or ONE reaction — never multiple
   - {storyline_guidance}

3. Create a COMPOSITION PROMPT for the start frame image:
   - Describe the camera shot type and what is visible in the frame
   - Reference characters, vehicles, objects, and environments BY NAME ONLY
   - Include their placement and any action (e.g. "kneeling", "standing at the doorway")
   - Do NOT include physical descriptions, clothing, lighting, atmosphere, or style
   - The image generator already has reference images for each entity — only describe composition
   - Use ONLY elements mentioned in THIS paragraph/beat
   - Example: "Wide shot of ELARA VANDERMERE kneeling in the fields of Briar's Hollow, her hands in the soil"
   - Example: "Close-up of MAELIS THORNE clutching a yellowed scroll, eyes wide"

4. Create a comprehensive VIDEO PROMPT for higgsfield.ai video generation:
   - {video_prompt_guidance}
   - MUST explicitly describe ALL motion and dynamic changes
   - Use explicit action verbs: walking, running, appearing, revealing, forming, emerging, etc.
   - Include detailed visual description, camera angles, lighting, composition
   - Describe ONLY what is seen: visual action, camera, composition. No music or sound design.
   - {brand_video_note}

5. Generate dialogue if characters are speaking{dialogue_note}
6. Provide detailed camera movement notes

CRITICAL: visual_description must be an empty string (""). You MUST return ONLY valid JSON.

Format your response as a JSON object with this EXACT structure:
{{
    "storyboard_items": [
        {{
            "sequence_number": {chunk_start + 1},
            "duration": 5,
            "storyline": "Narrative description of what happens.",
            "image_prompt": "Static establishing shot description.",
            "prompt": "Video generation prompt with explicit actions.",
            "visual_description": "",
            "dialogue": "Character: Dialogue text here",
            "scene_type": "action",
            "camera_notes": "Camera movement description."
        }}
    ]
}}

🚨 CRITICAL: Create EXACTLY {item_count_for_prompt} items. {"Sequence numbers " + str(chunk_start + 1) + "–" + str(chunk_end) + "." if is_chunked else ""}
{beat_mapping_block}
⚠️ FINAL REMINDER ⚠️
YOU ARE A TRANSCRIPTION TOOL — NOT A CREATIVE WRITER.
- Extract and represent ONLY what is in the provided SCENE CONTENT
- DO NOT add new events, actions, dialogue, details, or entities
- Each item MUST reference ONLY entities from its corresponding paragraph

IMPORTANT JSON RULES:
- Every property must be followed by a comma EXCEPT the last property in an object
- Every array item must be followed by a comma EXCEPT the last item
- All string values must be properly quoted and escaped
- No trailing commas before closing braces or brackets
"""
        return prompt

    def _salvage_truncated_storyboard_items(
        self,
        raw_content: str,
        parsed_items: list,
        expected_count: int,
    ) -> list | None:
        """Try to recover complete items from a truncated AI response.

        If the AI response was cut off mid-JSON, ``_extract_and_parse_json``
        may have already recovered *some* items.  This method checks whether
        the last item looks incomplete (e.g. missing required fields) and drops
        it so the rest can proceed.  Returns *None* if no salvaging was needed.
        """
        if not parsed_items:
            return None

        required_fields = {"storyline", "prompt", "image_prompt"}

        last_item = parsed_items[-1]
        last_is_truncated = False
        for field in required_fields:
            val = last_item.get(field)
            if val is None:
                last_is_truncated = True
                break
            if isinstance(val, str) and len(val.strip()) < 5:
                last_is_truncated = True
                break

        if not last_is_truncated and len(parsed_items) >= expected_count:
            return None

        finish_reason = ""
        try:
            if hasattr(raw_content, "choices"):
                finish_reason = raw_content.choices[0].finish_reason or ""
        except Exception:
            pass

        looks_truncated = (
            last_is_truncated
            or len(parsed_items) < expected_count
            or finish_reason == "length"
        )

        if not looks_truncated:
            return None

        if last_is_truncated:
            dropped = parsed_items.pop()
            seq = dropped.get("sequence_number", "?")
            print(f"TRUNCATION SALVAGE: Dropped incomplete item (seq {seq}), keeping {len(parsed_items)} complete items")

        if parsed_items:
            print(f"TRUNCATION SALVAGE: Salvaged {len(parsed_items)} of {expected_count} expected items")
            return parsed_items

        return None

    def generate_scene_storyboard(self, scene, screenplay: Screenplay) -> None:
        """Generate detailed storyboard items for a specific scene (Phase 2).
        
        Source-of-truth hierarchy: (1) Premise, (2) Story Structure, (3) Scene Content, (4) Storyboard.
        Lower layers must not contradict higher. Each paragraph in scene content becomes ONE storyboard item.
        """
        # Initialize debug log file
        try:
            from datetime import datetime
            with open("debug_entity_extraction.log", "w", encoding="utf-8") as debug_file:
                debug_file.write(f"Entity Extraction Debug Log\n")
                debug_file.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                debug_file.write(f"Scene: {scene.title if scene else 'Unknown'}\n")
                debug_file.write(f"{'='*80}\n\n")
        except:
            pass
        
        if not self._adapter:
            raise Exception("AI client not initialized. Please configure your API key or local AI server in settings.")
        
        # Get context from previous scenes (use consistency digest when available — token-efficient)
        all_scenes = screenplay.get_all_scenes()
        scene_index = next((i for i, s in enumerate(all_scenes) if s.scene_id == scene.scene_id), -1)
        context_scenes = []
        if scene_index > 0:
            context_scenes = all_scenes[0:scene_index]  # All previous scenes
        context_parts = []
        for s in context_scenes:
            digest = ""
            if s.metadata and s.metadata.get("consistency_digest"):
                digest = s.metadata["consistency_digest"]
            elif s.metadata and s.metadata.get("generated_content"):
                digest = (s.metadata["generated_content"][:200] or (s.description or "")[:100] or "") + "..."
            elif s.description:
                digest = (s.description or "")[:100] + "..."
            if digest:
                context_parts.append(f"Scene {s.scene_number}: {s.title}\n{digest}")
        context_text = "\n\n".join(context_parts) if context_parts else "Beginning of story"
        
        # Determine compression strategy
        compression_strategy = self._determine_compression_strategy(scene, screenplay)
        scene.compression_strategy = compression_strategy
        
        # Normalize scene content into beats/paragraphs
        scene_beats = self._normalize_scene_beats(scene)
        beat_count = len(scene_beats)
        
        # Debug output
        if beat_count > 0:
            print(f"DEBUG: Extracted {beat_count} beats from scene '{scene.title}':")
            for i, beat in enumerate(scene_beats, 1):
                print(f"  BEAT {i}: {beat[:80]}...")
        else:
            print(f"DEBUG: No beats extracted from scene '{scene.title}' - using fallback logic")
        
        # Determine minimum storyboard items: at least one per paragraph, more if paragraphs have multiple visual beats
        estimated_duration = scene.estimated_duration if scene.estimated_duration > 0 else 60
        
        if beat_count > 0:
            # Minimum: one item per paragraph. AI may produce more by splitting multi-beat paragraphs.
            num_items = beat_count
            print(f"Breaking down scene into at least {num_items} storyboard items ({beat_count} paragraphs, more if multi-beat)")
            print(f"CRITICAL: One visual beat per item. Multi-beat paragraphs must be split.")
        else:
            # Fallback to duration-based calculation only when no paragraphs/beats found
            min_items = max(2, estimated_duration // 10)
            max_items = max(3, estimated_duration // 5)
            if compression_strategy == "montage":
                num_items = max(1, int(estimated_duration // 15))
            elif compression_strategy == "beat_by_beat":
                num_items = max(3, int(estimated_duration // 5))
            elif compression_strategy == "atmospheric_hold":
                va_style = getattr(scene, 'visual_art_style', 'progressive')
                if va_style == "looping":
                    num_items = max(3, int(estimated_duration // 10))
                else:
                    num_items = max(2, int(estimated_duration // 15))
            else:
                num_items = 1
            print(f"Breaking down scene into {num_items} storyboard items based on estimated duration ({estimated_duration}s, strategy: {compression_strategy})")
        
        min_items = max(2, estimated_duration // 10)
        max_items = max(3, estimated_duration // 5)
        
        atmosphere_text = f"\nAtmosphere/Tone: {screenplay.atmosphere}" if screenplay.atmosphere else ""
        genre_text = ", ".join(screenplay.genre) if screenplay.genre else "General"
        
        # Build brand context section for promotional workflows
        brand_info = ""
        if screenplay.brand_context:
            brand_info = "\n\nBRAND / PRODUCT CONTEXT (REQUIRED - USE THIS INFORMATION IN ALL PROMPTS):\n"
            if screenplay.brand_context.brand_name:
                brand_info += f"Brand Name: {screenplay.brand_context.brand_name}\n"
            if screenplay.brand_context.product_name:
                brand_info += f"Product Name: {screenplay.brand_context.product_name}\n"
            if screenplay.brand_context.product_description:
                brand_info += f"Product Description: {screenplay.brand_context.product_description}\n"
            if screenplay.brand_context.core_benefit:
                brand_info += f"Core Benefit / Promise: {screenplay.brand_context.core_benefit}\n"
            if screenplay.brand_context.target_audience:
                brand_info += f"Target Audience: {screenplay.brand_context.target_audience}\n"
            if screenplay.brand_context.brand_personality:
                brand_info += f"Brand Personality: {', '.join(screenplay.brand_context.brand_personality)}\n"
            if screenplay.brand_context.mandatory_elements:
                brand_info += f"Mandatory Inclusions: {', '.join(screenplay.brand_context.mandatory_elements)}\n"
            brand_info += "\nCRITICAL: All storyboard items MUST reference the product/brand and incorporate the core benefit. Ensure product presence is consistent throughout all visual descriptions and prompts.\n"
        
        # Per-project cinematic and audio directives
        story_settings_text = self._build_story_settings_directives(screenplay)
        
        # Get generated scene content if available (this is the full scene content generated by AI)
        generated_content = ""
        if scene.metadata and isinstance(scene.metadata, dict):
            generated_content = scene.metadata.get("generated_content", "")
        
        # Use normalized beats for scene reference (ensures we have all beats)
        # If we have beats, use them; otherwise fall back to generated_content or description
        if beat_count > 0:
            # Use normalized beats as the source of truth
            scene_content_for_reference = "\n\n".join(scene_beats)
        elif generated_content and generated_content.strip():
            scene_content_for_reference = generated_content
        else:
            scene_content_for_reference = scene.description if scene.description else ""
        
        # Generate environment block for the scene (ONCE per scene, reused for all items)
        # This creates the static setting description for first-frame image prompts
        # Check if environment block exists and is approved
        scene_environment_block = ""
        if hasattr(scene, 'environment_id') and scene.environment_id:
            # Check if environment metadata exists and is approved
            env_metadata = screenplay.identity_block_metadata.get(scene.environment_id)
            if env_metadata and env_metadata.get("status") == "approved":
                scene_environment_block = env_metadata.get("identity_block", "")
                print(f"Using approved environment block for scene {scene.scene_number}")
        
        if not scene_environment_block:
            # Create placeholder for environment
            env_name = f"{scene.title} Environment"
            print(f"Creating environment placeholder for scene {scene.scene_number}...")
            env_id = screenplay.create_placeholder_identity_block(env_name, "environment", scene.scene_id)
            scene.environment_id = env_id
            
            # Scene-driven mode: MODE A (empty) vs MODE B (with extras)
            scene_desc = scene.description or ""
            scene_content_for_extras = (scene.metadata.get("generated_content", "") if scene.metadata else "") or ""
            requires_extras = self._scene_requires_extras(scene_desc, scene_content_for_extras)
            screenplay.update_identity_block_metadata(
                env_id,
                extras_present=requires_extras,
                foreground_zone="clear"
            )
            if requires_extras:
                screenplay.update_identity_block_metadata(
                    env_id,
                    extras_density="sparse",
                    extras_activities="",
                    extras_depth="background_only"
                )
            
            # Set environment user_notes only if not already populated by entity extraction
            existing_notes = (screenplay.identity_block_metadata.get(env_id, {}).get("user_notes") or "").strip()
            if not existing_notes:
                env_description = ""
                if scene.description:
                    env_description = f"Setting: {scene.title}. {scene.description[:200]}"
                else:
                    env_description = f"Setting: {scene.title}"
                screenplay.update_identity_block_metadata(env_id, user_notes=env_description)
            
            # Use a basic fallback for now
            scene_environment_block = f"a static establishing frame set in {scene.title.lower()}, grounded realistic environment, no motion"
            print(f"Environment placeholder created with description - review in Identity Blocks tab")
        
        # Use beat_count (from normalized beats) for breakdown instructions
        paragraph_count = beat_count
        
        # Build the scene reference using normalized beats
        scene_reference = ""
        if beat_count > 0:
            # Build beat-by-beat reference (this is the normalized list)
            beat_sections = []
            for i, beat in enumerate(scene_beats, 1):
                beat_sections.append(f"BEAT {i}:\n{beat}\n")
            
            scene_reference = f"""
Scene Content (Source Material - ALL BEATS MUST BE REPRESENTED):

{chr(10).join(beat_sections)}

Scene Summary: {scene.description}
"""
        elif scene_content_for_reference and scene_content_for_reference.strip():
            # Fallback: use scene_content_for_reference if no beats were found
            scene_reference = f"""
Scene Content (Source Material):

{scene_content_for_reference}

Scene Summary: {scene.description}
"""
        else:
            scene_reference = f"""
Scene Description: {scene.description}
"""
        
        # Deterministic storyboard rules — injected into ALL instruction variants
        deterministic_rules = """
═══════════════════════════════════════════════════════════════════════════════
PARAGRAPH → STORYBOARD STRUCTURE (MANDATORY — STRICT 1:1 MAPPING)
═══════════════════════════════════════════════════════════════════════════════

Each numbered paragraph [#] in Scene Content generates EXACTLY ONE storyboard item.
- Paragraph 1 → Storyboard Item 1.  Paragraph 2 → Storyboard Item 2.  Etc.
- No merging paragraphs.
- No splitting paragraphs.
- Storyboard index MUST match paragraph index.

═══════════════════════════════════════════════════════════════════════════════
COMPOSITION SCOPE RULE (MANDATORY)
═══════════════════════════════════════════════════════════════════════════════

Each storyboard item may ONLY reference:
  • Characters present in THAT paragraph
  • Objects present in THAT paragraph
  • Vehicles present in THAT paragraph
  • The active environment of THAT paragraph

Do NOT reference:
  • Items from OTHER paragraphs in the same scene
  • Global scene objects not visible in the paragraph
  • Future or past scene elements

═══════════════════════════════════════════════════════════════════════════════
PRIMARY ACTION EXTRACTION (BEAT DOMINANCE)
═══════════════════════════════════════════════════════════════════════════════

For each paragraph:
- Detect the dominant action verb (the first *asterisk* action in the paragraph).
- Camera framing MUST emphasize that dominant action.
- If the action is subtle (e.g. *adjusts*, *examines*) → use medium/close framing.
- If spatial shift (e.g. *walks*, *enters*, *runs*) → use wide shot.
- If tension implied (e.g. *freezes*, *stares*, *aims*) → allow slow push or low angle.
- Avoid generic "wide establishing shot" unless the paragraph is purely environmental.

If the paragraph contains 2+ distinct actions:
  → Prioritize the FIRST dominant action for camera composition.
  → Secondary actions remain in moment text but NOT as focal composition elements.

═══════════════════════════════════════════════════════════════════════════════
ENTITY LOCKING (MANDATORY)
═══════════════════════════════════════════════════════════════════════════════

- Character IDs must remain consistent across all items.
- Object IDs must remain consistent across all items.
- Vehicle IDs must remain consistent across all items.
- No new identities may be invented at storyboard stage.
- Use ONLY entities that exist in the scene content paragraphs.

═══════════════════════════════════════════════════════════════════════════════
FULL CHARACTER NAMES (MANDATORY)
═══════════════════════════════════════════════════════════════════════════════

- ALWAYS use the character's FULL registered name in FULL CAPS.
- NEVER abbreviate, shorten, or use only a first name or surname.
  ✗ "Fleck examines the evidence"  → WRONG (partial surname)
  ✗ "Jude turns to face the door"  → WRONG (first name only)
  ✓ "DETECTIVE JUDE FLECK examines the evidence" → CORRECT
- This applies to storyline text, image_prompt text, and prompt text.
- If the source paragraph uses a short name, expand it to the full name.

═══════════════════════════════════════════════════════════════════════════════
ZERO DRIFT POLICY (MANDATORY)
═══════════════════════════════════════════════════════════════════════════════

The storyboard is a visual translation layer. It must NOT:
- Reinterpret story.
- Add embellishment.
- Introduce unseen elements.
- Modify character motivation.
- Change narrative logic.

It MUST faithfully visualize the paragraph EXACTLY as written.

═══════════════════════════════════════════════════════════════════════════════
MOMENT FIELD REWRITE RULES
═══════════════════════════════════════════════════════════════════════════════

- Convert paragraph into present-tense cinematic action.
- Remove literary phrasing.
- Preserve *Action Markup* and (sfx) markup exactly.
- Insert appropriate (sfx) if implied but missing.
- Do NOT add new narrative content.

═══════════════════════════════════════════════════════════════════════════════

"""

        # Build instruction sections based on whether we have beats
        if beat_count > 0:
            instructions_section = f"""SOURCE OF TRUTH: Hierarchy is (1) Premise, (2) Story Structure, (3) Scene Content, (4) Storyboard. Lower layers must not contradict higher layers. Storyboard generation must NOT invent new story content.
{deterministic_rules}
Instructions for Creating Storyboard Items:

Each paragraph in the scene content generates EXACTLY ONE storyboard item.
Paragraph N → Storyboard Item N.  No merging.  No splitting.  No exceptions.

🚨 ABSOLUTE REQUIREMENT: Create EXACTLY {beat_count} storyboard items — one per paragraph.

Key Guidelines:
1. Extract content directly from each paragraph — use the exact dialogue, actions, and descriptions provided.
2. Create EXACTLY ONE storyboard item per paragraph in sequential order. Do NOT combine paragraphs. Do NOT skip any paragraph. Do NOT split paragraphs.
3. Each item may ONLY reference entities (characters, objects, vehicles, environments) that appear in its corresponding paragraph.
4. Preserve specific object names, character details, and scene descriptions exactly as written.
5. For the STORYLINE field: Convert the paragraph into present-tense cinematic action. Preserve *action* and (sfx) markup.
6. Storyboard generation must NOT invent new story content. No new entities. No embellishment.

Paragraph-to-Item Mapping (STRICT 1:1):
- Paragraph 1 (BEAT 1) → Storyboard Item 1
- Paragraph 2 (BEAT 2) → Storyboard Item 2
- Continue through ALL {beat_count} paragraphs — EVERY paragraph gets EXACTLY one item

Process:
1. Read each paragraph in order (BEAT 1, BEAT 2, ..., BEAT {beat_count})
2. For each paragraph, create EXACTLY ONE storyboard item
3. Identify the dominant *action* verb — camera framing must emphasize it
4. Do NOT skip, omit, combine, or split paragraphs
5. Distribute the total duration ({estimated_duration} seconds) across all {beat_count} items, choosing the optimal duration for each item (1-30 seconds) based on its content and pacing

VALIDATION CHECKLIST:
✓ EXACTLY {beat_count} storyboard items created (one per paragraph)
✓ Item N references ONLY entities from Paragraph N
✓ No cross-paragraph contamination
✓ No invented entities or embellishment
✓ Paragraph order preserved chronologically

"""
            requirement_section = f"""Scene Breakdown:
Create EXACTLY {beat_count} storyboard items (one per paragraph, strict 1:1). Each item references ONLY entities from its paragraph. Do NOT invent new story content.
Total duration: approximately {estimated_duration} seconds. Choose the optimal duration for each item (1-30 seconds) based on content complexity and pacing.

"""
            breakdown_instructions = f"""Create EXACTLY {beat_count} storyboard items. Paragraph N → Item N. Each item references ONLY entities from its source paragraph. Do NOT combine or split paragraphs. Do NOT add new actions, entities, or story content.
"""
            critical_note = f"🚨 EXACTLY {beat_count} ITEMS REQUIRED. Strict 1:1 paragraph-to-item mapping. No merging. No splitting."
            critical_instruction = f"Create EXACTLY {beat_count} items. Item N = Paragraph N. Each item scoped to its paragraph entities ONLY."
            critical_breakdown = f"Paragraph N → Storyboard Item N. Each storyline = cinematic translation of that paragraph only. No new content. No cross-paragraph references."
        elif scene_content_for_reference and scene_content_for_reference.strip():
            instructions_section = f"""Instructions for Creating Storyboard Items:
{deterministic_rules}
Your task is to break down the scene content above into distinct storyboard items (at least {num_items}) that progress chronologically through the scene. Each item must represent ONE dominant visual beat.

Key Guidelines:
1. Extract content directly from the scene - use the exact dialogue, actions, and descriptions provided
2. Break the scene into sequential moments, from beginning to end — one visual beat per item
3. Preserve specific object names, character details, and scene descriptions exactly as written
4. Each item should be unique and represent ONE action, ONE reveal, or ONE reaction — never multiple
5. If a moment introduces multiple objects or actions, split into separate items
6. Maintain continuity of all details throughout all items
7. Ensure all meaningful content from the scene is represented

Process:
1. Read the full scene content carefully
2. Identify distinct visual beats in chronological order (there may be more than {num_items})
3. Extract the dialogue, actions, and descriptions for each beat
4. Create one storyboard item per visual beat
5. Distribute the total duration ({estimated_duration} seconds) across items, choosing the optimal duration for each (1-30 seconds) based on content and pacing
6. Ensure no significant content is skipped

"""
            requirement_section = f"""Duration Planning:
Scene duration: {estimated_duration} seconds
Create at least {num_items} items (mix of 5 and 10 second durations). More items if paragraphs contain multiple visual beats.
Total should equal approximately {estimated_duration} seconds

"""
            breakdown_instructions = f"""Steps:
1. Read the scene content from beginning to end
2. Identify distinct visual beats progressing chronologically (may be more than {num_items})
3. Create one storyboard item per visual beat — ONE dominant focus per item
4. Preserve specific details from the scene content
5. Split paragraphs with multiple objects, actions, or visual focuses into separate items
6. Ensure each item is unique and shows scene progression
7. Do not skip significant content
"""
            critical_note = f"Target: at least {num_items} storyboard items for this {estimated_duration}-second scene. One visual beat per item."
            critical_instruction = f"Break the scene into sequential visual beats — one dominant focus per item"
            critical_breakdown = f"Create distinct items that progress chronologically. Each item = ONE action, ONE reveal, or ONE reaction."
        else:
            instructions_section = ""
            requirement_section = f"""Duration Planning:
Scene duration: {estimated_duration} seconds
Create {num_items} items (mix of 5 and 10 second durations)
Total should equal approximately {estimated_duration} seconds

"""
            breakdown_instructions = f"""Steps:
1. Read the scene description: "{scene.description[:200]}..."
2. Identify {num_items} distinct moments in chronological order
3. Create one storyboard item for each moment
4. Each item should be unique and show scene progression
"""
            critical_note = f"Target: {num_items} items for this {estimated_duration}-second scene"
            critical_instruction = f"- Think of this scene as a sequence of {num_items} moments, each with its own optimal duration based on content complexity"
            critical_breakdown = f"Break down the scene description into {num_items} distinct moments/actions/beats"
        
        # ── CHUNKED GENERATION ──────────────────────────────────────────────
        # Build shared context that every chunk prompt needs
        _shared_context = {
            "scene_title": scene.title,
            "scene_reference_full": scene_reference,
            "instructions_section": instructions_section,
            "plot_point": scene.plot_point if scene.plot_point else "None",
            "character_focus": ', '.join(scene.character_focus) if scene.character_focus else "None",
            "pacing": scene.pacing,
            "estimated_duration": estimated_duration,
            "genre_text": genre_text,
            "atmosphere_text": atmosphere_text,
            "brand_info": brand_info,
            "story_settings_text": story_settings_text,
            "ad_guidance": self._get_ad_storyboard_guidance(screenplay, scene) if screenplay.is_advertisement_mode() else "",
            "context_text": context_text,
            "requirement_section": requirement_section,
            "deterministic_rules": deterministic_rules,
            "breakdown_instructions": breakdown_instructions,
            "atmosphere": screenplay.atmosphere if screenplay.atmosphere else "as appropriate",
            "has_brand": bool(screenplay.brand_context),
            "dialogue_disabled": getattr(screenplay, 'story_settings', {}).get('audio_settings', {}).get('dialogue_generation_mode') == 'disabled',
            "has_scene_content": bool(scene_content_for_reference),
            "visual_art_style": getattr(scene, 'visual_art_style', 'progressive'),
            "is_visual_art": 'visual art' in (getattr(screenplay, 'intent', '') or '').lower()
                             or 'abstract' in (getattr(screenplay, 'intent', '') or '').lower(),
        }

        STORYBOARD_CHUNK_SIZE = 3

        if beat_count > 0 and beat_count > STORYBOARD_CHUNK_SIZE:
            chunks = []
            for start in range(0, beat_count, STORYBOARD_CHUNK_SIZE):
                end = min(start + STORYBOARD_CHUNK_SIZE, beat_count)
                chunks.append((start, end))
            print(f"CHUNKED GENERATION: {beat_count} beats → {len(chunks)} chunks of up to {STORYBOARD_CHUNK_SIZE} beats each")
        else:
            chunks = [(0, beat_count if beat_count > 0 else num_items)]
        
        try:
            storyboard_max_tokens = max(self.model_settings["max_tokens"], 3000)
            all_chunk_items = []
            chunk_failures = []

            for chunk_idx, (chunk_start, chunk_end) in enumerate(chunks):
                chunk_beat_count = chunk_end - chunk_start
                is_chunked = len(chunks) > 1

                if is_chunked:
                    print(f"\n{'='*60}")
                    print(f"CHUNK {chunk_idx + 1}/{len(chunks)}: Beats {chunk_start + 1}–{chunk_end} ({chunk_beat_count} items)")
                    print(f"{'='*60}")

                chunk_prompt = self._build_storyboard_chunk_prompt(
                    scene_beats=scene_beats,
                    chunk_start=chunk_start,
                    chunk_end=chunk_end,
                    total_beat_count=beat_count,
                    num_items=num_items,
                    shared_ctx=_shared_context,
                    is_chunked=is_chunked,
                )

                try:
                    response = self._chat_completion(
                        model=self.model_settings["model"],
                        messages=[
                            {"role": "system", "content": "You are a professional storyboard artist and script supervisor specializing in creating detailed, cinematic storyboards for video production optimized for higgsfield.ai. Your role is to behave like a script supervisor and continuity editor, not a writer. Your job is to prevent variation, not encourage creativity. Identity blocks for recurring entities must be reused verbatim — never paraphrase or reword them. STRICT 1:1 RULE: Each paragraph produces EXACTLY one storyboard item. No merging. No splitting. ENTITY LOCKING: Character IDs, Object IDs, Vehicle IDs must match the screenplay identity blocks exactly. No new entities may be invented. ZERO DRIFT POLICY: The storyboard is a visual translation layer — it must not reinterpret, embellish, introduce unseen elements, modify motivation, or change narrative logic."},
                            {"role": "user", "content": chunk_prompt}
                        ],
                        temperature=self.model_settings["temperature"],
                        max_tokens=storyboard_max_tokens
                    )

                    content = response.choices[0].message.content
                    chunk_data = self._extract_and_parse_json(content)
                    chunk_items_raw = chunk_data.get("storyboard_items", [])

                    salvaged = self._salvage_truncated_storyboard_items(content, chunk_items_raw, chunk_beat_count)
                    if salvaged is not None:
                        chunk_items_raw = salvaged

                    if is_chunked:
                        for ci, item_d in enumerate(chunk_items_raw):
                            item_d["sequence_number"] = chunk_start + ci + 1

                    all_chunk_items.extend(chunk_items_raw)
                    print(f"  ✓ Chunk {chunk_idx + 1}: received {len(chunk_items_raw)} items")

                except Exception as chunk_err:
                    print(f"  ✗ Chunk {chunk_idx + 1} FAILED: {chunk_err}")
                    chunk_failures.append((chunk_idx, chunk_start, chunk_end, str(chunk_err)))

            if chunk_failures and not all_chunk_items:
                failed_desc = "; ".join(f"Chunk {f[0]+1} (beats {f[1]+1}-{f[2]}): {f[3]}" for f in chunk_failures)
                raise Exception(f"All storyboard chunks failed: {failed_desc}")

            if chunk_failures:
                for cf_idx, cf_start, cf_end, cf_err in chunk_failures:
                    print(f"WARNING: Chunk {cf_idx + 1} failed ({cf_err}). Beats {cf_start + 1}–{cf_end} will have placeholder items.")
                    for placeholder_i in range(cf_start, cf_end):
                        beat_text = scene_beats[placeholder_i] if placeholder_i < len(scene_beats) else ""
                        all_chunk_items.append({
                            "sequence_number": placeholder_i + 1,
                            "duration": 5,
                            "storyline": beat_text[:500] if beat_text else f"[Generation failed for beat {placeholder_i + 1}]",
                            "image_prompt": "",
                            "prompt": "",
                            "visual_description": "",
                            "dialogue": "",
                            "scene_type": "action",
                            "camera_notes": "",
                            "_generation_failed": True,
                        })

                all_chunk_items.sort(key=lambda x: x.get("sequence_number", 0))

            storyboard_data = {"storyboard_items": all_chunk_items}
            print(f"\nCHUNKED GENERATION COMPLETE: {len(all_chunk_items)} total items from {len(chunks)} chunk(s), {len(chunk_failures)} failure(s)")
            
            # Create StoryboardItem objects and add to scene
            sequence_start = len(scene.storyboard_items) + 1
            n_items_before = len(scene.storyboard_items)
            seen_storylines = set()  # Track storylines to prevent duplicates
            for i, item_data in enumerate(storyboard_data.get("storyboard_items", [])):
                duration = item_data.get("duration", 5)
                duration = max(1, min(30, int(duration)))
                
                # Get storyline and check for duplicates
                storyline_text = item_data.get("storyline", "")
                if not isinstance(storyline_text, str):
                    storyline_text = str(storyline_text) if storyline_text else ""
                
                # When strict 1:1 (beat_count > 0), never skip — we need exactly one item per paragraph; post-processing will set storyline from paragraph.
                # Otherwise check for duplicate storylines
                if beat_count == 0:
                    storyline_normalized = storyline_text.lower().strip()[:100]
                    if storyline_normalized in seen_storylines:
                        print(f"Warning: Duplicate storyline detected at item {i+1}, modifying...")
                        storyline_text = f"{storyline_text} (Continued)"
                    seen_storylines.add(storyline_normalized)
                
                # Determine scene type
                scene_type_str = item_data.get("scene_type", "action").lower()
                scene_type = SceneType.ACTION
                for st in SceneType:
                    if st.value == scene_type_str:
                        scene_type = st
                        break
                
                # Get storyline
                storyline_text = item_data.get("storyline", "")
                if not isinstance(storyline_text, str):
                    storyline_text = str(storyline_text) if storyline_text else ""
                
                # Inject identity block references into storyline
                storyline_text = self._inject_identity_references(storyline_text, screenplay)
                # Enforce full character names (e.g. "Fleck" → "DETECTIVE JUDE FLECK")
                storyline_text = self._enforce_full_character_names(storyline_text, screenplay)
                
                # Get image prompt and clean it
                image_prompt_text = item_data.get("image_prompt", "")
                if not isinstance(image_prompt_text, str):
                    image_prompt_text = str(image_prompt_text) if image_prompt_text else ""
                image_prompt_text = self._clean_image_prompt(image_prompt_text)
                
                # Get video prompt (motion prompt) from AI response - PRESERVE THIS
                prompt_text = item_data.get("prompt", "")
                if not isinstance(prompt_text, str):
                    prompt_text = str(prompt_text) if prompt_text else ""
                
                # Inject identity block references into motion prompt
                prompt_text = self._inject_identity_references(prompt_text, screenplay)
                
                # Store original AI-generated prompt
                original_ai_prompt = prompt_text.strip()
                
                visual_desc = item_data.get("visual_description", "")
                if not isinstance(visual_desc, str):
                    visual_desc = str(visual_desc) if visual_desc else ""
                
                # Detect entities and generate identity blocks using FULL scene content (not just storyline)
                # Combine storyline with generated content for comprehensive entity detection
                scene_text_for_entities = storyline_text
                if generated_content and generated_content.strip():
                    # Use full scene content for better entity detection and identity block generation
                    scene_text_for_entities = generated_content + " " + storyline_text
                
                # Use five-section structure for prompts
                # Create a temporary item for section extraction
                temp_item = StoryboardItem(
                    item_id="temp",
                    sequence_number=sequence_start + i,
                    duration=duration,
                    storyline=storyline_text,
                    image_prompt=image_prompt_text,
                    prompt=prompt_text,
                    camera_notes=item_data.get("camera_notes", "")
                )
                
                # CRITICAL: Preserve the AI-generated motion prompt from the response
                # Only use _build_motion_video_prompt as a fallback if AI didn't provide a prompt
                if not original_ai_prompt or len(original_ai_prompt) < 50:
                    print(f"WARNING: AI did not provide motion prompt for item {i+1}, generating fallback...")
                    entity_names_for_motion = []
                    approved_entities = screenplay.get_approved_identity_blocks()
                    for entity_meta in approved_entities:
                        entity_name = entity_meta.get("name", "")
                        if entity_name:
                            entity_names_for_motion.append(entity_name)
                    
                    prompt_text, _ = self._build_motion_video_prompt(
                        duration=duration,
                        storyline=storyline_text,
                        dialogue=item_data.get("dialogue", ""),
                        camera_notes=item_data.get("camera_notes", ""),
                        entity_names=entity_names_for_motion
                    )
                else:
                    # Use the AI-generated prompt - it should already contain all necessary information
                    prompt_text = original_ai_prompt
                    print(f"Using AI-generated motion prompt for item {i+1} ({len(prompt_text)} chars)")
                
                # VALIDATION: Check if motion prompt is empty when storyline contains action verbs
                storyline_lower = storyline_text.lower() if storyline_text else ""
                action_verbs = ['appears', 'appear', 'bursts', 'burst', 'erupts', 'erupt', 'forms', 'form',
                              'emerges', 'emerge', 'swirls', 'swirl', 'reveals', 'reveal', 'transforms', 'transform',
                              'changes', 'change', 'moves', 'move', 'shifts', 'shift', 'rises', 'rise',
                              'spreads', 'spread', 'flows', 'flow', 'animates', 'animate', 'pulses', 'pulse',
                              'glows', 'glow', 'fades', 'fade', 'rotates', 'rotate', 'spins', 'spin',
                              'floats', 'float', 'drifts', 'drift', 'explodes', 'explode', 'dissolves', 'dissolve',
                              'materializes', 'materialize', 'vanishes', 'vanish', 'expands', 'expand',
                              'contracts', 'contract', 'morphs', 'morph', 'transitions', 'transition',
                              'walks', 'walk', 'runs', 'run', 'sits', 'sit', 'stands', 'stand', 'turns', 'turn']
                
                has_action_verbs = any(verb in storyline_lower for verb in action_verbs)
                prompt_lower = prompt_text.lower() if prompt_text else ""
                is_empty_or_static = not prompt_text or len(prompt_text) < 20 or 'no motion' in prompt_lower or 'static' in prompt_lower
                
                if has_action_verbs and is_empty_or_static:
                    warning_msg = f"⚠️ WARNING: Storyboard item {i+1} has action verbs in storyline but motion prompt is empty or static. Regenerating motion extraction..."
                    print(warning_msg)
                    # Try to extract motion again using the improved extraction
                    extracted_motion = self._extract_motion_from_storyline(storyline_text)
                    if extracted_motion and len(extracted_motion) > 20 and 'no motion' not in extracted_motion.lower():
                        # Combine with existing prompt if it has any content
                        if prompt_text and len(prompt_text) > 10:
                            prompt_text = f"{prompt_text} {extracted_motion}".strip()
                        else:
                            prompt_text = extracted_motion
                        print(f"✓ Motion extracted: {extracted_motion[:100]}...")
                    else:
                        print(f"⚠️ Motion extraction still failed for item {i+1}")
                
                # Build first-frame image prompt using pre-approved identity blocks
                # NOTE: Entities are now extracted upfront after scene content generation
                # Users should approve identity blocks BEFORE generating storyboard
                
                # Get all approved identity blocks for this scene
                identity_blocks = []
                approved_entities = screenplay.get_approved_identity_blocks()
                
                print(f"DEBUG: Found {len(approved_entities)} approved identity blocks available")
                for entity_meta in approved_entities:
                    if entity_meta.get("identity_block"):
                        identity_blocks.append(entity_meta["identity_block"])
                        print(f"DEBUG: Using approved identity block for {entity_meta.get('name', '?')} ({entity_meta.get('type', '?')})")
                
                # Check if we have enough approved blocks
                pending_count = len(screenplay.get_pending_identity_blocks())
                if pending_count > 0:
                    print(f"WARNING: {pending_count} identity block(s) are still pending approval. Image prompts may be incomplete.")
                
                print(f"DEBUG: Total approved identity blocks to use: {len(identity_blocks)}")
                
                # Create a more detailed item-specific positioning description
                # This makes each item unique by describing what's happening in THIS specific moment
                item_specific_description = storyline_text
                if visual_desc and visual_desc.strip():
                    item_specific_description = f"{storyline_text}. {visual_desc}"
                
                # Detect objects that are appearing/revealing (exclude from image prompt)
                appearing_objects = self._detect_appearing_objects(storyline_text, screenplay)
                
                # Build first-frame image prompt with environment and identity blocks
                # Exclude appearing objects (image = state BEFORE action)
                image_prompt_text = self._build_first_frame_image_prompt(
                    environment_block=scene_environment_block,
                    entity_identity_blocks=identity_blocks,
                    storyline=item_specific_description,
                    item=temp_item,
                    screenplay=screenplay,
                    appearing_object_ids=appearing_objects,
                    scene_id=scene.scene_id
                )
                
                print(f"DEBUG: Generated composition prompt length: {len(image_prompt_text)} chars")
                print(f"DEBUG: Composition prompt preview: {image_prompt_text[:300]}...")
                print(f"DEBUG: Motion prompt preview: {prompt_text[:300]}...")
                
                # Get dialogue (already included in motion prompt by _build_motion_video_prompt)
                dialogue_text = item_data.get("dialogue", "")
                if not isinstance(dialogue_text, str):
                    dialogue_text = str(dialogue_text) if dialogue_text else ""
                
                # Optional: inject atmospheric music only when project uses generated_with_video audio strategy
                audio_strategy = getattr(screenplay, "audio_strategy", "generated_with_video")
                if audio_strategy == "generated_with_video":
                    music_keywords = ["music", "soundtrack", "audio", "sound", "musical", "score", "melody", "ambient sound"]
                    has_music = any(keyword.lower() in prompt_text.lower() for keyword in music_keywords)
                    if not has_music:
                        music_descriptions = {
                            "Suspenseful": "Atmospheric music: Tense, suspenseful orchestral score with building tension",
                            "Lighthearted": "Atmospheric music: Upbeat, cheerful melody with light instrumentation",
                            "Dark": "Atmospheric music: Dark, ominous tones with deep bass and minor keys",
                            "Mysterious": "Atmospheric music: Enigmatic, ethereal sounds with subtle mystery",
                            "Epic": "Atmospheric music: Grand, sweeping orchestral score with dramatic crescendos",
                            "Intimate": "Atmospheric music: Soft, gentle acoustic music with emotional depth",
                            "Tense": "Atmospheric music: High-energy, intense score with rapid tempo",
                            "Whimsical": "Atmospheric music: Playful, light-hearted melody with quirky instrumentation",
                            "Melancholic": "Atmospheric music: Somber, emotional score with melancholic tones",
                            "Energetic": "Atmospheric music: Fast-paced, dynamic music with high energy",
                            "Somber": "Atmospheric music: Grave, serious orchestral tones with emotional weight",
                            "Playful": "Atmospheric music: Fun, bouncy melody with cheerful rhythm",
                            "Gritty": "Atmospheric music: Raw, edgy sound with industrial or urban tones",
                            "Ethereal": "Atmospheric music: Otherworldly, ambient sounds with ethereal quality",
                            "Realistic": "Atmospheric music: Natural, ambient sounds with subtle musical elements"
                        }
                        music_desc = music_descriptions.get(screenplay.atmosphere, "Atmospheric music: Ambient score matching the scene's tone and atmosphere")
                        prompt_text = f"{prompt_text} {music_desc}".strip()
                
                # Get camera notes
                camera_notes_text = item_data.get("camera_notes", "")
                if not isinstance(camera_notes_text, str):
                    camera_notes_text = str(camera_notes_text) if camera_notes_text else ""
                if not camera_notes_text or len(camera_notes_text) < 20:
                    scene_type_to_camera = {
                        SceneType.CLOSEUP: "Close-up shot, static camera",
                        SceneType.WIDE_SHOT: "Wide shot, static camera",
                        SceneType.ACTION: "Medium shot, dynamic camera movement",
                        SceneType.DIALOGUE: "Medium shot, static camera",
                        SceneType.ESTABLISHING: "Wide establishing shot, slow pan",
                    }
                    if scene_type in scene_type_to_camera:
                        camera_notes_text = scene_type_to_camera[scene_type]
                
                image_prompt_text = (image_prompt_text or "").strip()
                prompt_text = (prompt_text or "").strip()
                
                item = StoryboardItem(
                    item_id=str(uuid.uuid4()),
                    sequence_number=sequence_start + i,
                    duration=duration,
                    storyline=storyline_text,
                    image_prompt=image_prompt_text,
                    prompt=prompt_text,
                    visual_description=visual_desc,
                    dialogue=dialogue_text,
                    scene_type=scene_type,
                    camera_notes=camera_notes_text
                )
                # Set source paragraph index for strict 1:1 mapping
                item.source_paragraph_index = i
                # Infer shot_type from scene_type for new items
                _scene_to_shot = {
                    SceneType.CLOSEUP: "close_up",
                    SceneType.WIDE_SHOT: "wide",
                    SceneType.ACTION: "medium",
                    SceneType.DIALOGUE: "medium",
                    SceneType.ESTABLISHING: "wide",
                }
                item.shot_type = _scene_to_shot.get(scene_type, "wide")
                # Optional audio layer: set from AI response only when project uses audio
                if audio_strategy != "no_audio":
                    item.audio_intent = item_data.get("audio_intent", "") if isinstance(item_data.get("audio_intent"), str) else ""
                    item.audio_notes = item_data.get("audio_notes", "") if isinstance(item_data.get("audio_notes"), str) else ""
                    src = item_data.get("audio_source", "none")
                    item.audio_source = src if src in ("generated", "post", "none") else "none"
                
                # Calculate render cost
                render_cost, cost_factors = self._calculate_render_cost(item)
                item.render_cost = render_cost
                item.render_cost_factors = cost_factors
                
                # Detect identity drift
                drift_warnings = self._detect_identity_drift(item, screenplay)
                item.identity_drift_warnings = drift_warnings
                
                scene.add_storyboard_item(item)
            
            # Storyline alignment: when beat count matches new item count, use beats as source of truth
            new_items = scene.storyboard_items[n_items_before:]
            if beat_count > 0 and len(scene_beats) == len(new_items):
                for idx, item in enumerate(new_items):
                    beat_text = scene_beats[idx].strip()
                    storyline = self._inject_identity_references(beat_text, screenplay)
                    item.storyline = self._enforce_full_character_names(storyline, screenplay)
            
            # ── STRICT 1:1 VALIDATION (beat_count > 0) or LEGACY EXPANSION ──
            items_created = len(storyboard_data.get("storyboard_items", []))
            total_duration_created = sum(item.duration for item in scene.storyboard_items)
            
            if beat_count > 0:
                # ── STRICT 1:1 MODE: no splitting, no expanding ──
                final_item_count = len(scene.storyboard_items) - n_items_before
                if final_item_count < beat_count:
                    warning_msg = (
                        f"WARNING: Scene '{scene.title}' has {beat_count} paragraphs but "
                        f"only {final_item_count} storyboard items were generated. "
                        f"The validation layer will handle missing items."
                    )
                    print(f"{'=' * 80}\n{warning_msg}\n{'=' * 80}")
                    
                    if final_item_count == 0:
                        raise Exception(
                            f"Failed to generate any storyboard items for scene "
                            f"'{scene.title}' with {beat_count} paragraphs."
                        )
                elif final_item_count > beat_count:
                    # AI returned more items than paragraphs — trim to strict 1:1
                    excess = final_item_count - beat_count
                    del scene.storyboard_items[n_items_before + beat_count:]
                    print(f"STRICT 1:1: Trimmed {excess} excess items to match {beat_count} paragraphs")
                
                # Re-number and set source_paragraph_index
                new_items = scene.storyboard_items[n_items_before:]
                for idx, sb_item in enumerate(new_items):
                    sb_item.sequence_number = n_items_before + idx + 1
                    sb_item.source_paragraph_index = idx
                
                print(f"✓ Strict 1:1: {len(new_items)} storyboard items for {beat_count} paragraphs")
                
                # ── MOMENT REWRITE + BEAT DOMINANCE POST-PROCESSING ──
                for idx, sb_item in enumerate(new_items):
                    if idx < len(scene_beats):
                        src_paragraph = scene_beats[idx].strip()
                        
                        # Rewrite storyline: apply cinematic grammar to source paragraph
                        try:
                            grammar_result = enforce_cinematic_grammar(src_paragraph)
                            rewritten = grammar_result.corrected_text
                            # Inject identity references and enforce full character names
                            rewritten = self._inject_identity_references(rewritten, screenplay)
                            rewritten = self._enforce_full_character_names(rewritten, screenplay)
                            sb_item.storyline = rewritten
                        except Exception as e:
                            print(f"WARNING: Cinematic grammar rewrite failed for item {idx + 1}: {e}")
                            storyline = self._inject_identity_references(src_paragraph, screenplay)
                            sb_item.storyline = self._enforce_full_character_names(storyline, screenplay)
                        
                        # Extract dominant action and suggest camera framing
                        dominant = extract_dominant_action(src_paragraph)
                        if dominant:
                            framing = suggest_camera_framing(dominant, src_paragraph)
                            # Only override if current camera_notes are generic or empty
                            if not sb_item.camera_notes or len(sb_item.camera_notes) < 20:
                                sb_item.camera_notes = framing
                            print(f"  Item {idx + 1}: dominant action = *{dominant}* → {framing}")
                
                # ── ENTITY VALIDATION LAYER (MANDATORY) ──
                new_items = scene.storyboard_items[n_items_before:]
                validation_results = validate_storyboard_against_paragraphs(
                    scene_beats, new_items, screenplay
                )
                
                failed_indices = [
                    vr.paragraph_index for vr in validation_results
                    if not vr.is_valid and vr.paragraph_index < len(new_items)
                ]
                
                if failed_indices:
                    print(f"VALIDATION: {len(failed_indices)} item(s) failed entity validation — attempting regeneration")
                    
                    for fail_idx in failed_indices:
                        vr = validation_results[fail_idx]
                        sb_item = new_items[fail_idx]
                        src_paragraph = scene_beats[fail_idx].strip() if fail_idx < len(scene_beats) else ""
                        
                        if not src_paragraph:
                            sb_item.validation_status = "validation_failed"
                            sb_item.validation_errors = vr.errors
                            continue
                        
                        regen_success = False
                        for attempt in range(1, 3):  # Max 2 regeneration attempts
                            print(f"  Regenerating item {fail_idx + 1} (attempt {attempt}/2): {vr.errors}")
                            
                            regen_prompt = (
                                f"Regenerate storyboard item {fail_idx + 1} for this paragraph.\n\n"
                                f"SOURCE PARAGRAPH (BEAT {fail_idx + 1}):\n{src_paragraph}\n\n"
                                f"VALIDATION ERRORS:\n" +
                                "\n".join(f"- {e}" for e in vr.errors) +
                                f"\n\nRULES:\n"
                                f"- Reference ONLY entities from the paragraph above.\n"
                                f"- Do NOT add entities from other paragraphs.\n"
                                f"- Do NOT invent new entities.\n"
                                f"- Preserve all *action* and (sfx) markup.\n"
                                f"- Convert to present-tense cinematic action.\n\n"
                                f"Return ONLY valid JSON with this structure:\n"
                                f'{{"storyline": "...", "image_prompt": "...", "prompt": "...", '
                                f'"dialogue": "...", "scene_type": "action", "camera_notes": "...", '
                                f'"duration": 5}}'
                            )
                            
                            try:
                                regen_response = self._chat_completion(
                                    model=self.model_settings["model"],
                                    messages=[
                                        {"role": "system", "content": (
                                            "You are a storyboard artist fixing a validation error. "
                                            "Reference ONLY entities from the provided paragraph. "
                                            "No cross-paragraph contamination. No invented entities."
                                        )},
                                        {"role": "user", "content": regen_prompt}
                                    ],
                                    temperature=0.2,
                                    max_tokens=1000
                                )
                                regen_data = self._extract_and_parse_json(
                                    regen_response.choices[0].message.content
                                )
                                
                                # Apply regenerated fields
                                if isinstance(regen_data, dict):
                                    if regen_data.get("storyline"):
                                        regen_storyline = self._inject_identity_references(
                                            regen_data["storyline"], screenplay
                                        )
                                        sb_item.storyline = self._enforce_full_character_names(
                                            regen_storyline, screenplay
                                        )
                                    if regen_data.get("image_prompt"):
                                        sb_item.image_prompt = (regen_data["image_prompt"] or "").strip()
                                    if regen_data.get("prompt"):
                                        sb_item.prompt = (regen_data["prompt"] or "").strip()
                                    if regen_data.get("dialogue"):
                                        sb_item.dialogue = regen_data["dialogue"]
                                    if regen_data.get("camera_notes"):
                                        sb_item.camera_notes = regen_data["camera_notes"]
                                
                                # Re-validate
                                p_ent = extract_paragraph_entities(src_paragraph, screenplay)
                                s_ent = extract_storyboard_entities(sb_item, screenplay)
                                regen_raw = " ".join(filter(None, [
                                    getattr(sb_item, "storyline", ""),
                                    getattr(sb_item, "image_prompt", ""),
                                    getattr(sb_item, "prompt", ""),
                                ]))
                                mismatch = compare_entity_sets(p_ent, s_ent, item_raw_text=regen_raw, screenplay=screenplay)
                                
                                if mismatch.is_match:
                                    sb_item.validation_status = "passed"
                                    sb_item.validation_errors = []
                                    regen_success = True
                                    print(f"  ✓ Item {fail_idx + 1} passed validation after attempt {attempt}")
                                    break
                                else:
                                    vr = vr._replace(errors=list(mismatch.errors))
                                    print(f"  ✗ Item {fail_idx + 1} still failing: {mismatch.errors}")
                            except Exception as regen_err:
                                print(f"  ✗ Regeneration attempt {attempt} failed: {regen_err}")
                        
                        if not regen_success:
                            sb_item.validation_status = "validation_failed"
                            sb_item.validation_errors = vr.errors
                            print(f"  ⚠ Item {fail_idx + 1} flagged as validation_failed after 2 attempts")
                else:
                    print(f"VALIDATION: All {len(new_items)} items passed entity validation")
                
                # Mark passing items
                for idx, sb_item in enumerate(new_items):
                    if not sb_item.validation_status:
                        sb_item.validation_status = "passed"
                
            else:
                # ── LEGACY MODE (no beats): beat density check + duration adjustment ──
                new_items = scene.storyboard_items[n_items_before:]
                split_results = self._validate_and_split_beat_density(new_items, screenplay)
                if split_results is not None:
                    del scene.storyboard_items[n_items_before:]
                    for split_item in split_results:
                        scene.add_storyboard_item(split_item)
                    for seq_idx, sb_item in enumerate(
                        scene.storyboard_items[n_items_before:],
                        start=n_items_before + 1
                    ):
                        sb_item.sequence_number = seq_idx
                    print(f"BEAT DENSITY: Split {len(new_items)} items into {len(split_results)} items")
                
                # Duration adjustment for legacy mode
                current_total = sum(item.duration for item in scene.storyboard_items)
                if current_total < estimated_duration * 0.8:
                    scale_factor = estimated_duration / max(current_total, 1)
                    for sb_item in scene.storyboard_items:
                        new_duration = max(1, min(30, round(sb_item.duration * scale_factor)))
                        sb_item.duration = new_duration
            
            # ── DIALOGUE DURATION FLOOR ──
            # Ensure items with dialogue have enough duration for delivery
            for sb_item in scene.storyboard_items[n_items_before:]:
                dialogue = (sb_item.dialogue or "").strip()
                if dialogue:
                    word_count = len(dialogue.split())
                    min_duration = max(3, round(word_count / 2.0) + 1)
                    if sb_item.duration < min_duration:
                        sb_item.duration = min(30, min_duration)

            # ── MULTI-SHOT CLUSTERING (post-processing) ──
            try:
                from core.multishot_engine import apply_multishot_clustering
                apply_multishot_clustering(scene, screenplay, self.model_settings)
            except Exception as ms_err:
                print(f"WARNING: Multi-shot clustering failed, reverting to single-shot: {ms_err}")
                scene.generation_strategy = "single_shot"
                scene.multishot_clusters = []
                for sb_item in scene.storyboard_items:
                    sb_item.cluster_id = None
                    sb_item.shot_number_in_cluster = None

            # Mark scene as complete
            scene.is_complete = True
            scene.updated_at = datetime.now().isoformat()
                
        except Exception as e:
            error_message = str(e)
            raise Exception(f"Failed to generate scene storyboard: {error_message}")
    
    def generate_micro_story(self, premise: str, intent: str = "General Story", title: str = "") -> Screenplay:
        """Generate a complete micro story (premise → scene → storyboard) in one go.
        
        This is a streamlined workflow for micro stories that skips the outline and framework steps.
        """
        if not self._adapter:
            raise Exception("AI client not initialized. Please configure your API key or local AI server in settings.")
        
        # Create a basic screenplay with premise (title will be updated from AI response if blank)
        screenplay = Screenplay(title=title or "Micro Story", premise=premise)
        screenplay.intent = intent
        screenplay.length = "micro"
        
        # Generate a single scene description for the micro story
        scene_prompt = f"""
Create a single, compelling scene based on this premise:

Premise: {premise}
Story Intent: {intent}

Generate a detailed scene description (3-5 sentences) that tells a complete micro story.
The scene should be self-contained and work as a standalone narrative.

Return ONLY the scene description, no additional formatting.
"""
        
        try:
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You are a professional screenwriter specializing in creating compelling, self-contained micro stories."},
                    {"role": "user", "content": scene_prompt}
                ],
                temperature=self.model_settings["temperature"],
                max_tokens=500
            )
            
            scene_description = response.choices[0].message.content.strip()
            
            # Create a single act with a single scene
            from core.screenplay_engine import StoryAct, StoryScene
            import uuid
            
            act = StoryAct(
                act_number=1,
                title="Micro Story",
                description=scene_description
            )
            
            scene = StoryScene(
                scene_id=str(uuid.uuid4()),
                scene_number=1,
                title="Main Scene",
                description=scene_description,
                estimated_duration=30  # Micro stories are typically 15-30 seconds
            )
            
            act.add_scene(scene)
            screenplay.add_act(act)
            
            # Generate storyboard items for the scene
            self.generate_scene_storyboard(scene, screenplay)
            
            return screenplay
            
        except Exception as e:
            raise Exception(f"Failed to generate micro story: {str(e)}")
    
    def generate_storyboard(self, premise: str, title: str = "", length: str = "medium", atmosphere: str = "") -> Screenplay:
        """Generate a complete storyboard from a premise."""
        
        if not self._adapter:
            raise Exception("AI client not initialized. Please configure your API key or local AI server in settings.")
        
        # Determine target number of items based on length
        length_map = {
            "micro": {
                "description": "3-8 items (15-30 seconds total)",
                "min_items": 3,
                "max_items": 8,
                "target_seconds": 20
            },
            "short": {
                "description": "8-12 items (30-60 seconds total)",
                "min_items": 8,
                "max_items": 12,
                "target_seconds": 45
            },
            "medium": {
                "description": "15-25 items (1-3 minutes total)",
                "min_items": 15,
                "max_items": 25,
                "target_seconds": 120
            },
            "long": {
                "description": "30-50 items (3-5 minutes total)",
                "min_items": 30,
                "max_items": 50,
                "target_seconds": 240
            }
        }
        
        length_info = length_map.get(length.lower(), length_map["medium"])
        target_length = length_info["description"]
        min_items = length_info["min_items"]
        max_items = length_info["max_items"]
        
        atmosphere_text = f"\nAtmosphere/Tone: {atmosphere}" if atmosphere else ""
        
        prompt = f"""
You are a professional storyboard artist and screenwriter. Create a detailed storyboard for a video based on this premise:

Premise: {premise}
Title: {title if title else "(none provided — you MUST generate an original, compelling title)"}
Target Length: {target_length}
CRITICAL: You MUST create between {min_items} and {max_items} storyboard items. Aim for the HIGHER end ({max_items} items) to ensure a complete story.{atmosphere_text}

For each storyboard item, you must:
1. Choose the optimal duration in whole seconds (1-30) based on content:
   - Quick cuts, reaction shots, transitions = 2-3 seconds
   - Fast action beats = 3-5 seconds
   - Standard action or dialogue = 5-8 seconds
   - Complex scenes with extended dialogue = 8-12 seconds
   - Key dramatic moments, reveals = 6-10 seconds
   - Establishing/atmospheric shots = 3-6 seconds
   - Choose the duration that best serves the pacing and content of each specific moment

2. Create a COMPOSITION PROMPT for the start frame image:
   - Describe the camera shot type and what is visible in the frame
   - Reference characters, vehicles, objects, and environments BY NAME ONLY
   - Include their placement and any action (e.g. "kneeling", "standing at the doorway")
   - Do NOT include physical descriptions, clothing, lighting, atmosphere, or style
   - The image generator already has reference images for each entity — only describe composition
   - Example: "Wide shot of ELARA VANDERMERE kneeling in the fields of Briar's Hollow, her hands in the soil"
   - Example: "Close-up of MAELIS THORNE clutching a yellowed scroll, eyes wide"

3. Create a comprehensive VIDEO PROMPT for higgsfield.ai video generation:
   - CRITICAL: The video prompt MUST describe the EXACT SAME SETTING as the image prompt - same location, same environment, same visual elements
   - CRITICAL: MUST explicitly describe ALL character actions using clear action verbs so the AI video generator knows what movements to animate
   - Use explicit action verbs: walking, running, crouching, standing, sitting, jumping, reaching, grabbing, turning, looking, speaking, gesturing, moving, approaching, entering, leaving, etc.
   - Describe actions clearly: "Character walks across the room", "Character runs toward the door", "Character crouches behind the table", "Character stands up", "Character reaches for the object"
   - Include detailed visual description of the scene (setting, characters, actions, atmosphere)
   - Specify camera angles, lighting, and composition
   - Describe character movements and actions in EXPLICIT detail - what they are doing, how they move
   - Include setting and atmosphere details (MUST match image prompt setting)
   - Include lighting conditions (MUST match image prompt lighting)
   - Include environmental details (MUST match image prompt environment)
   - Describe ONLY what is seen: visual action, camera, composition. Do not include music or sound design in the prompt.
   - Use cinematic terminology
   - Be descriptive and comprehensive (no length limit; be as detailed as needed) to give maximum detail for video generation
   - This prompt should be the complete description needed for higgsfield.ai to generate the video
   - The video prompt should start from the same visual state as described in the image prompt, then describe the action/movement
   - Example: "Character walks slowly across the dimly lit room, reaching for the door handle. As they approach, they crouch down to examine something on the floor, then stand up and turn to face the camera."

4. Generate dialogue for the scene:
   - If characters are speaking, include realistic dialogue
   - Format as "Character: Dialogue text"
   - If no dialogue is needed, use empty string
   - Most scenes should have some dialogue unless it's purely action/visual

5. Provide detailed camera movement notes:
   - Specify camera movements (pan, tilt, zoom, dolly, tracking, static, etc.)
   - Include camera angles (high angle, low angle, eye level, Dutch angle, etc.)
   - Describe shot composition (close-up, medium shot, wide shot, extreme wide, etc.)
   - Note any camera transitions or movements within the shot
   - Be specific about camera direction (e.g., "Slow dolly forward", "Pan left to right", "Zoom in on character's face")

6. Classify the scene type (action, dialogue, transition, establishing, closeup, wide_shot, montage)

STORY TITLE (MANDATORY): The "title" field MUST contain an original, compelling title. If the user provided a title, use it. If no title was provided, you MUST generate one — NEVER use "Untitled", "Untitled Story", or leave it blank.

CRITICAL: You MUST return ONLY valid JSON. No markdown, no explanations, no code blocks.

Format your response as a JSON object with this EXACT structure (ensure all commas are present):
{{
    "title": "An original, compelling story title (MANDATORY — never 'Untitled')",
    "storyboard_items": [
        {{
            "sequence_number": 1,
            "duration": 5,
            "image_prompt": "Higgsfield.ai optimized image prompt (no length limit; be as detailed as needed) describing ONLY the static establishing shot/first frame. Be detailed and specific: precise setting, character appearance and exact positioning, camera angle/perspective, specific lighting conditions, environmental elements, atmospheric details. NO action or movement. Highly detailed photorealistic style.",
            "prompt": "COMPREHENSIVE video generation prompt (no length limit; be as detailed as needed) for higgsfield.ai. Include: detailed scene description, camera angles, lighting, composition, character actions, setting, atmosphere, dialogue. Visual and camera only; no music or sound design.",
            "visual_description": "Keep this field for reference, but the prompts above should contain all visual details",
            "dialogue": "Character: Dialogue text here. Include dialogue for most scenes unless purely visual.",
            "scene_type": "action",
            "camera_notes": "Detailed camera movement: e.g., 'Slow dolly forward, medium shot, eye level angle. Camera tracks character movement from left to right.'"
        }},
        {{
            "sequence_number": 2,
            "duration": 10,
            "image_prompt": "Higgsfield.ai optimized image prompt (no length limit; be as detailed as needed) for the static establishing shot. Detailed and specific: setting, character positioning, camera angle, lighting, environment. NO action.",
            "prompt": "COMPREHENSIVE video generation prompt (no length limit; be as detailed as needed) with full visual and cinematic details",
            "visual_description": "",
            "dialogue": "Character: More dialogue here",
            "scene_type": "dialogue",
            "camera_notes": "Camera movement details: e.g., 'Close-up shot, static camera, slight zoom in on character's face during dialogue.'"
        }}
    ]
}}

IMPORTANT JSON RULES:
- Every property must be followed by a comma EXCEPT the last property in an object
- Every array item must be followed by a comma EXCEPT the last item
- All string values must be properly quoted and escaped
- No trailing commas before closing braces or brackets
- Ensure proper nesting of all brackets and braces

IMPORTANT REQUIREMENTS:
- The "image_prompt" field is a COMPOSITION PROMPT — describe camera shot, entity names, placement, and action only
  - Reference entities BY NAME ONLY — no physical descriptions, clothing, lighting, atmosphere, or style
  - The image generator has reference images for each entity; only describe composition and framing
  - Example: "Wide shot of ELARA VANDERMERE kneeling in the fields of Briar's Hollow, her hands in the soil"
- The "prompt" field should be COMPREHENSIVE video generation prompt (no length limit; be as detailed as needed) for higgsfield.ai
  - CRITICAL: MUST explicitly describe ALL character actions using clear action verbs: walking, running, crouching, standing, sitting, jumping, reaching, grabbing, turning, looking, speaking, gesturing, moving, approaching, entering, leaving, etc.
  - Describe actions clearly so the AI video generator knows exactly what movements to animate
  - MUST incorporate the atmosphere/tone ({atmosphere if atmosphere else "as appropriate"}) throughout the video prompt
  - MUST include dialogue from the "dialogue" field - incorporate dialogue naturally into the scene description
  - Describe ONLY what is seen: visual action, camera, composition. Do not include music or sound design in the prompt.
- Generate dialogue for scenes where characters interact or speak (most scenes should have dialogue)
- Camera notes MUST include specific camera movements (pan, tilt, zoom, dolly, tracking, etc.) and angles

Create a complete, sequential storyboard that tells the story from beginning to end.
Make sure each item flows naturally into the next.

CRITICAL REQUIREMENT: You MUST create at least {min_items} storyboard items, and ideally {max_items} items for a complete story.
Do NOT stop early - create the full number of items requested to tell the complete story.
"""
        
        try:
            # Use higher max_tokens for storyboard generation (needs more content)
            storyboard_max_tokens = max(self.model_settings["max_tokens"], 4000)
            
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You are a professional storyboard artist and screenwriter specializing in creating detailed, cinematic storyboards for video production. When creating image_prompt fields, write a SHORT composition-only prompt: camera shot type, entity names, placement, and action. No physical descriptions, clothing, lighting, or style — the image generator has reference images for each entity. Be detailed and comprehensive for the video prompt field."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.model_settings["temperature"],
                max_tokens=storyboard_max_tokens
            )
            
            content = response.choices[0].message.content
            
            # Try to extract and parse JSON from the response
            storyboard_data = self._extract_and_parse_json(content)
            
            # Create Screenplay object — prefer AI-generated title, then user title, then premise-derived
            ai_title = storyboard_data.get("title", "")
            _untitled = {"untitled", "untitled story", "untitled brand content", "untitled experimental"}
            if ai_title and ai_title.strip().lower() not in _untitled:
                final_title = ai_title.strip()
            elif title and title.strip():
                final_title = title.strip()
            else:
                final_title = premise[:60].strip().rstrip(".") if premise else "My Story"
            screenplay = Screenplay(
                title=final_title,
                premise=premise
            )
            
            # Create StoryboardItem objects
            for item_data in storyboard_data.get("storyboard_items", []):
                duration = item_data.get("duration", 5)
                duration = max(1, min(30, int(duration)))
                
                # Determine scene type
                scene_type_str = item_data.get("scene_type", "action").lower()
                scene_type = SceneType.ACTION
                for st in SceneType:
                    if st.value == scene_type_str:
                        scene_type = st
                        break
                
                # Get storyline
                storyline_text = item_data.get("storyline", "")
                if not isinstance(storyline_text, str):
                    storyline_text = str(storyline_text) if storyline_text else ""
                
                # Get image prompt (for establishing image generation)
                image_prompt_text = item_data.get("image_prompt", "")
                if not isinstance(image_prompt_text, str):
                    image_prompt_text = str(image_prompt_text) if image_prompt_text else ""
                
                # Clean image prompt to ensure it only describes a static image, not dynamic action
                image_prompt_text = self._clean_image_prompt(image_prompt_text)
                
                # Merge prompt and visual_description if both exist and prompt doesn't already contain visual details
                prompt_text = item_data.get("prompt", "")
                if not isinstance(prompt_text, str):
                    prompt_text = str(prompt_text) if prompt_text else ""
                visual_desc = item_data.get("visual_description", "")
                if not isinstance(visual_desc, str):
                    visual_desc = str(visual_desc) if visual_desc else ""
                
                # Ensure consistency between image prompt and video prompt settings
                image_prompt_text, prompt_text = self._ensure_prompt_consistency(image_prompt_text, prompt_text)
                
                # If prompt is short and visual_description exists, combine them
                if len(prompt_text) < 100 and visual_desc:
                    prompt_text = f"{prompt_text} {visual_desc}".strip()
                elif not prompt_text and visual_desc:
                    prompt_text = visual_desc
                
                # Ensure dialogue is present (generate placeholder if missing for dialogue scenes)
                dialogue_text = item_data.get("dialogue", "")
                if not isinstance(dialogue_text, str):
                    dialogue_text = str(dialogue_text) if dialogue_text else ""
                if scene_type == SceneType.DIALOGUE and not dialogue_text:
                    dialogue_text = "[Dialogue to be added]"
                
                # Incorporate dialogue into the video prompt if it exists and isn't already included
                if dialogue_text and dialogue_text not in prompt_text:
                    # Add dialogue to the prompt in a natural way
                    prompt_text = f"{prompt_text} Dialogue: {dialogue_text}".strip()
                
                # Ensure actions are explicitly described in the video prompt
                prompt_text = self._ensure_actions_described(prompt_text, dialogue_text)
                
                # Optional: inject atmospheric music only when project uses generated_with_video audio strategy
                audio_strategy = getattr(screenplay, "audio_strategy", "generated_with_video")
                if audio_strategy == "generated_with_video":
                    music_keywords = ["music", "soundtrack", "audio", "sound", "musical", "score", "melody", "ambient sound"]
                    has_music = any(keyword.lower() in prompt_text.lower() for keyword in music_keywords)
                    if not has_music:
                        atmosphere = screenplay.atmosphere if hasattr(screenplay, 'atmosphere') and screenplay.atmosphere else ""
                        music_descriptions = {
                            "Suspenseful": "Atmospheric music: Tense, suspenseful orchestral score with building tension",
                            "Lighthearted": "Atmospheric music: Upbeat, cheerful melody with light instrumentation",
                            "Dark": "Atmospheric music: Dark, ominous tones with deep bass and minor keys",
                            "Mysterious": "Atmospheric music: Enigmatic, ethereal sounds with subtle mystery",
                            "Epic": "Atmospheric music: Grand, sweeping orchestral score with dramatic crescendos",
                            "Intimate": "Atmospheric music: Soft, gentle acoustic music with emotional depth",
                            "Tense": "Atmospheric music: High-energy, intense score with rapid tempo",
                            "Whimsical": "Atmospheric music: Playful, light-hearted melody with quirky instrumentation",
                            "Melancholic": "Atmospheric music: Somber, emotional score with melancholic tones",
                            "Energetic": "Atmospheric music: Fast-paced, dynamic music with high energy",
                            "Somber": "Atmospheric music: Grave, serious orchestral tones with emotional weight",
                            "Playful": "Atmospheric music: Fun, bouncy melody with cheerful rhythm",
                            "Gritty": "Atmospheric music: Raw, edgy sound with industrial or urban tones",
                            "Ethereal": "Atmospheric music: Otherworldly, ambient sounds with ethereal quality",
                            "Realistic": "Atmospheric music: Natural, ambient sounds with subtle musical elements"
                        }
                        music_desc = music_descriptions.get(atmosphere, "Atmospheric music: Ambient score matching the scene's tone and atmosphere")
                        prompt_text = f"{prompt_text} {music_desc}".strip()
                
                # Ensure camera notes include movement details
                camera_notes_text = item_data.get("camera_notes", "")
                if not isinstance(camera_notes_text, str):
                    camera_notes_text = str(camera_notes_text) if camera_notes_text else ""
                if not camera_notes_text or len(camera_notes_text) < 20:
                    # Generate basic camera notes if missing
                    scene_type_to_camera = {
                        SceneType.CLOSEUP: "Close-up shot, static camera",
                        SceneType.WIDE_SHOT: "Wide shot, static camera",
                        SceneType.ACTION: "Medium shot, dynamic camera movement",
                        SceneType.DIALOGUE: "Medium shot, static camera",
                        SceneType.ESTABLISHING: "Wide establishing shot, slow pan",
                    }
                    if scene_type in scene_type_to_camera:
                        camera_notes_text = scene_type_to_camera[scene_type]
                
                image_prompt_text = (image_prompt_text or "").strip()
                prompt_text = (prompt_text or "").strip()
                
                item = StoryboardItem(
                    item_id=str(uuid.uuid4()),
                    sequence_number=item_data.get("sequence_number", 0),
                    duration=duration,
                    storyline=storyline_text,
                    image_prompt=image_prompt_text,
                    prompt=prompt_text,
                    visual_description=visual_desc,  # Keep for reference/editing
                    dialogue=dialogue_text,
                    scene_type=scene_type,
                    camera_notes=camera_notes_text
                )
                
                # Calculate render cost
                render_cost, cost_factors = self._calculate_render_cost(item)
                item.render_cost = render_cost
                item.render_cost_factors = cost_factors
                
                # Detect identity drift
                drift_warnings = self._detect_identity_drift(item, screenplay)
                item.identity_drift_warnings = drift_warnings
                
                screenplay.add_item(item)
            
            # Final validation - ensure we have enough items
            final_count = len(screenplay.storyboard_items)
            if final_count < min_items:
                raise Exception(
                    f"Storyboard generation incomplete: Only {final_count} items created, but {length.lower()} length requires at least {min_items} items. "
                    f"Total duration: {screenplay.get_total_duration_formatted()}. Please try generating again."
                )
            
            return screenplay
                
        except Exception as e:
            error_message = str(e)
            raise Exception(f"Failed to generate storyboard: {error_message}")
    
    def _extract_partial_json(self, json_str: str) -> Optional[Dict[str, Any]]:
        """Extract partial data from incomplete JSON using regex."""
        try:
            # Extract title
            title_match = re.search(r'"title"\s*:\s*"([^"]*)"', json_str)
            title = title_match.group(1) if title_match else ""
            if not title or title.strip().lower() in {"untitled", "untitled story"}:
                title = "My Story"
            
            # Extract storyboard items using regex
            items = []
            # Pattern to match each item object
            item_pattern = r'\{\s*"sequence_number"\s*:\s*(\d+)\s*,\s*"duration"\s*:\s*(\d+)\s*,\s*"prompt"\s*:\s*"([^"]*)"\s*,\s*"visual_description"\s*:\s*"([^"]*)"\s*,\s*"dialogue"\s*:\s*"([^"]*)"\s*,\s*"scene_type"\s*:\s*"([^"]*)"\s*,\s*"camera_notes"\s*:\s*"([^"]*)"'
            
            # More flexible pattern that handles multiline strings
            item_blocks = re.finditer(r'\{\s*"sequence_number"\s*:\s*(\d+)', json_str)
            for match in item_blocks:
                start_pos = match.start()
                # Find the matching closing brace (simplified)
                brace_count = 0
                end_pos = start_pos
                for i in range(start_pos, min(start_pos + 2000, len(json_str))):
                    if json_str[i] == '{':
                        brace_count += 1
                    elif json_str[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_pos = i + 1
                            break
                
                # If no closing brace found, this might be the last incomplete item
                # Extract up to the end of the string
                if end_pos == start_pos:
                    # This is likely an incomplete last item
                    end_pos = len(json_str)
                
                if end_pos > start_pos:
                    item_str = json_str[start_pos:end_pos]
                    # Try to parse the complete item first
                    try:
                        # If item is incomplete, try to close it temporarily for parsing
                        if not item_str.rstrip().endswith('}'):
                            # Try adding closing brace
                            test_str = item_str.rstrip().rstrip(',') + '\n}'
                            try:
                                item_data = json.loads(test_str)
                                if "sequence_number" in item_data:
                                    items.append(item_data)
                                    continue
                            except:
                                pass
                        else:
                            item_data = json.loads(item_str)
                            if "sequence_number" in item_data:
                                items.append(item_data)
                                continue
                    except:
                        pass
                    
                    # If parsing fails, try regex extraction with better string handling
                    seq_match = re.search(r'"sequence_number"\s*:\s*(\d+)', item_str)
                    dur_match = re.search(r'"duration"\s*:\s*(\d+)', item_str)
                    
                    if seq_match and dur_match:
                        # Extract strings more carefully - handle escaped quotes
                        # Pattern: "key": "value" where value can contain escaped quotes
                        def extract_string_value(key, text):
                            pattern = f'"{key}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"'
                            match = re.search(pattern, text, re.DOTALL)
                            if match:
                                return self._unescape_json_string(match.group(1))
                            # Also try to extract if it's the last incomplete property
                            # Look for the key and extract everything after the colon until end or next property
                            key_pattern = f'"{key}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"?'
                            match = re.search(key_pattern, text, re.DOTALL)
                            if match:
                                value = match.group(1) if match.group(1) else ""
                                return self._unescape_json_string(value)
                            return ""
                        
                        # Also extract storyline if present
                        storyline = extract_string_value("storyline", item_str)
                        
                        items.append({
                            "sequence_number": int(seq_match.group(1)),
                            "duration": int(dur_match.group(1)),
                            "storyline": storyline if storyline else "",
                            "image_prompt": extract_string_value("image_prompt", item_str),
                            "prompt": extract_string_value("prompt", item_str),
                            "visual_description": extract_string_value("visual_description", item_str),
                            "dialogue": extract_string_value("dialogue", item_str),
                            "scene_type": extract_string_value("scene_type", item_str) or "action",
                            "camera_notes": extract_string_value("camera_notes", item_str)
                        })
                    
                    pos = end_pos
            
            if items:
                return {
                    "title": title,
                    "storyboard_items": items
                }
        except Exception:
            pass
        return None
    
    def _unescape_json_string(self, s: str) -> str:
        """Unescape JSON string (handle \\n, \\", etc.)."""
        if not s:
            return ""
        # Basic unescaping
        s = s.replace('\\n', '\n')
        s = s.replace('\\"', '"')
        s = s.replace('\\t', '\t')
        s = s.replace('\\\\', '\\')
        return s
    
    MAX_PROMPT_LENGTH = 512

    @staticmethod
    def _truncate_prompt(text: str, max_length: int = 512) -> str:
        """Truncate a prompt to max_length characters, breaking at the last word boundary."""
        if not text or len(text) <= max_length:
            return text
        truncated = text[:max_length]
        last_space = truncated.rfind(' ')
        if last_space > max_length * 0.6:
            truncated = truncated[:last_space]
        return truncated.rstrip(' .,;:|-')

    @staticmethod
    def _get_action_verb_list_for_prompt() -> str:
        """Return a comma-separated string of all approved action verbs for AI prompt injection."""
        verbs = sorted(get_effective_action_whitelist())
        return ", ".join(verbs)

    @staticmethod
    def _get_sfx_list_for_prompt() -> str:
        """Return a comma-separated string of all approved SFX for AI prompt injection."""
        sfx = sorted(get_effective_sfx_whitelist())
        return ", ".join(f"({s})" for s in sfx)

    def _clean_image_prompt(self, prompt: str) -> str:
        """Clean image prompt to remove action/movement descriptions and ensure it only describes a static image."""
        # Ensure prompt is a string
        if not isinstance(prompt, str):
            prompt = str(prompt) if prompt else ""
        
        if not prompt:
            return prompt
        
        # Words/phrases that indicate action or movement (to be removed or replaced)
        action_patterns = [
            (r'\b(walking|running|moving|approaching|entering|leaving|exiting|coming|going)\b', 'positioned'),
            (r'\b(turning|rotating|spinning|swiveling)\b', 'facing'),
            (r'\b(reaching|grabbing|taking|picking up|holding up)\b', 'holding'),
            (r'\b(looking|glancing|gazing|staring)\s+(at|toward|around|away)', 'facing'),
            (r'\b(speaking|saying|talking|whispering|shouting)\b', ''),
            (r'\b(begins|starts|begins to|starts to|begins moving|starts moving)\b', ''),
            (r'\b(as|while|when)\s+(he|she|they|it)\s+(walks|runs|moves|approaches)', ''),
            (r'\b(camera|shot)\s+(follows|tracks|pans|moves|zooms|dollies)', 'static camera'),
            (r'\b(dynamic|action|movement|motion|animated)\b', 'static'),
            (r'\b(sequence|progression|unfolds|develops|happens)\b', ''),
        ]
        
        cleaned = prompt
        for pattern, replacement in action_patterns:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        
        # Remove phrases that describe ongoing action
        action_phrases = [
            r'in the process of .+?\.',
            r'as .+? happens',
            r'while .+? occurs',
            r'during .+? action',
            r'while .+? moves',
            r'as .+? approaches',
        ]
        
        for phrase_pattern in action_phrases:
            cleaned = re.sub(phrase_pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Ensure we're describing a static state
        # Add "static" or "frozen moment" if not present and prompt seems dynamic
        dynamic_indicators = ['moving', 'action', 'dynamic', 'sequence', 'progression']
        has_dynamic = any(indicator in cleaned.lower() for indicator in dynamic_indicators)
        
        if has_dynamic and 'static' not in cleaned.lower() and 'frozen' not in cleaned.lower():
            # Try to add context that it's static
            if not cleaned.strip().endswith('.'):
                cleaned += '.'
            cleaned = cleaned.rstrip('.') + ', static composition, frozen moment.'
        
        # Clean up extra spaces
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = cleaned.strip()
        
        return cleaned
    
    def _extract_setting_elements(self, prompt: str) -> Dict[str, str]:
        """Extract key setting elements from a prompt (location, lighting, environment, time of day)."""
        setting = {
            "location": "",
            "lighting": "",
            "environment": "",
            "time_of_day": "",
            "weather": ""
        }
        
        # Ensure prompt is a string
        if not isinstance(prompt, str):
            prompt = str(prompt) if prompt else ""
        
        if not prompt:
            return setting
        
        prompt_lower = prompt.lower()
        
        # Extract location keywords
        location_keywords = ["room", "house", "building", "street", "park", "forest", "beach", "office", "kitchen", "bedroom", "city", "desert", "mountain", "field", "cafe", "restaurant", "bar", "shop", "store"]
        for keyword in location_keywords:
            if keyword in prompt_lower:
                # Try to get context around the keyword
                idx = prompt_lower.find(keyword)
                start = max(0, idx - 30)
                end = min(len(prompt), idx + len(keyword) + 30)
                context = prompt[start:end]
                if not setting["location"]:
                    setting["location"] = context.strip()
                break
        
        # Extract lighting keywords
        lighting_keywords = ["dimly lit", "brightly lit", "soft light", "harsh light", "golden hour", "sunset", "sunrise", "neon", "candlelight", "fluorescent", "natural light", "artificial light", "shadow", "dark", "bright"]
        for keyword in lighting_keywords:
            if keyword in prompt_lower:
                setting["lighting"] = keyword
                break
        
        # Extract time of day
        time_keywords = ["morning", "afternoon", "evening", "night", "dawn", "dusk", "midday", "midnight"]
        for keyword in time_keywords:
            if keyword in prompt_lower:
                setting["time_of_day"] = keyword
                break
        
        # Extract weather
        weather_keywords = ["rain", "rainy", "snow", "snowy", "fog", "foggy", "sunny", "cloudy", "wind", "windy", "storm", "stormy"]
        for keyword in weather_keywords:
            if keyword in prompt_lower:
                setting["weather"] = keyword
                break
        
        return setting
    
    def _ensure_prompt_consistency(self, image_prompt: str, video_prompt: str) -> tuple:
        """Ensure image prompt and video prompt describe the same setting."""
        # Ensure both prompts are strings
        if not isinstance(image_prompt, str):
            image_prompt = str(image_prompt) if image_prompt else ""
        if not isinstance(video_prompt, str):
            video_prompt = str(video_prompt) if video_prompt else ""
        
        if not image_prompt or not video_prompt:
            return image_prompt, video_prompt
        
        # Extract setting elements from both prompts
        image_setting = self._extract_setting_elements(image_prompt)
        video_setting = self._extract_setting_elements(video_prompt)
        
        # If video prompt has setting details that image prompt lacks, add them to image prompt
        if video_setting["location"] and not image_setting["location"]:
            # Try to add location context to image prompt
            location_context = video_setting["location"][:50]  # Limit length
            if location_context and location_context.lower() not in image_prompt.lower():
                # Add at the beginning if it makes sense
                image_prompt = f"{location_context}, {image_prompt}".strip()
        
        if video_setting["lighting"] and not image_setting["lighting"]:
            # Add lighting to image prompt if missing
            if video_setting["lighting"].lower() not in image_prompt.lower():
                image_prompt = f"{image_prompt}, {video_setting['lighting']} lighting".strip()
        
        if video_setting["time_of_day"] and not image_setting["time_of_day"]:
            # Add time of day to image prompt if missing
            if video_setting["time_of_day"].lower() not in image_prompt.lower():
                image_prompt = f"{image_prompt}, {video_setting['time_of_day']}".strip()
        
        if video_setting["weather"] and not image_setting["weather"]:
            # Add weather to image prompt if missing
            if video_setting["weather"].lower() not in image_prompt.lower():
                image_prompt = f"{image_prompt}, {video_setting['weather']} weather".strip()
        
        # If image prompt has setting details that video prompt lacks, ensure video prompt mentions them
        if image_setting["location"] and not video_setting["location"]:
            # Video prompt should reference the same location - add context if missing
            location_context = image_setting["location"][:50]
            if location_context and location_context.lower() not in video_prompt.lower():
                # Add at the beginning of video prompt
                video_prompt = f"In {location_context}, {video_prompt}".strip()
        
        if image_setting["lighting"] and not video_setting["lighting"]:
            # Ensure video prompt mentions the same lighting
            if image_setting["lighting"].lower() not in video_prompt.lower():
                video_prompt = f"{video_prompt}, {image_setting['lighting']} lighting".strip()
        
        if image_setting["time_of_day"] and not video_setting["time_of_day"]:
            # Ensure video prompt mentions the same time of day
            if image_setting["time_of_day"].lower() not in video_prompt.lower():
                video_prompt = f"{video_prompt}, {image_setting['time_of_day']}".strip()
        
        if image_setting["weather"] and not video_setting["weather"]:
            # Ensure video prompt mentions the same weather
            if image_setting["weather"].lower() not in video_prompt.lower():
                video_prompt = f"{video_prompt}, {image_setting['weather']} weather".strip()
        
        return image_prompt, video_prompt
    
    def _ensure_actions_described(self, prompt: str, dialogue: str = "") -> str:
        """Ensure the video prompt explicitly describes character actions using clear action verbs."""
        # Ensure prompt is a string
        if not isinstance(prompt, str):
            prompt = str(prompt) if prompt else ""
        
        if not isinstance(dialogue, str):
            dialogue = str(dialogue) if dialogue else ""
        
        if not prompt:
            return prompt
        
        prompt_lower = prompt.lower()
        
        # Common action verbs that should be explicitly mentioned
        action_verbs = [
            "walking", "walk", "walks", "running", "run", "runs", "crouching", "crouch", "crouches",
            "standing", "stand", "stands", "sitting", "sit", "sits", "jumping", "jump", "jumps",
            "reaching", "reach", "reaches", "grabbing", "grab", "grabs", "turning", "turn", "turns",
            "looking", "look", "looks", "speaking", "speak", "speaks", "gesturing", "gesture", "gestures",
            "moving", "move", "moves", "approaching", "approach", "approaches", "entering", "enter", "enters",
            "leaving", "leave", "leaves", "exiting", "exit", "exits", "climbing", "climb", "climbs",
            "falling", "fall", "falls", "rising", "rise", "rises", "lifting", "lift", "lifts",
            "pushing", "push", "pushes", "pulling", "pull", "pulls", "throwing", "throw", "throws",
            "catching", "catch", "catches", "dodging", "dodge", "dodges", "hiding", "hide", "hides",
            "searching", "search", "searches", "examining", "examine", "examines", "opening", "open", "opens",
            "closing", "close", "closes", "picking up", "picks up", "putting down", "puts down"
        ]
        
        # Check if prompt contains explicit action verbs
        has_explicit_actions = any(verb in prompt_lower for verb in action_verbs)
        
        # If no explicit actions found, try to infer from dialogue or add generic action
        if not has_explicit_actions:
            # If there's dialogue, characters are likely speaking/interacting
            if dialogue:
                # Add action description based on dialogue context
                if "?" in dialogue or "what" in dialogue.lower() or "who" in dialogue.lower():
                    # Questioning - character might be looking, turning, gesturing
                    prompt = f"{prompt} Character looks around, turns toward the speaker, and gestures while speaking."
                elif "!" in dialogue or any(word in dialogue.lower() for word in ["help", "stop", "wait", "no"]):
                    # Urgent/excited - character might be moving quickly, gesturing
                    prompt = f"{prompt} Character moves quickly, gestures emphatically, and speaks with urgency."
                else:
                    # Normal dialogue - character speaks, may gesture or move slightly
                    prompt = f"{prompt} Character speaks, gestures naturally, and moves slightly during the conversation."
            else:
                # No dialogue - add a generic action based on scene type
                # Try to infer from prompt content
                if any(word in prompt_lower for word in ["door", "entrance", "exit"]):
                    prompt = f"{prompt} Character walks toward the door, reaches for the handle, and opens it."
                elif any(word in prompt_lower for word in ["table", "desk", "surface"]):
                    prompt = f"{prompt} Character approaches the table, reaches out, and examines objects on the surface."
                elif any(word in prompt_lower for word in ["window", "view", "outside"]):
                    prompt = f"{prompt} Character walks to the window, looks outside, and turns back."
                else:
                    # Generic action
                    prompt = f"{prompt} Character moves through the scene, walking and interacting with the environment."
        
        # Ensure actions are described in present continuous or present tense for clarity
        # This helps the AI video generator understand the action is ongoing
        
        return prompt.strip()
    
    def _split_storyboard_item(self, item: StoryboardItem, target_count: int, min_items: int, max_items: int, total_duration: int, screenplay: Screenplay) -> List[StoryboardItem]:
        """
        Split a single storyboard item into multiple items based on storyline and estimated duration.
        
        Args:
            item: The single StoryboardItem to split
            target_count: Target number of items to create
            min_items: Minimum number of items required
            max_items: Maximum number of items allowed
            total_duration: Total duration of the scene in seconds
            screenplay: The screenplay object for context
        
        Returns:
            List of StoryboardItem objects
        """
        # Determine actual number of items to create (within bounds)
        num_items = max(min_items, min(max_items, target_count))
        
        # Split the storyline into segments
        storyline = item.storyline if item.storyline else ""
        if not storyline:
            # If no storyline, use the video prompt as fallback
            storyline = item.prompt if item.prompt else "Scene progression"
        
        # Split storyline by sentences to find natural break points
        sentences = re.split(r'(?<=[.!?])\s+', storyline.strip())
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # If we have fewer sentences than items needed, split sentences further
        if len(sentences) < num_items:
            # Split longer sentences or combine multiple sentences per item
            segments = []
            sentences_per_segment = max(1, len(sentences) // num_items)
            for i in range(0, len(sentences), sentences_per_segment):
                segment = ' '.join(sentences[i:i+sentences_per_segment])
                if segment:
                    segments.append(segment)
            # If still not enough, pad with the last segment
            while len(segments) < num_items:
                segments.append(segments[-1] if segments else storyline)
        else:
            # More sentences than needed - group them
            sentences_per_segment = max(1, len(sentences) // num_items)
            segments = []
            for i in range(0, len(sentences), sentences_per_segment):
                segment = ' '.join(sentences[i:i+sentences_per_segment])
                if segment:
                    segments.append(segment)
            # Ensure we have exactly num_items
            if len(segments) > num_items:
                segments = segments[:num_items]
            elif len(segments) < num_items:
                # Pad with last segment
                while len(segments) < num_items:
                    segments.append(segments[-1] if segments else storyline)
        
        # Distribute total_duration across items with flexible per-item durations
        base_duration_per_item = total_duration // max(num_items, 1)
        durations = []
        remaining_duration = total_duration
        
        for i in range(num_items):
            if i == num_items - 1:
                duration = max(1, min(30, remaining_duration))
            else:
                segment_lower = segments[i].lower()
                has_dialogue_indicators = any(word in segment_lower for word in ["says", "said", "speaks", "tells", "asks", "replies", "responds", "exclaims"])
                if has_dialogue_indicators:
                    duration = max(1, min(30, base_duration_per_item + 2))
                else:
                    duration = max(1, min(30, base_duration_per_item))
            
            durations.append(duration)
            remaining_duration -= duration
        
        # Create new items
        split_items = []
        for i, (segment, duration) in enumerate(zip(segments, durations)):
            # Generate image and video prompts for this segment
            # Use AI to generate prompts for each segment, or derive from original
            
            # For image prompt: describe the first moment of this segment
            # Extract setting from original image prompt
            original_image_prompt = item.image_prompt if item.image_prompt else ""
            original_video_prompt = item.prompt if item.prompt else ""
            
            # Create a simplified image prompt for this segment
            # Use the original setting but adapt for this moment
            image_prompt = self._create_segment_image_prompt(segment, original_image_prompt, screenplay)
            
            # Create video prompt for this segment
            video_prompt = self._create_segment_video_prompt(segment, original_video_prompt, screenplay, item.dialogue)
            
            # Extract dialogue for this segment if applicable
            segment_dialogue = ""
            if item.dialogue and i == 0:  # Use original dialogue for first segment
                segment_dialogue = item.dialogue
            
            # Determine scene type based on segment content
            segment_lower = segment.lower()
            if any(word in segment_lower for word in ["dialogue", "says", "speaks", "tells"]):
                scene_type = SceneType.DIALOGUE
            elif any(word in segment_lower for word in ["enters", "approaches", "walks", "runs"]):
                scene_type = SceneType.ACTION
            elif i == 0:
                scene_type = SceneType.ESTABLISHING
            else:
                scene_type = item.scene_type
            
            # Camera notes
            camera_notes = item.camera_notes if item.camera_notes else ""
            if not camera_notes or len(camera_notes) < 20:
                scene_type_to_camera = {
                    SceneType.CLOSEUP: "Close-up shot, static camera",
                    SceneType.WIDE_SHOT: "Wide shot, static camera",
                    SceneType.ACTION: "Medium shot, dynamic camera movement",
                    SceneType.DIALOGUE: "Medium shot, static camera",
                    SceneType.ESTABLISHING: "Wide establishing shot, slow pan",
                }
                camera_notes = scene_type_to_camera.get(scene_type, "Medium shot, static camera")
            
            new_item = StoryboardItem(
                item_id=str(uuid.uuid4()),
                sequence_number=item.sequence_number + i,
                duration=duration,
                storyline=segment,
                image_prompt=(image_prompt or "").strip(),
                prompt=(video_prompt or "").strip(),
                visual_description=item.visual_description,
                dialogue=segment_dialogue,
                scene_type=scene_type,
                camera_notes=camera_notes
            )
            
            # Calculate render cost
            render_cost, cost_factors = self._calculate_render_cost(new_item)
            new_item.render_cost = render_cost
            new_item.render_cost_factors = cost_factors
            
            # Detect identity drift (need screenplay context - pass None if not available)
            # This will be set when item is added to scene
            new_item.identity_drift_warnings = []
            
            split_items.append(new_item)
        
        return split_items
    
    def _create_segment_image_prompt(self, segment: str, original_image_prompt: str, screenplay: Screenplay) -> str:
        """Create an image prompt for a storyline segment."""
        # Extract key elements from segment
        # Use original image prompt as base for setting consistency
        # Adapt for the specific moment described in segment
        
        # Try to extract setting details from original
        setting_keywords = ["room", "building", "street", "forest", "house", "office", "car", "outdoor", "indoor"]
        setting_context = ""
        for keyword in setting_keywords:
            if keyword in original_image_prompt.lower():
                # Extract surrounding context
                pattern = rf'[^.]*{keyword}[^.]*\.'
                matches = re.findall(pattern, original_image_prompt, re.IGNORECASE)
                if matches:
                    setting_context = matches[0]
                    break
        
        # Create a static description for this segment's first moment
        # Remove action verbs and focus on static positioning
        segment_static = segment
        # Replace action verbs with static descriptions
        action_replacements = {
            r'\benters\b': 'positioned at the entrance of',
            r'\bapproaches\b': 'positioned near',
            r'\bwalks\b': 'standing in',
            r'\bruns\b': 'positioned in',
            r'\bmoves\b': 'located in',
            r'\blooks\b': 'facing',
            r'\bturns\b': 'positioned facing',
        }
        for pattern, replacement in action_replacements.items():
            segment_static = re.sub(pattern, replacement, segment_static, flags=re.IGNORECASE)
        
        # Combine setting context with segment description
        if setting_context:
            image_prompt = f"{setting_context} {segment_static[:100]}. Static establishing shot showing the initial moment of this scene segment."
        else:
            image_prompt = f"{segment_static[:150]}. Static establishing shot, detailed composition, cinematic lighting."
        
        # Clean to ensure it's static
        image_prompt = self._clean_image_prompt(image_prompt)
        
        # Add atmosphere if specified
        if screenplay.atmosphere:
            image_prompt = f"{image_prompt} Atmosphere: {screenplay.atmosphere}."
        
        return image_prompt.strip()
    
    def _create_segment_video_prompt(self, segment: str, original_video_prompt: str, screenplay: Screenplay, dialogue: str = "") -> str:
        """Create a video prompt for a storyline segment."""
        # Use segment as base
        video_prompt = segment
        
        # Extract setting from original prompt
        setting_keywords = ["room", "building", "street", "forest", "house", "office", "car"]
        setting_context = ""
        for keyword in setting_keywords:
            if keyword in original_video_prompt.lower():
                pattern = rf'[^.]*{keyword}[^.]*\.'
                matches = re.findall(pattern, original_video_prompt, re.IGNORECASE)
                if matches:
                    setting_context = matches[0]
                    break
        
        # Ensure explicit actions are described
        video_prompt = self._ensure_actions_described(video_prompt, dialogue)
        
        # Add setting context if found
        if setting_context:
            video_prompt = f"{setting_context} {video_prompt}"
        
        # Optional: add atmosphere and music only when project uses generated_with_video audio strategy
        audio_strategy = getattr(screenplay, "audio_strategy", "generated_with_video")
        if audio_strategy == "generated_with_video" and screenplay.atmosphere:
            music_descriptions = {
                "Suspenseful": "Atmospheric music: Tense, suspenseful orchestral score with building tension",
                "Lighthearted": "Atmospheric music: Upbeat, cheerful melody with light instrumentation",
                "Dark": "Atmospheric music: Dark, ominous tones with deep bass and minor keys",
                "Mysterious": "Atmospheric music: Enigmatic, ethereal sounds with subtle mystery",
            }
            music_desc = music_descriptions.get(screenplay.atmosphere, f"Atmospheric music: Ambient score matching the {screenplay.atmosphere} tone")
            video_prompt = f"{video_prompt} {music_desc}"
        
        # Add dialogue if present
        if dialogue and dialogue not in video_prompt:
            video_prompt = f"{video_prompt} Dialogue: {dialogue}"
        
        return video_prompt.strip()
    
    def _fix_incomplete_json(self, json_str: str, error: json.JSONDecodeError) -> Optional[str]:
        """Try to fix incomplete/truncated JSON by closing open structures."""
        try:
            error_msg = str(error)
            # Check if error suggests incomplete JSON
            if 'Expecting' in error_msg:
                # Count open/close braces and brackets
                open_braces = json_str.count('{')
                close_braces = json_str.count('}')
                open_brackets = json_str.count('[')
                close_brackets = json_str.count(']')
                
                fixed = json_str.rstrip()
                
                # Handle incomplete last line - if it ends with a property name and colon but no value
                lines = fixed.split('\n')
                if lines:
                    last_line = lines[-1].strip()
                    # If last line is like "sequence_number": 12, (incomplete object)
                    if last_line.endswith(',') and ':' in last_line:
                        # Remove the incomplete line
                        lines = lines[:-1]
                        fixed = '\n'.join(lines).rstrip()
                        # Remove trailing comma from previous line if present
                        if lines:
                            last_complete_line = lines[-1].rstrip()
                            if last_complete_line.endswith(','):
                                lines[-1] = last_complete_line[:-1]
                                fixed = '\n'.join(lines).rstrip()
                    
                    # If last line is like "sequence_number": (no value)
                    elif ':' in last_line and not last_line.endswith(',') and not last_line.endswith('"') and not last_line.endswith('}'):
                        # Remove incomplete line
                        lines = lines[:-1]
                        fixed = '\n'.join(lines).rstrip()
                        # Remove trailing comma from previous line if present
                        if lines:
                            last_complete_line = lines[-1].rstrip()
                            if last_complete_line.endswith(','):
                                lines[-1] = last_complete_line[:-1]
                                fixed = '\n'.join(lines).rstrip()
                
                # Close incomplete array items
                if open_brackets > close_brackets:
                    # Remove trailing comma if present
                    fixed = fixed.rstrip().rstrip(',')
                    indent_level = max(0, (fixed.count('{') - fixed.count('}')) - 1)
                    fixed += '\n' + '    ' * indent_level + ']'
                
                # Close incomplete objects (items in the array)
                if open_braces > close_braces:
                    # Remove trailing comma if present
                    fixed = fixed.rstrip().rstrip(',')
                    # Close each incomplete object
                    for _ in range(open_braces - close_braces):
                        indent_level = max(0, (fixed.count('{') - fixed.count('}')) - 1)
                        fixed += '\n' + '    ' * indent_level + '}'
                
                # Close the array
                if open_brackets > close_brackets or (fixed.count('[') > fixed.count(']')):
                    fixed = fixed.rstrip().rstrip(',')
                    indent_level = max(0, (fixed.count('{') - fixed.count('}')) - 1)
                    fixed += '\n' + '    ' * indent_level + ']'
                
                # Close the root object
                if fixed.count('{') > fixed.count('}'):
                    fixed = fixed.rstrip().rstrip(',')
                    # Remove any trailing incomplete string quotes
                    fixed = fixed.rstrip().rstrip('"')
                    fixed += '\n}'
                
                return fixed
        except Exception:
            pass
        return None
    
    def _fix_json_at_location(self, json_str: str, error: json.JSONDecodeError) -> Optional[str]:
        """Try to fix JSON at the specific error location."""
        try:
            error_msg = str(error)
            # Extract line and column from error message
            line_match = re.search(r'line (\d+)', error_msg)
            col_match = re.search(r'column (\d+)', error_msg)
            
            if not line_match or not col_match:
                # Try to get from error object attributes
                if hasattr(error, 'lineno') and hasattr(error, 'colno'):
                    line_num = error.lineno - 1
                    col_num = error.colno - 1
                else:
                    return None
            else:
                line_num = int(line_match.group(1)) - 1  # 0-indexed
                col_num = int(col_match.group(1)) - 1  # 0-indexed
            
            lines = json_str.split('\n')
            if not (0 <= line_num < len(lines)):
                return None
            
            line = lines[line_num]
            if col_num >= len(line):
                return None
            
            # Try multiple fix strategies at the error location
            fixes_to_try = []
            
            # Strategy 1: Insert comma before error location
            if col_num > 0:
                before_char = line[col_num-1]
                error_char = line[col_num] if col_num < len(line) else ''
                
                # If we have a value character followed by a key or structure, add comma
                if before_char not in ',{[(' and error_char in '"{[0123456789':
                    fixed_line = line[:col_num] + ',' + line[col_num:]
                    lines_copy = lines.copy()
                    lines_copy[line_num] = fixed_line
                    fixes_to_try.append('\n'.join(lines_copy))
            
            # Strategy 2: Look backwards for missing comma after a value
            if col_num > 1:
                # Check if we're after a closing quote, bracket, or brace
                for i in range(max(0, col_num-10), col_num):
                    char = line[i] if i < len(line) else ''
                    if char in '}"' and i+1 < col_num:
                        # Check if there's a comma after this
                        next_chars = line[i+1:col_num].strip()
                        if next_chars and not next_chars.startswith(','):
                            # Try inserting comma after this character
                            fixed_line = line[:i+1] + ',' + line[i+1:]
                            lines_copy = lines.copy()
                            lines_copy[line_num] = fixed_line
                            fixes_to_try.append('\n'.join(lines_copy))
                            break
            
            # Strategy 3: Look for pattern like "value" "key" and add comma
            pattern_match = re.search(r'("[^"]+")\s*"([^"]+)":', line[:col_num+20])
            if pattern_match and pattern_match.end() <= col_num + 5:
                fixed_line = line[:pattern_match.end(1)] + ',' + line[pattern_match.end(1):]
                lines_copy = lines.copy()
                lines_copy[line_num] = fixed_line
                fixes_to_try.append('\n'.join(lines_copy))
            
            # Try the first fix that works
            for fix in fixes_to_try:
                try:
                    # Quick validation - try parsing
                    json.loads(fix)
                    return fix
                except:
                    continue
            
            return None
        except Exception:
            return None
    
    def _repair_json(self, json_str: str) -> str:
        """Attempt to repair common JSON issues."""
        # Remove markdown code blocks if present
        json_str = re.sub(r'```json\s*', '', json_str)
        json_str = re.sub(r'```\s*', '', json_str)
        
        # Remove JSON comments (// and /* */ style comments)
        # Remove single-line comments (// ...)
        json_str = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
        # Remove multi-line comments (/* ... */)
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
        
        # Remove leading/trailing whitespace
        json_str = json_str.strip()
        
        # Fix: root object ends with ] instead of } (e.g. "acts": [...] ] - extra ] and missing })
        if json_str.startswith('{') and not json_str.endswith('}'):
            open_braces = json_str.count('{')
            close_braces = json_str.count('}')
            open_brackets = json_str.count('[')
            close_brackets = json_str.count(']')
            # Remove extra trailing ] (e.g. ... ] ] -> ... ])
            if close_brackets > open_brackets:
                excess = close_brackets - open_brackets
                for _ in range(excess):
                    json_str = json_str.rstrip().rstrip(',').rstrip()
                    if json_str.endswith(']'):
                        json_str = json_str[:-1].rstrip()
            # Add missing } for root object
            open_braces = json_str.count('{')
            close_braces = json_str.count('}')
            if open_braces > close_braces:
                json_str = json_str.rstrip().rstrip(',').rstrip()
                if not json_str.endswith('}'):
                    for _ in range(open_braces - close_braces):
                        json_str += '\n}'
        
        # Fix malformed array endings - replace ")" with "]" when it should close an array
        # Pattern: Find closing double quote followed by ) and then whitespace/newline and closing structure
        # This handles cases where the AI incorrectly uses ) instead of ] to close arrays
        # Match: " (closing quote) followed by ), then whitespace/newlines and } or , or ]
        # Use DOTALL flag to match across newlines
        json_str = re.sub(r'("\s*)\)(\s*[,}\]]|\n)', r'\1]\2', json_str, flags=re.DOTALL)
        # Also handle the case with no whitespace: ")" followed directly by } or ,
        json_str = re.sub(r'(")\)([,}\]])', r'\1]\2', json_str)
        
        # Try to fix trailing commas in arrays and objects (multiple passes for nested structures)
        for _ in range(5):  # Multiple passes to catch nested trailing commas
            json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        
        # Fix missing commas between object properties and values
        # Pattern: } or ] followed by " (new key) or number or { or [
        json_str = re.sub(r'([}\]"])\s*"([^"]+)":', r'\1,"\2":', json_str)  # Missing comma before new key
        json_str = re.sub(r'([}\]"])\s*(\d)', r'\1,\2', json_str)  # Missing comma before number
        json_str = re.sub(r'([}\]"])\s*\{', r'\1,{', json_str)  # Missing comma before object
        json_str = re.sub(r'([}\]"])\s*\[', r'\1,[', json_str)  # Missing comma before array
        
        # Fix missing commas after values before new keys
        json_str = re.sub(r'(")\s*"([^"]+)":', r'\1,"\2":', json_str)  # String value to new key
        json_str = re.sub(r'(\d)\s*"([^"]+)":', r'\1,"\2":', json_str)  # Number to new key
        json_str = re.sub(r'(true|false|null)\s*"([^"]+)":', r'\1,"\2":', json_str)  # Boolean/null to new key
        json_str = re.sub(r'(\})\s*"([^"]+)":', r'\1,"\2":', json_str)  # Object end to new key
        json_str = re.sub(r'(\])\s*"([^"]+)":', r'\1,"\2":', json_str)  # Array end to new key
        
        # Fix unquoted string values (e.g., "name": Dr. Sarah Johnson, should be "name": "Dr. Sarah Johnson",)
        # Pattern: "key": unquoted_text, where unquoted_text can span multiple lines
        
        # Process line by line, looking for unquoted values after colons
        lines = json_str.split('\n')
        repaired_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Look for pattern: "key": unquoted_value
            # Match colon followed by whitespace and then unquoted text
            colon_match = re.search(r'("([^"]+)":\s*)', line)
            if colon_match:
                key_with_colon = colon_match.group(1)
                value_start = colon_match.end()
                value_part = line[value_start:].strip()
                
                # Check if value is unquoted (doesn't start with ", {, [, and not a number/boolean/null)
                if value_part and not value_part.startswith('"') and not value_part.startswith('{') and not value_part.startswith('['):
                    # Check if it's a number, boolean, or null
                    if not re.match(r'^\s*(-?\d+\.?\d*|true|false|null)\s*', value_part):
                        # This is an unquoted string - find where it ends
                        # It ends at: comma followed by newline and new key, or closing brace
                        unquoted_value = value_part
                        rest = ""
                        
                        # Check if value continues on next lines
                        j = i + 1
                        while j < len(lines):
                            next_line = lines[j].strip()
                            # If next line starts with " or { or }, the value ended
                            if next_line.startswith('"') or next_line.startswith('{') or next_line.startswith('}'):
                                break
                            # If next line starts with ], the value ended
                            if next_line.startswith(']'):
                                break
                            # Otherwise, it's continuation of the unquoted value
                            unquoted_value += ' ' + next_line
                            j += 1
                        
                        # Find the actual end of the value (comma, closing brace, or closing bracket)
                        # Look for comma that's followed by newline and new key, or closing brace/bracket
                        end_match = None
                        # Try to find comma followed by whitespace and newline (end of property)
                        comma_pos = unquoted_value.rfind(',')
                        if comma_pos >= 0:
                            # Check if comma is followed by just whitespace (end of value)
                            after_comma = unquoted_value[comma_pos+1:].strip()
                            if not after_comma or after_comma in '}]':
                                end_match = (comma_pos, ',')
                        
                        # If no comma found, check for closing brace/bracket
                        if not end_match:
                            if unquoted_value.rstrip().endswith('}'):
                                end_match = (len(unquoted_value.rstrip()) - 1, '}')
                            elif unquoted_value.rstrip().endswith(']'):
                                end_match = (len(unquoted_value.rstrip()) - 1, ']')
                        
                        if end_match:
                            end_pos, end_char = end_match
                            actual_value = unquoted_value[:end_pos].strip()
                            rest = end_char + unquoted_value[end_pos+1:].strip()
                        else:
                            actual_value = unquoted_value.strip()
                            rest = ""
                        
                        # Quote the value
                        fixed_line = key_with_colon + ' "' + actual_value + '"' + rest
                        repaired_lines.append(fixed_line)
                        i = j  # Skip lines we processed
                        continue
            
            repaired_lines.append(line)
            i += 1
        
        json_str = '\n'.join(repaired_lines)
        
        # Fix unescaped quotes in string values (basic attempt - be careful)
        # Only fix if it's clearly inside a string value (between : and , or })
        lines = json_str.split('\n')
        repaired_lines = []
        for line in lines:
            # If line has a colon, try to fix unescaped quotes in the value part
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key_part = parts[0]
                    value_part = parts[1]
                    # Only fix if value starts with quote and has unescaped quotes
                    if value_part.strip().startswith('"') and not value_part.strip().endswith('",') and not value_part.strip().endswith('"'):
                        # Try to escape unescaped quotes (but not the first or last)
                        # This is tricky, so we'll be conservative
                        pass  # Skip for now to avoid breaking valid JSON
                repaired_lines.append(line)
            else:
                repaired_lines.append(line)
        json_str = '\n'.join(repaired_lines)
        
        # Fix unescaped newlines inside string values
        # JSON strings can't have literal newlines - they must be escaped as \n
        # Process character by character to properly handle strings
        
        result = []
        i = 0
        in_string = False
        escape_next = False
        
        while i < len(json_str):
            char = json_str[i]
            
            if escape_next:
                # Previous char was backslash - this char is escaped
                result.append(char)
                escape_next = False
                i += 1
                continue
            
            if char == '\\':
                # Escape character
                result.append(char)
                escape_next = True
                i += 1
                continue
            
            if char == '"':
                if in_string:
                    # Inside a string: this " may be start of embedded nickname (e.g. "JIM", "EVA")
                    # Look ahead for pattern: letters/spaces then closing "
                    rest = json_str[i + 1:]
                    nick_match = re.match(r'^([A-Za-z][A-Za-z.\s]{0,50})"', rest)
                    if nick_match:
                        word = nick_match.group(1)
                        result.append('\\"')
                        result.append(word)
                        result.append('\\"')
                        i += 1 + len(word) + 1  # skip opening ", word, closing "
                        continue
                # Structural quote (start/end of string)
                in_string = not in_string
                result.append(char)
                i += 1
                continue
            
            if in_string:
                # We're inside a string value
                if char == '\n':
                    # Unescaped newline in string - escape it
                    result.append('\\n')
                    i += 1
                elif char == '\r':
                    # Unescaped carriage return in string
                    if i + 1 < len(json_str) and json_str[i + 1] == '\n':
                        # \r\n - escape as \n
                        result.append('\\n')
                        i += 2
                    else:
                        # Just \r - escape it
                        result.append('\\r')
                        i += 1
                elif char == '\t':
                    # Tab in string - escape it
                    result.append('\\t')
                    i += 1
                elif ord(char) < 32 and char not in '\n\r\t':
                    # Other control characters - escape as unicode
                    result.append(f'\\u{ord(char):04x}')
                    i += 1
                else:
                    # Normal character
                    result.append(char)
                    i += 1
            else:
                # Outside string - keep as is (newlines are allowed for formatting)
                result.append(char)
                i += 1
        
        json_str = ''.join(result)
        
        # After fixing newlines, check if JSON is incomplete and close it
        open_braces = json_str.count('{')
        close_braces = json_str.count('}')
        open_brackets = json_str.count('[')
        close_brackets = json_str.count(']')
        
        if open_braces > close_braces or open_brackets > close_brackets:
            # Truncation recovery: if the string ends inside an open quote,
            # close it first so that brace/bracket closure produces valid JSON
            stripped = json_str.rstrip()
            in_str = False
            esc = False
            for ch in stripped:
                if esc:
                    esc = False
                    continue
                if ch == '\\':
                    esc = True
                    continue
                if ch == '"':
                    in_str = not in_str
            if in_str:
                json_str = stripped + '"'

            # Strip the last incomplete array element when it's clearly truncated.
            # Pattern: find the last complete }, then drop everything after it
            # up to (but not including) any structural ] or } closers we'll add.
            last_complete_brace = json_str.rfind('}')
            last_open_brace = json_str.rfind('{')
            if last_open_brace > last_complete_brace:
                # There's an unclosed { after the last } — likely a truncated item
                # Trim back to the last complete }
                json_str = json_str[:last_complete_brace + 1]
                json_str = json_str.rstrip().rstrip(',')
                print("TRUNCATION REPAIR: Stripped incomplete trailing object")

            # Recount after potential truncation trimming
            open_braces = json_str.count('{')
            close_braces = json_str.count('}')
            open_brackets = json_str.count('[')
            close_brackets = json_str.count(']')

            if open_brackets > close_brackets:
                for _ in range(open_brackets - close_brackets):
                    json_str = json_str.rstrip().rstrip(',')
                    json_str += '\n]'
            if open_braces > close_braces:
                for _ in range(open_braces - close_braces):
                    json_str = json_str.rstrip().rstrip(',')
                    json_str += '\n}'
        
        return json_str
    
    def _extract_and_parse_json(self, content: str, prefer_array: bool = False):
        """Extract and parse JSON from AI response with multiple fallback strategies.
        
        Args:
            content: The AI response content
            prefer_array: If True, prioritize finding and parsing arrays over objects
        """
        import re
        
        # PRIORITY 0: If prefer_array is True, check for array patterns first
        # This is used for entity extraction where we expect [...] responses
        if prefer_array:
            array_match = re.search(r'(\[[\s\S]*?\])', content, re.DOTALL)
            if array_match:
                array_str = array_match.group(1)
                try:
                    # Try to parse as JSON array
                    parsed = json.loads(array_str)
                    if isinstance(parsed, list):
                        print(f"DEBUG _extract_and_parse_json: Successfully parsed array with {len(parsed)} items")
                        return parsed
                except json.JSONDecodeError:
                    # Array might be incomplete, try to repair
                    open_brackets = array_str.count('[')
                    close_brackets = array_str.count(']')
                    if open_brackets > close_brackets:
                        # Try adding missing brackets
                        repaired = array_str.rstrip()
                        for _ in range(open_brackets - close_brackets):
                            repaired += ']'
                        try:
                            parsed = json.loads(repaired)
                            if isinstance(parsed, list):
                                print(f"DEBUG _extract_and_parse_json: Repaired and parsed array with {len(parsed)} items")
                                return parsed
                        except:
                            pass
        
        # Strategy 0: Try direct parse first (in case content is already clean JSON)
        content_stripped = content.strip()
        
        # If content is wrapped in markdown code blocks (```json ... ```), strip them first
        if content_stripped.startswith('```'):
            try:
                repaired = self._repair_json(content_stripped)
                if repaired != content_stripped:
                    content_stripped = repaired.strip()
            except Exception:
                pass
        
        # When content starts with {, try repair first (fixes extra ] and missing } at end)
        if content_stripped.startswith('{'):
            try:
                repaired = self._repair_json(content_stripped)
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
        
        # Handle both objects {...} and arrays [...]
        if (content_stripped.startswith('{') and content_stripped.endswith('}')) or \
           (content_stripped.startswith('[') and content_stripped.endswith(']')):
            try:
                repaired = self._repair_json(content_stripped)
                return json.loads(repaired)
            except json.JSONDecodeError as e:
                # If it's incomplete, try to fix it
                if content_stripped.startswith('{'):
                    open_braces = content_stripped.count('{')
                    close_braces = content_stripped.count('}')
                    if open_braces > close_braces:
                        fixed = content_stripped.rstrip().rstrip(',').rstrip('"')
                        for _ in range(open_braces - close_braces):
                            fixed += '\n}'
                        try:
                            return json.loads(fixed)
                        except:
                            pass
                elif content_stripped.startswith('['):
                    open_brackets = content_stripped.count('[')
                    close_brackets = content_stripped.count(']')
                    if open_brackets > close_brackets:
                        fixed = content_stripped.rstrip().rstrip(',').rstrip('"')
                        for _ in range(open_brackets - close_brackets):
                            fixed += '\n]'
                        try:
                            return json.loads(fixed)
                        except:
                            pass
        
        # Strategy 0b: Content starts with { but has trailing text - extract first complete object
        if content_stripped.startswith('{') and not content_stripped.endswith('}'):
            brace_count = 0
            in_str = False
            escape_next = False
            start_idx = content.find('{')
            if start_idx >= 0:
                for i in range(start_idx, len(content)):
                    c = content[i]
                    if escape_next:
                        escape_next = False
                        continue
                    if c == '\\':
                        escape_next = True
                        continue
                    if c == '"':
                        in_str = not in_str
                        continue
                    if not in_str:
                        if c == '{':
                            brace_count += 1
                        elif c == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                try:
                                    json_str = content[start_idx:i + 1]
                                    repaired = self._repair_json(json_str)
                                    return json.loads(repaired)
                                except json.JSONDecodeError:
                                    pass
                                break
        
        # Strategy 0.5: Try to find JSON after common prefixes
        import re
        # Updated patterns to match both objects and arrays
        prefix_patterns = [
            r'(?:Here\'?s? (?:my |the )?(?:extracted )?JSON (?:array|response|format)?:?\s*)(\[.*\])',
            r'(?:JSON (?:array|response|format):?\s*)(\[.*\])',
            r'(?:Response:?\s*)(\[.*\])',
            r'(?:Here\'?s? (?:my |the )?response (?:in |as )?JSON format:?\s*)(\{.*\})',
            r'(?:JSON (?:response|format):?\s*)(\{.*\})',
            r'(?:Response:?\s*)(\{.*\})',
        ]
        for pattern in prefix_patterns:
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                json_str = match.group(1) if match.groups() else match.group(0)
                # Try to extract complete JSON by balancing braces
                try:
                    # Find the first { and last matching }
                    brace_count = 0
                    in_string = False
                    escape_next = False
                    start_idx = json_str.find('{')
                    if start_idx >= 0:
                        json_end = -1
                        for i in range(start_idx, len(json_str)):
                            char = json_str[i]
                            if escape_next:
                                escape_next = False
                                continue
                            if char == '\\':
                                escape_next = True
                                continue
                            if char == '"' and not escape_next:
                                in_string = not in_string
                                continue
                            if not in_string:
                                if char == '{':
                                    brace_count += 1
                                elif char == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        json_end = i + 1
                                        break
                        
                        if json_end > start_idx:
                            json_content = json_str[start_idx:json_end]
                            repaired = self._repair_json(json_content)
                            return json.loads(repaired)
                except:
                    continue
        
        # Strategy 1: Try to find JSON in code blocks
        code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if code_block_match:
            try:
                json_str = code_block_match.group(1)
                json_str = self._repair_json(json_str)
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        
        # Strategy 2: Try to find JSON object with balanced braces (handling strings properly)
        # Find the first { and then find the matching }
        brace_count = 0
        start_idx = -1
        in_string = False
        escape_next = False
        
        for i, char in enumerate(content):
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if not in_string:
                if char == '{':
                    if start_idx == -1:
                        start_idx = i
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_idx != -1:
                        try:
                            json_str = content[start_idx:i+1]
                            json_str = self._repair_json(json_str)
                            return json.loads(json_str)
                        except json.JSONDecodeError:
                            # Try next JSON object
                            start_idx = -1
                            brace_count = 0
                            in_string = False
                            escape_next = False
        
        # Strategy 2.5: If we found a start but no end (incomplete JSON), try to repair it
        if start_idx != -1 and brace_count > 0:
            # We have an incomplete JSON - try to close it
            json_str = content[start_idx:]
            # Try to repair incomplete JSON
            try:
                # Add missing closing braces
                for _ in range(brace_count):
                    json_str = json_str.rstrip().rstrip(',').rstrip('"')
                    # Remove any trailing incomplete property
                    if json_str.rstrip().endswith(':'):
                        # Find last complete property
                        last_comma = json_str.rfind(',')
                        if last_comma > 0:
                            json_str = json_str[:last_comma]
                    json_str += '\n}'
                
                json_str = self._repair_json(json_str)
                return json.loads(json_str)
            except:
                pass
        
        # Strategy 3: Extract JSON from content (handles incomplete JSON)
        json_start = content.find('{')
        if json_start >= 0:
            # Take everything from first { to end
            json_str = content[json_start:]
        else:
            json_str = content
        
        # Check if JSON is incomplete (missing closing braces) and fix it immediately
        open_braces = json_str.count('{')
        close_braces = json_str.count('}')
        open_brackets = json_str.count('[')
        close_brackets = json_str.count(']')
        
        if open_braces > close_braces or open_brackets > close_brackets:
            # Fix incomplete JSON immediately
            fixed = json_str.rstrip()
            
            # Remove trailing incomplete content (unclosed strings, incomplete properties)
            # If it ends with a quote but no closing quote, remove it
            if fixed.endswith('"') and fixed.count('"') % 2 != 0:
                # Find the last complete property
                last_complete_brace = fixed.rfind('}')
                if last_complete_brace > 0:
                    fixed = fixed[:last_complete_brace+1]
            
            # Remove trailing commas and incomplete property values
            # If ends with a number or value without comma/brace, it might be incomplete
            fixed = fixed.rstrip()
            # Check if last line is incomplete (ends with a value but no closing structure)
            lines = fixed.split('\n')
            if lines:
                last_line = lines[-1].strip()
                # If last line is an incomplete property (ends with number, null, true, false but no }, ], or ,)
                # BUT: If it ends with ", it's a complete string value - don't remove it
                if (re.search(r':\s*\d+\s*$', last_line) or 
                    (last_line.endswith('null') and not last_line.endswith('null,') and not last_line.endswith('null}')) or
                    (last_line.endswith('true') and not last_line.endswith('true,') and not last_line.endswith('true}')) or
                    (last_line.endswith('false') and not last_line.endswith('false,') and not last_line.endswith('false}'))):
                    # This is an incomplete property - find the last complete line
                    last_complete_idx = -1
                    for i in range(len(lines) - 2, -1, -1):  # Start from second-to-last line
                        line = lines[i].strip()
                        if line.endswith('}') or line.endswith(']') or line.endswith(','):
                            last_complete_idx = i
                            break
                    
                    if last_complete_idx >= 0:
                        fixed = '\n'.join(lines[:last_complete_idx+1])
                        # Remove trailing comma from last line if it ends with ,
                        if lines[last_complete_idx].strip().endswith(','):
                            lines_fixed = fixed.split('\n')
                            if lines_fixed:
                                lines_fixed[-1] = lines_fixed[-1].rstrip().rstrip(',')
                                fixed = '\n'.join(lines_fixed)
                    else:
                        # No complete line found - remove last incomplete line
                        fixed = '\n'.join(lines[:-1]).rstrip()
                        # Remove trailing comma if present
                        fixed = fixed.rstrip().rstrip(',')
            
            # Close incomplete structures in the correct nested order
            # We need to close from innermost to outermost
            # Strategy: Find the last incomplete structure and close it, then work outward
            
            # Remove any trailing incomplete value (like a number without closing)
            # If the last line doesn't end with }, ], or , but has a colon, it's incomplete
            lines = fixed.split('\n')
            if lines:
                last_line = lines[-1].strip()
                # If last line has a colon but doesn't end properly, it might be incomplete
                if ':' in last_line and not last_line.endswith('}') and not last_line.endswith(']') and not last_line.endswith(','):
                    # Check if it's a number or value
                    if re.search(r':\s*\d+\s*$', last_line):
                        # It's an incomplete property - remove it
                        lines = lines[:-1]
                        fixed = '\n'.join(lines).rstrip()
                        # Remove trailing comma from previous line if present
                        if lines and lines[-1].rstrip().endswith(','):
                            lines[-1] = lines[-1].rstrip()[:-1]
                            fixed = '\n'.join(lines).rstrip()
            
            # Before closing, check if the last line is a complete property that needs its object closed
            # Example: "scene_type": "action" needs a closing }
            lines = fixed.split('\n')
            if lines:
                last_line = lines[-1].strip()
                # If last line is a complete property (ends with " or value) but no closing brace
                if ((':' in last_line) and 
                    not last_line.endswith('}') and 
                    not last_line.endswith(']') and 
                    not last_line.endswith(',') and
                    (last_line.endswith('"') or re.search(r':\s*"([^"]*)"\s*$', last_line) or 
                     re.search(r':\s*(\d+|true|false|null)\s*$', last_line))):
                    # This is a complete property - the object needs to be closed
                    # Don't remove it, just ensure we close the object properly
                    pass
            
            # Recalculate counts after any modifications
            open_braces = fixed.count('{')
            close_braces = fixed.count('}')
            open_brackets = fixed.count('[')
            close_brackets = fixed.count(']')
            
            # Close incomplete arrays first (inner structures)
            if open_brackets > close_brackets:
                for _ in range(open_brackets - close_brackets):
                    fixed = fixed.rstrip().rstrip(',')
                    fixed += '\n]'
            
            # Close incomplete objects
            # For storyboard_items structure, we need to close:
            # 1. The last item object (if incomplete)
            # 2. The array (if incomplete) 
            # 3. The root object (if incomplete)
            if open_braces > close_braces:
                # Check if we're in a storyboard_items array context
                if '"storyboard_items"' in fixed or 'storyboard_items' in fixed:
                    # Find where the array starts
                    array_start = fixed.find('[')
                    if array_start >= 0:
                        # Count braces after the array starts to see how many item objects we have
                        # We need to close: last item object, then array, then root object
                        # But since we're just appending }, they'll close in reverse order of opening
                        # which is correct (innermost first)
                        pass
                
                # Close all missing braces (will close from innermost to outermost)
                # This will close: last item object, then array bracket (already closed above), then root object
                for _ in range(open_braces - close_braces):
                    fixed = fixed.rstrip().rstrip(',')
                    fixed += '\n}'
            
            json_str = fixed
            
            # Repair JSON (fixes newlines, comments, etc.)
            json_str = self._repair_json(json_str)
            
            # Try parsing the fixed JSON immediately
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # If still fails, try with additional repair
                try:
                    repaired = self._repair_json(json_str)
                    return json.loads(repaired)
                except:
                    pass
        
        # Try multiple repair strategies
        repair_attempts = [
            json_str,  # Original (possibly fixed)
            self._repair_json(json_str),  # Basic repair
        ]
        
        # Additional repair attempts with specific fixes
        repaired = self._repair_json(json_str)
        repair_attempts.extend([
            re.sub(r',(\s*[}\]])', r'\1', repaired),  # Remove trailing commas
            re.sub(r'([}\]"])\s*"([^"]+)":', r'\1,"\2":', repaired),  # Add missing commas before keys
            re.sub(r'([}\]"])\s*(\d)', r'\1,\2', repaired),  # Add missing commas before numbers
        ])
        
        for attempt in repair_attempts:
            try:
                return json.loads(attempt)
            except json.JSONDecodeError as e:
                last_error = e
                # Try location-specific repair
                fixed_attempt = self._fix_json_at_location(attempt, e)
                if fixed_attempt:
                    try:
                        return json.loads(fixed_attempt)
                    except:
                        pass
                
                # Try to fix incomplete JSON (truncated response)
                incomplete_fix = self._fix_incomplete_json(attempt, e)
                if incomplete_fix:
                    try:
                        return json.loads(incomplete_fix)
                    except:
                        pass
                continue
        
        # Last resort: Try to extract partial data from incomplete JSON
        partial_data = self._extract_partial_json(json_str)
        if partial_data:
            # Check if it has the structure we need (for story outline, we need subplots, characters, conclusion)
            if "subplots" in partial_data or "characters" in partial_data or "conclusion" in partial_data:
                return partial_data
            # For storyboard items
            if partial_data.get("storyboard_items"):
                return partial_data
            # For story framework (acts, scenes)
            if partial_data.get("acts") or partial_data.get("title"):
                return partial_data
            
            # If all attempts fail, save the problematic content for debugging
            import os
            debug_file = "debug_json_error.json"
            try:
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(content)
            except:
                pass
            
            # Provide helpful error with line/column info
            error_info = f"Could not parse JSON: {str(last_error)}"
            if hasattr(last_error, 'lineno') and hasattr(last_error, 'colno'):
                error_info += f" (Line {last_error.lineno}, Column {last_error.colno})"
            error_info += f"\n\nContent preview (first 1000 chars):\n{content[:1000]}..."
            if os.path.exists(debug_file):
                error_info += f"\n\nFull content saved to: {debug_file}"
            raise Exception(error_info)
        
        # If we get here, no JSON was found at all
        # Try one more time: look for any { character and try to extract from there
        json_start = content.find('{')
        if json_start >= 0:
            # Found a {, try to extract everything from there
            remaining = content[json_start:]
            
            # Try to find balanced braces
            brace_count = 0
            end_idx = -1
            for i, char in enumerate(remaining):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            
            if end_idx > 0:
                # Found balanced JSON
                json_str = remaining[:end_idx]
                try:
                    repaired = self._repair_json(json_str)
                    return json.loads(repaired)
                except:
                    pass
            else:
                # Unbalanced, try to close it
                open_braces = remaining.count('{')
                close_braces = remaining.count('}')
                open_brackets = remaining.count('[')
                close_brackets = remaining.count(']')
                
                # Remove incomplete last line if it ends with a value but no closing structure
                remaining_stripped = remaining.rstrip()
                lines = remaining_stripped.split('\n')
                if lines:
                    last_line = lines[-1].strip()
                    # Check if last line is incomplete (ends with number, string value, null, true, false but no }, ], or ,)
                    if (re.search(r':\s*\d+\s*$', last_line) or 
                        (last_line.endswith('"') and ':' in last_line and not last_line.endswith('",') and not last_line.endswith('"}')) or
                        ((last_line.endswith('null') or last_line.endswith('true') or last_line.endswith('false')) and 
                         not last_line.endswith('},') and not last_line.endswith('}'))):
                        # Remove incomplete last line
                        remaining_stripped = '\n'.join(lines[:-1]).rstrip()
                        remaining_stripped = remaining_stripped.rstrip().rstrip(',')
                        remaining = remaining_stripped
                        # Recalculate counts after removing incomplete line
                        open_braces = remaining.count('{')
                        close_braces = remaining.count('}')
                        open_brackets = remaining.count('[')
                        close_brackets = remaining.count(']')
                
                # Close incomplete arrays first
                if open_brackets > close_brackets:
                    for _ in range(open_brackets - close_brackets):
                        remaining = remaining.rstrip().rstrip(',')
                        remaining += '\n]'
                
                # Close incomplete objects
                if open_braces > close_braces:
                    for _ in range(open_braces - close_braces):
                        remaining = remaining.rstrip().rstrip(',')
                        remaining += '\n}'
                    
                    try:
                        repaired = self._repair_json(remaining)
                        return json.loads(repaired)
                    except:
                        pass
        
        # Save content for debugging
        import os
        debug_file = "debug_json_error.json"
        try:
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(content)
        except:
            pass
        
        error_msg = "Could not find JSON in AI response."
        if content:
            error_msg += f"\n\nResponse preview (first 500 chars):\n{content[:500]}..."
            if len(content) > 500:
                error_msg += f"\n\n(Response is {len(content)} characters long)"
        else:
            error_msg += "\n\nAI returned an empty response."
        
        if os.path.exists(debug_file):
            error_msg += f"\n\nFull response saved to: {debug_file}"
        
        raise Exception(error_msg)
    
    @staticmethod
    def _strip_scene_headings(text: str) -> str:
        """Remove screenplay scene headings (INT./EXT. lines) that confuse entity extraction.

        Lines like 'INT. PENDERGAST MANSION - NIGHT' contain CAPS words (NIGHT, DAY)
        and location names that are NOT characters. Stripping them prevents the extraction
        AI from treating 'NIGHT' or building names as character entities.
        """
        if not text:
            return text
        return re.sub(
            r"^(INT\.|EXT\.|INT/EXT\.|INT |EXT ).*$",
            "",
            text,
            flags=re.MULTILINE | re.IGNORECASE,
        ).strip()

    def _extract_entities_from_text(self, text: str, entity_types: List[str] = None, screenplay: Optional[Screenplay] = None) -> List[Dict[str, str]]:
        """Extract recurring entities (vehicles, characters, objects, environments) from text using AI.
        
        When screenplay is provided and character_registry_frozen, Wizard character list is absolute
        authority: names in the registry are always classified as character and never as environment/object/vehicle.
        """
        if not self._adapter:
            return []
        
        # Strip scene headings to prevent NIGHT/DAY/building names from being extracted as characters
        text = self._strip_scene_headings(text)
        
        if entity_types is None:
            entity_types = ["vehicle", "character", "creature", "weapon", "object", "environment"]
        
        entity_types_str = ", ".join(entity_types)
        
        prompt = f"""Analyze the following text and identify ALL visual entities that appear in it.
Focus on finding specific, named entities that need to be visually depicted.

Entity types to look for: {entity_types_str}

Text to analyze:
{text[:2500]}

ENTITY MARKUP (Wizard convention): Text inside _underscores_ = locations/environments ONLY. NEVER extract individual words from _underlined_ text as characters. Example: "_THE DARKENED LABORATORY_" is ONE environment—do NOT extract "DARKENED" or "LABORATORY" as characters.

CRITICAL REQUIREMENTS:
1. For CHARACTERS: Extract their FULL PROPER NAME (e.g., "Captain Jaxon Vash", not just "captain"). Characters use FULL CAPS in screenplay style. Words inside _underlined_ regions are location/environment text, NOT character names. CRITICAL: REBECCA 'REX' STERN and REX are the SAME character — extract ONCE using the full name. Never extract both; nickname-only references (REX) = same person as full name (REBECCA 'REX' STERN).
2. For VEHICLES: Extract ONLY when a character explicitly enters, drives, rides, or operates the vehicle. Vehicles that appear only as background MUST NOT be extracted.
3. For OBJECTS: Extract ONLY when the text shows a character explicitly interacting with the object (e.g. uses, picks up, activates, breaks, drives, enters, manipulates). Objects that are only described, part of the background, or decorative MUST NOT be extracted. No interaction → no object identity block.
4. For ENVIRONMENTS: Extract ONLY proper location names (e.g., "Max's Apartment", "Central Hub", "Launchpad"). Text inside _underscores_ (e.g. _The Darkened Laboratory_) is an environment—extract the full phrase as environment. NEVER extract temporal words or phrases (Once, Soon, Later, Then, "Once, Soon") as environments—these are adverbs, NOT place names.
5. Look for proper nouns (capitalized names) - these are usually the most important entities
6. Include ALL characters mentioned, even if they appear briefly
7. Include ONLY vehicles that a character enters, drives, rides, or operates (not background vehicles)
8. Include ALL locations/spaces where action takes place
9. Be specific with names - "Captain Jaxon Vash" is better than "the captain"

CLASSIFICATION RULES (CRITICAL):
- Locations, rooms, facilities, buildings, spaces → type = "environment" (e.g., "apartment", "warehouse", "lab", "street")
- Vehicle INTERIORS (e.g. "the ship's Common Area", Bridge, Cockpit, Medbay) → type = "environment", NOT "vehicle". When referred to as "the ship's X" or "the [vehicle]'s X", X is a location/environment. Use _underscores_ markup.
- Vehicles (cars, bikes, trains, ships, aircraft, etc.) → type = "vehicle" (NEVER "object"). Only the exterior/craft itself. Only extract if character interacts with vehicle.
- Props, items, devices, tools, weapons → type = "object" (NEVER locations or vehicles). Only extract if character interacts with object.
- Named people, creatures → type = "character" (NEVER locations, objects, or vehicles)

✅ DO EXTRACT:
- Named characters (people, creatures)
- Vehicles ONLY when a character enters, drives, rides, or operates them
- Objects ONLY when a character uses, picks up, activates, breaks, or manipulates them
- Locations (rooms, facilities, buildings, interior/exterior spaces) → classify as "environment"

❌ DO NOT EXTRACT:
- Objects or vehicles that are merely described, background, or decorative (no character interaction)
- Environmental features that are not locations (e.g., "the sun", "the sky", "the ocean")
- Abstract concepts or emotions
- Background extras (crowds, guests) — these are handled separately

For each entity found, identify:
- Entity name (USE EXACT PROPER NAMES from the text - e.g., "Captain Jaxon Vash", "Aurora's Hope", "Max's Apartment")
- Entity category (character, vehicle, object, environment) based on CLASSIFICATION RULES above
- Brief appearance description from the text (this will be used as a starting point for the user)

CRITICAL: For the description field, extract ALL relevant visual details from the text:
- For CHARACTERS: **ALWAYS START WITH GENDER AND AGE** (e.g., "male, mid-30s" or "female, early 20s"), then physical appearance, clothing, build, distinguishing features
- For VEHICLES: size, color, condition, design features, identifying marks
- For OBJECTS: size, material, color, condition, purpose
- For ENVIRONMENTS: setting type, time of day, weather, architectural features

GENDER AND AGE EXTRACTION RULES (CRITICAL FOR CHARACTERS):
1. If gender is explicitly stated in the text (e.g., "he", "she", "his", "her"), use it
2. If not explicitly stated but strongly implied by name, infer it (e.g., "Captain Jaxon" = male, "Sarah" = female)
3. If age is stated, use it; otherwise estimate from context (e.g., "weathered" = older, "young" = 20s-30s, "veteran" = 40s+)
4. ALWAYS include both gender and age estimate at the START of character descriptions
5. Use format: "gender, age-range, [other details]" (e.g., "male, mid-40s, rugged face", "female, early 20s, athletic build")

Return ONLY a JSON array with this structure:
[
  {{"name": "exact_proper_name_from_text", "type": "character|vehicle|object", "description": "detailed visual description from text"}},
  ...
]

EXAMPLE:
If text mentions "Captain Jaxon Vash surveyed the scene, his worn military uniform a testament to years of service"
Return: {{"name": "Captain Jaxon Vash", "type": "character", "description": "male, mid-40s, wearing worn military uniform, appears to have years of service experience"}}

Extract AT LEAST 2-3 entities if they exist in the text.
If no entities are found, return an empty array [].
"""
        
        try:
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You are a meticulous script supervisor who extracts specific entity names and descriptions from scene text. Focus on proper nouns and specific identifiers. Never use generic names when specific names are provided. REBECCA \"REX\" STERN and REX are the SAME character — extract once with the full name; never extract both as separate characters."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=800
            )
            
            content = response.choices[0].message.content
            if not content:
                return []
            
            # Write to debug log
            try:
                with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                    debug_file.write(f"\n--- AI Response for Entity Extraction ---\n")
                    debug_file.write(f"Response length: {len(content)} characters\n")
                    debug_file.write(f"Response preview (first 1000 chars):\n{content[:1000]}\n")
                    debug_file.write(f"--- End AI Response ---\n\n")
            except:
                pass
            
            print(f"DEBUG: Entity extraction AI response (first 500 chars): {content[:500]}")
            
            # Extract JSON from response
            try:
                entities_data = self._extract_and_parse_json(content, prefer_array=True)
                
                # Write parsed data to debug log
                try:
                    with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                        debug_file.write(f"Parsed data type: {type(entities_data)}\n")
                        debug_file.write(f"Parsed data content: {entities_data}\n")
                        if isinstance(entities_data, list):
                            debug_file.write(f"Number of entities in parsed data: {len(entities_data)}\n")
                            for ent in entities_data:
                                debug_file.write(f"  Raw entity: {ent}\n")
                        elif isinstance(entities_data, dict):
                            debug_file.write(f"Dictionary keys: {list(entities_data.keys())}\n")
                        debug_file.write("\n")
                except:
                    pass
                
                print(f"DEBUG: Parsed entities data type: {type(entities_data)}")
                
                # Handle both list and dict responses
                final_list = []
                if isinstance(entities_data, list):
                    print(f"DEBUG: Found {len(entities_data)} entities in list")
                    final_list = entities_data
                elif isinstance(entities_data, dict):
                    # Check common dict keys that might contain the entities list
                    if "entities" in entities_data:
                        final_list = entities_data["entities"]
                        print(f"DEBUG: Found {len(final_list)} entities in dict['entities']")
                    elif "items" in entities_data:
                        final_list = entities_data["items"]
                        print(f"DEBUG: Found {len(final_list)} entities in dict['items']")
                    elif "results" in entities_data:
                        final_list = entities_data["results"]
                        print(f"DEBUG: Found {len(final_list)} entities in dict['results']")
                    else:
                        # Maybe the dict itself IS the list values
                        # Or try to find any key that contains a list
                        for key, value in entities_data.items():
                            if isinstance(value, list) and len(value) > 0:
                                final_list = value
                                print(f"DEBUG: Found {len(final_list)} entities in dict['{key}']")
                                break
                
                if not final_list:
                    print(f"DEBUG: No entities found in parsed data structure")
                    try:
                        with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                            debug_file.write(f"ERROR: Could not extract list from parsed data\n")
                            debug_file.write(f"Full parsed data: {entities_data}\n\n")
                    except:
                        pass
                    return []
                
                # Filter out low-quality extractions (very short names, etc.)
                filtered_entities = []
                for entity in final_list:
                    if isinstance(entity, dict) and "name" in entity and "type" in entity:
                        name = entity["name"].strip()
                        entity_type = entity.get("type", "").lower()
                        
                        # Filter: Reject malformed names (dialogue blocks, paragraph text, compound names)
                        if '\n' in name or '"' in name or len(name) > 80:
                            print(f"DEBUG: Filtered out malformed entity name: '{name[:60]}...' (contains newlines, quotes, or too long)")
                            try:
                                with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                                    debug_file.write(f"FILTERED OUT: malformed name (newlines/quotes/length)\n")
                            except:
                                pass
                            continue
                        
                        # Filter 1: Keep environments (locations are valid identity blocks)
                        # Environments extracted here are actual locations (e.g., "Max's Apartment", "Central Hub")
                        # NOT per-scene placeholders
                        
                        # Filter 2: Skip extras (guests, crowd, etc.) - extras belong to environment only, not character blocks
                        if self._is_extras_entity(name, entity.get("description", ""), entity_type):
                            print(f"DEBUG: Filtered out extras entity: '{name}' (environment-level only)")
                            try:
                                with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                                    debug_file.write(f"FILTERED OUT: name='{name}' (extras - environment only)\n")
                            except:
                                pass
                            continue
                        
                        # Filter 2b: Characters must be people — reject company/department/concept/brand names
                        if entity_type == "character" and self._is_company_or_concept_entity(name):
                            print(f"DEBUG: Filtered out non-person character: '{name}' (company/department/concept)")
                            try:
                                with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                                    debug_file.write(f"FILTERED OUT: name='{name}' (not a human character)\n")
                            except:
                                pass
                            continue
                        
                        # Filter 2c: Environments must be real locations — reject temporal words and invalid place names
                        if entity_type == "environment":
                            temporal_or_invalid = {
                                "once", "soon", "later", "then", "now", "here", "there",
                                "before", "after", "once soon", "soon after", "once, soon"
                            }
                            name_lower = name.lower().strip()
                            if name_lower in temporal_or_invalid:
                                print(f"DEBUG: Filtered out bogus environment: '{name}' (temporal word, not a place)")
                                try:
                                    with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                                        debug_file.write(f"FILTERED OUT: name='{name}' (temporal/invalid environment)\n")
                                except:
                                    pass
                                continue
                            # Reject comma-separated temporal phrases like "Once, Soon"
                            if "," in name and any(t in name_lower for t in ["once", "soon", "later", "then"]):
                                print(f"DEBUG: Filtered out bogus environment: '{name}' (temporal phrase, not a place)")
                                try:
                                    with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                                        debug_file.write(f"FILTERED OUT: name='{name}' (temporal phrase as environment)\n")
                                except:
                                    pass
                                continue
                        
                        # Filter 2d: Wizard markup - _underlined_ = locations/environments. Words inside _..._ are
                        # location fragments (e.g. "DARKENED" from "_THE DARKENED LABORATORY_"), NOT characters.
                        if entity_type == "character":
                            underlined_spans = [(m.start(), m.end()) for m in re.finditer(r'_[^_]+_', text)]
                            def _inside_underlined(pos: int) -> bool:
                                return any(s <= pos < e for s, e in underlined_spans)
                            # Find all occurrences of this name (word-boundary) in text
                            matches = list(re.finditer(r'\b' + re.escape(name) + r'\b', text, re.IGNORECASE))
                            if matches and all(_inside_underlined(m.start()) for m in matches):
                                print(f"DEBUG: Filtered out character '{name}' (only appears inside _underlined_ location markup)")
                                try:
                                    with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                                        debug_file.write(f"FILTERED OUT: name='{name}' (inside underlined env markup)\n")
                                except:
                                    pass
                                continue
                        
                        # Filter 3: Skip if name is too short or generic
                        if len(name) > 2 and name.lower() not in ["the", "a", "an", "it", "that", "this"]:
                            filtered_entities.append(entity)
                        else:
                            print(f"DEBUG: Filtered out entity with name: '{name}'")
                            try:
                                with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                                    debug_file.write(f"FILTERED OUT: name='{name}' (too short or generic)\n")
                            except:
                                pass
                print(f"DEBUG: After filtering: {len(filtered_entities)} entities")
                
                registry_frozen = screenplay is not None and getattr(screenplay, "character_registry_frozen", False)
                
                # Post-extraction validation: Wizard-first, then reclassify vehicles and locations
                for entity in filtered_entities:
                    entity_name = entity.get("name", "")
                    entity_type = entity.get("type", "").lower()
                    entity_desc = entity.get("description", "")
                    
                    # 1. Wizard character list is absolute authority: if name is in registry, always character
                    if registry_frozen and screenplay:
                        canonical = screenplay.resolve_character_to_canonical(entity_name)
                        if canonical is not None:
                            entity["type"] = "character"
                            entity["name"] = canonical
                            entity_type = "character"
                            entity_name = canonical
                            try:
                                with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                                    debug_file.write(f"WIZARD: '{entity.get('name', '')}' → character (canonical: {canonical})\n")
                            except:
                                pass
                    
                    # 1.5. Wizard location list (underlined): if name is in story_outline locations, always environment
                    story_outline = getattr(screenplay, "story_outline", None) if screenplay else None
                    wizard_locations = story_outline.get("locations", []) if isinstance(story_outline, dict) else []
                    if wizard_locations and entity_type != "character":
                        name_lower = entity_name.lower().strip()
                        if any(loc.lower().strip() == name_lower for loc in wizard_locations if isinstance(loc, str)):
                            entity["type"] = "environment"
                            entity_type = "environment"
                            try:
                                with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                                    debug_file.write(f"WIZARD: '{entity_name}' → environment (in location registry)\n")
                            except:
                                pass
                    
                    # Validate vehicle classification (object → vehicle)
                    if entity_type == "object" and self._is_vehicle_entity(entity_name, entity_desc):
                        print(f"RECLASSIFY: '{entity_name}' from object → vehicle")
                        try:
                            with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                                debug_file.write(f"RECLASSIFY: '{entity_name}' from object → vehicle\n")
                        except:
                            pass
                        entity["type"] = "vehicle"
                        entity_type = "vehicle"
                    
                    # Validate location classification: only reclassify to environment if NOT in Wizard registry
                    if entity_type in ["object", "character"] and self._is_location_entity(entity_name, entity_desc):
                        if registry_frozen and screenplay and screenplay.resolve_character_to_canonical(entity_name) is not None:
                            pass  # Do not reclassify Wizard characters to environment
                        else:
                            print(f"RECLASSIFY: '{entity_name}' from {entity_type} → environment")
                            try:
                                with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                                    debug_file.write(f"RECLASSIFY: '{entity_name}' from {entity_type} → environment\n")
                            except:
                                pass
                            entity["type"] = "environment"
                            entity_type = "environment"
                    
                    # Strict identity: environment must NOT contain person names — reclassify to character
                    if entity_type == "environment":
                        canonical = screenplay.resolve_character_to_canonical(entity_name) if (registry_frozen and screenplay) else None
                        if canonical is not None:
                            entity["type"] = "character"
                            entity["name"] = canonical
                            try:
                                with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                                    debug_file.write(f"RECLASSIFY: '{entity_name}' from environment → character (Wizard list)\n")
                            except:
                                pass
                        elif self._is_person_name(entity_name):
                            print(f"RECLASSIFY: '{entity_name}' from environment → character (person name in env block)")
                            try:
                                with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                                    debug_file.write(f"RECLASSIFY: '{entity_name}' from environment → character\n")
                            except:
                                pass
                            entity["type"] = "character"
                
                # Character identity normalization: one human = one character. Deduplicate by normalized name.
                filtered_entities = self._deduplicate_character_entities(filtered_entities)
                
                # When registry is frozen: drop any character entity not in the Wizard list (no new characters)
                if registry_frozen and screenplay:
                    filtered_entities = [
                        e for e in filtered_entities
                        if not (isinstance(e, dict) and (e.get("type") or "").lower() == "character")
                        or screenplay.resolve_character_to_canonical((e.get("name") or "").strip()) is not None
                    ]
                    try:
                        with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                            debug_file.write(f"After registry filter: {len(filtered_entities)} entities (non-registry characters dropped)\n")
                    except:
                        pass
                
                # Interaction-based object/vehicle only: drop objects or vehicles with no character interaction in text
                before_interaction = len(filtered_entities)
                filtered_entities = [
                    e for e in filtered_entities
                    if not isinstance(e, dict)
                    or (e.get("type") or "").lower() not in ("object", "vehicle")
                    or self._entity_has_interaction_in_text((e.get("name") or "").strip(), (e.get("type") or "").lower(), text or "")
                ]
                dropped = before_interaction - len(filtered_entities)
                if dropped > 0:
                    try:
                        with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                            debug_file.write(f"After interaction filter: dropped {dropped} object/vehicle entities with no interaction in text\n")
                    except:
                        pass
                
                # Heuristic: propagate implied context from group sentences (only when registry NOT frozen).
                # When frozen, do not invent or overwrite character names; only Wizard list applies.
                if not registry_frozen:
                    try:
                        text_lower = (text or "").lower()
                        group_vehicle = None
                        if "cyclist" in text_lower or "cyclists" in text_lower or "bikers" in text_lower:
                            group_vehicle = "bike"
                        elif "drivers" in text_lower or "a group of cars" in text_lower:
                            group_vehicle = "car"
                        elif "riders" in text_lower and "horse" in text_lower:
                            group_vehicle = "horse"
                        
                        if group_vehicle:
                            for ent in filtered_entities:
                                if not isinstance(ent, dict):
                                    continue
                                if ent.get("type", "").lower() != "character":
                                    continue
                                name = (ent.get("name") or "").strip()
                                desc = (ent.get("description") or "").strip()
                                blob = f"{name} {desc}".lower()
                                if "messenger bag" in blob and group_vehicle in ["bike"] and "bike" not in blob:
                                    ent["name"] = "young man on a bike with a messenger bag"
                                    if desc:
                                        ent["description"] = f"{desc}, on a bike"
                                    else:
                                        ent["description"] = "male, young adult, on a bike with a messenger bag"
                    except Exception:
                        pass
                
                # Mandatory validation pass: no Wizard character as environment/object/vehicle
                if registry_frozen and screenplay:
                    for entity in filtered_entities:
                        if not isinstance(entity, dict):
                            continue
                        name = (entity.get("name") or "").strip()
                        etype = (entity.get("type") or "").lower()
                        canonical = screenplay.resolve_character_to_canonical(name)
                        if canonical is not None and etype != "character":
                            try:
                                with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                                    debug_file.write(f"VALIDATION: forced '{name}' from {etype} → character (Wizard list)\n")
                            except:
                                pass
                            entity["type"] = "character"
                            entity["name"] = canonical
                
                # Write final filtered list to debug log
                try:
                    with open("debug_entity_extraction.log", "a", encoding="utf-8") as debug_file:
                        debug_file.write(f"\nFinal filtered entities: {len(filtered_entities)}\n")
                        for ent in filtered_entities:
                            debug_file.write(f"  - {ent.get('name', '?')} ({ent.get('type', '?')})\n")
                        debug_file.write("\n")
                except:
                    pass
                
                return filtered_entities
            except:
                return []
                
        except Exception:
            return []
    
    def _generate_identity_block(self, entity_name: str, entity_type: str, description: str, screenplay: Screenplay) -> str:
        """
        DEPRECATED: Use _generate_identity_block_from_scene() instead.
        This method is kept for backward compatibility but should not be used for new code.
        It redirects to scene-based generation with minimal context.
        """
        # Try to get any available scene context from the screenplay
        # Look for scene content in recent storyboard items
        scene_context = ""
        all_items = screenplay.get_all_storyboard_items()
        if all_items:
            # Get storylines from recent items to provide some context
            recent_storylines = [item.storyline for item in all_items[-5:] if item.storyline]
            scene_context = " ".join(recent_storylines)
        
        # Redirect to scene-based method
        if scene_context:
            return self._generate_identity_block_from_scene(entity_name, entity_type, description, scene_context, screenplay)
        else:
            # If no scene context available, use minimal fallback
            return self._extract_minimal_identity_from_scene(entity_name, entity_type, description)
    
    def _generate_identity_block_from_scene(self, entity_name: str, entity_type: str, description: str, scene_text: str, screenplay: Screenplay) -> str:
        """Generate identity block using details from scene content, not generic AI descriptions.
        
        For characters: when Character Registry is frozen, only generate if entity_name is in the
        registry. Use canonical character name verbatim. Generate physical appearance only.
        """
        if not self._adapter:
            # Fallback to basic description if no AI available
            return f"the same {entity_type} ({entity_name})"
        
        if (entity_type or "").lower() == "character" and getattr(screenplay, "character_registry_frozen", False):
            canonical = screenplay.resolve_character_to_canonical(entity_name)
            if canonical is not None:
                entity_name = canonical  # Use canonical name when in registry
        
        # Generate unique entity ID
        import hashlib
        entity_key = f"{entity_type}:{entity_name}".lower()
        entity_hash = hashlib.md5(entity_key.encode()).hexdigest()[:4].upper()
        entity_id = f"{entity_type.upper()}_{entity_hash}"
        
        # Check if identity block already exists
        existing_block = screenplay.get_identity_block_by_name(entity_name, entity_type)
        if existing_block:
            return existing_block
        
        character_canonical_rule = ""
        if (entity_type or "").lower() == "character":
            character_canonical_rule = """
CHARACTER IDENTITY RULE: Use the canonical character name verbatim. Generate PHYSICAL APPEARANCE ONLY: gender, height, face structure, hair color/style, eye color, skin tone, age range, build/body type, permanent features (scars, tattoos, glasses if permanent). Do NOT include the character's name in the physical description. Character identity MUST NOT include clothing, attire, or accessories—those belong in scene wardrobe. Do NOT rename or split this character."""
        
        prompt = f"""You are a script supervisor creating an IDENTITY BLOCK for a recurring entity in a video production.

⚠️ ABSOLUTELY CRITICAL RULES - FOLLOW THESE EXACTLY:
1. Use ONLY details that are EXPLICITLY mentioned in the scene text below
2. DO NOT invent, add, or assume any details that aren't in the scene
3. DO NOT use generic descriptions or examples from other stories
4. If the scene doesn't mention a detail, DO NOT include it in the identity block
5. Extract EXACT wording from the scene - preserve specific terms, colors, materials exactly as written
6. Follow the 8-FIELD UNIVERSAL IDENTITY BLOCK SCHEMA below
{character_canonical_rule}

Entity Name: {entity_name}
Entity Type: {entity_type}
Initial Description: {description}

SCENE TEXT (extract details ONLY from this - this is your ONLY source):
{scene_text[:5000]}

═══════════════════════════════════════════════════════════════════════════════
8-FIELD UNIVERSAL IDENTITY BLOCK SCHEMA
═══════════════════════════════════════════════════════════════════════════════

Create a SINGLE FLOWING PARAGRAPH that includes these 8 fields (extract from scene ONLY):

1. **Identity Lock Phrase**: MUST start with "the same [entity_type] with..."
   - Example: "the same adult human male with..."
   - Example: "the same street motorcycle with..."

2. **Classification**: Type/category (if mentioned in scene)
   - Examples: "adult human male", "mid-size SUV", "handheld object"

3. **Physical Form & Silhouette**: Shape, proportions, body type, size (if mentioned). FOR CHARACTERS: exclude clothing; clothing belongs in scene wardrobe.
   - Examples: "tall athletic build", "compact angular body", "narrow profile"

4. **Surface & Material Behavior** (CRITICAL): Color + texture + light reaction (if mentioned). FOR CHARACTERS: skin tone only, not clothing.
   - Examples: "matte black finish that absorbs light", "warm medium-brown skin tone that reflects soft daylight"
   - ONLY use if scene explicitly describes color/material/texture

5. **Key Identifying Features**: Distinct recognition elements (if mentioned)
   - Examples: "angular facial structure with prominent cheekbones", "round LED headlights", "leather seat with stitching"

6. **Negative Constraints** (MANDATORY if applicable): What is NOT present
   - Examples: "no visible logos", "no branding", "no damage", "no accessories"
   - Include ONLY if scene implies or mentions absence of something

7. **Condition & State**: Clean, worn, damaged, pristine, aged (if mentioned)
   - Examples: "pristine condition", "worn and weathered", "clean undamaged exterior"

8. **Style/Era/Design Language**: Modern, minimalist, industrial, etc. (if mentioned)
   - Examples: "modern casual style", "minimalist design", "utilitarian appearance"

═══════════════════════════════════════════════════════════════════════════════

EXAMPLE OUTPUT for CHARACTER (physical identity only—no clothing):

"the same adult human male with a tall athletic build, warm medium-brown skin tone that absorbs soft daylight, angular facial structure with prominent cheekbones, short dark hair with natural texture, brown eyes, no visible tattoos or piercings, clean-shaven, modern casual appearance"

IMPORTANT RULES:
- Start with "the same [entity_type] with..."
- Write as ONE continuous paragraph (not a list)
- Include ONLY details explicitly mentioned in the scene text
- If a field has no information in the scene, SKIP that field
- If scene provides minimal detail, keep it minimal: "the same {entity_type} ({entity_name})"
- DO NOT invent details not in the scene

Output ONLY the identity block text - no labels, no explanations, no markdown."""
        
        try:
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You are a script supervisor. Extract EXACT details from scene text. For characters: physical identity only (face, hair, eyes, skin, age, build, scars)—NEVER include clothing, attire, or accessories. Use only what is explicitly stated in the scene."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Very low temperature for consistent extraction following 8-field schema
                max_tokens=400  # Increased for 8-field schema
            )
            
            content = response.choices[0].message.content
            if not content:
                raise Exception("AI returned empty identity block")
            
            identity_block = content.strip()
            # Clean up any quotes or markdown
            identity_block = identity_block.strip('"').strip("'").strip()
            if identity_block.startswith("```"):
                lines = identity_block.split("\n")
                if len(lines) > 1:
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                identity_block = "\n".join(lines).strip()
            
            # Remove any preamble text that AI might add (e.g., "Here is the extracted IDENTITY BLOCK:")
            if "IDENTITY BLOCK" in identity_block and "the same" in identity_block.lower():
                # Find where "the same" starts and extract from there
                match = re.search(r'(the same\s+\w+.*)', identity_block, re.IGNORECASE | re.DOTALL)
                if match:
                    identity_block = match.group(1).strip()
            
            # Validate the identity block
            if not self._validate_identity_block(identity_block, entity_type):
                print(f"Warning: Generated identity block for {entity_name} ({entity_type}) failed validation")
                # Try to fix it if it doesn't start with "the same"
                if not identity_block.lower().startswith("the same"):
                    identity_block = f"the same {entity_type} with {identity_block}"
            
            # Store the identity block
            screenplay.add_identity_block(entity_id, entity_type, identity_block)
            screenplay.register_identity_block_id(entity_name, entity_type, entity_id)
            
            return identity_block
            
        except Exception as e:
            # Fallback: extract minimal details directly from scene text - no generic templates
            return self._extract_minimal_identity_from_scene(entity_name, entity_type, scene_text)
    
    def generate_identity_block_from_notes(
        self, 
        entity_name: str, 
        entity_type: str, 
        user_notes: str, 
        scene_context: str,
        screenplay: Screenplay,
        wizard_physical_appearance: str = "",
        strip_clothing_emphasis: bool = False,
        include_physical_traits: bool = False
    ) -> str:
        """Generate a detailed 8-field identity block from user's short description.
        
        This method is called from the Identity Blocks UI when the user provides notes
        and clicks "Generate Identity Block".
        
        Args:
            entity_name: Name of entity (e.g., "Captain Jaxon Vash")
            entity_type: Type (character/vehicle/object/environment)
            user_notes: User's short description
            scene_context: Scene text for additional context
            screenplay: Screenplay object
            wizard_physical_appearance: Optional wizard-defined physical appearance (characters only). Use as primary source.
            
        Returns:
            Complete identity block following 8-field schema
        """
        if not self._adapter:
            # Fallback to basic format if no AI available
            return f"the same {entity_type} with {user_notes}"
        
        character_rule = ""
        wizard_context = ""
        strip_emphasis = ""
        # Resolve species from screenplay character data
        char_species = "Human"
        if (entity_type or "").lower() == "character" and screenplay and hasattr(screenplay, 'story_outline'):
            so = screenplay.story_outline
            if isinstance(so, dict):
                for ch in (so.get("characters", []) or []):
                    if isinstance(ch, dict) and ch.get("name", "").strip().upper() == entity_name.strip().upper():
                        char_species = ch.get("species", "Human") or "Human"
                        break
        is_human_entity = (not char_species or char_species.strip().lower() in ("human", ""))
        
        if (entity_type or "").lower() == "character":
            if include_physical_traits:
                character_rule = (
                    "\nCHARACTER FULL IDENTITY RULE: Generate a COMPLETE identity block for this character "
                    "covering BOTH their physical traits AND their clothing/wardrobe. "
                    "The user's description contains the full appearance — physical features (face, hair, eyes, "
                    "skin, build, height, age, scars, etc.) and clothing/wardrobe. "
                    "You MUST preserve EVERY detail from the user's input — age, height, gender, species, "
                    "facial features, hair, eye colour, skin tone, build, scars, and clothing. "
                    "Do NOT drop, omit, or summarise any of these. Expand ALL of them into the identity block. "
                    "Do NOT include the character's name in the description.\n"
                )
            elif is_human_entity:
                character_rule = (
                    "\nCHARACTER SCENE IDENTITY RULE: Generate the identity block for this character AS THEY APPEAR IN THIS SCENE. "
                    "The user's description below is the SCENE WARDROBE — clothing, accessories, armor, uniforms, and scene-specific appearance state. "
                    "This is the PRIMARY input. Expand the wardrobe into the identity block. "
                    "Do NOT include the character's name in the description. "
                    "Do NOT add physical traits (face, hair, eyes, skin, build) — those are defined globally elsewhere.\n"
                )
            else:
                character_rule = (
                    f"\nCHARACTER SCENE IDENTITY RULE: This character is a {char_species}, NOT a human. "
                    "Generate the identity block describing this character AS THEY APPEAR IN THIS SCENE. "
                    f"Include species-appropriate anatomy and features for a {char_species}. "
                    "The user's description may include natural features (scales, wings, horns, etc.) and any worn accessories or harnesses. "
                    "Do NOT include the character's name in the description.\n"
                )
            if wizard_physical_appearance and wizard_physical_appearance.strip():
                if include_physical_traits:
                    wizard_context = ""
                elif is_human_entity:
                    wizard_context = (
                        f"\nBACKGROUND CONTEXT (physical appearance — DO NOT expand or repeat these traits, "
                        f"they are managed separately):\n{wizard_physical_appearance.strip()}\n\n"
                    )
                else:
                    wizard_context = (
                        f"\nBACKGROUND CONTEXT (physical appearance — reference for species-appropriate details):\n"
                        f"{wizard_physical_appearance.strip()}\n\n"
                    )
            if strip_clothing_emphasis and not include_physical_traits:
                strip_emphasis = (
                    "\nCRITICAL RETRY: The previous output was incorrect. Focus ONLY on wardrobe and clothing. "
                    "Describe garments, accessories, armor, uniforms, and scene-specific appearance state. "
                    "Do NOT include physical traits (face, hair, eyes, skin, build, scars). "
                    "Do NOT include the character's name.\n"
                )
        
        environment_rule = ""
        if (entity_type or "").lower() == "environment":
            environment_rule = (
                "\nENVIRONMENT IDENTITY RULE: This entity is a LOCATION/SETTING. "
                "Describe the physical space in rich detail: architecture, layout, furniture, fixtures, "
                "materials, surfaces, textures, colours, lighting quality "
                "(including which objects are the light sources — torches, lamps, candles, screens, fires, neon, "
                "sconces, braziers, chandeliers — and their specific visual effect: colour cast, warmth, intensity, "
                "shadow direction; also note any objects that are specifically unlit or dark), and atmosphere. "
                "Be expansive and specific — the more visual detail the better for image generation consistency. "
                "Do NOT mention any characters, character actions, wardrobe, or dialogue.\n"
            )
        
        if include_physical_traits:
            char_example = (
                'EXAMPLE EXPANSION (for CHARACTER—full appearance including physical traits and clothing):\n\n'
                'User Input: "Female, 5\'6", 19 years old, heart-shaped face, long wavy auburn hair, emerald green eyes, fair skin with freckles, '
                'slender but strong build. Wearing a worn leather jacket, muddy boots, torn jeans, dark scarf"\n'
                'Output: "the same 19-year-old human female, 5\'6" tall, with a heart-shaped face featuring high cheekbones and a defined jawline, '
                'long wavy auburn hair cascading past her shoulders, vivid emerald green eyes, fair skin with a natural scattering of '
                'freckles across the nose and cheeks that catch warm light, slender yet toned build suggesting physical endurance, '
                'wearing a distressed brown leather jacket with visible creases and scuffing at the elbows, heavy-duty muddy boots '
                'caked with dried earth, faded torn jeans with frayed hems, a dark wool scarf wrapped loosely around the neck, '
                'no visible jewelry or badges, weathered and road-worn outfit suggesting extended travel, rugged utilitarian style"'
            )
            char_rule_line = (
                "- For CHARACTERS: include EVERY detail from the user's description — age, height, gender, "
                "face, hair, eyes, skin, build, scars, AND clothing/wardrobe. Do NOT omit any of them."
            )
            char_start_hint = '- Start with "the same [entity_type] with..." (for characters use "the same character with...")'
        else:
            char_example = (
                'EXAMPLE EXPANSION (for CHARACTER—scene wardrobe, NOT physical traits):\n\n'
                'User Input: "Worn leather jacket, muddy boots, torn jeans, dark scarf"\n'
                'Output: "the same character wearing a distressed brown leather jacket with visible creases and scuffing at the elbows, '
                'heavy-duty muddy boots caked with dried earth, faded torn jeans with frayed hems, a dark wool scarf wrapped loosely '
                'around the neck, no visible jewelry or badges, weathered and road-worn outfit suggesting extended travel, rugged '
                'utilitarian style"'
            )
            char_rule_line = (
                "- For CHARACTERS: focus on wardrobe, clothing, accessories, and scene-specific appearance state ONLY. "
                "Do NOT include physical traits."
            )
            char_start_hint = '- Start with "the same [entity_type] with..." (for characters use "the same character wearing...")'

        prompt = f"""You are a script supervisor creating an IDENTITY BLOCK for a recurring entity in a video production.

Your task is to expand the user's short description into a detailed 8-field identity block.
{character_rule}{wizard_context}{strip_emphasis}{environment_rule}
Entity Name: {entity_name}
Entity Type: {entity_type}
User's Description: {user_notes}

Additional Scene Context (use for reference if needed):
{scene_context[:1000] if scene_context else "No additional context"}

═══════════════════════════════════════════════════════════════════════════════
8-FIELD UNIVERSAL IDENTITY BLOCK SCHEMA
═══════════════════════════════════════════════════════════════════════════════

Create a SINGLE FLOWING PARAGRAPH that includes these 8 fields based on the user's description:

1. **Identity Lock Phrase**: MUST start with "the same [entity_type] with..."
   - Example: "the same adult human male with..."
   - Example: "the same street motorcycle with..."
   - Example: "the same dragon with..."
   - Example: "the same elf with..."

2. **Classification**: Type/category from user description
   - Examples: "adult human male", "mid-size SUV", "handheld object", "ancient dragon", "female elf"

3. **Physical Form & Silhouette**: Shape, proportions, posture, size from user description
   - Examples: "tall athletic build", "compact angular body", "narrow profile"

4. **Surface & Material Behavior** (CRITICAL): Color + texture + light reaction
   - Examples: "matte black finish that absorbs light", "warm medium-brown skin tone that reflects soft daylight"
   - Expand from user's color/material descriptions

5. **Key Identifying Features**: Distinct recognition elements from user description
   - Examples: "angular facial structure with prominent cheekbones", "round LED headlights", "leather seat with stitching"

6. **Negative Constraints** (MANDATORY): What is NOT present
   - Examples: "no visible logos", "no branding", "no damage", "no accessories"
   - Infer reasonable constraints based on entity type

7. **Condition & State**: Clean, worn, damaged, pristine, aged from user description
   - Examples: "pristine condition", "worn and weathered", "clean undamaged exterior"

8. **Style/Era/Design Language**: Modern, minimalist, industrial, etc.
   - Examples: "modern casual style", "minimalist design", "utilitarian appearance"

═══════════════════════════════════════════════════════════════════════════════

{char_example}

EXAMPLE EXPANSION (for ENVIRONMENT):

User Input: "Victorian foyer, dark wood paneling, grand staircase, dim candlelight"
Output: "the same Victorian foyer with soaring double-height ceilings and ornate crown moulding, rich dark mahogany wall paneling with inset decorative carved panels, a grand sweeping staircase with wrought-iron balusters and a polished wooden handrail curving upward into shadow, a heavy crystal chandelier hanging unlit from the central ceiling medallion, warm dim candlelight flickering from wall-mounted brass sconces casting amber pools and deep angular shadows across the patterned marble tile floor, faded burgundy runner rug along the hallway, a narrow console table with tarnished brass hardware against one wall, no modern fixtures or electrical lighting visible, aged and weathered surfaces suggesting decades of wear, Gothic Revival architectural style with Victorian-era design language"

EXAMPLE EXPANSION (for NON-CHARACTER entity):

User Input: "Large starship, angular hull, battle-scarred, grey metallic"
Output: "the same capital starship with an angular wedge-shaped hull, matte grey metallic surface with battle scars and carbon scoring that absorbs ambient light, prominent forward bridge tower, no visible insignia or markings, heavily battle-damaged exterior with hull breaches and scorched plating, industrial military design language"

IMPORTANT RULES:
{char_start_hint}
- Write as ONE continuous paragraph (not a list)
- Expand the user's description into rich, specific details
- Include negative constraints (what is NOT present)
{char_rule_line}
- For ENVIRONMENTS: describe the physical space in rich detail (architecture, furniture, materials, lighting, atmosphere). Do NOT include characters, actions, wardrobe, or dialogue.
- For OTHER NON-CHARACTERS: focus on visual, physical descriptions only
- NO emotional states, NO narrative, NO action

Output ONLY the identity block text - no labels, no explanations, no markdown."""
        
        try:
            if include_physical_traits:
                char_sys_rule = (
                    "For characters: describe the COMPLETE appearance including ALL physical traits "
                    "(age, height, gender, face, hair, eyes, skin, build, scars) AND clothing/wardrobe. "
                    "Every detail the user provides must appear in the output — do not drop any. "
                )
            else:
                char_sys_rule = (
                    "For characters: describe scene wardrobe only (clothing, accessories, armor, uniforms, "
                    "scene-specific state)—do NOT include physical traits (face, hair, eyes, skin, build). "
                )
            system_content = (
                "You are a script supervisor who expands brief descriptions into detailed visual identity blocks. "
                + char_sys_rule +
                "For environments: describe the physical space with rich detail (architecture, furniture, materials, lighting, atmosphere)—do NOT mention characters, actions, wardrobe, or dialogue. "
                "For other non-characters: describe physical/visual identity."
            )
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=700 if include_physical_traits else 500
            )
            
            content = response.choices[0].message.content
            if not content:
                raise Exception("AI returned empty identity block")
            
            identity_block = content.strip()
            # Clean up any quotes or markdown
            identity_block = identity_block.strip('"').strip("'").strip()
            
            # Remove markdown code blocks if present
            if identity_block.startswith("```"):
                lines = identity_block.split("\n")
                if len(lines) > 1:
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                identity_block = "\n".join(lines).strip()
            
            # Remove any preamble text
            if "IDENTITY BLOCK" in identity_block and "the same" in identity_block.lower():
                match = re.search(r'(the same\s+\w+.*)', identity_block, re.IGNORECASE | re.DOTALL)
                if match:
                    identity_block = match.group(1).strip()
            
            # Validate the identity block
            if not identity_block.lower().startswith("the same"):
                identity_block = f"the same {entity_type} with {identity_block}"
            
            return identity_block
            
        except Exception as e:
            # Fallback: basic format with user notes
            return f"the same {entity_type} with {user_notes}"
    
    def extract_character_wardrobe_from_scene(
        self, content: str, character_name: str, scene_context: str = ""
    ) -> str:
        """Extract wardrobe (clothing, accessories, armor, condition) for a character from scene content.
        
        Used for scene-level character state. Does NOT include physical identity.
        
        Args:
            content: Scene content text
            character_name: Name of the character
            scene_context: Optional additional context (e.g., scene title, description)
            
        Returns:
            1-2 sentence wardrobe description, or "" if nothing found
        """
        if not self._adapter or not content or not character_name:
            return ""
        
        context_line = f"\nScene context: {scene_context[:200]}" if scene_context else ""
        prompt = f"""Extract ONLY the wardrobe (clothing, accessories, armor) for the character "{character_name}" from this scene.

Scene content:
{content[:2000]}
{context_line}

Output 1-2 concise sentences describing what {character_name} is WEARING in this scene:
- Clothing (shirt, jacket, dress, etc.)
- Accessories (hat, jewelry, etc.)
- Armor or uniform if applicable
- Condition (dirty, bloodstained, pristine) if relevant

Do NOT include: physical appearance (face, hair, build), actions, setting, or dialogue.
If no clothing is described, return "No wardrobe specified" (exactly that phrase).

Respond with ONLY the wardrobe description."""

        try:
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You extract only clothing and wardrobe from scene text. No physical identity, no actions."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=100
            )
            desc = (response.choices[0].message.content or "").strip().strip('"\'')
            if not desc or "no wardrobe specified" in desc.lower():
                return ""
            return desc
        except Exception as e:
            print(f"Error extracting character wardrobe: {e}")
            return ""
    
    @staticmethod
    def _extract_environment_only_context(scene_text: str, env_name: str = "") -> str:
        """Extract only setting/location sentences from scene text, removing character
        actions, wardrobe, and dialogue so the context is safe for environment identity blocks."""
        if not scene_text:
            return ""
        
        paragraphs = [p.strip() for p in scene_text.split('\n\n') if p.strip()]
        env_sentences = []
        
        # Indicators that a sentence describes setting/location
        setting_indicators = {
            'room', 'wall', 'walls', 'floor', 'ceiling', 'window', 'windows', 'door', 'doors',
            'hallway', 'corridor', 'building', 'house', 'apartment', 'office', 'street',
            'furniture', 'table', 'desk', 'chair', 'sofa', 'couch', 'shelf', 'shelves',
            'light', 'lighting', 'lamp', 'chandelier', 'glow', 'shadow', 'shadows',
            'sunlight', 'moonlight', 'daylight', 'dawn', 'dusk', 'night', 'overcast',
            'architecture', 'brick', 'concrete', 'marble', 'wooden', 'glass', 'steel',
            'paint', 'painted', 'poster', 'decor', 'decoration', 'carpet', 'rug',
            'staircase', 'stairs', 'balcony', 'porch', 'garden', 'yard', 'alley',
            'atmosphere', 'air', 'temperature', 'breeze', 'wind', 'rain', 'fog',
            'city', 'skyline', 'horizon', 'landscape', 'forest', 'field', 'park',
            'interior', 'exterior', 'foyer', 'lobby', 'kitchen', 'bedroom', 'bathroom',
            'stretch', 'tower', 'arch', 'pillar', 'column', 'beam', 'railing',
            'tile', 'tiles', 'fireplace', 'mantle', 'curtain', 'curtains', 'blind', 'blinds',
        }
        
        # Indicators that a sentence is about character action / wardrobe / dialogue
        char_action_patterns = re.compile(
            r'(?:'
            r'\b(?:he|she|they|his|her|their|him|hers|them)\b'
            r'|(?:^|\s)[A-Z]{2,}(?:\s+[A-Z]{2,})*\s+\*'  # CAPS NAME followed by *action*
            r'|\*[a-z]+(?:s|es|ed|ing)\*'  # *action verb*
            r'|"[^"]*"'  # dialogue in quotes
            r'|\bwearing\b|\bworn\b|\bdressed\b|\bjacket\b|\bhoodie\b|\bboots\b'
            r'|\bshirt\b|\bpants\b|\bjeans\b|\bcoat\b|\bgloves\b|\bhat\b|\bscarf\b'
            r')',
            re.IGNORECASE
        )
        
        env_name_lower = (env_name or "").lower()
        
        for para in paragraphs[:4]:
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sentence in sentences:
                s_lower = sentence.lower().strip()
                if not s_lower or len(s_lower) < 10:
                    continue
                
                # Keep if it mentions the environment name
                if env_name_lower and env_name_lower in s_lower:
                    env_sentences.append(sentence.strip())
                    continue
                
                # Keep if it has setting indicators and no character action patterns
                has_setting = any(w in s_lower.split() for w in setting_indicators)
                has_char_action = bool(char_action_patterns.search(sentence))
                
                if has_setting and not has_char_action:
                    env_sentences.append(sentence.strip())
        
        return " ".join(env_sentences) if env_sentences else ""

    def _extract_lighting_from_scene(self, scene) -> str:
        """Extract lighting description from scene content, scanning multiple paragraphs.
        
        Looks for both ambient lighting conditions (time of day, weather) and
        object-sourced lighting (torches, lamps, fires, screens, etc.), including
        objects that are specifically unlit or dark.
        
        Returns a concise lighting string or empty string if nothing found.
        """
        if not scene:
            return ""
        content = ""
        if scene.metadata and scene.metadata.get("generated_content"):
            content = scene.metadata["generated_content"]
        elif scene.description:
            content = scene.description
        if not content:
            return ""
        
        content = re.sub(r'^\[\d+\]\s+', '', content, flags=re.MULTILINE)
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        if not paragraphs:
            return ""
        
        lighting_indicators = [
            # Time of day / natural
            'dawn', 'dusk', 'twilight', 'golden hour', 'midday', 'midnight',
            'morning light', 'afternoon light', 'evening light', 'night',
            'moonlight', 'moonlit', 'starlight', 'starlit',
            'overcast', 'sunshine', 'sunlight', 'sun ',
            'stormy', 'lightning', 'grey sky', 'gray sky',
            # Artificial / fixture
            'fluorescent', 'incandescent', 'candlelight', 'candle',
            'firelight', 'fireplace', 'lantern', 'lamp', 'lamplight',
            'neon', 'spotlight', 'chandelier', 'bulb', 'strip light', 'overhead light',
            'window light', 'daylight', 'natural light', 'artificial light',
            'screen glow', 'backlit', 'silhouette',
            # Object-sourced light
            'torch', 'torchlight', 'brazier', 'sconce', 'campfire', 'bonfire',
            'fire pit', 'hearth', 'embers', 'oil lamp', 'gas lamp', 'street lamp',
            'headlights', 'taillights', 'dashboard glow', 'candelabra',
            'fairy lights', 'string lights', 'bioluminescent', 'luminous',
            'phosphorescent', 'lava', 'crystal glow', 'rune glow', 'holographic',
            # Quality descriptors
            'dim ', 'dimly', 'bright ', 'brightly',
            'shadow', 'shadows', 'glow', 'glowing', 'flicker', 'flickering',
            'amber', 'warm light', 'cool light', 'harsh light', 'soft light',
            # Unlit / negative
            'unlit', 'extinguished', 'dead screen', 'dark chandelier',
            'burned out', 'burnt out', 'no light', 'pitch dark', 'pitch black',
        ]
        
        lighting_sentences = []
        seen_lower = set()
        for para in paragraphs[:8]:
            para_lower = para.lower()
            if not any(indicator in para_lower for indicator in lighting_indicators):
                continue
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sentence in sentences:
                s_lower = sentence.lower()
                if any(indicator in s_lower for indicator in lighting_indicators):
                    cleaned = re.sub(r'[_\[\]{}*()]', '', sentence).strip()
                    cleaned = re.sub(r'\b[A-Z]{2,}(?:\s+[A-Z]{2,})*\b', '', cleaned).strip()
                    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
                    if cleaned and len(cleaned) > 10 and cleaned.lower() not in seen_lower:
                        lighting_sentences.append(cleaned)
                        seen_lower.add(cleaned.lower())
        
        if not lighting_sentences:
            return ""
        
        lighting_desc = ' '.join(lighting_sentences[:4])
        if len(lighting_desc) > 350:
            lighting_desc = lighting_desc[:350].rsplit(' ', 1)[0]
        
        return lighting_desc

    def generate_reference_image_prompt(
        self,
        entity_name: str,
        entity_type: str,
        identity_block: str,
        metadata: Optional[Dict[str, Any]] = None,
        scene_lighting: str = ""
    ) -> str:
        """Generate a Higgsfield reference image prompt from an approved identity block.
        
        This creates a standalone prompt for generating a reference image of an entity
        that can be used in Higgsfield Cinema Studio for consistent visual identity.
        
        Args:
            entity_name: Name of entity (e.g., "Captain Jaxon Vash")
            entity_type: Type (character/vehicle/object/environment)
            identity_block: The approved identity block text
            metadata: Optional identity block metadata (for environment: extras_present, extras_density, etc.)
            scene_lighting: Optional lighting description extracted from scene content (used for environments)
            
        Returns:
            A prompt optimized for generating a Higgsfield reference image
        """
        if not identity_block:
            return f"A photorealistic reference image of {entity_name}"
        
        # Build type-specific reference image prompt
        if entity_type == "character":
            char_species = (metadata or {}).get("species", "Human") if metadata else "Human"
            is_human_char = (not char_species or char_species.strip().lower() in ("human", ""))
            if is_human_char:
                prompt = f"""Photorealistic reference image for video production.
Full body portrait of {entity_name}, neutral standing pose, facing camera at slight 3/4 angle.
{identity_block}
Plain neutral grey backdrop, soft even studio lighting, full figure visible head to toe.
No props, no action, no motion blur, sharp focus, high detail.
Reference photo style, suitable for character consistency in video production."""
            else:
                prompt = f"""Photorealistic reference image for video production.
Full body portrait of {entity_name} ({char_species}), neutral pose, facing camera at slight 3/4 angle.
{identity_block}
Plain neutral grey backdrop, soft even studio lighting, entire body visible.
No props, no action, no motion blur, sharp focus, high detail.
Reference photo style, suitable for character consistency in video production."""
        
        elif entity_type == "vehicle":
            # Vehicles: 3/4 view, clean background
            prompt = f"""Photorealistic reference image for video production.
{entity_name} shown in clean 3/4 front view angle.
{identity_block}
Plain neutral backdrop, bright even lighting showing all details, no reflections.
No driver, no passengers, no motion, stationary vehicle, sharp focus.
Reference photo style, suitable for vehicle consistency in video production."""
        
        elif entity_type == "object":
            # Objects: Product-shot style, neutral background
            prompt = f"""Photorealistic reference image for video production.
Product-style shot of {entity_name}, centered in frame.
{identity_block}
Plain white or neutral grey backdrop, soft diffused lighting from multiple angles.
Object shown at optimal viewing angle, all details visible, sharp focus.
Reference photo style, suitable for prop consistency in video production."""
        
        elif entity_type == "environment":
            # MODE A (empty) vs MODE B (with extras) - backward compat: missing metadata = MODE A
            extras_present = bool(metadata.get("extras_present", False)) if metadata else False
            lighting_line = f"Lighting: {scene_lighting}." if scene_lighting else "Natural lighting appropriate to the setting."
            if extras_present:
                extras_density = (metadata or {}).get("extras_density", "sparse")
                extras_activities = (metadata or {}).get("extras_activities", "") or "background figures"
                extras_depth = (metadata or {}).get("extras_depth", "background_only")
                fg_zone = (metadata or {}).get("foreground_zone", "clear")
                extras_line = f"Soft-focus {extras_activities} in the {extras_depth.replace('_', ' ')}, {extras_density} density, {fg_zone} foreground."
                prompt = f"""Photorealistic reference image for video production.
Wide establishing shot of {entity_name}. {extras_line}
{identity_block}
Full environment visible. {lighting_line} Extras non-distinct, non-identifiable; foreground reserved for character placement.
Static scene, no motion, no activity. Reference photo style, suitable for environment consistency in video production."""
            else:
                prompt = f"""Photorealistic reference image for video production.
Wide establishing shot of {entity_name}, no people present, empty, unoccupied.
{identity_block}
Full environment visible. {lighting_line}
Static scene, no motion, no activity, empty space ready for character placement.
Reference photo style, suitable for environment consistency in video production."""
        
        else:
            # Generic fallback
            prompt = f"""Photorealistic reference image of {entity_name}.
{identity_block}
Neutral background, even lighting, sharp focus, high detail.
Reference photo style for video production consistency."""
        
        # Clean up the prompt
        prompt = prompt.strip()
        # Remove any "the same X with" prefix from identity block if it's in the middle
        prompt = re.sub(r'\bthe same \w+ with\b', '', prompt, flags=re.IGNORECASE)
        prompt = re.sub(r'\s+', ' ', prompt)  # Collapse multiple spaces
        
        return prompt.strip()
    
    def generate_character_appearance_prompt(
        self,
        character_name: str,
        physical_appearance: str,
        species: str = "Human"
    ) -> str:
        """Generate a canonical full-body appearance prompt for a character's reference image.
        
        Uses ONLY the character's persistent physical appearance data.
        The prompt includes a default neutral full-body outfit (for humanoids) and is structured
        for image generation models (Higgsfield, Midjourney, etc.).
        
        Args:
            character_name: The character's name
            physical_appearance: The persistent Physical Appearance text from Wizard Step 2
            species: The character's species/form (e.g. "Human", "Dragon", "Elf")
            
        Returns:
            A single-paragraph prompt optimized for generating a canonical reference image
        """
        is_human_species = (not species or species.strip().lower() in ("human", ""))
        species_label = species.strip() if species and species.strip() else "Human"
        
        if not physical_appearance or not physical_appearance.strip():
            if is_human_species:
                return f"Photorealistic full body reference image of {character_name}, neutral standing pose, plain studio backdrop."
            else:
                return f"Photorealistic full body reference image of {character_name} ({species_label}), neutral pose, plain studio backdrop."
        
        if not self._adapter:
            if is_human_species:
                return (
                    f"Photorealistic full body reference image of {character_name}. "
                    f"{physical_appearance.strip()} "
                    "Wearing neutral generic clothing (plain fitted shirt, dark trousers, simple shoes); "
                    "wardrobe will vary by scene. "
                    "Full body visible head to toe, neutral standing pose, slight 3/4 angle facing camera. "
                    "Plain neutral grey studio backdrop, soft even lighting, sharp focus, high detail. "
                    "No props, no action, no motion blur. Reference photo style for video production."
                )
            else:
                return (
                    f"Photorealistic full body reference image of {character_name} ({species_label}). "
                    f"{physical_appearance.strip()} "
                    "Entire body visible, neutral pose, slight 3/4 angle facing camera. "
                    "Plain neutral grey studio backdrop, soft even lighting, sharp focus, high detail. "
                    "No props, no action, no motion blur. Reference photo style for video production."
                )
        
        if is_human_species:
            clothing_rule = (
                "3. Include a DEFAULT NEUTRAL FULL-BODY OUTFIT:\n"
                "   - Generic, non-descript clothing (e.g., fitted neutral jacket, plain shirt, dark trousers, simple boots)\n"
                "   - The outfit must be visually complete (no partial outfit)\n"
                "   - The outfit must NOT define personality or reference story context\n"
                '   - Explicitly state: "neutral generic clothing; wardrobe will vary by scene"'
            )
            traits_hint = "face, hair, eyes, skin, age, build, height, scars, etc."
        else:
            clothing_rule = (
                f"3. This character is a {species_label}, NOT human. Do NOT include human clothing.\n"
                "   - Describe the character's natural body only.\n"
                "   - No armour, saddle, harness, or accessories unless they are part of the character's anatomy."
            )
            traits_hint = "species-appropriate anatomy, colouring, size, distinguishing features, etc."
        
        species_line = f"\nCharacter Species/Form: {species_label}" if not is_human_species else ""
        
        prompt = f"""You are a reference image prompt specialist for video production.

Generate a SINGLE PARAGRAPH prompt for creating a CANONICAL FULL-BODY REFERENCE IMAGE of a character.

Character Name: {character_name}{species_line}
Physical Appearance (Persistent Traits): {physical_appearance.strip()}

RULES:
1. The prompt must describe a FULL BODY shot — entire body visible
2. Include ALL physical traits from the Physical Appearance above ({traits_hint})
{clothing_rule}
4. Pose: Neutral pose, slight 3/4 angle facing camera
5. Background: Plain neutral grey studio backdrop
6. Lighting: Soft even studio lighting, high clarity
7. Style: Photorealistic, cinematic realism
8. Emphasize body proportions, distinguishing features, and overall silhouette
9. Do NOT include the character's name in the prompt output

MUST NOT INCLUDE:
- Actions or movement
- Emotions or expressions (beyond neutral)
- Dialogue
- Sound effects
- Scene references or story events
- Camera motion
- Narrative language

FORMAT:
- One continuous descriptive paragraph
- Optimized for image generation models
- Start with "Photorealistic full body reference image..."

Output ONLY the prompt text — no labels, no explanations, no markdown."""

        try:
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You generate precise, descriptive image prompts for character reference images. "
                            "Focus on physical traits and neutral presentation. "
                            "Never include narrative, emotion, action, or story context."
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=500
            )
            
            content = response.choices[0].message.content
            if not content:
                raise Exception("AI returned empty response")
            
            result = content.strip()
            # Clean up any quotes or markdown
            result = result.strip('"').strip("'").strip()
            if result.startswith("```"):
                lines = result.split("\n")
                if len(lines) > 1:
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                result = "\n".join(lines).strip()
            
            # Collapse to single paragraph
            result = re.sub(r'\n+', ' ', result)
            result = re.sub(r'\s+', ' ', result)
            
            return result.strip()
            
        except Exception as e:
            raise Exception(f"Failed to generate appearance prompt: {str(e)}")
    
    def _extract_minimal_identity_from_scene(self, entity_name: str, entity_type: str, scene_text: str) -> str:
        """Extract minimal identity details directly from scene text - no generic templates, only what's in scene."""
        if not scene_text:
            return f"the same {entity_type} ({entity_name})"
        
        # Extract any descriptive phrases that mention the entity
        # Look for patterns like "entity_name with X" or "entity_name, X" or "X entity_name"
        entity_escaped = re.escape(entity_name)
        patterns = [
            rf'\b{entity_escaped}\s+with\s+([^,\.]+)',  # "John with black jacket"
            rf'\b{entity_escaped}[,\s]+([^,\.]+)',      # "John, wearing black jacket"
            rf'\b([^,\.]+)\s+{entity_escaped}\b',       # "black jacket John"
        ]
        
        extracted_details = []
        for pattern in patterns:
            matches = re.finditer(pattern, scene_text, re.IGNORECASE)
            for match in matches:
                detail = match.group(1).strip()
                # Filter out common words that aren't descriptive
                if detail and len(detail) > 3 and detail.lower() not in ["the", "and", "or", "a", "an", "is", "was", "are", "were"]:
                    # Check if it's actually a descriptive detail (contains adjectives, colors, materials, etc.)
                    if any(word in detail.lower() for word in ["black", "white", "red", "blue", "green", "leather", "metal", "wood", "wearing", "carrying", "holding"]):
                        extracted_details.append(detail)
                        break
            if extracted_details:
                break
        
        # Build minimal identity block with only extracted details
        if extracted_details:
            return f"the same {entity_type} ({entity_name}), {', '.join(extracted_details[:2])}"  # Limit to 2 details max
        else:
            # No details found in scene - use minimal description
            return f"the same {entity_type} ({entity_name})"
    
    def _generate_environment_block(self, scene: 'StoryScene', scene_content: str, screenplay: 'Screenplay') -> str:
        """Generate a static environment block for a scene following the Higgsfield first-frame template.
        
        This creates a per-scene environment description that is reused for all storyboard items in the scene.
        The environment block defines the static setting without any motion or action.
        MODE A (empty): no people present. MODE B (with extras): background extras, clear foreground for characters.
        """
        # Check if scene already has an environment block - reuse it
        if hasattr(scene, 'environment_block') and scene.environment_block:
            return scene.environment_block
        
        if not self._adapter:
            # Fallback to basic environment description if no AI available
            return "a static establishing frame set in a cinematic location, grounded realistic environment, no motion"
        
        # Scene-driven mode: MODE A (empty) vs MODE B (with extras)
        scene_desc = scene.description or ""
        requires_extras = self._scene_requires_extras(scene_desc, scene_content or "")
        
        # Generate unique environment ID for tracking
        import hashlib
        scene_key = f"scene:{scene.scene_id}"
        env_hash = hashlib.md5(scene_key.encode()).hexdigest()[:4].upper()
        environment_id = f"ENV_{env_hash}"
        
        # Use scene content and description to extract environment details
        context_text = f"{scene.description}\n\n{scene_content[:2000]}"  # Limit to first 2000 chars for efficiency
        
        if requires_extras:
            mode_instructions = """
ENVIRONMENT MODE: WITH EXTRAS (MODE B).
The scene references guests, crowd, audience, or similar. Include BACKGROUND EXTRAS in the environment.
- Extras must be: non-distinct, non-identifiable, visually subordinate to named characters.
- In your output include: extras density (sparse, medium, or dense), extras activities (e.g. "seated guests", "mingling crowd"), extras depth (background_only, midground, or background_and_midground).
- CRITICAL: State that the FOREGROUND is CLEAR / unobstructed for character placement. Named characters are placed at storyboard level; extras are baked into the environment only in background/midground.
Example ending: "...soft-focus seated guests in the background, sparse density, clear foreground, grounded realistic environment, no motion"
"""
        else:
            mode_instructions = """
ENVIRONMENT MODE: EMPTY (MODE A).
No background people. The environment must have NO people visible.
- In your output explicitly include: no people present, empty, unoccupied.
- Reference images for this environment must contain no people. Used for full character placement at storyboard level.
Example: "...no people present, empty, unoccupied, grounded realistic environment, no motion"
"""
        
        prompt = f"""You are a script supervisor creating a STATIC ENVIRONMENT BLOCK for a video production scene.
{mode_instructions}

⚠️ CRITICAL RULES - FOLLOW THESE EXACTLY:
1. Extract ONLY environmental details from the provided scene content
2. DO NOT include character actions, movements, or story progression
3. DO NOT use motion verbs (walking, running, moving, driving, etc.)
4. Focus on the STATIC setting - what the location IS, not what happens in it

SCENE DESCRIPTION:
{scene.description}

SCENE CONTENT (extract environment details from this):
{context_text}

Create an ENVIRONMENT BLOCK following this EXACT template structure:

"a static establishing frame set in [location type],
with [physical surroundings],
[time of day],
[weather],
[lighting description],
grounded realistic environment,
no motion"

REQUIRED FIELDS TO EXTRACT:
1. **Location Type**: Geography/setting (e.g., "a desolate highway", "an interior office", "a forest clearing")
2. **Physical Surroundings**: Architecture or natural features (e.g., "asphalt road stretching into distance", "concrete walls and fluorescent lights")
3. **Time of Day**: When this takes place (e.g., "midday", "early morning", "dusk", "night")
4. **Weather**: Atmospheric conditions (e.g., "clear skies", "overcast", "light rain")
5. **Lighting Description**: Quality and direction of light (e.g., "harsh sunlight from above", "soft diffused daylight", "dim artificial lighting")

EXAMPLES OF CORRECT OUTPUT:

Example 1 (Outdoor):
"a static establishing frame set in a desolate highway landscape,
with asphalt road stretching into the distance and sparse vegetation,
midday,
clear skies with bright sunshine,
harsh direct sunlight casting sharp shadows,
grounded realistic environment,
no motion"

Example 2 (Interior):
"a static establishing frame set in a dimly lit office interior,
with concrete walls, metal desk, and filing cabinets,
late afternoon,
no visible weather (interior),
soft diffused light from a single window,
grounded realistic environment,
no motion"

IMPORTANT:
- Use ONLY details explicitly mentioned in the scene content
- If a detail is not mentioned, make a reasonable inference based on context
- Keep descriptions STATIC - no action words
- The template structure is MANDATORY - follow it exactly

Output ONLY the environment block text - no labels, no explanations, no markdown."""
        
        try:
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You are a script supervisor creating static environment descriptions. Extract only environmental details from scene content. Never include character actions or movements."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,  # Low temperature for consistent extraction
                max_tokens=300
            )
            
            content = response.choices[0].message.content
            if not content:
                raise Exception("AI returned empty environment block")
            
            environment_block = content.strip()
            # Clean up any quotes or markdown
            environment_block = environment_block.strip('"').strip("'").strip()
            
            # Validate that it starts with expected phrase
            if not environment_block.startswith("a static establishing frame"):
                # Try to fix it
                if "static establishing frame" in environment_block.lower():
                    # Extract from where it appears
                    match = re.search(r'(a static establishing frame.*)', environment_block, re.IGNORECASE | re.DOTALL)
                    if match:
                        environment_block = match.group(1)
                else:
                    # Prepend the required start
                    environment_block = f"a static establishing frame set in {environment_block}"
            
            # Ensure it ends with "no motion" if not already present
            if "no motion" not in environment_block.lower():
                environment_block = f"{environment_block.rstrip(',')}, no motion"
            
            # Inject MODE A / MODE B language if missing
            if requires_extras:
                if "clear foreground" not in environment_block.lower() and "foreground unobstructed" not in environment_block.lower() and "foreground clear" not in environment_block.lower():
                    environment_block = f"{environment_block.rstrip(',')}, clear foreground for character placement"
            else:
                if "no people" not in environment_block.lower() and "empty" not in environment_block.lower() and "unoccupied" not in environment_block.lower():
                    environment_block = f"{environment_block.rstrip(',')}, no people present, empty, unoccupied"
            
            # Validate the environment block
            if not self._validate_environment_block(environment_block):
                print(f"Warning: Generated environment block for scene {scene.scene_id} failed validation")
                # Try to fix it
                if not environment_block.lower().startswith("a static establishing frame"):
                    environment_block = f"a static establishing frame set in {environment_block}"
                if "no motion" not in environment_block.lower():
                    environment_block = f"{environment_block.rstrip(',')}, no motion"
            
            # Store in scene
            if hasattr(scene, 'environment_block'):
                scene.environment_block = environment_block
            if hasattr(scene, 'environment_id'):
                scene.environment_id = environment_id
            
            # Update identity_block_metadata for this scene's environment (placeholder may use different id prefix)
            if screenplay and hasattr(screenplay, 'identity_block_metadata'):
                scene_env_id = getattr(scene, 'environment_id', None)
                for eid, meta in screenplay.identity_block_metadata.items():
                    if meta.get("type") == "environment" and (eid == scene_env_id or meta.get("scene_id") == scene.scene_id):
                        screenplay.update_identity_block_metadata(eid, extras_present=requires_extras, foreground_zone="clear")
                        if requires_extras:
                            screenplay.update_identity_block_metadata(eid, extras_density="sparse", extras_activities="", extras_depth="background_only")
                        break
            
            return environment_block
            
        except Exception as e:
            error_message = str(e)
            print(f"Warning: Failed to generate environment block: {error_message}")
            # Fallback to basic environment description
            fallback = "a static establishing frame set in a cinematic location, grounded realistic environment, no motion"
            if hasattr(scene, 'environment_block'):
                scene.environment_block = fallback
            return fallback
    
    def _build_higgsfield_prompt(self, section_a: str, section_b: str, section_c: str, section_d: str, section_e: str) -> str:
        """Assemble the five-section Higgsfield prompt structure."""
        # Combine sections with proper formatting
        # Sections A, B, D, E are always required. Section C is optional (only if entities exist)
        sections = [section_a.strip(), section_b.strip()]
        # Add Section C only if it's not empty
        if section_c and section_c.strip():
            sections.append(section_c.strip())
        sections.extend([section_d.strip(), section_e.strip()])
        # Join with spaces, ensuring no double spaces
        result = " ".join(s.strip() for s in sections if s.strip())
        # Clean up any double commas or double spaces
        result = re.sub(r',\s*,', ',', result)  # Remove double commas
        result = re.sub(r'\s+', ' ', result)  # Remove multiple spaces
        return result
    
    def _build_motion_video_prompt(
        self,
        duration: int,
        storyline: str,
        dialogue: str,
        camera_notes: str,
        entity_names: List[str] = None
    ) -> tuple[str, str]:
        """Build a motion-focused video prompt for Higgsfield.ai.
        
        This creates a prompt focused on MOVEMENT and DIALOGUE only, not identity details.
        Visual identity comes from separate reference images in Higgsfield Cinema Studio.
        Duration and camera settings are handled separately in Higgsfield UI.
        
        The prompt describes:
        1. Actions and movements (using entity names, not descriptions)
        2. Dialogue
        
        Does NOT include duration or camera details - those are set separately in Higgsfield.
        Does NOT include detailed visual descriptions of entities - those come from reference images.
        
        Args:
            duration: Duration in seconds - used for guidance only
            storyline: The storyline text (describes what happens)
            dialogue: Any dialogue in this segment
            camera_notes: Camera movement instructions - used for guidance only
            entity_names: List of entity names to reference in motion description
            
        Returns:
            tuple: (motion_prompt, guidance_text)
        """
        prompt_parts = []
        
        # Section 1: Action and Movement
        if storyline and storyline.strip():
            # Extract only movement and actions from storyline, not environment descriptions
            action_text = self._extract_motion_from_storyline(storyline.strip())
            if action_text:
                prompt_parts.append(action_text)
        
        # Section 2: Dialogue (if any)
        if dialogue and dialogue.strip():
            # Parse dialogue - format is typically "Character: dialogue text" or just "dialogue text"
            clean_dialogue = dialogue.strip()
            character_name = None
            dialogue_text = clean_dialogue
            
            # Check if dialogue contains character name (format: "Character: dialogue")
            if ':' in clean_dialogue:
                parts = clean_dialogue.split(':', 1)
                if len(parts) == 2:
                    potential_char = parts[0].strip()
                    dialogue_text = parts[1].strip()
                    # If the part before colon looks like a character name (not too long, capitalized)
                    if len(potential_char) < 50 and potential_char and potential_char[0].isupper():
                        character_name = potential_char
            
            # Format dialogue according to Higgsfield requirements
            if character_name:
                formatted_dialogue = f"{character_name} speaks the following line verbatim, with no paraphrasing or changes: \"{dialogue_text}\" Dialogue constraint: spoken dialogue must match the provided text exactly, no paraphrasing, no substitutions, no additional words"
            else:
                # If no character name found, use generic format
                formatted_dialogue = f"Character speaks the following line verbatim, with no paraphrasing or changes: \"{dialogue_text}\" Dialogue constraint: spoken dialogue must match the provided text exactly, no paraphrasing, no substitutions, no additional words"
            
            prompt_parts.append(formatted_dialogue)
        
        # Join prompt parts
        if prompt_parts:
            result = " | ".join(prompt_parts)
        else:
            result = "Natural movement and realistic motion."
        
        # Clean up formatting
        result = re.sub(r'\s+', ' ', result)
        result = result.strip()
        
        # Create guidance text for Higgsfield settings
        guidance_parts = []
        guidance_parts.append(f"Duration: {duration} seconds")
        
        if camera_notes and camera_notes.strip():
            camera_text = camera_notes.strip()
        else:
            camera_text = "Medium shot, steady camera with subtle movement"
        guidance_parts.append(f"Camera: {camera_text}")
        
        guidance_text = " | ".join(guidance_parts)
        
        return result, guidance_text
    
    def _inject_identity_references(self, text: str, screenplay: Screenplay) -> str:
        """Inject identity block IDs into text when entities are mentioned,
        preserving cinematic markup (_underscores_, [brackets], {braces}, FULL CAPS).
        
        For each entity type the output format preserves the original markup:
        - Environments: _Entity Name_ (ENVIRONMENT_XXXX)
        - Objects: [Entity Name] (OBJECT_XXXX)  
        - Vehicles: {Entity Name} (VEHICLE_XXXX)
        - Characters: CHARACTER NAME (CHARACTER_XXXX)
        
        Args:
            text: Text that may contain entity names with cinematic markup
            screenplay: Screenplay object containing identity_block_ids mapping
            
        Returns:
            Text with identity block references injected, markup preserved
        """
        if not text or not screenplay.identity_block_ids:
            return text
        
        result = text
        import re
        
        # Process each identity block mapping (longer names first to avoid partial matches)
        items = list(screenplay.identity_block_ids.items())
        items.sort(key=lambda kv: len(kv[0]), reverse=True)
        for lookup_key, entity_id in items:
            if ':' not in lookup_key:
                continue
                
            # Extract entity name from "type:name" format
            entity_type, entity_name = lookup_key.split(':', 1)
            entity_name = entity_name.strip()
            
            if not entity_name:
                continue

            # Prefer canonical display name from metadata (prevents drift like Jasmin/Jill)
            canonical_name = entity_name
            try:
                meta = screenplay.identity_block_metadata.get(entity_id, {})
                if isinstance(meta, dict) and meta.get("name"):
                    canonical_name = str(meta.get("name")).strip() or entity_name
            except Exception:
                canonical_name = entity_name
            
            # Check if entity is already referenced (avoid double injection)
            if f"({entity_id})" in result:
                continue
            
            escaped_name = re.escape(entity_name)
            injected = False
            
            # ── MARKUP-AWARE REPLACEMENT ──
            # Try to match the entity name WITH its surrounding markup first,
            # preserving the markup and appending the identity ID after it.
            
            if entity_type == 'environment':
                # Match _Entity Name_ → _Entity Name_ (ENVIRONMENT_XXXX)
                markup_pattern = rf'_({escaped_name})_'
                markup_match = re.search(markup_pattern, result, flags=re.IGNORECASE)
                if markup_match:
                    original_name = markup_match.group(1)
                    replacement = f"_{original_name}_ ({entity_id})"
                    result = result[:markup_match.start()] + replacement + result[markup_match.end():]
                    injected = True
                    
            elif entity_type == 'object':
                # Match [Entity Name] → [Entity Name] (OBJECT_XXXX)
                markup_pattern = rf'\[({escaped_name})\]'
                markup_match = re.search(markup_pattern, result, flags=re.IGNORECASE)
                if markup_match:
                    original_name = markup_match.group(1)
                    replacement = f"[{original_name}] ({entity_id})"
                    result = result[:markup_match.start()] + replacement + result[markup_match.end():]
                    injected = True
                    
            elif entity_type == 'vehicle':
                # Match {Entity Name} or {{Entity Name}} → {Entity Name} (VEHICLE_XXXX)
                # Try double braces first (common in scene content)
                markup_pattern_double = rf'\{{\{{({escaped_name})\}}\}}'
                markup_match = re.search(markup_pattern_double, result, flags=re.IGNORECASE)
                if markup_match:
                    original_name = markup_match.group(1)
                    replacement = f"{{{{{original_name}}}}} ({entity_id})"
                    result = result[:markup_match.start()] + replacement + result[markup_match.end():]
                    injected = True
                else:
                    # Try single braces
                    markup_pattern_single = rf'\{{({escaped_name})\}}'
                    markup_match = re.search(markup_pattern_single, result, flags=re.IGNORECASE)
                    if markup_match:
                        original_name = markup_match.group(1)
                        replacement = f"{{{original_name}}} ({entity_id})"
                        result = result[:markup_match.start()] + replacement + result[markup_match.end():]
                        injected = True
                        
            elif entity_type == 'character':
                # Characters use FULL CAPS — match the name and preserve caps
                # Check for FULL CAPS version first
                caps_name = canonical_name.upper()
                caps_pattern = rf'\b{re.escape(caps_name)}\b'
                caps_match = re.search(caps_pattern, result)
                if caps_match:
                    original_name = caps_match.group(0)
                    replacement = f"{original_name} ({entity_id})"
                    result = result[:caps_match.start()] + replacement + result[caps_match.end():]
                    injected = True
            
            # ── FALLBACK: bare name without markup ──
            # If the markup-aware match didn't find anything, try plain name match
            # and ADD the appropriate markup around it
            if not injected:
                bare_pattern = rf'\b{escaped_name}\b'
                bare_match = re.search(bare_pattern, result, flags=re.IGNORECASE)
                if bare_match:
                    original_name = bare_match.group(0)
                    if entity_type == 'environment':
                        replacement = f"_{canonical_name}_ ({entity_id})"
                    elif entity_type == 'object':
                        replacement = f"[{canonical_name}] ({entity_id})"
                    elif entity_type == 'vehicle':
                        replacement = f"{{{{{canonical_name}}}}} ({entity_id})"
                    elif entity_type == 'character':
                        replacement = f"{canonical_name.upper()} ({entity_id})"
                    else:
                        replacement = f"{canonical_name} ({entity_id})"
                    result = result[:bare_match.start()] + replacement + result[bare_match.end():]
        
        return result
    
    def _enforce_full_character_names(self, text: str, screenplay: Screenplay) -> str:
        """Replace abbreviated or partial character names with full registered names.
        
        Ensures characters are always referred to by their complete FULL CAPS name
        as registered in the character_registry (e.g. "Fleck" → "DETECTIVE JUDE FLECK",
        "McCormack" → "SEAN MCCORMACK").
        
        Only replaces standalone occurrences — names already in full form or inside
        dialogue quotes are left untouched.
        """
        if not text or not screenplay:
            return text
        
        import re
        
        # Build list of full registered character names
        full_names = []
        if getattr(screenplay, 'character_registry', None):
            full_names = list(screenplay.character_registry)
        elif getattr(screenplay, 'identity_block_metadata', None):
            for _eid, meta in screenplay.identity_block_metadata.items():
                if (meta.get("type") or "").lower() == "character":
                    name = (meta.get("name") or "").strip()
                    if name:
                        full_names.append(name.upper())
        
        if not full_names:
            return text
        
        # Common title/rank words that should not trigger a match on their own
        _TITLE_WORDS = frozenset({
            "DR", "MR", "MRS", "MS", "DETECTIVE", "OFFICER", "SERGEANT",
            "CAPTAIN", "GENERAL", "PRIVATE", "CORPORAL", "MAJOR",
            "COLONEL", "LIEUTENANT", "COMMANDER", "AGENT", "INSPECTOR",
            "PROFESSOR", "CHIEF", "DUKE", "PRINCE", "PRINCESS", "KING",
            "QUEEN", "LORD", "LADY", "SIR", "BARON", "COUNT", "DC",
        })
        
        result = text
        
        # Process each full name (longest first to avoid partial overlap issues)
        for full_name in sorted(full_names, key=len, reverse=True):
            full_upper = full_name.upper()
            words = full_upper.split()
            
            # Build clean words (strip quotes) and nickname
            clean_words = [w.strip("'\"") for w in words]
            nickname = self._extract_nickname_from_full_name(full_name)
            
            # Build partial words: significant non-title words (>= 3 chars)
            partials = []
            for cw in clean_words:
                if cw and cw not in _TITLE_WORDS and len(cw) >= 3:
                    partials.append(cw)
            if not partials:
                continue
            
            # Build multi-word abbreviated forms to detect and replace as a whole.
            # e.g. for "SIR REGINALD 'REG' BARTLETT": detect "SIR REGINALD",
            # "SIR REG", "REGINALD BARTLETT" etc.
            abbrev_patterns = []
            # Title + first significant word (e.g. "SIR REGINALD")
            title_words = [w for w in clean_words if w in _TITLE_WORDS]
            if title_words and partials:
                for tw in title_words:
                    for pw in partials:
                        combo = f"{tw} {pw}"
                        if combo.upper() != full_upper and len(combo) > 4:
                            abbrev_patterns.append(combo)
                # Title + nickname (e.g. "SIR REG")
                if nickname and len(nickname) >= 3:
                    for tw in title_words:
                        combo = f"{tw} {nickname.upper()}"
                        if combo.upper() != full_upper:
                            abbrev_patterns.append(combo)
            # First + last without nickname (e.g. "REGINALD BARTLETT")
            non_title = [w for w in clean_words if w not in _TITLE_WORDS and len(w) >= 2]
            if len(non_title) >= 2:
                for i in range(len(non_title)):
                    for j in range(i + 1, len(non_title)):
                        combo = f"{non_title[i]} {non_title[j]}"
                        if combo.upper() != full_upper:
                            abbrev_patterns.append(combo)
            # Sort longest first
            abbrev_patterns = sorted(set(abbrev_patterns), key=len, reverse=True)
            
            # Replace multi-word abbreviated forms first
            for abbrev in abbrev_patterns:
                pat = re.compile(r'\b' + re.escape(abbrev) + r'\b', re.IGNORECASE)
                changed = True
                while changed:
                    changed = False
                    full_spans = [(fm.start(), fm.end()) for fm in re.finditer(re.escape(full_upper), result)]
                    for match in reversed(list(pat.finditer(result))):
                        start, end = match.start(), match.end()
                        if any(fs <= start and end <= fe for fs, fe in full_spans):
                            continue
                        quote_count = result[:start].count('"')
                        if quote_count % 2 == 1:
                            continue
                        result = result[:start] + full_upper + result[end:]
                        changed = True
                        break
            
            # Then replace single-word partials (longest first)
            for partial in sorted(partials, key=len, reverse=True):
                pattern = re.compile(r'\b' + re.escape(partial) + r'\b', re.IGNORECASE)
                
                changed = True
                while changed:
                    changed = False
                    
                    full_spans = [(fm.start(), fm.end()) for fm in re.finditer(re.escape(full_upper), result)]
                    
                    matches = list(pattern.finditer(result))
                    for match in reversed(matches):
                        start, end = match.start(), match.end()
                        
                        if any(fs <= start and end <= fe for fs, fe in full_spans):
                            continue
                        
                        quote_count = result[:start].count('"')
                        if quote_count % 2 == 1:
                            continue
                        
                        result = result[:start] + full_upper + result[end:]
                        changed = True
                        break
        
        return result

    def _detect_appearing_objects(self, storyline: str, screenplay: Screenplay) -> set:
        """Detect which objects are appearing/revealing in the storyline.
        
        Objects that are appearing/revealing should be excluded from image prompts
        (image = state BEFORE action).
        
        Args:
            storyline: The storyline text to analyze
            screenplay: Screenplay object containing identity_block_ids mapping
            
        Returns:
            Set of entity IDs that are appearing/revealing
        """
        appearing_ids = set()
        
        if not storyline or not screenplay.identity_block_ids:
            return appearing_ids
        
        import re
        storyline_lower = storyline.lower()
        
        # Appearance/reveal verbs that indicate an object is appearing
        appearance_verbs = [
            'appears', 'appear', 'appearing', 'appearance',
            'reveals', 'reveal', 'revealing', 'revealed',
            'bursts', 'burst', 'bursting',
            'erupts', 'erupt', 'erupting',
            'emerges', 'emerge', 'emerging',
            'forms', 'form', 'forming',
            'materializes', 'materialize', 'materializing',
            'pops up', 'pops', 'popping',
            'shows up', 'shows', 'showing',
            'becomes visible', 'becomes', 'becoming',
            'comes into view', 'comes', 'coming'
        ]
        
        # Process each identity block mapping
        for lookup_key, entity_id in screenplay.identity_block_ids.items():
            if ':' not in lookup_key:
                continue
            
            entity_type, entity_name = lookup_key.split(':', 1)
            entity_name = entity_name.strip()
            
            if not entity_name:
                continue
            
            # Only check objects (not characters or environments for appearing)
            if entity_type.lower() not in ['object']:
                continue
            
            # Find entity name in storyline
            entity_index = storyline_lower.find(entity_name.lower())
            
            if entity_index >= 0:
                # Check context around entity name (100 chars before and after)
                context_start = max(0, entity_index - 100)
                context_end = min(len(storyline_lower), entity_index + len(entity_name) + 100)
                context = storyline_lower[context_start:context_end]
                
                # Check if any appearance verb appears near the entity name
                if any(verb in context for verb in appearance_verbs):
                    appearing_ids.add(entity_id)
        
        return appearing_ids
    
    def _extract_motion_from_storyline(self, storyline: str) -> str:
        """Extract ALL dynamic motion and changes from storyline text, including non-character motion.
        
        Motion includes:
        - Character movements and actions (if characters are present)
        - Object appearances/disappearances (logo reveals, product shots)
        - Environmental changes (light, color, particles, explosions)
        - Graphic motion (text forming, symbols emerging, shapes swirling)
        - Camera movement
        - Energy, smoke, fire, water, abstract motion
        - Transitions and transformations
        
        Args:
            storyline: Full storyline text that may include environment and scene descriptions
            
        Returns:
            Motion-focused text describing ALL dynamic elements and changes
        """
        if not self._adapter:
            # Fallback: use simple pattern matching if AI not available
            return self._extract_motion_fallback(storyline)
        
        try:
            prompt = f"""Extract ALL motion and dynamic changes from this storyline for video animation.

STORYLINE: {storyline}

Extract ALL types of motion and changes, including:

CHARACTER MOTION (if characters are present):
- Character movements (walks, runs, sits, stands, turns, etc.)
- Physical actions (picks up, puts down, opens, closes, etc.) 
- Character interactions (hugs, shakes hands, points at, etc.)
- Facial expressions and gestures

NON-CHARACTER MOTION (ALWAYS extract these, even if no characters):
- Object appearances/disappearances (logo appears, product reveals, text forms)
- Environmental changes (light shifts, colors change, particles move)
- Graphic motion (symbols emerging, shapes swirling, typography animating)
- Visual effects (energy pulses, smoke rises, fire spreads, water flows)
- Transitions and transformations (fade in, burst onto, erupts, emerges)
- Camera movement (if mentioned)

CRITICAL RULES:
- Motion is NOT limited to characters - extract motion from ALL dynamic elements
- If storyline describes "logo appears" or "colors erupt", that IS motion
- Include environmental motion (light changes, particle effects, etc.)
- Include graphic motion (text forming, symbols emerging, etc.)
- Do NOT include static environment descriptions (location, setting, static objects)
- Do NOT include static atmosphere descriptions (mood, tone without change)

Return only the motion description, nothing else. If no motion is present, return "Static scene, no motion"."""

            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You extract ALL types of motion and dynamic changes from scene descriptions, including character motion, object appearances, environmental changes, graphic motion, visual effects, and transitions. Motion is NOT limited to characters - you extract motion from ALL dynamic elements even when no characters are present."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=300
            )
            
            motion_text = response.choices[0].message.content.strip()
            
            # Validate that we got motion-focused content
            # Check if it says "no motion" when there are clearly action verbs in the storyline
            storyline_lower = storyline.lower()
            action_verbs = ['appears', 'appear', 'bursts', 'burst', 'erupts', 'erupt', 'forms', 'form', 'emerges', 'emerge', 
                          'swirls', 'swirl', 'reveals', 'reveal', 'transforms', 'transform', 'changes', 'change',
                          'moves', 'move', 'shifts', 'shift', 'rises', 'rise', 'spreads', 'spread', 'flows', 'flow',
                          'animates', 'animate', 'pulses', 'pulse', 'glows', 'glow', 'fades', 'fade']
            
            has_action_verbs = any(verb in storyline_lower for verb in action_verbs)
            motion_lower = motion_text.lower()
            
            # If storyline has action verbs but motion text says "no motion", that's an error
            if has_action_verbs and ('no motion' in motion_lower or 'static' in motion_lower):
                print(f"WARNING: Storyline contains action verbs but motion extraction returned 'no motion'. Using fallback.")
                return self._extract_motion_fallback(storyline)
            
            # If motion text is empty or too short, use fallback
            if not motion_text or len(motion_text) < 10:
                return self._extract_motion_fallback(storyline)
            
            return motion_text
            
        except Exception as e:
            print(f"AI motion extraction failed: {e}")
            return self._extract_motion_fallback(storyline)
    
    def _extract_motion_fallback(self, storyline: str) -> str:
        """Fallback method to extract motion using pattern matching.
        
        Extracts ALL types of motion, not just character motion.
        """
        # Look for action verbs and movement patterns
        import re
        
        # Character action verbs and movement words
        character_motion_patterns = [
            r'[A-Z][a-z]+\s+(?:walks?|runs?|moves?|steps?|approaches?|turns?|sits?|stands?|dances?|laughs?|smiles?|looks?|reaches?|grabs?|picks?\s+up|puts?\s+down|opens?|closes?)',
            r'[A-Z][a-z]+\s+(?:enters?|exits?|arrives?|leaves?|comes?|goes?)',
            r'[A-Z][a-z]+\s+(?:speaks?|says?|shouts?|whispers?|calls?)',
            r'(?:They|He|She)\s+(?:walk|run|move|step|approach|turn|sit|stand|dance|laugh|smile|look|reach|grab|pick\s+up|put\s+down|open|close)',
            r'(?:walking|running|moving|stepping|approaching|turning|sitting|standing|dancing|laughing|smiling|looking|reaching|grabbing)'
        ]
        
        # Non-character motion patterns (appearances, reveals, environmental changes, etc.)
        non_character_motion_patterns = [
            r'(?:appears?|appearing|appearance)',
            r'(?:reveals?|revealing|reveal)',
            r'(?:bursts?|bursting|burst)',
            r'(?:erupts?|erupting|erupt)',
            r'(?:forms?|forming|form)',
            r'(?:emerges?|emerging|emerge)',
            r'(?:swirls?|swirling|swirl)',
            r'(?:transforms?|transforming|transform)',
            r'(?:changes?|changing|change)',
            r'(?:shifts?|shifting|shift)',
            r'(?:rises?|rising|rise)',
            r'(?:spreads?|spreading|spread)',
            r'(?:flows?|flowing|flow)',
            r'(?:animates?|animating|animate)',
            r'(?:pulses?|pulsing|pulse)',
            r'(?:glows?|glowing|glow)',
            r'(?:fades?|fading|fade)',
            r'(?:rotates?|rotating|rotate)',
            r'(?:spins?|spinning|spin)',
            r'(?:floats?|floating|float)',
            r'(?:drifts?|drifting|drift)',
            r'(?:explodes?|exploding|explode)',
            r'(?:dissolves?|dissolving|dissolve)',
            r'(?:materializes?|materializing|materialize)',
            r'(?:vanishes?|vanishing|vanish)',
            r'(?:expands?|expanding|expand)',
            r'(?:contracts?|contracting|contract)',
            r'(?:morphs?|morphing|morph)',
            r'(?:transitions?|transitioning|transition)',
            r'(?:logo|text|symbol|graphic|shape|particle|light|energy|smoke|fire|water|color|kaleidoscope).*?(?:appears?|reveals?|bursts?|erupts?|forms?|emerges?|swirls?|transforms?|changes?|moves?|shifts?|rises?|spreads?|flows?|animates?|pulses?|glows?|fades?)',
            r'(?:the screen|the frame|the image).*?(?:erupts?|bursts?|transforms?|changes?|shifts?)',
        ]
        
        # Camera movement patterns
        camera_motion_patterns = [
            r'(?:camera|shot|view|angle).*?(?:moves?|pans?|tilts?|zooms?|tracks?|dollies?|cranes?|rotates?|sweeps?)',
            r'(?:panning|tilting|zooming|tracking|dollying|craning|rotating|sweeping)',
        ]
        
        motion_sentences = []
        sentences = re.split(r'[.!?]+', storyline)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # Check if sentence contains ANY type of motion
            has_character_motion = any(re.search(pattern, sentence, re.IGNORECASE) for pattern in character_motion_patterns)
            has_non_character_motion = any(re.search(pattern, sentence, re.IGNORECASE) for pattern in non_character_motion_patterns)
            has_camera_motion = any(re.search(pattern, sentence, re.IGNORECASE) for pattern in camera_motion_patterns)
            
            # Also check for character names followed by action verbs
            character_action = re.search(r'[A-Z][a-z]+\s+[a-z]*(?:ed|s|ing)\b', sentence)
            
            if has_character_motion or has_non_character_motion or has_camera_motion or character_action:
                # Extract motion-related parts, but keep non-character motion
                clean_sentence = sentence
                
                # Remove ONLY static environment phrases (but keep dynamic environmental changes)
                # Only remove if they're truly static, not if they're part of motion
                static_environment_phrases = [
                    r'\ba trendy downtown warehouse\b(?!.*?(?:appears?|transforms?|erupts?))',
                    r'\bparty venue\b(?!.*?(?:erupts?|changes?|transforms?))',
                    r'\bpolished concrete floor\b(?!.*?(?:shifts?|changes?|transforms?))',
                ]
                
                for phrase in static_environment_phrases:
                    clean_sentence = re.sub(phrase, '', clean_sentence, flags=re.IGNORECASE)
                
                # Clean up extra spaces and punctuation
                clean_sentence = re.sub(r'\s+', ' ', clean_sentence).strip()
                clean_sentence = re.sub(r'^[,\s]+|[,\s]+$', '', clean_sentence)
                
                if clean_sentence and len(clean_sentence) > 10:
                    motion_sentences.append(clean_sentence)
        
        if motion_sentences:
            return '. '.join(motion_sentences) + '.'
        else:
            # Check if there are any action verbs at all in the storyline
            storyline_lower = storyline.lower()
            all_action_verbs = [
                'appears', 'appear', 'bursts', 'burst', 'erupts', 'erupt', 'forms', 'form',
                'emerges', 'emerge', 'swirls', 'swirl', 'reveals', 'reveal', 'transforms', 'transform',
                'changes', 'change', 'moves', 'move', 'shifts', 'shift', 'rises', 'rise',
                'spreads', 'spread', 'flows', 'flow', 'animates', 'animate', 'pulses', 'pulse',
                'glows', 'glow', 'fades', 'fade', 'rotates', 'rotate', 'spins', 'spin',
                'floats', 'float', 'drifts', 'drift', 'explodes', 'explode', 'dissolves', 'dissolve',
                'materializes', 'materialize', 'vanishes', 'vanish', 'expands', 'expand',
                'contracts', 'contract', 'morphs', 'morph', 'transitions', 'transition'
            ]
            
            has_any_motion = any(verb in storyline_lower for verb in all_action_verbs)
            
            if has_any_motion:
                # There's motion but we didn't extract it properly - return a generic motion description
                return "Dynamic visual elements animate and transform."
            else:
                # Truly static scene
                return "Static scene, no motion."
    
    def _build_first_frame_image_prompt(
        self, 
        environment_block: str, 
        entity_identity_blocks: List[str], 
        storyline: str,
        item: 'StoryboardItem',
        screenplay: 'Screenplay',
        appearing_object_ids: set = None,
        scene_id: str = ""
    ) -> str:
        """Build a Popcorn-style keyframe prompt for Higgsfield Cinema Studio 2.0.
        
        Produces a structured static-scene description following the Popcorn
        field layout: shot type, camera framing, lighting, environment, lens,
        mood.  No motion verbs — this is a hero-frame prompt.
        """
        from .screenplay_engine import SHOT_TYPE_OPTIONS, APERTURE_STYLE_OPTIONS
        from .video_prompt_builder import _make_static_description

        parts: list[str] = []

        # 1. Shot type and subject — strip all motion from storyline
        shot_key = getattr(item, 'shot_type', 'medium') or 'medium'
        shot_label = SHOT_TYPE_OPTIONS.get(shot_key, "Medium Shot")

        static_text = _make_static_description(storyline or "")
        if static_text:
            parts.append(f"{shot_label} of {static_text}")
        else:
            entity_names = self._collect_entity_names(entity_identity_blocks, screenplay, appearing_object_ids)
            if entity_names:
                parts.append(f"{shot_label} of {', '.join(entity_names)}")
            else:
                parts.append(shot_label)

        # 2. Lighting
        lighting = (getattr(item, 'lighting_description', '') or '').strip()
        if lighting:
            parts.append(f"Lighting: {lighting}")

        # 3. Environment
        env_name = ""
        if screenplay and scene_id:
            scene_obj = screenplay.get_scene(scene_id)
            if scene_obj:
                env_id = getattr(scene_obj, 'environment_id', None)
                if env_id:
                    env_meta = screenplay.identity_block_metadata.get(env_id, {})
                    env_name = env_meta.get("name", "").strip()
        if env_name:
            parts.append(f"Setting: {env_name}")

        # 4. Lens / film look
        focal = getattr(item, 'focal_length', 35) or 35
        aperture_key = getattr(item, 'aperture_style', 'cinematic_bokeh') or 'cinematic_bokeh'
        aperture_label = APERTURE_STYLE_OPTIONS.get(aperture_key, 'Cinematic Bokeh')
        parts.append(f"{focal}mm lens, {aperture_label.lower()}")

        # 5. Mood and tone
        mood = (getattr(item, 'mood_tone', '') or '').strip()
        if mood:
            parts.append(f"Mood: {mood}")
        elif screenplay and screenplay.atmosphere:
            parts.append(f"Mood: {screenplay.atmosphere}")

        return ". ".join(parts)

    def _collect_entity_names(self, entity_identity_blocks, screenplay, appearing_object_ids=None):
        """Extract entity names from identity blocks for use in prompts."""
        entity_names = []
        if entity_identity_blocks and screenplay:
            for block in entity_identity_blocks:
                if not block or not block.strip():
                    continue
                for entity_id, meta in screenplay.identity_block_metadata.items():
                    if meta.get("identity_block") == block:
                        if appearing_object_ids and entity_id in appearing_object_ids:
                            break
                        name = meta.get("name", "").strip()
                        if name:
                            entity_names.append(name)
                        break
        return entity_names
    
    def _validate_identity_block(self, block: str, entity_type: str) -> bool:
        """Validate that an identity block follows the required rules.
        
        Args:
            block: The identity block text to validate
            entity_type: The type of entity (character, vehicle, object, etc.)
            
        Returns:
            True if the block is valid, False otherwise
        """
        if not block or not isinstance(block, str):
            return False
        
        # Must start with "the same"
        if not block.lower().startswith("the same"):
            return False
        
        # Must be reasonably detailed (at least 50 characters)
        if len(block) < 50:
            return False
        
        # Should not contain motion verbs (these are for video prompts, not identity blocks)
        motion_verbs = ["walking", "running", "moving", "driving", "approaching", "entering", "exiting"]
        block_lower = block.lower()
        for verb in motion_verbs:
            if verb in block_lower:
                print(f"Warning: Identity block contains motion verb '{verb}': {block[:100]}...")
                return False
        
        return True
    
    def _strip_character_name_from_physical_appearance(self, text: str, character_name: str) -> str:
        """Remove character name from start of physical appearance (e.g. 'Sarah Chen has...' -> 'Has...')."""
        if not text or not character_name or not isinstance(text, str):
            return text
        name_escaped = re.escape(str(character_name).strip())
        pattern = rf'^\s*{name_escaped}\s+(?:has|is|has\s+a|has\s+an|\'s|—|-)\s+'
        stripped = re.sub(pattern, '', text, flags=re.IGNORECASE)
        if stripped != text:
            stripped = stripped.strip()
            if stripped and stripped[0].islower():
                stripped = stripped[0].upper() + stripped[1:]
            return stripped
        return text

    def _validate_environment_block(self, block: str) -> bool:
        """Validate that an environment block is static and follows the required template.
        
        Args:
            block: The environment block text to validate
            
        Returns:
            True if the block is valid, False otherwise
        """
        if not block or not isinstance(block, str):
            return False
        
        # Must start with "a static establishing frame"
        if not block.lower().startswith("a static establishing frame"):
            return False
        
        # Must end with "no motion"
        if "no motion" not in block.lower():
            return False
        
        # Should not contain motion verbs
        motion_verbs = ["walking", "running", "moving", "driving", "approaching", "entering", "exiting", "turning", "speaking"]
        block_lower = block.lower()
        for verb in motion_verbs:
            if verb in block_lower:
                print(f"Warning: Environment block contains motion verb '{verb}': {block[:100]}...")
                return False
        
        return True
    
    def _extract_prompt_sections(self, storyline: str, item: StoryboardItem, screenplay: Screenplay, is_image: bool = False, scene_content: str = None) -> Dict[str, str]:
        """Extract or generate the five sections for a Higgsfield prompt."""
        # Section A: Duration & Shot Integrity
        section_a = f"A continuous {item.duration}-second cinematic shot with no cuts,"
        
        # Section B: Location & Environment (extracted from storyline/prompts)
        # Try to extract from existing prompts or storyline
        location_text = ""
        if item.prompt:
            # Extract location from existing prompt
            location_match = re.search(r'(?:set on|location:|at|in|on)\s+([^,]+(?:,|\.|$))', item.prompt, re.IGNORECASE)
            if location_match:
                location_text = location_match.group(1).strip()
        
        if not location_text and storyline:
            # Try to extract from storyline - look for location keywords (NOT entities like vehicles)
            # Define entity words that should NOT be treated as locations
            entity_words = ["motorcycle", "car", "vehicle", "bike", "truck", "person", "character", "man", "woman"]
            location_keywords = ["highway", "road", "street", "asphalt", "room", "building", "field", "forest", "desert", "landscape", "countryside", "city", "interior", "exterior", "desolate"]
            storyline_lower = storyline.lower()
            
            # Look for location patterns - prioritize location keywords that are NOT entity words
            for keyword in location_keywords:
                if keyword in storyline_lower and keyword not in entity_words:
                    # Find the context around the keyword
                    match = re.search(r'([^.]*\b' + keyword + r'\b[^.]*)', storyline, re.IGNORECASE)
                    if match:
                        # Extract a location phrase but avoid entity words
                        phrase = match.group(1).strip()
                        # Remove entity references (e.g., "John's motorcycle")
                        phrase = re.sub(r'\b\w+\'?s?\s+(?:motorcycle|car|vehicle|bike|truck)\b', '', phrase, flags=re.IGNORECASE)
                        # Clean up action verbs to get just the location description
                        action_verbs_removed = re.sub(r'\b(beats|roars|echoing|through|as|the|sun|down)\b', '', phrase, flags=re.IGNORECASE)
                        location_text = action_verbs_removed.strip()
                        
                        # Extract just the location phrase (noun phrase with location keyword)
                        if location_text:
                            # Try to find just the location noun phrase
                            location_match = re.search(r'\b(?:the|a|an)?\s*([a-z]+(?:\s+[a-z]+)*\s+(?:highway|road|street|asphalt|landscape|countryside|room|building|field|forest|desert|desolate\s+\w+))\b', location_text, re.IGNORECASE)
                            if location_match:
                                location_text = location_match.group(1).strip()
                            else:
                                # Just use the keyword with a simple descriptor
                                if keyword == "asphalt":
                                    location_text = "the asphalt road"
                                elif keyword == "highway":
                                    location_text = "a highway"
                                elif keyword == "landscape":
                                    # Get the modifier before "landscape"
                                    landscape_match = re.search(r'(\w+)\s+landscape', storyline, re.IGNORECASE)
                                    if landscape_match:
                                        location_text = f"a {landscape_match.group(1)} landscape"
                                    else:
                                        location_text = "a landscape"
                                else:
                                    location_text = f"a {keyword}"
                        break
            
            # If still no location, try to extract from common patterns (excluding entities)
            if not location_text or any(entity in location_text.lower() for entity in entity_words):
                # Look for "on the X" or "at the X" patterns that are NOT entities
                location_match = re.search(r'(?:on|at|in|through|across|down on)\s+(?:the|a|an)?\s*([^,]+(?:highway|road|street|asphalt|landscape|countryside|room|building|field|forest|desert))', storyline, re.IGNORECASE)
                if location_match:
                    candidate = location_match.group(1).strip()
                    # Make sure it doesn't contain entity words
                    if not any(entity in candidate.lower() for entity in entity_words):
                        location_text = candidate
        
        # If still no location, provide a default based on storyline context
        if not location_text or location_text == "":
            if storyline:
                # Use a general location description based on context
                if any(word in storyline.lower() for word in ["highway", "road", "street", "asphalt"]):
                    location_text = "a highway or road"
                elif any(word in storyline.lower() for word in ["room", "building", "interior"]):
                    location_text = "an interior location"
                elif any(word in storyline.lower() for word in ["field", "forest", "countryside", "landscape"]):
                    location_text = "an outdoor landscape"
                else:
                    location_text = "a cinematic location"
            else:
                location_text = "a cinematic location"
        
        # Extract lighting/environment from storyline or prompts
        lighting_text = ""
        atmosphere = screenplay.atmosphere if screenplay.atmosphere else ""
        if atmosphere:
            lighting_text = f"{atmosphere.lower()} atmosphere"
        else:
            # Try to extract lighting from storyline
            if storyline:
                if "sun" in storyline.lower() or "bright" in storyline.lower() or "sunlight" in storyline.lower():
                    lighting_text = "bright sunny lighting"
                elif "dark" in storyline.lower() or "dim" in storyline.lower() or "shadows" in storyline.lower():
                    lighting_text = "dim lighting"
                elif "desolate" in storyline.lower():
                    lighting_text = "desolate atmosphere"
        
        # Build Section B - ensure no double spaces or commas
        lighting_desc = lighting_text if lighting_text else 'realistic lighting'
        section_b = f"set on {location_text}, {lighting_desc}, realistic environment,"
        
        # Section C: Identity Insertion (use ONLY pre-approved identity blocks)
        # NEW WORKFLOW: Entities are extracted upfront after scene generation
        # Users approve identity blocks BEFORE generating storyboard
        # This section now ONLY uses pre-approved blocks, no on-the-fly generation
        
        identity_blocks_text = []
        approved_entities = screenplay.get_approved_identity_blocks()
        
        for entity_meta in approved_entities:
            identity_block = entity_meta.get("identity_block", "")
            if identity_block and identity_block.strip():
                identity_blocks_text.append(identity_block.strip())
        
        if identity_blocks_text:
            section_c = f"featuring {', '.join(identity_blocks_text)},"
        else:
            section_c = ""
        
        # Section D: Action, Motion & Intent (variable - extracted from storyline)
        if is_image:
            # For image prompts: static descriptions only, no action verbs
            # Extract static positioning from storyline - PRESERVE ALL WORDS, just remove action verbs
            action_text = storyline if storyline else ""
            # Remove only specific action verbs, preserve all other words
            action_verbs_to_remove = ["walking", "running", "moving", "approaching", "entering", "turning", "speaking", "looking at"]
            for verb in action_verbs_to_remove:
                # Only remove if it's a standalone verb, not part of another word
                action_text = re.sub(rf'\b{verb}\b', '', action_text, flags=re.IGNORECASE)
            action_text = action_text.strip()
            # Replace action verbs with static equivalents, but keep all words
            action_text = action_text.replace("walks", "positioned").replace("runs", "positioned").replace("moves", "positioned")
            # Clean up multiple spaces but preserve content
            action_text = re.sub(r'\s+', ' ', action_text).strip()
            section_d = f"{action_text}," if action_text else ""
        else:
            # For video prompts: use EXACT storyline text - DO NOT shorten or modify
            # The storyline contains the exact scene content - use it verbatim
            action_text = storyline if storyline else ""
            if action_text:
                # Use the FULL storyline text - don't shorten it
                # Just ensure it ends with proper punctuation
                section_d = f"{action_text}, realistic motion, natural movement,"
            else:
                section_d = "realistic motion and natural movement,"
        
        # Section E: Camera Behavior
        camera_text = item.camera_notes if item.camera_notes else "medium shot, eye level angle"
        section_e = f"{camera_text}, subtle handheld cinematic shake, shallow depth of field, natural motion blur, grounded cinematic realism"
        
        return {
            "section_a": section_a,
            "section_b": section_b,
            "section_c": section_c,
            "section_d": section_d,
            "section_e": section_e
        }
    
    def regenerate_item_prompt(self, item: StoryboardItem, screenplay: Screenplay) -> str:
        """Regenerate the prompt for a specific storyboard item with context, merging visual description."""
        
        if not self._adapter:
            raise Exception("AI client not initialized. Please configure your API key or local AI server in settings.")
        
        # Get context from surrounding items (use get_all_storyboard_items to support both legacy and new structure)
        all_items = screenplay.get_all_storyboard_items()
        context_items = []
        for sb_item in all_items:
            if sb_item.sequence_number < item.sequence_number:
                context_items.append(f"Item {sb_item.sequence_number}: {sb_item.prompt[:100] if sb_item.prompt else 'No prompt'}...")
            elif sb_item.sequence_number > item.sequence_number:
                context_items.append(f"Item {sb_item.sequence_number}: {sb_item.prompt[:100] if sb_item.prompt else 'No prompt'}...")
                break
        
        context_text = "\n".join(context_items[-3:]) if context_items else "Beginning of story"
        
        # Use storyline if available, otherwise fall back to existing prompt
        storyline = item.storyline or ""
        existing_prompt = item.prompt or ""
        visual_desc = item.visual_description or ""
        
        # Get scene content for entity detection and identity block generation
        scene_content = None
        all_scenes = screenplay.get_all_scenes()
        for scene in all_scenes:
            for sb_item in scene.storyboard_items:
                if sb_item.item_id == item.item_id:
                    # Found the scene containing this item - get generated content
                    if scene.metadata and isinstance(scene.metadata, dict):
                        scene_content = scene.metadata.get("generated_content", "")
                    break
            if scene_content:
                break
        
        # Combine scene content with storyline for comprehensive context
        if scene_content and scene_content.strip():
            scene_text_for_entities = scene_content + " " + storyline
        else:
            scene_text_for_entities = storyline
        
        # ALWAYS use five-section structure for Higgsfield prompts
        try:
            # Extract sections using the storyline and item data - pass scene content
            sections = self._extract_prompt_sections(storyline or existing_prompt, item, screenplay, is_image=False, scene_content=scene_text_for_entities)
            
            # Refine Section D (action/motion) with AI if needed
            if storyline:
                # Use AI to refine the action description
                action_prompt = f"""Based on this storyline: "{storyline}"

Generate Section D (Action, Motion & Intent) for a Higgsfield video prompt:
- MUST explicitly describe ALL character actions using clear action verbs: walking, running, crouching, standing, sitting, jumping, reaching, grabbing, turning, looking, speaking, gesturing, moving, approaching, entering, leaving, etc.
- Describe actions clearly: "Character walks across the room", "Character runs toward the door", etc.
- Include spatial relationships
- Use realistic motion descriptions
- Include intent and motivation

Return ONLY the action description (Section D content), no labels."""
                
                try:
                    action_response = self._chat_completion(
                        model=self.model_settings["model"],
                        messages=[
                            {"role": "system", "content": "You are a script supervisor. Your job is to prevent variation, not encourage creativity."},
                            {"role": "user", "content": action_prompt}
                        ],
                        temperature=0.5,
                        max_tokens=200
                    )
                    refined_section_d = action_response.choices[0].message.content.strip().strip('"').strip("'")
                    if refined_section_d:
                        sections["section_d"] = f"{refined_section_d}, realistic motion, natural movement,"
                except:
                    # If AI refinement fails, use the default from _extract_prompt_sections
                    pass
            
            # Build the final prompt using five-section structure
            new_prompt = self._build_higgsfield_prompt(
                sections["section_a"],
                sections["section_b"],
                sections["section_c"],
                sections["section_d"],
                sections["section_e"]
            )
            
            # Ensure actions are explicitly described in the video prompt
            new_prompt = self._ensure_actions_described(new_prompt, item.dialogue)
            
            # Incorporate dialogue if present
            if item.dialogue and item.dialogue not in new_prompt:
                new_prompt = f"{new_prompt} Dialogue: {item.dialogue}".strip()
            
            return new_prompt
                
        except Exception as e:
            error_message = str(e)
            raise Exception(f"Failed to regenerate prompt: {error_message}")
    
    def regenerate_image_prompt(self, item: StoryboardItem, screenplay: Screenplay) -> str:
        """Regenerate the image prompt for a specific storyboard item using first-frame structure."""
        
        if not self._adapter:
            raise Exception("AI client not initialized. Please configure your API key or local AI server in settings.")
        
        # Use storyline if available, otherwise fall back to existing prompts
        storyline = item.storyline or ""
        existing_image_prompt = item.image_prompt or ""
        video_prompt = item.prompt or ""
        
        # Find the scene this item belongs to
        parent_scene = None
        scene_content = None
        all_scenes = screenplay.get_all_scenes()
        for scene in all_scenes:
            for sb_item in scene.storyboard_items:
                if sb_item.item_id == item.item_id:
                    parent_scene = scene
                    # Get generated content from scene metadata
                    if scene.metadata and isinstance(scene.metadata, dict):
                        scene_content = scene.metadata.get("generated_content", "")
                    break
            if parent_scene:
                break
        
        # Get or generate environment block from scene
        if parent_scene and hasattr(parent_scene, 'environment_block') and parent_scene.environment_block:
            environment_block = parent_scene.environment_block
        elif parent_scene:
            # Generate environment block if missing
            print(f"Generating environment block for scene {parent_scene.scene_number} during image prompt regeneration...")
            environment_block = self._generate_environment_block(parent_scene, scene_content or "", screenplay)
        else:
            # Fallback: create a basic environment block
            print("Warning: Could not find parent scene for item, using fallback environment block")
            environment_block = "a static establishing frame set in a cinematic location, grounded realistic environment, no motion"
        
        # Combine scene content with storyline for comprehensive entity detection
        if scene_content and scene_content.strip():
            scene_text_for_entities = scene_content + " " + storyline
        else:
            scene_text_for_entities = storyline
        
        # MANDATORY: Extract ALL characters named in scene (registry + scene-only)
        characters_named_in_scene = self._extract_all_characters_named_in_scene(
            scene_text_for_entities, screenplay
        )
        if not characters_named_in_scene and getattr(screenplay, "character_registry_frozen", False):
            characters_named_in_scene = self._extract_all_wizard_characters_from_scene(
                scene_text_for_entities, screenplay
            )
        
        # EXTRACTION RULES (identity blocks): Only explicitly marked entities.
        # FULL CAPS → Characters (above). UNDERLINED → Environments. [BRACKETS] → Objects. {BRACES} → Vehicles.
        # No inference: objects/vehicles only from markup; objects/vehicles require interaction.
        markup_objects = self._extract_objects_from_scene_markup(scene_text_for_entities, require_interaction=True)
        markup_vehicles = self._extract_vehicles_from_scene_markup(scene_text_for_entities, require_interaction=True)
        other_entities = [
            {"name": name, "type": "object", "description": ""} for name in markup_objects
        ] + [
            {"name": name, "type": "vehicle", "description": ""} for name in markup_vehicles
        ]
        
        # Get identity blocks for each entity
        identity_blocks = []
        
        # STEP 1: Get identity blocks for ALL characters named in scene
        for char_name in characters_named_in_scene:
            existing_block = screenplay.get_identity_block_by_name(char_name, "character")
            if existing_block:
                identity_blocks.append(existing_block)
            else:
                print(f"Warning: Identity block for {char_name} (character) not found, generating new one")
                new_block = self._generate_identity_block_from_scene(
                    char_name,
                    "character",
                    "",
                    scene_text_for_entities,
                    screenplay
                )
                identity_blocks.append(new_block)
        
        # STEP 2: Get identity blocks for other entities (vehicles, objects)
        for entity in other_entities:
            entity_type = (entity.get("type") or "").lower()
            entity_name = (entity.get("name") or "").strip()
            if not entity_name:
                continue
            existing_block = screenplay.get_identity_block_by_name(entity_name, entity_type)
            if existing_block:
                identity_blocks.append(existing_block)
            else:
                print(f"Warning: Identity block for {entity_name} ({entity_type}) not found, generating new one")
                new_block = self._generate_identity_block_from_scene(
                    entity_name,
                    entity_type,
                    entity.get("description", ""),
                    scene_text_for_entities,
                    screenplay
                )
                identity_blocks.append(new_block)
        
        # VALIDATION PASS (REQUIRED): Ensure ALL characters named in scene have identity blocks
        if characters_named_in_scene:
            passed, missing = self._validate_scene_character_identity_blocks(
                scene_text_for_entities, screenplay, identity_blocks
            )
            if not passed and missing:
                print(f"Validation FAILED: Missing identity blocks for: {missing}")
                # Generate identity blocks for missing characters (do NOT proceed with partial data)
                for char_name in missing:
                    print(f"  Generating missing identity block for: {char_name}")
                    existing_block = screenplay.get_identity_block_by_name(char_name, "character")
                    if existing_block:
                        identity_blocks.append(existing_block)
                    else:
                        new_block = self._generate_identity_block_from_scene(
                            char_name,
                            "character",
                            "",
                            scene_text_for_entities,
                            screenplay
                        )
                        identity_blocks.append(new_block)
                # Re-validate after adding missing blocks
                passed, still_missing = self._validate_scene_character_identity_blocks(
                    scene_text_for_entities, screenplay, identity_blocks
                )
                if not passed:
                    print(f"Warning: Still missing identity blocks after retry: {still_missing}")
            else:
                print(f"Validation PASSED: All {len(characters_named_in_scene)} characters have identity blocks")
        
        # Build first-frame image prompt using new six-section structure
        try:
            scene_id = parent_scene.scene_id if parent_scene else ""
            new_image_prompt = self._build_first_frame_image_prompt(
                environment_block=environment_block,
                entity_identity_blocks=identity_blocks,
                storyline=storyline,
                item=item,
                screenplay=screenplay,
                scene_id=scene_id
            )
            
            return new_image_prompt
                
        except Exception as e:
            error_message = str(e)
            print(f"Error generating first-frame image prompt: {error_message}")
            # Fallback to old method if new method fails
            pass
        
        # If storyline exists, use it as the primary context
        if storyline:
            story_context = f"Storyline: {storyline}"
        else:
            combined_context = f"{existing_image_prompt} {video_prompt} {visual_desc}".strip()
            story_context = f"Current Image Prompt: {existing_image_prompt if existing_image_prompt else 'None'}\nScene Context: {video_prompt[:200] if video_prompt else 'None'}...\nVisual Description: {visual_desc[:200] if visual_desc else 'None'}"
        
        atmosphere_text = f"\nAtmosphere/Tone: {screenplay.atmosphere}" if screenplay.atmosphere else ""
        
        prompt = f"""
You are a professional storyboard artist. Regenerate the establishing image prompt for this storyboard item:

{story_context}
Scene Type: {item.scene_type.value}
Duration: {item.duration} seconds
Dialogue: {item.dialogue if item.dialogue else "None"}{atmosphere_text}

Context (surrounding scenes):
{context_text}

{"CRITICAL: Use the STORYLINE above to understand what needs to be visualized. The image prompt should describe the FIRST FRAME/MOMENT from the storyline. " if storyline else ""}Create an image generation prompt (no length limit; be as detailed as needed) optimized specifically for higgsfield.ai that:
- CRITICAL: Describes ONLY the static establishing shot/first frame - a single moment frozen in time
- DO NOT describe action, movement, or story progression - only what is visible in the initial frame
- DO NOT use action verbs: avoid "walking", "running", "moving", "approaching", "entering", "turning", "speaking", "looking at"
- DO NOT use action phrases: avoid "begins to", "starts to", "as they walk", "while moving", "in the process of"
- USE static descriptions: "positioned", "standing", "sitting", "facing", "located", "arranged", "placed"
- Be detailed and specific - higgsfield.ai works best with rich, descriptive prompts
- Include: precise setting details, specific STATIC camera angle/perspective (low-angle, high-angle, eye-level, etc.), detailed lighting conditions (golden hour, harsh shadows, soft diffused light, etc.), environmental elements (weather, time of day, specific location), character appearance and EXACT positioning (where they are, how they're posed)
- Camera is STATIC - describe the angle but not camera movement
- MUST incorporate the atmosphere/tone from the screenplay context throughout
- Style: Highly detailed, photorealistic, cinematic quality, STATIC composition
- This image will be used as the starting frame for higgsfield.ai video generation
- Think of it as describing a detailed photograph or painting - a frozen moment, not a scene in motion

Return ONLY the prompt text, no additional formatting.
"""
        
        try:
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You are a professional storyboard artist specializing in creating image generation prompts optimized for higgsfield.ai. Create detailed, specific prompts (no length limit; be as detailed as needed) describing ONLY the static establishing image - a single frozen moment with precise setting details, camera angles, lighting conditions, and environmental elements. NO action, movement, or story progression. Be as detailed as needed for the prompt."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=max(self.model_settings.get("max_tokens", 150), 250)
            )
            
            # Validate response
            if not response or not response.choices or len(response.choices) == 0:
                raise Exception("AI returned empty response")
            
            content = response.choices[0].message.content
            if not content:
                raise Exception("AI returned empty content")
            
            new_prompt = content.strip()
            # Clean up any quotes or extra formatting
            new_prompt = new_prompt.strip('"').strip("'").strip()
            
            if not new_prompt:
                raise Exception("AI returned empty prompt after cleaning")
            
            # Use five-section structure for Higgsfield image prompts
            # Extract sections using the storyline and item data (is_image=True)
            sections = self._extract_prompt_sections(storyline if storyline else new_prompt, item, screenplay, is_image=True)
            
            # Refine Section D (static positioning) with AI if needed
            if storyline:
                # Use AI to refine the static description for image
                static_prompt = f"""Based on this storyline: "{storyline}"

Generate Section D (static positioning) for a Higgsfield IMAGE prompt:
- CRITICAL: Describes ONLY the static establishing shot/first frame - a single moment frozen in time
- DO NOT describe action, movement, or story progression - only what is visible in the initial frame
- DO NOT use action verbs: avoid "walking", "running", "moving", "approaching", "entering", "turning", "speaking", "looking at"
- USE static descriptions: "positioned", "standing", "sitting", "facing", "located", "arranged", "placed"
- Describe character appearance and EXACT positioning (where they are, how they're posed)
- Include precise setting details and camera angle

Return ONLY the static positioning description (Section D content), no labels."""
                
                try:
                    static_response = self._chat_completion(
                        model=self.model_settings["model"],
                        messages=[
                            {"role": "system", "content": "You are a script supervisor. Your job is to prevent variation, not encourage creativity."},
                            {"role": "user", "content": static_prompt}
                        ],
                        temperature=0.5,
                        max_tokens=200
                    )
                    refined_section_d = static_response.choices[0].message.content.strip().strip('"').strip("'")
                    if refined_section_d:
                        sections["section_d"] = f"{refined_section_d},"
                except:
                    # If AI refinement fails, use the default from _extract_prompt_sections
                    pass
            
            # Build the final prompt using five-section structure
            new_prompt = self._build_higgsfield_prompt(
                sections["section_a"],
                sections["section_b"],
                sections["section_c"],
                sections["section_d"],
                sections["section_e"]
            )
            
            # Clean the prompt to ensure it only describes a static image
            new_prompt = self._clean_image_prompt(new_prompt)
            
            if not new_prompt:
                raise Exception("AI returned empty prompt after cleaning for static image")
            
            return new_prompt.strip()
                
        except Exception as e:
            error_message = str(e)
            raise Exception(f"Failed to regenerate image prompt: {error_message}")
    
    def _get_app_usage_instructions(self) -> str:
        """Generate comprehensive step-by-step instructions for using the app."""
        # Import the comprehensive instructions from help_dialogs
        try:
            from ui.help_dialogs import get_comprehensive_instructions
            return get_comprehensive_instructions()
        except ImportError:
            # Fallback to basic instructions if import fails
            return """FRAMEFORGE - STEP-BY-STEP USAGE GUIDE

═══════════════════════════════════════════════════════════════════════════════

OVERVIEW
This application helps you create screenplays with AI assistance, from initial premise to detailed storyboards with image prompts.

═══════════════════════════════════════════════════════════════════════════════

GETTING STARTED

STEP 1: CREATE A NEW STORY
1. Click "File" → "New Story" or use the wizard
2. Choose either:
   - "New Story (Wizard)" - Guided creation with AI assistance
   - "New Story (Manual)" - Quick manual entry

═══════════════════════════════════════════════════════════════════════════════

STEP 2: STORY CREATION WIZARD (RECOMMENDED)

WIZARD STEP 1: PREMISE
1. Enter a story title (optional)
2. Either:
   - Manually enter your premise in the "Manual Entry" tab
   - Generate with AI in the "AI Generation" tab:
     a. Select genres (can choose multiple)
     b. Choose atmosphere/tone
     c. Click "Generate Premise"
     d. Review and edit the generated premise
3. Click "Next" when satisfied

WIZARD STEP 2: STORY OUTLINE
1. Click "Generate Story Outline" to create:
   - Main storyline
   - Subplots
   - Conclusion
   - Character profiles
2. Regenerate any section using the "Regenerate" buttons
3. Edit any text directly in the fields
4. Characters are automatically generated after the conclusion is finalized
5. Click "Next" when complete

WIZARD STEP 3: FRAMEWORK GENERATION
1. Click "Generate Framework" to create:
   - Story acts (Act 1, Act 2, Act 3)
   - Scenes within each act
   - Scene descriptions and metadata
2. Edit scene titles, descriptions, durations, and character focus
3. Add/Remove scenes as needed
4. Click "Finish" to complete the wizard

═══════════════════════════════════════════════════════════════════════════════

STEP 3: WORKING WITH SCENES

VIEWING SCENES
1. Scenes appear in the Storyboard Timeline (bottom panel)
2. Click a scene to select it
3. View scene details in the Scene Framework Editor (right panel)

EDITING SCENES
1. Select a scene in the timeline
2. Edit in the Scene Framework Editor:
   - Title
   - Description
   - Estimated duration
   - Character focus (which characters appear)
3. Changes save automatically

═══════════════════════════════════════════════════════════════════════════════

STEP 4: GENERATING STORYBOARDS

GENERATE STORYBOARD ITEMS
1. Select a scene in the timeline
2. Click "Generate Storyboard" button
3. The AI breaks the scene into storyboard items
4. Each item has:
   - Sequence number
   - Duration (seconds)
   - Image prompt (for video generation)
   - Description

EDITING STORYBOARD ITEMS
1. Click an item in the timeline to select it
2. Edit in the Storyboard Item Editor (right panel):
   - Duration
   - Image prompt
   - Description
3. Regenerate individual items using the "Regenerate" button

═══════════════════════════════════════════════════════════════════════════════

STEP 5: IDENTITY BLOCKS (CHARACTER/VEHICLE/OBJECT/ENVIRONMENT DESCRIPTIONS)

ACCESSING IDENTITY BLOCKS
1. Go to the "Identity Blocks" tab
2. View all entities (characters, vehicles, objects, environments)

CREATING IDENTITY BLOCKS
1. Select an entity from the list (or add a new one)
2. Enter User Notes - a brief description (e.g., "Male captain, 40s, worn uniform")
3. Click "Generate Identity Block"
4. Review the generated detailed description
5. Click "Approve" when satisfied

REFERENCE IMAGES
1. After approving an identity block, click "Generate Reference Image Prompt"
2. Copy the prompt to Higgsfield or other image generation tools
3. Use these prompts to create consistent visual references

═══════════════════════════════════════════════════════════════════════════════

STEP 6: AI CHAT ASSISTANT

USING THE CHAT
1. Open the AI Chat Panel (usually on the right side)
2. Type questions or requests about your story
3. The AI can:
   - Discuss story elements
   - Regenerate scenes
   - Edit scene content
   - Modify character outlines
   - Add/remove storyboard items
   - Change character focus in scenes

CHAT FEATURES
- Context-aware: Select a scene or storyboard items to give context
- Suggestions: The AI provides actionable suggestions with "Apply" and "Preview" buttons
- Preview Changes: Review changes before applying them

═══════════════════════════════════════════════════════════════════════════════

STEP 7: EXPORTING

EXPORT TO HIGGSFIELD
1. Click "File" → "Export" → "Export to Higgsfield"
2. Choose export options:
   - Include identity blocks
   - Include reference images
   - Scene selection
3. Save the exported file
4. Import into Higgsfield for video generation

═══════════════════════════════════════════════════════════════════════════════

TIPS AND BEST PRACTICES

STORY DEVELOPMENT
- Start with a strong premise - it guides everything else
- Let the AI generate initial content, then refine it
- Use the chat assistant for iterative improvements
- Regenerate sections that don't fit your vision

CHARACTER DEVELOPMENT
- Create identity blocks early for main characters
- Use detailed user notes for better AI generation
- Review and approve identity blocks before generating scenes
- Update character outlines as your story evolves

SCENE MANAGEMENT
- Set appropriate durations (typically 30-120 seconds per scene)
- Specify character focus to help with image generation
- Generate storyboards after scene content is finalized
- Edit storyboard items to fine-tune image prompts

AI CHAT
- Be specific in your requests
- Select relevant scenes/items for context
- Use "Preview" before applying major changes
- Ask for step-by-step instructions anytime

═══════════════════════════════════════════════════════════════════════════════

KEYBOARD SHORTCUTS
- Ctrl+Enter in chat: Send message
- Ctrl+N: New story
- Ctrl+O: Open story
- Ctrl+S: Save story

═══════════════════════════════════════════════════════════════════════════════

GETTING HELP
- Ask the AI chat: "How do I use this app?" or "Give me instructions"
- Check the Settings dialog for AI configuration
- Review scene/item descriptions for context

═══════════════════════════════════════════════════════════════════════════════

WORKFLOW EXAMPLE
1. Create new story with wizard
2. Generate premise (AI or manual)
3. Generate story outline
4. Generate framework (acts and scenes)
5. Generate storyboards for each scene
6. Create identity blocks for main characters
7. Refine using AI chat and manual edits
8. Export to Higgsfield for video generation

═══════════════════════════════════════════════════════════════════════════════

Remember: You can always ask me (the AI assistant) for help with any step or feature!"""
    
    def chat_about_story(self, user_message: str, context: dict) -> dict:
        """Handle chat about story and determine what changes to make."""
        
        # Detect if user is asking for app usage instructions FIRST (before client check)
        # This allows instruction requests to work even when AI client isn't initialized
        user_lower = user_message.lower()
        instruction_keywords = [
            "how to use", "how do i use", "instructions", "instruction", "tutorial", "guide", 
            "help me use", "show me how", "explain how", "walk me through", "step by step",
            "how does this work", "how does it work", "what can i do", "what does this do",
            "usage", "user guide", "getting started", "how to get started", "how to start",
            "tell me about", "explain the app", "app instructions", "app guide", "app tutorial"
        ]
        
        is_instruction_request = any(keyword in user_lower for keyword in instruction_keywords)
        
        if is_instruction_request:
            # Return comprehensive app usage instructions (no AI client needed)
            instructions = self._get_app_usage_instructions()
            return {
                "text": instructions,
                "intent": "discuss",
                "suggestions": []
            }
        
        # For all other requests, AI client is required
        if not self._adapter:
            raise Exception("AI client not initialized. Please configure your API key or local AI server in settings.")
        
        screenplay = context.get("screenplay")
        current_scene = context.get("current_scene")
        selected_items = context.get("selected_items", [])
        chat_history = context.get("chat_history", [])
        
        # Detect if user mentioned a specific character name
        mentioned_character = None
        if screenplay and screenplay.story_outline:
            characters = screenplay.story_outline.get("characters", [])
            if characters and isinstance(characters, list):
                # Extract character names
                character_names = []
                for char in characters:
                    if isinstance(char, dict):
                        char_name = char.get("name", "").strip()
                        if char_name:
                            character_names.append(char_name)
                
                # Check if user message contains any character name
                user_lower = user_message.lower()
                for char_name in character_names:
                    if char_name.lower() in user_lower:
                        mentioned_character = char_name
                        break
        
        # Build context description (include mentioned character if detected)
        context_description = self._build_chat_context(screenplay, current_scene, selected_items, mentioned_character)
        
        # Build chat history for context
        history_text = ""
        if chat_history:
            history_parts = []
            for msg in chat_history[-5:]:  # Last 5 messages
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if content:
                    history_parts.append(f"{role.capitalize()}: {content}")
            history_text = "\n".join(history_parts)
        
        # Detect if this is a character outline request (vs scene content request)
        user_lower = user_message.lower()
        is_character_outline_request = any(keyword in user_lower for keyword in [
            "character outline", "character's outline", "character outline", "extend outline", 
            "expand outline", "modify outline", "change outline", "update outline",
            "character backstory", "character background", "character description",
            "growth arc", "character arc", "character development"
        ])
        
        # Check if user mentioned a character name and is asking about outline
        if mentioned_character and is_character_outline_request:
            is_character_outline_request = True
        
        # Detect if this is specifically an "extend" or "expand" request
        is_extend_request = any(keyword in user_lower for keyword in [
            "extend", "expand", "add to", "develop", "elaborate", "enhance", "build on"
        ])
        
        prompt = f"""You are an AI assistant helping a screenwriter develop their story. The user wants to discuss and potentially modify their screenplay.

{context_description}

Recent conversation:
{history_text if history_text else "No previous conversation."}

User message: {user_message}

IMPORTANT CONTEXT:
- "Character outlines" refer to character descriptions stored in the story_outline (background, role, personality, etc.)
- "Character focus" refers to which characters appear in a specific scene
- "Scene content" refers to the actual narrative text describing what happens in a scene

Analyze the user's message and determine:
1. What is the user asking for? (discussion, regenerate content, edit content, add items, remove items, edit character outline, etc.)
2. What context are they referring to? (current scene, selected storyboard items, character outlines, or general story)
3. What changes should be made (if any)?

{"⚠️ CRITICAL: The user is asking about CHARACTER OUTLINES (character descriptions/backstories), NOT scene content. Focus on the character's outline, growth arc, and background information from the story_outline, NOT scene narrative content." if is_character_outline_request else ""}
{"🚨 EXTEND REQUEST DETECTED: The user wants to EXTEND/EXPAND the character outline. You MUST include the EXISTING outline text in your response and ADD new content. The extended version must be LONGER than the original. Do NOT replace or shorten it." if (is_character_outline_request and is_extend_request) else ""}

Respond in JSON format with this structure:
{{
    "text": "Your conversational response to the user",
    "intent": "discuss|regenerate_scene|edit_scene|regenerate_items|edit_items|add_items|remove_items|edit_character_outline",
    "suggestions": [
        {{
            "change_type": "edit_character_outline" if is_character_outline_request and mentioned_character else "regenerate_scene|edit_scene|regenerate_items|edit_items|add_items|remove_items",
            "description": "Brief description of the suggested change",
            "change_data": {{
                "character_name": "CharacterName",  // For edit_character_outline: name of character to edit
                "character_outline": "...",  // For edit_character_outline: new or extended character outline text
                "character_growth_arc": "...",  // For edit_character_outline: new or extended growth arc text (optional)
                "new_content": "...",  // For regenerate_scene
                "edits": {{
                    "description": "...",  // For edit_scene: scene description
                    "title": "...",  // For edit_scene: scene title
                    "estimated_duration": 60,  // For edit_scene: duration in seconds
                    "character_focus": ["Character1", "Character2"]  // For edit_scene: list of character names OR comma-separated string
                }},  // For edit_scene or edit_items
                "new_items": [...],  // For regenerate_items or add_items
                "items_to_remove": [...]  // For remove_items
            }}
        }}
    ]
}}

For edit_character_outline: Use this when the user wants to modify a character's outline, backstory, or growth arc from the story_outline.
- character_name: The name of the character to edit (must match exactly)
- character_outline: The EXTENDED character outline text - MUST include the existing outline PLUS new content. If the user asks to "extend", "expand", or "add to" the outline, you MUST keep the original text and add more detail. The result should be LONGER than the original, not shorter.
- character_growth_arc: Optional - the EXTENDED growth arc text - CRITICAL: If the user asks to extend a character, you MUST also extend the growth arc. Include the COMPLETE existing growth arc text PLUS new content. The extended growth arc MUST be LONGER than the original. Do NOT shorten or replace the growth arc - only extend it.

CRITICAL: When the user asks to "extend", "expand", "add to", or "develop" a character outline:
1. You MUST include the existing outline text in your response
2. You MUST add new content that builds upon the existing outline
3. The final outline MUST be longer than the original
4. Do NOT replace the existing outline - extend it with additional details, background, personality traits, relationships, motivations, etc.
5. If you provide character_growth_arc, you MUST include the COMPLETE existing growth arc text PLUS new content
6. The extended growth arc MUST be LONGER than the original - do NOT shorten it
7. If you're not extending the growth arc, do NOT include character_growth_arc in the response (leave it out entirely)

For edit_scene: The "edits" object can contain any of these properties: description, title, estimated_duration, or character_focus. 
- character_focus should be a list of character names (e.g., ["John", "Sarah"]) or a comma-separated string (e.g., "John, Sarah")
- If the user wants to change which characters are featured in the scene, use edit_scene with character_focus in edits

IMPORTANT: If the user mentions a specific character by name and asks about their "outline", "backstory", "background", "description", or "growth arc", you MUST use edit_character_outline, NOT edit_scene or regenerate_scene.
- Character outlines are stored separately from scene content
- When editing character outlines, focus on the character's role, background, personality, and growth arc
- Do NOT suggest editing scene content when the user asks about character outlines

CRITICAL FOR EXTENDING CHARACTER OUTLINES:
- If the user asks to "extend", "expand", "add to", "develop", or "elaborate on" a character outline:
  1. You MUST include the COMPLETE EXISTING outline text word-for-word in your character_outline response
  2. You MUST add NEW content that builds upon what's already there - add more sentences, details, depth
  3. The extended outline MUST be LONGER than the original (check the character count shown in context)
  4. Add details like: deeper background, more personality traits, specific motivations, relationships, past experiences, fears, desires, goals, conflicts, etc.
  5. Do NOT summarize, shorten, or paraphrase the existing outline - keep it EXACTLY as is and ADD to it
  6. The format MUST be: [Complete original outline text] [Additional new sentences that expand and develop the character further]
  7. Example: If original is "Sarah is a detective. She is determined." Extended should be "Sarah is a detective. She is determined. [ADD MORE: Her determination stems from... She has a troubled past involving... Her relationships with... etc.]"
  8. The extended version should be at least 1.5x longer than the original, preferably 2x longer

CRITICAL FOR GROWTH ARC WHEN EXTENDING:
- If you provide character_growth_arc when extending a character:
  1. You MUST include the COMPLETE EXISTING growth arc text word-for-word
  2. You MUST add NEW content that expands the growth arc
  3. The extended growth arc MUST be LONGER than the original - check the character count in context
  4. Do NOT shorten, summarize, or replace the growth arc - only extend it
  5. If you cannot extend the growth arc properly, do NOT include character_growth_arc in your response
  6. The format MUST be: [Complete original growth arc text] [Additional new sentences that expand the character's development]
  7. The extended growth arc should be at least 1.5x longer than the original
  8. Example: If original growth arc is "Sarah starts as a rookie. She becomes experienced." Extended should be "Sarah starts as a rookie. She becomes experienced. [ADD MORE: Her journey involves... She faces challenges such as... Her transformation includes... etc.]"

If the user is just discussing or asking questions without requesting changes, set "suggestions" to an empty array.
If the user wants changes, include appropriate suggestions with the change_data needed to implement them.

CRITICAL: Return ONLY valid JSON. No markdown, no explanations, no code blocks.
"""
        
        try:
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You are a helpful AI assistant for screenwriters. Analyze user requests and provide structured responses in JSON format."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=max(self.model_settings.get("max_tokens", 500), 1000)
            )
            
            content = response.choices[0].message.content.strip()
            
            # Try to extract JSON from response - handle cases where there's extra text
            # First, try to find and extract just the JSON object
            chat_response = None
            try:
                # Strategy: Find the first { and then find the matching closing }
                # This handles cases where there's text before/after the JSON
                json_start = content.find('{')
                if json_start >= 0:
                    # Find the matching closing brace
                    brace_count = 0
                    in_string = False
                    escape_next = False
                    json_end = -1
                    
                    for i in range(json_start, len(content)):
                        char = content[i]
                        if escape_next:
                            escape_next = False
                            continue
                        if char == '\\':
                            escape_next = True
                            continue
                        if char == '"' and not escape_next:
                            in_string = not in_string
                            continue
                        if not in_string:
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    json_end = i + 1
                                    break
                    
                    if json_end > json_start:
                        # Extract just the JSON portion
                        json_content = content[json_start:json_end]
                        # Try parsing it directly first
                        try:
                            chat_response = json.loads(json_content)
                        except json.JSONDecodeError as parse_err:
                            # If direct parse fails, try to repair common issues
                            # Fix malformed array endings (") should be "])
                            repaired = self._repair_json(json_content)
                            try:
                                chat_response = json.loads(repaired)
                            except json.JSONDecodeError:
                                # If repair fails, use the full extraction method
                                chat_response = self._extract_and_parse_json(json_content)
            
            except Exception:
                # Fall back to original method
                pass
            
            if chat_response is None:
                # Extract JSON from response using full extraction method
                try:
                    chat_response = self._extract_and_parse_json(content)
                except Exception as e:
                    # If extraction fails, try one more time with improved extraction
                    # Look for common patterns like "Here's my response in JSON format:" or similar
                    import re
                    # Try to find JSON after common prefixes
                    patterns = [
                        r'(?:Here\'?s? (?:my |the )?response (?:in |as )?JSON format:?\s*)(\{.*\})',
                        r'(?:JSON (?:response|format):?\s*)(\{.*\})',
                        r'(?:Response:?\s*)(\{.*\})',
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
                        if match:
                            json_str = match.group(1) if match.groups() else match.group(0)
                            # Try to find the complete JSON object by balancing braces
                            brace_count = 0
                            in_string = False
                            escape_next = False
                            json_start = json_str.find('{')
                            if json_start >= 0:
                                json_end = -1
                                
                                for i in range(json_start, len(json_str)):
                                    char = json_str[i]
                                    if escape_next:
                                        escape_next = False
                                        continue
                                    if char == '\\':
                                        escape_next = True
                                        continue
                                    if char == '"' and not escape_next:
                                        in_string = not in_string
                                        continue
                                    if not in_string:
                                        if char == '{':
                                            brace_count += 1
                                        elif char == '}':
                                            brace_count -= 1
                                            if brace_count == 0:
                                                json_end = i + 1
                                                break
                                
                                if json_end > json_start:
                                    json_content = json_str[json_start:json_end]
                                    try:
                                        # Try to repair common JSON issues
                                        repaired = self._repair_json(json_content)
                                        chat_response = json.loads(repaired)
                                        break
                                    except json.JSONDecodeError:
                                        continue
                    
                    # If still None, raise the original error
                    if chat_response is None:
                        # Save full response for debugging
                        import os
                        debug_file = "debug_json_error.json"
                        try:
                            with open(debug_file, 'w', encoding='utf-8') as f:
                                f.write(content)
                        except:
                            pass
                        error_msg = f"Failed to extract JSON from AI response: {str(e)}"
                        if content:
                            error_msg += f"\n\nResponse preview (first 500 chars):\n{content[:500]}..."
                            if len(content) > 500:
                                error_msg += f"\n\n(Response is {len(content)} characters long)"
                        if os.path.exists(debug_file):
                            error_msg += f"\n\nFull response saved to: {debug_file}"
                        raise Exception(error_msg)
            
            # Validate response structure
            if not isinstance(chat_response, dict):
                # Save for debugging
                import os
                debug_file = "debug_json_error.json"
                try:
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                        f.write("\n\n=== Extracted (but invalid) ===\n")
                        f.write(str(chat_response))
                except:
                    pass
                raise Exception(f"Invalid response format from AI. Expected dict, got {type(chat_response)}")
            
            # Ensure required fields
            if "text" not in chat_response:
                chat_response["text"] = "I understand your request."
            if "suggestions" not in chat_response:
                chat_response["suggestions"] = []
            
            # Post-process suggestions to detect paragraph-related requests and add paragraph_index
            user_lower = user_message.lower()
            is_paragraph_related = any(keyword in user_lower for keyword in [
                "paragraph", "paragragh", "first", "second", "third", "fourth", "fifth",
                "option", "options", "alternative", "alternatives", "version", "versions"
            ])
            
            if is_paragraph_related and current_scene and "regenerate_scene" in [s.get("change_type") for s in chat_response["suggestions"]]:
                # Try to extract paragraph index from user message
                import re
                paragraph_index = None
                paragraph_number_match = re.search(r'\[(\d+)\]|paragraph\s+(\d+)|paragragh\s+(\d+)', user_lower)
                if paragraph_number_match:
                    para_num = int(paragraph_number_match.group(1) or paragraph_number_match.group(2) or paragraph_number_match.group(3))
                    paragraph_index = para_num - 1  # Convert to 0-based index
                elif "second" in user_lower or "paragraph 2" in user_lower or "2nd" in user_lower:
                    paragraph_index = 1
                elif "third" in user_lower or "paragraph 3" in user_lower or "3rd" in user_lower:
                    paragraph_index = 2
                elif "fourth" in user_lower or "paragraph 4" in user_lower or "4th" in user_lower:
                    paragraph_index = 3
                elif "fifth" in user_lower or "paragraph 5" in user_lower or "5th" in user_lower:
                    paragraph_index = 4
                elif "first" in user_lower or "paragraph 1" in user_lower or "1st" in user_lower:
                    paragraph_index = 0
                
                # Add paragraph_index to suggestions with regenerate_scene change_type
                for suggestion in chat_response["suggestions"]:
                    if suggestion.get("change_type") == "regenerate_scene":
                        if "change_data" not in suggestion:
                            suggestion["change_data"] = {}
                        if paragraph_index is not None:
                            suggestion["change_data"]["paragraph_index"] = paragraph_index
                        # Always include user_request for context
                        if "user_request" not in suggestion["change_data"]:
                            suggestion["change_data"]["user_request"] = user_message
            
            # Post-process character outline suggestions to ensure character_name is set
            for suggestion in chat_response.get("suggestions", []):
                if suggestion.get("change_type") == "edit_character_outline":
                    change_data = suggestion.get("change_data", {})
                    if not change_data.get("character_name") and mentioned_character:
                        # Set character_name from mentioned_character if missing
                        change_data["character_name"] = mentioned_character
                        print(f"DEBUG: Set character_name to {mentioned_character} from mentioned_character")
                    elif not change_data.get("character_name"):
                        # Try to extract from user message
                        import re
                        # Look for capitalized words that might be character names
                        words = re.findall(r'\b([A-Z][a-z]+)\b', user_message)
                        if words and self.screenplay and self.screenplay.story_outline:
                            characters = self.screenplay.story_outline.get("characters", [])
                            char_names = [char.get("name", "") for char in characters if isinstance(char, dict)]
                            for word in words:
                                if word in char_names:
                                    change_data["character_name"] = word
                                    print(f"DEBUG: Extracted character_name {word} from user message")
                                    break
            
            return chat_response
                
        except Exception as e:
            error_message = str(e)
            raise Exception(f"Failed to process chat request: {error_message}")
    
    def _get_previous_scenes(self, screenplay: Screenplay, current_scene: StoryScene, max_scenes: Optional[int] = 50) -> List[StoryScene]:
        """Get previous scenes from the screenplay for continuity context.
        
        Returns ALL previous scenes by default (max_scenes=50) so consistency digests
        can be used for precise continuity. Use consistency_digest when available (token-efficient).
        """
        if not screenplay or not screenplay.acts:
            return []
        
        all_scenes = screenplay.get_all_scenes()
        current_index = -1
        
        for i, s in enumerate(all_scenes):
            if s.scene_id == current_scene.scene_id:
                current_index = i
                break
        
        if current_index <= 0:
            return []
        
        start_index = max(0, current_index - (max_scenes or 50))
        return all_scenes[start_index:current_index]
    
    def _extract_consistency_digest(self, scene_content: str, scene_title: str,
                                     screenplay: "Screenplay | None" = None) -> str:
        """Extract key continuity facts from scene content for consistency across the story.
        
        Uses LLM to produce a compact 80-120 word digest capturing: character locations/vehicles,
        objects used, revelations, state changes. Stored in scene.metadata for use in later prompts.
        """
        if not self._adapter or not scene_content or not scene_content.strip():
            return ""

        # Build canonical character list so the LLM uses exact names
        char_names_section = ""
        if screenplay:
            registry = getattr(screenplay, "character_registry", []) or []
            outline = getattr(screenplay, "story_outline", {}) or {}
            chars = outline.get("characters", []) if isinstance(outline, dict) else []
            names = list(dict.fromkeys(
                [n.strip() for n in registry if isinstance(n, str) and n.strip()]
            ))
            # Build brief relationship context from premise/storyline
            relationships = []
            premise = getattr(screenplay, "premise", "") or ""
            storyline = ""
            if isinstance(outline, dict):
                storyline = outline.get("main_storyline", "") or ""
            for ch in chars:
                if not isinstance(ch, dict):
                    continue
                cname = ch.get("name", "").strip()
                if not cname:
                    continue
                crole = ch.get("role", "")
                for text_block in (premise, storyline):
                    if not text_block:
                        continue
                    import re
                    for m in re.finditer(
                        re.escape(cname) + r'[,]?\s+(his|her|their)\s+(\w+)',
                        text_block, re.IGNORECASE
                    ):
                        relationships.append(f"{cname}: {m.group(2)}")
                    for m in re.finditer(
                        r'(?:wife|husband|sister|brother|mother|father|daughter|son|partner)\s+'
                        + re.escape(cname),
                        text_block, re.IGNORECASE
                    ):
                        relationships.append(m.group(0))

            if names:
                char_names_section = (
                    f"\nCANONICAL CHARACTER NAMES (use EXACTLY — never merge, abbreviate, or combine):\n"
                    f"{', '.join(names)}\n"
                    f"Each name above is a SEPARATE character. ADRIAN VAUGHN and LENA VAUGHN are TWO different people.\n"
                )
            if relationships:
                char_names_section += f"Relationships: {'; '.join(dict.fromkeys(relationships))}\n"

        try:
            prompt = f"""Extract ONLY the key continuity facts from this scene. Output 80-120 words max.

Scene: {scene_title}
{char_names_section}
Content:
{scene_content[:3000]}

Extract and list:
- Key events (1-2 sentences: what happened, what was revealed)
- Character locations: who was where, in what vehicle (use {{braces}} for vehicles, _underscores_ for locations)
- Objects used (use [brackets] for significant objects)
- Revelations: what characters learned or discovered
- State changes: damage, captures, changes to places, who has what

CRITICAL: Use the EXACT character names from the CANONICAL list above. NEVER merge two character names into one (e.g. never write "ADRIAN LENA VAUGHN"). Each character is a separate person — refer to them individually.
Use the same markup: Characters in FULL CAPS, locations _underlined_, objects [brackets], vehicles {{braces}}.
Output ONLY the digest. No preamble."""

            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You extract key continuity facts from scene text. Output a compact 80-120 word digest. Preserve entity markup (FULL CAPS, _underlined_, [brackets], {braces}). NEVER merge character names — each character must be named individually using their exact canonical name."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=300
            )
            digest = (response.choices[0].message.content or "").strip()
            digest = digest.strip('"\'')
            return digest[:500] if digest else ""
        except Exception as e:
            print(f"Could not extract consistency digest: {e}")
            return ""
    
    def _build_previous_scenes_context(self, previous_scenes: List[StoryScene]) -> str:
        """Build context string from previous scenes using consistency digests when available.
        
        Prefers LLM-extracted consistency_digest (compact, continuity-focused). Falls back to
        truncated full content for scenes without a digest (e.g. from before this feature).
        Includes character wardrobe data from previous scenes for visual continuity.
        """
        if not previous_scenes:
            return ""
        
        context_parts = ["\nPrevious Scenes (key continuity facts — must not contradict):"]
        for prev_scene in previous_scenes:
            digest = ""
            if prev_scene.metadata and prev_scene.metadata.get("consistency_digest"):
                digest = prev_scene.metadata["consistency_digest"]
            elif prev_scene.metadata and prev_scene.metadata.get("generated_content"):
                digest = prev_scene.metadata["generated_content"][:400] + "..."
            elif prev_scene.description:
                digest = prev_scene.description[:400] + "..."
            
            if digest:
                context_parts.append(f"\nScene {prev_scene.scene_number} - {prev_scene.title}:")
                context_parts.append(digest)
            
            # Include character wardrobe from previous scenes
            if hasattr(prev_scene, 'character_wardrobe') and prev_scene.character_wardrobe:
                wardrobe_lines = []
                for entity_id, wardrobe_desc in prev_scene.character_wardrobe.items():
                    if wardrobe_desc and isinstance(wardrobe_desc, str):
                        wardrobe_lines.append(f"  - {entity_id}: {wardrobe_desc}")
                if wardrobe_lines:
                    context_parts.append(f"  Character Wardrobe (Scene {prev_scene.scene_number}):")
                    context_parts.extend(wardrobe_lines)
        
        return "\n".join(context_parts)
    
    def _build_chat_context(self, screenplay: Optional[Screenplay], scene: Optional[StoryScene], items: List[StoryboardItem], mentioned_character: Optional[str] = None) -> str:
        """Build a context description for chat.
        
        Args:
            screenplay: The screenplay object
            scene: Current scene (if any)
            items: Selected storyboard items (if any)
            mentioned_character: Name of a specific character mentioned by the user (if any)
        """
        context_parts = []
        
        if screenplay:
            context_parts.append(f"Story: {screenplay.title}")
            if screenplay.premise:
                context_parts.append(f"Premise: {screenplay.premise[:200]}...")
            if screenplay.genre:
                context_parts.append(f"Genres: {', '.join(screenplay.genre)}")
            if screenplay.atmosphere:
                context_parts.append(f"Atmosphere: {screenplay.atmosphere}")
            
            # Add character information from story_outline
            if screenplay.story_outline and isinstance(screenplay.story_outline, dict):
                characters = screenplay.story_outline.get("characters", [])
                if characters and isinstance(characters, list):
                    # If a specific character was mentioned, include their details prominently
                    if mentioned_character:
                        # Find the mentioned character
                        for char in characters:
                            if isinstance(char, dict):
                                char_name = char.get("name", "").strip()
                                if char_name and char_name.lower() == mentioned_character.lower():
                                    context_parts.append(f"\n⚠️ FOCUS CHARACTER: {char_name}")
                                    char_outline = char.get("outline", "")
                                    if char_outline:
                                        outline_length = len(char_outline)
                                        context_parts.append(f"CURRENT Character Outline ({outline_length} characters):")
                                        context_parts.append(f"{char_outline}")
                                        context_parts.append(f"⚠️ CRITICAL: If the user asks to 'extend', 'expand', or 'add to' this outline, you MUST:")
                                        context_parts.append(f"  1. Include the ENTIRE existing outline text above")
                                        context_parts.append(f"  2. Add NEW content that expands on it")
                                        context_parts.append(f"  3. Make the extended version LONGER than {outline_length} characters")
                                        context_parts.append(f"  4. Do NOT summarize or shorten - only ADD more detail")
                                    else:
                                        context_parts.append(f"Character Outline: (none - create new)")
                                    char_growth = char.get("growth_arc", "")
                                    if char_growth:
                                        growth_length = len(char_growth)
                                        context_parts.append(f"CURRENT Character Growth Arc ({growth_length} characters):")
                                        context_parts.append(f"{char_growth}")
                                        context_parts.append(f"⚠️ CRITICAL: If extending, keep the existing text and ADD to it.")
                                    else:
                                        context_parts.append(f"Character Growth Arc: (none)")
                                    break
                    
                    # Also include all characters for reference
                    context_parts.append(f"\nAll Characters in Story:")
                    for char in characters:
                        if isinstance(char, dict):
                            char_name = char.get("name", "Unnamed Character")
                            char_outline = char.get("outline", "")
                            if char_outline:
                                context_parts.append(f"  - {char_name}: {char_outline[:150]}...")
                            else:
                                context_parts.append(f"  - {char_name}: (no outline)")
        
        # Add previous scenes for continuity
        if screenplay and scene:
            previous_scenes = self._get_previous_scenes(screenplay, scene)
            if previous_scenes:
                context_parts.append(self._build_previous_scenes_context(previous_scenes))
        
        if scene:
            context_parts.append(f"\nCurrent Scene: {scene.title}")
            context_parts.append(f"Scene Description: {scene.description[:200]}...")
            if scene.metadata and scene.metadata.get("generated_content"):
                content = scene.metadata["generated_content"][:300]
                context_parts.append(f"Scene Content: {content}...")
            context_parts.append(f"Estimated Duration: {scene.estimated_duration} seconds")
            context_parts.append(f"Storyboard Items: {len(scene.storyboard_items)}")
            # Add character focus information
            if scene.character_focus:
                context_parts.append(f"Character Focus: {', '.join(scene.character_focus)}")
            else:
                context_parts.append(f"Character Focus: (none)")
        
        if items:
            context_parts.append(f"\nSelected Storyboard Items: {len(items)}")
            for item in items[:3]:  # First 3 items
                context_parts.append(f"  - Item {item.sequence_number}: {item.storyline[:100] if item.storyline else item.prompt[:100]}...")
        
        return "\n".join(context_parts) if context_parts else "No context available."
    
    def regenerate_scene_content(self, scene: StoryScene, user_request: str, screenplay: Screenplay) -> str:
        """Regenerate scene content based on chat discussion."""
        if not self._adapter:
            raise Exception("AI client not initialized.")
        
        # Get existing content (remove paragraph numbers if present for processing)
        existing_content = ""
        if scene.metadata and scene.metadata.get("generated_content"):
            existing_content = scene.metadata["generated_content"]
        else:
            existing_content = scene.description
        
        # Remove paragraph numbers from existing content for processing
        # Numbers are added for display but shouldn't affect AI processing
        import re
        existing_content = re.sub(r'^\[\d+\]\s+', '', existing_content, flags=re.MULTILINE)
        
        # Get previous scenes for continuity
        previous_scenes = self._get_previous_scenes(screenplay, scene)
        previous_scenes_context = self._build_previous_scenes_context(previous_scenes) if previous_scenes else ""
        
        # Check if user wants to edit a specific paragraph
        user_lower = user_request.lower()
        is_paragraph_edit = any(keyword in user_lower for keyword in ["first paragraph", "second paragraph", "third paragraph", 
                                                                      "paragraph 1", "paragraph 2", "paragraph 3",
                                                                      "change paragraph", "edit paragraph", "modify paragraph",
                                                                      "extend paragraph", "expand paragraph", "add to paragraph"])
        
        if is_paragraph_edit:
            # Split content into paragraphs (remove paragraph numbers if present)
            # Paragraph numbers are in format [1], [2], etc.
            import re
            content_without_numbers = re.sub(r'^\[\d+\]\s+', '', existing_content, flags=re.MULTILINE)
            paragraphs = [p.strip() for p in content_without_numbers.split('\n\n') if p.strip()]
            if not paragraphs:
                paragraphs = [content_without_numbers]
            
            # Determine which paragraph to edit by looking for paragraph numbers in the request
            paragraph_index = None  # Start with None, don't default to 0
            # Look for explicit paragraph numbers like [1], [2], paragraph 1, etc. FIRST (most specific)
            paragraph_number_match = re.search(r'\[(\d+)\]|paragraph\s+(\d+)|paragragh\s+(\d+)', user_lower)
            if paragraph_number_match:
                # Extract the number
                para_num = int(paragraph_number_match.group(1) or paragraph_number_match.group(2) or paragraph_number_match.group(3))
                paragraph_index = para_num - 1  # Convert to 0-based index
            # Check for explicit word-based references
            elif "first" in user_lower or "paragraph 1" in user_lower or "1st" in user_lower:
                paragraph_index = 0
            elif "second" in user_lower or "paragraph 2" in user_lower or "2nd" in user_lower:
                paragraph_index = 1
            elif "third" in user_lower or "paragraph 3" in user_lower or "3rd" in user_lower:
                paragraph_index = 2
            elif "fourth" in user_lower or "paragraph 4" in user_lower or "4th" in user_lower:
                paragraph_index = 3
            elif "fifth" in user_lower or "paragraph 5" in user_lower or "5th" in user_lower:
                paragraph_index = 4
            
            # If still not found, default to 0 but this should be rare
            if paragraph_index is None:
                paragraph_index = 0
            
            if paragraph_index < 0:
                paragraph_index = 0
            if paragraph_index >= len(paragraphs):
                paragraph_index = len(paragraphs) - 1
            
            # Check if this is an extend/expand request
            is_extend = "extend" in user_lower or "expand" in user_lower or "add to" in user_lower
            
            # Build prompt for editing specific paragraph
            if is_extend:
                extend_instruction = f"""The user wants to EXTEND or EXPAND paragraph {paragraph_index + 1}. This means you should:
- Keep the existing content of paragraph {paragraph_index + 1} exactly as it is
- Add new content to the paragraph to make it longer and more detailed
- The new content should flow naturally from the existing content
- Do not remove or change any of the existing text in paragraph {paragraph_index + 1}
- Simply add more detail, description, or content to extend it"""
            else:
                extend_instruction = f"""The user wants to EDIT paragraph {paragraph_index + 1}. You can modify, change, or rewrite it based on their request."""
            
            # Build paragraph list for reference with clear numbering
            paragraph_list = "\n\n".join([f"[{i+1}] {para}" for i, para in enumerate(paragraphs)])
            
            prompt = f"""You are editing ONLY paragraph [{paragraph_index + 1}] of a scene. You MUST return the COMPLETE scene content with ALL paragraphs.

{previous_scenes_context}

Scene: {scene.title}

CURRENT FULL SCENE CONTENT (ALL {len(paragraphs)} PARAGRAPHS - NOTE THE NUMBERING):
{paragraph_list}

User Request: {user_request}

IMPORTANT: The user is asking to edit paragraph [{paragraph_index + 1}]. This is the paragraph marked with [{paragraph_index + 1}] above.

{extend_instruction}

CRITICAL CONTINUITY INSTRUCTIONS:
- Maintain consistency with previous scenes. If a character was in a specific location, vehicle, or situation in previous scenes, preserve that continuity.
- Do not introduce contradictions (e.g., if John was on a motorbike in the previous scene, don't suddenly put him in a car unless the user explicitly requests it).
- Reference the previous scenes above to understand the story state and maintain logical progression.
- ENTITY DESCRIPTION RULE: Once an entity (character, location, vehicle, object) has been fully described in a previous scene, do NOT repeat that description in later scenes. Reference the entity by name/markup only unless the story has changed them (e.g. damage, new state).
  EXCEPTION — CHARACTER WARDROBE: Character clothing/wardrobe MUST be described on each character's first appearance in EVERY scene. If unchanged, a brief reference suffices (e.g. "still wearing his olive vest"). If changed, describe fully.

OWNERSHIP RULE (STRICT): If a character's outline or growth arc establishes them as owner of a location, vehicle, or object, enforce it. Only the owner may use/operate/possess that entity unless ownership is explicitly transferred. Do NOT have other characters use an owned vehicle, location, or object without the owner's involvement.

HELD-OBJECT CONTINUITY (MANDATORY — PHYSICAL LOGIC):
- Track what each character is HOLDING or USING in their hands throughout the scene.
- A character holding an object CANNOT freely use another hand-held object unless they FIRST visibly put down, holster, pocket, sling, clip, or set aside the current object.
- When a character needs to use a different object, write the transition: e.g. CHLOE *tucks* the [Ecto-Detector 3000] under her arm, then *pulls* out her [phone].
- TWO-HANDED objects require BOTH hands — character must fully set them down before using another object.
- Small one-handed objects (phone, flashlight, key) can be held simultaneously with one other small object if realistic.
- If a character puts an object down, they must *pick up* or *grab* it again before using it later.

CANONICAL NAMES (MANDATORY): Preserve ALL character and entity names from the current content EXACTLY. Do NOT substitute, abbreviate, shorten, or creatively alter (e.g. KAI LEE must never become KAIRA LIN; ALEX SPECTRE MORGAN must never become ALEXIS; vehicle names like {{Starweaver}} must never become {{Starwarrior}}). Do NOT add titles or ranks (Captain, Detective, Dr., etc.) to character names unless the title is already part of the registered name. Use the exact names as they appear in the current content.

SCENE MARKUP STANDARD (MANDATORY):
- CHARACTERS: Individual character names (human or non-human) in FULL CAPS using their COMPLETE registered name on every mention (e.g. MAYA RIVERA not MAYA, SIR REGINALD 'REG' BARTLETT not SIR REGINALD, SHADOWFANG not SHADOW). The ONLY exception is inside dialogue quotes where nicknames are natural speech. Every character in FULL CAPS at least once. FULL CAPS are ONLY for individual character names — NEVER for emphasis, codenames, protocols, operations, programs, labels, warnings, signs, organizations, groups, teams, companies, brands, sound effects, or any non-character text. Write all non-character text in normal case or Title Case (e.g. "Terminal Sanction" not "TERMINAL SANCTION").
- DIALOGUE: ALL dialogue MUST be enclosed in double quotes " ". Character name on own line (FULL CAPS), dialogue on the VERY NEXT line inside " " — separated by exactly ONE newline (\\n), NEVER a blank line. Example:\nHENRY\n"We're out of time."\nNever unquoted dialogue. Never put a blank line between the character name and their dialogue line.
- SOUND EFFECTS (SFX): ALL audible events MUST use (lowercase_underscore_format). You MUST use ONLY SFX from this approved list — no others: {self._get_sfx_list_for_prompt()}. If the sound you want is not listed, substitute the closest approved alternative. NEVER use (Meanwhile), (Henry), (Tension). Convert prose sounds to SFX markup. LAYERED SFX: Primary (action-caused, max 1 per action) + Ambient (environmental, max 2 per paragraph, ambient_ prefix).
- ACTION WORDS (WHITELIST ONLY): ALL visible physical movement MUST be wrapped in *asterisks*. You MUST use ONLY action verbs from this approved whitelist — no others: {self._get_action_verb_list_for_prompt()}. If the ideal verb is not listed, substitute the closest approved alternative (e.g. "clips" → *bump*; "nudges" → *push*). NEVER use feel, think, realize, decide, hope, fear, remember, regret. Intensity modifiers INSIDE markup: *walks (slowly)*, *slams (violently)*. Remove filler verbs: "begins to walk" → "*walks*".
- LOCATIONS: Title Case + underlined (e.g. _City Hall_, _The Warehouse_, _Common Area_). Vehicle interiors (e.g. "the ship's Common Area", Bridge, Cockpit) are locations — use _underscores_, NOT {{braces}}. Example: "gathers in the ship's _Common Area_". Every location underlined on every mention.
- OBJECTS (interactable only): [brackets]. Mark objects when a character DIRECTLY interacts with them. Also mark any object that is the direct target of any action verb, or that a character or their body part physically contacts (touches, strikes, bumps, knocks, brushes). Example: His elbow *bumps* the [porcelain vase] on the [entry table]. She *grabs* the [handle]. Objects not directly interacted with must NOT be bracketed. OBJECT INTERACTION EXPANSION: mark when character sits on, perches on, leans on/against, rests feet on, holds, touches, places on, or props feet on. No "chair" or "stool" without brackets when physically interacted with.
- VEHICLES: {{braces}} — only when character drives/enters/operates. Example: {{motorcycle}}. Interior spaces (Common Area, Bridge) use _underscores_, not {{braces}}. No interaction → no markup.

SCREENPLAY MODE: Write only what can be seen or heard. Action-line style; no internal thoughts or metaphor. All dialogue in double quotes " ".

MANDATORY INSTRUCTIONS - YOU MUST FOLLOW THESE EXACTLY:
1. Edit ONLY paragraph [{paragraph_index + 1}] based on the user's request
2. Keep ALL other paragraphs ([1], [2], ... [{paragraph_index}], [{paragraph_index+2}], ... [{len(paragraphs)}]) EXACTLY as they are - copy them word-for-word, character-for-character
3. Return the COMPLETE scene content with ALL {len(paragraphs)} paragraphs, maintaining the same numbering format:
   - Paragraph [1]: {"[EDIT THIS]" if paragraph_index == 0 else "[KEEP EXACTLY AS IS - copy from above]"}
   - Paragraph [2]: {"[EDIT THIS]" if paragraph_index == 1 else "[KEEP EXACTLY AS IS - copy from above]"}
   - Paragraph [3]: {"[EDIT THIS]" if paragraph_index == 2 else "[KEEP EXACTLY AS IS - copy from above]"}
   - ... continue for all {len(paragraphs)} paragraphs ...
4. Maintain the same paragraph structure (separate paragraphs with double newlines: \\n\\n)
5. Include the paragraph numbers in your response: [1], [2], [3], etc. at the start of each paragraph
6. Ensure continuity with previous scenes

EXAMPLE OF WHAT TO RETURN (if editing paragraph [2]):
[1] [Original paragraph 1 text exactly as shown above - copy word-for-word]

[2] [Your edited paragraph 2 text here - this is the ONLY paragraph you should change]

[3] [Original paragraph 3 text exactly as shown above - copy word-for-word]

[4] [Original paragraph 4 text exactly as shown above - copy word-for-word]
... (all other paragraphs exactly as shown, with their numbers)

CRITICAL: 
- Return ALL {len(paragraphs)} paragraphs with their numbers [1], [2], [3], etc.
- Do NOT return only the edited paragraph
- Do NOT return fewer paragraphs
- Do NOT change any paragraph except [{paragraph_index + 1}]
- Return the COMPLETE scene with all paragraphs numbered

Return ONLY the complete scene content with all paragraphs numbered, no additional formatting or explanations.
"""
        else:
            # Full scene regeneration
            prompt = f"""Regenerate the scene content based on the user's request.

{previous_scenes_context}

Scene: {scene.title}
Current Content:
{existing_content}

User Request: {user_request}

CRITICAL CONTINUITY INSTRUCTIONS:
- Maintain consistency with previous scenes. If a character was in a specific location, vehicle, or situation in previous scenes, preserve that continuity.
- Do not introduce contradictions (e.g., if John was on a motorbike in the previous scene, don't suddenly put him in a car unless the user explicitly requests it).
- Reference the previous scenes above to understand the story state and maintain logical progression.
- ENTITY DESCRIPTION RULE: Once an entity (character, location, vehicle, object) has been fully described in a previous scene, do NOT repeat that description in later scenes. Reference the entity by name/markup only unless the story has changed them (e.g. damage, new state).
  EXCEPTION — CHARACTER WARDROBE: Character clothing/wardrobe MUST be described on each character's first appearance in EVERY scene. If their outfit has not changed, a brief reference is sufficient (e.g. "still wearing his olive vest"). If changed, describe the new wardrobe fully.

ENVIRONMENT ESTABLISHMENT (MANDATORY — FIRST PARAGRAPH):
- The FIRST paragraph of the scene MUST establish the environment/location.
- Describe the setting: architecture, surfaces, lighting, atmosphere, key visual features.
- Use _underscored_ location markup on every mention.
- If the scene introduces a NEW environment, provide a full sensory description.
- If returning to a previously seen environment, a brief re-establishing line is sufficient.
- The environment paragraph must come BEFORE any character action or dialogue.

LIGHTING CONDITIONS (MANDATORY — EVERY SCENE):
- The scene MUST explicitly state the lighting conditions in the environment-establishing paragraph.
- EXTERIOR: specify time of day and its visual effect (dawn, early morning, midday, afternoon, golden hour, dusk, twilight, night, overcast, bright sunshine, stormy).
- INTERIOR: specify the source and quality of light (fluorescent, incandescent, candlelight, firelight, window light, neon, dim bulbs, spotlights, screen glow, darkness). State whether daylight enters and its quality.
- Lighting must be described in concrete visual terms the camera can capture.
- If the scene changes location, the new location's lighting must also be established.

OWNERSHIP RULE (STRICT): If a character's outline or growth arc establishes them as owner of a location, vehicle, or object, enforce it. Only the owner may use/operate/possess that entity unless ownership is explicitly transferred. Do NOT have other characters use an owned vehicle, location, or object without the owner's involvement.

HELD-OBJECT CONTINUITY (MANDATORY — PHYSICAL LOGIC):
- Track what each character is HOLDING or USING in their hands throughout the scene.
- A character holding an object CANNOT freely use another hand-held object unless they FIRST visibly put down, holster, pocket, sling, clip, or set aside the current object.
- When a character needs to use a different object, write the transition: e.g. CHLOE *tucks* the [Ecto-Detector 3000] under her arm, then *pulls* out her [phone].
- TWO-HANDED objects require BOTH hands — character must fully set them down before using another object.
- Small one-handed objects (phone, flashlight, key) can be held simultaneously with one other small object if realistic.
- If a character puts an object down, they must *pick up* or *grab* it again before using it later.

CANONICAL NAMES (MANDATORY): Preserve ALL character and entity names from the current content and scene EXACTLY. Do NOT substitute, abbreviate, shorten, or creatively alter (e.g. KAI LEE must never become KAIRA LIN; ALEX SPECTRE MORGAN must never become ALEXIS; {{Starweaver}} must never become {{Starwarrior}}). Do NOT add titles or ranks (Captain, Detective, Dr., etc.) to character names unless the title is already part of the registered name. Use the exact names as they appear in the current content.

SCENE MARKUP STANDARD (MANDATORY):
- CHARACTERS: Individual character names (human or non-human) in FULL CAPS using their COMPLETE registered name on every mention (e.g. MAYA RIVERA not MAYA, SIR REGINALD 'REG' BARTLETT not SIR REGINALD, SHADOWFANG not SHADOW). The ONLY exception is inside dialogue quotes where nicknames are natural speech. Every character present in FULL CAPS at least once. FULL CAPS are ONLY for individual character names — NEVER for emphasis, codenames, protocols, operations, programs, labels, warnings, signs, organizations, groups, teams, companies, brands, sound effects, or any non-character text. Write all non-character text in normal case or Title Case.
- DIALOGUE: ALL dialogue MUST be enclosed in double quotes " ". Character name on own line (FULL CAPS), dialogue on the VERY NEXT line inside " " — separated by exactly ONE newline (\\n), NEVER a blank line. Never unquoted dialogue. Never put a blank line between the character name and their dialogue line.
- SOUND EFFECTS (SFX): ALL audible events MUST use (lowercase_underscore_format). You MUST use ONLY SFX from this approved list — no others: {self._get_sfx_list_for_prompt()}. If the sound you want is not listed, substitute the closest approved alternative. NEVER use (Meanwhile), (Henry), (Tension). Convert prose sounds to SFX. LAYERED SFX: Primary (max 1 per action) + Ambient (max 2 per paragraph, ambient_ prefix).
- ACTION WORDS (WHITELIST ONLY): ALL visible physical movement MUST be wrapped in *asterisks*. You MUST use ONLY action verbs from this approved whitelist — no others: {self._get_action_verb_list_for_prompt()}. If the ideal verb is not listed, substitute the closest approved alternative (e.g. "clips" → *bump*; "nudges" → *push*). NEVER use feel, think, realize, decide, hope, fear, remember. Intensity modifiers INSIDE: *walks (slowly)*, *slams (violently)*. Remove fillers: "begins to walk" → "*walks*".
- LOCATIONS: Title Case + underlined (e.g. _City Hall_, _The Warehouse_, _Common Area_). Vehicle interiors ("the ship's Common Area", Bridge, Cockpit) are locations — use _underscores_, NOT {{braces}}. Every location underlined on every mention.
- OBJECTS (interactable only): [brackets]. Mark objects when a character DIRECTLY interacts with them. Also mark any object that is the direct target of any action verb, or that a character or their body part physically contacts (touches, strikes, bumps, knocks, brushes). Example: His elbow *bumps* the [porcelain vase] on the [entry table]. Objects not directly interacted with must NOT be bracketed. OBJECT INTERACTION EXPANSION: mark when character sits on, perches on, leans on/against, rests feet on, holds, touches, places on, or props feet on. No unmarked chair/stool/console when physically interacted with.
- VEHICLES: {{braces}} — only when a character drives/enters/operates. Example: {{motorcycle}}. Interior spaces use _underscores_, not {{braces}}. No interaction → no markup.

SCREENPLAY MODE: Write only what can be seen or heard. Action-line style; no internal thoughts or metaphor. All dialogue in double quotes " ".

Generate new scene content that incorporates the user's request while maintaining story continuity with previous scenes. Return screenplay-style content only (visible action and dialogue).
Return ONLY the new scene content, no additional formatting or explanations.
"""
        
        try:
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You are a screenwriter regenerating scene content. CRITICAL: Use character and entity names EXACTLY as in the current content—never substitute, abbreviate, or creatively alter (e.g. KAI LEE must never become KAIRA LIN; ALEX SPECTRE MORGAN must never become ALEXIS; vehicle names must match exactly). Scene content must be SCREENPLAY STYLE: only visible action and audible dialogue; no internal thoughts or metaphor; action-line style; dialogue = name on own line (FULL CAPS), dialogue on the VERY NEXT line (one \\n, NEVER a blank line). CRITICAL: All dialogue MUST be in double quotes \" \" — every spoken line, no exceptions. SCENE MARKUP: Characters = FULL CAPS only (never for sound effects). CINEMATIC GRAMMAR (MANDATORY): ACTION — ALL visible physical movement MUST be wrapped in *asterisks*. Use ONLY action verbs from the approved whitelist in the prompt — if a verb is not on the list, substitute the closest approved alternative. Intensity modifiers INSIDE markup: *walks (slowly)*, *slams (violently)*. Remove filler verbs: 'begins to walk' → '*walks*'. NEVER wrap emotional verbs (feel, think, realize, decide, hope, fear, remember). SFX — ALL audible events MUST use ONLY SFX from the approved whitelist in the prompt — if a sound is not on the list, substitute the closest approved alternative. LAYERED SFX: Primary (max 1 per action) + Ambient (max 2 per paragraph, ambient_ prefix). NEVER use (Meanwhile), (Henry), (Tension). Locations = Title Case + underlined (_Location_). Vehicle interiors (ship's Common Area, Bridge, Cockpit) are locations — use _underscores_, NOT curly braces. Only the vehicle itself uses curly braces. Objects = [brackets] when character directly interacts (sit, lean, hold, touch, use) OR when an object is the direct target of any action or physical contact (including body-part contact like elbows, shoulders, hips). Do NOT bracket objects not directly interacted with. Vehicles = curly braces when character drives/enters/operates. OWNERSHIP: If a character owns a location/vehicle/object (per outline), only they may use it unless ownership is explicitly transferred."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=max(self.model_settings.get("max_tokens", 1000), 3000)  # Increased for full scene content
            )
            
            new_content = response.choices[0].message.content.strip()
            # Auto-correct physical-interaction object markup (sit/lean/perch/rest/prop + unmarked noun → [noun])
            new_content = self._fix_physical_interaction_object_markup(new_content)
            # ── SENTENCE INTEGRITY REPAIR ──
            new_content, _ = self._repair_sentence_integrity(new_content)
            # ── CINEMATIC GRAMMAR PASS ──
            new_content, _ = enforce_cinematic_grammar(new_content)
            # Dialogue validation: ensure all dialogue is in double quotes
            new_content = self._fix_dialogue_quotes(new_content)
            # Strip cinematic markup from inside dialogue
            new_content = self._strip_markup_from_dialogue(new_content)
            
            # If this was a paragraph edit, ALWAYS reconstruct from original paragraphs
            # This ensures we never lose any paragraphs, even if AI only returns the edited one
            if is_paragraph_edit:
                # Split original content into paragraphs
                original_paragraphs = [p.strip() for p in existing_content.split('\n\n') if p.strip()]
                if not original_paragraphs:
                    # Try single newline split
                    original_paragraphs = [p.strip() for p in existing_content.split('\n') if p.strip()]
                
                if not original_paragraphs:
                    # No paragraphs found - return as-is
                    return new_content
                
                # Split AI response into paragraphs (remove numbers if present)
                import re
                new_content_cleaned = re.sub(r'^\[\d+\]\s+', '', new_content, flags=re.MULTILINE)
                new_paragraphs = [p.strip() for p in new_content_cleaned.split('\n\n') if p.strip()]
                if not new_paragraphs:
                    # Try single newline split
                    new_paragraphs = [p.strip() for p in new_content_cleaned.split('\n') if p.strip()]
                
                # Start with a copy of all original paragraphs
                reconstructed = original_paragraphs.copy()
                
                # Extract the edited paragraph from AI response
                # Try to find the paragraph by its number first (e.g., [2] ...)
                edited_paragraph = None
                paragraph_number_pattern = rf'\[{paragraph_index + 1}\]\s+(.+?)(?=\n\n\[|\Z)'
                numbered_match = re.search(paragraph_number_pattern, new_content, re.DOTALL)
                
                if numbered_match:
                    # Found the paragraph by its number - extract content after the number
                    edited_paragraph = numbered_match.group(1).strip()
                elif len(new_paragraphs) == len(original_paragraphs):
                    # AI returned full scene with same paragraph count
                    # ALWAYS try to extract by paragraph number first (most reliable)
                    # If numbered match failed above, try a broader pattern to find the paragraph
                    if not numbered_match:
                        # Try to find paragraph with any number that matches our target
                        for para_num in range(1, len(new_paragraphs) + 1):
                            broader_pattern = rf'\[{para_num}\]\s+(.+?)(?=\n\n\[{para_num+1}\]|\n\n\[|\Z)'
                            broader_match = re.search(broader_pattern, new_content, re.DOTALL)
                            if broader_match and para_num == paragraph_index + 1:
                                edited_paragraph = broader_match.group(1).strip()
                                numbered_match = broader_match  # Mark as found
                                break
                    
                    # If we still don't have it from numbering, use index-based extraction
                    # But validate that the paragraph at expected index actually changed
                    if not numbered_match and paragraph_index < len(new_paragraphs) and paragraph_index < len(original_paragraphs):
                        new_para_at_index = new_paragraphs[paragraph_index].strip()
                        original_para_at_index = original_paragraphs[paragraph_index].strip()
                        
                        # Check if paragraph at expected index is different from original
                        # But also check if it matches another paragraph (which would indicate an error)
                        is_duplicate = False
                        for orig_idx, orig_para in enumerate(original_paragraphs):
                            if orig_idx != paragraph_index and new_para_at_index == orig_para.strip():
                                # This paragraph matches another original paragraph - likely an AI error
                                is_duplicate = True
                                break
                        
                        if is_duplicate:
                            # Paragraph at index is a duplicate of another paragraph - this is an error
                            # Look for which paragraph actually changed (it might be at a different index)
                            found_correct_change = False
                            for i, (new_p, orig_p) in enumerate(zip(new_paragraphs, original_paragraphs)):
                                if i != paragraph_index:
                                    new_p_stripped = new_p.strip()
                                    orig_p_stripped = orig_p.strip()
                                    # Check if this paragraph changed and is not a duplicate
                                    if new_p_stripped != orig_p_stripped:
                                        # Check if it's not a duplicate of another original paragraph
                                        is_other_dup = any(j != i and new_p_stripped == op.strip() for j, op in enumerate(original_paragraphs))
                                        if not is_other_dup:
                                            # This looks like the correct changed paragraph
                                            # If it's close to expected, use it
                                            if abs(i - paragraph_index) <= 1:
                                                edited_paragraph = new_p_stripped
                                                paragraph_index = i  # Update to correct index
                                                found_correct_change = True
                                                break
                            
                            if not found_correct_change:
                                # Couldn't find correct change - likely AI error
                                # The paragraph at expected index is a duplicate - this is wrong
                                # Regenerate the content by reconstructing: use original paragraphs and try again
                                # For now, we'll use the original paragraph to avoid wrong replacement
                                # But ideally we should regenerate with clearer instructions
                                # Since we can't regenerate here, we'll extract by trying to find the paragraph
                                # by its explicit number in the response, or keep original as fallback
                                edited_paragraph = original_para_at_index  # Keep original to avoid wrong replacement
                                # Log that we detected an issue (in production, you might want to log this)
                        elif new_para_at_index != original_para_at_index:
                            # Paragraph changed and is not a duplicate - use it
                            edited_paragraph = new_para_at_index
                        else:
                            # Paragraph unchanged - try to find which paragraph actually changed
                            for i, (new_p, orig_p) in enumerate(zip(new_paragraphs, original_paragraphs)):
                                if i != paragraph_index and new_p.strip() != orig_p.strip():
                                    # Found a different paragraph that changed
                                    # Only use it if it's close to expected (within 1 position)
                                    if abs(i - paragraph_index) <= 1:
                                        edited_paragraph = new_p.strip()
                                        paragraph_index = i  # Update to use actual changed paragraph
                                        break
                            else:
                                # No other paragraph changed - use the expected one (might be minimal changes)
                                edited_paragraph = new_para_at_index
                    elif paragraph_index < len(new_paragraphs):
                        # Fallback: use paragraph at expected index
                        edited_paragraph = new_paragraphs[paragraph_index].strip()
                    else:
                        # Index out of range - use last paragraph
                        edited_paragraph = new_paragraphs[-1].strip() if new_paragraphs else new_content_cleaned.strip()
                elif len(new_paragraphs) > len(original_paragraphs):
                    # AI returned more paragraphs - use the one at expected index
                    if paragraph_index < len(new_paragraphs):
                        edited_paragraph = new_paragraphs[paragraph_index]
                    else:
                        # Try to extract by paragraph number pattern
                        if numbered_match:
                            edited_paragraph = numbered_match.group(1).strip()
                        else:
                            edited_paragraph = new_paragraphs[-1]
                else:
                    # AI returned fewer paragraphs - likely just the edited one
                    # Use the first (or only) paragraph from response (it's the edited paragraph)
                    if new_paragraphs:
                        edited_paragraph = new_paragraphs[0]
                    else:
                        # No paragraphs found - use whole response as edited paragraph
                        edited_paragraph = new_content_cleaned.strip()
                
                # Validate that we have the edited paragraph before replacing
                if edited_paragraph and edited_paragraph.strip() and paragraph_index < len(reconstructed):
                    # CRITICAL: Final validation before replacing
                    # Ensure we're not replacing with a duplicate of another paragraph
                    edited_stripped = edited_paragraph.strip()
                    original_at_index = reconstructed[paragraph_index].strip()
                    
                    # Check if edited paragraph is a duplicate of another original paragraph
                    is_final_duplicate = False
                    for orig_idx, orig_para in enumerate(original_paragraphs):
                        if orig_idx != paragraph_index and edited_stripped == orig_para.strip():
                            is_final_duplicate = True
                            break
                    
                    if is_final_duplicate:
                        # Edited paragraph is a duplicate - don't replace, keep original
                        # This prevents paragraph 2 from becoming a duplicate of paragraph 1
                        pass  # Don't replace - keep original paragraph at this position
                    elif edited_stripped != original_at_index:
                        # Paragraph is different and not a duplicate - safe to replace
                        reconstructed[paragraph_index] = edited_paragraph
                    # If they're the same, also don't replace (no change needed)
                
                # Reconstruct the full scene content
                new_content = '\n\n'.join(reconstructed)
            
            # Ensure final content has physical-interaction object markup applied (covers reconstructed paragraph-edit result)
            new_content = self._fix_physical_interaction_object_markup(new_content)
            # ── SENTENCE INTEGRITY REPAIR ──
            new_content, _ = self._repair_sentence_integrity(new_content)
            # ── CINEMATIC GRAMMAR PASS ──
            new_content, _ = enforce_cinematic_grammar(new_content)
            # Dialogue validation: ensure all dialogue is in double quotes
            new_content = self._fix_dialogue_quotes(new_content)
            # Strip cinematic markup from inside dialogue
            new_content = self._strip_markup_from_dialogue(new_content)
            # Optional: validate screenplay style (log only; regenerate path has no drift_warnings)
            screenplay_style_passed, screenplay_style_issues = self._validate_screenplay_style(new_content)
            if not screenplay_style_passed and screenplay_style_issues:
                for issue in screenplay_style_issues:
                    print(f"Screenplay style (regenerate): {issue}")
            # HELD-OBJECT CONTINUITY VALIDATION (regenerate path)
            held_object_warnings = self._validate_held_object_continuity(new_content)
            if held_object_warnings:
                for hw in held_object_warnings:
                    print(f"Held-object continuity (regenerate): {hw}")
                if scene.metadata is None:
                    scene.metadata = {}
                existing_hw = scene.metadata.get("held_object_warnings", [])
                scene.metadata["held_object_warnings"] = existing_hw + held_object_warnings
            # Enforce full character names throughout regenerated scene content
            new_content = self._enforce_full_character_names(new_content, screenplay)
            # Extract and store consistency digest for continuity in later prompts
            digest = self._extract_consistency_digest(new_content, scene.title, screenplay=screenplay)
            if digest and scene:
                if scene.metadata is None:
                    scene.metadata = {}
                scene.metadata["consistency_digest"] = digest
            return new_content
        except Exception as e:
            raise Exception(f"Failed to regenerate scene content: {str(e)}")
    
    def regenerate_storyboard_items(self, scene: StoryScene, items: List[StoryboardItem], user_request: str, screenplay: Screenplay) -> List[StoryboardItem]:
        """Regenerate selected storyboard items based on chat discussion."""
        # This will use the existing generate_scene_storyboard logic but for specific items
        # For now, return a simplified version that regenerates items
        if not self._adapter:
            raise Exception("AI client not initialized.")
        
        # Get scene content
        scene_content = ""
        if scene.metadata and scene.metadata.get("generated_content"):
            scene_content = scene.metadata["generated_content"]
        else:
            scene_content = scene.description
        
        # Build prompt for regenerating items
        items_context = "\n".join([f"Item {item.sequence_number}: {item.storyline or item.prompt}" for item in items])
        
        prompt = f"""Regenerate the following storyboard items based on the user's request.

Scene: {scene.title}
Scene Content:
{scene_content[:500]}...

Current Items to Regenerate:
{items_context}

User Request: {user_request}

Regenerate these items incorporating the user's request. Return a JSON array with the regenerated items in this format:
{{
    "items": [
        {{
            "sequence_number": 1,
            "duration": 5,
            "storyline": "...",
            "image_prompt": "...",
            "prompt": "...",
            "dialogue": "...",
            "scene_type": "action",
            "camera_notes": "..."
        }}
    ]
}}

Return ONLY valid JSON. No markdown, no explanations.
"""
        
        try:
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": "You are a storyboard artist regenerating items based on user feedback."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=max(self.model_settings.get("max_tokens", 2000), 3000)
            )
            
            content = response.choices[0].message.content.strip()
            data = self._extract_and_parse_json(content)
            
            # Convert to StoryboardItem objects
            new_items = []
            for item_data in data.get("items", []):
                from core.screenplay_engine import StoryboardItem, SceneType
                import uuid
                
                scene_type_str = item_data.get("scene_type", "action").lower()
                scene_type = SceneType.ACTION
                for st in SceneType:
                    if st.value == scene_type_str:
                        scene_type = st
                        break
                
                new_item = StoryboardItem(
                    item_id=str(uuid.uuid4()),
                    sequence_number=item_data.get("sequence_number", 1),
                    duration=item_data.get("duration", 10),
                    storyline=item_data.get("storyline", ""),
                    image_prompt=(item_data.get("image_prompt", "") or "").strip(),
                    prompt=(item_data.get("prompt", "") or "").strip(),
                    visual_description=item_data.get("visual_description", ""),
                    dialogue=item_data.get("dialogue", ""),
                    scene_type=scene_type,
                    camera_notes=item_data.get("camera_notes", "")
                )
                
                # Calculate render cost
                render_cost, cost_factors = self._calculate_render_cost(new_item)
                new_item.render_cost = render_cost
                new_item.render_cost_factors = cost_factors
                
                # Detect identity drift (screenplay context needed - will be set when added)
                new_item.identity_drift_warnings = []
                
                new_items.append(new_item)
            
            return new_items
        except Exception as e:
            raise Exception(f"Failed to regenerate storyboard items: {str(e)}")
    
    def generate_scene_content(self, scene_description: str, word_count: int, 
                              screenplay: Screenplay, scene: StoryScene) -> str:
        """
        Generate full scene content based on scene description.
        
        Source-of-truth hierarchy: (1) Premise, (2) Story Structure, (3) Scene Content, (4) Storyboard.
        Lower layers must not contradict higher layers. Scene content is an EXPANSION of the scene summary only.
        
        Args:
            scene_description: The scene description (3-5 sentences) — CANON, must be followed exactly
            word_count: Target word count (200, 400, or 600)
            screenplay: The screenplay object for context
            scene: The scene object for context
        
        Returns:
            Tuple of (generated scene content as string, list of drift warnings if any)
        """
        if not self._adapter:
            raise Exception("AI client not initialized. Please configure your API key or local AI server in settings.")
        
        # Build context from screenplay
        genres = ", ".join(screenplay.genre) if screenplay.genre else "General"
        atmosphere = screenplay.atmosphere or "Neutral"
        title = screenplay.title or "Untitled Story"
        
        # Get act and scene context
        act_number = None
        for act in screenplay.acts:
            if scene in act.scenes:
                act_number = act.act_number
                break
        
        # Build character context - include ALL characters from story outline, not just character_focus
        # This ensures newly added characters are available for un-generated scenes
        primary_characters = scene.character_focus if scene.character_focus else []
        all_characters_info = ""
        all_character_names = []
        
        # Get all characters from story outline
        if screenplay.story_outline and isinstance(screenplay.story_outline, dict):
            characters = screenplay.story_outline.get("characters", [])
            if characters and isinstance(characters, list):
                all_characters_info = "\n\nALL AVAILABLE CHARACTERS (use any that fit naturally in this scene):\n"
                for char in characters:
                    if isinstance(char, dict):
                        char_name = char.get("name", "Unnamed Character")
                        char_outline = char.get("outline", "")
                        char_growth = char.get("growth_arc", "")
                        char_role = char.get("role", "main")
                        
                        all_character_names.append(char_name)
                        
                        # Mark primary characters (those in character_focus) and minor characters
                        is_primary = char_name in primary_characters
                        if is_primary:
                            role_marker = " [PRIMARY - MUST FEATURE IN THIS SCENE]"
                        elif char_role == "minor":
                            role_marker = " [MINOR - may appear if named in scene summary or fits naturally]"
                        else:
                            role_marker = ""
                        
                        char_phys = char.get("physical_appearance", "")
                        char_species = char.get("species", "Human") or "Human"
                        
                        species_note = f"  Species/Form: {char_species}\n" if char_species != "Human" else ""
                        all_characters_info += f"\n{char_name}{role_marker}:\n"
                        if species_note:
                            all_characters_info += species_note
                        if char_outline:
                            all_characters_info += f"  Outline: {char_outline}\n"
                        if char_growth:
                            all_characters_info += f"  Growth Arc: {char_growth}\n"
                        if char_phys and char_role == "minor":
                            all_characters_info += f"  Physical Appearance: {char_phys}\n"
                
                # Add character_focus names not in outline (e.g. AI AEON in body-swap stories)
                outline_char_names = {str(c.get("name", "")).strip().upper() for c in (characters or []) if isinstance(c, dict) and c.get("name")}
                for cf in (primary_characters or []):
                    if cf and str(cf).strip().upper() not in outline_char_names:
                        all_characters_info += f"\n{cf.strip()} [PRIMARY - MUST FEATURE IN THIS SCENE]:\n  (Character from character_focus—use this EXACT name.)"
                if primary_characters:
                    all_characters_info += "\nCHARACTER RULES:"
                    all_characters_info += "\n- Characters marked [PRIMARY] MUST appear in this scene."
                    all_characters_info += "\n- Characters marked [MINOR] who are named in the scene summary MUST appear using their EXACT name."
                    all_characters_info += "\n- You MAY introduce NEW minor characters if they serve the story naturally (e.g. a shopkeeper, a bystander, a receptionist). Give them a proper name in FULL CAPS."
                    all_characters_info += "\n- NEVER rename, replace, or substitute any existing character. Use EXACT names (e.g. MARSHAL ELIAS CROSS, not MARSHAL CROSS or MARSHAL SMITH). NEVER substitute similar names (e.g. TIMMONS for TIMOTHY; LUCA for LUCIEN). NEVER add titles or ranks (Captain, Detective, Dr., etc.) to a character name unless that title is already part of the registered name."
                    all_characters_info += "\n- NEW minor characters must have COMPLETELY DIFFERENT names from existing characters. NEVER create a character whose first name, last name, title, or nickname overlaps with ANY existing character (e.g. if SIR REGINALD 'REG' BARTLETT exists, do NOT create SIR REGINALD FITZSIMMONS or BARTLETT anything or REGINALD anything). No two characters may share any name part."
                    all_characters_info += "\n- NAME UNIQUENESS: No two characters in the scene may share any part of their name. Check every word in the new name against every word in every existing character name. If ANY word matches, choose a completely different name."
                else:
                    all_characters_info += "\nCHARACTER RULES:"
                    all_characters_info += "\n- Characters marked [PRIMARY] must be featured in this scene."
                    all_characters_info += "\n- Other characters from the list may appear naturally if they fit the scene's context."
                    all_characters_info += "\n- You MAY introduce NEW minor characters if they serve the story naturally. Give them a proper name in FULL CAPS."
                    all_characters_info += "\n- NEVER rename or substitute any existing character. NEVER add titles or ranks (Captain, Detective, Dr., etc.) to names."
                    all_characters_info += "\n- NEW minor characters must have COMPLETELY DIFFERENT names from existing characters. No two characters may share any part of their name (first name, last name, title, or nickname)."
                all_characters_info += "\nOWNERSHIP RULE (STRICT): If a character is established as the owner of a location (_underlined_), vehicle ({{braces}}), or object ([brackets]) in their outline or growth arc, this MUST be strictly enforced. Only the owner may use, operate, or possess that entity unless ownership has been explicitly transferred in the story. Do NOT have other characters use an owned vehicle, enter an owned location as if they own it, or take an owned object without the owner's involvement or explicit transfer."
                all_characters_info += "\nHELD-OBJECT CONTINUITY (MANDATORY): Track what each character is HOLDING in their hands throughout the scene. A character holding one object CANNOT use another hand-held object unless they first put down, pocket, holster, tuck, or set aside the current one. Write the transition explicitly (e.g. *tucks* the [detector] under her arm, then *pulls* out her [phone]). Two-handed objects must be fully set down first. Small one-handed items (phone, key, flashlight) may be held simultaneously with one other small item if realistic."
        
        # Build canonical names list (characters + entities from scene) - MUST be used exactly, never altered
        canonical_characters = set(primary_characters) | set(all_character_names)
        if getattr(screenplay, 'character_registry', None):
            canonical_characters.update(screenplay.character_registry or [])
        # Extract vehicle/location/object markup from scene description ({braces}, {{braces}}, _underscores_)
        canonical_entities = []
        for match in re.findall(r'\{+([^{}]+)\}+|_([^_]+)_', scene_description):
            entity = (match[0] or match[1] or "").strip()
            if entity and entity not in canonical_entities:
                canonical_entities.append(entity)
        # Add story outline locations (scene may say "town of X" without underscores)
        if screenplay.story_outline and isinstance(screenplay.story_outline, dict):
            outline_locs = screenplay.story_outline.get("locations", []) or []
            for loc in outline_locs:
                if isinstance(loc, str) and loc.strip():
                    clean = loc.strip().rstrip("'")  # e.g. "Midnight Falls'" -> "Midnight Falls"
                    if clean and clean not in canonical_entities:
                        canonical_entities.append(clean)
        # Extract location-like proper nouns from scene description (e.g. "town of Midnight Falls", "at The Salty Spur")
        for m in re.finditer(r'(?:town of|in|at|near)\s+([A-Z][A-Za-z\s\']+?)(?:\s|,|\.|$)', scene_description):
            loc = m.group(1).strip().rstrip("'")
            if len(loc) > 2 and loc not in canonical_entities and loc.lower() not in ('the', 'a', 'an'):
                canonical_entities.append(loc)
        
        # Extract character names explicitly mentioned in scene description
        # This ensures ALL characters named in the description are used, not just character_focus
        scene_desc_characters = set()
        desc_upper = scene_description.upper()
        all_known = (all_character_names or []) + list(getattr(screenplay, 'character_registry', []) or [])
        # Build a set of name-words shared by 2+ characters so they can't trigger inclusion alone
        _name_word_counts: dict = {}
        for _cn in all_known:
            if isinstance(_cn, str) and _cn.strip():
                for _w in _cn.upper().split():
                    if len(_w) > 2:
                        _name_word_counts[_w] = _name_word_counts.get(_w, 0) + 1
        _shared_words = {w for w, c in _name_word_counts.items() if c > 1}

        for char_name in all_known:
            if not isinstance(char_name, str) or not char_name.strip():
                continue
            # Full-name match is always reliable
            if char_name.upper() in desc_upper:
                scene_desc_characters.add(char_name)
                continue
            # Word-level match: only trigger on words UNIQUE to this character
            unique_words = [w for w in char_name.upper().split() if len(w) > 2 and w not in _shared_words]
            if unique_words and any(w in desc_upper for w in unique_words):
                scene_desc_characters.add(char_name)
        if scene_desc_characters:
            canonical_characters = (canonical_characters or set()) | scene_desc_characters
        
        # Location entities - valid place names from scene + outline (exclude temporal words, gang names)
        temporal_words = {'once', 'soon', 'later', 'then', 'now', 'here', 'there', 'before', 'after'}
        canonical_locations = [e for e in canonical_entities if e.strip() and e.lower() not in temporal_words]
        
        # Build character text for the prompt header (primary + scene-described characters)
        chars_to_feature = sorted(set(primary_characters) | scene_desc_characters)
        character_text = ", ".join(chars_to_feature) if chars_to_feature else "Various characters"
        
        # Identify newly added characters (in story outline but not in original character_focus)
        new_characters = []
        if all_character_names:
            new_characters = [name for name in all_character_names if name not in primary_characters]
        
        # Get previous scenes for continuity
        previous_scenes = self._get_previous_scenes(screenplay, scene)
        previous_scenes_context = self._build_previous_scenes_context(previous_scenes) if previous_scenes else ""
        
        # Presence validation: extract present vs referenced-only entities from summary
        allowed_present, referenced_only = self._extract_allowed_entities_from_summary(scene_description)
        present_list_str = ", ".join(allowed_present) if allowed_present else "(all entities mentioned in summary may appear visually unless listed below as REFERENCED ONLY)"
        referenced_list_str = ", ".join(referenced_only) if referenced_only else "(none)"
        
        # Build prompt
        new_characters_note = ""
        if new_characters:
            new_characters_note = f"\n\nNOTE: The following characters were added to the story after this scene was created: {', '.join(new_characters)}. You may naturally incorporate them into this scene if they fit the narrative context and story progression."
        
        # Premise is ABSOLUTE CANON: origin of powers, genre logic, causal rules. Scene may ONLY expand, not rewrite.
        premise_section = ""
        if getattr(screenplay, "premise", None) and screenplay.premise.strip():
            premise_section = f"""
CANON STORY RULES — MUST BE FOLLOWED EXACTLY:
The Premise defines the origin of powers, core genre logic, and the story's causal rules. It is CANON and MUST NOT be reinterpreted or replaced.

PREMISE (CANON — DO NOT CHANGE):
{screenplay.premise.strip()}

- Scene content may ONLY EXPAND this premise, not rewrite it.
- You are NOT allowed to introduce alternative origins, causes, or explanations (e.g. if the Premise says powers come from an energy drink, do NOT change this to an accident, technology malfunction, or other origin).
- No retconning. No alternate explanations. No genre drift.
- If anything in your draft would contradict the Premise, remove or change that part so it aligns with the Premise.
"""
        
        # Build forbidden list for prompt: only forbid example names NOT in this story
        allowed_locs_lower = {loc.strip().lower() for loc in canonical_locations}
        allowed_chars_lower = {c.strip().lower() for c in (canonical_characters or [])}
        forbidden_locs_prompt = [x for x in self.FORBIDDEN_EXAMPLE_LOCATIONS if x not in allowed_locs_lower]
        forbidden_chars_prompt = [x for x in self.FORBIDDEN_EXAMPLE_CHARACTERS if x not in allowed_chars_lower]
        forbidden_note = ""
        if forbidden_locs_prompt or forbidden_chars_prompt:
            parts = []
            if forbidden_locs_prompt:
                parts.append(f"locations: {', '.join('_' + x.replace(' ', '_') + '_' for x in forbidden_locs_prompt)}")
            if forbidden_chars_prompt:
                parts.append(f"characters: {', '.join(x.upper() for x in forbidden_chars_prompt)}")
            forbidden_note = f" Do NOT use example names from other stories ({'; '.join(parts)})."

        # ── Advertisement mode: build ad-specific guidance for scene content ──
        ad_guidance_section = ""
        if screenplay.is_advertisement_mode():
            from core.ad_framework import (
                build_ad_scene_content_guidance, get_brand_visual_style
            )
            bc = screenplay.brand_context
            emotional_anchor = getattr(bc, "emotional_anchor", "") if bc else ""
            personality = getattr(bc, "brand_personality", []) if bc else []
            visual_style = get_brand_visual_style(personality)
            ad_beat_type = getattr(scene, "ad_beat_type", "") or ""
            ad_guidance_section = build_ad_scene_content_guidance(
                brand_context=bc,
                emotional_anchor=emotional_anchor,
                visual_style=visual_style,
                ad_beat_type=ad_beat_type,
            )

        # ── Brand context section (for all promotional, not just ad mode) ──
        brand_context_section = ""
        if screenplay.brand_context:
            bc = screenplay.brand_context
            brand_context_section = "\n\nBRAND / PRODUCT CONTEXT:\n"
            if bc.brand_name:
                brand_context_section += f"Brand Name: {bc.brand_name}\n"
            if bc.product_name:
                brand_context_section += f"Product Name: {bc.product_name}\n"
            if bc.product_description:
                brand_context_section += f"Product Description: {bc.product_description}\n"
            if bc.core_benefit:
                brand_context_section += f"Core Benefit: {bc.core_benefit}\n"
            brand_context_section += "CRITICAL: All scene content MUST reference the product/brand and incorporate the core benefit.\n"

        # ── Wardrobe instructions based on selector state ──
        wardrobe_selector = getattr(scene, 'character_wardrobe_selector', {}) or {}
        _same_chars = []
        _change_chars = []
        _change_in_scene_chars = []
        for _eid, _choice in wardrobe_selector.items():
            _meta = screenplay.identity_block_metadata.get(_eid, {})
            _cname = _meta.get("name", _eid) if isinstance(_meta, dict) else _eid
            if _choice == "same":
                _same_chars.append(_cname)
            elif _choice == "change":
                _change_chars.append(_cname)
            elif _choice == "change_in_scene":
                _change_in_scene_chars.append(_cname)

        wardrobe_instruction_block = ""
        if _same_chars or _change_chars or _change_in_scene_chars:
            parts = ["CHARACTER WARDROBE INSTRUCTIONS (PER-CHARACTER):"]
            if _same_chars:
                parts.append(
                    f"- The following characters have the SAME wardrobe as their previous scene. "
                    f"Do NOT describe new clothing. A brief reference is sufficient (e.g. \"still in his olive vest\"): "
                    + ", ".join(_same_chars)
                )
            if _change_chars:
                parts.append(
                    f"- The following characters have a WARDROBE CHANGE. On their first appearance, "
                    f"describe their NEW outfit in full detail (clothing, accessories, condition): "
                    + ", ".join(_change_chars)
                )
            if _change_in_scene_chars:
                parts.append(
                    f"- The following characters change wardrobe DURING this scene. "
                    f"Explicitly describe the moment the clothing change occurs: "
                    + ", ".join(_change_in_scene_chars)
                )
            wardrobe_instruction_block = "\n".join(parts)
        else:
            wardrobe_instruction_block = (
                "CHARACTER WARDROBE (MANDATORY — FIRST APPEARANCE IN SCENE):\n"
                "- The FIRST time each character appears in a scene, describe what they are WEARING.\n"
                "- Include: clothing, accessories, equipment, and condition of clothing.\n"
                "- If a character appeared in a previous scene and their wardrobe has NOT changed, a brief reference is acceptable.\n"
                "- Character wardrobe MUST be described — do NOT skip this."
            )

        prompt = f"""You are a professional screenwriter. Write a full, detailed scene based on the following scene description.

Title: {title}
Genres: {genres}
Atmosphere/Tone: {atmosphere}
Act: {act_number if act_number else "Unknown"}
Scene: {scene.scene_number} - {scene.title}
Primary Characters (must feature): {character_text}
Pacing: {scene.pacing}
Plot Point: {scene.plot_point if scene.plot_point else "None"}

{all_characters_info}{new_characters_note}
{brand_context_section}{ad_guidance_section}
{previous_scenes_context}
{premise_section}
SOURCE OF TRUTH: Hierarchy is (1) Premise, (2) Story Structure, (3) Scene Content, (4) Storyboard. Lower layers must not contradict higher layers. If there is a conflict, the higher layer wins and content must be regenerated.

CANON SCENE SUMMARY — MUST BE FOLLOWED EXACTLY:
{scene_description}

CANONICAL NAMES (MANDATORY — USE EXACTLY, NEVER ALTER):
You MUST use these exact character and entity names. Do NOT substitute, abbreviate, shorten, or creatively alter them.
- Characters (use exact spelling): {', '.join(sorted(canonical_characters)) if canonical_characters else '(see scene summary and character list above)'}
- Named entities from summary (vehicles {{braces}}, locations _underscores_): {', '.join(canonical_entities) if canonical_entities else '(use names from scene summary exactly)'}
Examples of FORBIDDEN alterations: KAI LEE must never become KAIRA LIN or similar variants; ALEX SPECTRE MORGAN must never become ALEXIS; {{Starweaver}} must never become {{Starwarrior}}. Use the exact names from the scene description and character list above. FULL NAME RULE: Always use the COMPLETE character name in FULL CAPS (e.g. SIR REGINALD 'REG' BARTLETT, not SIR REGINALD or SIR REG or BARTLETT). The ONLY exception is inside dialogue quotes (" ") where nicknames or short forms are natural speech. NICKNAME RULE: REBECCA 'REX' STERN and REX are the SAME character — one person. Outside dialogue, always use the full form. TITLE/RANK PROHIBITION: Do NOT add titles, ranks, or honorifics (Captain, Detective, Professor, Dr., etc.) to character names unless the title is ALREADY part of the registered name. JAXON REED must stay JAXON REED — never "CAPTAIN JAXON REED".

CHARACTERS — CRITICAL: NEVER RENAME EXISTING CHARACTERS:
- Characters from the character list above MUST use their EXACT FULL names (e.g. SIR REGINALD 'REG' BARTLETT, not SIR REGINALD or SIR REG or BARTLETT). The ONLY exception is inside dialogue quotes (" ") where nicknames or short forms are natural speech.
- NEVER rename, abbreviate, or substitute them with similar names. SARAH CHEN is NOT SARAH MARTIN. DANIEL 'DANNY' MARTINEZ is NOT DANIEL LEE.
- NEVER ADD titles, ranks, or honorifics to character names. If the character is registered as JAXON REED, write JAXON REED — NOT "Captain Jaxon Reed", "Detective Jaxon Reed", or "Dr. Jaxon Reed". The registered name IS the complete name. Titles may only appear inside dialogue quotes as natural speech.
- Every character explicitly named in the scene summary MUST appear. Do NOT omit or replace them. Use EXACT names — never substitute (JEREMIAH not JERMY, LUCIEN not LUKE).
- You MAY introduce new minor characters (e.g. a shopkeeper, guard, bystander) if they serve the story. Give each new minor character a proper name in FULL CAPS with cinematic markup. Do NOT rename an existing character to fill a minor role.
- New minor characters must have COMPLETELY DIFFERENT names from all existing characters. If REGINALD exists, do NOT create REGINALD FITZSIMMONS. No overlapping first names, last names, titles, or nicknames. Check every word in the new name against every word in every existing character name — if ANY word matches, choose a completely different name.

LOCATIONS — CRITICAL: USE EXACT LOCATION FROM SCENE:
- Use ONLY these allowed locations for THIS story: {', '.join(canonical_locations) if canonical_locations else '(extract from scene summary — see _underscores_ and place names)'}
- Do NOT invent new place names (e.g. _Midnight Ranch_ when the story has _Midnight Falls_). Do NOT use temporal words (Once, Soon, Later, Then) as locations.{forbidden_note}

SCENE SCOPE — CURRENT MOMENT ONLY:
- The scene summary defines the CURRENT moment only.
- You may ONLY describe: actions occurring in the present scene; characters physically present; information the characters currently know.
- You MUST NOT: show future outcomes; visualize targets before they are encountered; depict states that occur in later scenes.

TEMPORAL RULES (no future-state visualization):
- Do NOT describe events, visuals, or states that occur after this scene.
- Do NOT show the target of a plan unless the summary explicitly says they are present.
- Planning scenes must not depict the execution or result of the plan.
- This applies to: characters, objects, locations, and conditions (e.g. captured, destroyed, revealed).

REFERENCE vs APPEARANCE:
- REFERENCED entities: allowed in dialogue, planning, or conceptual mention (e.g. "They talk about Cap", "The plan involves Cap"). They may NOT be visually described or shown in the scene.
- PRESENT entities: allowed in visual description (setting, character appearance, actions in frame). Only PRESENT entities may appear in scene visuals.
- Rule: Only PRESENT entities may appear in scene visuals. Referenced-only entities must not be depicted visually or physically.

ALLOWED IN VISUALS (PRESENT): {present_list_str}
REFERENCED ONLY (do NOT depict visually): {referenced_list_str}

RULES — YOU ARE NOT ALLOWED TO:
- Introduce new events
- Change tone or outcome
- Add characters not referenced in the canon summary
- Add new story direction

YOU MAY ONLY:
- Expand the summary descriptively
- Add sensory detail
- Add atmosphere and pacing

RESTRICTIONS:
- Do NOT invent new story elements.
- Do NOT change the sequence of events.
- Each paragraph must map directly to a moment implied by the summary.
- The scene content is an EXPANSION of the summary, not a reinterpretation.

ENVIRONMENT ESTABLISHMENT (MANDATORY — FIRST PARAGRAPH):
- The FIRST paragraph of every scene MUST establish the environment/location.
- Describe the setting: architecture, surfaces, lighting, atmosphere, key visual features.
- Use _underscored_ location markup on every mention (e.g. _Foyer_, _Blackwood Manor_).
- If the scene introduces a NEW environment not seen in previous scenes, the first paragraph must provide a full sensory description: what the space looks like, its condition, lighting, textures, and mood.
- If the scene takes place in a previously established environment, a brief re-establishing line is sufficient.
- The environment paragraph must come BEFORE any character action or dialogue.

LIGHTING CONDITIONS (MANDATORY — EVERY SCENE):
- Every scene MUST explicitly state the lighting conditions in the environment-establishing paragraph.
- For EXTERIOR scenes, specify the time of day and its visual effect: dawn (soft pink/orange glow on the horizon), early morning (pale golden light), midday (bright overhead sun, harsh shadows), afternoon (warm angled light), golden hour (rich amber light), dusk (fading purple/orange sky), twilight (deep blue, last traces of light), night (moonlit, starlit, or pitch darkness), overcast (flat grey diffused light), bright sunshine (vivid, high-contrast light), stormy (dark brooding clouds, intermittent lightning).
- For INTERIOR scenes, specify the source and quality of artificial or natural light: fluorescent strip lights, warm incandescent lamps, candlelight, firelight, light filtering through windows, neon signage, dim overhead bulbs, harsh spotlights, screens casting blue-white glow, or darkness with specific light sources. Also state whether daylight enters through windows and its quality.
- Lighting MUST be described in concrete visual terms the camera can capture — never abstract or metaphorical.
- If the scene changes location mid-scene, the new location's lighting MUST also be established when the setting shifts.

{wardrobe_instruction_block}

OBJECT AND VEHICLE DESCRIPTIONS (MANDATORY — FIRST MENTION):
- The FIRST time an object [brackets] or vehicle {{braces}} appears in a scene, include a brief visual description.
- Describe: shape, size, material, colour, condition, any distinguishing features — what the camera would see.
- The description must be woven into the sentence where the entity first appears, using an appositive or descriptive clause.
- Example (object): Her [Ecto-Detector 3000], a bulky device cobbled together from a gutted microwave and a mood ring taped to its antenna, *buzzes* erratically.
- Example (vehicle): The {{Interceptor}}, a battered matte-black muscle car with cracked headlights and rust creeping along the wheel arches, *idles* at the kerb.
- If an object or vehicle was fully described in a previous scene, do NOT repeat the full description — reference it by name/markup only. If its state has changed (damaged, modified), describe only the change.
- This is essential for generating identity blocks. Every object and vehicle MUST have a visual description on first mention.

PARAGRAPH STRUCTURE (REQUIRED FOR STORYBOARD DECOMPOSITION):
- Write in discrete paragraphs. Use double newlines between paragraphs.
- One paragraph = one clear beat or moment.
- No paragraph should describe multiple unrelated actions.

CRITICAL CONTINUITY INSTRUCTIONS:
- Maintain consistency with previous scenes. If a character was in a specific location, vehicle, or situation in previous scenes, preserve that continuity.
- Do not introduce contradictions (e.g., if John was on a motorbike in the previous scene, don't suddenly put him in a car unless the scene description explicitly indicates a change).
- Reference the previous scenes above to understand the story state and maintain logical progression.
- Ensure character locations, vehicles, possessions, and situations flow logically from previous scenes.
- ENTITY DESCRIPTION RULE: Once an entity (character, location, vehicle, object) has been fully described in a previous scene, do NOT repeat that description in later scenes. Reference the entity by name/markup only unless the story has changed them (e.g. damage, new state).
  EXCEPTION — CHARACTER WARDROBE: Follow the CHARACTER WARDROBE INSTRUCTIONS above for each character's wardrobe handling in this scene.
- PRIMARY characters (marked above) MUST be featured in this scene.
- Other characters may appear naturally if they fit the scene's context, story progression, and make narrative sense.
- If new characters were added to the story, you may incorporate them organically if their presence enhances the scene and aligns with their character outlines.

OWNERSHIP RULE (STRICT): If a character's outline or growth arc establishes them as the owner of a location (_underlined_), vehicle ({{braces}}), or object ([brackets]), this MUST be strictly enforced. Only the owner may use, operate, or possess that entity unless ownership has been explicitly transferred in the story. Do NOT have other characters drive an owned vehicle, enter an owned location as if they own it, or take/use an owned object without the owner's involvement or explicit transfer.

HELD-OBJECT CONTINUITY (MANDATORY — PHYSICAL LOGIC):
- Track what each character is HOLDING or USING in their hands throughout the scene.
- A character who is holding an object (e.g. [Ecto-Detector 3000] in her hands) CANNOT freely use another hand-held object (e.g. [phone]) unless they FIRST visibly put down, holster, pocket, sling, clip, or set aside the current object.
- When a character needs to use a different object, write the transition: e.g. CHLOE *tucks* the [Ecto-Detector 3000] under her arm, then *pulls* out her [phone].
- TWO-HANDED objects (rifles, rigs, large devices) require BOTH hands — the character must fully set them down before using another object.
- Small one-handed objects (phone, flashlight, key) can be held simultaneously with one other small object if realistic.
- If a character puts an object down, they must *pick up* or *grab* it again before using it later.
- This applies within a single scene — every paragraph must be physically consistent with the previous one.

SCREENPLAY MODE (MANDATORY — scene content must read like a screenplay, NOT novel prose):
- Write only what can be SEEN or HEARD. No internal thoughts, no metaphorical language, no abstract emotion. If the camera cannot capture it, do not write it.
- ACTION LINE STYLE: Short, direct sentences. One action per sentence when possible. Focus on physical movement and interaction.
- Examples — Correct: [CHARACTER_NAME] opens the [door]. He steps into [LOCATION_FROM_SCENE]. The floorboards (crack). Incorrect: [CHARACTER] hesitates, feeling the weight of his past. Incorrect: The floorboards CRACK (FULL CAPS are only for character names). Incorrect: "protocol: TERMINAL SANCTION" (FULL CAPS used for a non-character label — write as "protocol: Terminal Sanction"). Use the actual character and location names from THIS scene's summary.
- CHARACTER PRESENCE: Every character present must be named in FULL CAPS and appear in action or dialogue. No implied presence.
- DIALOGUE FORMAT (MANDATORY): All spoken dialogue MUST be enclosed in double quotes " ". Character name on its own line (FULL CAPS), dialogue on the VERY NEXT line inside " " — separated by exactly ONE newline, NEVER a blank line. Example:\nHENRY\n"We're out of time."\nNever write unquoted dialogue. No single quotes, no bare text — every line of dialogue must be inside " ". Never put a blank line between the character name and their dialogue.
- NO NOVELISTIC LANGUAGE: No metaphors, poetic imagery, emotional interpretation, or adverbs describing internal state. Let action imply emotion.
- SENTENCE COMPLETENESS (CRITICAL): Every sentence MUST be grammatically complete with subject, verb, and object where required. Do NOT drop words. Do NOT write incomplete phrases. Every sentence must make sense when read aloud. Common errors to AVOID:
  - Missing verbs: "The beam before steadying" (WRONG) → "The beam *flickers* before steadying" (CORRECT)
  - Missing nouns after articles: "falls off with a." (WRONG) → "*falls* off with a (metal_clang)." (CORRECT)
  - Subject without verb: "It erratically." (WRONG) → "It *beeps* erratically." (CORRECT)
  - Possessive without noun: "The detector's intensifies." (WRONG) → "The detector's signal *intensifies*." (CORRECT)
  If in doubt, read each sentence aloud — if it sounds incomplete, add the missing word(s).

SCENE MARKUP STANDARD (MANDATORY — use consistently in ALL scene text):
- CHARACTERS: Write individual character names (human or non-human) in FULL CAPITAL LETTERS using their COMPLETE registered name on every mention. Example: MAYA RIVERA (not MAYA), SIR REGINALD 'REG' BARTLETT (not SIR REGINALD or SIR REG), SHADOWFANG (not SHADOW). The ONLY exception is inside dialogue quotes (" ") where nicknames or short forms are natural speech. Every character present MUST appear in FULL CAPS at least once. FULL CAPS are ONLY for individual character names — NEVER for anything else. This includes: organizations, groups, teams, companies, brands, sound effects, actions, emphasis, codenames, protocols, operations, programs, labels, warnings, signs, titles of documents, or any non-character phrase. Write all non-character text in normal case or Title Case. Example of FORBIDDEN usage: "protocol: TERMINAL SANCTION" or "PROJECT GENESIS" — these must be written as "protocol: Terminal Sanction" or "Project Genesis". Organizations/groups/teams use Title Case only.
- SOUND EFFECTS (SFX): ALL audible events MUST use (lowercase_underscore_format). You MUST use ONLY SFX from this approved list — no others are permitted: {self._get_sfx_list_for_prompt()}. If the sound you want is not on this list, choose the closest approved alternative. NEVER use (Meanwhile), (Henry), (Tension), emotions, or narrative. Convert prose sounds to SFX markup: "His boots crunch on broken glass" → "(glass_crunch)". LAYERED SFX: Primary SFX (action-caused, max 1 per action) + Ambient SFX (environmental, max 2 per paragraph, use ambient_ prefix): (ambient_wind), (ambient_rain), (ambient_mill_creak). Example: (ambient_mill_creak) MILO *steps* into the _Mill_. His [boots] *step* on broken glass (glass_crunch).
- ACTION WORDS (MANDATORY — WHITELIST ONLY): ALL visible physical movement MUST be wrapped in *asterisks*. You MUST use ONLY action verbs from this approved whitelist — no other action verbs are permitted: {self._get_action_verb_list_for_prompt()}. If the ideal verb is not on this list, you MUST substitute the closest approved alternative (e.g. "clips" → *bump* or *knock*; "nudges" → *push* or *tap*; "brushes" → *touch*; "slips" → *slide*). NEVER use an action verb that is not on this list. NEVER use feel, think, realize, decide, hope, fear, remember, regret. Intensity modifiers go INSIDE markup: *walks (slowly)*, *slams (violently)*, *turns (cautiously)*. Remove filler verbs: "begins to walk" → "*walks*", "starts turning" → "*turns*". Actions must be direct, concrete, visually observable.
- LOCATIONS / ENVIRONMENTS: Title Case + underlined with underscores. Use ONLY the allowed locations listed above. Every location MUST be underlined on every mention.
- VEHICLE INTERIORS = LOCATIONS (underlined), NOT vehicles. When something is referred to as "the ship's X" or "the [vehicle]'s X" (e.g. "the ship's Common Area", "the Stellar Wanderer's Bridge"), X is an interior space/environment — use _underscores_. Example: "The crew of the {{Stellar Wanderer}} gathers in the ship's _Common Area_." Common Area is a location because it is a room/space within the ship. Do NOT use {{braces}} for interior spaces like Common Area, Bridge, Cockpit, Medbay — use _underscores_.
- VEHICLES (exterior only): Wrap in curly braces. Example: {{Stellar Wanderer}}, {{motorcycle}}. Mark ONLY when referring to the vehicle itself (exterior). One identity = exterior of the craft. Camera outside the craft → VEHICLE.
- OBJECTS (interactable only): Wrap in square brackets. Mark objects when a character DIRECTLY interacts with them (sits on, leans on, holds, touches, uses, picks up, etc.). Objects that characters do NOT directly interact with must NOT be placed in [brackets] — no background props, no merely visible items.
  OBJECT INTERACTION EXPANSION (CRITICAL): Mark objects when a character: sits on it, perches on it, leans on or against it, rests feet on it, holds it, touches it, places an item on it, or props feet on it. These are explicit interactions even if described casually.
  OBJECT AS DIRECT TARGET OF ACTION (CRITICAL): Any object that is the direct object of an action verb MUST be in [brackets]. Any object that a character or a character's body part touches, strikes, impacts, bumps, knocks, or otherwise physically contacts MUST be in [brackets]. This includes incidental contact (e.g. an elbow clipping a vase, a shoulder brushing a shelf, a hip bumping a table).
  Examples: His elbow *bumps* the [porcelain vase] on the [entry table]. PAN BOLA *leans* back in his [chair], boots propped up on the [console]. She *grabs* the [handle]. He *kicks* the [door]. Her hand *brushes* the [railing].
  Do NOT write "bumps the vase" or "kicks the door" without brackets — any object receiving a physical action or contact REQUIRES [brackets].
  Also mark when a character uses, picks up, activates, or manipulates an object. Background props (merely visible, decorative) must NOT be bracketed. Do NOT bracket objects that appear in the scene but are not physically interacted with.
- No other entities may use these formats. No entity may use multiple markup types.
- Example format: [CHARACTER] enters [LOCATION], picks up the [keycard]. Use actual names from the scene summary. Vehicle interiors (Common Area, Bridge, Cockpit) use _underscores_; the vehicle itself uses {{braces}}.
- DIALOGUE IS MARKUP-FREE (MANDATORY): Text inside double quotes " " is spoken dialogue. NEVER place any cinematic markup inside dialogue. No _underscores_, no [brackets], no {{braces}}, no *asterisks* within " ". Dialogue must contain only plain spoken words.
  Correct: CHLOE BAXTER "Wave to our new subscribers, Marcus!"
  Wrong: CHLOE BAXTER "Wave to our [subscribers], Marcus!"

Write a complete scene in SCREENPLAY FORMAT that expands on the canon summary. The scene must read like a screenplay, not novel prose.
- Be approximately {word_count} words long
- Include only visible action and audible dialogue (what the camera can capture)
- Use short action lines; one action per sentence when possible
- Include dialogue if appropriate: character name on its own line (FULL CAPS), dialogue on the VERY NEXT line (one newline, NEVER a blank line). CRITICAL: ALL dialogue MUST be inside double quotes " " — every spoken line (e.g. "We're out of time.", "Go now."). No exceptions.
- Match the specified atmosphere and pacing through action and setting, not internal state
- Advance the plot and develop characters as described in the canon summary only through action and dialogue

Write in screenplay format with discrete paragraphs (double newlines between paragraphs). Include:
- Setting and environment details (visible only)
- LIGHTING (MANDATORY): The first paragraph MUST describe the lighting — time of day for exteriors (dawn, morning, midday, golden hour, dusk, night, overcast, sunshine) or light source/quality for interiors (fluorescent, candlelight, window light, neon, dim, etc.)
- Character actions and movements (physical, explicit)
- Dialogue (if any): name on own line, then dialogue in " " — all dialogue must be in double quotes
- Visual and atmospheric details (what can be seen/heard)
- No internal thoughts, metaphor, or abstract emotion — let action imply emotion

CRITICAL: Generate ONLY the scene content itself. Do NOT include:
- Act numbers or scene numbers
- Scene titles
- Pacing information
- Plot point labels
- Any metadata or headers
- Meta-commentary, explanations, or notes

Start directly with the scene description. Begin with the setting/lighting, then characters or action - not with labels or metadata."""

        system_msg = "You are a professional screenwriter. CRITICAL: Use character and entity names EXACTLY as specified in the prompt—never substitute, abbreviate, or creatively alter. ALL characters named in the scene description MUST appear—do not omit or replace any. FULL NAME RULE: Always refer to characters by their complete FULL CAPS name (e.g. SIR REGINALD 'REG' BARTLETT, not SIR REGINALD or SIR REG). The ONLY exception is inside dialogue quotes where nicknames/short forms are natural speech. For LOCATIONS: use ONLY the allowed locations listed in the prompt—never invent place names. Use THIS story's locations and characters only—never copy names from other stories." + forbidden_note + " NEVER use temporal words (Once, Soon, Later, Then) as locations. Vehicle interiors (Common Area, Bridge, Cockpit) are LOCATIONS — use _underscores_. LIGHTING (MANDATORY): The first paragraph of every scene MUST explicitly describe lighting conditions — time of day for exteriors (dawn, morning, midday, golden hour, dusk, night, overcast, sunshine) or light source and quality for interiors (fluorescent, candlelight, window light, neon, dim bulbs, screen glow, etc.). Never omit lighting. Scene content must be SCREENPLAY STYLE: only visible action and audible dialogue; no internal thoughts or metaphor; short, direct action lines; dialogue = character name on own line (FULL CAPS), dialogue on the VERY NEXT line (one newline, NEVER a blank line between name and dialogue). CRITICAL: All dialogue MUST be in double quotes. CINEMATIC GRAMMAR (MANDATORY): ACTION — ALL visible physical movement MUST be wrapped in *asterisks*. Use ONLY verbs from the approved whitelist in the prompt — if a verb is not on the list, substitute the closest approved alternative. Intensity modifiers INSIDE: *walks (slowly)*, *slams (violently)*. Remove filler verbs: 'begins to walk' → '*walks*'. NEVER wrap emotional verbs (feel, think, realize, decide). SFX — ALL audible events MUST use ONLY SFX from the approved whitelist in the prompt — if a sound is not on the list, substitute the closest approved alternative. LAYERED SFX: Primary (max 1 per action) + Ambient (max 2 per paragraph, ambient_ prefix). SCENE MARKUP: Characters = FULL CAPS only. Locations = Title Case + underlined. Objects = [brackets] when character directly interacts OR when an object is the direct target of any action or physical contact (including body-part contact like elbows, shoulders, hips). Vehicles = curly braces. OWNERSHIP: If a character owns a location/vehicle/object (per outline), only they may use it unless ownership is explicitly transferred."
        try:
            response = self._chat_completion(
                model=self.model_settings["model"],
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=max(self.model_settings["max_tokens"], 2000)
            )
            
            content = response.choices[0].message.content
            
            # Validate content
            if content is None:
                raise Exception("AI returned None response. Please check your AI settings and try again.")
            
            if not isinstance(content, str):
                content = str(content)
            
            if not content.strip():
                raise Exception("AI returned an empty response. Please check your AI settings and try again.")
            
            # Clean up the content (remove markdown, extra whitespace, etc.)
            content = content.strip()
            
            # Remove markdown code blocks if present
            if content.startswith("```"):
                lines = content.split("\n")
                # Remove first line (```markdown or ```)
                if len(lines) > 1:
                    lines = lines[1:]
                # Remove last line if it's ```
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
            
            # Remove metadata headers that the AI might include
            # Remove lines that look like "Act: X", "Scene: X - Title", "Pacing: X", "Plot Point: X"
            lines = content.split("\n")
            cleaned_lines = []
            skip_metadata = True
            for line in lines:
                line_stripped = line.strip()
                # Skip metadata lines at the start
                if skip_metadata:
                    # Check if this line looks like metadata
                    if (line_stripped.startswith("Act:") or 
                        line_stripped.startswith("Scene:") or 
                        line_stripped.startswith("Pacing:") or 
                        line_stripped.startswith("Plot Point:") or
                        line_stripped.startswith("Characters:") or
                        line_stripped.startswith("Title:") or
                        line_stripped.startswith("Genres:") or
                        line_stripped.startswith("Atmosphere:") or
                        line_stripped == ""):
                        continue
                    else:
                        skip_metadata = False
                        cleaned_lines.append(line)
                else:
                    cleaned_lines.append(line)
            
            content = "\n".join(cleaned_lines).strip()
            
            # Auto-correct physical-interaction object markup (sit/lean/perch/rest/prop + unmarked noun → [noun])
            content = self._fix_physical_interaction_object_markup(content)
            # ── SENTENCE INTEGRITY REPAIR (detect and fix broken/incomplete sentences) ──
            content, integrity_warnings = self._repair_sentence_integrity(content)
            if integrity_warnings:
                drift_warnings_pre = integrity_warnings  # Will be merged into drift_warnings later
            else:
                drift_warnings_pre = []
            # ── CINEMATIC GRAMMAR PASS (MANDATORY) ──
            # Enforces: action auto-wrap, filler rewrite, intensity modifiers, SFX expansion, layered SFX
            content, grammar_report = enforce_cinematic_grammar(content)
            if grammar_report.was_modified:
                print(f"CINEMATIC GRAMMAR: {grammar_report.summary()}")
            # Dialogue validation: ensure all dialogue is enclosed in double quotes
            content = self._fix_dialogue_quotes(content)
            # Strip cinematic markup from inside dialogue
            content = self._strip_markup_from_dialogue(content)
            # Fix character name typos (e.g. TIMMONS -> TIMOTHY when Timothy is in the story)
            char_names_for_typos = list(canonical_characters) if canonical_characters else []
            if screenplay and getattr(screenplay, "character_registry", None):
                char_names_for_typos = list(set(char_names_for_typos) | set(screenplay.character_registry or []))
            content = self._fix_character_typos_in_text(content, char_names_for_typos)
            
            # Validate scene content against canon summary (heuristic drift check)
            allowed_locs = set(e.strip() for e in canonical_entities) | {m.strip() for m in re.findall(r'_([^_]+)_', scene_description)}
            _, drift_warnings = self._validate_scene_against_summary(
                scene_description, content,
                allowed_locations=allowed_locs,
                allowed_characters=canonical_characters
            )
            # Presence validation: referenced-only entities must not appear visually
            _, presence_warnings = self._validate_presence_in_scene(content, allowed_present, referenced_only)
            drift_warnings = list(drift_warnings)
            drift_warnings.extend(presence_warnings)
            # Merge sentence integrity warnings
            if drift_warnings_pre:
                drift_warnings.extend(drift_warnings_pre)
            
            # SCREENPLAY STYLE VALIDATION: no internal thoughts, metaphor, or abstract emotion
            screenplay_style_passed, screenplay_style_issues = self._validate_screenplay_style(content)
            if not screenplay_style_passed and screenplay_style_issues:
                drift_warnings.extend([f"Screenplay style: {issue}" for issue in screenplay_style_issues])
            
            # SCENE MARKUP VALIDATION (MANDATORY): every Wizard character has markup, markup follows standard
            markup_passed, markup_issues = self._validate_scene_markup(content, screenplay)
            if not markup_passed and markup_issues:
                drift_warnings.extend([f"Scene markup: {issue}" for issue in markup_issues])
            
            # HELD-OBJECT CONTINUITY VALIDATION: detect characters using new objects while still holding another
            held_object_warnings = self._validate_held_object_continuity(content)
            if held_object_warnings:
                drift_warnings.extend(held_object_warnings)
            
            # Invented entities (wrong location, renamed characters): if detected, regenerate once.
            # New minor characters are allowed, so "introduce name/entity" is no longer a retry trigger.
            invented_warnings = [w for w in drift_warnings if (
                "Forbidden example" in w or
                "not in scene description" in w
            )]
            if invented_warnings:
                allowed_loc_list = ', '.join(sorted(allowed_locs)[:10]) if allowed_locs else '(from scene summary)'
                allowed_char_list = ', '.join(sorted(canonical_characters)[:15]) if canonical_characters else '(from character list)'
                retry_line = f"\n\nCRITICAL: The previous draft used WRONG locations or renamed existing characters. You MUST use ONLY: Locations: {allowed_loc_list}. Existing characters: {allowed_char_list}. Do NOT rename existing characters (e.g. SARAH MARTIN when the list says SARAH CHEN)—use EXACT names from the lists above. Do NOT invent new locations. The scene has character_focus={primary_characters}—those characters MUST appear. You may introduce new minor characters with new proper names if they serve the story, but NEVER rename an existing character."
                retry_prompt = prompt + retry_line
                try:
                    retry_system = f"You are a professional screenwriter. Use ONLY these locations: {allowed_loc_list}. Existing characters MUST use EXACT names: {allowed_char_list}. NEVER rename existing characters (e.g. SARAH MARTIN when the list says SARAH CHEN). NEVER invent new locations. You may introduce new minor characters with new proper names if they serve the story."
                    retry_response = self._chat_completion(
                        model=self.model_settings["model"],
                        messages=[
                            {"role": "system", "content": retry_system},
                            {"role": "user", "content": retry_prompt}
                        ],
                        temperature=0.5,
                        max_tokens=max(self.model_settings["max_tokens"], 2000)
                    )
                    content_retry = retry_response.choices[0].message.content
                    if content_retry and isinstance(content_retry, str) and content_retry.strip():
                        content_retry = content_retry.strip()
                        if content_retry.startswith("```"):
                            lines_retry = content_retry.split("\n")
                            if len(lines_retry) > 1:
                                lines_retry = lines_retry[1:]
                            if lines_retry and lines_retry[-1].strip() == "```":
                                lines_retry = lines_retry[:-1]
                            content_retry = "\n".join(lines_retry).strip()
                        lines_retry = content_retry.split("\n")
                        cleaned_retry = []
                        skip_md = True
                        for line in lines_retry:
                            ls = line.strip()
                            if skip_md and (ls.startswith("Act:") or ls.startswith("Scene:") or ls.startswith("Pacing:") or ls.startswith("Plot Point:") or ls.startswith("Characters:") or ls.startswith("Title:") or ls.startswith("Genres:") or ls.startswith("Atmosphere:") or ls == ""):
                                continue
                            skip_md = False
                            cleaned_retry.append(line)
                        content_retry = "\n".join(cleaned_retry).strip()
                        content_retry = self._fix_physical_interaction_object_markup(content_retry)
                        # ── SENTENCE INTEGRITY REPAIR ──
                        content_retry, _ = self._repair_sentence_integrity(content_retry)
                        # ── CINEMATIC GRAMMAR PASS ──
                        content_retry, _ = enforce_cinematic_grammar(content_retry)
                        content_retry = self._fix_dialogue_quotes(content_retry)
                        # Strip cinematic markup from inside dialogue
                        content_retry = self._strip_markup_from_dialogue(content_retry)
                        retry_valid, _ = self._validate_scene_against_summary(
                            scene_description, content_retry,
                            allowed_locations=allowed_locs,
                            allowed_characters=canonical_characters
                        )
                        retry_forbid = self._validate_forbidden_example_names(content_retry, allowed_locs, canonical_characters)
                        if retry_valid and not retry_forbid:
                            content = content_retry
                            drift_warnings = [w for w in drift_warnings if w not in invented_warnings]
                            drift_warnings.append("Scene was regenerated to fix invented locations/characters.")
                except Exception:
                    pass
            
            # Premise contradiction: if detected, regenerate once with explicit canon reminder
            premise_text = getattr(screenplay, "premise", None) or ""
            if premise_text.strip() and self._detect_premise_contradiction(premise_text, content):
                retry_premise_line = "\n\nCRITICAL PREMISE VIOLATION: The previous draft introduced an alternative origin, cause, or explanation that contradicts the CANON PREMISE above. Regenerate this scene so that it ONLY expands the premise — do NOT add alternate origins, retcons, or genre drift. The premise is absolute canon."
                retry_prompt = prompt + retry_premise_line
                try:
                    retry_response = self._chat_completion(
                        model=self.model_settings["model"],
                        messages=[
                            {"role": "system", "content": "You are a professional screenwriter. The story premise is CANON. You must never introduce alternative origins, causes, or explanations. Scene content may only EXPAND the premise, not rewrite it."},
                            {"role": "user", "content": retry_prompt}
                        ],
                        temperature=0.5,
                        max_tokens=max(self.model_settings["max_tokens"], 2000)
                    )
                    content_retry = retry_response.choices[0].message.content
                    if content_retry and isinstance(content_retry, str) and content_retry.strip():
                        content_retry = content_retry.strip()
                        if not self._detect_premise_contradiction(premise_text, content_retry):
                            content = content_retry
                            drift_warnings.append("Scene was regenerated to remove premise contradiction.")
                except Exception:
                    pass
            
            # Optional: one retry with stricter prompt if presence check failed
            if presence_warnings and referenced_only:
                retry_line = f"\n\nCRITICAL: The previous attempt showed entities that are not present in this scene. Generate again. Only the following may be visually shown: {present_list_str}. Do NOT visually depict: {referenced_list_str}."
                retry_prompt = prompt + retry_line
                try:
                    retry_response = self._chat_completion(
                        model=self.model_settings["model"],
                        messages=[
                            {"role": "system", "content": "You are a professional screenwriter specializing in detailed, cinematic scene descriptions suitable for film and video production. You must never depict targets of a plan or referenced-only entities visually."},
                            {"role": "user", "content": retry_prompt}
                        ],
                        temperature=0.5,
                        max_tokens=max(self.model_settings["max_tokens"], 2000)
                    )
                    content_retry = retry_response.choices[0].message.content
                    if content_retry and isinstance(content_retry, str) and content_retry.strip():
                        content_retry = content_retry.strip()
                        if content_retry.startswith("```"):
                            lines = content_retry.split("\n")
                            if len(lines) > 1:
                                lines = lines[1:]
                            if lines and lines[-1].strip() == "```":
                                lines = lines[:-1]
                            content_retry = "\n".join(lines).strip()
                        lines = content_retry.split("\n")
                        cleaned_lines = []
                        skip_metadata = True
                        for line in lines:
                            line_stripped = line.strip()
                            if skip_metadata:
                                if (line_stripped.startswith("Act:") or line_stripped.startswith("Scene:") or line_stripped.startswith("Pacing:") or line_stripped.startswith("Plot Point:") or line_stripped.startswith("Characters:") or line_stripped.startswith("Title:") or line_stripped.startswith("Genres:") or line_stripped.startswith("Atmosphere:") or line_stripped == ""):
                                    continue
                                skip_metadata = False
                            cleaned_lines.append(line)
                        content_retry = "\n".join(cleaned_lines).strip()
                        _, retry_presence = self._validate_presence_in_scene(content_retry, allowed_present, referenced_only)
                        if not retry_presence:
                            content = content_retry
                            drift_warnings = [w for w in drift_warnings if w not in presence_warnings]
                        else:
                            drift_warnings.extend(retry_presence)
                except Exception:
                    pass
            
            # Enforce full character names throughout scene content
            content = self._enforce_full_character_names(content, screenplay)
            
            # Extract consistency digest for use in later scene prompts (token-efficient continuity)
            digest = self._extract_consistency_digest(content, scene.title, screenplay=screenplay)
            if digest and scene:
                if scene.metadata is None:
                    scene.metadata = {}
                scene.metadata["consistency_digest"] = digest
            
            return (content, drift_warnings)
            
        except Exception as e:
            error_message = str(e)
            raise Exception(f"Failed to generate scene content: {error_message}")

