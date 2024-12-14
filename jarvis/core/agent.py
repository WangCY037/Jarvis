from __future__ import annotations

import asyncio
import dataclasses
from typing import List, Dict, Optional
from pathlib import Path
import aiohttp

from jarvis.memory.memory import Memory, BotType
from jarvis.planning.planner import Planner
from jarvis.action.executor import ActionExecutor
from xiaogpt.xiaogpt import MiGPT
from xiaogpt.bot.siliconflow_bot import SiliconFlowBot
from jarvis.configs.Config import Config

@dataclasses.dataclass
class JarvisAgent:
    """智能家居AI助手的核心Agent类"""
    
    # 基础配置
    name: str = "Jarvis"
    config: Config = None
    migpt: MiGPT = None
    memory: Memory = None
    planner: Planner = None 
    executor: ActionExecutor = None
    client_session: Optional[aiohttp.ClientSession] = None
    bot: Optional[SiliconFlowBot] = None
    
    # 运行时状态
    is_active: bool = True
    in_conversation: bool = False
    current_context: Dict = dataclasses.field(default_factory=dict)
    
    def __post_init__(self):
        """初始化各个模块"""
        self.memory = Memory()
        self.planner = Planner(self.memory)
        self.executor = ActionExecutor()
        
    async def init_bot(self):
        """初始化对话机器人"""
        if not self.config:
            raise RuntimeError("Config not initialized")
            
        self.bot = SiliconFlowBot(
            api_key=self.config.siliconflow_key,
            proxy=self.config.proxy,
            memory=self.memory
        )
        
    async def process_input(self, input_text: str, source: str = "voice") -> str:
        """处理输入并返回响应"""
        # 1. 更新上下文
        self.current_context.update({
            "input": input_text,
            "source": source,
            "timestamp": asyncio.get_event_loop().time()
        })
        
        # # 2. 规划处理步骤
        # plan = await self.planner.create_plan(input_text, self.current_context)
        
        # # 3. 执行计划
        # response = await self.executor.execute_plan(plan)
        
        plan = None
        response = input_text
        # 4. 记录小爱的回答
        if source == "voice" and self.migpt:
            try:
                xiaoai_response = self.migpt.last_record.get_nowait().get("answers", [])[0].get("tts", {}).get("text", "")
                await self.memory.add_conversation(
                    BotType.XIAOAI,
                    input_text,
                    xiaoai_response,
                    self.current_context
                )
            except asyncio.QueueEmpty:
                pass
        
        # 5. 记录GPT/Silicon的回答
        await self.memory.add_conversation(
            BotType.SILICON if self.migpt else BotType.GPT,
            input_text,
            response,
            self.current_context,
            {"plan": plan.to_dict() if plan else None}
        )
        
        # 6. 通过MIGPT输出响应
        if self.migpt:
            await self.migpt.speak(self.migpt.ask_gpt(response))
                
        return response
    
    async def handle_device_event(self, event: Dict):
        """处理设备事件"""
        plan = await self.planner.create_plan_for_event(event)
        if plan:
            await self.executor.execute_plan(plan)
            
    def update_config(self, config: Dict):
        """更新配置"""
        # TODO: 实现配置更新逻辑
        pass
        
    @classmethod
    async def create(cls, config: Config) -> JarvisAgent:
        """工厂方法创建agent实例"""
        # 创建 client_session
        client_session = aiohttp.ClientSession()
        agent = cls(config=config, client_session=client_session)
        
        # 初始化bot
        await agent.init_bot()
        
        if agent.config:
            # 传递 client_session 和 bot 给 MiGPT
            agent.migpt = MiGPT(agent.config, client_session=client_session, bot=agent.bot)
            await agent.migpt.init_all_data()  # 初始化MIGPT
            
        return agent

    async def run_forever(self):
        """持续运行agent"""
        if not self.migpt:
            raise RuntimeError("MIGPT not initialized")
            
        # 启动MIGPT的轮询任务
        migpt_task = asyncio.create_task(self.migpt.poll_latest_ask())
        
        try:
            print(f"Jarvis is running with MIGPT, start conversation")
            while True:
                # 从MIGPT获取用户输入
                self.migpt.polling_event.set()
                new_record = await self.migpt.last_record.get()
                self.migpt.polling_event.clear()
                
                query = new_record.get("query", "").strip()
                
                # 处理用户输入
                await self.process_input(query)
                
                # 如果在对话模式,继续等待用户输入
                if self.in_conversation:
                    await self.migpt.wakeup_xiaoai()
                    
        except asyncio.CancelledError:
            print("Agent任务被取消")
        except Exception as e:
            print(f"Agent运行时发生错误: {str(e)}")
        finally:
            migpt_task.cancel()
            await self.migpt.close()

    @classmethod
    async def run(cls, config: Config):
        """
        入口函数,用于启动Agent
        """
        agent = None
        try:
            # 创建并初始化agent
            agent = await cls.create(config)
            # 运行agent
            await agent.run_forever()
        except Exception as e:
            print(f"Agent运行时发生错误: {str(e)}")
            raise
        finally:
            if agent:
                await agent.shutdown()

    async def shutdown(self):
        """安全关闭Agent的所有组件"""
        self.is_active = False
        
        # 更新长期记忆
        if self.memory:
            await self.memory.update_long_term()
        
        # 关闭 ClientSession
        if self.client_session and not self.client_session.closed:
            await self.client_session.close()
        
        # 关闭 MIGPT
        if self.migpt:
            await self.migpt.close()
        
        # 关闭其他组件
        if self.memory:
            await self.memory.close()
                
        if self.executor:
            await self.executor.close()