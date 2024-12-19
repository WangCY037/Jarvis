from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from enum import Enum

from jarvis.configs.Config import Config

class BotType(Enum):
    XIAOAI = "xiaoai"  # 小爱自身
    GLM = "glm"        # GPT
    SILICON = "silicon" # Silicon Flow
    OTHER = "other"    # 其他bot

class MessageType(Enum):
    USER_CHAT = "user_chat"        # 用户真实对话
    SYSTEM_TASK = "system_task"    # 系统任务（如总结、分析等）
    DEVICE_CONTROL = "device_control" # 设备控制
    SEARCH_INFO = "search_info" # 信息查询

class MemoryType(Enum):
    HISTORY = "history"      # 历史对话
    SHORT_TERM = "short"     # 短期记忆
    LONG_TERM = "long"       # 长期记忆

class MemorySummarizer:
    """记忆总结器"""
    def __init__(self, bot: Any):
        self.bot = bot
        
    async def generate_short_term_summary(self, conversations: List[Dict]) -> str:
        """生成短期记忆的上下文摘要"""
        if not self.bot:
            return ""
            
        prompt = """请总结以下对话的上下文，包括：
1. 用户当前的意图和需求
2. 重要的上下文信息
3. 需要继续跟进的点

对话内容：
"""
        for conv in conversations:
            prompt += f"用户: {conv['input']}\n"
            prompt += f"助手: {conv['response']}\n"
            
        try:
            summary = await self.bot.ask(prompt, message_type=MessageType.SYSTEM_TASK, stream=False)
            return summary
        except Exception as e:
            print(f"生成短期记忆摘要时出错: {str(e)}")
            return ""
            
    async def generate_long_term_summary(self,
                                       conversations: List[Dict],
                                       current_context: str,
                                       previous_context: str) -> str:
        """生成长期记忆的摘要"""
        if not self.bot:
            return ""
            
        # 生成时间信息
        time_info = []
        for conv in conversations:
            timestamp = datetime.fromisoformat(conv["timestamp"])
            time_str = timestamp.strftime("%Y年%m月%d日 %A %H:%M")
            time_info.append(time_str)
        
        prompt = f"""请基于以下信息，总结用户的整体情况：

历史上下文：
{previous_context}

当前对话上下文：
{current_context}

最近的对话记录（{time_info[0] if time_info else ""}）：
"""
        for conv, time_str in zip(conversations, time_info):
            prompt += f"[{time_str}]\n"
            prompt += f"用户: {conv['input']}\n"
            prompt += f"助手: {conv['response']}\n"
            
        try:
            summary = await self.bot.ask(prompt, {"message_type": MessageType.SYSTEM_TASK})
            return summary
        except Exception as e:
            print(f"生成长期记忆摘要时出错: {str(e)}")
            return ""

class Memory:
    """统一的记忆管理模块"""
    
    def __init__(self, 
                 config: Config,
                 summarizer: Optional[MemorySummarizer] = None):
        # 创建记忆存储目录
        self.config = config
        self.memory_dir = Path(self.config.memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置各类记忆文件路径
        self.current_memory_file = self.memory_dir / "current_memory.json"  # 最新的长期记忆
        self.history_file = self.memory_dir / "conversation_history.jsonl"  # 改用jsonl格式
        
        self.max_short_term = self.config.max_short_term
        self.summarizer = summarizer
        
        # 修改短期记忆结构
        self.short_term = {
            "conversations": [],  # 所有最近对话
            "context": {},       # 当前session的上下文摘要
            "last_save": datetime.now().isoformat()  # 上次保存到文件的时间
        }
        
        # 长期记忆: AI总结的重要信息
        self.long_term = self._load_long_term()

    def _load_long_term(self) -> Dict:
        """加载最新的长期记忆"""
        if self.current_memory_file.exists():
            try:
                with open(self.current_memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        return {
            "context": "",  # 用户的整体上下文
            "last_updated": datetime.now().isoformat()
        }
        
    def _save_conversation_history(self):
        """保存对话历史到文件，采用追加模式"""
        if not self.short_term["conversations"]:
            return
            
        # 直接追加新的对话到历史文件
        with open(self.history_file, 'a', encoding='utf-8') as f:
            for conv in self.short_term["conversations"]:
                f.write(json.dumps(conv, ensure_ascii=False) + '\n')
        
        # 清空短期记忆中的对话
        self.short_term["conversations"] = []
        # 更新保存时间
        self.short_term["last_save"] = datetime.now().isoformat()

    def _save_long_term(self):
        """保存最新的长期记忆"""
        # 更新时间戳
        self.long_term["last_updated"] = datetime.now().isoformat()
        
        # 保存到当前记忆文件
        with open(self.current_memory_file, 'w', encoding='utf-8') as f:
            json.dump(self.long_term, f, indent=2, ensure_ascii=False)
            
        # 同时保存一个带时间戳的版本用于备份
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.memory_dir / f"memory_backup_{timestamp}.json"
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(self.long_term, f, indent=2, ensure_ascii=False)

    async def add_conversation(self, 
                             bot_type: BotType,
                             input_text: str,
                             response: str, 
                             context: Dict,
                             metadata: Optional[Dict] = None,
                             message_type: MessageType = MessageType.USER_CHAT,
                             full_context: Optional[List[Dict]] = None):
        """添加一条对话记录
        
        Args:
            bot_type: 机器人类型
            input_text: 用户输入
            response: 机器人回复
            context: 上下文信息
            metadata: 元数据
            message_type: 消息类型
            full_context: 完整的对话上下文列表，包含此次请求发送给bot的所有消息
        """
        conversation = {
            "timestamp": datetime.now().isoformat(),
            "bot_type": bot_type.value,
            "message_type": message_type.value,
            "input": input_text,
            "response": response,
            "context": context,
            "metadata": metadata or {},
            "full_context": full_context or []  # 保存完整的对话上下文
        }
        
        # 添加到短期记忆
        self.short_term["conversations"].append(conversation)
        
        # 当短期记忆中用户真实对话数量超过max_short_term时，生成上下文摘要
        if (message_type == MessageType.USER_CHAT and self.summarizer and 
            len([c for c in self.short_term["conversations"] 
                 if c["message_type"] == MessageType.USER_CHAT.value]) >= self.max_short_term):
            # 获取用户对话
            user_conversations = [
                c for c in self.short_term["conversations"] 
                if c["message_type"] == MessageType.USER_CHAT.value
            ]
            # 生成上下文摘要
            context_summary = await self.summarizer.generate_short_term_summary(
                user_conversations
            )
            # 更新上下文
            self.short_term["context"].update({
                "timestamp": datetime.now().isoformat(),
                "summary": context_summary
            })
            
            # 在清空对话之前保存到历史记录
            self._save_conversation_history()
            
            # 清空对话
            self.short_term["conversations"] = []

    def get_messages(self, 
                    message_type: Optional[MessageType] = None,
                    additional_messages: Optional[List[Dict]] = None) -> List[Dict]:
        """获取用于对话的消息列表，包含上下文和当前session的对话
        
        Args:
            message_type: 可选的消息类型过滤器，如果指定则只返回该类型的消息
            additional_messages: 可选的额外消息列表，将被添加到返回结果中
        """
        messages = []
        # 只有当message_type为USER_CHAT时，才添加上下文信息
        if message_type == MessageType.USER_CHAT:
            # 1. 处理system prompt和上下文
            if additional_messages:
                system_messages = [msg for msg in additional_messages if msg["role"] == "system"]
                non_system_messages = [msg for msg in additional_messages if msg["role"] != "system"]
                
                if system_messages and self.short_term["context"]:
                    # 将上下文添加到现有的system prompt中
                    context_info = f"\n当前对话上下文：{self.short_term['context'].get('summary', '')}"
                    system_messages[0]["content"] = system_messages[0]["content"] + context_info
                    messages.extend(system_messages)
                elif self.short_term["context"]:
                    # 如果没有system prompt但有上下文，创建默认的system message
                    messages.append({
                        "role": "system",
                        "content": f"你是一个智能生活助手，你为用户提供舒适的生活体验，当前对话上下文：{self.short_term['context'].get('summary', '')}"
                    })
                elif system_messages:
                    # 如果有system prompt但没有上下文，直接使用原有的system message
                    messages.extend(system_messages)
                    
                # 添加其他非system消息
                messages.extend(non_system_messages)
            elif self.short_term["context"]:
                # 如果没有additional_messages但有上下文，使用默认的system message
                messages.append({
                    "role": "system",
                    "content": f"你是一个智能生活助手，你为用户提供舒适的生活体验，当前对话上下文：{self.short_term['context'].get('summary', '')}"
                })
            
            # 2. 添加当前session的对话，根据message_type过滤
            filtered_conversations = (
                [conv for conv in self.short_term["conversations"]
                if message_type is not None and conv["message_type"] == message_type.value]
            )
        
            for conv in filtered_conversations:
                messages.extend([
                    {"role": "user", "content": conv["input"]},
                    {"role": "assistant", "content": conv["response"]}
                ])
        
        # 3. 如果不是USER_CHAT类型，直接添加additional_messages
        elif additional_messages:
            messages.extend(additional_messages)
        
        return messages
            
    async def _update_long_term_async(self):
        """异步更新长期记忆"""
        if not self.summarizer:
            return
            
        # 生成长期记忆摘要
        summary = await self.summarizer.generate_long_term_summary(
            self.short_term["conversations"],
            self.short_term["context"].get("summary", ""),
            self.long_term.get("context", "")
        )
        
        if summary:
            self.long_term["context"] = summary
            self.long_term["last_updated"] = datetime.now().isoformat()
            
            # 保存长期记忆
            self._save_long_term()
        
    async def close(self):
        """关闭并清理内存资源"""
        # 如果存在短期记忆，更新到长期记忆
        if self.short_term["conversations"] and self.short_term["context"]:
            await self._update_long_term_async()
                
        self._save_conversation_history()