# utils/colors.py
from __future__ import annotations
import pandas as pd


def cell_style_color(v):
    """
    Cell-level kleurregels:
    >0 groen, <0 rood, 0/NaN neutraal (geen kleur).
    """
    if pd.isna(v):
        return ""
    if v > 0:
        return "background-color: #0f5132; color: white;"  # groen
    if v < 0:
        return "background-color: #842029; color: white;"  # rood
    return ""  # 0 -> geen kleur
