"""Optional local vision (Ollama): look at a picture and answer in JSON. Fully offline; nothing leaves the PC.

Used by krita_look (describe the canvas or a layer) and by krita_cutout (check that each cut-out piece really is
what was asked for, so a wrong match is caught instead of silently added).
"""
import base64
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

import ollama_ctl  # noqa: E402
OLLAMA = ollama_ctl.OLLAMA          # normalized address
MODEL = os.environ.get('KRITA_EYES_MODEL') or config.CFG['vision_model']

LOOK_PROMPT = ('Describe this picture for an image editor in JSON only: {"summary": str (one or two sentences), '
               '"subjects": [str], "colours": str, "problems": [str]} where problems lists visible editing issues '
               'such as hard cut-out edges, halos or outlines, mismatched lighting or colour, seams, stretched or '
               'blurry areas, empty corners. Use an empty list if there are none. Be concrete and short.')
CHECK_PROMPT = ('This is one cut-out object on a plain grey background. The user asked to cut out: "{what}". '
                'Reply with JSON only: {{"match": true|false, "looks_like": str (what the object is, a few words), '
                '"complete": true|false (false if parts are clearly cut off), "note": str}}.')


class NotAvailable(RuntimeError):
    pass


def available():
    """(True, '') if the local vision model can be used now, else (False, reason). May start Ollama."""
    if not config.CFG['local_ai'].get('enabled', True):
        return False, 'local AI is turned off in config.json (local_ai.enabled)'
    import ollama_ctl
    if not ollama_ctl.ensure_running():
        return False, 'Ollama is not running and could not be started (optional: install it from ollama.com)'
    if not ollama_ctl.has_model(MODEL):
        return False, 'Ollama has no "%s" model yet; run: ollama pull %s' % (MODEL, MODEL)
    return True, ''


def ask(image_path, prompt, timeout=180):
    ok, why = available()
    if not ok:
        raise NotAvailable(why)
    with open(image_path, 'rb') as f:
        img = base64.b64encode(f.read()).decode('ascii')
    body = {'model': MODEL, 'stream': False, 'format': 'json', 'keep_alive': '10m', 'options': {'temperature': 0},
            'messages': [{'role': 'user', 'content': prompt, 'images': [img]}]}
    req = urllib.request.Request(OLLAMA + '/api/chat', json.dumps(body).encode(), {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = json.load(r)['message']['content']
    try:
        return json.loads(text)
    except ValueError:
        return {'raw': text}


def look(image_path):
    return ask(image_path, LOOK_PROMPT)


def check_piece(image_path, what):
    res = ask(image_path, CHECK_PROMPT.format(what=what.replace('"', "'")))
    if isinstance(res, dict) and 'match' in res:
        res['match'] = res['match'] in (True, 'true', 'True', 'yes')
    return res
