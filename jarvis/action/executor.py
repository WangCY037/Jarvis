from __future__ import annotations

import json
import logging
from pathlib import Path
import time
from typing import Optional
from jarvis.memory.memory import BotType, MessageType
from jarvis.planning.planner import ActionPlan
from xiaogpt.xiaogpt import MiGPT
from miservice import miio_command
from xiaogpt.bot.glm_bot import GLMBot
import asyncio

class ActionExecutor:
    """动作执行器 - 负责执行设备控制、信息查询等具体动作"""
    
    def __init__(self, bot, migpt: MiGPT, search_bot, logger=None, config_path: str = None):
        self.logger = logger or logging.getLogger('ActionExecutor')
        self.bot = bot
        self.migpt = migpt
        self.search_bot = search_bot
        self._load_configs(config_path)

        # 设备动作分析的prompt
        self.device_action_prompt = """作为智能家居助手，请分析用户需求并给出具体的设备控制指令。

用户输入：{user_input}
可用设备：
{available_devices}

请直接返回可以发送给智能音箱的自然语言控制指令。例如：
- "打开客厅的灯"
- "把卧室空调温度调到26度"
- "关闭所有设备"
如果没有设备能满足用户的需求或者让用户体验更好，请满足用户的情绪价值，体察用户的情绪，回复的内容可以温柔、幽默、有趣，让用户感到开心。
"""

        # 信息查询的prompt
        self.info_query_prompt = """作为AI助手，请基于查询结果生成回复。

用户原始输入: {user_input}
查询结果: {query_result}

请以JSON格式返回：
{
    "response_text": "基于查询结果的回复文本"
}"""
        
    def _load_configs(self, config_path: Optional[str] = None):
        """加载设备和控制配置"""
        # 加载设备配置
        config_path = Path(__file__).parent.parent / "configs"
        try:
            with open(config_path / "devices.json") as f:
                self.available_devices = json.load(f)
        except Exception as e:
            self.logger.error(f"加载设备列表失败: {str(e)}")
            self.available_devices = []
     
    async def execute_device_actions(self, actions: str) -> str:
        """执行设备控制动作"""
        try:
            await miio_command(
                self.migpt.miio_service,
                self.migpt.config.mi_did,
                f"5-4 {actions} #0")
        except Exception as e:
            self.logger.error(f"执行设备控制动作失败: {str(e)}")
            return "抱歉，执行设备控制动作失败"

    async def execute_info_query(self, search_query: str, query_result: str = None) -> str:
        """执行信息查询"""
        try:
            # 直接使用整理好的搜索请求
            search_result = await self.migpt.ask_gpt(search_query, 
                                                    {
                                                        "message_type": MessageType.SEARCH_INFO, 
                                                        "stream": True
                                                    })
            return search_result
        except Exception as e:
            self.logger.error(f"执行信息查询失败: {str(e)}")
            return "抱歉，信息查询失败"

    async def analyze_device_actions(self, user_input: str) -> str:
        """分析用户输入，生成具体的设备控制指令"""
        try:
            prompt = self.device_action_prompt.format(
                user_input=user_input,
                available_devices="\n".join([f"- {dev['name']}: {dev.get('description', '')}" for dev in self.available_devices])
            )
            response = await self.bot.ask(prompt, message_type=MessageType.DEVICE_CONTROL)
            return response  # 直接返回文本指令
        except Exception as e:
            self.logger.error(f"分析设备动作失败: {str(e)}")
            return ""

    async def execute_plan(self, plan: ActionPlan):
        """执行行动计划并返回最终响应"""
        try:
            response = ""
            # 如果是基础命令，等待小爱音箱处理
            if plan.analysis.is_basic_command:
                # 等待小爱音箱处理
                await self.migpt.wait_for_tts_finish()
                time.sleep(2)
                return 

            # 如果需要设备控制
            elif plan.analysis.requires_device_control:
                device_actions = await self.analyze_device_actions(plan.user_input)
                if device_actions:
                    device_response = await self.execute_device_actions(device_actions)
                    response = f"{plan.response_text}\n{device_response}"
            
            # 如果需要信息查询
            elif plan.analysis.requires_info_query:
                query_response = await self.execute_info_query(
                    plan.analysis.search_query
                )
                response = f"{plan.response_text}\n{query_response}"
            
            # 普通对话直接返回计划中的响应
            else:
                response = plan.response_text
            
            # 处理响应 先停掉小爱音箱
            await self.migpt.stop_if_xiaoai_is_playing()
            if isinstance(response, str):
                # 如果是字符串，转换为异步生成器
                async def response_generator():
                    yield response
                await self.migpt.speak(response_generator())
            else:
                # 如果已经是流，直接传递
                await self.migpt.speak(response)

            # 如果在对话模式，准备下一轮对话
            if self.migpt.in_conversation:
                await self.migpt.wakeup_xiaoai()
            return 
            
        except Exception as e:
            self.logger.error(f"执行计划失败: {str(e)}")
            return 
        

            
    async def close(self):
        """关闭执行器"""
        # TODO: 清理资源
        pass
