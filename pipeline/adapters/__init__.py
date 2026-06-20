"""Source adapters (Strategy pattern).

A common SourceAdapter interface with one implementation per source. Each adapter
owns its own retrieval + normalization logic and emits the single canonical
CommunicationRecord. Adding a source = adding an adapter, never editing the
pipeline. Registration is config-driven (see registry.py): open for extension,
closed for modification.
"""
