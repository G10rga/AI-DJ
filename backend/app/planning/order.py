"""Deterministic constrained nearest-neighbor paths over learned features."""
import numpy as np


def cost_matrix(learned, method='ml'):
    descriptors = learned['descriptors']
    timbre, tempo, chroma, energy, uncertainty = [descriptors[:, :, i] for i in range(5)]
    if method not in {'ml', 'baseline'}:
        raise ValueError('Unknown ordering method')
    distance = timbre/(1+np.median(timbre[timbre > 0])) if np.any(timbre > 0) else timbre
    costs = 4*tempo+.5*chroma+.25*energy+.15*uncertainty
    if method == 'ml':
        costs = costs+.65*distance+.08*(learned['track_labels'][:, None] != learned['track_labels'][None, :])
    np.fill_diagonal(costs, 0)
    return costs


def order_entries(entries, learned, method='ml'):
    n = len(entries)
    if n == 1:
        return [0], 0.0
    costs = cost_matrix(learned, method)
    energy = np.array([np.median(entry['analysis'].get('energy') or [0]) for entry in entries])
    span = float(np.ptp(energy))
    relative = (energy-np.min(energy))/span if span > 1e-12 else np.full(n, .5)
    arc = np.interp(np.linspace(0, 1, n), [0, .7, 1], [.2, .85, .6])
    def objective(route):
        edges = sum(costs[a, b] for a, b in zip(route, route[1:]))
        return float(edges+.12*np.sum(abs(relative[route]-arc)))
    starts = sorted(range(n), key=lambda i: (relative[i], entries[i]['entry_id']))
    starts = starts if n <= 24 else [starts[i] for i in np.linspace(0, n-1, 24, dtype=int)]
    candidates = []
    for start in starts:
        route, remaining = [start], set(range(n))-{start}
        while remaining:
            nxt = min(remaining, key=lambda i: (costs[route[-1], i]+.12*abs(relative[i]-arc[len(route)]), entries[i]['entry_id']))
            route.append(nxt)
            remaining.remove(nxt)
        # Reversible local improvements preserve membership by construction.
        current = objective(route)
        for _ in range(3):
            changed = False
            for left in range(n-1):
                for right in range(left+1, n):
                    trial = route[:left]+route[left:right+1][::-1]+route[right+1:]
                    score = objective(trial)
                    if score < current-1e-10:
                        route, current, changed = trial, score, True
            if not changed:
                break
        candidates.append((current, tuple(entries[i]['entry_id'] for i in route), route))
    score, _, route = min(candidates)
    return route, score
