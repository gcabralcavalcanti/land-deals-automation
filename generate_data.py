"""Writes the synthetic land portfolio to data/portfolio.json.

    python generate_data.py [--seed 11]
"""
import argparse
import json

from land_deals.synthetic import generate

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=11)
    print(json.dumps(generate(seed=ap.parse_args().seed), ensure_ascii=False, indent=1))
