from __future__ import annotations

import dataclasses
import re
from typing import List, Dict, Optional
from datetime import datetime, time

@dataclasses.dataclass
class Plan:
    """计划类"""
    steps: List[Dict]  # 执行步骤
    requires_memory_update: bool = False  # 是否需要更新长期记忆
    requires_external_api: bool = False  # 是否需要调用外部API

class Planner:
    """规划模块"""
    
    # 设备控制关键词映射
    DEVICE_KEYWORDS = {
        "灯": {
            "开": "turn_on",
            "关": "turn_off",
            "调亮": "brightness_up",
            "调暗": "brightness_down"
        },
        "空调": {
            "开": "turn_on",
            "关": "turn_off",
            "制冷": "cool_mode",
            "制热": "heat_mode",
            "温度": "set_temperature"
        },
        "窗帘": {
            "开": "open",
            "关": "close",
            "停": "stop"
        }
    }
    
    # 需要记忆的关键词
    MEMORY_KEYWORDS = [
        "喜欢", "讨厌", "习惯", "通常", "一般",
        "每天", "每次", "总是", "记住", "别忘了"
    ]
    
    def __init__(self, memory):
        self.memory = memory
        
    async def create_plan(self, 
                         input_text: str, 
                         context: Dict) -> Plan:
        """为用户输入创建执行计划"""
        plan = Plan(steps=[])
        
        self.migpt.ask_gpt(input_text)
        
        # # 1. 判断是否需要调用外部API
        # if self._needs_external_api(input_text):
        #     plan.requires_external_api = True
        #     plan.steps.append({
        #         "type": "api_call",
        #         "api": self._determine_api(input_text)
        #     })
            
        # # 2. 判断是否需要控制设备
        # if device_actions := self._extract_device_actions(input_text):
        #     for action in device_actions:
        #         plan.steps.append({
        #             "type": "device_control",
        #             "action": action
        #         })
            
        # # 3. 判断是否需要更新长期记忆
        # if self._should_update_memory(input_text, context):
        #     plan.requires_memory_update = True
            
        return plan
    
    async def create_plan_for_event(self, event: Dict) -> Optional[Plan]:
        """为设备事件创建执行计划"""
        plan = Plan(steps=[])
        
        # 1. 处理设备状态变化
        if event.get("type") == "device_status_change":
            device = event["device"]
            status = event["status"]
            
            # 获取相关的用户习惯
            habits = self.memory.long_term["user_habits"].get(device, {})
            current_time = datetime.now().time()
            
            # 根据时间和习惯决定是否需要额外操作
            if self._should_adjust_by_habit(device, status, current_time, habits):
                plan.steps.append({
                    "type": "device_control",
                    "action": self._get_habit_based_action(device, habits)
                })
                
        # 2. 处理定时任务
        elif event.get("type") == "schedule":
            schedule_type = event["schedule_type"]
            if schedule_type == "morning":
                plan.steps.extend(self._create_morning_routine())
            elif schedule_type == "evening":
                plan.steps.extend(self._create_evening_routine())
                
        return plan if plan.steps else None
        
    def _needs_external_api(self, text: str) -> bool:
        """判断是否需要调用外部API"""
        # 检查是否包含需要外部信息的关键词
        api_keywords = ["天气", "新闻", "股票", "路况", "日程"]
        return any(keyword in text for keyword in api_keywords)
        
    def _determine_api(self, text: str) -> str:
        """确定需要调用的API"""
        if "天气" in text:
            return "weather_api"
        elif "新闻" in text:
            return "news_api"
        elif "股票" in text:
            return "stock_api"
        elif "路况" in text:
            return "traffic_api"
        elif "日程" in text:
            return "calendar_api"
        return "default_api"
        
    def _extract_device_actions(self, text: str) -> List[Dict]:
        """提取设备控制动作"""
        actions = []
        
        for device, commands in self.DEVICE_KEYWORDS.items():
            if device in text:
                for keyword, action in commands.items():
                    if keyword in text:
                        # 提取可能的参数值(如温度数值)
                        params = {}
                        if action == "set_temperature":
                            if temp_match := re.search(r"(\d+)度", text):
                                params["temperature"] = int(temp_match.group(1))
                                
                        actions.append({
                            "device": device,
                            "command": action,
                            "params": params
                        })
                        
        return actions
        
    def _should_update_memory(self, text: str, context: Dict) -> bool:
        """判断是否需要更新长期记忆"""
        # 1. 检查是否包含记忆关键词
        if any(keyword in text for keyword in self.MEMORY_KEYWORDS):
            return True
            
        # 2. 检查是否是重要的设备操作
        if device_actions := self._extract_device_actions(text):
            current_time = datetime.now().time()
            # 如果是在特定时间段的操作,可能代表习惯
            if self._is_routine_time(current_time):
                return True
                
        return False
        
    def _is_routine_time(self, current_time: time) -> bool:
        """判断是否是日常作息时间"""
        morning_start = time(6, 0)
        morning_end = time(9, 0)
        evening_start = time(18, 0)
        evening_end = time(23, 0)
        
        return (morning_start <= current_time <= morning_end or
                evening_start <= current_time <= evening_end)
                
    def _should_adjust_by_habit(self, device: str, status: str, 
                               current_time: time, habits: Dict) -> bool:
        """根据用户习惯判断是否需要调整设备状态"""
        if not habits:
            return False
            
        # 检查是否符合用户的时间习惯
        for habit in habits.get("time_patterns", []):
            habit_time = datetime.strptime(habit["time"], "%H:%M").time()
            if (abs(current_time.hour - habit_time.hour) <= 1 and
                habit["status"] != status):
                return True
                
        return False
        
    def _get_habit_based_action(self, device: str, habits: Dict) -> Dict:
        """根据用户习惯生成设备控制动作"""
        return {
            "device": device,
            "command": habits.get("preferred_status", "turn_on"),
            "params": habits.get("preferred_params", {})
        }
        
    def _create_morning_routine(self) -> List[Dict]:
        """创建早晨例程"""
        return [
            {"type": "device_control", "action": {"device": "窗帘", "command": "open"}},
            {"type": "device_control", "action": {"device": "灯", "command": "turn_on"}},
        ]
        
    def _create_evening_routine(self) -> List[Dict]:
        """创建晚间例程"""
        return [
            {"type": "device_control", "action": {"device": "窗帘", "command": "close"}},
            {"type": "device_control", "action": {"device": "灯", "command": "turn_off"}},
        ]