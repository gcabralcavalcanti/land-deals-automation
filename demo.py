"""One command: synthetic portfolio, model, AI intake and memos (replayed without a key), workbook, dashboard, PDF."""

import sys

from land_deals.cli import main

if __name__ == "__main__":
    main(["demo", *sys.argv[1:]])
