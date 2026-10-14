"""Allow python -m cars_data_pipeline as well as the installed CLI."""
import sys

from .pipeline import main


if __name__ == "__main__":
    sys.exit(main())
