"""
LLM utilities for PDF parser - simplified version from ppt-generator.

Provides Claude API integration for image description using vision capabilities.
"""

import json
import logging
import os
import re
import traceback
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import anthropic
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

logging.getLogger('tenacity').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)

# Load environment variables from .env file
load_dotenv()

CLAUDE_KEY = os.getenv("ANTHROPIC_API_KEY")


def get_caller_function() -> str:
    """Get the name of the calling function."""
    import inspect
    stack = inspect.stack()
    utility_functions = [
        'log_llm_message', 'llm_call', 'get_caller_function', '__call__', 'wrapped_f', '<module>',
        'claude_complete'
    ]
    
    for frame in stack:
        if frame.function not in utility_functions:
            return frame.function
    
    return "unknown_caller"


def log_llm_message(messages: List[Dict[str, Any]], response: str, invoker: str) -> None:
    """Log LLM messages and responses to a file."""
    filename = './llm_outputs.log'
    mode = 'a' if os.path.exists(filename) else 'w'
    
    def format_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "image":
                    parts.append("[IMAGE]")
            return "\n".join(parts)
        return str(content)
    
    def truncate_content(content: str) -> str:
        """Truncate to first 5 lines + ... + last 3 lines."""
        lines = content.split('\n')
        if len(lines) <= 8:
            return content
        return '\n'.join(lines[:5]) + '\n...\n' + '\n'.join(lines[-3:])
    
    def format_message(idx: int, m: dict) -> str | None:
        content = format_content(m['content'])
        is_last = idx == len(messages) - 1
        is_second_last = idx == len(messages) - 2
        
        # Skip last assistant if it duplicates response
        if is_last and m['role'] == 'assistant' and content.strip() == response.strip():
            return None
        
        # Full content for last 2 messages
        if is_last or is_second_last:
            return f"[[ {m['role']} ]]\n{content}\n"
        
        # Truncate all others (system + middle)
        return f"[[ {m['role']} ]]\n{truncate_content(content)}\n"
    
    formatted = [format_message(i, m) for i, m in enumerate(messages)]
    text = "\n".join([msg for msg in formatted if msg is not None])
    text = f"\n######################## {invoker} ########################\n{text}\n[[ response ]]\n{response}\n########################################################\n"
    
    with open(filename, mode, encoding='utf-8') as file:
        file.write(text)


class LLM(str, Enum):
    """Supported LLM models."""
    CLAUDE_4_5_SONNET = "claude-sonnet-4-5-20250929"
    CLAUDE_4_1_OPUS = "claude-opus-4-1-20250805"
    CLAUDE_4_5_OPUS = "claude-opus-4-5-20251101"
    CLAUDE_4_5_OPUS_THINKING = "claude-opus-4-5-20251101-thinking"


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, max=60))
def llm_call(
    system_prompt: str, 
    user_prompt: Union[str, List[Dict[str, Any]]], 
    model: LLM, 
    tag: Optional[str] = None, 
    temperature: float = 0,
    history: Optional[List[Dict[str, Any]]] = None
) -> Tuple[List[Dict[str, Any]], Any]:
    """
    Make an LLM API call with retry logic.
    
    Args:
        system_prompt: System prompt text
        user_prompt: User prompt (text or list of content blocks for vision)
        model: LLM model to use
        tag: Optional XML tag to extract from response
        temperature: Temperature for generation
        history: Optional existing message history to append to (for multi-turn conversations)
        
    Returns:
        Tuple of (messages, response)
    """
    if history is not None:
        # Continue existing conversation - append new user message
        messages = history.copy()
        messages.append(user_message(user_prompt))
    else:
        # Start fresh conversation
        messages = [
            system_message(system_prompt),
            user_message(user_prompt)
        ]
    
    chat_messages, system = gpt_messages_2_claude3(messages)
    response = claude_complete(chat_messages, system, model, temperature=temperature)
    
    messages.append(assistant_message(response))
    
    # Log the LLM interaction
    log_llm_message(messages, response, get_caller_function())

    if tag is not None:
        response = extract_tag_content(tag, response or "")

    return messages, response


def claude_complete(
    messages: List, 
    system: Optional[str] = None, 
    model: LLM = LLM.CLAUDE_4_5_SONNET, 
    max_tokens: int = 16000, 
    temperature: float = 0
) -> str:
    """
    Generate response through Claude API.
    
    Args:
        messages: List of message dictionaries
        system: System prompt text
        model: Claude model to use
        max_tokens: Maximum tokens in response
        temperature: Temperature for generation
        
    Returns:
        Response text from Claude
    """
    # Check if this is a thinking model
    think = False
    model_name: str
    if model.value.endswith("-thinking"):
        model_name = model.value.rstrip("-thinking")
        think = True
    else:
        model_name = model.value
    
    try:
        client = anthropic.Anthropic(api_key=CLAUDE_KEY, timeout=1200.0)
        
        if think:
            completion = client.messages.create(
                model=model_name,
                max_tokens=60000,
                messages=messages,
                temperature=1,
                stream=False,
                thinking={
                    "type": "enabled",
                    "budget_tokens": 16000
                },
                **({"system": system} if system else {})
            )
            # Return the text content (not the thinking)
            return str(completion.content[1].text)
        else:
            completion = client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                messages=messages,
                temperature=temperature,
                stream=False,
                **({"system": system} if system else {})
            )
            return str(completion.content[0].text)
        
    except Exception as e:
        logger.error(f"Error from Claude API: {e}\n{traceback.format_exc()}")
        raise e


def gpt_messages_2_claude3(messages: List[Dict]) -> Tuple[List[Dict], str]:
    """
    Convert GPT-style messages to Claude format.
    
    Args:
        messages: List of message dictionaries with 'role' and 'content'
        
    Returns:
        Tuple of (chat_messages, system_prompt)
    """
    system = ""
    history = []
    
    for message in messages:
        if message["role"] == "system":
            system = message["content"]
        else:
            if "name" in message:
                del message["name"]
            history.append(message)
            
    return history, system


def system_message(prompt: str, *args: Any, **kwargs: Any) -> Dict[str, str]:
    """Create a system message."""
    return {
        "role": "system",
        "content": prompt
    }


def assistant_message(prompt: str, *args: Any, **kwargs: Any) -> Dict[str, str]:
    """Create an assistant message."""
    if kwargs:
        prompt = prompt.format(**kwargs)
    return {
        "role": "assistant",
        "content": prompt
    }


def user_message(prompt: Union[str, List[Dict[str, Any]]], *args: Any, **kwargs: Any) -> Dict[str, Any]:
    """
    Create a user message.
    
    Args:
        prompt: Text string or list of content blocks (for vision API)
        
    Returns:
        User message dictionary
    """
    if isinstance(prompt, str):
        if kwargs:
            prompt = prompt.format(**kwargs)
        return {"role": "user", "content": prompt}
    return {"role": "user", "content": prompt}


def extract_tag_content(tag_name: str, text: str) -> Optional[str]:
    """
    Extract content from XML tags in response.
    
    Args:
        tag_name: Name of XML tag to extract
        text: Text containing XML tags
        
    Returns:
        Extracted content or None if not found
    """
    pattern = f"<{tag_name}[^>]*>(.*?)</{tag_name}>"
    match = re.search(pattern, text, re.DOTALL)
    
    if match:
        return match.group(1).strip()
    else:
        logger.warning(f"No tag '{tag_name}' found in response")
        return None


