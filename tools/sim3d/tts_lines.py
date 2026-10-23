"""Generate narrator lines with the free local kokoro voice. Usage: python3 tts_lines.py lines.json out_dir"""
import json, os, sys, wave
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import quiz as Q
spec = json.load(open(sys.argv[1]))
out = sys.argv[2]
os.makedirs(out, exist_ok=True)
voices = Q.tts_all(spec['lines'], spec.get('voice', 'am_michael'), spec.get('speed', 1.08))
durs = []
for i, v in enumerate(voices):
    pcm = (np.clip(v, -1, 1) * 32767).astype('<i2')
    with wave.open(os.path.join(out, f'l{i}.wav'), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(Q.SR); w.writeframes(pcm.tobytes())
    durs.append(len(v) / Q.SR)
json.dump(durs, open(os.path.join(out, 'durs.json'), 'w'))
print([round(d, 2) for d in durs], round(sum(durs), 2))
