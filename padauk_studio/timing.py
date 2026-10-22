"""Timer math from the datasheets (same on all three chips).

TM2/TM3 PWM:     f = Y / (R * S1 * (S2+1)), R = 256 (8-bit) or 64 (6-bit), duty = (K+1)/R
TM2/TM3 period:  interrupt rate = Y / ((K+1) * S1 * (S2+1))     (output toggles at half that)
PWMG0..2:        f = Y / (P * (K+1) * (CB+1)), duty = (D+1) / (2*(CB+1)), CB 10-bit, D 11-bit
Timer16:         interrupt rate = Y / (S1 * 2^(n+1)) for "bit n" (rising edge of counter bit n)
"""

from dataclasses import dataclass
from typing import Dict, Optional

PRESCALERS = {"DIV1": 1, "DIV4": 4, "DIV16": 16, "DIV64": 64}


@dataclass
class TimerSetting:
    source: str           # IHRC / SYSCLK / ILRC
    pre: str              # DIV1 / DIV4 / DIV16 / DIV64
    scale: int = 0        # S2 / K (0..31)
    bound: int = 0        # TMxB / CB / T16 bit number
    res: int = 8          # 8 or 6 (TMx PWM)
    actual_hz: float = 0.0

    def error(self, target):
        return abs(self.actual_hz - target) / target if target else 0.0


def tm8_pwm(sources: Dict[str, float], target_hz: float, allow_6bit=True) -> Optional[TimerSetting]:
    best = None
    for src, y in sources.items():
        for res in ((8, 6) if allow_6bit else (8,)):
            r = 256 if res == 8 else 64
            for pre, s1 in PRESCALERS.items():
                for s2 in range(32):
                    f = y / (r * s1 * (s2 + 1))
                    cand = TimerSetting(src, pre, s2, 0, res, f)
                    # prefer: small error, then 8-bit, then the faster (more accurate) clock
                    key = (round(cand.error(target_hz), 4), res != 8, -y)
                    if best is None or key < best[0]:
                        best = (key, cand)
    return best[1] if best else None


def tm8_period(sources: Dict[str, float], target_hz: float) -> Optional[TimerSetting]:
    best = None
    for src, y in sources.items():
        for pre, s1 in PRESCALERS.items():
            for s2 in range(32):
                k = round(y / (target_hz * s1 * (s2 + 1))) - 1
                if not 0 <= k <= 255:
                    continue
                f = y / ((k + 1) * s1 * (s2 + 1))
                cand = TimerSetting(src, pre, s2, k, 8, f)
                key = (round(cand.error(target_hz), 5), -k, -y)   # larger bound = finer steps
                if best is None or key < best[0]:
                    best = (key, cand)
    return best[1] if best else None


def pwmg(sources: Dict[str, float], target_hz: float) -> Optional[TimerSetting]:
    """Pick the setting with the most duty steps whose frequency is within 1 %."""
    exact, close = None, None
    for src, y in sources.items():
        for pre, p in PRESCALERS.items():
            for k in range(32):
                cb = round(y / (target_hz * p * (k + 1))) - 1
                if not 1 <= cb <= 1023:
                    continue
                f = y / (p * (k + 1) * (cb + 1))
                cand = TimerSetting(src, pre, k, cb, 11, f)
                err = cand.error(target_hz)
                if err <= 0.01:
                    key = (-cb, err)
                    if exact is None or key < exact[0]:
                        exact = (key, cand)
                key = (err, -cb)
                if close is None or key < close[0]:
                    close = (key, cand)
    if exact:
        return exact[1]
    return close[1] if close else None


def t16_tick(sources: Dict[str, float], target_hz: float) -> Optional[TimerSetting]:
    best = None
    for src, y in sources.items():
        for pre, s1 in PRESCALERS.items():
            for n in range(8, 16):
                f = y / (s1 * (1 << (n + 1)))
                cand = TimerSetting(src, pre, 0, n, 16, f)
                key = (round(cand.error(target_hz), 4), -y)
                if best is None or key < best[0]:
                    best = (key, cand)
    return best[1] if best else None


def fmt_hz(f: float) -> str:
    if f >= 1e6:
        return f"{f / 1e6:.4g} MHz"
    if f >= 1e3:
        return f"{f / 1e3:.4g} kHz"
    return f"{f:.4g} Hz"
