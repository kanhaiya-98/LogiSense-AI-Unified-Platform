from scipy import stats
from db.supabase_client import get_carrier, update_carrier_reliability
from streams.redis_client import cache_carrier_reliability

RELIABILITY_SWAP_THRESHOLD   = 0.65  # auto-swap if below this
RELIABILITY_WARN_THRESHOLD   = 0.75  # log warning if below this
RELIABILITY_BLACKLIST_THRESHOLD = 0.45  # blacklist if below this

def bayesian_reliability_score(alpha: float, beta: float) -> dict:
    """
    Compute reliability metrics from Beta(alpha, beta) distribution.
    Returns: mean, lower_95, upper_95, credible_interval_width
    """
    dist = stats.beta(alpha, beta)
    mean = dist.mean()
    lower, upper = dist.interval(0.95)
    return {
        'mean':         round(float(mean), 4),
        'lower_95':     round(float(lower), 4),
        'upper_95':     round(float(upper), 4),
        'ci_width':     round(float(upper - lower), 4),
        'alpha':        alpha,
        'beta':         beta,
    }

def update_reliability_from_event(carrier_id: str, was_on_time: bool) -> dict:
    """
    Online Bayesian update: one new check-in event arrives.
    Increments alpha (success) or beta (failure) by 1.
    Updates Supabase + Redis cache.
    Returns updated reliability metrics.
    """
    carrier = get_carrier(carrier_id)
    if not carrier:
        return {}
        
    alpha = float(carrier.get('alpha_param', 10.0))
    beta  = float(carrier.get('beta_param',  2.0))
    
    # Bayesian update — one line
    if was_on_time:
        alpha += 1
    else:
        beta += 1
        
    metrics = bayesian_reliability_score(alpha, beta)
    new_score = metrics['mean']
    
    # Determine status
    if new_score < RELIABILITY_BLACKLIST_THRESHOLD:
        status = 'BLACKLISTED'
        blacklisted = True
        blacklist_reason = f'Reliability {new_score:.2f} below blacklist threshold {RELIABILITY_BLACKLIST_THRESHOLD}'
    elif new_score < RELIABILITY_SWAP_THRESHOLD:
        status = 'SWAP_REQUIRED'
        blacklisted = False
        blacklist_reason = None
    elif new_score < RELIABILITY_WARN_THRESHOLD:
        status = 'WARN'
        blacklisted = False
        blacklist_reason = None
    else:
        status = 'OK'
        blacklisted = False
        blacklist_reason = None
        
    # Update Supabase
    updates = {
        'alpha_param':             alpha,
        'beta_param':              beta,
        'current_reliability_score': new_score,
        'blacklisted':             blacklisted,
    }
    if blacklist_reason:
        updates['blacklist_reason'] = blacklist_reason
    update_carrier_reliability(carrier_id, updates)
    
    # Update Redis cache
    cache_carrier_reliability(carrier_id, new_score)
    
    return {
        'carrier_id':   carrier_id,
        'status':       status,
        'reliability':  metrics,
        'blacklisted':  blacklisted,
    }

def get_carrier_reliability_score(carrier_id: str) -> float:
    """Fast reliability score lookup — Supabase only."""
    carrier = get_carrier(carrier_id)
    if not carrier:
        return 0.5  # unknown carrier — cautious default
    return float(carrier.get('current_reliability_score', 0.85))

def should_swap(carrier_id: str) -> tuple[bool, str]:
    """Returns (should_swap, reason) for a carrier."""
    score = get_carrier_reliability_score(carrier_id)
    if score < RELIABILITY_BLACKLIST_THRESHOLD:
        return True, f'BLACKLIST_THRESHOLD (score={score:.2f})'
    if score < RELIABILITY_SWAP_THRESHOLD:
        return True, f'RELIABILITY_THRESHOLD (score={score:.2f})'
    return False, ''
