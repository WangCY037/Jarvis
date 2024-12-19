from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import List, Dict, Optional
from pathlib import Path
import aiohttp
import json

from jarvis.memory.memory import Memory, BotType, MessageType, MemorySummarizer
from jarvis.planning.planner import DialogueState, PlanType, Planner
from jarvis.action.executor import ActionExecutor
from xiaogpt.xiaogpt import MiGPT
from xiaogpt.bot.siliconflow_bot import SiliconFlowBot
from xiaogpt.bot.glm_bot import GLMBot
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
    search_bot: Optional[GLMBot] = None
    logger: logging.Logger = dataclasses.field(default_factory=lambda: logging.getLogger('JarvisAgent'))
    
    # 运行时状态
    is_active: bool = True
    in_conversation: bool = False
    
    def __post_init__(self):
        """初始化各个模块"""
        if self.config:
            self.memory = Memory(config=self.config)
            # 移除 planner 的初始化，因为它需要在 migpt 初始化后进行
            self.executor = None
        
    async def init_bot(self):
        """初始化对话机器人"""
        if not self.config:
            raise RuntimeError("Config not initialized")
        
        # 先创建 client_session 如果还没有的话
        if not self.client_session:
            self.client_session = aiohttp.ClientSession()
        
        # 初始化 Memory 如果还没有的话
        if not self.memory:
            self.memory = Memory(config=self.config)
        
        # 初始化机器人
        self.bot = SiliconFlowBot(
            api_key=self.config.siliconflow_key,
            proxy=self.config.proxy,
            memory=self.memory,
            logger=self.logger.getChild('SiliconFlow')
        )
        
        self.search_bot = GLMBot(
            glm_key=self.config.glm_key, 
            memory=self.memory, 
            logger=self.logger.getChild('GLM')
        )
        
        # 初始化 MemorySummarizer
        self.memory.summarizer = MemorySummarizer(self.bot)
        
        # 初始化 MIGPT - 移到 planner 初始化之前
        self.migpt = MiGPT(
            self.config, 
            client_session=self.client_session,
            bot=self.bot,
            search_bot=self.search_bot
        )
        await self.migpt.init_all_data()
        
        # 初始化 planner - 移到 MIGPT 初始化之后
        self.planner = Planner(
            bot=self.bot,
            logger=self.logger.getChild('Planner')
        )
        
        # 初始化 executor 
        self.executor = ActionExecutor(self.bot, self.migpt, self.search_bot, logger=self.logger.getChild('ActionExecutor'))
        
    async def process_input(self, input_text: str, xiaoai_response: str):
        """处理输入并返回响应"""
        if not self.migpt or not self.migpt.last_record:
            self.logger.error("MIGPT or last_record not initialized")
            return
        
        # 1. 使用Planner分析意图并创建计划
        plan = await self.planner.create_plan(input_text, xiaoai_response)
        
        # 2. 设置对话状态
        self.in_conversation = (plan.analysis.dialogue_state == DialogueState.CONTINUOUS)
        
        # 3. 使用executor执行计划
        await self.executor.execute_plan(plan)
        
        return 
        
    @classmethod
    async def create(cls, config: Config) -> JarvisAgent:
        """工厂方法创建agent实例"""
        agent = cls(config=config)
        
        # 初始化所有组件
        await agent.init_bot()
        
        return agent

    async def run_forever(self):
        """持续运行agent"""
        if not self.migpt:
            raise RuntimeError("MIGPT not initialized")
            
        # 启动MIGPT的轮询任务
        migpt_task = asyncio.create_task(self.migpt.poll_latest_ask())
        
        try:
            self.logger.info("Jarvis is running with MIGPT, start conversation")
            while True:
                # 从MIGPT获取用户输入
                self.migpt.polling_event.set()
                new_record = await self.migpt.last_record.get()
                self.migpt.polling_event.clear()
                query = new_record.get("query", "").strip()
                try: 
                    answers = new_record.get("answers", [])
                    xiaoai_response = answers[0].get("tts", {}).get("text", "") if answers else ""
                    self.logger.info(f"query: {query} \n 小爱音箱的回答: {xiaoai_response}")
                except IndexError:
                    self.logger.warning("没有收到小爱音箱的回答")
                    xiaoai_response = ""
                    continue
                
                # 处理用户输入
                await self.process_input(query, xiaoai_response)
                
                # 如果在对话模式,继续等待用户输入
                if self.in_conversation:
                    await self.migpt.wakeup_xiaoai()
                    
        except asyncio.CancelledError:
            self.logger.info("Agent任务被取消")
        except Exception as e:
            self.logger.error(f"Agent运行时发生错误: {str(e)}", exc_info=True)
        finally:
            migpt_task.cancel()
            await self.migpt.close()

    @classmethod
    async def run(cls, config: Config):
        """
        入口函数,用于启动Agent
        """
        agent = None
        logger = logging.getLogger('JarvisAgent')
        try:
            # 创建并初始化agent
            agent = await cls.create(config)
            # 运行agent
            await agent.run_forever()
        except Exception as e:
            logger.error(f"Agent运行时发生错误: {str(e)}", exc_info=True)
            raise
        finally:
            if agent:
                await agent.shutdown()

    async def shutdown(self):
        """安全关闭Agent的所有组件"""
        self.is_active = False
        
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