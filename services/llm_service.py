import os
import re
import time
import config
from services.story_pools import (
    PLOT_ARCHETYPES, SURPRISE_TWISTS, NARRATIVE_STYLES, 
    SUB_GENRES, PLOT_SPARKS, ATMOSPHERES
)
from services.storage import update_story_task
from services.story_builder import build_character_descriptions

ERROR_LOG_PATH = "data/last_ai_error.txt"

def _set_last_error(msg: str):
    """Persist error message to disk for cross-worker visibility."""
    try:
        os.makedirs("data", exist_ok=True)
        with open(ERROR_LOG_PATH, "w") as f:
            f.write(msg)
    except Exception as e:
        print(f"[ERROR_LOG_FAIL] {e}")

def get_last_error():
    """Retrieve the persisted error message."""
    try:
        if os.path.exists(ERROR_LOG_PATH):
            with open(ERROR_LOG_PATH, "r") as f:
                return f.read().strip()
    except Exception as e:
        print(f"[ERROR_READ_FAIL] {e}")
    return None


def generate_story(prompt: str, params: dict, max_tokens: int = 3000) -> str:
    """
    Generate a story using the configured Google Gemini model.
    """
    if not config.GEMINI_API_KEY:
        print("[LLM] CRITICAL ERROR: GOOGLE_API_KEY is missing. Story generation aborted.")
        return None

    try:
        result = _call_gemini_api(config.GEMINI_MODEL_STANDARD, prompt, max_tokens)
        if result:
            return result
    except Exception as e:
        print(f"[LLM] Gemini fatal error: {e}")

    return None


def count_words(text: str) -> int:
    """Accurately count words in a story string."""
    if not text:
        return 0
    import re
    # Remove headers and scene tags to count only narrative words
    clean_text = re.sub(r'##\s*.*?\n|\[SCENE:.*?\]', '', text, flags=re.DOTALL)
    return len(clean_text.split())


def generate_story_8act(params: dict, task_id: str = None) -> str:
    """
    The 8-Act Narrative Engine with automatic retries and engine resilience.
    Now supports task_id for live progress updates.
    """
    from services.story_builder import build_8act_prompts, set_seeds
    
    seeds = set_seeds(params)
    full_story = ""
    
    act_titles = [
        "ACT_1: Setting the Scene",
        "ACT_2: Character Depth",
        "ACT_3: The Inciting Incident",
        "ACT_4: Rising Action",
        "ACT_5: The Complication",
        "ACT_6: The Climax",
        "ACT_7: The Resolution",
        "ACT_8: THE_MANDATORY_POEM"
    ]

    import uuid
    story_seed = uuid.uuid4().hex[:8] 

    for i in range(1, 9):
        print(f"[LLM] Generating {act_titles[i-1]} (Act {i}/8) using {config.TEXT_GEN_ENGINE}...")
        
        # Continuity context
        context = full_story[-2000:] if full_story else None
        prompt = build_8act_prompts(params, act_number=i, previous_content=context, seeds=seeds)
        prompt = f"[UNIQUE_STORY_SEED: {story_seed}]\n{prompt}"

        act_text = None
        attempts = 0
        max_attempts = 2 
        
        while not act_text and attempts < max_attempts:
            if task_id:
                progress = 5 + int((i / 8) * 75)
                update_story_task(task_id, status="generating", status_message=f"Writing Act {i}: {act_titles[i-1]}...", progress_pct=progress)
            
            if attempts > 0:
                print(f"  -> Retry attempt {attempts} for {act_titles[i-1]}...")
                
            # DEFAULT TO PRO for Act 8, but FALLBACK to Flash if it fails
            model_to_use = config.GEMINI_MODEL_PRO if (i == 8 and attempts == 0) else config.GEMINI_MODEL_STANDARD
            act_text = _call_gemini_api(model_to_use, prompt, max_tokens=800, task_id=task_id)
            
            attempts += 1
        
        if not act_text:
            print(f"[LLM] Gemini failed for Act {i}. Attempting Hugging Face Tertiary Fallback...")
            if task_id:
                update_story_task(task_id, status="generating", status_message=f"Gemini exhausted. Using Hugging Face for Act {i}...")
            act_text = _call_hf_api(prompt, max_tokens=800)
            
        if not act_text:
            error_msg = f"Act {i} ({act_titles[i-1]}) failed on all AI engines."
            print(f"  -> {error_msg} Returning overall fallback.")
            # We DON'T overwrite if persistence already has a specific API error
            existing_error = get_last_error()
            if not existing_error or "ENGINE_FAILURE" in existing_error:
                _set_last_error(f"ENGINE_FAILURE: {error_msg}")
            
            # Enforce Absolute Originality: If AI fails, the generation FAILS. No static templates.
            return None
        
        full_story += f"[[{act_titles[i-1]}]]\n{act_text}\n\n"
        print(f"  -> {act_titles[i-1]} completed.")
        
        # Proactive Free-tier rate limit padding
        time.sleep(4)

    return full_story


def expand_content(text: str, params: dict, section_type: str, seeds: dict) -> str:
    """Instruct the AI to lengthen existing content with sensory detail."""
    current_count = count_words(text)
    print(f"[EXPAND] Expanding {section_type} (Current: {current_count} words)...")
    
    expansion_prompt = f"""You are a master of DESCRIPTIVE EXPANSION.
    The following {section_type} of our story is only {current_count} words long. Rewrite the following text but make it TWICE AS LONG (at least 500 words).
    
    RULES:
    - Include 3 new paragraphs of SENSORY details (smell, feel, sound).
    - Add deep INTERNAL MONOLOGUE for the characters.
    - KEEP THE PLOT THE SAME. Just ELABORATE.
    
    ORIGINAL TEXT:
    {text}
    """
    
    expanded_text = generate_story(expansion_prompt, params, max_tokens=1500)
    return expanded_text if count_words(expanded_text) > current_count else text


def _discovery_gemini_models(api_key: str) -> list:
    """Query Google for all available models on this key."""
    import requests
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return [m.get("name", "unknown") for m in data.get("models", [])]
    except Exception as e:
        print(f"[DISCOVERY_FAIL] {e}")
    return []


def _call_gemini_api(model_name: str, prompt: str, max_tokens: int, task_id: str = None) -> str | None:
    """
    ULTIMATE RELIABILITY: Make a direct REST API call to Gemini.
    With Auto-Healing and Quota Resilience.
    """
    import requests
    import json
    
    api_key = config.get_gemini_key()
    if not api_key:
        _set_last_error("GEMINI_API_KEY is missing.")
        return None
        
    # Start with standard aliases
    model_aliases = [model_name]
    if "-latest" not in model_name:
        model_aliases.append(f"{model_name}-latest")
        
    # AUTO-HEALING: If we previously discovered models, prioritize them
    discovery_log = get_last_error()
    if discovery_log and "Model Discovery Found:" in discovery_log:
        discovered_str = discovery_log.split("Model Discovery Found:")[1].strip()
        discovered_list = [m.strip() for m in discovered_str.split(",")]
        # Prioritize these as they are proven to exist on this account
        for d_model in discovered_list:
            if d_model not in model_aliases:
                model_aliases.append(d_model)
    
    # Try multiple API versions and aliases
    for api_version in ["v1beta", "v1", "v1alpha"]:
        for m_alias in model_aliases:
            # NORMALIZATION: Ensure model starts with 'models/' and handle full paths correctly
            if m_alias.startswith("models/"):
                model_path = m_alias
            else:
                model_path = f"models/{m_alias}"
                
            url = f"https://generativelanguage.googleapis.com/{api_version}/{model_path}:generateContent?key={api_key}"
            
            system_instruction = "You are a master storyteller for children, writing in the whimsical style of C.S. Lewis. Your stories are segmented into 8 acts. IMPORTANT: Act 8 MUST conclude with a 4-8 line RHYMING POEM."
            
            payload = {
                "contents": [{"role": "user", "parts": [{"text": f"INSTRUCTIONS: {system_instruction}\n\nREQUEST: {prompt}"}]}],
                "generationConfig": {"temperature": 1.0, "maxOutputTokens": max_tokens},
                "safetySettings": [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
                ]
            }
            
            try:
                print(f"[LLM] Trying {api_version} with {model_path}...")
                
                # Internal retry for 429 Quota issues
                max_429_retries = 2
                for retry_attempt in range(max_429_retries):
                    response = requests.post(url, json=payload, timeout=30)
                    
                    if response.status_code == 200:
                        res_data = response.json()
                        if "candidates" in res_data and res_data["candidates"]:
                            candidate = res_data["candidates"][0]
                            if "content" in candidate and "parts" in candidate["content"]:
                                text = candidate["content"]["parts"][0]["text"].strip()
                                print(f"[LLM] Success with {model_path} on {api_version}")
                                return text
                        
                        reason = res_data.get("candidates", [{}])[0].get("finishReason", "UNKNOWN")
                        _set_last_error(f"Gemini Blocked ({model_path}): {reason}")
                        break # Not a quota issue, break internal retry
                    
                    elif response.status_code == 429:
                        res_text = response.text
                        if "limit: 0" in res_text:
                            print(f"[LLM] Model {model_path} is disabled (limit: 0). Skipping...")
                            _set_last_error(f"MODEL_DISABLED: {model_path}")
                            break # Go to next alias/version
                            
                        if retry_attempt == max_429_retries - 1:
                            print(f"[LLM] Hard Quota block on {model_path}")
                            _set_last_error(f"HARD_QUOTA_REACHED: {model_path}")
                            return None # Hard stop for this request
                            
                        msg_prefix = f"Waiting for Quota... "
                        wait_seconds = 10.0
                        
                        print(f"[LLM] 429 Quota Exceeded on {model_path}. {msg_prefix} {wait_seconds}s")
                        _set_last_error(f"QUOTA_WAITING ({wait_seconds}s): {model_path}")
                        
                        # Interactive countdown for better UX
                        start_wait = int(wait_seconds)
                        for remaining in range(start_wait, 0, -1):
                            if task_id:
                                update_story_task(task_id, status="waiting_for_quota", 
                                                 status_message=f"{msg_prefix} {remaining}s")
                            time.sleep(1)
                        
                        if task_id:
                            update_story_task(task_id, status="generating", status_message="Quota cleared! Resuming...")
                        
                        continue # Loop and try the exact same model again
                    
                    else:
                        err_msg = f"API Error ({response.status_code}) on {api_version}/{model_path}: {response.text[:500]}"
                        print(f"[LLM] {err_msg}")
                        # Record and continue to next alias/version
                        _set_last_error(err_msg)
                        if response.status_code in [401, 403]: return None
                        break # Go to next alias/version
                        
            except Exception as e:
                _set_last_error(f"Network Exception: {str(e)}")
                return None
        
    # Final Fallback to Discovery if all attempts failed
    print("[LLM] All attempts failed. Refreshing Discovery...")
    available_models = _discovery_gemini_models(api_key)
    if available_models:
        model_list_str = ", ".join(available_models)
        _set_last_error(f"Model Discovery Found: {model_list_str}")
    
    return None


def _call_hf_api(prompt: str, max_tokens: int) -> str | None:
    """Tertiary fallback using robust Hugging Face REST logic to prevent version mismatches."""
    import requests
    import config
    
    api_key = config.HF_API_KEY
    if not api_key:
        _set_last_error("HF_TOKEN missing for text fallback.")
        return None
        
    try:
        model = config.HF_TEXT_MODEL
        url = "https://router.huggingface.co/hf-inference/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        
        system_instruction = "You are a master storyteller. Your task is to write a vividly descriptive creative story segment. IMPORTANT: If this is Act 8, you MUST end the response with a 4-8 line RHYMING POEM."
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.8
        }
        
        print(f"[LLM] Calling HF API ({model})...")
        response = requests.post(url, headers=headers, json=payload, timeout=40)
        
        if response.status_code == 200:
            res_data = response.json()
            if "choices" in res_data and res_data["choices"]:
                text = res_data["choices"][0]["message"]["content"].strip()
                print(f"[LLM] Success with HF {model}")
                return text
        else:
            err = f"HF Fallback Error ({response.status_code}): {response.text[:200]}"
            print(f"[LLM] {err}")
            _set_last_error(err)
            
    except Exception as e:
        err = f"HF Network Error: {str(e)}"
        print(f"[LLM] {err}")
        _set_last_error(err)
        
    return None

# Initialization check
if not os.path.exists(ERROR_LOG_PATH):
    _set_last_error("ENGINE_INITIALIZED (No errors yet)")



