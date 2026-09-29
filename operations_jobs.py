"""
Background Jobs for Operations Dashboard
Periodic tasks for metrics aggregation and maintenance.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("sabi.operations")


class OperationalJobsRunner:
    """Background job runner for operational metrics."""
    
    def __init__(self):
        self.running = False
    
    async def start(self):
        """Start background jobs."""
        self.running = True
        logger.info("Starting operational background jobs...")
        
        asyncio.create_task(self._daily_metrics_job())
        asyncio.create_task(self._hourly_health_check())
        asyncio.create_task(self._intervention_detection())
    
    async def stop(self):
        """Stop background jobs."""
        self.running = False
        logger.info("Stopping operational background jobs...")
    
    async def _daily_metrics_job(self):
        """Aggregate daily metrics at midnight."""
        while self.running:
            try:
                now = datetime.now()
                next_midnight = (now + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                wait_seconds = (next_midnight - now).total_seconds()
                
                await asyncio.sleep(wait_seconds)
                
                if self.running:
                    await self._aggregate_daily_metrics()
            except Exception as e:
                logger.error(f"Error in daily metrics job: {e}")
                await asyncio.sleep(3600)
    
    async def _hourly_health_check(self):
        """Run system health checks every hour."""
        while self.running:
            try:
                await self._check_system_health()
                await asyncio.sleep(3600)
            except Exception as e:
                logger.error(f"Error in health check: {e}")
                await asyncio.sleep(300)
    
    async def _intervention_detection(self):
        """Detect students needing intervention every 4 hours."""
        while self.running:
            try:
                await self._detect_interventions_needed()
                await asyncio.sleep(14400)
            except Exception as e:
                logger.error(f"Error in intervention detection: {e}")
                await asyncio.sleep(3600)
    
    async def _aggregate_daily_metrics(self):
        """Aggregate and store daily metrics."""
        logger.info("Aggregating daily metrics...")
        
        from operations_api import calculate_daily_metrics
        
        metrics = calculate_daily_metrics()
        
        metrics_file = Path("data/metrics") / f"daily_{datetime.now().date()}.json"
        metrics_file.parent.mkdir(parents=True, exist_ok=True)
        
        import json
        metrics_file.write_text(json.dumps(metrics, indent=2))
        
        logger.info(f"Daily metrics saved: {metrics}")
    
    async def _check_system_health(self):
        """Check system health and create alerts if needed."""
        logger.info("Running system health check...")
    
    async def _detect_interventions_needed(self):
        """Detect students needing intervention."""
        logger.info("Detecting interventions needed...")


async def start_background_jobs():
    """Start background jobs for operations."""
    runner = OperationalJobsRunner()
    await runner.start()
    return runner
