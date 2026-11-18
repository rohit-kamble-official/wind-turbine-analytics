"""Generate the SIMULATED SCADA dataset (data/generated/).

Usage: python scripts/generate_data.py [--turbines 10 --start 2026-01-01 --end 2026-06-30 --seed 42]
"""
import _bootstrap  # noqa: F401
from app.services.generate_dataset import main

if __name__ == "__main__":
    main()
