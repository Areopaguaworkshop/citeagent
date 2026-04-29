import dspy
import logging
from typing import Dict, Optional


def get_llm_model(model_name: str = "ollama/qwen3", temperature: float = 0.1) -> dspy.LM:
    """
    Get a configured LLM model based on the model name.
    
    Args:
        model_name: Model name in format "provider/model" 
                   Examples: 
                   - "ollama/qwen3", "ollama/llama3", "ollama/mixtral"
                   - "gemini/gemini-1.5-flash", "gemini/gemini-2.0-flash-exp", "gemini/gemini-2.5-flash"
                   - Any valid Gemini model name supported by Google AI
        temperature: Temperature for the model (default: 0.1 for more deterministic outputs)
    
    Returns:
        Configured dspy.LM instance
    """
    if model_name.startswith("gemini/"):
        # Extract the actual model name (e.g., "gemini-1.5-flash" from "gemini/gemini-1.5-flash")
        actual_model = model_name.split("/", 1)[1]
        logging.info(f"Using Gemini model: {actual_model} with temperature: {temperature}")
        # Use the full model name with gemini/ prefix for proper provider detection
        return dspy.LM(
            model=f"gemini/{actual_model}",
            model_kwargs={"temperature": temperature}
        )
    
    elif model_name.startswith("ollama/"):
        # Keep the full model name with ollama/ prefix for LiteLLM compatibility
        logging.info(f"Using Ollama model: {model_name} with temperature: {temperature}")
        return dspy.LM(
            model=model_name, 
            base_url="http://localhost:11434",
            model_kwargs={"temperature": temperature}
        )
    
    else:
        # Default to Ollama for backward compatibility
        logging.warning(f"Unknown model format: {model_name}, defaulting to Ollama")
        return dspy.LM(
            model=model_name, 
            base_url="http://localhost:11434",
            model_kwargs={"temperature": temperature}
        )


def get_provider_info() -> Dict[str, str]:
    """
    Get information about supported providers and their URL formats.
    
    Returns:
        Dictionary mapping provider names to their descriptions
    """
    return {
        "ollama": "Local Ollama models (format: ollama/model-name)",
        "gemini": "Google Gemini models (format: gemini/model-name)",
    }
