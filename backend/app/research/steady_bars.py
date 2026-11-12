"""Find observed regular bar spans and fit tempo without quantized-median bias."""
from backend.app.audio.bar_evidence import regular_bar_spans


def stable_spans(source,anchor,bars=8,minimum_start=35,after_span_context=25):
    return regular_bar_spans(source,anchor,bars=bars,minimum_start=minimum_start,
                             after_span_context=after_span_context)
