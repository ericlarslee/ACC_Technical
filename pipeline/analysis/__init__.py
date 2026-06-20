"""Analysis layer — a Pipes-and-Filters pipeline, two stages, one model.

Claude is the ONLY model in the pipeline. There is no embedding model and no
vector math. The analysis is exactly two Claude prompts, each returning
structured JSON:

  1. extract.py   — Extraction filter, run PER record (Claude prompt #1)
  2. cluster.py   — Clustering filter, run ONCE over the batch (Claude prompt #2)

claude_client.py is where Claude actually sits: a real Anthropic implementation
and a clearly-mocked equivalent behind one ClaudeAnalyzer interface.
"""
