"""Download the public UVR instrumental model and its hash-keyed metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, default=Path('D:/AI-DJ-data/separation/models'))
    args = parser.parse_args()
    args.model_dir.mkdir(parents=True, exist_ok=True)
    url = 'https://raw.githubusercontent.com/TRvlvr/application_data/main/mdx_model_data/model_data_new.json'
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    metadata = response.json()
    (args.model_dir/'mdx_model_data.json').write_text(json.dumps(metadata), encoding='utf-8')
    name = 'UVR-MDX-NET-Inst_HQ_3.onnx'
    destination = args.model_dir/name
    if not destination.exists():
        model_url = 'https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/'+name
        temporary = args.model_dir/(name+'.part')
        with requests.get(model_url, stream=True, timeout=(30, 120)) as model:
            model.raise_for_status()
            with temporary.open('wb') as output:
                for block in model.iter_content(1024*1024):
                    output.write(block)
        temporary.replace(destination)
    blob = destination.read_bytes()
    fingerprint = hashlib.md5(blob[-10000*1024:]).hexdigest()
    parameters = metadata[fingerprint]
    if parameters['primary_stem'] != 'Instrumental':
        raise ValueError('Downloaded model is not an instrumental separator')
    selected = {'filename': name, 'sha256': hashlib.sha256(blob).hexdigest(),
                'uvr_hash': fingerprint, 'parameters': parameters}
    (args.model_dir/'selected_model.json').write_text(json.dumps(selected, indent=2), encoding='utf-8')
    print(f'Model ready: {destination}')


if __name__ == '__main__':
    main()
