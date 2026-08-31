"""Create instance of SDK's Anthropic model provider (direct API, no AWS/Bedrock)."""

from strands.models import Model
from strands.models.anthropic import AnthropicModel
from typing_extensions import Unpack


def instance(**model_config: Unpack[AnthropicModel.AnthropicConfig]) -> Model:
    """Create instance of SDK's Anthropic model provider.

    Args:
        **model_config: Configuration options for the Anthropic model
            (e.g., model_id, max_tokens, params).

    Returns:
        Anthropic model provider.
    """
    return AnthropicModel(**model_config)
