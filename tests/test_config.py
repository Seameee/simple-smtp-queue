import os
import pytest
from app.config import Config, get_config, setup_logging


class TestConfig:
    """配置管理测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = Config()
        assert config.log_level == "INFO"
        assert config.proxy_host == "0.0.0.0"
        assert config.proxy_port == 8025
        assert config.rate_limit == 10
        assert config.rate_window == 60
        
    def test_environment_override(self):
        """测试环境变量覆盖"""
        os.environ["SMTP_QUEUE_LOG_LEVEL"] = "DEBUG"
        os.environ["SMTP_QUEUE_RATE_LIMIT"] = "20"
        
        config = Config()
        assert config.log_level == "DEBUG"
        assert config.rate_limit == 20
        
        # 清理环境变量
        del os.environ["SMTP_QUEUE_LOG_LEVEL"]
        del os.environ["SMTP_QUEUE_RATE_LIMIT"]
        
    def test_get_config_singleton(self):
        """测试配置单例模式"""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2
        
    def test_setup_logging(self):
        """测试日志设置"""
        # 这个测试主要是确保没有异常抛出
        try:
            setup_logging()
            assert True
        except Exception:
            pytest.fail("setup_logging raised an exception")


if __name__ == "__main__":
    pytest.main([__file__])
