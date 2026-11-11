"""Fetch pinned research sources and one checksum-verified official UnmixDB set."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import urllib.request
import zipfile

SOURCES={
    'djtransgan':('ChenPaulYu/DJtransGAN','64228931f3b4514f289fbbbc0e5675adb57aeb88'),
    'unmixdb-creation':('Ircam-RnD/unmixdb-creation','abc606a30d5f5b01df589bef5345a73c79528907')}
DATASET={'name':'mixotic-set222-excerpts.zip','md5':'423d62a8c2659507d6b964ac4ec2bffc','size':85106114,
         'url':'https://zenodo.org/api/records/1422385/files/mixotic-set222-excerpts.zip/content'}


def digest(path,algorithm='sha256'):
    h=hashlib.new(algorithm)
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def download(url,path,*,size=None,md5=None):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and (size is None or path.stat().st_size==size) and (md5 is None or digest(path,'md5')==md5):return
    staged=path.with_suffix(path.suffix+'.part')
    request=urllib.request.Request(url,headers={'User-Agent':'AI-DJ-local-benchmark/1.0'})
    print('Downloading '+path.name,flush=True)
    with urllib.request.urlopen(request,timeout=60) as response,staged.open('wb') as stream:
        total=0;last=0
        while block:=response.read(1024*1024):
            total+=len(block)
            if size and total>size:raise ValueError('Download exceeds published size')
            stream.write(block)
            if total-last>=10*1024**2:print(f'  {total/1024**2:.0f} MiB',flush=True);last=total
    if size is not None and staged.stat().st_size!=size:raise ValueError('Download size differs from publisher metadata')
    if md5 and digest(staged,'md5')!=md5:raise ValueError('Official dataset checksum mismatch')
    staged.replace(path)


def extract(archive,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as zipped:
        members=zipped.infolist()
        if sum(m.file_size for m in members)>2*1024**3:raise ValueError('Archive exceeds experiment extraction bound')
        for member in members:
            name=member.filename.replace('\\','/')
            target=(destination/name).resolve()
            if ':' in name or not target.is_relative_to(destination.resolve()) or stat.S_ISLNK(member.external_attr>>16):
                raise ValueError('Unsafe archive member: '+name)
        for member in members:
            target=destination/member.filename
            if member.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with zipped.open(member) as source,target.open('wb') as output:shutil.copyfileobj(source,output)


def ensure_extracted(archive,destination):
    """A partial extraction is never mistaken for a completed download."""
    destination=Path(destination)
    stamp=destination/'.archive-sha256'
    checksum=digest(archive)
    if not stamp.exists() or stamp.read_text(encoding='utf-8').strip()!=checksum:
        extract(archive,destination)
        stamp.write_text(checksum+'\n',encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path('D:/AI-DJ-data/experiments/open-dj'));args=p.parse_args()
    root=args.root.resolve();root.mkdir(parents=True,exist_ok=True)
    manifest={'sources':{},'dataset':dict(DATASET),'purpose':'isolated evaluation; no owner labels or model promotion'}
    for name,(repo,commit) in SOURCES.items():
        path=root/'downloads'/(name+'-'+commit+'.zip')
        url=f'https://codeload.github.com/{repo}/zip/{commit}'
        download(url,path)
        destination=root/'sources'/name
        ensure_extracted(path,destination)
        folders=[d for d in destination.iterdir() if d.is_dir()]
        if len(folders)!=1:raise ValueError('Unexpected source archive layout')
        manifest['sources'][name]={'repository':repo,'commit':commit,'archive_sha256':digest(path),'directory':str(folders[0]),'url':url}
    path=root/'downloads'/DATASET['name'];download(DATASET['url'],path,size=DATASET['size'],md5=DATASET['md5'])
    destination=root/'datasets/unmixdb-set222'
    ensure_extracted(path,destination)
    manifest['dataset'].update(sha256=digest(path),directory=str(destination),record_id='1422385')
    (root/'sources.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Verified manifest: '+str(root/'sources.json'),flush=True)


if __name__=='__main__':main()
