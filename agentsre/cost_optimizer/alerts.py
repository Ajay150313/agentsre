"""
Budget alerts and monitoring for cost control

Author: Ajay Devineni
License: MIT
"""

from dataclasses import dataclass
from typing import Callable, Optional
from datetime import datetime
from enum import Enum


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class BudgetAlert:
    """Budget alert"""
    severity: AlertSeverity
    message: str
    current_spend: float
    budget_limit: float
    timestamp: datetime


class AlertManager:
    """Manage budget alerts"""
    
    def __init__(self):
        self.alerts = []
        self.handlers = []
    
    def add_handler(self, handler: Callable) -> None:
        """Add alert handler (e.g., Slack, email)"""
        self.handlers.append(handler)
    
    def send_alert(self, alert: BudgetAlert) -> None:
        """Send alert to all handlers"""
        self.alerts.append(alert)
        
        for handler in self.handlers:
            try:
                handler(alert)
            except Exception as e:
                print(f"Alert handler failed: {e}")
