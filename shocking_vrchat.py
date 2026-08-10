import asyncio
import collections
import datetime
import yaml, uuid, os, sys, traceback, time, socket, re, json
from threading import Thread
from loguru import logger
import copy

from fastapi import FastAPI, Request, WebSocket, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from websockets.server import serve as wsserve

import srv
from srv.connector.coyotev3ws import DGWSMessage, DGConnection
from srv.connector.coyotev4ws import DGV4Connection, DGV4RelayServer
from srv.handler.shock_handler import ShockHandler
from srv.command_queue import CommandQueue, CommandPriority

from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.dispatcher import Dispatcher


def get_runtime_base_dir():
    """Bundled resources dir (static, templates - packed inside binary)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_exe_dir():
    """Directory where the exe/script lives (for external files: wave_presets, dg-lab, configs)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


RUNTIME_BASE_DIR = get_runtime_base_dir()
STATIC_DIR = os.path.join(RUNTIME_BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(RUNTIME_BASE_DIR, "templates")

app = FastAPI(docs_url=None, redoc_url=None)

WAVE_HISTORY_SAMPLE_MS = 25

CONFIG_FILE_VERSION  = 'v0.2'
APP_VERSION = '0.6.2'  # Semantic version of the application
GITHUB_REPO = 'MoLiYue/Shocking-VRChat'
CONFIG_FILENAME = f'settings-advanced-{CONFIG_FILE_VERSION}.yaml'
CONFIG_FILENAME_BASIC = f'settings-{CONFIG_FILE_VERSION}.yaml'
CONFIG_HOT_RELOAD_INTERVAL = 1.0
SETTINGS_BASIC = {
    'dglab3':{
        'channel_a': {
            'avatar_params': [
                {'path': '/avatar/parameters/pcs/contact/enterPass', 'mode': 'distance'},
                {'path': '/avatar/parameters/Shock/TouchAreaA', 'mode': 'distance'},
                {'path': '/avatar/parameters/Shock/TouchAreaC', 'mode': 'distance'},
                {'path': '/avatar/parameters/Shock/wildcard/*', 'mode': 'distance'},
            ],
            'mode': 'distance',
            'strength_limit': 5,
            'overlimit_max': 20,
        },
        'channel_b': {
            'avatar_params': [
                {'path': '/avatar/parameters/pcs/contact/enterPass', 'mode': 'distance'},
                {'path': '/avatar/parameters/lms-penis-proximityA*', 'mode': 'distance'},
                {'path': '/avatar/parameters/Shock/TouchAreaB', 'mode': 'distance'},
                {'path': '/avatar/parameters/Shock/TouchAreaC', 'mode': 'distance'},
            ],
            'mode': 'distance',
            'strength_limit': 5,
            'overlimit_max': 20,
        }
    },
    'version': CONFIG_FILE_VERSION,
}

DEFAULT_SHOCK_WAVE = '["0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464"]'

def _default_mode_config():
    return {
        'shock': {
            'duration': 2,
            'wave': DEFAULT_SHOCK_WAVE,
            'wave_preset': None,
            'wave_scale': 1.0,
        },
        'distance': {
            'freq_ms': 10,
            'wave_preset': None,
            'wave_scale': 1.0,
        },
        'touch': {
            'wave_preset': None,
            'wave_scale': 1.0,
            'n_derivative': 1,
        },
        'combo': {
            'enabled': False,
            'shock_threshold': 0.9,
            'shock_hold_ms': 200,
        },
        'trigger_range': {
            'bottom': 0.0,
            'top': 0.8,
        },
    }

SETTINGS = {
    'SERVER_IP': None,
    'dglab3': {
        'channel_a': {'mode_config': _default_mode_config()},
        'channel_b': {'mode_config': _default_mode_config()},
    },
    'ws': {
        'master_uuid': None,
        'listen_host': '0.0.0.0',
        'listen_port': 28846,
        'v4_enabled': True,
    },
    'osc': {
        'listen_host': '127.0.0.1',
        'listen_port': 9001,
    },
    'web_server': {
        'listen_host': '127.0.0.1',
        'listen_port': 8800,
    },
    'log_level': 'INFO',
    'version': CONFIG_FILE_VERSION,
    'general': {
        'auto_open_qr_web_page': True,
        'local_ip_detect': {
            'host': '223.5.5.5',
            'port': 80,
        },
        'github_mirror': '',  # e.g. 'https://mirror.ghproxy.com/' for China mainland
    },
}
DEFAULT_SETTINGS_BASIC = copy.deepcopy(SETTINGS_BASIC)
DEFAULT_SETTINGS = copy.deepcopy(SETTINGS)
SERVER_IP = None
CONFIG_MTIMES = {}
handlers = []


def merge_defaults(defaults, current):
    if isinstance(defaults, dict) and isinstance(current, dict):
        merged = copy.deepcopy(current)
        for key, value in defaults.items():
            if key in merged:
                merged[key] = merge_defaults(value, merged[key])
            else:
                merged[key] = copy.deepcopy(value)
        return merged
    return copy.deepcopy(current)


def normalize_avatar_param_entries(channel_settings: dict):
    default_mode = channel_settings.get('mode', 'distance')
    normalized = []
    for entry in channel_settings.get('avatar_params', []):
        if isinstance(entry, str):
            normalized.append({'path': entry, 'mode': default_mode, 'enabled': True})
        elif isinstance(entry, dict):
            normalized.append({
                'path': entry.get('path', ''),
                'mode': entry.get('mode', default_mode),
                'enabled': entry.get('enabled', True),
            })
    channel_settings['avatar_params'] = normalized


def load_config_files():
    with open(CONFIG_FILENAME_BASIC, 'r', encoding='utf-8') as f:
        basic = yaml.safe_load(f)
    with open(CONFIG_FILENAME, 'r', encoding='utf-8') as f:
        advanced = yaml.safe_load(f)
    basic = merge_defaults(DEFAULT_SETTINGS_BASIC, basic)
    advanced = merge_defaults(DEFAULT_SETTINGS, advanced)
    # Sync basic params into advanced
    for ch in ['channel_a', 'channel_b']:
        advanced['dglab3'][ch]['avatar_params'] = basic['dglab3'][ch]['avatar_params']
        advanced['dglab3'][ch]['mode'] = basic['dglab3'][ch]['mode']
        advanced['dglab3'][ch]['strength_limit'] = basic['dglab3'][ch]['strength_limit']
        if 'overlimit_max' in basic['dglab3'][ch]:
            advanced['dglab3'][ch]['overlimit_max'] = basic['dglab3'][ch]['overlimit_max']
        normalize_avatar_param_entries(advanced['dglab3'][ch])
    return advanced, basic


def reset_logger():
    logger.remove()
    # Only add stderr sink when console is available (--noconsole / GUI mode sets it to None)
    if sys.stderr is not None:
        logger.add(sys.stderr, level=SETTINGS.get('log_level', 'INFO'))
    # File log (always available, even without console)
    _log_file = os.path.join(get_exe_dir(), 'shocking_vrchat.log')
    logger.add(_log_file, level='DEBUG', rotation='5 MB', retention=2, encoding='utf-8')
    logger.add(_log_buffer_sink, level=SETTINGS.get('log_level', 'INFO'), format="{time:HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}")


# --- Log buffer for web UI ---
_LOG_BUFFER_MAX = 500
_log_buffer: list = []  # [{text, level, time}]

def _log_buffer_sink(message):
    record = message.record
    entry = {
        'text': str(message).rstrip('\n'),
        'level': record['level'].name.lower(),
        'time': record['time'].timestamp(),
    }
    _log_buffer.append(entry)
    if len(_log_buffer) > _LOG_BUFFER_MAX:
        del _log_buffer[:len(_log_buffer) - _LOG_BUFFER_MAX]
    # Push to WebSocket subscribers
    try:
        _ws_broadcast_sync('log', entry)
    except:
        pass


def update_config_mtimes():
    for path in [CONFIG_FILENAME, CONFIG_FILENAME_BASIC]:
        if os.path.exists(path):
            CONFIG_MTIMES[path] = os.path.getmtime(path)


def has_config_file_changed():
    for path, previous_mtime in CONFIG_MTIMES.items():
        current_mtime = os.path.getmtime(path) if os.path.exists(path) else None
        if current_mtime != previous_mtime:
            return True
    return False


def apply_hot_reloadable_settings(new_settings, new_settings_basic):
    global SERVER_IP
    old_settings = copy.deepcopy(SETTINGS)

    engine_restart_needed = False
    ws_restart_needed = False

    if new_settings['osc'] != old_settings['osc']:
        engine_restart_needed = True
    if new_settings['ws'] != old_settings['ws']:
        ws_restart_needed = True
    if new_settings.get('SERVER_IP') != old_settings.get('SERVER_IP'):
        engine_restart_needed = True

    old_basic = copy.deepcopy(SETTINGS_BASIC)
    if new_settings_basic['dglab3'] != old_basic['dglab3']:
        if any(
            new_settings_basic['dglab3'][ch]['avatar_params'] != old_basic['dglab3'][ch]['avatar_params'] or
            new_settings_basic['dglab3'][ch]['mode'] != old_basic['dglab3'][ch]['mode']
            for ch in ['channel_a', 'channel_b']
        ):
            engine_restart_needed = True

    # Web server port/host cannot be changed at runtime
    if new_settings['web_server'] != old_settings['web_server']:
        logger.warning("[hot-reload] web_server config changed. Full program restart required to apply.")
        new_settings['web_server'] = old_settings['web_server']

    SETTINGS.clear()
    SETTINGS.update(new_settings)
    SETTINGS_BASIC.clear()
    SETTINGS_BASIC.update(new_settings_basic)

    SERVER_IP = SETTINGS['SERVER_IP'] or get_current_ip()
    reset_logger()
    DGConnection.refresh_limits_from_settings(SETTINGS)

    if engine_restart_needed or ws_restart_needed:
        if ws_restart_needed and not engine_restart_needed:
            # Only WS config changed: restart WS server only, keep OSC/handlers running
            logger.info("[hot-reload] WS config changed, restarting WS server only...")
            _schedule_engine_ws_restart()
        elif ws_restart_needed and engine_restart_needed:
            # Both changed: full restart including WS
            logger.info("[hot-reload] OSC + WS config changed, full engine restart...")
            _schedule_engine_restart(keep_ws=False)
        else:
            # Only OSC/params changed: restart engine but keep WS connections
            logger.info("[hot-reload] OSC/param config changed, restarting engine (preserving WS connections)...")
            _schedule_engine_restart(keep_ws=True)
    else:
        for handler in handlers:
            if hasattr(handler, 'refresh_settings'):
                handler.refresh_settings()

    logger.success("[hot-reload] Configuration reloaded.")


def hot_reload_configs():
    try:
        new_settings, new_settings_basic = load_config_files()
        apply_hot_reloadable_settings(new_settings, new_settings_basic)
        update_config_mtimes()
    except Exception:
        logger.error(traceback.format_exc())
        logger.error("[hot-reload] Failed to reload configuration.")


async def config_hot_reload_loop():
    while True:
        await asyncio.sleep(CONFIG_HOT_RELOAD_INTERVAL)
        if has_config_file_changed():
            hot_reload_configs()

def get_current_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((SETTINGS['general']['local_ip_detect']['host'], SETTINGS['general']['local_ip_detect']['port']))
    client_ip = s.getsockname()[0]
    s.close()
    return client_ip

def get_qr_content():
    return (
        f'https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#ws://'
        f'{SERVER_IP}:{SETTINGS["ws"]["listen_port"]}/{SETTINGS["ws"]["master_uuid"]}'
    )

def get_qr_content_v4():
    """Generate V4 QR code content for DG-LAB 4 APP."""
    import urllib.parse
    ws_port = SETTINGS['web_server']['listen_port']
    ws_url = f'ws://{SERVER_IP}:{ws_port}/ws/dglab-v4?tid={v4_relay.controller_id}'
    return f'https://dungeon-lab.cn/s/?v=1&action=socket&url={urllib.parse.quote(ws_url, safe="")}'

def _serve_spa():
    """Serve Vue SPA index.html with no-cache headers."""
    spa_index = os.path.join(STATIC_DIR, 'index.html')
    if os.path.exists(spa_index):
        return FileResponse(spa_index, media_type='text/html',
                          headers={'Cache-Control': 'no-cache, no-store, must-revalidate', 'Pragma': 'no-cache'})
    return RedirectResponse("/dashboard-legacy")

def _read_template(name, **kwargs):
    """Read a template file and do simple string substitution."""
    path = os.path.join(TEMPLATES_DIR, name)
    if not os.path.exists(path):
        return HTMLResponse("<h1>Template not found</h1>", status_code=404)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    for key, val in kwargs.items():
        content = content.replace('{{ ' + key + ' }}', str(val))
        content = content.replace('{{' + key + '}}', str(val))
    return HTMLResponse(content)


# --- Page routes ---
@app.get("/")
async def web_index():
    return _serve_spa()

@app.get("/get_ip")
async def web_get_ip():
    return get_current_ip()

@app.get("/dashboard-legacy")
async def web_dashboard_legacy():
    return _read_template('dashboard.html')

@app.get("/qr")
async def web_qr():
    return _read_template('tiny-qr.html', content=get_qr_content())


# --- Error handling ---
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": str(exc)})


# --- API Routes ---

@app.get("/api/v1/status")
async def api_v1_status():
    return {
        'healthy': 'ok',
        'engine_running': engine.running,
        'osc_listening': f"{SETTINGS['osc']['listen_host']}:{SETTINGS['osc']['listen_port']}",
        'last_osc_time': _osc_activity[0]['time'] if _osc_activity else None,
        'devices': [
            {
                "type": 'shock',
                'device': 'coyotev3',
                'attr': {
                    'strength': conn.strength,
                    'strength_max': conn.strength_max,
                    'strength_limit': conn.strength_limit,
                    'overlimit_max': conn.overlimit_max,
                    'overlimit_active': conn.overlimit_active,
                    'uuid': conn.uuid,
                }
            } for conn in srv.WS_CONNECTIONS
        ],
    }

@app.get("/api/v1/wave_history")
async def api_v1_wave_history():
    return {'A': _get_wave_history_snapshot('A'), 'B': _get_wave_history_snapshot('B')}

@app.get("/api/v1/wave_history/stream")
async def api_v1_wave_history_stream(channel: str = 'A', since: int = 0):
    """Incremental wave history: return only samples after 'since' seq number."""
    channel = channel.upper()
    history = _wave_history.get(channel, collections.deque())
    new_samples = [s for s in history if s.get('seq', 0) > since]
    latest_seq = _wave_history_seq.get(channel, 0)
    samples = [{'s': s['s'], 'f': s['f']} for s in new_samples]
    return {'samples': samples, 'seq': latest_seq, 'sample_ms': WAVE_HISTORY_SAMPLE_MS}

@app.get("/api/v1/osc_activity")
async def api_v1_osc_activity():
    return {'events': list(_osc_activity)}

@app.get("/api/v1/qr_payload")
async def api_v1_qr_payload():
    return {'content': get_qr_content()}

@app.get("/api/v1/qr_payload_v4")
async def api_v1_qr_payload_v4():
    """Get V4 QR code content for DG-LAB 4 APP."""
    return {
        'content': get_qr_content_v4(),
        'enabled': SETTINGS['ws'].get('v4_enabled', True),
        'controller_id': v4_relay.controller_id,
    }

@app.get("/api/v1/strength/{channel}/{action}/{value}")
async def api_v1_strength(channel: str, action: str, value: int):
    """Adjust device strength. action: set/add/sub. value: 0-200."""
    channel = channel.upper()
    if channel == 'ALL':
        channels = ['A', 'B']
    elif channel in ('A', 'B'):
        channels = [channel]
    else:
        raise HTTPException(400, 'invalid channel')
    mode_map = {'set': '2', 'add': '1', 'sub': '0'}
    mode = mode_map.get(action)
    if mode is None:
        raise HTTPException(400, 'action must be set/add/sub')
    value = max(0, min(200, value))
    for ch in channels:
        for conn in srv.WS_CONNECTIONS:
            await conn.set_strength(ch, mode=mode, value=value, force=True)
    return {'result': 'OK', 'action': action, 'value': value, 'channels': channels}

# --- Strength Boost (temporary +N with auto-revert) ---
_strength_boost = {'A': 0, 'B': 0}
_strength_boost_expire = {'A': 0.0, 'B': 0.0}

@app.get("/api/v1/strength_boost/{channel}/{value}/{duration}")
async def api_v1_strength_boost(channel: str, value: int, duration: float):
    """Temporarily boost strength by value, auto-reverts after duration seconds."""
    channel = channel.upper()
    if channel == 'ALL':
        channels = ['A', 'B']
    elif channel in ('A', 'B'):
        channels = [channel]
    else:
        raise HTTPException(400, 'invalid channel')
    value = max(1, min(100, value))
    duration = max(0.5, min(30.0, duration))
    for ch in channels:
        already_boosted = _strength_boost[ch]
        if already_boosted == 0:
            for conn in srv.WS_CONNECTIONS:
                await conn.set_strength(ch, mode='1', value=value, force=True)
            _strength_boost[ch] = value
        elif already_boosted != value:
            for conn in srv.WS_CONNECTIONS:
                await conn.set_strength(ch, mode='0', value=already_boosted, force=True)
                await conn.set_strength(ch, mode='1', value=value, force=True)
            _strength_boost[ch] = value
        _strength_boost_expire[ch] = time.time() + duration
    return {'result': 'OK', 'boost': value, 'duration': duration, 'channels': channels}

async def _strength_boost_checker(stop_event: asyncio.Event):
    """Background task: revert expired strength boosts."""
    while not stop_event.is_set():
        try:
            await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            return
        now = time.time()
        for ch in ['A', 'B']:
            if _strength_boost[ch] > 0 and now >= _strength_boost_expire[ch]:
                boost_val = _strength_boost[ch]
                _strength_boost[ch] = 0
                for conn in srv.WS_CONNECTIONS:
                    await conn.set_strength(ch, mode='0', value=boost_val, force=True)
                logger.debug(f"[strength] channel={ch} reverted -{boost_val}")

async def _ws_status_pusher(stop_event: asyncio.Event):
    """Periodically push device status to subscribed WS clients."""
    last_device_count = -1
    while not stop_event.is_set():
        try:
            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            return
        # Only push if there are subscribers
        has_subs = any('status' in subs for subs in _ws_subscriptions.values())
        if not has_subs:
            continue
        device_count = len(srv.WS_CONNECTIONS)
        # Push on device count change, or every 10s as heartbeat
        if device_count != last_device_count:
            last_device_count = device_count
            devices = []
            for conn in srv.WS_CONNECTIONS:
                devices.append({
                    'strength': conn.strength,
                    'strength_max': conn.strength_max,
                    'strength_limit': conn.strength_limit,
                })
            await _ws_broadcast('status', {'devices': devices, 'engine_running': True})

# --- Strength Limit ---
@app.get("/api/v1/strength_limit")
async def api_v1_strength_limit_get():
    return {
        'channel_a': SETTINGS_BASIC['dglab3']['channel_a']['strength_limit'],
        'channel_b': SETTINGS_BASIC['dglab3']['channel_b']['strength_limit'],
        'overlimit_a': SETTINGS_BASIC['dglab3']['channel_a'].get('overlimit_max', 20),
        'overlimit_b': SETTINGS_BASIC['dglab3']['channel_b'].get('overlimit_max', 20),
    }

@app.post("/api/v1/strength_limit")
async def api_v1_strength_limit_set(request: Request):
    data = await request.json()
    changed = False
    for ch_key, ch_name in [('channel_a', 'A'), ('channel_b', 'B')]:
        if ch_key in data:
            val = max(0, min(200, int(data[ch_key])))
            SETTINGS_BASIC['dglab3'][ch_key]['strength_limit'] = val
            SETTINGS['dglab3'][ch_key]['strength_limit'] = val
            changed = True
        ol_key = f'overlimit_{ch_key[-1]}'
        if ol_key in data:
            val = max(0, min(200, int(data[ol_key])))
            SETTINGS_BASIC['dglab3'][ch_key]['overlimit_max'] = val
            SETTINGS['dglab3'][ch_key]['overlimit_max'] = val
            changed = True
    if changed:
        config_save()
        DGConnection.refresh_limits_from_settings(SETTINGS)
        logger.info(f"[strength] Updated: A={SETTINGS_BASIC['dglab3']['channel_a']['strength_limit']}(+{SETTINGS_BASIC['dglab3']['channel_a'].get('overlimit_max',20)}), B={SETTINGS_BASIC['dglab3']['channel_b']['strength_limit']}(+{SETTINGS_BASIC['dglab3']['channel_b'].get('overlimit_max',20)})")
    return {
        'success': True,
        'channel_a': SETTINGS_BASIC['dglab3']['channel_a']['strength_limit'],
        'channel_b': SETTINGS_BASIC['dglab3']['channel_b']['strength_limit'],
        'overlimit_a': SETTINGS_BASIC['dglab3']['channel_a'].get('overlimit_max', 20),
        'overlimit_b': SETTINGS_BASIC['dglab3']['channel_b'].get('overlimit_max', 20),
    }

# --- Overlimit Rules Engine ---
OVERLIMIT_RULES_FILE = 'overlimit_rules.yaml'
_overlimit_rules = []
_osc_param_state = {}
_overlimit_effective = {'A': 0, 'B': 0}

def _load_overlimit_rules():
    global _overlimit_rules
    if os.path.exists(OVERLIMIT_RULES_FILE):
        with open(OVERLIMIT_RULES_FILE, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        _overlimit_rules = data.get('rules', [])
    else:
        _overlimit_rules = []

def _save_overlimit_rules():
    tmp = OVERLIMIT_RULES_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        yaml.safe_dump({'rules': _overlimit_rules}, f, allow_unicode=True)
    os.replace(tmp, OVERLIMIT_RULES_FILE)

def _eval_condition(condition: dict, param_state: dict) -> bool:
    param = condition.get('param', '')
    operator = condition.get('operator', '==')
    threshold = condition.get('value', 0)
    current = param_state.get(param)
    if current is None:
        return False
    try:
        current = float(current)
        threshold = float(threshold)
    except (TypeError, ValueError):
        return False
    ops = {'==': lambda a,b: abs(a-b)<0.001, '!=': lambda a,b: abs(a-b)>=0.001,
           '>': lambda a,b: a>b, '<': lambda a,b: a<b, '>=': lambda a,b: a>=b, '<=': lambda a,b: a<=b}
    return ops.get(operator, lambda a,b: False)(current, threshold)

def _evaluate_overlimit_rules():
    global _overlimit_effective
    max_limit = {'A': 0, 'B': 0}
    for rule in _overlimit_rules:
        if not rule.get('enabled', True):
            continue
        if _eval_condition(rule.get('condition', {}), _osc_param_state):
            limit_val = int(rule.get('limit_value', 0))
            channel = rule.get('channel', 'both')
            if channel in ('a', 'both'):
                max_limit['A'] = max(max_limit['A'], limit_val)
            if channel in ('b', 'both'):
                max_limit['B'] = max(max_limit['B'], limit_val)
    changed = False
    for ch in ['A', 'B']:
        if max_limit[ch] != _overlimit_effective[ch]:
            _overlimit_effective[ch] = max_limit[ch]
            changed = True
    if changed:
        for conn in srv.WS_CONNECTIONS:
            conn.overlimit_active['A'] = max_limit['A'] > 0
            conn.overlimit_active['B'] = max_limit['B'] > 0
            conn.overlimit_max['A'] = max_limit['A'] if max_limit['A'] > 0 else SETTINGS['dglab3']['channel_a'].get('overlimit_max', 20)
            conn.overlimit_max['B'] = max_limit['B'] if max_limit['B'] > 0 else SETTINGS['dglab3']['channel_b'].get('overlimit_max', 20)

def _overlimit_osc_hook(address, *args):
    if args:
        _osc_param_state[address] = args[0]
    if _overlimit_rules:
        _evaluate_overlimit_rules()

@app.get("/api/v1/overlimit_rules")
async def api_v1_overlimit_rules_get():
    return {'rules': _overlimit_rules, 'effective': _overlimit_effective}

@app.post("/api/v1/overlimit_rules")
async def api_v1_overlimit_rules_set(request: Request):
    global _overlimit_rules
    data = await request.json()
    _overlimit_rules = data.get('rules', [])
    _save_overlimit_rules()
    _evaluate_overlimit_rules()
    logger.info(f"[config] Overlimit rules saved: {len(_overlimit_rules)} rules")
    return {'success': True, 'rules': _overlimit_rules}

@app.delete("/api/v1/overlimit_rules/{index}")
async def api_v1_overlimit_rules_delete(index: int):
    if 0 <= index < len(_overlimit_rules):
        removed = _overlimit_rules.pop(index)
        _save_overlimit_rules()
        _evaluate_overlimit_rules()
        logger.info(f"[config] Overlimit rule deleted: {removed.get('name', index)}")
        return {'success': True, 'rules': _overlimit_rules}
    raise HTTPException(400, 'invalid index')


# --- Shock / Sendwave ---
@app.get("/api/v1/shock/{channel}/{second}")
async def api_v1_shock(channel: str, second: str):
    if channel == 'all':
        channels = ['A', 'B']
    else:
        channels = [channel.upper()]
    try:
        second = float(second)
    except Exception:
        second = 1.0
    second = min(second, 10.0)
    repeat = int(10 * second)
    for _ in range(repeat // 10):
        for chan in channels:
            wavestr = json.dumps(['0A0A0A0A64646464'] * 10, separators=(',', ':'))
            await command_queue.put(CommandPriority.API, chan, 'wave', value=wavestr, source_id='api_shock')
    if repeat % 10 > 0:
        for chan in channels:
            wavestr = json.dumps(['0A0A0A0A64646464'] * (repeat % 10), separators=(',', ':'))
            await command_queue.put(CommandPriority.API, chan, 'wave', value=wavestr, source_id='api_shock')
    return {'result': 'OK'}

@app.get("/api/v1/sendwave/{channel}/{repeat}/{wavedata}")
async def api_v1_sendwave(channel: str, repeat: str, wavedata: str):
    """Send raw wave data. channel: A/B, repeat: 1-100, wavedata: 16 hex chars."""
    try:
        channel = channel.upper()
        if channel not in ['A', 'B']:
            raise Exception
    except:
        channel = 'A'
    try:
        repeat_int = int(repeat)
        if repeat_int > 100 or repeat_int < 1:
            raise Exception
    except:
        repeat_int = 10
    try:
        if not re.match(r'^([0-9A-F]{16})$', wavedata):
            raise Exception
    except:
        wavedata = '0A0A0A0A64646464'
    wavestr = json.dumps([wavedata] * repeat_int, separators=(',', ':'))
    logger.debug(f'[API][sendwave] C:{channel} R:{repeat_int} W:{wavedata}')
    await command_queue.put(CommandPriority.API, channel, 'wave', value=wavestr, source_id='api_sendwave')
    return {'result': 'OK'}

# --- Wave Test ---
_wave_test_state = {
    'active': False,
    'channel': 'A',
    'strength': 50,
    'wave_scale': 1.0,
    'preset': None,
}

@app.post("/api/v1/wave_test/start")
async def api_v1_wave_test_start(request: Request):
    data = await request.json()
    channel = data.get('channel', 'A').upper()
    if channel not in ('A', 'B', 'AB'):
        raise HTTPException(400, 'channel must be A, B, or AB')
    strength = max(0, min(200, int(data.get('strength', 50))))
    wave_scale = max(0.0, min(1.0, float(data.get('wave_scale', 1.0))))
    preset_name = data.get('preset', None)
    _wave_test_state['active'] = True
    _wave_test_state['channel'] = channel
    _wave_test_state['strength'] = strength
    _wave_test_state['wave_scale'] = wave_scale
    _wave_test_state['preset'] = preset_name
    logger.info(f"[wave-test] Started: ch={channel} str={strength} scale={wave_scale} preset={preset_name or 'default'}")
    return {'result': 'OK', 'active': True}

@app.post("/api/v1/wave_test/stop")
async def api_v1_wave_test_stop():
    _wave_test_state['active'] = False
    channel = _wave_test_state['channel']
    channels = ['A', 'B'] if channel == 'AB' else [channel]
    for ch in channels:
        for conn in srv.WS_CONNECTIONS:
            await conn.clear_wave(ch)
    logger.info("[wave-test] Stopped")
    return {'result': 'OK', 'active': False}

@app.post("/api/v1/wave_test/update")
async def api_v1_wave_test_update(request: Request):
    if not _wave_test_state['active']:
        raise HTTPException(400, 'test not running')
    data = await request.json()
    if 'strength' in data:
        _wave_test_state['strength'] = max(0, min(200, int(data['strength'])))
    if 'wave_scale' in data:
        _wave_test_state['wave_scale'] = max(0.0, min(1.0, float(data['wave_scale'])))
    if 'preset' in data:
        _wave_test_state['preset'] = data['preset'] or None
    return {'result': 'OK', 'state': {
        'active': True,
        'strength': _wave_test_state['strength'],
        'wave_scale': _wave_test_state['wave_scale'],
        'preset': _wave_test_state['preset'],
    }}

@app.get("/api/v1/wave_test/status")
async def api_v1_wave_test_status():
    return {
        'active': _wave_test_state['active'],
        'channel': _wave_test_state['channel'],
        'strength': _wave_test_state['strength'],
        'wave_scale': _wave_test_state['wave_scale'],
        'preset': _wave_test_state['preset'],
    }

async def _wave_test_loop(stop_event: asyncio.Event):
    """Background loop that sends waves continuously while test is active."""
    from srv.wave_preset import WavePresetLibrary
    wave_position = 0.0
    lib = WavePresetLibrary()
    saved_limits = None
    while not stop_event.is_set():
        try:
            if _wave_test_state['active']:
                channel = _wave_test_state['channel']
                channels = ['A', 'B'] if channel == 'AB' else [channel]
                strength = _wave_test_state['strength']
                wave_scale = _wave_test_state['wave_scale']
                preset_name = _wave_test_state['preset']
                if saved_limits is None:
                    saved_limits = {
                        'A': SETTINGS['dglab3']['channel_a']['strength_limit'],
                        'B': SETTINGS['dglab3']['channel_b']['strength_limit'],
                    }
                    DGConnection._suppress_clear = True
                    command_queue.set_enabled(CommandPriority.OSC_INTERACTION, False)
                    command_queue.set_enabled(CommandPriority.OSC_PANEL, False)
                    command_queue.set_enabled(CommandPriority.GAME, False)
                for ch in channels:
                    ch_key = f'channel_{ch.lower()}'
                    SETTINGS['dglab3'][ch_key]['strength_limit'] = strength
                DGConnection.refresh_limits_from_settings(SETTINGS)
                for ch in channels:
                    for conn in srv.WS_CONNECTIONS:
                        await conn.set_strength(ch, mode='2', value=strength, force=True)
                wavestr = None
                if preset_name and lib.get(preset_name):
                    wavestr = lib.build_resampled_window(
                        preset_name, start_position=wave_position,
                        window_ops=10, wave_scale=wave_scale,
                        texture_floor=0.0, sample_step=1.0,
                    )
                    wave_position += 40.0
                if not wavestr:
                    wavestr = ShockHandler.scale_wavestr(DEFAULT_SHOCK_WAVE, wave_scale)
                for ch in channels:
                    await command_queue.put(CommandPriority.API, ch, 'wave', value=wavestr, source_id='wave_test_loop')
                await asyncio.sleep(0.9)
            else:
                if saved_limits is not None:
                    SETTINGS['dglab3']['channel_a']['strength_limit'] = saved_limits['A']
                    SETTINGS['dglab3']['channel_b']['strength_limit'] = saved_limits['B']
                    DGConnection.refresh_limits_from_settings(SETTINGS)
                    DGConnection._suppress_clear = False
                    command_queue.set_enabled(CommandPriority.OSC_INTERACTION, True)
                    command_queue.set_enabled(CommandPriority.OSC_PANEL, True)
                    command_queue.set_enabled(CommandPriority.GAME, True)
                    saved_limits = None
                wave_position = 0.0
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"[wave-test] error: {e}")
            await asyncio.sleep(0.5)

# --- Settings ---
def strip_basic_settings(settings: dict):
    ret = copy.deepcopy(settings)
    for chann in ['channel_a', 'channel_b']:
        del ret['dglab3'][chann]['avatar_params']
        del ret['dglab3'][chann]['mode']
        del ret['dglab3'][chann]['strength_limit']
    return ret

@app.get("/setup")
async def web_setup_wizard():
    return _read_template('setup_wizard.html')

@app.post("/api/v1/setup")
async def api_v1_setup(request: Request):
    global SETTINGS, SETTINGS_BASIC, SERVER_IP
    try:
        data = await request.json()
        for ch in ['channel_a', 'channel_b']:
            ch_data = data.get(ch, {})
            SETTINGS_BASIC['dglab3'][ch]['mode'] = ch_data.get('mode', 'distance')
            SETTINGS_BASIC['dglab3'][ch]['strength_limit'] = int(ch_data.get('strength_limit', 100))
            SETTINGS_BASIC['dglab3'][ch]['avatar_params'] = [
                {'path': p, 'mode': ch_data.get('mode', 'distance')} for p in ch_data.get('avatar_params', [])
            ]
        if 'osc' in data:
            SETTINGS['osc']['listen_port'] = int(data['osc'].get('listen_port', 9001))
            SETTINGS['osc']['listen_host'] = data['osc'].get('listen_host', '127.0.0.1')
        SETTINGS['ws']['master_uuid'] = str(uuid.uuid4())
        config_save()
        app.state.setup_complete = True
        return {'success': True, 'message': 'Configuration saved.'}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/v1/config")
async def get_config():
    return {
        'basic': SETTINGS_BASIC,
        'advanced': strip_basic_settings(SETTINGS),
    }

@app.post("/api/v1/settings")
async def api_v1_settings_update(request: Request):
    data = await request.json()
    restart_needed = []
    if 'osc' in data:
        osc = data['osc']
        if 'listen_port' in osc:
            SETTINGS['osc']['listen_port'] = int(osc['listen_port'])
            restart_needed.append('osc')
        if 'listen_host' in osc:
            SETTINGS['osc']['listen_host'] = osc['listen_host']
            restart_needed.append('osc')
    if 'ws' in data:
        ws = data['ws']
        if 'listen_port' in ws:
            SETTINGS['ws']['listen_port'] = int(ws['listen_port'])
            restart_needed.append('ws')
        if 'v4_enabled' in ws:
            SETTINGS['ws']['v4_enabled'] = bool(ws['v4_enabled'])
    if 'web_server' in data:
        web = data['web_server']
        if 'listen_port' in web:
            SETTINGS['web_server']['listen_port'] = int(web['listen_port'])
            restart_needed.append('web_server')
        if 'listen_host' in web:
            SETTINGS['web_server']['listen_host'] = web['listen_host']
            restart_needed.append('web_server')
    if 'log_level' in data:
        SETTINGS['log_level'] = data['log_level']
        reset_logger()
    if 'github_mirror' in data:
        SETTINGS.setdefault('general', {})['github_mirror'] = data['github_mirror'].strip()
        # Clear update cache so next check uses new mirror
        global _update_cache, _update_cache_time
        _update_cache = {}
        _update_cache_time = 0
    config_save()
    if restart_needed:
        web_restart = 'web_server' in restart_needed
        ws_restart = 'ws' in restart_needed
        engine_needs_restart = any(r in restart_needed for r in ('osc', 'ws'))
        async def _delayed_restart():
            await asyncio.sleep(0.5)
            if engine_needs_restart:
                if ws_restart:
                    logger.info("[config] Restarting engine (WS config changed)...")
                    await engine.restart(keep_ws=False)
                else:
                    logger.info("[config] Restarting engine (preserving WS connections)...")
                    await engine.restart(keep_ws=True)
            if web_restart:
                logger.warning("[config] Web server port/host changed. Full restart required.")
                _restart_program()
        asyncio.create_task(_delayed_restart())
    return {
        'success': True,
        'restart_needed': list(set(restart_needed)),
        'message': '已保存。' + ('引擎正在重启...' if restart_needed else ''),
    }

@app.get("/api/v1/config/export")
async def api_v1_config_export():
    """Export full configuration as a downloadable JSON file."""
    from fastapi.responses import Response
    export_data = {
        'version': CONFIG_FILE_VERSION,
        'exported_at': datetime.datetime.now().isoformat(),
        'basic': copy.deepcopy(SETTINGS_BASIC),
        'advanced': strip_basic_settings(SETTINGS),
    }
    content = json.dumps(export_data, ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type='application/json',
        headers={'Content-Disposition': 'attachment; filename="shocking-vrchat-config.json"'},
    )

@app.post("/api/v1/config/import")
async def api_v1_config_import(file: UploadFile = File(...)):
    """Import configuration from a previously exported JSON file."""
    if not file.filename or not file.filename.endswith('.json'):
        raise HTTPException(400, 'Please upload a .json file')

    content_bytes = await file.read()
    try:
        import_data = json.loads(content_bytes.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(400, f'Invalid JSON: {e}')

    if 'basic' not in import_data or 'advanced' not in import_data:
        raise HTTPException(400, 'Invalid config file: missing "basic" or "advanced" section')

    imported_version = import_data.get('version', '')
    if imported_version != CONFIG_FILE_VERSION:
        raise HTTPException(400, f'Config version mismatch: file is {imported_version}, expected {CONFIG_FILE_VERSION}')

    # Merge imported config into current settings
    new_basic = import_data['basic']
    new_advanced = import_data['advanced']

    # Reconstruct full advanced settings (re-add basic fields to dglab3)
    for ch in ['channel_a', 'channel_b']:
        if ch in new_basic.get('dglab3', {}):
            new_advanced.setdefault('dglab3', {}).setdefault(ch, {})
            new_advanced['dglab3'][ch]['avatar_params'] = new_basic['dglab3'][ch].get('avatar_params', [])
            new_advanced['dglab3'][ch]['mode'] = new_basic['dglab3'][ch].get('mode', 'distance')
            new_advanced['dglab3'][ch]['strength_limit'] = new_basic['dglab3'][ch].get('strength_limit', 100)

    # Preserve non-exportable fields
    new_advanced.setdefault('ws', {})['master_uuid'] = SETTINGS['ws'].get('master_uuid')
    new_advanced['version'] = CONFIG_FILE_VERSION
    new_basic['version'] = CONFIG_FILE_VERSION

    # Normalize avatar params
    for ch in ['channel_a', 'channel_b']:
        if ch in new_advanced.get('dglab3', {}):
            normalize_avatar_param_entries(new_advanced['dglab3'][ch])

    # Apply
    SETTINGS_BASIC.clear()
    SETTINGS_BASIC.update(new_basic)
    SETTINGS.clear()
    SETTINGS.update(new_advanced)

    global SERVER_IP
    SERVER_IP = SETTINGS.get('SERVER_IP') or get_current_ip()
    reset_logger()
    DGConnection.refresh_limits_from_settings(SETTINGS)
    config_save()

    # Restart engine to apply all changes (keep WS since port likely didn't change)
    async def _delayed():
        await asyncio.sleep(0.3)
        await engine.restart(keep_ws=True)
    asyncio.create_task(_delayed())

    return {'success': True, 'message': '配置已导入，引擎正在重启...'}

@app.post("/api/v1/engine/restart")
async def api_v1_engine_restart():
    async def _do_restart():
        await asyncio.sleep(0.3)
        await engine.restart(keep_ws=True)
    asyncio.create_task(_do_restart())
    return {'success': True, 'message': '引擎正在重启（保持设备连接）...'}

@app.get("/api/v1/engine/status")
async def api_v1_engine_status():
    return {'running': engine.running}


async def _graceful_shutdown():
    """Gracefully shutdown: stop engine, tray, uvicorn, flush logs, then exit."""
    global _tray_icon_ref, _uvicorn_server
    logger.info("[shutdown] Graceful shutdown initiated...")

    # 1. Stop the engine (OSC, WS server, handlers)
    try:
        await engine.stop(keep_ws=False)
    except Exception as e:
        logger.warning(f"[shutdown] Engine stop error: {e}")

    # 2. Stop tray icon (releases Win32 message loop / thread)
    if _tray_icon_ref is not None:
        try:
            _tray_icon_ref.stop()
        except Exception:
            pass
        _tray_icon_ref = None

    # 3. Signal uvicorn to exit
    if _uvicorn_server is not None:
        _uvicorn_server.should_exit = True

    # 4. Flush loguru sinks
    try:
        logger.complete()
    except Exception:
        pass

    # 5. Give a moment for cleanup, then exit
    await asyncio.sleep(0.3)
    sys.exit(0)


@app.post("/api/v1/shutdown")
async def api_v1_shutdown():
    """Shutdown the entire program."""
    logger.info("[shutdown] Shutdown requested via API.")
    async def _do_shutdown():
        await asyncio.sleep(0.5)
        await _graceful_shutdown()
    asyncio.create_task(_do_shutdown())
    return {'success': True, 'message': 'Shutting down...'}

@app.get("/api/v1/logs")
async def api_v1_logs():
    """Get recent log entries."""
    return {'logs': _log_buffer[-200:]}

# --- Auto Update ---
_update_cache: dict = {}
_update_cache_time = 0.0
_update_lock = asyncio.Lock()

def _get_github_mirror() -> str:
    """Get configured GitHub mirror prefix (empty string = direct)."""
    return (SETTINGS.get('general', {}).get('github_mirror') or '').strip().rstrip('/')

def _apply_mirror(url: str) -> str:
    """Apply GitHub mirror proxy to a download URL if configured.
    
    Only proxies github.com download links (releases, raw files).
    Does NOT proxy api.github.com — most mirrors don't support API proxying.
    """
    mirror = _get_github_mirror()
    if not mirror:
        return url
    # Don't proxy API requests — mirrors typically only handle download URLs
    if 'api.github.com' in url:
        return url
    # Proxy format: mirror_prefix/original_url
    return f'{mirror}/{url}'


def _blocking_update_check():
    """Blocking HTTP call to GitHub API. Run via asyncio.to_thread()."""
    import urllib.request
    api_url = f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest'
    url = _apply_mirror(api_url)
    req = urllib.request.Request(url, headers={'Accept': 'application/vnd.github.v3+json', 'User-Agent': 'ShockingVRChat'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _blocking_download(url: str, dest_path: str, expected_size: int = 0):
    """Blocking file download with progress logging. Run via asyncio.to_thread()."""
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': 'ShockingVRChat'})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get('Content-Length', 0)) or expected_size
        downloaded = 0
        last_log_pct = -10
        with open(dest_path, 'wb') as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = int(downloaded * 100 / total)
                    if pct - last_log_pct >= 10:
                        logger.info(f"[update] Download progress: {pct}% ({downloaded}/{total})")
                        last_log_pct = pct
    return downloaded


def _verify_zip_integrity(zip_path: str, expected_size: int, expected_sha256: str | None):
    """Verify downloaded file size and SHA256 hash. Returns error message or None."""
    import hashlib

    actual_size = os.path.getsize(zip_path)
    if expected_size > 0 and actual_size != expected_size:
        return f"Size mismatch: expected {expected_size}, got {actual_size}"

    if expected_sha256:
        sha256 = hashlib.sha256()
        with open(zip_path, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                sha256.update(chunk)
        actual_hash = sha256.hexdigest()
        if actual_hash.lower() != expected_sha256.lower():
            return f"SHA256 mismatch: expected {expected_sha256[:16]}..., got {actual_hash[:16]}..."

    return None


def _check_zip_slip(zf, extract_dir: str) -> str | None:
    """Check for zip slip (path traversal) attacks. Returns malicious path or None."""
    abs_extract = os.path.realpath(extract_dir)
    for info in zf.infolist():
        member_path = os.path.join(extract_dir, info.filename)
        abs_member = os.path.realpath(member_path)
        if not abs_member.startswith(abs_extract + os.sep) and abs_member != abs_extract:
            return info.filename
    return None


def _try_fetch_sha256(assets: list, zip_name: str) -> str | None:
    """Try to download sha256sums.txt from release assets and find hash for our file."""
    import urllib.request
    sha_url = None
    for asset in assets:
        name = asset.get('name', '').lower()
        if 'sha256' in name and name.endswith('.txt'):
            sha_url = asset.get('browser_download_url')
            break
    if not sha_url:
        return None
    try:
        actual_url = _apply_mirror(sha_url)
        req = urllib.request.Request(actual_url, headers={'User-Agent': 'ShockingVRChat'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8', errors='replace')
        for line in content.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                # Format: hash  filename (or hash *filename)
                hash_val = parts[0]
                fname = parts[-1].lstrip('*')
                if fname == zip_name or fname.endswith('/' + zip_name):
                    return hash_val
    except Exception as e:
        logger.warning(f"[update] Could not fetch sha256sums.txt: {e}")
    return None


@app.get("/api/v1/update/check")
async def api_v1_update_check():
    """Check GitHub releases for a newer version."""
    global _update_cache, _update_cache_time

    # Cache for 5 minutes
    if _update_cache and (time.time() - _update_cache_time) < 300:
        return _update_cache

    try:
        data = await asyncio.to_thread(_blocking_update_check)
    except Exception as e:
        return {'current': APP_VERSION, 'latest': None, 'update_available': False, 'error': str(e)}

    latest_tag = data.get('tag_name', '')
    latest_ver = latest_tag.lstrip('v')
    update_available = _version_newer(latest_ver, APP_VERSION)

    # Find download URL for the onedir zip
    download_url = None
    download_size = 0
    download_name = ''
    assets = data.get('assets', [])
    for asset in assets:
        name = asset.get('name', '')
        if 'windows_x64.zip' in name and 'onefile' not in name:
            download_url = asset.get('browser_download_url')
            download_size = asset.get('size', 0)
            download_name = name
            break
    if not download_url:
        for asset in assets:
            if asset.get('name', '').endswith('.zip'):
                download_url = asset.get('browser_download_url')
                download_size = asset.get('size', 0)
                download_name = asset.get('name', '')
                break

    _update_cache = {
        'current': APP_VERSION,
        'latest': latest_ver,
        'latest_tag': latest_tag,
        'update_available': update_available,
        'download_url': download_url,
        'download_size': download_size,
        'download_name': download_name,
        'assets': assets,
        'release_name': data.get('name', ''),
        'release_notes': data.get('body', '')[:2000],
        'published_at': data.get('published_at', ''),
        'github_mirror': _get_github_mirror(),
    }
    _update_cache_time = time.time()
    return _update_cache

@app.post("/api/v1/update/apply")
async def api_v1_update_apply():
    """Download and apply the latest update. Replaces files and restarts."""
    import zipfile
    import shutil
    import tempfile

    # Concurrency guard: only one update at a time
    if _update_lock.locked():
        raise HTTPException(409, '更新正在进行中，请勿重复操作')

    async with _update_lock:
        # Only works for frozen (packaged) builds
        if not getattr(sys, 'frozen', False):
            raise HTTPException(400, '仅打包版本支持自动更新，开发环境请使用 git pull')

        check = await api_v1_update_check()
        if not check.get('update_available'):
            return {'success': False, 'message': '当前已是最新版本'}
        download_url = check.get('download_url')
        if not download_url:
            raise HTTPException(400, '未找到可下载的更新文件')

        expected_size = check.get('download_size', 0)
        download_name = check.get('download_name', '')
        assets = check.get('assets', [])

        exe_dir = get_exe_dir()
        tmp_dir = tempfile.mkdtemp(prefix='svrc_update_')
        zip_path = os.path.join(tmp_dir, 'update.zip')

        try:
            # --- Download (non-blocking) ---
            actual_url = _apply_mirror(download_url)
            logger.info(f"[update] Downloading: {actual_url}")
            downloaded_size = await asyncio.to_thread(
                _blocking_download, actual_url, zip_path, expected_size
            )
            logger.info(f"[update] Downloaded {downloaded_size} bytes to {zip_path}")

            # --- Integrity check ---
            # Try to get SHA256 from release assets
            expected_sha256 = await asyncio.to_thread(
                _try_fetch_sha256, assets, download_name
            )
            if expected_sha256:
                logger.info(f"[update] SHA256 from release: {expected_sha256[:16]}...")

            integrity_error = _verify_zip_integrity(zip_path, expected_size, expected_sha256)
            if integrity_error:
                logger.error(f"[update] Integrity check failed: {integrity_error}")
                raise HTTPException(500, f'文件完整性校验失败: {integrity_error}')

            logger.info("[update] Integrity check passed")

            # --- Zip Slip protection ---
            extract_dir = os.path.join(tmp_dir, 'extracted')
            with zipfile.ZipFile(zip_path, 'r') as zf:
                malicious_path = _check_zip_slip(zf, extract_dir)
                if malicious_path:
                    logger.error(f"[update] Zip slip detected! Malicious path: {malicious_path}")
                    raise HTTPException(500, f'压缩包包含恶意路径，更新已中止: {malicious_path}')
                zf.extractall(extract_dir)

            # Find the actual content dir (might be nested)
            # CI (GitHub Actions) packages as: shocking_vrchat_windows_x64.zip containing
            # a single top-level directory "shocking_vrchat/" with all files inside.
            # If the zip is flat (no wrapper dir), contents will have multiple entries
            # and we use extract_dir directly. Both cases are handled correctly.
            contents = os.listdir(extract_dir)
            if len(contents) == 1 and os.path.isdir(os.path.join(extract_dir, contents[0])):
                source_dir = os.path.join(extract_dir, contents[0])
            else:
                source_dir = extract_dir

            # Write update script that replaces files after this process exits
            bat_path = os.path.join(tmp_dir, 'apply_update.bat')
            pid = os.getpid()
            exe_path = os.path.join(exe_dir, "shocking_vrchat.exe")
            # Directories to exclude from backup (user data, not program files)
            exclude_dirs = ['_backup', 'wave_presets', 'dg-lab', 'profiles', 'recordings']
            exclude_files = [CONFIG_FILENAME, CONFIG_FILENAME_BASIC, 'curve_config.yaml',
                            'overlimit_rules.yaml', 'shocking_vrchat.log', 'error.log']
            with open(bat_path, 'w', encoding='utf-8') as f:
                f.write('@echo off\n')
                f.write('chcp 65001 >nul 2>&1\n')
                f.write('echo Waiting for process to exit...\n')
                # Wait for the process to exit (poll by PID, max 10s)
                f.write(f'set WAIT_COUNT=0\n')
                f.write(f':WAIT_LOOP\n')
                f.write(f'tasklist /FI "PID eq {pid}" 2>nul | find /I "{pid}" >nul\n')
                f.write(f'if errorlevel 1 goto COPY_FILES\n')
                f.write(f'set /a WAIT_COUNT+=1\n')
                f.write(f'if %WAIT_COUNT% GEQ 20 (\n')
                f.write(f'    echo Process did not exit in 10s, force killing...\n')
                f.write(f'    taskkill /F /PID {pid} >nul 2>&1\n')
                f.write(f'    timeout /t 1 /nobreak >nul\n')
                f.write(f'    goto COPY_FILES\n')
                f.write(f')\n')
                f.write(f'timeout /t 1 /nobreak >nul\n')
                f.write(f'goto WAIT_LOOP\n')
                # Backup and copy
                f.write(f':COPY_FILES\n')
                f.write(f'echo Backing up current version...\n')
                f.write(f'if exist "{exe_dir}\\_backup" rmdir /s /q "{exe_dir}\\_backup"\n')
                f.write(f'mkdir "{exe_dir}\\_backup"\n')
                # Use robocopy for comprehensive backup with exclusions
                exclude_dir_args = ' '.join(f'"{d}"' for d in exclude_dirs)
                exclude_file_args = ' '.join(f'"{ef}"' for ef in exclude_files)
                f.write(f'robocopy "{exe_dir}" "{exe_dir}\\_backup" /s /xd {exclude_dir_args} /xf {exclude_file_args} >nul 2>&1\n')
                f.write(f'echo Applying update...\n')
                f.write(f'xcopy /s /y /q "{source_dir}\\*" "{exe_dir}\\"\n')
                f.write(f'if errorlevel 1 (\n')
                f.write(f'    echo.\n')
                f.write(f'    echo [ERROR] File copy failed. Attempting rollback from backup...\n')
                f.write(f'    xcopy /s /y /q "{exe_dir}\\_backup\\*" "{exe_dir}\\"\n')
                f.write(f'    if errorlevel 1 (\n')
                f.write(f'        echo.\n')
                f.write(f'        echo [ERROR] Rollback also failed!\n')
                f.write(f'        echo Please manually restore from: {exe_dir}\\_backup\n')
                f.write(f'        echo Or manually copy update files from: {source_dir}\n')
                f.write(f'        echo.\n')
                f.write(f'        pause\n')
                f.write(f'        exit /b 1\n')
                f.write(f'    )\n')
                f.write(f'    echo Rollback successful. Update cancelled.\n')
                f.write(f'    echo Starting previous version...\n')
                f.write(f'    start "" "{exe_path}"\n')
                f.write(f'    rmdir /s /q "{tmp_dir}"\n')
                f.write(f'    exit\n')
                f.write(f')\n')
                f.write(f'echo Update complete. Starting...\n')
                f.write(f'start "" "{exe_path}"\n')
                f.write(f'rmdir /s /q "{tmp_dir}"\n')
                f.write('exit\n')

            # Launch the update script and exit
            logger.info("[update] Launching update script and exiting...")
            import subprocess
            subprocess.Popen(
                ['cmd', '/c', bat_path],
                creationflags=0x00000008,  # DETACHED_PROCESS
                close_fds=True,
            )

            # Schedule graceful shutdown
            async def _shutdown():
                await asyncio.sleep(0.5)
                await _graceful_shutdown()
            asyncio.create_task(_shutdown())

            return {'success': True, 'message': '更新下载完成，正在应用更新并重启...'}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[update] Failed: {e}")
            # Cleanup
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except:
                pass
            raise HTTPException(500, f'更新失败: {e}')

def _version_newer(latest: str, current: str) -> bool:
    """Check if latest version is newer than current (semver comparison)."""
    try:
        def parse(v): return tuple(int(x) for x in v.split('.')[:3])
        return parse(latest) > parse(current)
    except (ValueError, IndexError):
        return False

def _restart_program():
    """Restart the current process. Works on both Windows and Linux."""
    import subprocess
    if getattr(sys, 'frozen', False):
        cmd = [sys.executable] + sys.argv[1:]
    else:
        cmd = [sys.executable] + sys.argv
    if sys.platform == 'win32':
        subprocess.Popen(cmd, close_fds=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        # Minimal cleanup before hard exit (new process already running, must release port)
        _sync_cleanup_before_exit()
        os._exit(0)
    else:
        _sync_cleanup_before_exit()
        os.execv(cmd[0], cmd)


def _sync_cleanup_before_exit():
    """Synchronous minimal cleanup: stop tray icon and flush logs.
    
    Used before os._exit / os.execv where async shutdown is not possible.
    Does NOT stop the event loop or uvicorn (would deadlock in sync context).
    """
    global _tray_icon_ref
    if _tray_icon_ref is not None:
        try:
            _tray_icon_ref.stop()
        except Exception:
            pass
        _tray_icon_ref = None
    try:
        logger.complete()
    except Exception:
        pass


# --- Params ---
@app.get("/api/v1/params/{channel}")
async def api_v1_params_get(channel: str):
    ch = channel.lower()
    if ch not in ('a', 'b'):
        raise HTTPException(400, 'invalid channel')
    ch_key = f'channel_{ch}'
    params = SETTINGS_BASIC['dglab3'][ch_key].get('avatar_params', [])
    default_mode = SETTINGS_BASIC['dglab3'][ch_key].get('mode', 'distance')
    strength_limit = SETTINGS_BASIC['dglab3'][ch_key].get('strength_limit', 100)
    return {'params': params, 'default_mode': default_mode, 'strength_limit': strength_limit}

@app.post("/api/v1/params/{channel}")
async def api_v1_params_set(channel: str, request: Request):
    ch = channel.lower()
    if ch not in ('a', 'b'):
        raise HTTPException(400, 'invalid channel')
    data = await request.json()
    ch_key = f'channel_{ch}'
    new_params = data.get('params', [])
    validated = []
    for p in new_params:
        if isinstance(p, str):
            validated.append({'path': p, 'mode': data.get('default_mode', 'distance'), 'enabled': True})
        elif isinstance(p, dict) and p.get('path'):
            validated.append({
                'path': p['path'],
                'mode': p.get('mode', 'distance'),
                'enabled': p.get('enabled', True),
            })
    SETTINGS_BASIC['dglab3'][ch_key]['avatar_params'] = validated
    if 'default_mode' in data:
        SETTINGS_BASIC['dglab3'][ch_key]['mode'] = data['default_mode']
    if 'strength_limit' in data:
        SETTINGS_BASIC['dglab3'][ch_key]['strength_limit'] = int(data['strength_limit'])
    SETTINGS['dglab3'][ch_key]['avatar_params'] = validated
    SETTINGS['dglab3'][ch_key]['mode'] = SETTINGS_BASIC['dglab3'][ch_key]['mode']
    SETTINGS['dglab3'][ch_key]['strength_limit'] = SETTINGS_BASIC['dglab3'][ch_key]['strength_limit']
    normalize_avatar_param_entries(SETTINGS['dglab3'][ch_key])
    config_save()
    async def _delayed_restart():
        await asyncio.sleep(0.5)
        logger.info("[params] Restarting engine to apply param changes (preserving WS)...")
        await engine.restart(keep_ws=True)
    asyncio.create_task(_delayed_restart())
    return {'success': True, 'params': validated, 'restarting': True}

# --- Mode Config ---
@app.get("/api/v1/mode_config/{channel}/{mode}")
async def api_v1_mode_config_get(channel: str, mode: str):
    ch = channel.lower()
    if ch not in ('a', 'b'):
        raise HTTPException(400, 'invalid channel')
    if mode not in ('shock', 'distance', 'touch'):
        raise HTTPException(400, 'invalid mode, use: shock, distance, touch')
    cfg = SETTINGS['dglab3'][f'channel_{ch}']['mode_config']
    mode_cfg = cfg.get(mode, {})
    trigger = cfg.get('trigger_range', {})
    return {'config': mode_cfg, 'trigger_range': trigger}

@app.post("/api/v1/mode_config/{channel}/{mode}")
async def api_v1_mode_config_set(channel: str, mode: str, request: Request):
    ch = channel.lower()
    if ch not in ('a', 'b'):
        raise HTTPException(400, 'invalid channel')
    if mode not in ('shock', 'distance', 'touch'):
        raise HTTPException(400, 'invalid mode, use: shock, distance, touch')
    data = await request.json()
    cfg = SETTINGS['dglab3'][f'channel_{ch}']['mode_config']
    mode_cfg = cfg.setdefault(mode, {})

    # Update mode-specific fields
    if mode == 'shock':
        for key in ('duration', 'wave_preset', 'wave_scale', 'wave'):
            if key in data:
                mode_cfg[key] = data[key]
    elif mode == 'distance':
        for key in ('freq_ms', 'wave_preset', 'wave_scale', 'texture_floor',
                    'wave_window_ops', 'wave_sample_step', 'wave_advance_samples',
                    'wave_envelope_curve'):
            if key in data:
                mode_cfg[key] = data[key]
    elif mode == 'touch':
        for key in ('wave_preset', 'wave_scale', 'n_derivative', 'texture_floor',
                    'wave_window_ops', 'wave_sample_step', 'wave_advance_samples',
                    'wave_envelope_curve'):
            if key in data:
                mode_cfg[key] = data[key]

    # Update trigger_range if provided
    if 'trigger_range' in data:
        cfg.setdefault('trigger_range', {}).update(data['trigger_range'])

    for handler in handlers:
        if hasattr(handler, 'refresh_settings'):
            handler.refresh_settings()
    config_save()
    return {'success': True}

# --- Combo ---
@app.get("/api/v1/combo/{channel}")
async def api_v1_combo_get(channel: str):
    ch = channel.lower()
    if ch not in ('a', 'b'):
        raise HTTPException(400, 'invalid channel')
    cfg = SETTINGS['dglab3'][f'channel_{ch}']['mode_config']
    return {
        'combo': cfg.get('combo', {}),
        'shock': cfg.get('shock', {}),
        'touch': cfg.get('touch', {}),
        'trigger_range': cfg.get('trigger_range', {}),
    }

@app.post("/api/v1/combo/{channel}")
async def api_v1_combo_set(channel: str, request: Request):
    ch = channel.lower()
    if ch not in ('a', 'b'):
        raise HTTPException(400, 'invalid channel')
    data = await request.json()
    cfg = SETTINGS['dglab3'][f'channel_{ch}']['mode_config']
    if 'combo' in data:
        cfg.setdefault('combo', {}).update(data['combo'])
    if 'shock' in data:
        for key in ('duration', 'wave_preset', 'wave_scale'):
            if key in data['shock']:
                cfg['shock'][key] = data['shock'][key]
    if 'touch' in data:
        for key in ('wave_preset', 'wave_scale', 'n_derivative'):
            if key in data['touch']:
                cfg['touch'][key] = data['touch'][key]
    if 'trigger_range' in data:
        cfg['trigger_range'].update(data['trigger_range'])
    for handler in handlers:
        if hasattr(handler, 'refresh_settings'):
            handler.refresh_settings()
    config_save()
    return {'success': True}

# --- Curve Mapping ---
DEFAULT_CURVE_POINTS = [{'x': 0, 'y': 0}, {'x': 1, 'y': 1}]
_curve_config = {}

def _get_curve_config_path():
    return os.path.join(get_exe_dir(), 'curve_config.yaml')

def _load_curve_config():
    global _curve_config
    path = _get_curve_config_path()
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            _curve_config = yaml.safe_load(f) or {}

def _save_curve_config():
    path = _get_curve_config_path()
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        yaml.safe_dump(_curve_config, f, allow_unicode=True)
    os.replace(tmp, path)

def get_curve_points(param_path):
    if param_path and param_path in _curve_config:
        return _curve_config[param_path]
    if param_path and param_path.upper() in ('A', 'B'):
        return _curve_config.get(f'channel_{param_path.lower()}') or DEFAULT_CURVE_POINTS
    return DEFAULT_CURVE_POINTS

def get_curve_keys():
    return list(_curve_config.keys())

def apply_curve(value, points):
    if not points or value <= 0:
        return 0.0
    if value >= 1:
        return min(1.0, points[-1]['y'] if points else 1.0)
    for i in range(len(points) - 1):
        if value >= points[i]['x'] and value <= points[i + 1]['x']:
            dx = points[i + 1]['x'] - points[i]['x']
            if dx <= 0:
                return points[i]['y']
            t = (value - points[i]['x']) / dx
            return points[i]['y'] + t * (points[i + 1]['y'] - points[i]['y'])
    return points[-1]['y'] if points else value

@app.get("/api/v1/curve")
async def api_v1_curve_list():
    result = {}
    for key, pts in _curve_config.items():
        result[key] = pts
    return {'curves': result, 'default': DEFAULT_CURVE_POINTS}

@app.get("/api/v1/curve/{param_key:path}")
async def api_v1_curve_get(param_key: str):
    pts = get_curve_points(param_key)
    return {'key': param_key, 'points': pts}

@app.post("/api/v1/curve/{param_key:path}")
async def api_v1_curve_set(param_key: str, request: Request):
    data = await request.json()
    pts = data.get('points', [])
    validated = []
    for p in pts:
        x = max(0.0, min(1.0, float(p.get('x', 0))))
        y = max(0.0, min(1.0, float(p.get('y', 0))))
        validated.append({'x': round(x, 4), 'y': round(y, 4)})
    validated.sort(key=lambda p: p['x'])
    _curve_config[param_key] = validated
    _save_curve_config()
    return {'success': True, 'key': param_key, 'points': validated}

@app.delete("/api/v1/curve/{param_key:path}")
async def api_v1_curve_delete(param_key: str):
    if param_key in _curve_config:
        del _curve_config[param_key]
        _save_curve_config()
    return {'success': True}

_load_curve_config()
_load_overlimit_rules()

# --- Profile Management ---
PROFILES_DIR = os.path.join(get_exe_dir(), 'profiles')

def _ensure_profiles_dir():
    os.makedirs(PROFILES_DIR, exist_ok=True)

def _safe_profile_name(name):
    return re.sub(r'[^\w\u4e00-\u9fff\-]', '_', name.strip())[:50]

@app.get("/api/v1/profiles")
async def api_v1_profiles_list():
    _ensure_profiles_dir()
    profiles = []
    for f in sorted(os.listdir(PROFILES_DIR)):
        if f.endswith('.yaml'):
            profiles.append(f[:-5])
    return {'profiles': profiles}

@app.put("/api/v1/profiles/{name}")
async def api_v1_profiles_save(name: str):
    _ensure_profiles_dir()
    safe_name = _safe_profile_name(name)
    if not safe_name:
        raise HTTPException(400, 'Invalid name')
    profile_data = {
        'basic': copy.deepcopy(SETTINGS_BASIC),
        'advanced': strip_basic_settings(SETTINGS),
    }
    path = os.path.join(PROFILES_DIR, safe_name + '.yaml')
    with open(path, 'w', encoding='utf-8') as fw:
        yaml.safe_dump(profile_data, fw, allow_unicode=True)
    logger.info(f"[profile] Saved profile: {safe_name}")
    return {'success': True, 'name': safe_name}

@app.post("/api/v1/profiles/{name}")
async def api_v1_profiles_load(name: str):
    safe_name = _safe_profile_name(name)
    path = os.path.join(PROFILES_DIR, safe_name + '.yaml')
    if not os.path.exists(path):
        raise HTTPException(404, 'Profile not found')
    try:
        with open(path, 'r', encoding='utf-8') as fr:
            profile_data = yaml.safe_load(fr)
        new_basic = merge_defaults(DEFAULT_SETTINGS_BASIC, profile_data.get('basic', {}))
        new_advanced = merge_defaults(DEFAULT_SETTINGS, profile_data.get('advanced', {}))
        for ch in ['channel_a', 'channel_b']:
            new_advanced['dglab3'][ch]['avatar_params'] = new_basic['dglab3'][ch]['avatar_params']
            new_advanced['dglab3'][ch]['mode'] = new_basic['dglab3'][ch]['mode']
            new_advanced['dglab3'][ch]['strength_limit'] = new_basic['dglab3'][ch]['strength_limit']
            normalize_avatar_param_entries(new_advanced['dglab3'][ch])
        new_advanced['ws']['master_uuid'] = SETTINGS['ws']['master_uuid']
        apply_hot_reloadable_settings(new_advanced, new_basic)
        config_save()
        logger.success(f"[profile] Loaded profile: {safe_name}")
        return {'success': True, 'name': safe_name}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.delete("/api/v1/profiles/{name}")
async def api_v1_profiles_delete(name: str):
    safe_name = _safe_profile_name(name)
    path = os.path.join(PROFILES_DIR, safe_name + '.yaml')
    if os.path.exists(path):
        os.remove(path)
        return {'success': True}
    raise HTTPException(404, 'Not found')


# --- OSC Recording / Playback ---
RECORDINGS_DIR = os.path.join(get_exe_dir(), 'recordings')

_recording_state = {
    'active': False,
    'start_time': 0,
    'messages': [],
    'filename': None,
}

_playback_state = {
    'active': False,
    'filename': None,
    'progress': 0,
    'total': 0,
    'speed': 1.0,
    'loop': False,
    'stop_flag': False,
}

def _ensure_recordings_dir():
    os.makedirs(RECORDINGS_DIR, exist_ok=True)

def _osc_record_hook(address, *args):
    """Global OSC handler for recording ALL params."""
    _overlimit_osc_hook(address, *args)
    if _recording_state['active']:
        elapsed_ms = (time.perf_counter() - _recording_state['start_time']) * 1000.0
        _recording_state['messages'].append({
            't': round(elapsed_ms, 3),
            'addr': address,
            'args': list(args),
        })

@app.post("/api/v1/recorder/start")
async def api_v1_recorder_start():
    if _recording_state['active']:
        return {'success': False, 'message': 'Already recording'}
    _ensure_recordings_dir()
    from datetime import datetime
    _recording_state['active'] = True
    _recording_state['start_time'] = time.perf_counter()
    _recording_state['messages'] = []
    _recording_state['filename'] = f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    logger.success(f"[recorder] Started recording: {_recording_state['filename']}")
    return {'success': True, 'filename': _recording_state['filename']}

@app.post("/api/v1/recorder/stop")
async def api_v1_recorder_stop():
    if not _recording_state['active']:
        return {'success': False, 'message': 'Not recording'}
    _recording_state['active'] = False
    messages = _recording_state['messages']
    filename = _recording_state['filename']
    duration_ms = messages[-1]['t'] if messages else 0
    data = {
        'version': 1,
        'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'duration_ms': round(duration_ms, 3),
        'message_count': len(messages),
        'messages': messages,
    }
    filepath = os.path.join(RECORDINGS_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    _recording_state['messages'] = []
    logger.success(f"[recorder] Stopped. Saved {len(messages)} messages ({duration_ms/1000:.1f}s) to {filename}")
    return {'success': True, 'filename': filename, 'message_count': len(messages), 'duration_ms': duration_ms}

@app.get("/api/v1/recorder/status")
async def api_v1_recorder_status():
    elapsed_ms = 0
    if _recording_state['active']:
        elapsed_ms = (time.perf_counter() - _recording_state['start_time']) * 1000.0
    return {
        'recording': _recording_state['active'],
        'filename': _recording_state['filename'],
        'message_count': len(_recording_state['messages']),
        'elapsed_ms': round(elapsed_ms, 0),
    }

@app.get("/api/v1/recordings")
async def api_v1_recordings_list():
    _ensure_recordings_dir()
    files = []
    for f in sorted(os.listdir(RECORDINGS_DIR), reverse=True):
        if f.endswith('.json'):
            filepath = os.path.join(RECORDINGS_DIR, f)
            try:
                size = os.path.getsize(filepath)
                with open(filepath, 'r', encoding='utf-8') as fp:
                    header = json.load(fp)
                files.append({
                    'name': f,
                    'size_kb': round(size / 1024, 1),
                    'duration_ms': header.get('duration_ms', 0),
                    'message_count': header.get('message_count', 0),
                    'recorded_at': header.get('recorded_at', ''),
                })
            except Exception:
                files.append({'name': f, 'size_kb': 0, 'duration_ms': 0, 'message_count': 0, 'recorded_at': ''})
    return {'recordings': files}

@app.delete("/api/v1/recordings/{filename}")
async def api_v1_recordings_delete(filename: str):
    filepath = os.path.join(RECORDINGS_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        return {'success': True}
    raise HTTPException(404, 'Not found')

@app.post("/api/v1/playback/start")
async def api_v1_playback_start(request: Request):
    if _playback_state['active']:
        return {'success': False, 'message': 'Already playing'}
    data = await request.json()
    filename = data.get('filename')
    speed = float(data.get('speed', 1.0))
    loop = bool(data.get('loop', False))
    filepath = os.path.join(RECORDINGS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, 'File not found')
    _playback_state['stop_flag'] = False
    _playback_state['filename'] = filename
    _playback_state['speed'] = speed
    _playback_state['loop'] = loop
    _playback_state['progress'] = 0
    _playback_state['active'] = True
    th = Thread(target=_playback_worker, args=(filepath, speed, loop), daemon=True)
    th.start()
    return {'success': True, 'filename': filename}

@app.post("/api/v1/playback/stop")
async def api_v1_playback_stop():
    _playback_state['stop_flag'] = True
    return {'success': True}

@app.get("/api/v1/playback/status")
async def api_v1_playback_status():
    return {
        'active': _playback_state['active'],
        'filename': _playback_state['filename'],
        'progress': _playback_state['progress'],
        'total': _playback_state['total'],
        'speed': _playback_state['speed'],
        'loop': _playback_state['loop'],
    }

def _playback_worker(filepath, speed, loop):
    """Background thread: replay OSC messages with original timing."""
    from pythonosc.udp_client import SimpleUDPClient
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        messages = data.get('messages', [])
        _playback_state['total'] = len(messages)
        if not messages:
            return
        target_port = SETTINGS['osc']['listen_port']
        client = SimpleUDPClient('127.0.0.1', target_port)
        while True:
            start_time = time.perf_counter()
            for i, msg in enumerate(messages):
                if _playback_state['stop_flag']:
                    return
                target_s = (msg['t'] / speed) / 1000.0
                while True:
                    elapsed = time.perf_counter() - start_time
                    remaining = target_s - elapsed
                    if remaining <= 0:
                        break
                    if remaining > 0.005:
                        time.sleep(remaining * 0.8)
                addr = msg['addr']
                args = msg.get('args', [])
                try:
                    osc_args = []
                    for a in args:
                        if isinstance(a, bool):
                            osc_args.append(a)
                        elif isinstance(a, int):
                            osc_args.append(float(a))
                        else:
                            osc_args.append(a)
                    client.send_message(addr, osc_args if len(osc_args) != 1 else osc_args[0])
                except Exception:
                    pass
                _playback_state['progress'] = i + 1
            if not loop:
                break
            time.sleep(0.5)
    finally:
        _playback_state['active'] = False
        _playback_state['progress'] = 0

# --- Wave Simulate ---
@app.post("/api/v1/wave_simulate")
async def api_v1_wave_simulate(request: Request):
    """Simulate wave output for given mode parameters and input value. Pure computation, no device needed."""
    from srv.wave_preset import WavePresetLibrary
    try:
        data = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "Invalid or missing JSON body"})
    mode = data.get('mode', 'distance')
    channel = data.get('channel', 'a').lower()
    input_value = float(data.get('input_value', 0.5))
    params = data.get('params', {})

    input_value = max(0.0, min(1.0, input_value))
    trigger_range = params.get('trigger_range', {'bottom': 0.0, 'top': 0.8})
    bottom = float(trigger_range.get('bottom', 0.0))
    top = float(trigger_range.get('top', 0.8))

    # Normalize input through trigger range
    if top <= bottom:
        normalized = 0.0
    elif input_value <= bottom:
        normalized = 0.0
    else:
        normalized = min(1.0, (input_value - bottom) / (top - bottom))

    # Apply curve if available
    effective_strength = normalized
    curve_getter = ShockHandler._curve_getter
    if curve_getter:
        points = curve_getter(f'channel_{channel}')
        if points:
            effective_strength = apply_curve(normalized, points)

    # Determine wave parameters
    wave_preset = params.get('wave_preset') or None
    wave_scale = max(0.0, min(1.0, float(params.get('wave_scale', 1.0))))
    texture_floor = max(0.0, min(1.0, float(params.get('texture_floor', 0.0))))

    lib = WavePresetLibrary()
    samples = []

    if mode == 'shock':
        duration_s = max(0.5, min(10.0, float(params.get('duration', 2.0))))
        total_samples = int(duration_s * 40)  # 40 samples/sec (25ms each)

        if wave_preset and lib.get(wave_preset):
            preset = lib.get(wave_preset)
            texture_samples = preset.get('texture_samples', [])
            if texture_samples:
                for i in range(total_samples):
                    # Shock mode: strength decays from 1.0 to 0.0 over duration
                    t_frac = i / max(1, total_samples - 1)
                    envelope = max(0.0, 1.0 - t_frac)
                    tex_idx = i % len(texture_samples)
                    tex_val = texture_samples[tex_idx]
                    val = tex_val * wave_scale * envelope * effective_strength
                    samples.append(max(0.0, min(1.0, val)))
            else:
                for i in range(total_samples):
                    t_frac = i / max(1, total_samples - 1)
                    envelope = max(0.0, 1.0 - t_frac)
                    samples.append(envelope * wave_scale * effective_strength)
        else:
            # Default shock wave: full strength decaying
            for i in range(total_samples):
                t_frac = i / max(1, total_samples - 1)
                envelope = max(0.0, 1.0 - t_frac)
                samples.append(envelope * wave_scale * effective_strength)

        duration_ms = duration_s * 1000

    elif mode in ('distance', 'touch'):
        window_ops = max(1, min(16, int(params.get('wave_window_ops', 4))))
        sample_step = max(0.25, min(8.0, float(params.get('wave_sample_step', 1.0))))
        total_samples = window_ops * 4  # 4 samples per op

        if wave_preset and lib.get(wave_preset):
            preset = lib.get(wave_preset)
            texture_samples = preset.get('texture_samples', [])
            freq_samples = preset.get('freq_samples', [])
            if texture_samples:
                for i in range(total_samples):
                    position = i * sample_step
                    tex_len = len(texture_samples)
                    pos_mod = position % tex_len
                    left = int(pos_mod) % tex_len
                    right = (left + 1) % tex_len
                    frac = pos_mod - int(pos_mod)
                    tex_val = texture_samples[left] * (1.0 - frac) + texture_samples[right] * frac
                    # Apply texture_floor
                    lifted = texture_floor + tex_val * (1.0 - texture_floor)
                    val = lifted * wave_scale * effective_strength
                    samples.append(max(0.0, min(1.0, val)))
            else:
                for i in range(total_samples):
                    samples.append(wave_scale * effective_strength)
        else:
            # No preset: generate simple pulse based on freq_ms
            freq_ms = max(10, min(240, int(params.get('freq_ms', 10))))
            for i in range(total_samples):
                samples.append(wave_scale * effective_strength)

        duration_ms = total_samples * 25  # Each sample = 25ms

    else:
        duration_ms = 0

    return {
        'samples': [round(s, 4) for s in samples],
        'effective_strength': round(effective_strength, 4),
        'duration_ms': duration_ms,
        'info': {
            'mode': mode,
            'input_value': input_value,
            'normalized': round(normalized, 4),
            'wave_preset': wave_preset,
            'total_samples': len(samples),
        },
    }


# --- Wave Presets ---
@app.get("/api/v1/wave_presets")
async def api_v1_wave_presets():
    from srv.wave_preset import WavePresetLibrary
    lib = WavePresetLibrary()
    return {'presets': list(lib.presets.keys())}

@app.get("/api/v1/wave_presets/{preset_name}/samples")
async def api_v1_wave_preset_samples(preset_name: str):
    """Get raw waveform samples for visualization."""
    from srv.wave_preset import WavePresetLibrary
    lib = WavePresetLibrary()
    preset = lib.get(preset_name)
    if not preset:
        raise HTTPException(404, 'preset not found')
    return {
        'name': preset_name,
        'texture_samples': preset.get('texture_samples', []),
        'strength_samples': preset.get('strength_samples', []),
        'freq_samples': preset.get('freq_samples', []),
        'num_ops': len(preset.get('ops', [])),
    }

@app.get("/api/v1/wave_presets/{preset_name}/preview")
async def api_v1_wave_preset_preview(preset_name: str):
    from srv.wave_preset import WavePresetLibrary
    from pulse_to_hex.dglab_pulse_converter import parse_pulse
    import math

    lib = WavePresetLibrary()
    preset = lib.get(preset_name)
    if not preset:
        raise HTTPException(404, 'preset not found')

    # Try to get preview from preset JSON metadata (works on all platforms)
    raw_preset = lib.get_raw(preset_name)
    if raw_preset and 'preview_sections' in raw_preset and raw_preset['preview_sections']:
        header_data = raw_preset.get('header') or {}
        speed = header_data.get('speed', 1) if header_data else 1
        rest_ticks = header_data.get('rest_ticks', 0) if header_data else 0
        return {
            'name': preset_name,
            'speed': speed,
            'rest_ticks': rest_ticks,
            'sections': raw_preset['preview_sections'],
        }

    # Fallback: try .pulse source file
    pulse_dir = os.path.join(get_exe_dir(), 'dg-lab')
    pulse_file = os.path.join(pulse_dir, preset_name + '.pulse')
    if os.path.exists(pulse_file):
        with open(pulse_file, 'r', encoding='utf-8') as f:
            pulse_text = f.read().strip()

        header, sections = parse_pulse(pulse_text)
        speed = header.speed if header else 1

        result_sections = []
        for sec in sections:
            if not sec.enabled:
                continue
            if not sec.points:
                continue
            n_points = len(sec.points)
            duration = max(0, sec.duration)
            repeats = max(1, math.ceil(duration / n_points)) if duration > 0 else 1
            points = []
            for val, flag in sec.points:
                points.append({
                    'strength': round(max(0, min(100, val))),
                    'anchor': flag == 1,
                })
            result_sections.append({
                'freq_low': sec.freq_low,
                'freq_high': sec.freq_high,
                'freq_mode': sec.freq_mode,
                'duration': duration,
                'n_points': n_points,
                'repeats': repeats,
                'points': points,
            })

        return {
            'name': preset_name,
            'speed': speed,
            'rest_ticks': header.rest_ticks if header else 0,
            'sections': result_sections,
        }

    # Last fallback: build from ops data
    ops = preset.get('ops', [])
    strengths = []
    for op in ops:
        for i in range(4):
            strengths.append(int(op[8 + i * 2:8 + i * 2 + 2], 16))
    n_points = len(strengths)
    header_data = raw_preset.get('header') or {} if raw_preset else {}
    speed = header_data.get('speed', 1) if header_data else 1
    return {
        'name': preset_name,
        'speed': speed,
        'rest_ticks': header_data.get('rest_ticks', 0) if header_data else 0,
        'sections': [{
            'freq_low': 0,
            'freq_high': 0,
            'freq_mode': 1,
            'duration': n_points,
            'n_points': n_points,
            'repeats': 1,
            'points': [{'strength': s, 'anchor': True} for s in strengths],
        }],
    }

@app.post("/api/v1/wave_presets/import")
async def api_v1_wave_presets_import(file: UploadFile = File(...)):
    """Import a wave preset from uploaded .pulse or .json file."""
    from pulse_to_hex.dglab_pulse_converter import convert_to_ops
    from srv.wave_preset import WavePresetLibrary, PRESET_DIR

    if not file.filename:
        raise HTTPException(400, 'empty filename')

    filename = file.filename
    content_bytes = await file.read()
    content = content_bytes.decode('utf-8', errors='replace').strip()

    if filename.endswith('.pulse'):
        try:
            ops, wavestrs, header, sections = convert_to_ops(content)
        except Exception as e:
            raise HTTPException(400, f'pulse parse failed: {e}')
        if not ops:
            raise HTTPException(400, 'no valid wave data in file')
        preset_name = filename.rsplit('.', 1)[0]

        # Build preview_sections metadata (same logic as batch converter)
        import math as _math
        preview_sections = []
        for sec in sections:
            if not sec.enabled or not sec.points:
                continue
            n_points = len(sec.points)
            duration = max(0, sec.duration)
            repeats = max(1, _math.ceil(duration / n_points)) if duration > 0 else 1
            preview_sections.append({
                'freq_low': sec.freq_low,
                'freq_high': sec.freq_high,
                'freq_mode': sec.freq_mode,
                'duration': duration,
                'n_points': n_points,
                'repeats': repeats,
                'points': [{'strength': round(max(0, min(100, v))), 'anchor': flag == 1} for v, flag in sec.points],
            })

        preset_data = {
            'name': preset_name,
            'source_file': filename,
            'num_ops': len(ops),
            'header': header.__dict__ if header else None,
            'preview_sections': preview_sections,
            'wavestrs': wavestrs,
        }
        out_path = PRESET_DIR / f'{preset_name}.json'
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(preset_data, f, ensure_ascii=False, indent=2)
        dg_lab_dir = os.path.join(get_exe_dir(), 'dg-lab')
        os.makedirs(dg_lab_dir, exist_ok=True)
        pulse_path = os.path.join(dg_lab_dir, filename)
        with open(pulse_path, 'w', encoding='utf-8') as f:
            f.write(content)
        lib = WavePresetLibrary()
        lib.reload()
        return {'result': 'OK', 'name': preset_name, 'ops': len(ops)}

    elif filename.endswith('.json'):
        try:
            preset_data = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(400, f'invalid JSON: {e}')
        if 'wavestrs' not in preset_data and 'ops' not in preset_data:
            raise HTTPException(400, 'JSON must contain "wavestrs" or "ops"')
        preset_name = preset_data.get('name') or filename.rsplit('.', 1)[0]
        preset_data['name'] = preset_name
        out_path = PRESET_DIR / f'{preset_name}.json'
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(preset_data, f, ensure_ascii=False, indent=2)
        lib = WavePresetLibrary()
        lib.reload()
        num_ops = preset_data.get('num_ops', 0)
        return {'result': 'OK', 'name': preset_name, 'ops': num_ops}

    else:
        raise HTTPException(400, 'unsupported format, use .pulse or .json')

@app.get("/api/v1/wave_preset/{channel}/{preset_name}/{duration}")
async def api_v1_wave_preset(channel: str, preset_name: str, duration: int):
    from srv.wave_preset import WavePresetLibrary
    lib = WavePresetLibrary()
    preset = lib.get(preset_name)
    if not preset:
        raise HTTPException(404, 'preset not found')
    channel = channel.upper()
    if channel not in ['A', 'B']:
        channel = 'A'
    duration = min(max(duration, 1), 10)
    ops = preset['ops']
    ops_needed = duration * 10
    repeated = (ops * ((ops_needed // len(ops)) + 1))[:ops_needed]
    for i in range(0, len(repeated), 80):
        chunk = repeated[i:i+80]
        wavestr = json.dumps(chunk, separators=(',', ':'))
        await command_queue.put(CommandPriority.API, channel, 'wave', value=wavestr, source_id='api_wave_preset')
    return {'result': 'OK', 'ops_sent': len(repeated)}


# --- SPA catch-all routes ---
_SPA_PATHS = ["/dashboard", "/curve", "/combo", "/params", "/recorder",
              "/settings", "/strength", "/overlimit-rules", "/wave-test"]

for _spa_path in _SPA_PATHS:
    async def _spa_handler(_p=_spa_path):
        return _serve_spa()
    app.add_api_route(_spa_path, _spa_handler, methods=["GET"], include_in_schema=False)

# Mount static files for assets only (not root, to avoid interfering with WS/API)
if os.path.exists(STATIC_DIR):
    assets_dir = os.path.join(STATIC_DIR, 'assets')
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="static_assets")

# --- Shared state ---
command_queue = CommandQueue()

# --- Graceful shutdown state ---
_uvicorn_server = None  # Set when uvicorn starts (Server instance)
_tray_icon_ref = None   # Set when tray icon starts (pystray.Icon instance)

# --- V4 Relay Server ---
v4_relay = DGV4RelayServer(SETTINGS)

# --- Frontend WebSocket push ---
_ws_clients: set[WebSocket] = set()
_ws_subscriptions: dict[WebSocket, set] = {}  # ws -> set of topics ('wave_A', 'wave_B', 'osc', 'status')

async def _ws_broadcast(topic: str, data: dict):
    """Send data to all clients subscribed to topic."""
    if not _ws_clients:
        return
    dead = []
    msg = json.dumps({'topic': topic, **data}, separators=(',', ':'))
    for ws in list(_ws_clients):
        if topic in _ws_subscriptions.get(ws, set()):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)
        _ws_subscriptions.pop(ws, None)

def _ws_broadcast_sync(topic: str, data: dict):
    """Schedule WS broadcast as a task on the running event loop."""
    if not _ws_clients:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_ws_broadcast(topic, data))
    except RuntimeError:
        pass

@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    """Frontend WebSocket for real-time push.
    
    Client sends JSON to subscribe: {"subscribe": ["wave_A", "wave_B", "osc", "status"]}
    Server pushes: {"topic": "wave_A", "samples": [...]}
    """
    await ws.accept()
    _ws_clients.add(ws)
    _ws_subscriptions[ws] = set()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                if 'subscribe' in msg:
                    _ws_subscriptions[ws] = set(msg['subscribe'])
                if msg.get('ping'):
                    await ws.send_text(json.dumps({'pong': True}))
            except (json.JSONDecodeError, TypeError):
                pass
    except Exception:
        pass
    finally:
        _ws_clients.discard(ws)
        _ws_subscriptions.pop(ws, None)


@app.websocket("/ws/dglab-v4")
async def ws_dglab_v4(ws: WebSocket, tid: str = None):
    """DG-LAB V4 WebSocket relay endpoint.
    
    DG-LAB 4 APP connects here with ?tid=<controller_id> to be controlled.
    This implements the V4 relay server protocol on the same HTTP port.
    """
    if not SETTINGS['ws'].get('v4_enabled', True):
        await ws.close(4003, 'v4_disabled')
        return
    await ws.accept()
    await v4_relay.handle_websocket(ws, tid=tid)


# OSC activity ring buffer
_osc_activity = collections.deque(maxlen=50)

def _record_osc_activity(address, value, channel, mode):
    event = {
        'time': time.time(),
        'address': address,
        'value': round(value, 4),
        'channel': channel,
        'mode': mode,
    }
    _osc_activity.appendleft(event)
    # Push to WS clients
    _ws_broadcast_sync('osc', {'event': event})

# Wave history ring buffer
_wave_history = {'A': collections.deque(maxlen=800), 'B': collections.deque(maxlen=800)}
_wave_history_last_update = {'A': 0.0, 'B': 0.0}
_wave_history_seq = {'A': 0, 'B': 0}

def _record_wave(channel, wavestr):
    try:
        channel = channel.upper()
        ops = json.loads(wavestr)
        samples = []
        for op in ops:
            for i in range(4):
                freq = int(op[i*2:i*2+2], 16)
                strength = int(op[8+i*2:10+i*2], 16)
                _wave_history_seq[channel] += 1
                _wave_history[channel].append({'s': strength, 'f': freq, 'seq': _wave_history_seq[channel]})
                samples.append({'s': strength, 'f': freq})
        _wave_history_last_update[channel] = time.monotonic()
        # Push to WS clients
        _ws_broadcast_sync(f'wave_{channel}', {
            'samples': samples,
            'seq': _wave_history_seq[channel],
        })
    except Exception:
        pass

def _clear_wave_history(channel):
    channel = channel.upper()
    if channel not in _wave_history:
        return
    _wave_history[channel].clear()
    _wave_history_last_update[channel] = 0.0

DGConnection.wave_observer = _record_wave
DGConnection.clear_observer = _clear_wave_history

def _get_wave_history_snapshot(channel):
    history = list(_wave_history[channel])
    if not history:
        return []
    last_update = _wave_history_last_update.get(channel, 0.0)
    zero_sample = {'s': 0, 'f': 10}
    if last_update <= 0.0:
        return history[-200:]
    elapsed_ms = max(0.0, (time.monotonic() - last_update) * 1000.0)
    elapsed_samples = int(elapsed_ms // WAVE_HISTORY_SAMPLE_MS)
    if elapsed_samples <= 0:
        return history[-200:]
    if elapsed_samples >= 200:
        return [zero_sample] * 200
    tail = history[-200:]
    if elapsed_samples >= len(tail):
        return [zero_sample] * len(tail)
    return tail[elapsed_samples:] + [zero_sample] * elapsed_samples

# --- Command Queue Processor ---
async def command_queue_processor(stop_event: asyncio.Event):
    while not stop_event.is_set():
        try:
            cmd = await asyncio.wait_for(command_queue.get(), timeout=0.5)
            if cmd.action == 'osc_trigger':
                handler_fn = cmd.value['handler']
                await handler_fn(cmd.value['val'], context=cmd.value['context'])
            elif cmd.action == 'wave':
                await DGConnection.broadcast_wave(channel=cmd.channel, wavestr=cmd.value)
            elif cmd.action == 'clear':
                if not _wave_test_state['active']:
                    await DGConnection.broadcast_clear_wave(cmd.channel)
            command_queue.task_done()
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"[queue] error: {e}")
            await asyncio.sleep(0.01)

# --- DG-LAB WebSocket handler ---
async def wshandler(connection):
    client = DGConnection(connection, SETTINGS=SETTINGS)
    await client.serve()

# --- Engine ---
class Engine:
    """Data processing engine: OSC listener, WebSocket server, command queue, handlers.
    
    Runs as async tasks on the same event loop as Uvicorn (no separate thread).
    WS server lifecycle is independent of OSC/handlers — hot-reload only restarts
    what's needed, preserving DG-LAB device connections.
    """

    def __init__(self):
        self._stop_event: asyncio.Event | None = None
        self._tasks: list[asyncio.Task] = []
        self._transport = None
        self._ws_server = None
        self._ws_running = False
        self._running = False
        self.dispatcher: Dispatcher | None = None
        self.handlers: list = []

    @property
    def running(self):
        return self._running

    def _build_dispatcher_and_handlers(self):
        self.dispatcher = Dispatcher()
        self.dispatcher.set_default_handler(_osc_record_hook)
        self.handlers = []

        ShockHandler.set_command_queue(command_queue)
        ShockHandler.osc_activity_observer = _record_osc_activity
        ShockHandler._curve_getter = get_curve_points

        for chann in ['A', 'B']:
            config_chann_name = f'channel_{chann.lower()}'
            channel_handlers = {}
            avatar_params = SETTINGS['dglab3'][config_chann_name].get('avatar_params', [])
            for param_entry in avatar_params:
                if not param_entry.get('enabled', True):
                    logger.info(f"[engine] Channel {chann} skipping disabled param: {param_entry['path']}")
                    continue
                param_path = param_entry['path']
                param_mode = param_entry['mode']
                if param_mode not in channel_handlers:
                    channel_handlers[param_mode] = ShockHandler(
                        SETTINGS=SETTINGS,
                        DG_CONN=DGConnection,
                        channel_name=chann,
                        handler_mode=param_mode,
                    )
                    self.handlers.append(channel_handlers[param_mode])
                logger.info(f"[engine] Channel {chann} mode {param_mode} listening {param_path}")
                self.dispatcher.map(param_path, channel_handlers[param_mode].osc_handler)

        global handlers
        handlers = self.handlers

    async def start(self):
        """Start the engine as async tasks on the current event loop."""
        if self._running:
            logger.warning("[engine] Already running, stop first.")
            return

        self._build_dispatcher_and_handlers()
        self._stop_event = asyncio.Event()
        command_queue.clear()

        # Start background tasks
        self._tasks = [
            asyncio.create_task(command_queue_processor(self._stop_event)),
            asyncio.create_task(_strength_boost_checker(self._stop_event)),
            asyncio.create_task(_wave_test_loop(self._stop_event)),
            asyncio.create_task(_ws_status_pusher(self._stop_event)),
        ]
        for handler in self.handlers:
            handler.start_background_jobs()

        # Start OSC server
        try:
            server = AsyncIOOSCUDPServer(
                (SETTINGS["osc"]["listen_host"], SETTINGS["osc"]["listen_port"]),
                self.dispatcher, asyncio.get_event_loop()
            )
            self._transport, _ = await server.create_serve_endpoint()
            logger.success(f'[engine] OSC Listening: {SETTINGS["osc"]["listen_host"]}:{SETTINGS["osc"]["listen_port"]}')
        except Exception:
            logger.error(traceback.format_exc())
            logger.error("[engine] OSC listen failed, possible port conflict")
            await self._cleanup_tasks()
            return

        # Start DG-LAB WebSocket server (only if not already running)
        if not self._ws_running:
            await self._start_ws_server()

        self._running = True
        logger.info("[engine] Started.")

    async def _start_ws_server(self):
        """Start the DG-LAB WebSocket server independently."""
        try:
            self._ws_server = await wsserve(wshandler, SETTINGS['ws']["listen_host"], SETTINGS['ws']["listen_port"])
            self._ws_running = True
            logger.success(f'[engine] WS Listening: {SETTINGS["ws"]["listen_host"]}:{SETTINGS["ws"]["listen_port"]}')
        except Exception:
            logger.error(traceback.format_exc())
            logger.error("[engine] WS server listen failed, possible port conflict")

    async def _stop_ws_server(self):
        """Stop the DG-LAB WebSocket server."""
        if self._ws_server:
            self._ws_server.close()
            await self._ws_server.wait_closed()
            self._ws_server = None
            self._ws_running = False
            logger.info("[engine] WS server stopped.")

    async def stop(self, *, keep_ws: bool = False):
        """Stop the engine gracefully.
        
        Args:
            keep_ws: If True, preserve the DG-LAB WebSocket server (device connections stay alive).
        """
        if not self._running:
            return

        # Stop wave test if active
        if _wave_test_state['active']:
            _wave_test_state['active'] = False
            command_queue.set_enabled(CommandPriority.OSC_INTERACTION, True)
            command_queue.set_enabled(CommandPriority.OSC_PANEL, True)
            command_queue.set_enabled(CommandPriority.GAME, True)
            DGConnection._suppress_clear = False
            logger.info("[engine] Wave test stopped due to engine shutdown.")

        # Signal stop
        if self._stop_event:
            self._stop_event.set()

        logger.info("[engine] Stopping...")

        # Close WS server only if requested
        if not keep_ws:
            await self._stop_ws_server()

        # Close OSC transport
        if self._transport:
            self._transport.close()
            self._transport = None

        # Cancel tasks
        await self._cleanup_tasks()
        self._running = False
        logger.info(f"[engine] Stopped.{' (WS preserved)' if keep_ws else ''}")

    async def _cleanup_tasks(self):
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def restart(self, *, keep_ws: bool = True):
        """Restart the engine.
        
        Args:
            keep_ws: If True (default), preserve DG-LAB WebSocket connections.
                     Only set False when ws port/host config actually changed.
        """
        logger.info(f"[engine] Restarting...{' (preserving WS connections)' if keep_ws else ''}")
        await self.stop(keep_ws=keep_ws)
        await self.start()

    async def restart_ws(self):
        """Restart only the DG-LAB WebSocket server (when ws config changes)."""
        logger.info("[engine] Restarting WS server (port/host changed)...")
        await self._stop_ws_server()
        await self._start_ws_server()

engine = Engine()

def _schedule_engine_restart(*, keep_ws: bool = True):
    """Schedule engine restart from sync context."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(engine.restart(keep_ws=keep_ws))
    except RuntimeError:
        logger.error("[engine] Cannot schedule restart: no running event loop")

def _schedule_engine_ws_restart():
    """Schedule WS-only restart from sync context."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(engine.restart_ws())
    except RuntimeError:
        logger.error("[engine] Cannot schedule WS restart: no running event loop")

@app.on_event("startup")
async def on_startup():
    """Start the engine and config watcher when Uvicorn's event loop is ready."""
    await engine.start()
    asyncio.create_task(config_hot_reload_loop())

# --- Config save ---
def config_save():
    for path, data in [(CONFIG_FILENAME, SETTINGS), (CONFIG_FILENAME_BASIC, SETTINGS_BASIC)]:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fw:
            yaml.safe_dump(data, fw, allow_unicode=True)
        os.replace(tmp, path)

class ConfigFileInited(Exception):
    pass

def config_init():
    logger.info(f'[init] Loading config: {CONFIG_FILENAME_BASIC}, {CONFIG_FILENAME}')
    global SERVER_IP
    if not (os.path.exists(CONFIG_FILENAME) and os.path.exists(CONFIG_FILENAME_BASIC)):
        SETTINGS['ws']['master_uuid'] = str(uuid.uuid4())
        config_save()
        raise ConfigFileInited()

    new_settings, new_basic = load_config_files()
    SETTINGS.clear()
    SETTINGS.update(new_settings)
    SETTINGS_BASIC.clear()
    SETTINGS_BASIC.update(new_basic)

    if SETTINGS.get('version', None) != CONFIG_FILE_VERSION or SETTINGS_BASIC.get('version', None) != CONFIG_FILE_VERSION:
        logger.error(f"[init] Config version mismatch! Delete {CONFIG_FILENAME_BASIC} and {CONFIG_FILENAME} and restart.")
        raise Exception(f'Config version mismatch.')
    SERVER_IP = SETTINGS['SERVER_IP'] or get_current_ip()

    reset_logger()
    update_config_mtimes()
    logger.success("[init] Config loaded. WS needs external access - allow firewall prompt if shown.")

def main():
    if SETTINGS['general']['auto_open_qr_web_page'] and not os.environ.pop('SHOCKING_SKIP_OPEN', None):
        import webbrowser
        webbrowser.open_new_tab(f"http://127.0.0.1:{SETTINGS['web_server']['listen_port']}")
    else:
        info_ip = SETTINGS['web_server']['listen_host']
        if info_ip == '0.0.0.0':
            info_ip = get_current_ip()
        logger.success(f"[init] Open browser: http://{info_ip}:{SETTINGS['web_server']['listen_port']}")

    # Startup summary
    enabled_a = sum(1 for p in SETTINGS['dglab3']['channel_a']['avatar_params'] if p.get('enabled', True))
    enabled_b = sum(1 for p in SETTINGS['dglab3']['channel_b']['avatar_params'] if p.get('enabled', True))
    logger.info(f"[init] Channel A: {enabled_a} params | Channel B: {enabled_b} params")
    logger.info(f"[init] Web: :{SETTINGS['web_server']['listen_port']} | WS: :{SETTINGS['ws']['listen_port']} | OSC: :{SETTINGS['osc']['listen_port']}")

    # Determine run mode based on --no-tray flag
    no_tray = '--no-tray' in sys.argv

    if no_tray or sys.platform != 'win32':
        # Console mode: tray in background thread (if Windows), uvicorn in main thread
        if not no_tray:
            _start_tray_icon()
        _run_uvicorn_blocking()
    else:
        # Windows tray mode (default): tray in main thread, uvicorn in background thread.
        # This hides the console window completely — the tray icon is the only UI.
        _run_with_tray()


def _create_tray_icon_image():
    """Create tray icon image. Uses .ico file if available, otherwise generates programmatically."""
    from PIL import Image, ImageDraw

    # Try to load the shipped .ico file
    ico_path = os.path.join(get_runtime_base_dir(), 'shocking_vrchat.ico')
    if not os.path.exists(ico_path):
        ico_path = os.path.join(get_exe_dir(), 'shocking_vrchat.ico')
    if os.path.exists(ico_path):
        try:
            img = Image.open(ico_path)
            img = img.resize((64, 64), Image.LANCZOS)
            return img
        except Exception:
            pass

    # Fallback: generate programmatically
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Purple circle background
    draw.ellipse([4, 4, 60, 60], fill=(139, 92, 246, 255))
    # Lightning bolt shape
    draw.polygon([(32, 8), (18, 34), (28, 34), (24, 56), (46, 28), (34, 28), (38, 8)], fill=(255, 255, 255, 255))
    return img


def _start_tray_icon():
    """Start system tray icon in a background thread (Windows only).
    
    Used when --no-tray is NOT set but tray cannot run in main thread (e.g. non-Windows).
    """
    if sys.platform != 'win32':
        return
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        logger.debug("[tray] pystray/Pillow not available, skipping tray icon.")
        return

    def _on_open(icon, item):
        import webbrowser
        webbrowser.open_new_tab(f"http://127.0.0.1:{SETTINGS['web_server']['listen_port']}")

    def _on_quit(icon, item):
        icon.stop()
        # Schedule graceful shutdown on the running event loop
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(lambda: loop.create_task(_graceful_shutdown()))
        except RuntimeError:
            # No event loop running — do synchronous cleanup and exit
            _sync_cleanup_before_exit()
            sys.exit(0)

    port = SETTINGS['web_server']['listen_port']
    menu = pystray.Menu(
        pystray.MenuItem(f'打开管理页面 (:{port})', _on_open, default=True),
        pystray.MenuItem('退出', _on_quit),
    )
    icon = pystray.Icon('ShockingVRChat', _create_tray_icon_image(), 'Shocking VRChat', menu)

    tray_thread = Thread(target=icon.run, daemon=True)
    tray_thread.start()
    logger.info("[tray] System tray icon started (background thread).")


def _run_with_tray():
    """Run with system tray in the main thread, uvicorn in a background thread.
    
    This is the default mode on Windows when --no-tray is not specified.
    The Win32 tray message loop requires the main thread, so uvicorn runs in a daemon thread.
    """
    global _uvicorn_server, _tray_icon_ref
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        logger.warning("[tray] pystray/Pillow not available, falling back to console mode.")
        _run_uvicorn_blocking()
        return

    import uvicorn

    # Start uvicorn in a background thread
    uvicorn_config = uvicorn.Config(
        app,
        host=SETTINGS['web_server']['listen_host'],
        port=SETTINGS['web_server']['listen_port'],
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(uvicorn_config)
    _uvicorn_server = server

    def _uvicorn_thread():
        server.run()

    server_thread = Thread(target=_uvicorn_thread, daemon=True, name='uvicorn-server')
    server_thread.start()

    logger.info("[tray] Uvicorn started in background thread.")

    # Tray callbacks
    def _on_open(icon, item):
        import webbrowser
        webbrowser.open_new_tab(f"http://127.0.0.1:{SETTINGS['web_server']['listen_port']}")

    def _on_quit(icon, item):
        logger.info("[tray] Quit requested via tray menu.")
        icon.stop()
        server.should_exit = True

    port = SETTINGS['web_server']['listen_port']
    menu = pystray.Menu(
        pystray.MenuItem(f'打开管理页面 (:{port})', _on_open, default=True),
        pystray.MenuItem('退出', _on_quit),
    )
    icon = pystray.Icon('ShockingVRChat', _create_tray_icon_image(), 'Shocking VRChat', menu)
    _tray_icon_ref = icon

    logger.info("[tray] System tray icon running in main thread.")
    # icon.run() blocks the main thread with Win32 message pump
    icon.run()

    # After tray exits, ensure uvicorn stops
    server.should_exit = True
    server_thread.join(timeout=5)
    logger.info("[shutdown] Tray and server stopped.")


def _run_uvicorn_blocking():
    """Run uvicorn directly in the main thread (--no-tray mode or non-Windows)."""
    import uvicorn
    uvicorn.run(
        app,
        host=SETTINGS['web_server']['listen_host'],
        port=SETTINGS['web_server']['listen_port'],
        log_level="warning",
        access_log=False,
    )

if __name__ == "__main__":
    # Fix for PyInstaller --noconsole: sys.stdout/stderr are None, which crashes
    # uvicorn's DefaultFormatter (calls .isatty()) and other stdlib code.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')

    # Ensure errors are visible even with console=False (Windows GUI mode)
    _error_log_path = os.path.join(get_exe_dir(), 'error.log')
    try:
        config_init()
        main()
    except ConfigFileInited:
        logger.success('[init] No config file found, starting setup wizard...')
        import webbrowser
        port = SETTINGS['web_server']['listen_port']
        webbrowser.open_new_tab(f"http://127.0.0.1:{port}/setup")
        app.state.setup_complete = False

        @app.get('/api/v1/setup/poll')
        async def setup_poll():
            return {'done': getattr(app.state, 'setup_complete', False)}

        import uvicorn

        def _run_wizard_server():
            uvicorn.run(app, host='127.0.0.1', port=port, log_level="warning", access_log=False)

        wizard_th = Thread(target=_run_wizard_server, daemon=True)
        wizard_th.start()

        # Wait for setup completion then restart
        while not getattr(app.state, 'setup_complete', False):
            time.sleep(0.5)

        logger.success('[init] Setup wizard complete, restarting...')
        os.environ['SHOCKING_SKIP_OPEN'] = '1'
        config_save()
        time.sleep(1)
        _restart_program()
    except Exception as e:
        err_msg = traceback.format_exc()
        # Write to error.log (always accessible even without console)
        try:
            with open(_error_log_path, 'w', encoding='utf-8') as f:
                f.write(f"Shocking VRChat crashed at startup:\n\n{err_msg}\n")
        except:
            pass
        # Try logger (works if stderr exists)
        try:
            logger.error(err_msg)
            logger.error("[init] Unexpected Error. See error.log for details.")
        except:
            pass
        # Show Windows message box if GUI mode (no console)
        if sys.platform == 'win32' and not sys.stderr:
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    0,
                    f"程序启动失败，详细信息已写入 error.log:\n\n{str(e)[:500]}",
                    "Shocking VRChat - Error",
                    0x10  # MB_ICONERROR
                )
            except:
                pass
    try:
        logger.info('[shutdown] Exiting...')
    except:
        pass
    time.sleep(1)
