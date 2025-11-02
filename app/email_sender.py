import asyncio
import logging
import smtplib
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
from app.models import EmailMessageData, SendingResult
from app.config import config

logger = logging.getLogger(__name__)


class EmailSender:
    """邮件发送器"""
    
    def __init__(self):
        self.smtp_client: Optional[aiosmtplib.SMTP] = None
        
    async def connect(self):
        """连接到目标SMTP服务器"""
        try:
            self.smtp_client = aiosmtplib.SMTP(
                hostname=config.target_smtp.host,
                port=config.target_smtp.port,
                use_tls=config.target_smtp.use_tls
            )
            
            await self.smtp_client.connect()
            
            # 如果需要认证
            if config.target_smtp.username and config.target_smtp.password:
                await self.smtp_client.login(
                    config.target_smtp.username,
                    config.target_smtp.password
                )
            
            logger.info(f"已连接到目标SMTP服务器: {config.target_smtp.host}:{config.target_smtp.port}")
            
        except Exception as e:
            logger.error(f"连接目标SMTP服务器失败: {e}")
            raise

    async def send_email(self, message: EmailMessageData) -> SendingResult:
        """发送邮件"""
        try:
            if not self.smtp_client:
                await self.connect()

            # 转换为SMTP消息
            message_bytes = message.to_smtp_message()
            
            # 发送邮件
            errors = await self.smtp_client.sendmail(
                message.from_addr,
                message.to_addrs,
                message_bytes
            )
            
            if errors:
                error_msg = f"发送失败，错误: {errors}"
                logger.error(f"邮件发送失败: {message.id}, {error_msg}")
                return SendingResult(
                    success=False,
                    message_id=message.id,
                    error_message=error_msg,
                    retry_count=message.retry_count
                )
            else:
                logger.info(f"邮件发送成功: {message.id}")
                return SendingResult(
                    success=True,
                    message_id=message.id,
                    retry_count=message.retry_count
                )
                
        except Exception as e:
            error_msg = f"发送异常: {str(e)}"
            logger.error(f"邮件发送异常: {message.id}, {error_msg}")
            return SendingResult(
                success=False,
                message_id=message.id,
                error_message=error_msg,
                retry_count=message.retry_count
            )

    async def close(self):
        """关闭SMTP连接"""
        if self.smtp_client:
            try:
                await self.smtp_client.quit()
                logger.info("SMTP连接已关闭")
            except Exception as e:
                logger.warning(f"关闭SMTP连接时出现警告: {e}")


class RetryManager:
    """重试管理器"""
    
    def __init__(self, email_sender: EmailSender):
        self.email_sender = email_sender
        
    async def send_with_retry(self, message: EmailMessageData) -> SendingResult:
        """带重试机制的邮件发送"""
        max_retries = config.rate_limit.max_retries
        
        while True:
            result = await self.email_sender.send_email(message)
            
            if result.success:
                return result
                
            # 检查是否达到最大重试次数
            if not message.can_retry(max_retries):
                logger.warning(f"邮件达到最大重试次数，放弃发送: {message.id}")
                return result
                
            # 计算重试延迟
            delay = message.get_retry_delay(config.rate_limit.retry_delay)
            message.increment_retry()
            
            logger.info(f"邮件发送失败，将在 {delay} 秒后重试 (第 {message.retry_count} 次): {message.id}")
            await asyncio.sleep(delay)


class EmailWorker:
    """邮件工作器，负责从队列获取邮件并发送"""
    
    def __init__(self, queue_manager, rate_limiter):
        self.queue_manager = queue_manager
        self.rate_limiter = rate_limiter
        self.email_sender = EmailSender()
        self.retry_manager = RetryManager(self.email_sender)
        self.is_running = False
        
    async def start(self):
        """启动工作器"""
        await self.email_sender.connect()
        self.is_running = True
        
        logger.info("邮件工作器已启动")
        
        while self.is_running:
            try:
                # 等待速率限制
                await self.rate_limiter.acquire()
                
                # 从队列获取消息
                message = await self.queue_manager.dequeue()
                
                if message:
                    await self._process_message(message)
                else:
                    # 队列为空，等待一段时间再检查
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"邮件工作器处理异常: {e}")
                await asyncio.sleep(5)  # 异常后等待一段时间再继续

    async def _process_message(self, message: EmailMessageData):
        """处理单个邮件消息"""
        try:
            # 发送邮件
            result = await self.retry_manager.send_with_retry(message)
            
            # 根据发送结果更新消息状态
            if result.success:
                await self.queue_manager.mark_completed(message.id, "sent")
                logger.info(f"邮件处理完成: {message.id}")
            else:
                if message.can_retry(config.rate_limit.max_retries):
                    # 重新加入队列等待重试
                    message.status = "pending"
                    await self.queue_manager.enqueue(message)
                    await self.queue_manager.mark_completed(message.id, "failed_retry")
                    logger.info(f"邮件重新加入队列等待重试: {message.id}")
                else:
                    # 达到最大重试次数，标记为最终失败
                    await self.queue_manager.mark_completed(message.id, "failed")
                    logger.error(f"邮件最终发送失败: {message.id}")
                    
        except Exception as e:
            logger.error(f"处理邮件消息异常: {message.id}, {e}")
            # 发生异常时，将消息重新加入队列
            try:
                message.status = "pending"
                await self.queue_manager.enqueue(message)
                await self.queue_manager.mark_completed(message.id, "failed_retry")
            except Exception as enqueue_error:
                logger.error(f"重新加入队列失败: {message.id}, {enqueue_error}")

    async def stop(self):
        """停止工作器"""
        self.is_running = False
        await self.email_sender.close()
        logger.info("邮件工作器已停止")


async def create_email_worker(queue_manager, rate_limiter) -> EmailWorker:
    """创建邮件工作器实例"""
    worker = EmailWorker(queue_manager, rate_limiter)
    return worker
