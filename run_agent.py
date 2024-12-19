import asyncio
import aiohttp
import logging
import os
from datetime import datetime
from jarvis.core.agent import JarvisAgent
from jarvis.configs.Config import Config
import tracemalloc
import sys

if sys.platform.startswith('win'):
    import subprocess
    subprocess.run(['chcp', '65001'], capture_output=True)

tracemalloc.start()

# 初始化配置
config = Config()

def setup_logging():
    # 确保日志目录存在
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 生成日志文件名（包含时间戳）
    log_filename = os.path.join(log_dir, f'jarvis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    # 配置日志格式
    file_format = '%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s'
    console_format = '%(levelname)s - %(message)s\n%(pathname)s:%(lineno)d'
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.ERROR)
    
    # 清除可能存在的旧处理器
    root_logger.handlers.clear()
    
    # 文件处理器 - 使用 utf-8 编码，记录所有日志
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(file_format))
    file_handler.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    
    # 控制台处理器 - 只显示重要信息
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(console_format))
    console_handler.setLevel(logging.DEBUG if config.verbose else logging.INFO)
    root_logger.addHandler(console_handler)
    
    # 创建并返回 JarvisAgent 的 logger
    loggerJarvisAgent = logging.getLogger('JarvisAgent')
    loggerJarvisAgent.setLevel(logging.DEBUG if config.verbose else logging.INFO)

    loggerXiaogpt = logging.getLogger('xiaogpt')
    loggerXiaogpt.setLevel(logging.DEBUG if config.verbose else logging.INFO)
    
    return loggerJarvisAgent

async def main():
    # 设置日志记录
    logger = setup_logging()
    
    try:
        # 启动agent
        logger.info("正在启动Agent...")
        await JarvisAgent.run(config)
        
    except KeyboardInterrupt:
        logger.info("\n检测到退出信号，正在安全关闭Agent...")
    except Exception as e:
        logger.error(f"运行过程中发生错误: {str(e)}")
        logger.exception("详细错误堆栈:")
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await asyncio.sleep(0.1)
        logging.shutdown()

if __name__ == "__main__":
    # 使用 asyncio 运行异步主函数
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序已终止")
    except Exception as e:
        logging.error("程序发生致命错误:", exc_info=True) 