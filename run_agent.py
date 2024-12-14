import asyncio
import aiohttp
import logging
import os
from datetime import datetime
from jarvis.core.agent import JarvisAgent
from jarvis.configs.Config import Config
import tracemalloc

tracemalloc.start()

def setup_logging():
    # 确保日志目录存在
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 生成日志文件名（包含时间戳）
    log_filename = os.path.join(log_dir, f'jarvis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    # 配置日志格式
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # 配置根日志记录器
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler()  # 同时输出到控制台
        ]
    )
    
    return logging.getLogger('JarvisAgent')

async def main():
    # 设置日志记录
    logger = setup_logging()
    
    # 初始化配置
    config = Config()
    
    try:
        # 启动agent
        logger.info("正在启动Agent...")
        await JarvisAgent.run(config)
        
    except KeyboardInterrupt:
        logger.info("\n检测到退出信号，正在安全关闭Agent...")
    except Exception as e:
        logger.error(f"运行过程中发生错误: {str(e)}")
        # 添加更详细的错误日志
        logger.error("详细错误信息:", exc_info=True)

if __name__ == "__main__":
    # 使用 asyncio 运行异步主函数
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序已终止") 