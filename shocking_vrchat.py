import asyncio
import yaml, uuid, os, sys, traceback, time, socket
from threading import Thread
from loguru import logger

from flask import Flask, render_template, redirect
from websockets.server import serve as wsserve

import srv
from srv.coyotev3ws import DGWSMessage, DGConnection
from srv.shock_handler import ShockHandler

from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.dispatcher import Dispatcher

app = Flask(__name__)

CONFIG_FILE_VERSION  = 'v0.1'
CONFIG_FILENAME = f'settings-{CONFIG_FILE_VERSION}.yaml'
SETTINGS = {
    'SERVER_IP': None,
    'dglab3': {
        'channel_a': {
            'avatar_params': [
                '/avatar/parameters/pcs/sps/pussy',
                '/avatar/parameters/Shock/wildcard/*',
            ],
            'mode': 'distance',
            'mode_config':{
                'shock': {
                    'duration': 2,
                    'wave': '["0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464"]',
                },
                'distance': {
                    'freq_ms': 10,
                },
                'strength_limit': 100,
                'trigger_range': {
                    'bottom': 0.0,
                    'top': 1.0,
                },
            }
        },
        'channel_b': {
            'avatar_params': [
                '/avatar/parameters/VF87_humi/nsfw/contact/dick_touch',
                '/avatar/parameters/ShockB2/some/param',
            ],
            'mode': 'shock',
            'mode_config':{
                'shock': {
                    'duration': 2,
                    'wave': '["0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464"]',
                },
                'distance': {
                    'freq_ms': 10,
                },
                'strength_limit': 100,
                'trigger_range': {
                    'bottom': 0.1,
                    'top': 1.0,
                },
            }
        },
    },
    'ws':{
        'master_uuid': None,
        'listen_host': '0.0.0.0',
        'listen_port': 28846 
    },
    'osc':{
        'listen_host': '127.0.0.1',
        'listen_port': 9001,
    },
    'web_server':{
        'listen_host': '127.0.0.1',
        'listen_port': 8800
    },
    'log_level': 'INFO',
    'version': CONFIG_FILE_VERSION,
    'general': {
        'auto_open_qr_web_page': True,
        'local_ip_detect': {
            'host': '223.5.5.5',
            'port': 80,
        }
    }
}
SERVER_IP = None

@app.route('/get_ip')
def get_current_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((SETTINGS['general']['local_ip_detect']['host'], SETTINGS['general']['local_ip_detect']['port']))
    client_ip = s.getsockname()[0]
    s.close()
    return client_ip

@app.route("/")
def web_index():
    return redirect("/qr", code=302)

@app.route("/qr")
def web_qr():
    return render_template('tiny-qr.html', content=f'https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#ws://{SERVER_IP}:{SETTINGS["ws"]["listen_port"]}/{SETTINGS["ws"]["master_uuid"]}')

@app.route('/conns')
def get_conns():
    return str(srv.WS_CONNECTIONS)

@app.route('/sendwav')
async def sendwav():
    await DGConnection.broadcast_wave(channel='A', wavestr=srv.waveData[0])
    return 'OK'

async def wshandler(connection):
    client = DGConnection(connection, SETTINGS=SETTINGS)
    await client.serve()

async def async_main():
    shock_handler_A.start_background_jobs()
    shock_handler_B.start_background_jobs()
    server = AsyncIOOSCUDPServer((SETTINGS["osc"]["listen_host"], SETTINGS["osc"]["listen_port"]), dispatcher, asyncio.get_event_loop())
    transport, protocol = await server.create_serve_endpoint()
    # await wsserve(wshandler, "127.0.0.1", 8765)
    async with wsserve(wshandler, SETTINGS['ws']["listen_host"], SETTINGS['ws']["listen_port"]):
        await asyncio.Future()  # run forever
    transport.close()

def async_main_wrapper():
    """Not async Wrapper around async_main to run it as target function of Thread"""
    asyncio.run(async_main())

def config_save():
    with open(CONFIG_FILENAME, 'w', encoding='utf-8') as fw:
        yaml.safe_dump(SETTINGS, fw, allow_unicode=True)

class ConfigFileInited(Exception):
    pass

def config_init():
    logger.info(f'Init settings..., Config filename: {CONFIG_FILENAME}, Config version: {CONFIG_FILE_VERSION}.')
    global SETTINGS, SERVER_IP
    if not os.path.exists(CONFIG_FILENAME):
        SETTINGS['ws']['master_uuid'] = str(uuid.uuid4())
        config_save()
        raise ConfigFileInited()
    with open(CONFIG_FILENAME, 'r', encoding='utf-8') as fr:
        SETTINGS = yaml.safe_load(fr)
    if SETTINGS.get('version', None) != CONFIG_FILE_VERSION:
        raise Exception(f'配置文件版本不匹配！请删除 {CONFIG_FILENAME} 文件后再次运行程序，以生成最新版本的配置文件。')
    if SETTINGS['ws']['master_uuid'] is None:
        SETTINGS['ws']['master_uuid'] = str(uuid.uuid4())
        config_save()
    SERVER_IP = SETTINGS['SERVER_IP'] or get_current_ip()
    logger.remove()
    logger.add(sys.stderr, level=SETTINGS['log_level'])
    logger.success("配置文件初始化完成，Websocket服务需要监听外来连接，如弹出防火墙提示，请点击允许访问。")

def main():
    global shock_handler_A, shock_handler_B
    shock_handler_A = ShockHandler(SETTINGS=SETTINGS, DG_CONN = DGConnection, channel_name='A')
    shock_handler_B = ShockHandler(SETTINGS=SETTINGS, DG_CONN = DGConnection, channel_name='B')

    global dispatcher
    dispatcher = Dispatcher()
    for param in SETTINGS['dglab3']['channel_a']['avatar_params']:
        dispatcher.map(param, shock_handler_A.osc_handler)
    for param in SETTINGS['dglab3']['channel_b']['avatar_params']:
        dispatcher.map(param, shock_handler_B.osc_handler)

    th = Thread(target=async_main_wrapper, daemon=True)
    th.start()

    if SETTINGS['general']['auto_open_qr_web_page']:
        import webbrowser
        webbrowser.open_new_tab(f"http://127.0.0.1:{SETTINGS['web_server']['listen_port']}")
    else:
        info_ip = SETTINGS['web_server']['listen_host']
        if info_ip == '0.0.0.0':
            info_ip = get_current_ip()
        logger.success(f"请打开浏览器访问 http://{info_ip}:{SETTINGS['web_server']['listen_port']}")
    app.run(SETTINGS['web_server']['listen_host'], SETTINGS['web_server']['listen_port'], debug=False)

if __name__ == "__main__":
        try:
            config_init()
            main()
        except ConfigFileInited:
            logger.success('配置文件初始化完成，请按需修改后重启程序。')
        logger.info('退出等待60秒 ... 按Ctrl-C立即退出')
        time.sleep(60)