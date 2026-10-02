"""Small, explicit count models shared by research and paper forecasts."""
from math import exp, floor, isfinite


def count_over(line, mean, dispersion=None):
    """Poisson or NB2 survival probability; NB variance is mu + mu**2/k."""
    if not isfinite(mean) or mean < 0 or not isfinite(line) or line < 0:
        raise ValueError("Finite nonnegative mean and line required")
    if dispersion is not None and (not isfinite(dispersion) or dispersion <= 0):
        raise ValueError("Positive finite dispersion required")
    if mean == 0:
        return 0.0
    kmax = floor(line)
    if dispersion is None:
        mass = exp(-mean)
        total = mass
        for n in range(1, kmax + 1):
            mass *= mean / n
            total += mass
    else:
        k = dispersion
        mass = (k / (k + mean)) ** k
        total = mass
        for n in range(1, kmax + 1):
            mass *= (n - 1 + k) / n * mean / (k + mean)
            total += mass
    return max(0.0, min(1.0, 1 - total))


def blend_mean(history, prior, strength=20, prior_window=30):
    """Shrink current-season mean toward the last prior-season appearances.

    Inputs must already be strictly pregame; never splice seasons as though
    their appearances were consecutive. No prior means a current-only mean.
    """
    if strength < 0 or prior_window < 1:
        raise ValueError("Invalid prior strength or window")
    current = [g['shots'] for g in history]
    previous = [g['shots'] for g in prior[:prior_window]]
    if any(not isinstance(x, int) or x < 0 for x in current + previous):
        raise ValueError("Nonnegative integer shot counts required")
    if not current and not previous:
        raise ValueError("No player history")
    effective = strength if previous else 0
    denominator = len(current) + effective
    if denominator == 0:
        raise ValueError("No usable player history")
    prior_mean = sum(previous) / len(previous) if previous else 0
    return (sum(current) + effective * prior_mean) / denominator
