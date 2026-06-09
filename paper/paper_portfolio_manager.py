from paper.models import PaperPortfolio


class PaperPortfolioManager:
    def __init__(self, initial_usdt: float = 50.0, initial_usdc: float = 50.0) -> None:
        self.portfolio = PaperPortfolio(usdt=initial_usdt, usdc=initial_usdc)

    def get_portfolio(self, price: float = 1.0) -> PaperPortfolio:
        self.portfolio.usdc_price = price
        return self.portfolio

    def can_buy_usdc(self, notional: float) -> bool:
        return self.portfolio.usdt >= notional

    def can_sell_usdc(self, quantity: float) -> bool:
        return self.portfolio.usdc >= quantity

    def apply_buy_usdc(self, price: float, quantity: float, fee: float) -> None:
        notional = price * quantity
        self.portfolio.usdt -= notional + fee
        self.portfolio.usdc += quantity
        self.portfolio.usdc_price = price

    def apply_sell_usdc(self, price: float, quantity: float, fee: float) -> None:
        notional = price * quantity
        self.portfolio.usdc -= quantity
        self.portfolio.usdt += notional - fee
        self.portfolio.usdc_price = price
