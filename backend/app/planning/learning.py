"""Unsupervised library embeddings and pair groups, with inspectable JSON state."""
import math
import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import RobustScaler
from threadpoolctl import threadpool_limits

VERSION = 'library-ml-1'
SEED = 11


def feature_vector(analysis):
    energy = np.asarray(analysis.get('energy', [0.0]), dtype=float)
    if not len(energy):
        energy = np.zeros(1)
    rhythm = analysis.get('rhythm', {})
    bpm = rhythm.get('bpm') if rhythm.get('reliable') else None
    chroma = np.asarray(analysis.get('chroma', [0.0]*12), dtype=float)
    mean = np.asarray(analysis.get('mfcc_mean', [0.0]*13), dtype=float)
    std = np.asarray(analysis.get('mfcc_std', [0.0]*13), dtype=float)
    spectral = np.asarray(analysis.get('spectral_summary', [0.0]*3), dtype=float)
    if chroma.shape != (12,) or mean.shape != (13,) or std.shape != (13,) or spectral.shape != (3,):
        raise ValueError('Unexpected audio feature dimensions')
    values = np.concatenate((mean[1:], std[1:], chroma, spectral,
                             np.quantile(20*np.log10(np.maximum(energy, 1e-8)), [.1, .5, .9]),
                             [math.log2(bpm/120) if bpm else 0, float(rhythm.get('confidence', 0)),
                              float(rhythm.get('valid_fraction', 0))]))
    if not np.all(np.isfinite(values)):
        raise ValueError('Planning features must be finite')
    return values


def cosine_distance(first, second):
    a, b = np.asarray(first, dtype=float), np.asarray(second, dtype=float)
    denominator = float(np.linalg.norm(a)*np.linalg.norm(b))
    return float(np.clip(1-np.dot(a, b)/denominator, 0, 1)) if denominator > 1e-12 else .5


def pair_descriptors(entries, embedding):
    n = len(entries)
    descriptors = np.zeros((n, n, 5))
    for i, a in enumerate(entries):
        for j, b in enumerate(entries):
            if i == j:
                continue
            ra, rb = a['analysis'].get('rhythm', {}), b['analysis'].get('rhythm', {})
            ba, bb = ra.get('bpm'), rb.get('bpm')
            tempo = abs(math.log2(ba/bb)) if ba and bb else 1.0
            ea = float(np.median(a['analysis'].get('energy') or [0]))
            eb = float(np.median(b['analysis'].get('energy') or [0]))
            descriptors[i, j] = [float(np.linalg.norm(embedding[i]-embedding[j])/math.sqrt(embedding.shape[1])),
                                 tempo, cosine_distance(a['analysis'].get('chroma', [0]*12), b['analysis'].get('chroma', [0]*12)),
                                 abs(math.log2(max(ea, 1e-8)/max(eb, 1e-8))),
                                 1-min(float(ra.get('confidence', 0)), float(rb.get('confidence', 0)))]
    return descriptors


def fit_library(entries):
    if not entries:
        raise ValueError('A library cannot be empty')
    ids = [entry['entry_id'] for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError('Upload entry IDs must be unique')
    raw = np.stack([feature_vector(entry['analysis']) for entry in entries])
    unique = {}
    for i, entry in enumerate(entries):
        unique.setdefault(entry['analysis']['content_hash'], i)
    training_indices = sorted(unique.values(), key=lambda i: entries[i]['analysis']['content_hash'])
    training = raw[training_indices]
    scaler = RobustScaler().fit(training)
    scaled = np.clip(scaler.transform(raw), -5, 5)
    # Balance feature families after robust scaling, so twelve chroma bins do
    # not outweigh the complete energy/tempo descriptors merely by count.
    family_weights = np.concatenate((np.full(24, 1/math.sqrt(24)), np.full(12, 1/math.sqrt(12)),
                                     np.full(3, 1/math.sqrt(3)), np.full(3, 1/math.sqrt(3)), np.ones(3)))
    scaled *= family_weights
    training_scaled = scaled[training_indices]
    distinct = len(np.unique(np.round(training_scaled, 8), axis=0))
    pca = None
    with threadpool_limits(limits=1):
        if len(training_indices) >= 3 and distinct >= 2:
            pca = PCA(n_components=min(8, len(training_indices)-1, raw.shape[1]), svd_solver='full').fit(training_scaled)
            embedding = pca.transform(scaled)
        else:
            embedding = scaled
        count = min(max(1, round(math.sqrt(len(training_indices)))), distinct)
        clusterer = KMeans(n_clusters=count, n_init=10, random_state=SEED).fit(embedding[training_indices])
        labels = clusterer.predict(embedding)
    descriptors = pair_descriptors(entries, embedding)
    training_pairs = [(i, j) for offset, i in enumerate(training_indices) for j in training_indices[offset+1:]]
    values = np.array([descriptors[i, j] for i, j in training_pairs])
    pair_labels = np.zeros((len(entries), len(entries)), dtype=int)
    pair_model, pair_scaler, rank = None, None, {0: 0}
    if len(values) >= 6 and len(np.unique(np.round(values, 8), axis=0)) >= 2:
        pair_scaler = RobustScaler().fit(values)
        normalized = np.clip(pair_scaler.transform(values), -5, 5)
        components = min(3, len(np.unique(np.round(normalized, 8), axis=0)))
        with threadpool_limits(limits=1):
            pair_model = GaussianMixture(n_components=components, covariance_type='diag', reg_covar=1e-3,
                                         random_state=SEED, n_init=5).fit(normalized)
            predicted = pair_model.predict(np.clip(pair_scaler.transform(descriptors.reshape(-1, 5)), -5, 5))
        pair_labels = predicted.reshape(len(entries), len(entries))
        # Unsupervised labels have no inherent musical meaning. Map groups by
        # their typical physical difficulty; this is a declared rule, not a
        # learned probability that listeners will like a transition.
        difficulty = values[:, 0]*.35+values[:, 1]*4+values[:, 2]*.5+values[:, 3]*.25+values[:, 4]
        assignments = pair_model.predict(normalized)
        means = {label: float(np.mean(difficulty[assignments == label])) if np.any(assignments == label) else float('inf')
                 for label in range(components)}
        rank = {label: position for position, label in enumerate(sorted(means, key=lambda label: (means[label], label)))}
    model = {
        'version': VERSION, 'seed': SEED, 'training_content_hashes': [entries[i]['analysis']['content_hash'] for i in training_indices],
        'training_samples': len(training_indices), 'feature_count': raw.shape[1],
        'feature_families': ['MFCC mean/std (excluding coefficient zero)', 'chroma', 'spectral shape', 'energy quantiles', 'tempo/pulse evidence'],
        'scaler_center': scaler.center_.tolist(), 'scaler_scale': scaler.scale_.tolist(), 'family_weights': family_weights.tolist(),
        'pca': {'mean': pca.mean_.tolist(), 'components': pca.components_.tolist(),
                'explained_variance_ratio': pca.explained_variance_ratio_.tolist()} if pca else None,
        'track_clusters': {'centers': clusterer.cluster_centers_.tolist(), 'count': count},
        'pair_model': {'weights': pair_model.weights_.tolist(), 'means': pair_model.means_.tolist(),
                       'variances': pair_model.covariances_.tolist(), 'scaler_center': pair_scaler.center_.tolist(),
                       'scaler_scale': pair_scaler.scale_.tolist(), 'converged': bool(pair_model.converged_)} if pair_model else None,
        'pair_cluster_rank': {str(label): position for label, position in rank.items()},
        'limitations': ['Unsupervised similarity and pair groups do not learn human mix quality.',
                       'Blend curves remain deterministic; phase/structure/vocals need waveform validation.'],
    }
    return {'model': model, 'embedding': embedding, 'track_labels': labels,
            'descriptors': descriptors, 'pair_labels': pair_labels, 'pair_rank': rank}
