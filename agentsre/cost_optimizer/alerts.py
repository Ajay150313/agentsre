"""
Budget alerts for cost control

Author: Ajay Devineni
License: MIT
"""


class BudgetAlert:
    """Budget alert"""
    
    def __init__(self, severity: str, message: str, current: float, limit: float):
        self.severity = severity
        self.message = message
        self.current = current
        self.limit = limit


class CostAlertManager:
    """Manage cost alerts"""
    
    def __init__(self):
        self.alerts = []
        self.handlers = []
    
    def add_handler(self, handler):
        """Add alert handler"""
        self.handlers.append(handler)
    
    def send_alert(self, alert: BudgetAlert):
        """Send alert"""
        self.alerts.append(alert)
        for handler in self.handlers:
            try:
                handler(alert)
            except Exception as e:
                print(f"Alert handler error: {e}")
