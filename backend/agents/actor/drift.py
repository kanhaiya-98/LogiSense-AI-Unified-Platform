import numpy as np
from scipy import stats
from db.supabase_client import get_carrier_events_for_drift

DRIFT_PVALUE_THRESHOLD   = 0.05   # p < 0.05 = statistically significant drift
DRIFT_STATISTIC_WARN     = 0.25   # KS stat > 0.25 = WARN severity
DRIFT_STATISTIC_CRITICAL = 0.40   # KS stat > 0.40 = CRITICAL severity
MIN_SAMPLES_REQUIRED     = 20     # need at least 20 events per window


def run_ks_test(carrier_id: str) -> dict:
    """
    Run KS drift test on a carrier's on-time rate history.
    Splits events into early half vs recent half and tests if distributions differ.
    
    Returns dict with:
        drifting: bool
        severity: 'NONE' | 'WARN' | 'CRITICAL'
        ks_statistic: float
        ks_pvalue: float
        early_mean: float   (on-time rate in early period)
        recent_mean: float  (on-time rate in recent period)
    """
    events = get_carrier_events_for_drift(carrier_id, days=30)
    
    if len(events) < MIN_SAMPLES_REQUIRED * 2:
        return {
            'drifting': False, 'severity': 'NONE',
            'ks_statistic': 0.0, 'ks_pvalue': 1.0,
            'early_mean': 0.0, 'recent_mean': 0.0,
            'reason': f'Insufficient data: {len(events)} events'
        }
        
    # on_time is 1 (on time) or 0 (late) per event
    on_time_rates = [float(e['on_time']) for e in events]
    
    # Split: events are ordered newest-first (we ordered by date desc)
    mid = len(on_time_rates) // 2
    recent = on_time_rates[:mid]   # newer events
    early  = on_time_rates[mid:]   # older events
    
    ks_stat, p_value = stats.ks_2samp(early, recent)
    
    early_mean  = float(np.mean(early))
    recent_mean = float(np.mean(recent))
    is_degrading = recent_mean < early_mean  # only flag if getting WORSE
    
    drifting = (p_value < DRIFT_PVALUE_THRESHOLD) and is_degrading
    
    if not drifting:
        severity = 'NONE'
    elif ks_stat >= DRIFT_STATISTIC_CRITICAL:
        severity = 'CRITICAL'
    elif ks_stat >= DRIFT_STATISTIC_WARN:
        severity = 'WARN'
    else:
        severity = 'NONE'
        drifting = False  # small effect size, not actionable
        
    return {
        'carrier_id':    carrier_id,
        'drifting':      drifting,
        'severity':      severity,
        'ks_statistic':  round(ks_stat, 4),
        'ks_pvalue':     round(p_value, 6),
        'early_mean':    round(early_mean, 4),
        'recent_mean':   round(recent_mean, 4),
        'delta':         round(recent_mean - early_mean, 4),
    }

def scan_all_carriers(carrier_ids: list[str]) -> list[dict]:
    """Run KS test on all carriers. Returns only those that are drifting."""
    drifting = []
    for cid in carrier_ids:
        result = run_ks_test(cid)
        if result['drifting']:
            drifting.append(result)
            print(f'  DRIFT: {cid} — KS={result["ks_statistic"]:.3f} p={result["ks_pvalue"]:.4f}'
                  f'  {result["early_mean"]:.2f} → {result["recent_mean"]:.2f}')
    return drifting
