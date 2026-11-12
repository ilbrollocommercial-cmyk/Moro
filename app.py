"""FLUX: local-only media downloader. Run with bootstrap.py or python server.py."""
from __future__ import annotations
import atexit
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, send_file, send_from_directory, abort, session
from werkzeug.middleware.proxy_fix import ProxyFix
import yt_dlp

ROOT = Path(tempfile.mkdtemp(prefix='flux-assets-'))
_assets = {'manifest.webmanifest': '{"name":"FLUX — Il tuo link. Il tuo formato.","short_name":"FLUX","start_url":"/","display":"standalone","background_color":"#f8faff","theme_color":"#123aff","icons":[{"src":"/static/icon.svg","sizes":"any","type":"image/svg+xml","purpose":"any"}]}\n', 'icon.svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><rect width="128" height="128" rx="28" fill="#123aff"/><path d="M40 36 91 19v22L40 58zm0 31 44-15v21l-23 8v13h17l-28 23-27-23h17z" fill="white"/></svg>\n', 'index.html': '<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="theme-color" content="#123aff"><meta name="description" content="FLUX: download online da YouTube, TikTok, Instagram e Facebook."><meta property="og:title" content="FLUX — Il tuo link. Il tuo formato."><meta property="og:image" content="/static/icon.svg"><meta name="flux-token" content="__FLUX_TOKEN__"><link rel="icon" href="/static/icon.svg" type="image/svg+xml"><link rel="manifest" href="/static/manifest.webmanifest"><link rel="stylesheet" href="/static/style.css"><title>FLUX — Il tuo link. Il tuo formato.</title></head><body><header><a class="brand" href="/"><img src="/static/icon.svg" alt="" width="36" height="36">FLUX</a><span class="local"><i></i> Online · anche su iPhone</span><a class="help-link" href="#help">Come funziona</a></header><main><div class="eyebrow">DAL LINK AL FILE. SENZA GIRI.</div><h1>Il tuo link.<br><em>Il tuo formato.</em></h1><p class="intro">Incolla un link, scegli la qualità e scarica.<br>YouTube, TikTok, Instagram e Facebook, in un unico posto.</p><section class="workspace"><div class="platforms"><span class="youtube">▶ <b>YouTube</b></span><span>♪ <b>TikTok</b></span><span class="instagram">◎ <b>Instagram</b></span><span class="facebook">f <b>Facebook</b></span></div><form id="form"><label for="url">Link del video</label><div class="urlbox"><span aria-hidden="true">↗</span><input id="url" name="url" type="url" placeholder="Incolla qui il link…" autocomplete="off" required><button id="paste" type="button">Incolla</button></div><div class="settings"><fieldset><legend>Formato</legend><div class="pills" id="formats"><button type="button" class="selected" data-value="mp4" aria-pressed="true">MP4</button><button type="button" data-value="mp3" aria-pressed="false">MP3</button><button type="button" data-value="mov" aria-pressed="false">MOV</button><button type="button" data-value="webm" aria-pressed="false">WebM</button><button type="button" data-value="m4a" aria-pressed="false">M4A</button><button type="button" data-value="wav" aria-pressed="false">WAV</button></div></fieldset><fieldset><legend>Qualità video</legend><div class="pills" id="qualities"><button type="button" class="selected" data-value="best" aria-pressed="true">Massima</button><button type="button" data-value="2160" aria-pressed="false">4K</button><button type="button" data-value="1440" aria-pressed="false">1440p</button><button type="button" data-value="1080" aria-pressed="false">1080p</button><button type="button" data-value="720" aria-pressed="false">720p</button><button type="button" data-value="480" aria-pressed="false">480p</button><button type="button" data-value="360" aria-pressed="false">360p</button></div></fieldset></div><p class="hint" id="qualityhint">Scegli un limite di risoluzione. Il file finale rispetta quel limite, senza ingrandire il video.</p><button class="primary" id="submit" type="submit"><span>↓</span> Prepara il download</button><p id="error" class="error" role="alert" hidden></p></form><div class="statusbar"><span id="engine">Collegamento al motore…</span><span>Nessun account FLUX · nessun abbonamento</span></div></section><section id="downloads" aria-live="polite" hidden><div class="section-heading"><h2>I tuoi download</h2><span>Pronti quando lo sei tu.</span></div><div id="jobs"></div></section><div class="features"><span>↙ Video e audio</span><span>✧ Qualità a tua scelta</span><span>⌑ Salva sul tuo dispositivo</span></div><details id="help"><summary>Come funziona FLUX?</summary><div><p>1. Copia il link di un singolo video, reel o short da YouTube, TikTok, Instagram o Facebook.</p><p>2. Scegli formato e qualità. “Massima” usa il miglior flusso disponibile; 1080p o 720p impostano un limite, senza creare dettagli che non esistono nell’originale.</p><p>3. Premi “Prepara il download”, poi “Salva il file”. Tieni aperta questa pagina fino alla fine. La conversione può richiedere tempo, soprattutto per 4K, MOV e WebM.</p><p>MP3 viene esportato a 320 kbps, M4A a 256 kbps e WAV senza compressione: la qualità originale non può essere aumentata.</p><p>Su iPhone, premi “Salva il file” e apri Download in Safari: il risultato è nell’app File. Per aggiungere FLUX alla Home, usa Condividi → Aggiungi alla schermata Home.</p><p>Il server prepara i file temporanei, che scadono dopo circa un’ora e possono sparire a ogni riavvio. In questa versione di prova: massimo 20 minuti per video e 300 MB per sorgente, due lavori contemporanei. Un server gratuito può richiedere un’attesa al primo accesso.</p><p>Contenuti rimossi, accessi richiesti e blocchi delle piattaforme possono impedire il download.</p></div></details><footer><a href="/static/icon.svg" target="_blank">La copertina FLUX ↗</a><span>Il tuo link. Il tuo formato.</span><span>SEMPLICE. OVUNQUE. TUO.</span></footer></main><script src="/static/app.js" defer></script></body></html>\n', 'style.css': ":root{font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#131726;background:#f8faff;font-synthesis:none}*{box-sizing:border-box}body{margin:0}button,input{font:inherit}button,a{touch-action:manipulation}button{cursor:pointer}button:disabled{cursor:default;opacity:.45}a{color:inherit;text-decoration:none}header{max-width:1200px;margin:auto;display:flex;align-items:center;gap:20px;padding:27px 32px;border-bottom:1px solid #e2e8f1}.brand{display:flex;align-items:center;gap:10px;font-size:29px;font-weight:900;letter-spacing:-1px}.local{margin-left:auto;font-size:11px;color:#6c7891;background:#edf1fa;border:1px solid #dfe6f4;padding:9px 12px;border-radius:30px}.local i{display:inline-block;width:6px;height:6px;border-radius:50%;background:#4f966c;margin-right:5px}.help-link{font-size:12px;font-weight:600;margin-left:14px}main{max-width:1060px;padding:56px 30px 0;margin:auto}.eyebrow{text-align:center;font-size:9px;letter-spacing:2px;font-weight:750;color:#8892a7}h1{font-size:70px;font-weight:850;letter-spacing:-3.8px;line-height:1.04;text-align:center;margin:20px 0}h1 em{font-style:normal;color:#123aff}.intro{text-align:center;color:#7a8499;font-size:14px;line-height:1.8;margin:22px 0 35px}.workspace{padding:28px 30px 0;background:white;border-radius:21px;border:1px solid #e0e6f0;box-shadow:0 12px 40px #1c388808}.platforms{display:flex;gap:10px;margin-bottom:28px}.platforms>span{display:flex;justify-content:center;align-items:center;gap:8px;background:#f5f7fb;flex:1;border-radius:10px;padding:13px 8px;font-size:20px}.platforms b{font-size:12px;color:#222b3b}.platforms .youtube{color:#f12535}.platforms .instagram{color:#bc3b9c}.platforms .facebook{color:#1671ed;font-weight:900}label,legend{font-size:12px;font-weight:700;display:block;margin-bottom:10px}.urlbox{display:flex;align-items:center;gap:12px;border:1px solid #d2daea;border-radius:11px;padding:8px 10px 8px 15px}.urlbox:focus-within{outline:3px solid #123aff15;border-color:#123aff}.urlbox>span{color:#8792a7;font-size:22px}.urlbox input{flex:1;min-width:0;border:0;outline:0;font-size:14px;padding:7px 0;color:#25324d;background:transparent}.urlbox button{border:0;background:#eff3fc;color:#506383;font-size:11px;font-weight:650;border-radius:7px;padding:10px 13px}.settings{display:grid;grid-template-columns:1fr 1.15fr;gap:25px;margin-top:25px}fieldset{border:0;padding:0;margin:0;min-width:0}legend{padding:0}.pills{display:flex;flex-wrap:wrap;gap:6px}.pills button{background:#f1f5fc;border:1px solid transparent;border-radius:8px;padding:9px 12px;font-size:11px;font-weight:650;color:#526077}.pills button.selected{background:#123aff;color:white;box-shadow:0 4px 8px #123aff18}.hint{font-size:10px;line-height:1.7;color:#929bad;margin:17px 0 22px}.primary{border:0;display:block;width:100%;background:#123aff;color:white;border-radius:10px;padding:17px;font-size:15px;font-weight:650;box-shadow:0 5px 16px #123aff18}.primary>span{font-size:22px;margin-right:10px}.primary:hover{background:#0a2cdb}.statusbar{border-top:1px solid #edf0f7;margin:24px -30px 0;padding:14px 30px;display:flex;justify-content:space-between;gap:12px;font-size:9px;color:#8a94a8}.features{display:flex;justify-content:center;gap:40px;margin:29px 0 38px;font-size:12px;color:#68758f}.features span:first-letter{color:#123aff}details{border-top:1px solid #e1e7f1;border-bottom:1px solid #e1e7f1;padding:19px 3px;font-size:12px;color:#70809b}summary{cursor:pointer;font-weight:650;color:#38496b}details div{line-height:1.8;max-width:790px}footer{display:flex;justify-content:space-between;gap:12px;padding:25px 0;font-size:10px;color:#8a95aa}footer a{color:#355bba}footer span:last-child{font-size:8px;letter-spacing:1.3px}.section-heading{display:flex;align-items:center;justify-content:space-between;margin:27px 0 14px}.section-heading h2{font-size:18px;letter-spacing:-.5px;margin:0}.section-heading span{font-size:10px;color:#8794ac}.job{border:1px solid #e0e6f1;border-radius:13px;padding:19px 22px;background:white;margin:10px 0}.jobhead{display:flex;gap:15px;align-items:start}.jobhead h3{font-size:13px;line-height:1.5;margin:0;overflow-wrap:anywhere;flex:1}.tag{font-size:9px;background:#eff3ff;padding:5px 7px;border-radius:4px;color:#123aff}.job p{font-size:11px;color:#7f8da5;line-height:1.7}.job progress{width:100%;height:6px;accent-color:#123aff}.job-actions{display:flex;gap:10px;align-items:center;margin-top:15px}.save{background:#123aff;color:white;border-radius:7px;padding:11px 17px;font-size:12px;font-weight:600}.cancel{border:1px solid #e1e6f0;background:white;color:#7b89a1;border-radius:6px;font-size:10px;padding:8px 12px}.job .error,.error{color:#b1444b;font-size:12px;line-height:1.6}.job details{border:0;padding:5px 0;font-size:10px}.job pre{white-space:pre-wrap;word-break:break-word;font-size:10px;background:#f7f8fc;padding:12px;max-height:140px;overflow:auto}.job small{color:#8b96aa;font-size:10px}.job[data-state=done]{border-color:#bdcdec}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #85a1ff;outline-offset:3px}@media(max-width:650px){header{padding:20px;gap:8px}.brand{font-size:24px}.local{font-size:9px;padding:7px}.help-link{display:none}main{padding:37px 16px 0}h1{font-size:49px;letter-spacing:-2.7px}.intro{font-size:12px}.intro br{display:none}.workspace{padding:19px 18px 0;border-radius:16px}.platforms{gap:5px;margin-bottom:22px}.platforms>span{font-size:16px;flex-direction:column;gap:6px;padding:10px 4px}.platforms b{font-size:9px}.settings{grid-template-columns:1fr;gap:20px}.pills button{padding:10px 13px}.statusbar{margin:20px -18px 0;padding:13px 18px;flex-direction:column;gap:7px}.features{font-size:9px;gap:15px}footer>span:last-child{display:none}.section-heading span{display:none}.job{padding:16px}.eyebrow{font-size:8px}}\n", 'app.js': '\'use strict\';\nconst $=s=>document.querySelector(s);\nconst token=$(\'meta[name="flux-token"]\').content;\nlet format=\'mp4\',quality=\'best\',pollTimer=null,health=false;\nconst jobs=new Map();\nasync function api(path,options={}){\n const res=await fetch(path,{...options,headers:{\'Content-Type\':\'application/json\',\'X-Flux-Token\':token,...options.headers}});\n let data;try{data=await res.json()}catch{throw Error(\'Risposta del motore non valida. Ricarica la pagina.\')}\n if(!res.ok)throw Error(data.error||\'Richiesta non riuscita. Ricarica la pagina.\');return data;\n}\nfunction error(message){$(\'#error\').textContent=message;$(\'#error\').hidden=!message}\nfor(const id of [\'formats\',\'qualities\']){\n $(\'#\'+id).addEventListener(\'click\',e=>{const button=e.target.closest(\'button\');if(!button||button.disabled)return;\n $(\'#\'+id).querySelectorAll(\'button\').forEach(b=>{b.classList.toggle(\'selected\',b===button);b.setAttribute(\'aria-pressed\',b===button?\'true\':\'false\')});\n if(id===\'formats\'){format=button.dataset.value;const audio=[\'mp3\',\'m4a\',\'wav\'].includes(format);$(\'#qualities\').querySelectorAll(\'button\').forEach(b=>b.disabled=audio);$(\'#qualityhint\').textContent=audio?\'Audio dalla migliore sorgente disponibile. MP3 320 kbps · M4A 256 kbps · WAV non compresso.\':\'Scegli un limite di risoluzione. Il file finale rispetta quel limite, senza ingrandire il video.\'}else quality=button.dataset.value;\n });\n}\n$(\'#paste\').onclick=async()=>{try{$(\'#url\').value=await navigator.clipboard.readText();$(\'#url\').focus();error(\'\')}catch{error(\'Il browser non consente l’accesso agli appunti. Incolla il link con ⌘V o Ctrl+V.\');$(\'#url\').focus()}};\nfunction el(tag,text,cls){const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n}\nfunction render(job){\n let card=document.getElementById(\'job-\'+job.id);if(!card){card=el(\'article\',null,\'job\');card.id=\'job-\'+job.id;$(\'#jobs\').prepend(card)}\n card.dataset.state=job.state;card.replaceChildren();\n const head=el(\'div\',null,\'jobhead\');head.append(el(\'h3\',job.title||\'Il tuo download\'),el(\'span\',job.format.toUpperCase(),\'tag\'));card.append(head);\n const meta=[job.platform,job.height?job.height+\'p sorgente\':null,job.size?(job.size/1048576).toFixed(1)+\' MB\':null].filter(Boolean).join(\' · \');if(meta)card.append(el(\'small\',meta));\n card.append(el(\'p\',job.message,job.state===\'error\'?\'error\':\'\'));\n if(![\'done\',\'error\',\'cancelled\'].includes(job.state)){const progress=el(\'progress\');progress.max=100;if(job.percent!=null)progress.value=job.percent;card.append(progress);if(job.speed)card.append(el(\'small\',`${(job.speed/1048576).toFixed(1)} MB/s${job.eta?\' · circa \'+Math.ceil(job.eta)+\' s\':\'\'}`));const actions=el(\'div\',null,\'job-actions\');const cancel=el(\'button\',\'Annulla\',\'cancel\');cancel.onclick=async()=>{cancel.disabled=true;try{await api(\'/api/jobs/\'+job.id+\'/cancel\',{method:\'POST\'});cancel.textContent=\'Annullamento…\'}catch(e){error(e.message);cancel.disabled=false}};actions.append(cancel);card.append(actions)}\n if(job.state===\'done\'){const actions=el(\'div\',null,\'job-actions\'),a=el(\'a\',\'↓ Salva il file\',\'save\');a.href=\'/download/\'+job.id;a.download=job.filename;actions.append(a);card.append(actions)}\n if(job.detail){const d=el(\'details\');d.append(el(\'summary\',\'Dettagli tecnici\'),el(\'pre\',job.detail));card.append(d)}\n $(\'#downloads\').hidden=false;\n}\nasync function poll(){\n const active=[...jobs.values()].filter(j=>![\'done\',\'error\',\'cancelled\'].includes(j.state));\n if(!active.length){pollTimer=null;return}\n try{for(const job of active){const updated=await api(\'/api/jobs/\'+job.id);jobs.set(job.id,updated);render(updated)}error(\'\')}catch(e){error(\'Connessione al motore interrotta. Tieni aperta questa pagina. Riprovo…\')}\n pollTimer=setTimeout(poll,1200);\n}\n$(\'#form\').onsubmit=async e=>{e.preventDefault();error(\'\');$(\'#submit\').disabled=true;\n try{const j=await api(\'/api/jobs\',{method:\'POST\',body:JSON.stringify({url:$(\'#url\').value.trim(),format,quality})});jobs.set(j.id,j);render(j);if(!pollTimer)poll();$(\'#downloads\').scrollIntoView({behavior:\'smooth\',block:\'nearest\'})}catch(e){error(e.message)}finally{$(\'#submit\').disabled=!health}\n};\n(async()=>{try{const h=await api(\'/api/health\');health=true;$(\'#engine\').textContent=\'● Motore pronto · \'+h.engine+(h.js?\'\':\' · runtime YouTube mancante\');if(!h.js)error(\'Per il supporto completo a YouTube installa Deno e riapri FLUX. Gli altri siti possono comunque funzionare.\')}catch(e){$(\'#engine\').textContent=\'Motore non collegato\';error(\'Il server non risponde. Attendi un minuto e ricarica la pagina.\')}$(\'#submit\').disabled=!health})();\n'}
(ROOT / 'static').mkdir()
for _name, _text in _assets.items():
    (ROOT / 'static' / _name).write_text(_text)

WORK = Path(tempfile.mkdtemp(prefix='flux-'))
atexit.register(lambda: shutil.rmtree(WORK, ignore_errors=True))
TOKEN = secrets.token_urlsafe(32)
WEB = os.environ.get('FLUX_WEB') == '1'
JOBS = {}
LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=2)
app = Flask(__name__, static_folder=str(ROOT / 'static'))
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024
app.secret_key = os.environ.get('FLUX_SECRET') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=WEB)
if WEB:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
FORMATS = {'mp4', 'mov', 'webm', 'mp3', 'm4a', 'wav'}
QUALITIES = {'best', '2160', '1440', '1080', '720', '480', '360'}
HOSTS = {'youtube.com','youtu.be','tiktok.com','instagram.com','facebook.com','fb.watch','fb.com'}

def validate_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError('Incolla un link valido.')
    value = value.strip()
    try:
        p = urlsplit(value)
        host = (p.hostname or '').lower().rstrip('.')
        port = p.port
    except ValueError:
        raise ValueError('Link non valido.')
    if p.scheme not in {'https', 'http'} or p.username or p.password or port not in {None, 80, 443}:
        raise ValueError('Usa un normale link https del video.')
    if not any(host == h or host.endswith('.' + h) for h in HOSTS):
        raise ValueError('Sono supportati YouTube, TikTok, Instagram e Facebook.')
    if not p.path.strip('/'):
        raise ValueError('Incolla il link di un video, non la pagina iniziale.')
    return value

def ffmpeg_binary():
    custom = os.environ.get('FLUX_FFMPEG')
    if custom and Path(custom).is_file():
        return custom
    found = shutil.which('ffmpeg')
    if found:
        return found
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def runtime_options():
    deno = ROOT / '.tools' / ('deno.exe' if os.name == 'nt' else 'deno')
    if deno.is_file():
        return {'deno': {'path': str(deno)}}
    if shutil.which('deno'):
        return {'deno': {}}
    if shutil.which('node'):
        return {'node': {}}
    return {}

def download_options(folder, quality, hook=None):
    cap = '' if quality == 'best' else f'[height<={int(quality)}]'
    return {
        'format': f'bv*{cap}+ba/b{cap}/bv*+ba/best',
        'merge_output_format': 'mkv',
        'outtmpl': str(folder / 'source.%(ext)s'),
        'noplaylist': True, 'playlist_items': '1',
        'max_filesize': 300 * 1024 * 1024 if WEB else None,
        'match_filter': (lambda info, **kw: 'Video troppo lungo: massimo 20 minuti sul server gratuito.' if (info.get('duration') or 0) > 1200 else None) if WEB else None,
        'quiet': True, 'no_warnings': True,
        'socket_timeout': 25, 'retries': 2, 'fragment_retries': 2,
        'overwrites': True, 'continuedl': False,
        'ffmpeg_location': ffmpeg_binary(),
        'js_runtimes': runtime_options(),
        'progress_hooks': [hook] if hook else [],
        'restrictfilenames': True,
        'cachedir': str(ROOT / '.cache'),
        'logger': SilentLogger(),
    }

class SilentLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass

class Cancelled(Exception): pass

def update(job_id, **values):
    with LOCK:
        JOBS[job_id].update(values)

def public_job(job):
    return {k: v for k, v in job.items() if k not in {'folder', 'file', 'cancel', 'created', 'owner'}}

def friendly_error(error):
    msg = re.sub(r'\x1b\[[0-9;]*m', '', str(error))
    if any(x in msg.lower() for x in ['sign in', 'login', 'log in', 'cookies', 'private', 'not a bot']):
        prefix = 'La piattaforma richiede un accesso o una verifica. Prova un video pubblico diverso.'
    elif 'format' in msg.lower() and 'not available' in msg.lower():
        prefix = 'Questa risoluzione non è disponibile. Prova “Massima disponibile” o una qualità inferiore.'
    elif any(x in msg.lower() for x in ['403', '429', 'blocked', 'restricted']):
        prefix = 'La piattaforma ha limitato il download. Riprova più tardi o aggiorna il motore.'
    else:
        prefix = 'Download non riuscito. Verifica il link e la connessione, oppure aggiorna il motore.'
    return prefix, msg[-1200:]

def transcode(source, target, format_, job_id=None, quality="best"):
    ff = ffmpeg_binary()
    audio = {'mp3': ['-vn','-c:a','libmp3lame','-b:a','320k'],
             'm4a': ['-vn','-c:a','aac','-b:a','256k'],
             'wav': ['-vn','-c:a','pcm_s16le']}
    if format_ in audio:
        options = audio[format_]
    elif format_ == 'webm':
        options = ['-map','0:v:0','-map','0:a:0?','-c:v','libvpx-vp9','-crf','24','-b:v','0','-c:a','libopus']
    else:
        options = ['-map','0:v:0','-map','0:a:0?','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart']
    if format_ not in audio and quality != 'best':
        options += ['-vf', rf'scale=-2:trunc(min(ih\,{int(quality)})/2)*2']
    # Arguments are passed as an array. User input never becomes a shell command.
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen([ff,'-hide_banner','-loglevel','error','-nostdin','-y','-i',str(source),*options,str(target)], stdout=subprocess.DEVNULL, stderr=err)
        start = time.monotonic()
        try:
            while proc.poll() is None:
                if job_id and JOBS[job_id]['cancel'].is_set():
                    raise Cancelled()
                if time.monotonic() - start > (1800 if WEB else 7200):
                    raise RuntimeError('Conversione interrotta dopo due ore.')
                time.sleep(.2)
            if proc.returncode:
                err.seek(0)
                raise RuntimeError(err.read().decode(errors='replace')[-1200:])
        finally:
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill(); proc.wait()
    if not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError('Nessun file prodotto.')

def run_job(job_id, url, format_, quality):
    job = JOBS[job_id]
    folder = job['folder']
    def progress(data):
        if job['cancel'].is_set(): raise Cancelled()
        if WEB and (time.time()-job['created'] > 1800 or data.get('downloaded_bytes',0) > 300*1024*1024):
            raise RuntimeError('Limite server raggiunto: prova un video più breve o una qualità inferiore.')
        size = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
        done = data.get('downloaded_bytes', 0)
        pct = round(100 * done / size, 1) if size else None
        if data.get('status') == 'downloading':
            update(job_id, state='downloading', message='Download in corso…', percent=min(99, pct) if pct is not None else None,
                   speed=data.get('speed'), eta=data.get('eta'))
    try:
        update(job_id, state='analyzing', message='Lettura del link…')
        options = download_options(folder, quality, progress)
        if format_ in {'mp3','m4a','wav'}: options['format'] = 'bestaudio/best'
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
        if job['cancel'].is_set(): raise Cancelled()
        if not info or info.get('_type') in {'playlist','multi_video'}:
            raise ValueError('Usa il link di un singolo video o reel.')
        candidates = [p for p in folder.glob('source.*') if p.suffix not in {'.part','.ytdl','.temp'} and '.f' not in p.name.removeprefix('source')]
        if not candidates: raise RuntimeError('La piattaforma non ha restituito un file video o audio.')
        source = max(candidates, key=lambda p:p.stat().st_mtime)
        update(job_id, state='converting', message=f'Preparazione del file {format_.upper()}…', percent=None,
               title=info.get('title') or 'Video', platform=info.get('extractor_key') or '',
               height=info.get('height'), duration=info.get('duration'))
        target = folder / ('download.' + format_)
        transcode(source, target, format_, job_id, quality)
        if job['cancel'].is_set(): raise Cancelled()
        title = str(info.get('title') or 'FLUX-video')
        title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '-', title).strip(' .')[:150] or 'FLUX-video'
        update(job_id, state='done', message='Il tuo file è pronto.', percent=100, file=target,
               filename=title+'.'+format_, size=target.stat().st_size)
        for other in folder.iterdir():
            if other != target and other.is_file(): other.unlink(missing_ok=True)
    except Cancelled:
        update(job_id, state='cancelled', message='Download annullato.', percent=None)
        shutil.rmtree(folder, ignore_errors=True)
    except Exception as e:
        if job['cancel'].is_set():
            update(job_id, state='cancelled', message='Download annullato.', percent=None)
        else:
            message, detail = friendly_error(e)
            update(job_id, state='error', message=message, detail=detail, percent=None)
        shutil.rmtree(folder, ignore_errors=True)

def clean_jobs():
    now = time.time()
    with LOCK:
        expired = [k for k,v in JOBS.items() if v['state'] in {'done','error','cancelled'} and now-v['created']>3600]
        for k in expired:
            shutil.rmtree(JOBS[k]['folder'], ignore_errors=True)
            del JOBS[k]

@app.before_request
def local_only():
    if not WEB and request.host.split(':')[0] not in {'127.0.0.1','localhost'}: abort(403)
    origin = request.headers.get('Origin')
    if origin and origin != request.host_url.rstrip('/'): abort(403)
    if WEB:
        if 'owner' not in session:
            session['owner'] = secrets.token_urlsafe(24)
            session['csrf'] = secrets.token_urlsafe(32)
        expected = session['csrf']
    else:
        expected = TOKEN
    if request.path.startswith('/api/') and not (WEB and request.path == '/api/health') and not secrets.compare_digest(request.headers.get('X-Flux-Token',''), expected): abort(403)

@app.after_request
def headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Cache-Control'] = 'no-store' if not request.path.startswith('/static/') else 'public, max-age=3600'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    return response

@app.get('/')
def index():
    return (ROOT / 'static/index.html').read_text().replace('__FLUX_TOKEN__', session['csrf'] if WEB else TOKEN)

@app.get('/api/health')
def health():
    return jsonify(ok=True, engine=yt_dlp.version.__version__, ffmpeg=bool(ffmpeg_binary()), js=bool(runtime_options()))

@app.post('/api/jobs')
def create_job():
    data = request.get_json(silent=True) or {}
    try: url = validate_url(data.get('url'))
    except ValueError as e: return jsonify(error=str(e)), 400
    format_, quality = data.get('format'), data.get('quality')
    if format_ not in FORMATS or quality not in QUALITIES:
        return jsonify(error='Formato o qualità non validi.'), 400
    clean_jobs()
    with LOCK:
        if sum(j['state'] not in {'done','error','cancelled'} for j in JOBS.values()) >= 2:
            return jsonify(error='Ci sono già due download in corso. Attendi o annullane uno.'), 429
        job_id = uuid.uuid4().hex
        folder = WORK / job_id
        folder.mkdir()
        JOBS[job_id] = dict(id=job_id, state='queued', message='In coda…', percent=None, title='', format=format_,
                            folder=folder, cancel=threading.Event(), created=time.time(), owner=session.get('owner') if WEB else None)
        POOL.submit(run_job, job_id, url, format_, quality)
        return jsonify(public_job(JOBS[job_id])), 202

@app.get('/api/jobs/<job_id>')
def get_job(job_id):
    with LOCK:
        job=JOBS.get(job_id)
        if not job or (WEB and job.get('owner') != session.get('owner')): abort(404)
        return jsonify(public_job(job))

@app.post('/api/jobs/<job_id>/cancel')
def cancel_job(job_id):
    with LOCK:
        job=JOBS.get(job_id)
        if not job or (WEB and job.get('owner') != session.get('owner')): abort(404)
        if job['state'] not in {'done','error','cancelled'}: job['cancel'].set()
    return jsonify(ok=True)

@app.get('/download/<job_id>')
def download(job_id):
    with LOCK:
        job=JOBS.get(job_id)
        if not job or (WEB and job.get('owner') != session.get('owner')) or job['state']!='done' or not job.get('file') or not job['file'].is_file(): abort(404)
        return send_file(job['file'], as_attachment=True, download_name=job['filename'], conditional=True)

if __name__ == '__main__':
    from werkzeug.serving import make_server
    import webbrowser
    port = int(os.environ.get('FLUX_PORT','8765'))
    try: server=make_server('127.0.0.1', port, app, threaded=True)
    except SystemExit:
        print('Porta occupata. Chiudi l’altra finestra FLUX oppure imposta FLUX_PORT.'); raise
    address=f'http://127.0.0.1:{port}'
    print(f'\nFLUX è pronto: {address}\nLascia aperta questa finestra. Ctrl+C per chiudere.\n', flush=True)
    if os.environ.get('FLUX_NO_BROWSER') != '1':
        threading.Timer(1, lambda:webbrowser.open(address)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        for job in JOBS.values(): job['cancel'].set()
        POOL.shutdown(wait=True, cancel_futures=True)
        server.server_close()
