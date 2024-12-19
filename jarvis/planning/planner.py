from __future__ import annotations

import dataclasses
import json
import logging
import re
from enum import Enum
from typing import Optional, Dict, List, Tuple

from jarvis.memory.memory import BotType, MessageType
from jarvis.configs.Config import Config, WAKEUP_KEYWORD
from jarvis.utils.text_utils import extract_json_from_text

config = Config()

@dataclasses.dataclass
class QuickIntent:
    """快速意图判断结果"""
    is_basic_command: bool  # 是否是基础命令
    command_type: str = ""  # 命令类型（如果是基础命令）

class IntentType(Enum):
    DEVICE_CONTROL = "DEVICE_CONTROL"  # 设备控制，如开关灯、调温度等
    CHAT_COMPANION = "CHAT_COMPANION"  # 聊天陪伴，日常对话
    INFORMATION_QUERY = "INFORMATION_QUERY"  # 信息查询，包括天气、新闻等需要联网的查询
    EMOTIONAL_SUPPORT = "EMOTIONAL_SUPPORT"  # 情感支持，如安慰、鼓励等

class DialogueState(Enum):
    SINGLE = "SINGLE"
    CONTINUOUS = "CONTINUOUS" 
    WAITING_DEVICE = "WAITING_DEVICE"  # 等待设备控制
    WAITING_INFO = "WAITING_INFO"  # 等待信息查询

class PlanType(Enum):
    INTERNET_SEARCH = "INTERNET_SEARCH"
    LOCAL_ACTION = "LOCAL_ACTION"

@dataclasses.dataclass
class IntentAnalysis:
    """意图分析结果"""
    intents: List[Dict[str, float]]  # 每个意图及其置信度
    dialogue_state: DialogueState = DialogueState.SINGLE  # 对话状态
    is_basic_command: bool = False  # 是否是基础命令
    command_type: str = ""  # 如果是基础命令，命令的类型
    immediate_response: str = ""  # 立即回复的文本
    requires_device_control: bool = False  # 是否需要设备控制
    requires_info_query: bool = False  # 是否需要信息查询
    search_query: str = ""  # 整理后的搜索请求

@dataclasses.dataclass
class ActionPlan:
    """行动计划 - 简化后只包含最终执行所需信息"""
    analysis: IntentAnalysis  # 意图分析结果
    response_text: str  # 最终响应文本
    user_input: str = ""  # 添加用户输入字段

class Planner:
    """计划制定器 - 只负责分析意图和制定计划"""
    
    def __init__(self, bot, logger=None):
        self.bot = bot
        self.logger = logger
        # 基础命令模式
        self.basic_command_patterns = {
            "时间查询": [r"几点", r"现在时间", r"当前时间"],
            "闹钟设置": [r"闹钟", r"提醒", r"叫我", r"定时"],
            "设备控制": [r"打开", r"关闭", r"开启", r"停止", r"暂停", r"继续"],
            "音乐控制": [r"播放", r"音乐", r"暂停", r"下一首", r"上一首", r"声音", r"音量"],
            "天气查询": [r"天气", r"下雨", r"温度"],
            "日程管理": [r"日程", r"行程", r"安排", r"日历"],
            "设备发现": [r"发现设备", r"搜索设备", r"连接设备"],
            "智能家居": [r"灯", r"空调", r"窗帘", r"电视", r"小爱同学"],
            "基础问答": [r"你是谁", r"你叫什么", r"你能做什么"],
            "唤醒回应": [r"在呢", r"在", r"我在", r"来了"],
        }
        # 添加命令类型到意图类型的映射
        self.command_to_intent = {
            "时间查询": IntentType.INFORMATION_QUERY,
            "闹钟设置": IntentType.DEVICE_CONTROL,
            "设备控制": IntentType.DEVICE_CONTROL,
            "音乐控制": IntentType.DEVICE_CONTROL,
            "天气查询": IntentType.INFORMATION_QUERY,
            "日程管理": IntentType.DEVICE_CONTROL,
            "设备发现": IntentType.DEVICE_CONTROL,
            "智能家居": IntentType.DEVICE_CONTROL,
            "基础问答": IntentType.CHAT_COMPANION,
            "唤醒回应": IntentType.CHAT_COMPANION,
        }
        
        # 意图分析和初步回复的prompt
        self.intent_analysis_prompt = """作为AI助手Jarvis，请分析用户输入并给出温暖、亲切的回复。我是用户的贴心伙伴，应该用温暖关怀的语气交谈。

分析以下几个方面：
1. 意图类型：
   - CHAT_COMPANION: 日常聊天，陪伴交谈
   - EMOTIONAL_SUPPORT: 需要情感支持和安慰
   - DEVICE_CONTROL: 可能需要通过设备来改善情绪或环境
   - INFORMATION_QUERY: 需要查询信息来帮助用户

2. 对话状态：
   - SINGLE: 单次对话，用户的问题可以通过一次回复完整解决
   - CONTINUOUS: 需要持续对话，比如深入的情感交流或复杂问题的讨论
   - WAITING_DEVICE: 需要等待设备控制的结果
   - WAITING_INFO: 需要等待信息查询的结果

3. 回复要求：
   - 对于聊天和情感支持，立即给出温暖、共情的回复
   - 如果判断环境调节可能有帮助，可以在回复中自然提及
   - 如果需要查询信息，告知用户正在搜索

4. 信息查询要求：
   - 如果需要查询信息，请直接提供完整的搜索请求
   - 搜索请求应该清晰明确，包含必要的上下文
   - 格式应该是可以直接提供给搜索引擎的自然语言问题

请以JSON格式返回：
{
    "intents": [
        {"type": "意图类型", "confidence": 0.9}
    ],
    "immediate_response": "立即回复的温暖亲切的文本",
    "dialogue_state": "对话状态",
    "requires_device_control": false,  # 是否需要设备控制
    "requires_info_query": false,  # 是否需要信息查询
    "search_query": ""  # 如果需要信息查询，完整的搜索请求
}

示例：
用户输入："今天北京天气怎么样？"
返回：
{
    "intents": [{"type": "INFORMATION_QUERY", "confidence": 0.9}],
    "immediate_response": "让我帮您查询一下北京的天气情况。",
    "dialogue_state": "WAITING_INFO",
    "requires_device_control": false,
    "requires_info_query": true,
    "search_query": "请提供北京市今天的天气预报，包括气温、天气状况、空气质量等信息。"
}
"""

    def quick_intent_check(self, user_input: str) -> QuickIntent:
        """快速检查是否是基础命令"""
        # 如果输入太长（超过15个字），不视为基础命令
        if len(user_input) > 20:
            return QuickIntent(is_basic_command=False)
            
        # 检查是否匹配任何基础命令模式
        for command_type, patterns in self.basic_command_patterns.items():
            for pattern in patterns:
                if re.search(pattern, user_input):
                    return QuickIntent(is_basic_command=True, command_type=command_type)
                    
        return QuickIntent(is_basic_command=False)

    async def analyze_intent(self, user_input: str, xiaoai_response: str) -> IntentAnalysis:
        """分析用户输入并生成初步回复"""
        # 首先进行快速意图判断
        quick_intent = self.quick_intent_check(user_input)
        self.logger.info(f"快速意图判断: {quick_intent}")

        if quick_intent.is_basic_command:
            # 如果是基础相应，就不加到对话里：
            if user_input != WAKEUP_KEYWORD or quick_intent.command_type != "唤醒回应":
                # 将小米的回复转换为JSON格式，让回复统一    
                intent = self.command_to_intent[quick_intent.command_type]  
                requires_device_control = "true" if intent == IntentType.DEVICE_CONTROL else "false"
                requires_info_query = "true" if intent == IntentType.INFORMATION_QUERY else "false"
                response = f"""{{
                    "intents": [
                        {{"type": "{intent}", "confidence": 0.9}}
                    ],      
                    "immediate_response": "{xiaoai_response}",
                    "dialogue_state": "SINGLE",
                    "requires_device_control": {requires_device_control},
                    "requires_info_query": {requires_info_query},
                    "search_query": ""  
                    }}"""
                messages = self.bot.memory.get_messages(message_type=MessageType.USER_CHAT, additional_messages=[
                    {"role": "system", "content": f"{self.intent_analysis_prompt}"}
                ])
                messages.append({"role": "user", "content": user_input})
                messages.append({"role": "assistant", "content": response})

                await self.bot.memory.add_conversation(
                    bot_type=BotType.XIAOAI,
                    input_text=user_input,
                    response=response,
                    context={}, 
                    message_type=MessageType.USER_CHAT,
                    full_context=messages
                )

            return IntentAnalysis(
                intents=[{"type": "DEVICE_CONTROL", "confidence": 1.0}],
                is_basic_command=True,
                command_type=quick_intent.command_type,
                immediate_response=xiaoai_response,  # 小爱音箱的回答
                dialogue_state=DialogueState.SINGLE,
                requires_device_control=True
            )

        prompt = self.intent_analysis_prompt
        # 收集完整的响应
        full_response = await self.bot.ask(
            user_input, 
            message_type=MessageType.USER_CHAT,
            additional_messages=[{"role": "system", "content": f"{prompt}"}],
            stream=False
        )
        self.logger.debug(f"意图分析结果: {full_response}")
        try:
            # 尝试直接解析
            result = extract_json_from_text(full_response)

        except json.JSONDecodeError:
            self.logger.error(f"无法解析JSON响应: {full_response}")
            # 提供一个默认的回退响应
            return IntentAnalysis(
                intents=[{"type": "CHAT_COMPANION", "confidence": 1.0}],
                is_basic_command=False,
                immediate_response="抱歉，我现在有点混乱。能请您重复一遍吗？",
                dialogue_state=DialogueState.CONTINUOUS,
                requires_device_control=False,
                requires_info_query=False,
                search_query=""
            )
        
        return IntentAnalysis(
            intents=result["intents"],
            is_basic_command=False,
            immediate_response=result["immediate_response"],
            dialogue_state=DialogueState(result["dialogue_state"]),
            requires_device_control=result.get("requires_device_control", False),
            requires_info_query=result.get("requires_info_query", False),
            search_query=result.get("search_query", "")
        )

    async def create_plan(self, user_input: str, xiaoai_response: str) -> ActionPlan:
        """创建行动计划"""
        # 进行意图分析
        intent_analysis = await self.analyze_intent(user_input, xiaoai_response)
        
        return ActionPlan(
            analysis=intent_analysis,
            response_text=intent_analysis.immediate_response,
            user_input=user_input
        ) 
