import time
from dataclasses import dataclass

from app.bot_engine import BotEngine


@dataclass(frozen=True)
class RunnerResult:
    iterations_completed: int
    stopped_by_limit: bool


class BotRunner:
    """Запускає BotEngine у періодичному циклі.

    MVP-захист:
    - max_iterations обмежує кількість ітерацій;
    - це не безкінечний production-loop;
    - зручно для тестування Demo-режиму.
    """

    def __init__(
        self,
        bot: BotEngine,
        interval_seconds: int,
        max_iterations: int,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds має бути більшим за 0.")
        if max_iterations <= 0:
            raise ValueError("max_iterations має бути більшим за 0.")

        self.bot = bot
        self.interval_seconds = interval_seconds
        self.max_iterations = max_iterations
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> RunnerResult:
        iterations = 0

        while not self._stop_requested and iterations < self.max_iterations:
            iterations += 1
            print(f"--- Runner iteration {iterations}/{self.max_iterations} ---")
            self.bot.start()

            if iterations < self.max_iterations and not self._stop_requested:
                time.sleep(self.interval_seconds)

        return RunnerResult(
            iterations_completed=iterations,
            stopped_by_limit=iterations >= self.max_iterations,
        )
