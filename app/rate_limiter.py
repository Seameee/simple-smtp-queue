import asyncio
import time
import logging
from typing import Optional
from app.config import config

logger = logging.getLogger(__name__)


class RateLimiter:
    """速率限制器基类"""
    
    async def acquire(self) -> None:
        """获取发送许可，如果超过限制则等待"""
        raise NotImplementedError

    async def close(self):
        """关闭资源"""
        pass


class TokenBucketRateLimiter(RateLimiter):
    """令牌桶速率限制器"""
    
    def __init__(self):
        self.tokens = config.rate_limit.max_tokens
        self.last_refill_time = time.time()
        self.lock = asyncio.Lock()
        
    async def _refill_tokens(self):
        """补充令牌"""
        now = time.time()
        time_passed = now - self.last_refill_time
        tokens_to_add = time_passed * config.rate_limit.tokens_per_second
        
        if tokens_to_add > 0:
            self.tokens = min(
                config.rate_limit.max_tokens,
                self.tokens + tokens_to_add
            )
            self.last_refill_time = now

    async def acquire(self) -> None:
        """获取发送许可"""
        async with self.lock:
            while True:
                await self._refill_tokens()
                
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                    
                # 计算需要等待的时间
                tokens_needed = 1 - self.tokens
                wait_time = tokens_needed / config.rate_limit.tokens_per_second
                
                if wait_time > 0:
                    logger.debug(f"速率限制，等待 {wait_time:.2f} 秒")
                    await asyncio.sleep(wait_time)


class FixedWindowRateLimiter(RateLimiter):
    """固定窗口速率限制器"""
    
    def __init__(self):
        self.window_start = time.time()
        self.request_count = 0
        self.lock = asyncio.Lock()
        
    async def acquire(self) -> None:
        """获取发送许可"""
        async with self.lock:
            now = time.time()
            
            # 检查是否进入新的时间窗口
            if now - self.window_start >= config.rate_limit.window_seconds:
                self.window_start = now
                self.request_count = 0
                
            # 检查是否超过窗口限制
            if self.request_count >= config.rate_limit.requests_per_window:
                # 计算需要等待的时间
                wait_time = self.window_start + config.rate_limit.window_seconds - now
                if wait_time > 0:
                    logger.debug(f"速率限制，等待 {wait_time:.2f} 秒")
                    await asyncio.sleep(wait_time)
                    
                # 重置窗口
                self.window_start = time.time()
                self.request_count = 0
                
            self.request_count += 1


class LeakyBucketRateLimiter(RateLimiter):
    """漏桶速率限制器"""
    
    def __init__(self):
        self.bucket_capacity = config.rate_limit.bucket_capacity
        self.leak_rate = config.rate_limit.leak_rate
        self.current_volume = 0
        self.last_leak_time = time.time()
        self.lock = asyncio.Lock()
        
    async def _leak_bucket(self):
        """漏桶漏水"""
        now = time.time()
        time_passed = now - self.last_leak_time
        leaked_amount = time_passed * self.leak_rate
        
        if leaked_amount > 0:
            self.current_volume = max(0, self.current_volume - leaked_amount)
            self.last_leak_time = now

    async def acquire(self) -> None:
        """获取发送许可"""
        async with self.lock:
            while True:
                await self._leak_bucket()
                
                # 检查桶中是否有空间
                if self.current_volume < self.bucket_capacity:
                    self.current_volume += 1
                    return
                    
                # 计算需要等待的时间
                overflow = self.current_volume - self.bucket_capacity + 1
                wait_time = overflow / self.leak_rate
                
                if wait_time > 0:
                    logger.debug(f"速率限制，等待 {wait_time:.2f} 秒")
                    await asyncio.sleep(wait_time)


class CompositeRateLimiter(RateLimiter):
    """组合速率限制器，可以同时应用多种限制策略"""
    
    def __init__(self):
        self.limiters = []
        
        # 根据配置创建相应的限制器
        if config.rate_limit.strategy == "token_bucket":
            self.limiters.append(TokenBucketRateLimiter())
        elif config.rate_limit.strategy == "fixed_window":
            self.limiters.append(FixedWindowRateLimiter())
        elif config.rate_limit.strategy == "leaky_bucket":
            self.limiters.append(LeakyBucketRateLimiter())
        elif config.rate_limit.strategy == "composite":
            # 可以组合多种策略
            if config.rate_limit.enable_token_bucket:
                self.limiters.append(TokenBucketRateLimiter())
            if config.rate_limit.enable_fixed_window:
                self.limiters.append(FixedWindowRateLimiter())
            if config.rate_limit.enable_leaky_bucket:
                self.limiters.append(LeakyBucketRateLimiter())
        
        # 如果没有配置任何限制器，使用令牌桶作为默认
        if not self.limiters:
            self.limiters.append(TokenBucketRateLimiter())

    async def acquire(self) -> None:
        """获取发送许可，需要满足所有限制器的条件"""
        for limiter in self.limiters:
            await limiter.acquire()

    async def close(self):
        """关闭所有限制器"""
        for limiter in self.limiters:
            await limiter.close()


async def create_rate_limiter() -> RateLimiter:
    """创建速率限制器实例"""
    limiter = CompositeRateLimiter()
    return limiter


# 全局速率限制器实例
_global_rate_limiter: Optional[RateLimiter] = None


async def get_rate_limiter() -> RateLimiter:
    """获取全局速率限制器实例（单例模式）"""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = await create_rate_limiter()
    return _global_rate_limiter


async def close_rate_limiter():
    """关闭全局速率限制器"""
    global _global_rate_limiter
    if _global_rate_limiter:
        await _global_rate_limiter.close()
        _global_rate_limiter = None
