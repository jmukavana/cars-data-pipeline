import logging
from pathlib import Path
import subprocess
import sys
from time import perf_counter


PROJECT_DIR = Path(__file__).resolve().parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def main():
    started = perf_counter()

    steps = [
        ("Transform cars data", "transform_cars.py"),
        ("Load source table", "load_cars.py"),
        ("Load warehouse tables", "load_warehouse.py"),
    ]

    for label, script in steps:
        logging.info("Starting: %s", label)

        try:
            subprocess.run(
                [sys.executable, str(PROJECT_DIR / script)],
                cwd=PROJECT_DIR,
                check=True,
            )
        except subprocess.CalledProcessError:
            logging.exception("Failed: %s. Pipeline stopped.", label)
            return 1

        logging.info("Finished: %s", label)

    logging.info(
        "Pipeline completed in %.2f seconds",
        perf_counter() - started,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())