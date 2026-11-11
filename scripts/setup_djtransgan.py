"""Create an isolated inference runtime and verify the author's pretrained weights."""
import argparse
import json
from pathlib import Path
import subprocess
from backend.app.research.djtransgan import CHECKPOINT_SHA256, CHECKPOINT_URL
from scripts.setup_dj_benchmarks import digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('D:/AI-DJ-data/experiments/open-dj'))
    parser.add_argument('--base-python',type=Path,default=Path('D:/AI-DJ-data/timeline/venv/Scripts/python.exe'))
    args=parser.parse_args()
    # Read the existing runtime only; install exclusively through the new venv.
    query="import sys,sysconfig,json,importlib.metadata as m; print(json.dumps({'python':list(sys.version_info[:2]),'purelib':sysconfig.get_path('purelib'),'packages':{n:m.version(n) for n in ['torch','torchaudio','numpy','scipy','soundfile']}}))"
    base=json.loads(subprocess.check_output([str(args.base_python),'-c',query],text=True))
    expected={'torch':'2.6.0+cpu','torchaudio':'2.6.0+cpu','numpy':'1.26.4','scipy':'1.13.1','soundfile':'0.13.1'}
    if base['python']!=[3,12] or base['packages']!=expected:
        raise ValueError('Research bootstrap requires the documented Python 3.12 CPU base runtime')
    runtime=args.root.resolve()/'runtime'
    python=runtime/'Scripts/python.exe'
    if not python.exists():subprocess.run([str(args.base_python),'-m','venv',str(runtime)],check=True)
    (runtime/'Lib/site-packages/ai_dj_cpu_runtime.pth').write_text(Path(base['purelib']).as_posix()+'\n',encoding='utf-8')
    requirements=Path(__file__).with_name('dj_benchmark_requirements.txt')
    subprocess.run([str(python),'-m','pip','install','-r',str(requirements)],check=True)
    checkpoint=args.root.resolve()/'checkpoints/djtransgan_minmax.pt'
    checkpoint.parent.mkdir(parents=True,exist_ok=True)
    if not checkpoint.exists():
        # Download to a staging file. A failed or interrupted download is not a model.
        staged=checkpoint.with_suffix('.part')
        code="import gdown,sys; gdown.download(url=sys.argv[1],output=sys.argv[2],quiet=False)"
        subprocess.run([str(python),'-c',code,CHECKPOINT_URL,str(staged)],check=True)
        if digest(staged)!=CHECKPOINT_SHA256:raise ValueError('Pretrained checkpoint checksum mismatch')
        staged.replace(checkpoint)
    if digest(checkpoint)!=CHECKPOINT_SHA256:raise ValueError('Existing checkpoint checksum mismatch')
    provenance={'base':base,'requirements_sha256':digest(requirements),'checkpoint_sha256':digest(checkpoint),
                'checkpoint_url':CHECKPOINT_URL,'runtime':str(runtime)}
    (runtime/'setup.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    print('Verified pretrained research runtime: '+str(python))


if __name__=='__main__':main()
