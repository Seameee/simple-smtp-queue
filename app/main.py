#!/usr/bin/env python3
"""
SMTP队列代理服务器主应用程序
"""

import asyncio
import logging
import signal
import sys
from typing import List, Callable
from app.config import config, setup_logging
from app.smtp_proxy import get_smtp_proxy_server, close_smtp_proxy_server
from app.queue_manager import get_queue_manager, close_queue_manager
from app.email_sender import get_email_sender, close_email_sender
from app.rate_limiter import get_rate_limiter, close_rate_limiter
from app.monitoring import get_monitoring_server, close_monitoring_server

logger = logging.getLogger(__name__)


class Application:
    """主应用程序类"""
    
    def __init__(self):
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        self.cleanup_tasks: List[Callable] = []
        
    async def startup(self):
        """启动应用程序"""
        try:
            logger.info("正在启动SMTP队列代理服务器...")
            
            # 设置日志
            setup_logging()
            
            # 初始化组件
            await self._initialize_components()
            
            # 注册信号处理器
            self._register_signal_handlers()
            
            self.is_running = True
            logger.info("SMTP队列代理服务器启动完成")
            
        except Exception as e:
            logger.error(f"启动应用程序失败: {e}")
            await self.shutdown()
            raise
            
    async def _initialize_components(self):
        """初始化所有组件"""
        # 初始化队列管理器
        logger.info("初始化队列管理器...")
        await get_queue_manager()
        
        # 初始化速率限制器
        logger.info("初始化速率限制器...")
        await get_rate_limiter()
        
        # 初始化邮件发送器
        logger.info("初始化邮件发送器...")
        email_sender = await get_email_sender()
        await email_sender.start()
        
        # 初始化监控服务器
        logger.info("初始化监控服务器...")
        monitoring_server = await get_monitoring_server()
        await monitoring_server.start()
        
        # 启动SMTP代理服务器
        logger.info("启动SMTP代理服务器...")
        smtp_server = await get_smtp_proxy_server()
        await smtp_server.start()
        
        # 注册清理任务
        self.cleanup_tasks = [
            close_smtp_proxy_server,
            close_email_sender,
            close_rate_limiter,
            close_queue_manager,
            close_monitoring_server
        ]
        
    def _register_signal_handlers(self):
        """注册信号处理器"""
        def signal_handler(signum, frame):
            logger.info(f"接收到信号 {signum}, 正在关闭服务器...")
            self.shutdown_event.set()
            
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
    async def run(self):
        """运行应用程序主循环"""
        try:
            logger.info("应用程序正在运行，按 Ctrl+C 退出")
            
            # 等待关闭信号
            await self.shutdown_event.wait()
            
            logger.info("开始优雅关闭...")
            await self.shutdown()
            
        except Exception as e:
            logger.error(f"应用程序运行异常: {e}")
            await self.shutdown()
            raise
            
    async def shutdown(self):
        """关闭应用程序"""
        if not self.is_running:
            return
            
        self.is_running = False
        
        try:
            logger.info("正在关闭应用程序组件...")
            
            # 执行所有清理任务
            for cleanup_task in self.cleanup_tasks:
                try:
                    await cleanup_task()
                except Exception as e:
                    logger.error(f"清理任务执行失败: {e}")
                    
            logger.info("应用程序已成功关闭")
            
        except Exception as e:
            logger.error(f"关闭应用程序时发生错误: {e}")
            raise


async def main():
    """主函数"""
    app = Application()
    
    try:
        await app.startup()
        await app.run()
    except KeyboardInterrupt:
        logger.info("接收到键盘中断信号")
        await app.shutdown()
    except Exception as e:
        logger.error(f"应用程序异常退出: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # 设置事件循环策略（Windows兼容性）
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # 运行主程序
    asyncio.run(main())
