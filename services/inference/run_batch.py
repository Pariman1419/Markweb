"""Transfer a frozen image batch to the AI host, run inference, and retrieve outputs."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

from mark_engine.adapters.env import load_env
from mark_engine.freeze import check_freeze


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda: file.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--freeze', type=Path, default=Path('mark_engine/rules/data/FREEZE-R1.json'))
    parser.add_argument('--url', default='http://10.151.28.9:8095')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    frozen = check_freeze(repo, args.freeze)
    validation_path = repo / 'services' / 'inference' / 'validation.json'
    validation = json.loads(validation_path.read_text(encoding='utf-8'))
    if args.url.rstrip('/') != validation['reocr_url']:
        raise ValueError('re-OCR endpoint differs from validated environment')
    load_env()
    import paramiko
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(os.environ['AI_SERVER_HOST'], username=os.environ['AI_SERVER_USER'],
                   password=os.environ['AI_SERVER_PASSWORD'], timeout=10, allow_agent=False, look_for_keys=False)

    def run(command, *, stream=False):
        _, stdout, stderr = client.exec_command(command, timeout=14400, get_pty=stream)
        if stream:
            for line in iter(stdout.readline, ''):
                print(line.rstrip(), flush=True)
        else:
            output = stdout.read().decode('utf-8', errors='replace').strip()
        status = stdout.channel.recv_exit_status()
        if status:
            raise RuntimeError(f'AI command failed ({status}): {stderr.read().decode(errors="replace")[-500:]}')
        return '' if stream else output

    try:
        sftp = client.open_sftp()
        home = sftp.normalize('.')
        if not home.startswith('/home/') or not re.fullmatch(r'/home/[A-Za-z0-9_.-]+', home):
            raise RuntimeError('Unexpected remote home directory')
        with (args.cache / 'images_index.csv').open(encoding='utf-8-sig', newline='') as file:
            rows = list(csv.DictReader(file))
        if not rows:
            raise ValueError('image index is empty')
        names = sorted({row['image'] for row in rows})
        if any(not re.fullmatch(r'[0-9a-f]{64}\.png', name) for name in names):
            raise ValueError('unexpected image filename')
        index_hash = digest(args.cache / 'images_index.csv')
        remote = home + '/mark_phase1_blind_' + index_hash[:16]
        for path in (remote, remote + '/images'):
            try:
                sftp.mkdir(path)
            except OSError:
                if not sftp.stat(path).st_mode:
                    raise
        for name in names:
            path = args.cache / 'images' / name
            if digest(path) != name[:-4]:
                raise ValueError(f'local image hash mismatch: {name}')
            target = remote + '/images/' + name
            try:
                if sftp.stat(target).st_size == path.stat().st_size:
                    continue
            except OSError:
                pass
            sftp.put(str(path), target)
        for name in ('det_rec_batch.py', 'yolo_batch.py'):
            sftp.put(str(repo / 'services' / 'inference' / name), remote + '/' + name)
        sftp.close()
        q = shlex.quote
        for name in names:
            actual = run('sha256sum ' + q(remote + '/images/' + name)).split()[0]
            if actual != name[:-4]:
                raise ValueError(f'remote image hash mismatch: {name}')
        image_id = run("docker image inspect ic-marking-ocr:exp09 --format '{{.Id}}'")
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
            raise ValueError('unexpected OCR image ID')
        weights = home + '/ic_marking_symdet/runs/symdet_v2/weights/best.pt'
        det = home + '/ic_marking_h1/paddlex_cache/official_models/PP-OCRv5_server_det/inference.pdiparams'
        symbol_hash = run('sha256sum ' + q(weights)).split()[0]
        det_hash = run('sha256sum ' + q(det)).split()[0]
        det_config = run('sha256sum ' + q(det.rsplit('/', 1)[0] + '/inference.json')).split()[0]
        det_settings = run('sha256sum ' + q(det.rsplit('/', 1)[0] + '/inference.yml')).split()[0]
        ocr_hash = run('docker run --rm --entrypoint sha256sum ' + q(image_id) + ' /models/exp09/inference.pdiparams').split()[0]
        service_hash = run('docker exec ic-marking-ocr sha256sum /models/exp09/inference.pdiparams').split()[0]
        service_image = run("docker inspect ic-marking-ocr --format '{{.Image}}'")
        versions = run(q(home + '/ic_marking_symdet/venv/bin/python') +
                       " -c 'import ultralytics,torch; print(ultralytics.__version__); print(torch.__version__)'").splitlines()
        observed = {'ocr_image_id': image_id, 'ocr_rec_sha256': ocr_hash, 'symbol_sha256': symbol_hash,
                    'detector_sha256': det_hash, 'detector_config_sha256': det_config,
                    'detector_settings_sha256': det_settings,
                    'ultralytics_version': versions[0], 'torch_version': versions[1]}
        if any(validation.get(key) != value for key, value in observed.items()) or service_image != image_id:
            raise ValueError('AI runtime or model differs from historical validation')
        registry = json.loads((repo / 'models' / 'REGISTRY.json').read_text(encoding='utf-8'))
        approved = {entry['name']: entry for entry in registry['models']}
        if (symbol_hash != approved['symdet']['weights_sha256'] or
                ocr_hash != approved['ocr-rec-exp09']['weights_sha256'] or service_hash != ocr_hash):
            raise ValueError('AI model weights do not match registry')
        cache_mount = home + '/ic_marking_h1/paddlex_cache:/root/.paddlex'
        run('docker run --rm -v ' + q(remote + ':/work') + ' -v ' + q(cache_mount) + ' ' + q(image_id) +
            ' python /work/det_rec_batch.py /work/images /work/det_rec.json', stream=True)
        run(q(home + '/ic_marking_symdet/venv/bin/python') + ' ' + q(remote + '/yolo_batch.py') + ' ' +
            q(weights) + ' ' + q(remote + '/images') + ' ' + q(remote + '/detections.json'), stream=True)
        if (run('sha256sum ' + q(weights)).split()[0] != symbol_hash or
                run('sha256sum ' + q(det)).split()[0] != det_hash or
                run('sha256sum ' + q(det.rsplit('/', 1)[0] + '/inference.json')).split()[0] != det_config or
                run('sha256sum ' + q(det.rsplit('/', 1)[0] + '/inference.yml')).split()[0] != det_settings):
            raise ValueError('model weights changed during inference')
        sftp = client.open_sftp()
        for name in ('det_rec.json', 'detections.json'):
            temp = args.cache / (name + '.part')
            sftp.get(remote + '/' + name, str(temp))
            temp.replace(args.cache / name)
        sftp.close()
        subprocess.run([sys.executable, '-m', 'services.inference.reocr_batch', str(args.cache / 'images'),
                        str(args.cache / 'det_rec.json'), str(args.cache / 'reocr.csv'), '--url', args.url,
                        '--trim-logo'], check=True)
        if (run('docker exec ic-marking-ocr sha256sum /models/exp09/inference.pdiparams').split()[0] != service_hash or
                run("docker inspect ic-marking-ocr --format '{{.Image}}'") != image_id):
            raise ValueError('recognizer service model changed during inference')
        record = {'freeze_id': frozen['freeze_id'], 'code_sha256': frozen['code_sha256'],
                  'images_index_sha256': index_hash, 'ocr_image_id': image_id, 'ocr_rec_sha256': ocr_hash,
                  'symbol_sha256': symbol_hash, 'detector_sha256': det_hash,
                  'validation_sha256': digest(validation_path), 'runtime': observed,
                  'output_sha256': {name: digest(args.cache / name) for name in ('det_rec.json', 'detections.json', 'reocr.csv')}}
        (args.cache / 'models.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        print('Completed AI batch:', len(names), 'images', flush=True)
    finally:
        client.close()


if __name__ == '__main__':
    main()
