"""CPU-only training/prediction in the existing isolated PyTorch environment."""
import argparse
import json
from pathlib import Path
from backend.app.planning.reference_learning import train, predict


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    fitting = commands.add_parser('train')
    fitting.add_argument('dataset', type=Path)
    fitting.add_argument('destination', type=Path)
    fitting.add_argument('--epochs', type=int, default=300)
    fitting.add_argument('--seed', type=int, default=11)
    scoring = commands.add_parser('predict')
    scoring.add_argument('model', type=Path)
    scoring.add_argument('context', type=Path)
    args = parser.parse_args()
    if args.command == 'train':
        result = train(json.loads(args.dataset.read_text(encoding='utf-8')), args.destination,
                       epochs=args.epochs, seed=args.seed)
    else:
        context = json.loads(args.context.read_text(encoding='utf-8'))
        result = predict(args.model, context['source'], context.get('recording'))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
