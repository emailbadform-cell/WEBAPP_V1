"""Auto Paper V1 frozen prospective collection specification.

Research-only/paper-only. This module MUST NOT place live orders or feed Kalshi prices
into Decision, Settlement, GT, Chart, MP, or other predictive authority.
"""
AUTO_PAPER_V1 = {
    "version": "AUTO_PAPER_V1_FROZEN_2026_09_16",
    "authority": False, "paper_only": True,
    "entry": {"seconds_remaining": [20,180], "max_ask": 0.75, "decision_persistence_s": 2, "require_settlement_agreement": True},
    "primary_exit": {"decision_opposition_confirm_s": 5, "profit_min": 0.08, "profit_giveback": 0.05, "late_profit_seconds": 45},
    "shadow_policies": ["decision_only","decision_settlement","decision_gt","decision_structure","decision_of_l2","hold_settlement","decision_flip","decision_flip_5s","target_recross","reversal","of_l2_opposition","take_profit","trailing_protection","time_exit","multi_risk"],
}

def spec(): return dict(AUTO_PAPER_V1)
