"""Isolated CPU adapter for reviewed cue/style fitting and inference."""
import argparse,json
from pathlib import Path
from backend.app.planning.decision_learning import fit,predict

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('kind',choices=('train','predict'));p.add_argument('request',type=Path)
    p.add_argument('destination',type=Path);p.add_argument('--model',type=Path)
    a=p.parse_args();request=json.loads(a.request.read_text(encoding='utf-8'))
    if a.kind=='train':
        result=fit(request,a.destination)
    else:
        result=predict(a.model,request)
        a.destination.write_text(json.dumps(result,allow_nan=False),encoding='utf-8')
    print(json.dumps({'completed':True,'kind':a.kind}))

if __name__=='__main__':main()
