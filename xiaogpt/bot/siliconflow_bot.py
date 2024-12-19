from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, ClassVar

import httpx
import json

from xiaogpt.bot.base_bot import BaseBot
from jarvis.memory.memory import Memory, BotType, MessageType

@dataclasses.dataclass
class SiliconFlowBot(BaseBot):
    name: ClassVar[str] = "SiliconFlow"
    default_options: ClassVar[dict[str, str | float | int]] = {
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "max_tokens": 1024,
        "temperature": 0.7,
        "top_p": 0.7,
        "top_k": 50,
        "frequency_penalty": 0,
        "n": 1,
        "stream": False,
    }
    
    api_key: str
    api_base: str = "https://api.siliconflow.cn/v1/chat/completions"
    proxy: str | None = None
    memory: Memory = dataclasses.field(default_factory=Memory)
    logger: logging.Logger = dataclasses.field(default=None)

    @classmethod
    def from_config(cls, config):
        return cls(
            api_key=config.siliconflow_key,
            proxy=config.proxy,
            logger=logging.getLogger('JarvisAgent.SiliconFlow')
        )

    async def ask(self, query, **options):
        try:
            message_type = options.get("message_type", "")
            additional_messages = options.get("additional_messages", [])
            additional_messages.append({"role": "user", "content": f"{query}"})
            full_messages = self.get_messages(message_type=message_type,
                                   additional_messages=additional_messages)
            
            kwargs = {**self.default_options, **options}
            payload = {
                "model": kwargs.get("model", "Qwen/Qwen2.5-7B-Instruct"),
                "messages": full_messages,
                "stream": False,
                "max_tokens": kwargs.get("max_tokens", 1024),
                "temperature": kwargs.get("temperature", 0.7),
                "top_p": kwargs.get("top_p", 0.7),
                "top_k": kwargs.get("top_k", 50),
                "frequency_penalty": kwargs.get("frequency_penalty", 0.5),
                "n": kwargs.get("n", 1),
                "response_format": kwargs.get("response_format", {"type": "text"}),
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            httpx_kwargs = {}
            if self.proxy:
                httpx_kwargs["proxies"] = self.proxy

            self.logger.info(f"请求体: {json.dumps(payload, ensure_ascii=False, indent=2)}")

            async with httpx.AsyncClient(trust_env=True, **httpx_kwargs) as client:
                try:
                    response = await client.post(
                        self.api_base,
                        json=payload,
                        headers=headers,
                    )
                    response.raise_for_status()
                    result = response.json()
                    if "choices" in result and len(result["choices"]) > 0:
                        message = result["choices"][0]["message"]["content"]
                        self.logger.info(f"GPT回答: {message}")
                        await self.save_conversation(query, message, message_type, full_messages)
                        return message
                    else:
                        self.logger.error("API 返回数据格式错误")
                        return ""
                except httpx.TimeoutException as e:
                    self.logger.error(f"请求超时: {str(e)}")
                    return ""
                except httpx.HTTPError as e:
                    error_detail = ""
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_detail = e.response.json()
                        except:
                            error_detail = e.response.text if hasattr(e.response, 'text') else str(e)
                        
                        self.logger.error(f"HTTP 错误: {str(e)}\n"
                                        f"状态码: {e.response.status_code if hasattr(e.response, 'status_code') else 'N/A'}\n"
                                        f"错误详情: {error_detail}\n"
                                        f"请求 URL: {e.response.url if hasattr(e.response, 'url') else self.api_base}\n"
                                        f"请求头: {headers}\n")
                    else:
                        self.logger.error(f"HTTP 错误（无响应详情）: {str(e)}")
                    return ""
                except json.JSONDecodeError as e:
                    self.logger.error(f"JSON 解析错误: {str(e)}")
                    return ""
                except Exception as e:
                    self.logger.error(f"发生错误: {str(e)}")
                    return ""
        except Exception as e:
            self.logger.error(f"发生错误: {str(e)}", exc_info=True)
            return ""

    async def ask_stream(self, query, **options):
        try:
            message_type = options.get("message_type","")
            additional_messages = options.get("additional_messages", [])
            additional_messages.append({"role": "user", "content": f"{query}"})
            full_messages = self.get_messages(message_type=message_type,
                                   additional_messages=additional_messages)
            
            kwargs = {**self.default_options, **options}
            kwargs["stream"] = True
            
            payload = {
                "model": kwargs.get("model", "Qwen/Qwen2.5-7B-Instruct"),
                "messages": full_messages,
                "stream": True,
                "max_tokens": kwargs.get("max_tokens", 1024),
                "temperature": kwargs.get("temperature", 0.7),
                "top_p": kwargs.get("top_p", 0.7),
                "top_k": kwargs.get("top_k", 50),
                "frequency_penalty": kwargs.get("frequency_penalty", 0.5),
                "n": kwargs.get("n", 1),
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
                        await self.save_conversation(query, message, message_type, full_messages)
                except Exception as e:
                    self.logger.error(f"发生错误: {str(e)}")
                    return
        except Exception as e:
            self.logger.error(f"发生错误: {str(e)}", exc_info=True)
            return

    def get_messages(self, message_type, additional_messages=None) -> list[dict]:
        return self.memory.get_messages(message_type=message_type, additional_messages=additional_messages)
    
    async def save_conversation(self, query, message, message_type, full_context):
        try:
            await self.memory.add_conversation(
                bot_type=BotType.SILICON,
                input_text=query,
                response=message,
                context={},
                message_type=message_type,
                full_context=full_context
            )
        except Exception as e:
            self.logger.error(f"保存对话时发生错误: {str(e)}", exc_info=True)
            raise
    def change_prompt(self, prompt):
        pass 
    
    def has_history(self):
        pass
