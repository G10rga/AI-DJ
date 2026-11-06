"""Register auditions, give explicit feedback, and retrain a local preference ranker."""
import argparse
import json
from backend.app.config import Settings
from backend.app.planning.preferences import PreferenceStore


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('register');r.add_argument('reports',nargs='+')
    r=sub.add_parser('prefer');r.add_argument('winner');r.add_argument('loser');r.add_argument('--notes',default='')
    r=sub.add_parser('rate');r.add_argument('candidate');r.add_argument('rating',type=float);r.add_argument('--notes',default='')
    sub.add_parser('list');sub.add_parser('train');sub.add_parser('status')
    r=sub.add_parser('rank');r.add_argument('--pair')
    a=p.parse_args();store=PreferenceStore(Settings.from_env().data_root/'feedback')
    if a.command=='register':result=[{'id':store.register(path),'report':path} for path in a.reports]
    elif a.command=='prefer':result=store.feedback('prefer',a.winner,a.loser,notes=a.notes)
    elif a.command=='rate':result=store.feedback('rate',a.candidate,value=a.rating,notes=a.notes)
    elif a.command=='rank':result=store.rank(a.pair)
    elif a.command=='list':result=[{'id':r['id'],'pair_key':r['pair_key'],'output':json.loads(r['report_json'])['output']} for r in store.candidates()]
    else:result=store.train()
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
