import asyncio
import logging
import time
import psutil
import json
from typing import Dict, Any, Optional
from datetime import datetime
from app.config import config
from app.queue_manager import get_queue_manager

logger = logging.getLogger(__name__)


class SystemMetrics:
    """系统指标收集器"""
    
    @staticmethod
    def get_cpu_usage() -> float:
        """获取CPU使用率"""
        return psutil.cpu_percent(interval=1)
    
    @staticmethod
    def get_memory_usage() -> Dict[str, Any]:
        """获取内存使用情况"""
        memory = psutil.virtual_memory()
        return {
            'total': memory.total,
            'available': memory.available,
            'used': memory.used,
            'percent': memory.percent
        }
    
    @staticmethod
    def get_disk_usage() -> Dict[str, Any]:
        """获取磁盘使用情况"""
        disk = psutil.disk_usage('/')
        return {
            'total': disk.total,
            'used': disk.used,
            'free': disk.free,
            'percent': disk.percent
        }
    
    @staticmethod
    def get_network_io() -> Dict[str, Any]:
        """获取网络IO"""
        net_io = psutil.net_io_counters()
        return {
            'bytes_sent': net_io.bytes_sent,
            'bytes_recv': net_io.bytes_recv,
            'packets_sent': net_io.packets_sent,
            'packets_recv': net_io.packets_recv
        }


class QueueMetrics:
    """队列指标收集器"""
    
    def __init__(self):
        self.queue_manager = None
        
    async def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        if not self.queue_manager:
            self.queue_manager = await get_queue_manager()
            
        try:
            stats = await self.queue_manager.get_stats()
            return stats
        except Exception as e:
            logger.error(f"获取队列统计信息失败: {e}")
            return {}


class EmailMetrics:
    """邮件指标收集器"""
    
    def __init__(self):
        self.sent_count = 0
        self.failed_count = 0
        self.retry_count = 0
        self.start_time = time.time()
        self.lock = asyncio.Lock()
        
    async def record_sent(self):
        """记录发送成功"""
        async with self.lock:
            self.sent_count += 1
            
    async def record_failed(self):
        """记录发送失败"""
        async with self.lock:
            self.failed_count += 1
            
    async def record_retry(self):
        """记录重试"""
        async with self.lock:
            self.retry_count += 1
            
    def get_stats(self) -> Dict[str, Any]:
        """获取邮件统计信息"""
        uptime = time.time() - self.start_time
        total_attempts = self.sent_count + self.failed_count
        
        return {
            'sent_count': self.sent_count,
            'failed_count': self.failed_count,
            'retry_count': self.retry_count,
            'total_attempts': total_attempts,
            'success_rate': self.sent_count / total_attempts if total_attempts > 0 else 0,
            'uptime_seconds': uptime,
            'emails_per_minute': self.sent_count / (uptime / 60) if uptime > 0 else 0
        }


class HealthChecker:
    """健康检查器"""
    
    def __init__(self, queue_metrics: QueueMetrics, email_metrics: EmailMetrics):
        self.queue_metrics = queue_metrics
        self.email_metrics = email_metrics
        self.last_check_time = time.time()
        
    async def check_health(self) -> Dict[str, Any]:
        """执行健康检查"""
        try:
            # 收集系统指标
            system_metrics = {
                'cpu_usage': SystemMetrics.get_cpu_usage(),
                'memory_usage': SystemMetrics.get_memory_usage(),
                'disk_usage': SystemMetrics.get_disk_usage(),
                'network_io': SystemMetrics.get_network_io()
            }
            
            # 收集队列指标
            queue_stats = await self.queue_metrics.get_queue_stats()
            
            # 收集邮件指标
            email_stats = self.email_metrics.get_stats()
            
            # 计算总体健康状态
            health_status = self._calculate_health_status(
                system_metrics, queue_stats, email_stats
            )
            
            return {
                'timestamp': datetime.now().isoformat(),
                'status': health_status,
                'system': system_metrics,
                'queue': queue_stats,
                'email': email_stats
            }
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'status': 'unhealthy',
                'error': str(e)
            }
    
    def _calculate_health_status(self, system_metrics: Dict, queue_stats: Dict, email_stats: Dict) -> str:
        """计算总体健康状态"""
        # 检查系统资源
        cpu_usage = system_metrics['cpu_usage']
        memory_usage = system_metrics['memory_usage']['percent']
        disk_usage = system_metrics['disk_usage']['percent']
        
        if cpu_usage > 90 or memory_usage > 90 or disk_usage > 90:
            return 'unhealthy'
        elif cpu_usage > 80 or memory_usage > 80 or disk_usage > 80:
            return 'degraded'
            
        # 检查队列状态
        pending_count = queue_stats.get('pending_count', 0)
        if pending_count > 1000:
            return 'degraded'
            
        # 检查邮件发送成功率
        success_rate = email_stats.get('success_rate', 1.0)
        if success_rate < 0.5:
            return 'unhealthy'
        elif success_rate < 0.8:
            return 'degraded'
            
        return 'healthy'


class MetricsCollector:
    """指标收集器"""
    
    def __init__(self):
        self.queue_metrics = QueueMetrics()
        self.email_metrics = EmailMetrics()
        self.health_checker = HealthChecker(self.queue_metrics, self.email_metrics)
        self.metrics_history: list = []
        self.max_history_size = 1000
        
    async def collect_metrics(self) -> Dict[str, Any]:
        """收集所有指标"""
        health_status = await self.health_checker.check_health()
        
        # 添加到历史记录
        self.metrics_history.append(health_status)
        if len(self.metrics_history) > self.max_history_size:
            self.metrics_history.pop(0)
            
        return health_status
    
    def get_metrics_history(self, limit: int = 100) -> list:
        """获取指标历史记录"""
        return self.metrics_history[-limit:] if limit else self.metrics_history.copy()
    
    def get_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        if not self.metrics_history:
            return {}
            
        recent_metrics = self.metrics_history[-10:]  # 最近10个数据点
        
        # 计算平均值
        cpu_usage = sum(m['system']['cpu_usage'] for m in recent_metrics) / len(recent_metrics)
        memory_usage = sum(m['system']['memory_usage']['percent'] for m in recent_metrics) / len(recent_metrics)
        
        # 统计健康状态
        status_counts = {}
        for metric in recent_metrics:
            status = metric['status']
            status_counts[status] = status_counts.get(status, 0) + 1
            
        return {
            'average_cpu_usage': cpu_usage,
            'average_memory_usage': memory_usage,
            'recent_status_counts': status_counts,
            'total_metrics_collected': len(self.metrics_history)
        }


class MonitoringServer:
    """监控服务器"""
    
    def __init__(self):
        self.metrics_collector = MetricsCollector()
        self.collection_task: Optional[asyncio.Task] = None
        self.is_running = False
        
    async def start(self):
        """启动监控服务器"""
        self.is_running = True
        self.collection_task = asyncio.create_task(self._collect_metrics_loop())
        logger.info("监控服务器已启动")
        
    async def stop(self):
        """停止监控服务器"""
        self.is_running = False
        if self.collection_task:
            self.collection_task.cancel()
            try:
                await self.collection_task
            except asyncio.CancelledError:
                pass
        logger.info("监控服务器已停止")
        
    async def _collect_metrics_loop(self):
        """指标收集循环"""
        while self.is_running:
            try:
                await self.metrics_collector.collect_metrics()
                await asyncio.sleep(config.monitoring.collection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"指标收集异常: {e}")
                await asyncio.sleep(5)  # 异常后等待5秒再继续
    
    async def get_current_metrics(self) -> Dict[str, Any]:
        """获取当前指标"""
        return await self.metrics_collector.collect_metrics()
    
    async def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        metrics = await self.metrics_collector.collect_metrics()
        return {
            'status': metrics['status'],
            'timestamp': metrics['timestamp']
        }


# 全局监控服务器实例
_global_monitoring_server: Optional[MonitoringServer] = None


async def get_monitoring_server() -> MonitoringServer:
    """获取全局监控服务器实例（单例模式）"""
    global _global_monitoring_server
    if _global_monitoring_server is None:
        _global_monitoring_server = MonitoringServer()
    return _global_monitoring_server


async def close_monitoring_server():
    """关闭全局监控服务器"""
    global _global_monitoring_server
    if _global_monitoring_server:
        await _global_monitoring_server.stop()
        _global_monitoring_server = None
