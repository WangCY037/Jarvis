from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from enum import Enum

class BotType(Enum):
    XIAOAI = "xiaoai"  # 小爱自身
    GPT = "big_model"        # GPT
    SILICON = "silicon" # Silicon Flow
    OTHER = "other"    # 其他bot

class MemoryType(Enum):
    HISTORY = "history"      # 历史对话
    SHORT_TERM = "short"     # 短期记忆
    LONG_TERM = "long"       # 长期记忆

class Memory:
    """统一的记忆管理模块"""
    
    def __init__(self, 
                 memory_dir: str = "jarvis/memory",
                 max_short_term: int = 10,
                 max_history: int = 100):
        # 创建记忆存储目录
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置各类记忆文件路径
        self.history_file = self.memory_dir / "conversation_history.json"
        self.long_term_file = self.memory_dir / "long_term_memory.json"
        self.long_term_versions_dir = self.memory_dir / "long_term_versions"
        self.long_term_versions_dir.mkdir(exist_ok=True)
        
        self.max_short_term = max_short_term
        self.max_history = max_history
        
        # 仅初始化最近的对话历史用于追加
        self._recent_history: List[Dict] = []
        self._load_recent_history()
        
        # 短期记忆: 当前session的重要信息
        self.short_term: Dict[str, Any] = {
            "current_session": [],
            "key_points": [],
            "context": {}
        }
        
        # 长期记忆: 持久化的重要信息
        self.long_term = self._load_long_term()
        
    def _load_recent_history(self, limit: int = 100) -> None:
        """只加载最近的一部分历史对话"""
        if self.history_file.exists():
            with open(self.history_file, 'r', encoding='utf-8') as f:
                # 从文件末尾读取最后limit条记录
                try:
                    history = json.loads(f.read())
                    self._recent_history = history[-limit:]
                except json.JSONDecodeError:
                    self._recent_history = []
        else:
            self._recent_history = []

    def _load_long_term(self) -> Dict:
        """加载最新的长期记忆"""
        if self.long_term_file.exists():
            return json.loads(self.long_term_file.read_text())
        return {
            "user_habits": {},      # 用户习惯
            "preferences": {},      # 用户偏好
            "important_events": [], # 重要事件
            "bot_summaries": {},    # 各bot的对话总结
            "device_history": {},   # 设备使用历史
            "version": datetime.now().isoformat()  # 版本时间戳
        }
        
    def _save_conversation_history(self):
        """保存对话历史"""
        # 如果文件存在，先读取现有历史
        existing_history = []
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    existing_history = json.loads(f.read())
            except json.JSONDecodeError:
                pass

        # 合并现有历史和最近历史
        updated_history = existing_history + self._recent_history
        
        # 保存完整历史
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(updated_history, f, indent=2, ensure_ascii=False)
            
        # 重置最近历史
        self._recent_history = []
        self._load_recent_history()

    def _save_long_term_version(self):
        """保存长期记忆的新版本"""
        # 生成版本文件名
        version_time = datetime.now().isoformat().replace(":", "-")
        version_file = self.long_term_versions_dir / f"long_term_{version_time}.json"
        
        # 更新版本信息
        self.long_term["version"] = version_time
        
        # 保存当前版本
        version_file.write_text(json.dumps(self.long_term, indent=2, ensure_ascii=False))
        # 更新最新版本文件
        self.long_term_file.write_text(json.dumps(self.long_term, indent=2, ensure_ascii=False))

    async def add_conversation(self, 
                             bot_type: BotType,
                             input_text: str,
                             response: str, 
                             context: Dict,
                             metadata: Optional[Dict] = None):
        """添加一条对话记录"""
        conversation = {
            "bot_type": bot_type.value,
            "input": input_text,
            "response": response,
            "timestamp": datetime.now().isoformat(),
            "context": context,
            "metadata": metadata or {}
        }
        
        # 更新最近对话历史
        self._recent_history.append(conversation)
        if len(self._recent_history) >= self.max_history:
            # 当最近历史达到上限时，保存到文件
            self._save_conversation_history()
            
        # 更新短期记忆
        self.short_term["current_session"].append(conversation)
        if len(self.short_term["current_session"]) > self.max_short_term:
            self.short_term["current_session"].pop(0)
            
        # 分析并提取关键信息
        await self._analyze_conversation(conversation)
        
    async def _analyze_conversation(self, conversation: Dict):
        """分析对话内容,提取关键信息"""
        # TODO: 使用NLP或其他方法分析对话
        # 1. 提取关键点
        # 2. 更新用户偏好
        # 3. 识别重要事件
        pass
        
    async def update_long_term(self):
        """更新长期记忆"""
        # 1. 分析当前session的对话
        session = self.short_term["current_session"]
        if not session:
            return
            
        # 2. 按bot类型分组总结
        summaries = {}
        for conv in session:
            bot_type = conv["bot_type"]
            if bot_type not in summaries:
                summaries[bot_type] = []
            summaries[bot_type].append(conv)
            
        # 3. 更新各bot的对话总结
        for bot_type, convs in summaries.items():
            if bot_type not in self.long_term["bot_summaries"]:
                self.long_term["bot_summaries"][bot_type] = []
            # TODO: 使用更智能的方式总结对话
            summary = {
                "timestamp": datetime.now().isoformat(),
                "conversation_count": len(convs),
                "key_points": self.short_term["key_points"]
            }
            self.long_term["bot_summaries"][bot_type].append(summary)
            
        # 4. 保存新版本的长期记忆
        self._save_long_term_version()
        
    def get_history(self, 
                   bot_type: Optional[BotType] = None,
                   limit: int = 10) -> List[Dict]:
        """获取指定bot的历史对话"""
        # 从文件中读取历史记录
        all_history = []
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    all_history = json.loads(f.read())
            except json.JSONDecodeError:
                pass
        
        # 合并文件中的历史和最近的历史
        all_history.extend(self._recent_history)
        
        # 根据bot类型过滤
        if bot_type:
            filtered = [
                conv for conv in all_history 
                if conv["bot_type"] == bot_type.value
            ]
            return filtered[-limit:]
        
        return all_history[-limit:]
    
    def get_short_term_context(self) -> Dict:
        """获取短期记忆上下文"""
        return {
            "current_session": self.short_term["current_session"],
            "key_points": self.short_term["key_points"],
            "context": self.short_term["context"]
        }
    
    def get_long_term_summary(self, bot_type: Optional[BotType] = None) -> Dict:
        """获取长期记忆摘要"""
        if bot_type:
            return {
                "summaries": self.long_term["bot_summaries"].get(bot_type.value, []),
                "user_habits": self.long_term["user_habits"],
                "preferences": self.long_term["preferences"]
            }
        return self.long_term
    
    def clear_session(self):
        """清除当前会话的短期记忆"""
        self.short_term["current_session"] = []
        self.short_term["key_points"] = []
        self.short_term["context"] = {}
        
    async def close(self):
        """关闭并清理内存资源"""
        await self.update_long_term()
        self._save_conversation_history()