# -*- coding: utf-8 -*-
"""Convert MBPP+ samples from completion format to EvalPlus solution format."""
import json, os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

for name in ['scaffolded', 'raw']:
    src = os.path.join(OUT_DIR, f'samples_mbpp_{name}.jsonl')
    dst = os.path.join(OUT_DIR, f'samples_mbpp_{name}_evalplus.jsonl')
    if not os.path.exists(src):
        print(f'Skip {name}: {src} not found')
        continue
    lines = open(src, 'r', encoding='utf-8').readlines()
    with open(dst, 'w', encoding='utf-8') as f:
        for l in lines:
            j = json.loads(l)
            f.write(json.dumps({'task_id': j['task_id'], 'solution': j['completion']}, ensure_ascii=False) + '\n')
    print(f'{name}: {len(lines)} samples -> {dst}')
