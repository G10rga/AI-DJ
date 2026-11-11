"""Install the pinned effect engine in a separate local experiment runtime."""
import json
from pathlib import Path
import subprocess

from scripts.setup_dj_benchmarks import download,digest

VERSION='0.9.26'
WHEEL='pedalboard-0.9.26-cp312-cp312-win_amd64.whl'
URL='https://files.pythonhosted.org/packages/dd/55/eb95ca568bec01ae73a16fe47c56369f3b84a0d94778981bb7efd1c5e440/'+WHEEL
SHA256='816b7063d3befb00263bfee7656932ee5f51788c586d5184d4d61f7a85f61aea'


def main():
    root=Path('D:/AI-DJ-data/experiments/open-dj')
    base=Path('D:/AI-DJ-data/timeline/venv/Scripts/python.exe')
    query="import json,sys,sysconfig,importlib.metadata as m; print(json.dumps({'python':list(sys.version_info[:2]),'purelib':sysconfig.get_path('purelib'),'numpy':m.version('numpy')}))"
    info=json.loads(subprocess.check_output([str(base),'-c',query],text=True))
    if info['python']!=[3,12] or info['numpy']!='1.26.4':raise ValueError('Unexpected base runtime')
    runtime=root/'pedalboard-runtime';python=runtime/'Scripts/python.exe'
    if not python.exists():subprocess.run([str(base),'-m','venv',str(runtime)],check=True)
    (runtime/'Lib/site-packages/ai_dj_cpu_runtime.pth').write_text(Path(info['purelib']).as_posix()+'\n',encoding='utf-8')
    wheel=root/'downloads'/WHEEL
    download(URL,wheel)
    if digest(wheel)!=SHA256:raise ValueError('Pedalboard wheel checksum mismatch')
    subprocess.run([str(python),'-m','pip','install','--no-deps',str(wheel)],check=True)
    observed=subprocess.check_output([str(python),'-c',"import pedalboard,importlib.metadata as m; print(m.version('pedalboard'))"],text=True).strip()
    if observed!=VERSION:raise ValueError('Unexpected effect engine version')
    (runtime/'setup.json').write_text(json.dumps({'version':VERSION,'wheel_url':URL,'wheel_sha256':SHA256,
                        'base':info,'license':'GPL-3.0','runtime':str(runtime)},indent=2),encoding='utf-8')
    print('Verified effect runtime: '+str(python))


if __name__=='__main__':main()
