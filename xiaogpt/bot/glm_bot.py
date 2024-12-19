"""ChatGLM bot"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, ClassVar

from rich import print
from jarvis.memory.memory import Memory, BotType

@dataclasses.dataclass
class GLMBot:
    name: ClassVar[str] = "Chat GLM"
    default_options: ClassVar[dict[str, str | float | int]] = {
        "model": "glm-4-flash",
        "max_tokens": 1024,
        "temperature": 0.7,
        "top_p": 0.7,
        "frequency_penalty": 0.5,
        "n": 1,
        "stream": False,
        "tools": [{"type":"web_search","web_search":{"search_result":True}}],
    }

    glm_key: str
    memory: Memory = dataclasses.field(default_factory=Memory)
    logger: logging.Logger = dataclasses.field(default=None)

    def __post_init__(self):
        from zhipuai import ZhipuAI
        self.client = ZhipuAI(api_key=self.glm_key)

    @classmethod
    def from_config(cls, config):
        return cls(
            glm_key=config.glm_key,
            logger=logging.getLogger('JarvisAgent.GLM')
        )

    async def ask(self, query, **options):
        try:
            message_type = options.get("message_type", "")
            additional_messages = options.get("additional_messages", [])
            additional_messages.append({"role": "user", "content": f"{query}"})
            full_messages = self.get_messages(message_type=message_type,
                                   additional_messages=additional_messages)
            
            kwargs = {**self.default_options, **options}
            kwargs["messages"] = full_messages

            try:
                r = self.client.chat.completions.create(**kwargs)
                message = r.choices[0].message.content
                self.logger.info(message)
                await self.save_conversation(query, message, message_type, full_messages)
                print(message)
                return message
            except Exception as e:
                self.logger.error(f"API 调用错误: {str(e)}")
                print(str(e))
                return ""
                
        except Exception as e:
            self.logger.error(f"发生错误: {str(e)}", exc_info=True)
            return ""

    async def ask_stream(self, query: str, **options: Any):
        try:
            message_type = options.get("message_type", "")
            additional_messages = options.get("additional_messages", [])
            additional_messages.append({"role": "user", "content": f"{query}"})
            full_messages = self.get_messages(message_type=message_type,
                                   additional_messages=additional_messages)
            
            kwargs = {**self.default_options, **options}
            kwargs["messages"] = full_messages
            kwargs["stream"] = True

            try:
                r = self.client.chat.completions.create(**kwargs)
                full_content = ""
                for chunk in r:
                    content = chunk.choices[0].delta.content
                    if content:
                        full_content += content
                        print(content, end="", flush=True)
                        yield content
                await self.save_conversation(query, full_content, message_type, full_messages)
            except Exception as e:
                self.logger.error(f"Stream API 调用错误: {str(e)}")
                print(str(e))
                return
                
        except Exception as e:
            self.logger.error(f"发生错误: {str(e)}", exc_info=True)
            return

    def get_messages(self, message_type, additional_messages=None) -> list[dict]:
        return self.memory.get_messages(message_type=message_type, additional_messages=additional_messages)
    
    async def save_conversation(self, query, message, message_type, full_context):
        try:
            await self.memory.add_conversation(
                bot_type=BotType.GLM,
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
