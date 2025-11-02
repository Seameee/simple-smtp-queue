import time
import uuid
from typing import List, Dict, Any
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import message_from_bytes
import email.utils


@dataclass
class EmailMessageData:
    """邮件消息数据模型"""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_addr: str = ""
    to_addrs: List[str] = field(default_factory=list)
    message_headers: Dict[str, str] = field(default_factory=dict)
    message_body: str = ""
    created_at: float = field(default_factory=time.time)
    retry_count: int = 0
    last_retry_at: float = 0
    status: str = "pending"  # pending, sending, sent, failed
    
    @classmethod
    def from_smtp_message(cls, envelope, message_data: bytes) -> 'EmailMessageData':
        """从SMTP消息创建邮件数据"""
        # 解析邮件消息
        message = message_from_bytes(message_data)
        
        # 提取发件人
        from_addr = envelope.mail_from or ""
        
        # 提取收件人
        to_addrs = list(envelope.rcpt_tos) if envelope.rcpt_tos else []
        
        # 提取邮件头
        message_headers = {}
        for header_name in message.keys():
            message_headers[header_name] = message[header_name]
        
        # 提取邮件正文
        message_body = ""
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == "text/plain":
                    message_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    break
                elif part.get_content_type() == "text/html":
                    message_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
        else:
            message_body = message.get_payload(decode=True).decode('utf-8', errors='ignore')
        
        return cls(
            from_addr=from_addr,
            to_addrs=to_addrs,
            message_headers=message_headers,
            message_body=message_body
        )
    
    def to_smtp_message(self) -> bytes:
        """将邮件数据转换为SMTP消息字节"""
        # 创建邮件消息
        if 'Content-Type' in self.message_headers and 'multipart' in self.message_headers['Content-Type']:
            msg = MIMEMultipart()
        else:
            msg = MIMEText(self.message_body, 'plain', 'utf-8')
        
        # 设置邮件头
        for header_name, header_value in self.message_headers.items():
            if header_name.lower() not in ['content-type', 'content-transfer-encoding']:
                msg[header_name] = header_value
        
        # 确保必要的邮件头
        if 'From' not in msg:
            msg['From'] = self.from_addr
        if 'To' not in msg:
            msg['To'] = ', '.join(self.to_addrs)
        if 'Date' not in msg:
            msg['Date'] = email.utils.formatdate()
        if 'Message-ID' not in msg:
            msg['Message-ID'] = email.utils.make_msgid()
        
        return msg.as_bytes()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'id': self.id,
            'from_addr': self.from_addr,
            'to_addrs': self.to_addrs,
            'message_headers': self.message_headers,
            'message_body': self.message_body,
            'created_at': self.created_at,
            'retry_count': self.retry_count,
            'last_retry_at': self.last_retry_at,
            'status': self.status
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmailMessageData':
        """从字典创建实例"""
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            from_addr=data.get('from_addr', ''),
            to_addrs=data.get('to_addrs', []),
            message_headers=data.get('message_headers', {}),
            message_body=data.get('message_body', ''),
            created_at=data.get('created_at', time.time()),
            retry_count=data.get('retry_count', 0),
            last_retry_at=data.get('last_retry_at', 0),
            status=data.get('status', 'pending')
        )
    
    def increment_retry(self) -> None:
        """增加重试次数"""
        self.retry_count += 1
        self.last_retry_at = time.time()
    
    def can_retry(self, max_retries: int) -> bool:
        """检查是否可以进行重试"""
        return self.retry_count < max_retries
    
    def get_retry_delay(self, base_delay: int) -> int:
        """计算重试延迟时间（指数退避）"""
        return base_delay * (2 ** self.retry_count)


@dataclass
class SendingResult:
    """发送结果模型"""
    
    success: bool
    message_id: str
    error_message: str = ""
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'success': self.success,
            'message_id': self.message_id,
            'error_message': self.error_message,
            'retry_count': self.retry_count
        }
