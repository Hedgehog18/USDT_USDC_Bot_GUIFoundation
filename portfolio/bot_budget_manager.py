from datetime import datetime

from portfolio.models import BotBudget, BotBudgetEvent
from storage.database_manager import DatabaseManager


class BotBudgetManager:
    """Керує внутрішнім бюджетом бота та історією поповнень."""

    def __init__(self, database: DatabaseManager | None = None) -> None:
        self.database = database
        self._budget = BotBudget(usdt_budget=0.0, usdc_budget=0.0, usdc_price=1.0)

        if self.database:
            self._load_from_database()

        if self._budget.total_value <= 0:
            # Стартове тестове поповнення для Demo.
            self.add_deposit(50.0, "USDT", "Стартове Demo-поповнення USDT")
            self.add_deposit(50.0, "USDC", "Стартове Demo-поповнення USDC")

    def get_budget(self) -> BotBudget:
        return self._budget

    def add_deposit(self, amount: float, asset: str, note: str = "") -> BotBudgetEvent:
        if amount <= 0:
            raise ValueError("Сума поповнення має бути більшою за 0.")

        normalized_asset = asset.upper()

        if normalized_asset == "USDT":
            value_usdt = amount
            self._budget.usdt_budget += amount
        elif normalized_asset == "USDC":
            value_usdt = amount * self._budget.usdc_price
            self._budget.usdc_budget += amount
        else:
            raise ValueError("Підтримуються лише USDT або USDC.")

        event = BotBudgetEvent(
            event_type="DEPOSIT",
            asset=normalized_asset,
            amount=amount,
            value_usdt=value_usdt,
            note=note,
            created_at=datetime.utcnow(),
        )

        if self.database:
            self.database.save_bot_budget_event(event)

        return event

    def remove_from_budget(self, amount: float, asset: str, note: str = "") -> BotBudgetEvent:
        if amount <= 0:
            raise ValueError("Сума має бути більшою за 0.")

        normalized_asset = asset.upper()

        if normalized_asset == "USDT":
            if amount > self._budget.usdt_budget:
                raise ValueError("Недостатньо USDT у бюджеті бота.")
            value_usdt = amount
            self._budget.usdt_budget -= amount
        elif normalized_asset == "USDC":
            if amount > self._budget.usdc_budget:
                raise ValueError("Недостатньо USDC у бюджеті бота.")
            value_usdt = amount * self._budget.usdc_price
            self._budget.usdc_budget -= amount
        else:
            raise ValueError("Підтримуються лише USDT або USDC.")

        event = BotBudgetEvent(
            event_type="WITHDRAW_FROM_BOT_BUDGET",
            asset=normalized_asset,
            amount=amount,
            value_usdt=value_usdt,
            note=note,
            created_at=datetime.utcnow(),
        )

        if self.database:
            self.database.save_bot_budget_event(event)

        return event

    def _load_from_database(self) -> None:
        events = self.database.load_bot_budget_events()

        for event in events:
            if event.event_type == "DEPOSIT":
                if event.asset == "USDT":
                    self._budget.usdt_budget += event.amount
                elif event.asset == "USDC":
                    self._budget.usdc_budget += event.amount
            elif event.event_type == "WITHDRAW_FROM_BOT_BUDGET":
                if event.asset == "USDT":
                    self._budget.usdt_budget -= event.amount
                elif event.asset == "USDC":
                    self._budget.usdc_budget -= event.amount
