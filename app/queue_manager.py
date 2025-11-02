import asyncio
import json
import logging
import time
import aiosqlite
import aioredis
from typing import List, Optional
from app.models import EmailMessageData
from app.config import config

logger = logging.getLogger(__name__)


class QueueManager:
    """队列管理器基类"""
    
    async def enqueue(self, message: EmailMessageData) -> bool:
        """将消息加入队列"""
        raise NotImplementedError

    async def dequeue(self) -> Optional[EmailMessageData]:
        """从队列中取出消息"""
        raise NotImplementedError

    async def get_queue_size(self) -> int:
        """获取队列大小"""
        raise NotImplementedError

    async def close(self):
        """关闭连接"""
        pass


class RedisQueueManager(QueueManager):
    """Redis队列管理器"""
    
    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self.queue_key = "smtp_queue"
        self.processing_key = "smtp_processing"
        
    async def connect(self):
        """连接到Redis"""
        try:
            self.redis = await aioredis.from_url(
                config.queue.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info(f"已连接到Redis: {config.queue.redis_url}")
        except Exception as e:
            logger.error(f"连接Redis失败: {e}")
            raise

    async def enqueue(self, message: EmailMessageData) -> bool:
        """将消息加入Redis队列"""
        try:
            message_data = json.dumps(message.to_dict())
            await self.redis.lpush(self.queue_key, message_data)
            logger.debug(f"消息已加入队列: {message.id}")
            return True
        except Exception as e:
            logger.error(f"加入队列失败: {e}")
            return False

    async def dequeue(self) -> Optional[EmailMessageData]:
        """从Redis队列中取出消息"""
        try:
            # 使用RPOPLPUSH实现可靠队列
            message_data = await self.redis.rpoplpush(self.queue_key, self.processing_key)
            if message_data:
                data = json.loads(message_data)
                message = EmailMessageData.from_dict(data)
                logger.debug(f"从队列取出消息: {message.id}")
                return message
            return None
        except Exception as e:
            logger.error(f"从队列取出消息失败: {e}")
            return None

    async def mark_completed(self, message_id: str):
        """标记消息处理完成"""
        try:
            # 从处理中队列移除
            processing_items = await self.redis.lrange(self.processing_key, 0, -1)
            for item in processing_items:
                data = json.loads(item)
                if data['id'] == message_id:
                    await self.redis.lrem(self.processing_key, 1, item)
                    break
        except Exception as e:
            logger.error(f"标记消息完成失败: {e}")

    async def get_queue_size(self) -> int:
        """获取队列大小"""
        try:
            return await self.redis.llen(self.queue_key)
        except Exception as e:
            logger.error(f"获取队列大小失败: {e}")
            return 0

    async def get_processing_size(self) -> int:
        """获取处理中队列大小"""
        try:
            return await self.redis.llen(self.processing_key)
        except Exception as e:
            logger.error(f"获取处理中队列大小失败: {e}")
            return 0

    async def close(self):
        """关闭Redis连接"""
        if self.redis:
            await self.redis.close()


class SQLiteQueueManager(QueueManager):
    """SQLite队列管理器"""
    
    def __init__(self):
        self.db: Optional[aiosqlite.Connection] = None
        
    async def connect(self):
        """连接到SQLite数据库"""
        try:
            self.db = await aiosqlite.connect(config.queue.sqlite_path)
            await self._create_table()
            logger.info(f"已连接到SQLite: {config.queue.sqlite_path}")
        except Exception as e:
            logger.error(f"连接SQLite失败: {e}")
            raise

    async def _create_table(self):
        """创建消息表"""
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS smtp_queue (
                id TEXT PRIMARY KEY,
                from_addr TEXT NOT NULL,
                to_addrs TEXT NOT NULL,
                message_headers TEXT NOT NULL,
                message_body TEXT NOT NULL,
                created_at REAL NOT NULL,
                retry_count INTEGER DEFAULT 0,
                last_retry_at REAL,
                status TEXT DEFAULT 'pending',
                processing INTEGER DEFAULT 0
            )
        ''')
        await self.db.commit()

    async def enqueue(self, message: EmailMessageData) -> bool:
        """将消息加入SQLite队列"""
        try:
            message_dict = message.to_dict()
            await self.db.execute('''
                INSERT INTO smtp_queue 
                (id, from_addr, to_addrs, message_headers, message_body, created_at, retry_count, last_retry_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                message_dict['id'],
                message_dict['from_addr'],
                json.dumps(message_dict['to_addrs']),
                json.dumps(message_dict['message_headers']),
                message_dict['message_body'],
                message_dict['created_at'],
                message_dict['retry_count'],
                message_dict['last_retry_at'],
                message_dict['status']
            ))
            await self.db.commit()
            logger.debug(f"消息已加入队列: {message.id}")
            return True
        except Exception as e:
            logger.error(f"加入队列失败: {e}")
            return False

    async def dequeue(self) -> Optional[EmailMessageData]:
        """从SQLite队列中取出消息"""
        try:
            async with self.db.execute('''
                SELECT * FROM smtp_queue 
                WHERE processing = 0 AND status = 'pending'
                ORDER BY created_at ASC 
                LIMIT 1
            ''') as cursor:
                row = await cursor.fetchone()
                if row:
                    # 标记为处理中
                    await self.db.execute(
                        'UPDATE smtp_queue SET processing = 1 WHERE id = ?',
                        (row[0],)
                    )
                    await self.db.commit()
                    
                    # 构建消息对象
                    message_data = {
                        'id': row[0],
                        'from_addr': row[1],
                        'to_addrs': json.loads(row[2]),
                        'message_headers': json.loads(row[3]),
                        'message_body': row[4],
                        'created_at': row[5],
                        'retry_count': row[6],
                        'last_retry_at': row[7],
                        'status': row[8]
                    }
                    message = EmailMessageData.from_dict(message_data)
                    logger.debug(f"从队列取出消息: {message.id}")
                    return message
            return None
        except Exception as e:
            logger.error(f"从队列取出消息失败: {e}")
            return None

    async def mark_completed(self, message_id: str, status: str = "sent"):
        """标记消息处理完成"""
        try:
            await self.db.execute('''
                UPDATE smtp_queue 
                SET status = ?, processing = 0 
                WHERE id = ?
            ''', (status, message_id))
            await self.db.commit()
        except Exception as e:
            logger.error(f"标记消息完成失败: {e}")

    async def update_retry_count(self, message_id: str, retry_count: int):
        """更新重试次数"""
        try:
            await self.db.execute('''
                UPDATE smtp_queue 
                SET retry_count = ?, last_retry_at = ?
                WHERE id = ?
            ''', (retry_count, time.time(), message_id))
            await self.db.commit()
        except Exception as e:
            logger.error(f"更新重试次数失败: {e}")

    async def get_queue_size(self) -> int:
        """获取队列大小"""
        try:
            async with self.db.execute('''
                SELECT COUNT(*) FROM smtp_queue 
                WHERE processing = 0 AND status = 'pending'
            ''') as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error(f"获取队列大小失败: {e}")
            return 0

    async def close(self):
        """关闭SQLite连接"""
        if self.db:
            await self.db.close()


async def create_queue_manager() -> QueueManager:
    """创建队列管理器实例"""
    if config.queue.backend == "redis":
        manager = RedisQueueManager()
    else:
        manager = SQLiteQueueManager()
    
    await manager.connect()
    return manager
