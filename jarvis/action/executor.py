from __future__ import annotations

import json
import aiohttp
from typing import Dict, Optional
from datetime import datetime
from xiaogpt.xiaogpt import MiGPT

class ActionExecutor:
    """动作执行模块"""
    
    # API端点配置
    API_ENDPOINTS = {
        "weather_api": "https://api.weather.com/v1/current",
        "news_api": "https://api.news.com/v1/top",
        "stock_api": "https://api.stock.com/v1/quote",
        "traffic_api": "https://api.traffic.com/v1/status",
        "calendar_api": "https://api.calendar.com/v1/events"
    }
    
    def __init__(self):
        self.migpt = None  # MiGPT实例
        self.session = None
        self.api_keys = {}  # 存储API密钥
        
    async def init(self):
        """初始化"""
        self.session = aiohttp.ClientSession()
        
    async def close(self):
        """关闭执行器并清理资源"""
        pass
        
    def set_migpt(self, migpt: MiGPT):
        """设置MiGPT实例"""
        self.migpt = migpt
        
    def set_api_key(self, api_name: str, key: str):
        """设置API密钥"""
        self.api_keys[api_name] = key
        
    async def execute_plan(self, plan) -> str:
        """执行计划"""
        response = []
        
        try:
            for step in plan.steps:
                if step["type"] == "api_call":
                    if api_response := await self._call_api(step["api"]):
                        response.append(api_response)
                elif step["type"] == "device_control":
                    await self._control_device(step["action"])
                    response.append(
                        f"已{step['action']['command']}{step['action']['device']}"
                    )
        except Exception as e:
            response.append(f"执行出错: {str(e)}")
            
        return "，".join(response) if response else "执行完成"
        
    async def _call_api(self, api_name: str) -> Optional[str]:
        """调用外部API"""
        if not self.session:
            await self.init()
            
        if api_name not in self.API_ENDPOINTS:
            return None
            
        endpoint = self.API_ENDPOINTS[api_name]
        headers = {}
        if api_key := self.api_keys.get(api_name):
            headers["Authorization"] = f"Bearer {api_key}"
            
        try:
            async with self.session.get(endpoint, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._format_api_response(api_name, data)
        except Exception as e:
            print(f"API调用出错 {api_name}: {str(e)}")
        return None
        
    def _format_api_response(self, api_name: str, data: Dict) -> str:
        """格式化API响应"""
        if api_name == "weather_api":
            return f"当前天气: {data.get('weather')}, 温度: {data.get('temperature')}°C"
        elif api_name == "news_api":
            return f"热门新闻: {', '.join(n['title'] for n in data.get('news', [])[:3])}"
        elif api_name == "stock_api":
            return f"股票信息: {data.get('symbol')} {data.get('price')}"
        elif api_name == "traffic_api":
            return f"交通状况: {data.get('status')}"
        elif api_name == "calendar_api":
            events = data.get("events", [])
            return f"今日日程: {', '.join(e['title'] for e in events)}"
        return str(data)
        
    async def _control_device(self, action: Dict):
        """控制智能设备"""
        if not self.migpt:
            raise Exception("MiGPT未初始化")
            
        device = action["device"]
        command = action["command"]
        params = action.get("params", {})
        
        # 构建命令字符串
        cmd_str = self._build_command(device, command, params)
        
        # 发送命令
        await self.migpt.miio_service.send_command(
            self.migpt.config.mi_did,
            f"5-4 {cmd_str} #1"
        )
        
    def _build_command(self, device: str, command: str, params: Dict) -> str:
        """构建设备控制命令"""
        # 基础命令
        cmd = f"{device}_{command}"
        
        # 添加参数
        if params:
            param_str = "_".join(f"{k}_{v}" for k, v in params.items())
            cmd = f"{cmd}_{param_str}"
            
        return cmd