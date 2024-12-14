from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, ClassVar

import httpx
from rich import print
import json

from xiaogpt.bot.base_bot import BaseBot
from jarvis.memory.memory import Memory, BotType

@dataclasses.dataclass
class SiliconFlowBot(BaseBot):
    name: ClassVar[str] = "SiliconFlow"
    default_options: ClassVar[dict[str, str | float | int]] = {
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "max_tokens": 1024,
        "temperature": 0.7,
        "top_p": 0.7,
        "top_k": 50,
        "frequency_penalty": 0.5,
        "n": 1,
        "stream": False,
    }
    
    api_key: str
    api_base: str = "https://api.siliconflow.cn/v1/chat/completions"
    proxy: str | None = None
    memory: Memory = dataclasses.field(default_factory=Memory)

    @classmethod
    def from_config(cls, config):
        return cls(
            api_key=config.siliconflow_key,
            proxy=config.proxy,
        )

    async def ask(self, query, **options):
        ms = self.get_messages()
        ms.append({"role": "user", "content": f"{query}"})
        
        kwargs = {**self.default_options, **options}
        payload = {
            "model": kwargs.get("model"),
            "messages": ms,
            "stream": kwargs.get("stream", False),
            "max_tokens": kwargs.get("max_tokens"),
            "temperature": kwargs.get("temperature"),
            "top_p": kwargs.get("top_p"),
            "top_k": kwargs.get("top_k"),
            "frequency_penalty": kwargs.get("frequency_penalty"),
            "n": kwargs.get("n"),
            "response_format": {"type": "text"},
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        httpx_kwargs = {}
        if self.proxy:
            httpx_kwargs["proxies"] = self.proxy

        async with httpx.AsyncClient(trust_env=True, **httpx_kwargs) as client:
            try:
                response = await client.post(
                    self.api_base,
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    message = result["choices"][0]["message"]["content"]
                    await self.memory.add_conversation(
                        BotType.SILICON,
                        query,
                        message,
                        {"model": kwargs.get("model")}
                    )
                    print(message)
                    return message
                else:
                    print("API 返回数据格式错误")
                    return ""
            except httpx.HTTPError as e:
                print(f"HTTP 错误: {str(e)}")
                return ""
            except json.JSONDecodeError as e:
                print(f"JSON 解析错误: {str(e)}")
                return ""
            except Exception as e:
                print(f"发生错误: {str(e)}")
                return ""

    async def ask_stream(self, query, **options):
        ms = self.get_messages()
        ms.append({"role": "user", "content": f"{query}"})
        
        kwargs = {**self.default_options, **options}
        kwargs["stream"] = True
        
        payload = {
            "model": kwargs.get("model"),
            "messages": ms,
            "stream": True,
            "max_tokens": kwargs.get("max_tokens"),
            "temperature": kwargs.get("temperature"),
            "top_p": kwargs.get("top_p"),
            "top_k": kwargs.get("top_k"),
            "frequency_penalty": kwargs.get("frequency_penalty"),
            "n": kwargs.get("n"),
            "response_format": {"type": "text"},
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        httpx_kwargs = {}
        if self.proxy:
            httpx_kwargs["proxies"] = self.proxy

        async with httpx.AsyncClient(trust_env=True, **httpx_kwargs) as client:
            try:
                async with client.stream(
                    "POST",
                    self.api_base,
                    json=payload,
                    headers=headers
                ) as response:
                    response.raise_for_status()
                    message = ""
                    buffer = ""  # 用于累积内容的缓冲区
                    async for chunk in response.aiter_lines():
                        if chunk:
                            try:
                                chunk_data = json.loads(chunk.replace("data: ", ""))
                                if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                                    content = chunk_data["choices"][0]["delta"].get("content", "")
                                    if content:
                                        buffer += content
                                        # 检查是否有完整句子
                                        if buffer.endswith(('.', '!', '?')):
                                            print(buffer, end="", flush=True)
                                            message += buffer
                                            yield buffer
                                            buffer = ""  # 清空缓冲区
                            except json.JSONDecodeError:
                                continue
                    # 打印剩余的缓冲区内容
                    if buffer:
                        print(buffer, end="", flush=True)
                        message += buffer
                        yield buffer
                    print()
                    await self.memory.add_conversation(
                        BotType.SILICON,
                        query,
                        message,
                        {"model": kwargs.get("model"), "stream": True}
                    )
            except Exception as e:
                print(f"发生错误: {str(e)}")
                return

    def has_history(self) -> bool:
        history = self.memory.get_history(BotType.SILICON)
        return bool(history)

    def change_prompt(self, new_prompt: str) -> None:
        history = self.memory.get_history(BotType.SILICON)
        if history:
            history[0]["input"] = new_prompt

    def get_messages(self) -> list[dict]:
        ms = []
        history = self.memory.get_history(BotType.SILICON)
        for h in history:
            ms.append({"role": "user", "content": h["input"]})
            ms.append({"role": "assistant", "content": h["response"]})
        return ms
