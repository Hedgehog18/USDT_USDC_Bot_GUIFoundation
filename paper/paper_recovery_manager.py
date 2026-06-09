from dataclasses import dataclass
from paper.models import PaperPortfolio


@dataclass(frozen=True)
class PaperRecoverySnapshot:
    portfolio: PaperPortfolio
    active_cycles: int
    last_cycle_status: str
    last_cycle_net_profit: float


class PaperRecoveryManager:
    def __init__(self, database) -> None:
        self.database = database

    def recover(self) -> PaperRecoverySnapshot:
        portfolio = self.database.load_last_paper_portfolio()
        if portfolio is None:
            portfolio = PaperPortfolio(usdt=50.0, usdc=50.0, usdc_price=1.0)

        last_cycle = self.database.load_last_paper_cycle_summary()
        return PaperRecoverySnapshot(
            portfolio=portfolio,
            active_cycles=self.database.count_open_paper_cycles(),
            last_cycle_status=str(last_cycle[0]) if last_cycle else "NONE",
            last_cycle_net_profit=float(last_cycle[1]) if last_cycle else 0.0,
        )
