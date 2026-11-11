"""Run the frozen interpreter on checksum-verified UnmixDB annotations."""
import argparse
import json
from pathlib import Path
from backend.app.config import Settings
from backend.app.research.unmixdb import evaluate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('D:/AI-DJ-data/experiments/open-dj'))
    p.add_argument('--limit',type=int)
    args=p.parse_args()
    report=evaluate(args.root,Settings.from_env(),args.limit)
    print(json.dumps(report['metrics'],indent=2))


if __name__=='__main__':main()
