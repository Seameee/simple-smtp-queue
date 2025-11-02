import asyncio
import logging
import aiosmtpd
from aiosmtpd.smtp import SMTP, Envelope
from aiosmtpd.handlers import Message
from email import message_from_bytes
from typing import Optional
from app.models import EmailMessageData
from app.queue_manager import get_queue_manager
from app.config import config

logger = logging.getLogger(__name__)


class SMTPProxyHandler:
    """SMTP代理处理器"""
    
    def __init__(self):
        self.queue_manager = None
        
    async def handle_DATA(self, server: SMTP, session: dict, envelope: Envelope) -> str:
        """处理接收到的邮件数据"""
        try:
            if not self.queue_manager:
                self.queue_manager = await get_queue_manager()
            
            # 创建邮件消息数据
            message = EmailMessageData.from_smtp_message(envelope, envelope.content)
            
            # 验证邮件数据
            if not self._validate_message(message):
                return "550 邮件数据无效"
            
            # 将邮件加入队列
            await self.queue_manager.enqueue(message)
            
            logger.info(f"邮件已加入队列: {message.id}, 发件人: {message.from_addr}, 收件人: {message.to_addrs}")
            
            return "250 邮件已接收并加入队列"
            
        except Exception as e:
            logger.error(f"处理邮件数据失败: {e}")
            return "451 处理邮件时发生错误"

    def _validate_message(self, message: EmailMessageData) -> bool:
        """验证邮件消息"""
        # 检查发件人
        if not message.from_addr:
            logger.warning("邮件缺少发件人地址")
            return False
            
        # 检查收件人
        if not message.to_addrs:
            logger.warning("邮件缺少收件人地址")
            return False
            
        # 检查邮件大小
        message_size = len(message.message_body.encode('utf-8'))
        if message_size > config.proxy.max_message_size:
            logger.warning(f"邮件大小超过限制: {message_size} > {config.proxy.max_message_size}")
            return False
            
        return True


class SMTPProxyServer:
    """SMTP代理服务器"""
    
    def __init__(self):
        self.handler = SMTPProxyHandler()
        self.controller: Optional[aiosmtpd.controller] = None
        
    async def start(self):
        """启动SMTP代理服务器"""
        try:
            # 创建SMTP控制器
            self.controller = aiosmtpd.controller.Controller(
                self.handler,
                hostname=config.proxy.host,
                port=config.proxy.port,
                # 配置SMTP服务器选项
                require_starttls=config.proxy.require_starttls,
                auth_required=config.proxy.auth_required,
                auth_require_tls=config.proxy.auth_require_tls,
                # 设置最大消息大小
                decode_data=True,
                enable_SMTPUTF8=True,
                ident="Simple SMTP Queue Proxy"
            )
            
            # 启动服务器
            self.controller.start()
            
            logger.info(f"SMTP代理服务器已启动，监听 {config.proxy.host}:{config.proxy.port}")
            logger.info(f"服务器配置: require_starttls={config.proxy.require_starttls}, auth_required={config.proxy.auth_required}")
            
        except Exception as e:
            logger.error(f"启动SMTP代理服务器失败: {e}")
            raise

    async def stop(self):
        """停止SMTP代理服务器"""
        if self.controller:
            self.controller.stop()
            logger.info("SMTP代理服务器已停止")


class SMTPAuthHandler:
    """SMTP认证处理器"""
    
    def __init__(self):
        self.valid_users = {
            config.proxy.auth_username: config.proxy.auth_password
        } if config.proxy.auth_username and config.proxy.auth_password else {}
        
    async def auth_MECHANISM(self, server: SMTP, session: dict, mechanism: str, args: bytes) -> bool:
        """处理SMTP认证"""
        try:
            if not config.proxy.auth_required:
                return True
                
            if mechanism.upper() not in ['LOGIN', 'PLAIN']:
                logger.warning(f"不支持的认证机制: {mechanism}")
                return False
                
            # 这里可以实现更复杂的认证逻辑
            # 目前只支持简单的用户名密码验证
            return True
            
        except Exception as e:
            logger.error(f"认证处理失败: {e}")
            return False

    async def auth_LOGIN(self, server: SMTP, session: dict, args: bytes) -> bool:
        """处理LOGIN认证"""
        return await self._authenticate(server, session, args)
        
    async def auth_PLAIN(self, server: SMTP, session: dict, args: bytes) -> bool:
        """处理PLAIN认证"""
        return await self._authenticate(server, session, args)
        
    async def _authenticate(self, server: SMTP, session: dict, args: bytes) -> bool:
        """通用认证处理"""
        try:
            if not config.proxy.auth_required:
                return True
                
            # 解析认证参数
            if isinstance(args, bytes):
                args = args.decode('utf-8')
                
            # 简单的用户名密码验证
            if not self.valid_users:
                logger.warning("未配置认证用户")
                return False
                
            # 这里应该根据认证机制解析用户名和密码
            # 简化实现，实际应该根据认证机制解析
            username = config.proxy.auth_username
            password = config.proxy.auth_password
            
            if username in self.valid_users and self.valid_users[username] == password:
                session['authenticated'] = True
                session['username'] = username
                logger.info(f"用户认证成功: {username}")
                return True
            else:
                logger.warning(f"用户认证失败: {username}")
                return False
                
        except Exception as e:
            logger.error(f"认证处理异常: {e}")
            return False


class EnhancedSMTPProxyHandler(SMTPProxyHandler):
    """增强的SMTP代理处理器，包含认证支持"""
    
    def __init__(self):
        super().__init__()
        self.auth_handler = SMTPAuthHandler()
        
    async def handle_EHLO(self, server: SMTP, session: dict, hostname: str) -> str:
        """处理EHLO命令"""
        try:
            # 返回服务器能力
            capabilities = [
                f"250-{server.hostname} Hello {hostname}",
                "250-PIPELINING",
                "250-SIZE 52428800",  # 50MB
                "250-ENHANCEDSTATUSCODES",
                "250-8BITMIME",
                "250-SMTPUTF8"
            ]
            
            # 添加认证支持
            if config.proxy.auth_required:
                capabilities.append("250-AUTH LOGIN PLAIN")
                
            # 添加STARTTLS支持
            if config.proxy.require_starttls:
                capabilities.append("250-STARTTLS")
                
            capabilities.append("250 CHUNKING")
            
            return "\r\n".join(capabilities)
            
        except Exception as e:
            logger.error(f"处理EHLO失败: {e}")
            return "502 命令未实现"
            
    async def handle_AUTH(self, server: SMTP, session: dict, command: str, arg: str) -> str:
        """处理AUTH命令"""
        try:
            if not config.proxy.auth_required:
                return "530 认证未启用"
                
            # 解析认证命令
            parts = command.split()
            if len(parts) < 2:
                return "501 语法错误"
                
            mechanism = parts[1].upper()
            
            # 调用认证处理器
            auth_method = getattr(self.auth_handler, f"auth_{mechanism}", None)
            if not auth_method:
                return "504 认证机制不支持"
                
            # 执行认证
            success = await auth_method(server, session, arg.encode() if arg else b'')
            if success:
                session['authenticated'] = True
                return "235 2.7.0 认证成功"
            else:
                return "535 5.7.8 认证失败"
                
        except Exception as e:
            logger.error(f"处理AUTH失败: {e}")
            return "451 认证处理错误"
            
    async def handle_MAIL(self, server: SMTP, session: dict, command: str, from_addr: str) -> str:
        """处理MAIL命令"""
        try:
            # 检查认证
            if config.proxy.auth_required and not session.get('authenticated'):
                return "530 5.7.0 需要认证"
                
            return await super().handle_MAIL(server, session, command, from_addr)
            
        except Exception as e:
            logger.error(f"处理MAIL失败: {e}")
            return "451 处理命令时发生错误"


async def create_smtp_proxy_server() -> SMTPProxyServer:
    """创建SMTP代理服务器实例"""
    server = SMTPProxyServer()
    # 使用增强的处理器
    server.handler = EnhancedSMTPProxyHandler()
    return server


# 全局SMTP代理服务器实例
_global_smtp_server: Optional[SMTPProxyServer] = None


async def get_smtp_proxy_server() -> SMTPProxyServer:
    """获取全局SMTP代理服务器实例（单例模式）"""
    global _global_smtp_server
    if _global_smtp_server is None:
        _global_smtp_server = await create_smtp_proxy_server()
    return _global_smtp_server


async def close_smtp_proxy_server():
    """关闭全局SMTP代理服务器"""
    global _global_smtp_server
    if _global_smtp_server:
        await _global_smtp_server.stop()
        _global_smtp_server = None
