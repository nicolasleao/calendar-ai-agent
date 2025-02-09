from typing import TypeVar, Type, Any, Optional, List, Dict, Union, Literal, Callable
from pydantic import BaseModel, Field
from openai import OpenAI, OpenAIError
from openai.types.chat import ChatCompletion, ChatCompletionMessageToolCall
from functools import wraps
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Type variable for Pydantic models
T = TypeVar('T', bound=BaseModel)

# Type for tool handler function
ToolHandler = Callable[[ChatCompletionMessageToolCall, Dict[str, Any]], Any]

class FunctionParameters(BaseModel):
    type: Literal["object"] = "object"
    properties: Dict[str, Dict[str, Any]]
    required: List[str]
    additionalProperties: bool = False

class Function(BaseModel):
    name: str
    description: str
    parameters: FunctionParameters
    strict: bool = True

class Tool(BaseModel):
    type: Literal["function"] = "function"
    function: Function

def handle_openai_errors(func):
    """Decorator to handle OpenAI API errors"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except OpenAIError as e:
            raise Exception(f"OpenAI API error: {str(e)}")
        except Exception as e:
            raise Exception(f"Unexpected error: {str(e)}")
    return wrapper

def _format_completion_response_json(completion: ChatCompletion) -> T:
    # Convert completion to a dictionary
    completion = completion.model_dump()

    # Calculate cost based on prompt and completion tokens used
    cost = (completion["usage"]["prompt_tokens"] * 0.001 + completion["usage"]["completion_tokens"] * 0.002) / 1000
    total_tokens = completion["usage"]["total_tokens"]

    # Format the response as a JSON string
    return json.dumps({
        "data": completion["choices"][0]["message"]["parsed"],
        "cost": cost,
        "total_tokens": total_tokens
    })

@handle_openai_errors
def structured_chat_completion(
    messages: list[dict[str, str]],
    output_model: Type[T],
    model: str = "gpt-4o",
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    top_p: float = 1.0,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    tools: Optional[List[Tool]] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    tool_handler: Optional[ToolHandler] = None,
    **kwargs: Any
) -> T:
    """
    Make a chat completion request to OpenAI and parse the response into a Pydantic model.
    Supports tool calls and their execution through a provided tool handler.
    """
    working_messages = messages.copy()
    completion_kwargs = {
        "model": model,
        "messages": working_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": top_p,
        "frequency_penalty": frequency_penalty,
        "presence_penalty": presence_penalty,
        **kwargs
    }

    # Add tools if provided
    if tools:
        if not tool_handler:
            raise ValueError("tool_handler is required when tools are provided")
        
        completion_kwargs["tools"] = [tool.model_dump() for tool in tools]
        if tool_choice:
            completion_kwargs["tool_choice"] = tool_choice
    
        # Call the OpenAI API to check if we need to run any tools
        response = client.chat.completions.create(**completion_kwargs)
        message = response.choices[0].message

        # Check if the model wants to call tools
        if message.tool_calls:
            # Append the model's message with tool calls
            working_messages.append(message.model_dump())

            # Execute each tool call and append results
            for tool_call in message.tool_calls:
                try:
                    print("executing tool", tool_call.function.name, "with args", tool_call.function.arguments)
                    args = json.loads(tool_call.function.arguments)
                    result = tool_handler(tool_call, args)
                    
                    working_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result)
                    })
                except Exception as e:
                    print(f"Error executing tool {tool_call.function.name}: {str(e)}")
                    working_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"Error: {str(e)}"
                    })
            # After all tools have been executed, call the model again with the new messages and passing the output format
            completion_kwargs["messages"] = working_messages
        
        # If no tools need to be called, or we have already executed them, call the model again passing the output format
        completion_kwargs["response_format"] = output_model
        response = client.beta.chat.completions.parse(**completion_kwargs)
        return _format_completion_response_json(response)

            
