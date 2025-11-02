import os
import yaml
from typing import Dict, Any, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class SMTPConfig:
    """SMTP服务器配置"""
    local_host: str = "0.0.0.0"
    local_port: int = 1025
    auth_required: bool = False


@dataclass
class TargetSMTPConfig:
    """目标SMTP服务器配置"""
    host: str = "smtp.gmail.com"
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True


@dataclass
class QueueConfig:
    """队列配置"""
    backend: str = "redis"  # redis 或 sqlite
    redis_url: str = "redis://localhost:6379"
    sqlite_path: str = "/data/queue.db"


@dataclass
class RateLimitConfig:
    """速率限制配置"""
    messages_per_second: int = 10
    max_retries: int = 3
    retry_delay: int = 60  # 秒


@dataclass
class LogConfig:
    """日志配置"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class Config:
    """配置管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file
        self._config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self):
        """加载配置，优先级：环境变量 > 配置文件 > 默认值"""
        # 从配置文件加载
        file_config = {}
        if self.config_file and os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                file_config = yaml.safe_load(f) or {}

        # 合并配置，环境变量优先级最高
        self._config = {
            'smtp': self._load_smtp_config(file_config.get('smtp', {})),
            'target_smtp': self._load_target_smtp_config(file_config.get('target_smtp', {})),
            'queue': self._load_queue_config(file_config.get('queue', {})),
            'rate_limit': self._load_rate_limit_config(file_config.get('rate_limit', {})),
            'log': self._load_log_config(file_config.get('log', {}))
        }

    def _load_smtp_config(self, file_config: Dict) -> SMTPConfig:
        """加载SMTP配置"""
        return SMTPConfig(
            local_host=os.getenv('SMTP_LOCAL_HOST', file_config.get('local_host', '0.0.0.0')),
            local_port=int(os.getenv('SMTP_LOCAL_PORT', file_config.get('local_port', 1025))),
            auth_required=os.getenv('SMTP_AUTH_REQUIRED', str(file_config.get('auth_required', False))).lower() == 'true'
        )

    def _load_target_smtp_config(self, file_config: Dict) -> TargetSMTPConfig:
        """加载目标SMTP配置"""
        return TargetSMTPConfig(
            host=os.getenv('TARGET_SMTP_HOST', file_config.get('host', 'smtp.gmail.com')),
            port=int(os.getenv('TARGET_SMTP_PORT', file_config.get('port', 587))),
            username=os.getenv('TARGET_SMTP_USERNAME', file_config.get('username', '')),
            password=os.getenv('TARGET_SMTP_PASSWORD', file_config.get('password', '')),
            use_tls=os.getenv('TARGET_SMTP_USE_TLS', str(file_config.get('use_tls', True))).lower() == 'true'
        )

    def _load_queue_config(self, file_config: Dict) -> QueueConfig:
        """加载队列配置"""
        return QueueConfig(
            backend=os.getenv('QUEUE_BACKEND', file_config.get('backend', 'redis')),
            redis_url=os.getenv('QUEUE_REDIS_URL', file_config.get('redis_url', 'redis://localhost:6379')),
            sqlite_path=os.getenv('QUEUE_SQLITE_PATH', file_config.get('sqlite_path', '/data/queue.db'))
        )

    def _load_rate_limit_config(self, file_config: Dict) -> RateLimitConfig:
        """加载速率限制配置"""
        return RateLimitConfig(
            messages_per_second=int(os.getenv('RATE_LIMIT_MESSAGES_PER_SECOND', 
                                            file_config.get('messages_per_second', 10))),
            max_retries=int(os.getenv('RATE_LIMIT_MAX_RETRIES', 
                                    file_config.get('max_retries', 3))),
            retry_delay=int(os.getenv('RATE_LIMIT_RETRY_DELAY', 
                                    file_config.get('retry_delay', 60)))
        )

    def _load_log_config(self, file_config: Dict) -> LogConfig:
        """加载日志配置"""
        return LogConfig(
            level=os.getenv('LOG_LEVEL', file_config.get('level', 'INFO')),
            format=os.getenv('LOG_FORMAT', file_config.get('format', 
                                                         '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        )

    @property
    def smtp(self) -> SMTPConfig:
        return self._config['smtp']

    @property
    def target_smtp(self) -> TargetSMTPConfig:
        return self._config['target_smtp']

    @property
    def queue(self) -> QueueConfig:
        return self._config['queue']

    @property
    def rate_limit(self) -> RateLimitConfig:
        return self._config['rate_limit']

    @property
    def log(self) -> LogConfig:
        return self._config['log']


# 全局配置实例
config = Config()
