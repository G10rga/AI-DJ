# Preference learning

Owner explicitly authorized feedback-driven learning. Add an append-only local
feedback store and an inspectable pairwise logistic ranker for candidate settings.
Register real rendered reports with audio hashes and source-pair identity; collect
explicit ratings/preferences only. Never turn chat impressions or synthetic tests
into owner labels. Train on candidate feature differences within ordered song pairs,
deduplicate current votes, split validation by song pair, and keep cold-start output
clearly untrained until there are enough independent comparisons. Save JSON weights,
training evidence and held-out results; retrain after feedback. Scores are relative
preferences, not musical-quality probabilities. Keep DSP validation authoritative.
Provide CLI register/list/rate/prefer/train/rank/status and an actual A/B audition.
No generative audio, learned curves, cloud audio upload or commits.
