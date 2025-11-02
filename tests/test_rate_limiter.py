import asyncio
import time
import pytest
from app.rate_limiter import RateLimiter, get_rate_limiter, close_rate_limiter


class TestRateLimiter:
    """速率限制器测试"""
    
    @pytest.fixture
    async def rate_limiter(self):
        """创建速率限制器实例"""
        limiter = RateLimiter(rate_limit=2, rate_window=1)  # 每秒2次
        await limiter.initialize()
        yield limiter
        await limiter.close()
        
    async def test_acquire_within_limit(self, rate_limiter):
        """测试在限制内获取许可"""
        # 第一次获取应该成功
        result1 = await rate_limiter.acquire("test_key")
        assert result1 is True
        
        # 第二次获取应该成功
        result2 = await rate_limiter.acquire("test_key")
        assert result2 is True
        
    async def test_acquire_exceed_limit(self, rate_limiter):
        """测试超过限制时获取许可"""
        # 获取两次许可（达到限制）
        await rate_limiter.acquire("test_key")
        await rate_limiter.acquire("test_key")
        
        # 第三次获取应该失败
        result = await rate_limiter.acquire("test_key")
        assert result is False
        
    async def test_acquire_after_window(self, rate_limiter):
        """测试窗口期后可以重新获取许可"""
        # 获取两次许可（达到限制）
        await rate_limiter.acquire("test_key")
        await rate_limiter.acquire("test_key")
        
        # 第三次获取应该失败
        result1 = await rate_limiter.acquire("test_key")
        assert result1 is False
        
        # 等待窗口期结束
        await asyncio.sleep(1.1)
        
        # 现在应该可以再次获取
        result2 = await rate_limiter.acquire("test_key")
        assert result2 is True
        
    async def test_different_keys_independent(self, rate_limiter):
        """测试不同键的速率限制相互独立"""
        # 键1获取两次
        await rate_limiter.acquire("key1")
        await rate_limiter.acquire("key1")
        
        # 键2应该不受影响
        result = await rate_limiter.acquire("key2")
        assert result is True
        
    async def test_get_rate_limiter_singleton(self):
        """测试速率限制器单例模式"""
        limiter1 = await get_rate_limiter()
        limiter2 = await get_rate_limiter()
        assert limiter1 is limiter2
        await close_rate_limiter()


if __name__ == "__main__":
    pytest.main([__file__])
