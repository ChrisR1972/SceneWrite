#!/usr/bin/env python3
"""
Fix and improve storyboard extraction from MoviePrompterAI project JSON.
Processes generated_content and creates proper storyboard items.
"""

import json
import re
import uuid
from typing import Dict, List, Any
from datetime import datetime

def split_into_paragraphs(content: str) -> List[str]:
    """Split content into paragraphs using double line breaks."""
    if not content:
        return []
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    return paragraphs

def get_identity_block_reference(entity_name: str, entity_type: str, identity_block_ids: Dict[str, str]) -> str:
    """Get identity block ID for an entity."""
    lookup_key = f"{entity_type}:{entity_name}".lower()
    return identity_block_ids.get(lookup_key, "")

def extract_entities_from_text(text: str, identity_block_ids: Dict[str, str]) -> Dict[str, List[str]]:
    """Extract entity references from text."""
    entities = {
        "characters": [],
        "objects": [],
        "vehicles": [],
        "environments": []
    }
    
    text_lower = text.lower()
    
    # Characters
    char_mappings = {
        "james": "CHARACTER_DDDC",
        "lucy": "CHARACTER_721B", 
        "martha": "CHARACTER_01FA",
        "mike": "CHARACTER_F8C7",
        "marion": "CHARACTER_27EA"
    }
    
    for name, block_id in char_mappings.items():
        if name in text_lower:
            entities["characters"].append(block_id)
    
    # Objects
    if "acme smart watch" in text_lower or ("smart watch" in text_lower and "acme" in text_lower):
        entities["objects"].append("OBJECT_5200")
    if "coffee maker" in text_lower or "coffee machine" in text_lower:
        entities["objects"].append("OBJECT_FBEB")
    if "eco-friendly container" in text_lower or ("container" in text_lower and "eco" in text_lower):
        entities["objects"].append("OBJECT_97D0")
    if "backpack" in text_lower:
        entities["objects"].append("OBJECT_3AD3")
    if "tablet" in text_lower:
        entities["objects"].append("OBJECT_064E")
    if "wireless earbuds" in text_lower or ("earbuds" in text_lower and "wireless" in text_lower):
        entities["objects"].append("OBJECT_1D91")
    if "dual monitors" in text_lower or ("monitors" in text_lower and "dual" in text_lower):
        entities["objects"].append("OBJECT_B860")
    if "treadmill" in text_lower:
        entities["objects"].append("OBJECT_388D")
    
    # Vehicles
    if "bike" in text_lower or "bicycle" in text_lower or ("hybrid" in text_lower and "bike" in text_lower):
        entities["vehicles"].append("VEHICLE_3DF5")
    
    return entities

def extract_dialogue(text: str) -> str:
    """Extract dialogue from text."""
    # Look for quoted text
    dialogue_matches = re.findall(r'"([^"]+)"', text)
    if dialogue_matches:
        # Try to find speaker - check text around the dialogue
        for match in dialogue_matches:
            # Find the sentence containing this dialogue
            sentences = re.split(r'[.!?]+', text)
            for sentence in sentences:
                if match in sentence:
                    # Look for character name in this sentence or previous one
                    sentence_lower = sentence.lower()
                    char_name = None
                    
                    # Check for character names
                    if "james" in sentence_lower or "james" in text.lower()[:text.find(match)]:
                        char_name = "James"
                    elif "lucy" in sentence_lower or "lucy" in text.lower()[:text.find(match)]:
                        char_name = "Lucy"
                    elif "martha" in sentence_lower or "martha" in text.lower()[:text.find(match)]:
                        char_name = "Martha"
                    elif "mike" in sentence_lower or "mike" in text.lower()[:text.find(match)]:
                        char_name = "Mike"
                    elif "marion" in sentence_lower or "marion" in text.lower()[:text.find(match)]:
                        char_name = "Marion"
                    
                    if char_name:
                        return f"{char_name}: \"{match}\""
                    else:
                        return f"Character: \"{match}\""
        
        # Fallback: return first dialogue found
        return f"Character: \"{dialogue_matches[0]}\""
    return ""

def determine_scene_type(paragraph: str) -> str:
    """Determine scene type from paragraph content."""
    para_lower = paragraph.lower()
    
    if any(word in para_lower for word in ['says', 'speaks', 'replies', 'dialogue', 'conversation', '"']):
        return "dialogue"
    elif any(word in para_lower for word in ['establishing', 'wide', 'overview', 'panoramic', 'hum', 'buzzes']):
        return "establishing"
    elif any(word in para_lower for word in ['close-up', 'closeup', 'zooms', 'focuses']):
        return "closeup"
    else:
        return "action"

def create_image_prompt(paragraph: str, environment_id: str, identity_blocks: Dict[str, str], entities: Dict[str, List[str]], identity_block_metadata: Dict[str, Dict]) -> str:
    """Create static image prompt (state BEFORE action)."""
    parts = []
    
    # Environment - use identity block
    if environment_id and environment_id in identity_blocks:
        env_block = identity_blocks[environment_id]
        # Extract key environment details (first part before comma)
        env_desc = env_block.split(',')[0] if ',' in env_block else env_block
        env_desc = env_desc.replace("The same environment with ", "").replace("The same ", "").strip()
        parts.append(f"Environment ({environment_id}): {env_desc}")
    
    # Characters (positioned, static - use identity block references)
    if entities["characters"]:
        char_refs = []
        for char_id in entities["characters"]:
            if char_id in identity_block_metadata:
                char_name = identity_block_metadata[char_id].get("name", "")
                char_refs.append(f"{char_name} ({char_id})")
        if char_refs:
            parts.append(f"Characters: {', '.join(char_refs)} positioned in frame, static pose")
    
    # Objects (visible, NOT appearing - CRITICAL for logo reveals)
    if entities["objects"]:
        obj_refs = []
        for obj_id in entities["objects"]:
            if obj_id in identity_block_metadata:
                obj_name = identity_block_metadata[obj_id].get("name", "")
                # For logo/watch reveals, DON'T include in image prompt (image = state BEFORE)
                para_lower = paragraph.lower()
                obj_mentioned = obj_name.lower() in para_lower
                
                # Check if object is appearing/revealing (CRITICAL: exclude from image prompt)
                is_appearing = False
                if obj_mentioned:
                    # Look for appearance/reveal ACTION verbs (not state verbs)
                    obj_index = para_lower.find(obj_name.lower())
                    if obj_index >= 0:
                        # Check context around object name (100 chars before and after)
                        context_start = max(0, obj_index - 100)
                        context_end = min(len(para_lower), obj_index + len(obj_name) + 100)
                        context = para_lower[context_start:context_end]
                        
                        # ACTION verbs (appearing) - exclude from image
                        action_appearance = any(word in context for word in [
                            "appears", "reveals", "bursts", "erupts", "emerges", "forms",
                            "becomes visible", "shows up", "materializes", "pops up"
                        ])
                        
                        # STATE verbs (already there) - can include in image
                        state_description = any(phrase in context for phrase in [
                            "is visible", "is prominently", "visible on", "visible in",
                            "glows", "displays"  # These can be states if not with "appears"
                        ])
                        
                        # If it says "appears" or action verb, it's appearing
                        # If it just says "is visible" without "appears", it's a state
                        is_appearing = action_appearance or (
                            "prominently visible" in context and "appears" in context
                        )
                
                # CRITICAL: If object is appearing/revealing, exclude from image prompt
                # Image prompt = state BEFORE action
                if obj_mentioned and not is_appearing:
                    obj_refs.append(f"{obj_name} ({obj_id})")
        if obj_refs:
            parts.append(f"Objects: {', '.join(obj_refs)} visible in frame")
    
    # Camera
    parts.append("Camera: Medium shot, eye level, static")
    
    # Extract static moment (first sentence, remove action verbs)
    sentences = re.split(r'[.!?]+', paragraph)
    if sentences:
        static_desc = sentences[0].strip()
        # Remove action verbs
        action_verbs = ['moves', 'walks', 'runs', 'pedals', 'rides', 'glances', 'checks', 'pours', 
                       'grabs', 'rushes', 'vibrates', 'displays', 'appears', 'glows', 'bursts',
                       'erupts', 'forms', 'emerges', 'transforms', 'changes', 'shifts', 'rises',
                       'begins', 'starts', 'hastily', 'quickly', 'dancing', 'brushing', 'pulling']
        
        for verb in action_verbs:
            static_desc = re.sub(rf'\b{verb}[a-z]*\b', '', static_desc, flags=re.IGNORECASE)
        
        static_desc = re.sub(r'\s+', ' ', static_desc).strip()
        if len(static_desc) > 80:
            static_desc = static_desc[:77] + "..."
        
        parts.append(f"Moment: {static_desc}")
    
    return " | ".join(parts)

def create_motion_prompt(paragraph: str, entities: Dict[str, List[str]], identity_block_metadata: Dict[str, Dict], identity_blocks: Dict[str, str]) -> str:
    """Create motion prompt (what CHANGES/happens)."""
    parts = []
    
    # Use the FULL paragraph as the base motion description
    motion_description = paragraph
    
    # Replace character names with identity block references
    if entities["characters"]:
        for char_id in entities["characters"]:
            if char_id in identity_block_metadata:
                char_name = identity_block_metadata[char_id].get("name", "")
                # Replace with identity reference (but keep it readable)
                motion_description = re.sub(
                    rf'\b{re.escape(char_name)}\b',
                    f"{char_name} ({char_id})",
                    motion_description,
                    flags=re.IGNORECASE
                )
    
    # Replace object names with identity block references
    for obj_id in entities["objects"]:
        if obj_id in identity_block_metadata:
            obj_name = identity_block_metadata[obj_id].get("name", "")
            # Replace with identity reference
            motion_description = re.sub(
                rf'\b{re.escape(obj_name)}\b',
                f"{obj_name} ({obj_id})",
                motion_description,
                flags=re.IGNORECASE
            )
    
    # Add the motion description (this is the PRIMARY content)
    parts.append(motion_description)
    
    # Add explicit object appearances/reveals (CRITICAL for logo reveals)
    para_lower = paragraph.lower()
    for obj_id in entities["objects"]:
        if obj_id in identity_block_metadata:
            obj_name = identity_block_metadata[obj_id].get("name", "")
            if any(word in para_lower for word in ['appears', 'reveals', 'displays', 'glows', 'visible', 'bursts', 'erupts', 'prominently']):
                if "OBJECT_5200" in obj_id:  # Acme Smart Watch
                    if 'logo' in para_lower or 'tagline' in para_lower:
                        parts.append(f"CRITICAL: {obj_name} ({obj_id}) logo and tagline appear/reveal on screen")
                    else:
                        parts.append(f"CRITICAL: {obj_name} ({obj_id}) appears prominently on wrist, screen glowing with data")
                else:
                    parts.append(f"{obj_name} ({obj_id}) appears/reveals in frame")
    
    # Camera movement based on content
    if any(word in para_lower for word in ['pedals', 'rides', 'bike', 'bicycle', 'cuts through']):
        parts.append("Camera: Slow tracking shot following bike movement, medium shot, eye level")
    elif any(word in para_lower for word in ['moves', 'walks', 'runs', 'strides', 'rushing', 'hastily', 'blur of motion']):
        parts.append("Camera: Medium shot tracking character movement")
    elif any(word in para_lower for word in ['pans', 'sweeps', 'moves across', 'hum', 'buzzes']):
        parts.append("Camera: Slow pan across scene, wide shot")
    elif any(word in para_lower for word in ['close-up', 'closeup', 'zooms', 'focuses']):
        parts.append("Camera: Close-up shot, static camera")
    else:
        parts.append("Camera: Medium shot, static camera")
    
    # Atmosphere
    parts.append("Atmospheric music: Upbeat, energetic music matching the scene's tone")
    
    # Join and clean up
    result = ". ".join(parts)
    # Remove excessive whitespace
    result = re.sub(r'\s+', ' ', result).strip()
    # Fix double periods
    result = re.sub(r'\.\.+', '.', result)
    # Ensure ends with single period
    if result and not result.endswith('.'):
        result += '.'
    return result

def create_storyboard_item_from_paragraph(
    paragraph: str,
    sequence_number: int,
    scene_id: str,
    environment_id: str,
    identity_block_ids: Dict[str, str],
    identity_blocks: Dict[str, str],
    identity_block_metadata: Dict[str, Dict],
    scene_title: str
) -> Dict[str, Any]:
    """Create a storyboard item from a paragraph."""
    
    # Extract entities
    entities = extract_entities_from_text(paragraph, identity_block_ids)
    
    # Determine duration (3-7 seconds based on content complexity)
    word_count = len(paragraph.split())
    if word_count > 120:
        duration = 7
    elif word_count > 80:
        duration = 5
    else:
        duration = 3
    
    # Determine scene type
    scene_type = determine_scene_type(paragraph)
    
    # Create storyline (concise summary)
    sentences = re.split(r'[.!?]+', paragraph)
    storyline_sentences = [s.strip() for s in sentences[:2] if s.strip()]
    storyline = '. '.join(storyline_sentences)
    if storyline and not storyline.endswith('.'):
        storyline += '.'
    if len(storyline) > 200:
        storyline = storyline[:197] + '...'
    
    # Extract dialogue
    dialogue = extract_dialogue(paragraph)
    
    # Create image prompt (static - state BEFORE action)
    image_prompt = create_image_prompt(paragraph, environment_id, identity_blocks, entities, identity_block_metadata)
    
    # Create motion prompt (dynamic - what CHANGES)
    prompt = create_motion_prompt(paragraph, entities, identity_block_metadata, identity_blocks)
    
    # Ensure prompt is comprehensive (100-150 words target)
    word_count_prompt = len(prompt.split())
    if word_count_prompt < 50:
        # Add more detail from paragraph if needed
        sentences = re.split(r'[.!?]+', paragraph)
        if len(sentences) > 2:
            additional_detail = '. '.join(sentences[2:4])
            prompt = f"{prompt} {additional_detail}"
    
    # Camera notes
    if 'tracking' in prompt.lower():
        camera_notes = "Tracking shot, medium shot, eye level angle"
    elif 'pan' in prompt.lower():
        camera_notes = "Slow pan, wide shot, eye level angle"
    elif 'close-up' in prompt.lower() or 'zoom' in prompt.lower():
        camera_notes = "Close-up shot, static camera"
    elif 'wide' in prompt.lower() or 'establishing' in prompt.lower():
        camera_notes = "Wide establishing shot, slow pan"
    else:
        camera_notes = "Medium shot, static camera"
    
    # Calculate render cost
    has_motion = any(verb in paragraph.lower() for verb in ['moves', 'walks', 'runs', 'pedals', 'rides', 'appears', 'reveals'])
    char_count = len(entities["characters"])
    
    render_cost = "easy"
    if char_count > 2 or word_count > 150:
        render_cost = "moderate"
    if word_count > 200 or char_count > 4:
        render_cost = "expensive"
    
    return {
        "item_id": str(uuid.uuid4()),
        "sequence_number": sequence_number,
        "duration": duration,
        "storyline": storyline,
        "image_prompt": image_prompt,
        "prompt": prompt,
        "visual_description": "",  # Empty, not "Reference field"
        "dialogue": dialogue,
        "scene_type": scene_type,
        "camera_notes": camera_notes,
        "render_cost": render_cost,
        "render_cost_factors": {
            "motion_complexity": 2 if has_motion else 0,
            "character_count": char_count,
            "environmental_chaos": 0,
            "camera_movement": 2 if 'tracking' in camera_notes.lower() or 'pan' in camera_notes.lower() else 0,
            "special_effects": 0
        },
        "identity_drift_warnings": [],
        "metadata": {},
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

def process_scene(
    scene: Dict[str, Any],
    identity_block_ids: Dict[str, str],
    identity_blocks: Dict[str, str],
    identity_block_metadata: Dict[str, Dict]
) -> Dict[str, Any]:
    """Process a scene and regenerate storyboard items from generated_content."""
    
    metadata = scene.get("metadata", {})
    generated_content = metadata.get("generated_content", "")
    
    # Check if generated_content is a summary (short, starts with scene title)
    is_summary = False
    if generated_content:
        # If it's very short (< 200 chars) or starts with scene title followed by colon, it's likely a summary
        if len(generated_content) < 200 or (scene.get("title", "") and generated_content.startswith(scene["title"] + ":")):
            is_summary = True
    
    if not generated_content or is_summary:
        # No full generated_content or it's a summary
        # Try to reconstruct from existing storyboard items or clean up existing items
        existing_items = scene.get("storyboard_items", [])
        if existing_items and len(existing_items) > 0:
            # Reconstruct paragraphs from existing storylines
            reconstructed_paragraphs = []
            current_para = []
            
            for item in existing_items:
                storyline = item.get("storyline", "")
                if storyline:
                    current_para.append(storyline)
                    # If storyline is substantial, treat as paragraph break
                    if len(storyline) > 100:
                        if current_para:
                            reconstructed_paragraphs.append(" ".join(current_para))
                            current_para = []
            
            if current_para:
                reconstructed_paragraphs.append(" ".join(current_para))
            
            if reconstructed_paragraphs:
                generated_content = "\n\n".join(reconstructed_paragraphs)
            else:
                # Just clean up existing items
                for item in existing_items:
                    if item.get("visual_description") == "Reference field":
                        item["visual_description"] = ""
                    if item.get("image_prompt", "").endswith("Reference field"):
                        item["image_prompt"] = item["image_prompt"].replace("Reference field", "").strip()
                    # Add identity block references to prompts
                    prompt = item.get("prompt", "")
                    if prompt and "CHARACTER_DDDC" not in prompt and "James" in prompt:
                        prompt = prompt.replace("James", "James (CHARACTER_DDDC)")
                        item["prompt"] = prompt
                return scene
        else:
            return scene
    
    # Split into paragraphs
    paragraphs = split_into_paragraphs(generated_content)
    
    if not paragraphs:
        return scene
    
    # Generate new storyboard items from paragraphs
    new_items = []
    sequence_number = 1
    
    environment_id = scene.get("environment_id", "")
    
    for paragraph in paragraphs:
        # Check if paragraph has multiple distinct beats (multiple sentences with different actions)
        sentences = re.split(r'[.!?]+', paragraph)
        word_count = len(paragraph.split())
        
        # If paragraph is very long or has many distinct actions, split it
        if len(sentences) > 5 or word_count > 150:
            # Split into 2-3 items
            num_splits = min(3, max(2, len(sentences) // 3))
            split_size = len(sentences) // num_splits
            
            for i in range(num_splits):
                start_idx = i * split_size
                end_idx = (i + 1) * split_size if i < num_splits - 1 else len(sentences)
                split_para = '. '.join([s.strip() for s in sentences[start_idx:end_idx] if s.strip()]) + '.'
                
                if split_para.strip() and len(split_para.strip()) > 20:
                    item = create_storyboard_item_from_paragraph(
                        split_para, sequence_number, scene["scene_id"],
                        environment_id, identity_block_ids, identity_blocks, 
                        identity_block_metadata, scene["title"]
                    )
                    new_items.append(item)
                    sequence_number += 1
        else:
            # Single item for paragraph
            item = create_storyboard_item_from_paragraph(
                paragraph, sequence_number, scene["scene_id"],
                environment_id, identity_block_ids, identity_blocks,
                identity_block_metadata, scene["title"]
            )
            new_items.append(item)
            sequence_number += 1
    
    # Replace storyboard items
    scene["storyboard_items"] = new_items
    scene["is_complete"] = len(new_items) > 0
    
    # Update estimated duration
    total_duration = sum(item["duration"] for item in new_items)
    scene["estimated_duration"] = total_duration
    
    # Replace generated_content with summary
    if paragraphs:
        summary = f"{scene['title']}: {paragraphs[0][:150]}..."
        scene["metadata"]["generated_content"] = summary
    
    return scene

def fix_json_file(input_file: str, output_file: str):
    """Fix the JSON file."""
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    identity_block_ids = data.get("identity_block_ids", {})
    identity_blocks = data.get("identity_blocks", {})
    identity_block_metadata = data.get("identity_block_metadata", {})
    
    # Process each act and scene
    if "acts" in data:
        for act in data["acts"]:
            if "scenes" in act:
                for scene in act["scenes"]:
                    scene = process_scene(scene, identity_block_ids, identity_blocks, identity_block_metadata)
    
    # Update updated_at timestamp
    data["updated_at"] = datetime.now().isoformat()
    
    # Save fixed JSON
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Fixed JSON saved to {output_file}")
    print(f"Processed {len(data.get('acts', []))} acts")

if __name__ == "__main__":
    fix_json_file("Empowering Every Moment.json", "Empowering Every Moment_fixed.json")
