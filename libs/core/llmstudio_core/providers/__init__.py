import os
import yaml
# from llmstudio_core.providers.anthropic import AnthropicProvider #TODO: adpat it
from llmstudio_core.providers.azure import AzureProvider
# from llmstudio_core.providers.ollama import OllamaProvider #TODO: adapt it
from llmstudio_core.providers.openai import OpenAIProvider
from llmstudio_core.providers.vertexai import VertexAIProvider

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ValidationError


class CostRange(BaseModel):
    range: List[Optional[int]]
    cost: float


class ModelConfig(BaseModel):
    mode: str
    max_tokens: int
    input_token_cost: Union[float, List[CostRange]]
    output_token_cost: Union[float, List[CostRange]]


class ProviderConfig(BaseModel):
    id: str
    name: str
    chat: bool
    embed: bool
    keys: Optional[List[str]] = None
    models: Optional[Dict[str, ModelConfig]] = None
    parameters: Optional[Dict[str, Any]] = None


class EngineConfig(BaseModel):
    providers: Dict[str, ProviderConfig]


def _load_engine_config() -> EngineConfig:
    #TODO read from github
    default_config_path = Path(os.path.join(os.path.dirname(__file__), "config.yaml"))
    local_config_path = Path(os.getcwd(), "config.yaml")

    def _merge_configs(config1, config2):
        for key in config2:
            if key in config1:
                if isinstance(config1[key], dict) and isinstance(config2[key], dict):
                    _merge_configs(config1[key], config2[key])
                elif isinstance(config1[key], list) and isinstance(config2[key], list):
                    config1[key].extend(config2[key])
                else:
                    config1[key] = config2[key]
            else:
                config1[key] = config2[key]
        return config1

    try:
        default_config_data = yaml.safe_load(default_config_path.read_text())
        local_config_data = (
            yaml.safe_load(local_config_path.read_text())
            if local_config_path.exists()
            else {}
        )
        config_data = _merge_configs(default_config_data, local_config_data)
        return EngineConfig(**config_data)
    except yaml.YAMLError as e:
        raise RuntimeError(f"Error parsing YAML configuration: {e}")
    except ValidationError as e:
        raise RuntimeError(f"Error in configuration data: {e}")
