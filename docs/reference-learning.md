# Experimental reference context learning

The owner requested training on HouseMixN3 on 2026-11-08. Its automatic alignment
proposals remain unreviewed. A positive-only successor-context model can learn
from the known order and matched audio without inventing transition-style or
preference labels. This is a precursor to the planned contextual/style models.

```powershell
scripts/local.ps1 -m scripts.train_reference REFERENCE_ID
```

The command validates consumed source hashes, pins the latest immutable alignment,
builds a provenance-bearing dataset, and runs the small PyTorch model in the
existing isolated CPU timeline environment. It requires that runtime, not another
download or a new package installation. All data and checkpoints stay under the
configured data root. Complete runs publish atomically under `models`; failures
cannot replace an existing run. A repeated identical run preserves its artifacts.

Input descriptors are 32-band spectral mean/std summaries of eight-second source
and recording windows. Frame-wide gain is removed. The network predicts the next
source descriptor as a residual from the outgoing source descriptor. Training
uses observed positive successor pairs only. It does not label other choices
bad, infer mixer settings, generate audio or learn EQ/waveform curves.

Unresolved entries are excluded without connecting their neighbors. Source and
recording windows must be bounded and supported by the selected alignment.
At most four window examples augment each observed pair; counts are not claims
of independent human judgments. Metrics weight original pairs equally.

The split reserves the last quarter of located source identities, assigns every
occurrence of a repeated hash to the same group, excludes cross-group edges and
uses a 16-second recording-window embargo. Every augmentation of a pair stays
together. Standardization fits training data only. Evaluation does not select
epochs or hyperparameters. Training-target mean and persistence baselines are
reported even when they outperform the network.

Artifacts contain the exact dataset, split, normalization/configuration,
dependency versions, implementation hash, tensor-only state dict and evaluation.
Loading verifies artifact hashes and the architecture, then uses `weights_only`
and strict state-dict loading. The checkpoint remains `experimental`, inactive
and without listening approval. Existing render/planning selection is unchanged.

Prediction accepts a JSON object with a 64-value `source` descriptor and optional
64-value `recording` descriptor, produced by `reference_learning.descriptor`:

```powershell
& D:/AI-DJ-data/timeline/venv/Scripts/python.exe -m scripts.reference_training_worker predict MODEL_DIRECTORY CONTEXT_JSON
```

Omitting recording context explicitly uses the source descriptor as a fallback;
that input substitution has not been evaluated on generated mixes. Predictions
are musical descriptor vectors, not preference scores or transition commands.

One reference cannot provide an independent reference-set evaluation. Assigned
source hashes are disjoint in the split, but alternate edits can have different
hashes, and unreviewed matched recording passages can include other audible
tracks. These limits remain in every report. Reviewed reference observations
are still needed for transition-style supervision; explicit A/B votes remain
the source of preference supervision.
