from abc import ABC
from typing import Optional
from llmstudio_core.providers.provider import BaseProvider, provider_registry

from llmstudio_core.providers import _load_engine_config

_engine_config = _load_engine_config()


def LLM(provider: str, api_key: Optional[str] = None) -> BaseProvider:
    """
    Factory method to create an instance of a provider.

    Args:
        provider (str): The name of the provider.
        api_key (Optional[str], optional): The API key for the provider. Defaults to None.

    Returns:
        BaseProvider: An instance of the provider.

    Raises:
        NotImplementedError: If the provider is not found in the provider map.
    """
    provider_config = _engine_config.providers.get(provider)
    provider_class = provider_registry.get(provider_config.id)
    if provider_class:
        return provider_class(config=provider_config, api_key=api_key)
    raise NotImplementedError(f"BaseProvider not found: {provider_config.id}. Available providers: {str(provider_registry.keys())}")


if __name__ == "__main__":
    from pprint import pprint
    import os
    from dotenv import load_dotenv
    load_dotenv()
    chat_request = {
        "chat_input": "Hello, my name is Json",
        "model": "gpt-3.5-turbo",
        "is_stream": False,
        "retries": 0,
        "parameters": {
            "temperature": 0,
            "max_tokens": 100,
            "response_format": {"type": "json_object"},
            "functions": None,
        }
    }

    provider = "openai"

    llm = LLM(provider=provider, api_key=os.environ["OPENAI_API_KEY"])
    
    import asyncio
    response_async = asyncio.run(llm.achat(chat_request))
    pprint(response_async)

    # stream
    print("\nasync stream")
    async def async_stream():
        chat_request = {
            "chat_input": "Hello, my name is Json",
            "model": "gpt-3.5-turbo",
            "is_stream": True,
            "retries": 0,
            "parameters": {
                "temperature": 0,
                "max_tokens": 100,
                "response_format": {"type": "json_object"},
                "functions": None,
            }
        }

        provider = "openai"
        llm = LLM(provider=provider, api_key=os.environ["OPENAI_API_KEY"])
        
        response_async = await llm.achat(chat_request)
        async for p in response_async:
            pprint(p.chat_output)
            pprint(p.choices[0].delta.content==p.chat_output)
            print("metrics: ",p.metrics)
            if p.metrics:
                pprint(p)
    asyncio.run(async_stream())
    
    
    print("# Now sync calls")
    chat_request = {
        "chat_input": "Hello, my name is Json",
        "model": "gpt-3.5-turbo",
        "is_stream": False,
        "retries": 0,
        "parameters": {
            "temperature": 0,
            "max_tokens": 100,
            "response_format": {"type": "json_object"},
            "functions": None,
        }
    }

    provider = "openai"

    llm = LLM(provider=provider, api_key=os.environ["OPENAI_API_KEY"])
    
    response_sync = llm.chat(chat_request)
    pprint(response_sync)

    print("# Now sync calls streaming")
    chat_request = {
        "chat_input": "Hello, my name is Json",
        "model": "gpt-3.5-turbo",
        "is_stream": True,
        "retries": 0,
        "parameters": {
            "temperature": 0,
            "max_tokens": 100,
            "response_format": {"type": "json_object"},
            "functions": None,
        }
    }

    provider = "openai"

    llm = LLM(provider=provider, api_key=os.environ["OPENAI_API_KEY"])
    
    response_sync_stream = llm.chat(chat_request)
    for p in response_sync_stream:
        pprint(p.chat_output)
        pprint(p.choices[0].delta.content==p.chat_output)
        print("metrics: ",p.metrics)
        if p.metrics:
            pprint(p)
