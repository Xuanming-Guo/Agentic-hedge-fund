from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TokenBudget:
    max_calls_per_cycle: int = 12
    used_calls: int = 0
    total_tokens: int = 0


class TokenGovernor:
    def __init__(self, max_calls_per_cycle: int = 12) -> None:
        self.max_calls_per_cycle = max_calls_per_cycle

    def new_budget(self) -> TokenBudget:
        return TokenBudget(max_calls_per_cycle=self.max_calls_per_cycle)

    def allow_call(self, budget: TokenBudget) -> bool:
        if budget.used_calls >= budget.max_calls_per_cycle:
            return False
        budget.used_calls += 1
        return True
