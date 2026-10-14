"""Cars listing ingestion, warehouse loading, and analytical reporting."""


def main() -> int:
    from .pipeline import main as run_pipeline

    return run_pipeline()
