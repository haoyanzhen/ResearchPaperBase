"""Reserve the single migration chain; no target or business schema is enabled."""
raise RuntimeError(
    "Migration execution unavailable: isolated target and first schema require a separate slice."
)
