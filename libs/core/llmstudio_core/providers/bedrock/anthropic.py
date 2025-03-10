import json
import os
import time
import uuid
from typing import (
    Any,
    AsyncGenerator,
    Coroutine,
    Dict,
    Generator,
    List,
    Optional,
    Union,
)

import boto3
from llmstudio_core.exceptions import ProviderError
from llmstudio_core.providers.provider import ChatRequest, ProviderCore, provider
from llmstudio_core.utils import OpenAIToolFunction
from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import (
    Choice,
    ChoiceDelta,
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)
from pydantic import ValidationError

SERVICE = "bedrock-runtime"


@provider
class BedrockAnthropicProvider(ProviderCore):
    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self._client = boto3.client(
            SERVICE,
            region_name=self.region if self.region else os.getenv("BEDROCK_REGION"),
            aws_access_key_id=self.access_key
            if self.access_key
            else os.getenv("BEDROCK_ACCESS_KEY"),
            aws_secret_access_key=self.secret_key
            if self.secret_key
            else os.getenv("BEDROCK_SECRET_KEY"),
        )

    @staticmethod
    def _provider_config_name():
        return "bedrock-antropic"

    def validate_request(self, request: ChatRequest):
        return ChatRequest(**request)

    async def agenerate_client(self, request: ChatRequest) -> Coroutine[Any, Any, Any]:
        """Generate an AWS Bedrock client"""
        return self.generate_client(request=request)

    def generate_client(self, request: ChatRequest) -> Coroutine[Any, Any, Generator]:
        """Generate an AWS Bedrock client"""
        try:
            messages, system_prompt = self._process_messages(request.chat_input)
            tools = self._process_tools(request.parameters)

            system_prompt = (
                request.parameters.get("system")
                if request.parameters.get("system")
                else system_prompt
            )

            client_params = {
                "modelId": request.model,
                "messages": messages,
                "inferenceConfig": self._process_parameters(request.parameters),
                "system": system_prompt,
            }
            if tools:
                client_params["toolConfig"] = tools

            return self._client.converse_stream(**client_params)
        except Exception as e:
            raise ProviderError(str(e))

    async def aparse_response(
        self, response: Any, **kwargs
    ) -> AsyncGenerator[Any, None]:
        return self.parse_response(response=response, **kwargs)

    def parse_response(self, response: AsyncGenerator[Any, None], **kwargs) -> Any:
        tool_name = None
        tool_arguments = ""
        tool_id = None

        for chunk in response["stream"]:
            if chunk.get("messageStart"):
                first_chunk = ChatCompletionChunk(
                    id=str(uuid.uuid4()),
                    choices=[
                        Choice(
                            delta=ChoiceDelta(
                                content=None,
                                function_call=None,
                                role="assistant",
                                tool_calls=None,
                            ),
                            index=0,
                        )
                    ],
                    created=int(time.time()),
                    model=kwargs.get("request").model,
                    object="chat.completion.chunk",
                    usage=None,
                )
                yield first_chunk.model_dump()

            elif chunk.get("contentBlockStart"):
                if chunk["contentBlockStart"]["start"].get("toolUse"):
                    tool_name = chunk["contentBlockStart"]["start"]["toolUse"]["name"]
                    tool_arguments = ""
                    tool_id = chunk["contentBlockStart"]["start"]["toolUse"][
                        "toolUseId"
                    ]

            elif chunk.get("contentBlockDelta"):
                delta = chunk["contentBlockDelta"]["delta"]
                if delta.get("text"):
                    # Regular content, yield it
                    text = delta["text"]
                    chunk = ChatCompletionChunk(
                        id=str(uuid.uuid4()),
                        choices=[
                            Choice(
                                delta=ChoiceDelta(content=text),
                                finish_reason=None,
                                index=0,
                            )
                        ],
                        created=int(time.time()),
                        model=kwargs.get("request").model,
                        object="chat.completion.chunk",
                    )
                    yield chunk.model_dump()

                elif delta.get("toolUse"):
                    partial_json = delta["toolUse"]["input"]
                    tool_arguments += partial_json

            elif chunk.get("contentBlockStop") and tool_id:
                name_chunk = ChatCompletionChunk(
                    id=str(uuid.uuid4()),
                    choices=[
                        Choice(
                            delta=ChoiceDelta(
                                role="assistant",
                                tool_calls=[
                                    ChoiceDeltaToolCall(
                                        index=chunk["contentBlockStop"][
                                            "contentBlockIndex"
                                        ],
                                        id=tool_id,
                                        function=ChoiceDeltaToolCallFunction(
                                            name=tool_name,
                                            arguments="",
                                            type="function",
                                        ),
                                    )
                                ],
                            ),
                            finish_reason=None,
                            index=chunk["contentBlockStop"]["contentBlockIndex"],
                        )
                    ],
                    created=int(time.time()),
                    model=kwargs.get("request").model,
                    object="chat.completion.chunk",
                )
                yield name_chunk.model_dump()

                args_chunk = ChatCompletionChunk(
                    id=tool_id,
                    choices=[
                        Choice(
                            delta=ChoiceDelta(
                                tool_calls=[
                                    ChoiceDeltaToolCall(
                                        index=chunk["contentBlockStop"][
                                            "contentBlockIndex"
                                        ],
                                        function=ChoiceDeltaToolCallFunction(
                                            arguments=tool_arguments,
                                        ),
                                    )
                                ],
                            ),
                            finish_reason=None,
                            index=chunk["contentBlockStop"]["contentBlockIndex"],
                        )
                    ],
                    created=int(time.time()),
                    model=kwargs.get("request").model,
                    object="chat.completion.chunk",
                )
                yield args_chunk.model_dump()

            elif chunk.get("messageStop"):
                stop_reason = chunk["messageStop"].get("stopReason")
                final_chunk = ChatCompletionChunk(
                    id=str(uuid.uuid4()),
                    choices=[
                        Choice(
                            delta=ChoiceDelta(),
                            finish_reason="tool_calls"
                            if stop_reason == "tool_use"
                            else "length"
                            if stop_reason == "max_tokens"
                            else "stop",
                            index=0,
                        )
                    ],
                    created=int(time.time()),
                    model=kwargs.get("request").model,
                    object="chat.completion.chunk",
                )
                yield final_chunk.model_dump()

    @staticmethod
    def _process_messages(
        chat_input: Union[str, List[Dict[str, str]]]
    ) -> List[Dict[str, Union[List[Dict[str, str]], str]]]:

        if isinstance(chat_input, str):
            return [
                {
                    "role": "user",
                    "content": [{"text": chat_input}],
                }
            ], []

        elif isinstance(chat_input, list):
            messages = []
            next_tool_result_message = False
            system_prompt = []
            for message in chat_input:
                if message.get("role") in ["assistant", "user"]:
                    next_tool_result_message = False
                    if message.get("tool_calls"):
                        tool_use = {"role": "assistant", "content": []}
                        for tool in message.get("tool_calls"):
                            tool_use["content"].append(
                                {
                                    "toolUse": {
                                        "toolUseId": tool["id"],
                                        "name": tool["function"]["name"],
                                        "input": json.loads(
                                            tool["function"]["arguments"]
                                        ),
                                    }
                                }
                            )
                        messages.append(tool_use)
                    else:
                        messages.append(
                            {
                                "role": message.get("role"),
                                "content": [{"text": message.get("content")}],
                            }
                        )
                if message.get("role") in ["tool"]:
                    if not next_tool_result_message:
                        tool_result = {"role": "user", "content": []}
                        next_tool_result_message = True
                        messages.append(tool_result)

                    tool_result = {
                        "toolResult": {
                            "toolUseId": message["tool_call_id"],
                            "content": [{"json": {"text": message["content"]}}],
                        }
                    }

                    messages[-1]["content"].append(tool_result)

                if message.get("role") in ["system"]:
                    system_prompt = [{"text": message.get("content")}]

            return messages, system_prompt

    @staticmethod
    def _process_tools(parameters: dict) -> Optional[Dict]:
        if parameters.get("tools") is None and parameters.get("functions") is None:
            return None

        try:
            if parameters.get("tools"):
                parsed_tools = [
                    OpenAIToolFunction(**tool["function"])
                    for tool in parameters["tools"]
                ]

            if parameters.get("functions"):
                parsed_tools = [
                    OpenAIToolFunction(**tool) for tool in parameters["functions"]
                ]

            tool_configurations = []
            for tool in parsed_tools:
                tool_config = {
                    "toolSpec": {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": {
                            "json": {
                                "type": tool.parameters.type,
                                "properties": tool.parameters.properties,
                                "required": tool.parameters.required,
                            }
                        },
                    }
                }
                tool_configurations.append(tool_config)
            return {"tools": tool_configurations}

        except ValidationError:
            return parameters.get("tools", parameters.get("functions"))

    @staticmethod
    def _process_parameters(parameters: dict) -> dict:
        remove_keys = ["system", "stop", "tools", "functions"]
        for key in remove_keys:
            parameters.pop(key, None)
        return parameters
