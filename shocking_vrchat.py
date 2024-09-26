from typing import List
import asyncio
import yaml, uuid, os, sys, traceback, time, socket
from threading import Thread
from loguru import logger
import traceback
import copy

from flask import Flask, render_template, redirect
from websockets.server import serve as wsserve

import srv
from srv.connector.coyotev3ws import DGWSMessage, DGConnection
from srv.handler.shock_handler import ShockHandler
from srv.handler.machine_handler import TuyaHandler, TuYaConnection

from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.dispatcher import Dispatcher

app = Flask(__name__)

CONFIG_FILE_VERSION  = 'v0.2'
CONFIG_FILENAME = f'settings-advanced-{CONFIG_FILE_VERSION}.yaml'
CONFIG_FILENAME_BASIC = f'settings-{CONFIG_FILE_VERSION}.yaml'
SETTINGS_BASIC = {
    'dglab3':{
        'channel_a': {
            'avatar_params': [
                '/avatar/parameters/pcs/contact/enterPass',
                '/avatar/parameters/Shock/TouchAreaA',
                '/avatar/parameters/Shock/TouchAreaC',
                '/avatar/parameters/Shock/wildcard/*',
            ],
            'mode': 'distance',
            'strength_limit': 100,
        },
        'channel_b': {
            'avatar_params': [
                '/avatar/parameters/lms-penis-proximityA*',
                '/avatar/parameters/Shock/TouchAreaB',
                '/avatar/parameters/Shock/TouchAreaC',
            ],
            'mode': 'distance',
            'strength_limit': 100,
        }
    },
    'version': CONFIG_FILE_VERSION,
}
SETTINGS = {
    'SERVER_IP': None,
    'dglab3': {
        'channel_a': {
            'mode_config':{
                'shock': {
                    'duration': 2,
                    'wave': '["0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464"]',
                },
                'distance': {
                    'freq_ms': 10,
                },
                'trigger_range': {
                    'bottom': 0.0,
                    'top': 1.0,
                },
            }
        },
        'channel_b': {
            'mode_config':{
                'shock': {
                    'duration': 2,
                    'wave': '["0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464"]',
                },
                'distance': {
                    'freq_ms': 10,
                },
                'trigger_range': {
                    'bottom': 0.0,
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

def strip_basic_settings(settings: dict):
    ret = copy.deepcopy(settings)
    for chann in ['channel_a', 'channel_b']:
        del ret['dglab3'][chann]['avatar_params']
        del ret['dglab3'][chann]['mode'] 
        del ret['dglab3'][chann]['strength_limit'] 
    return ret

@app.route('/api/v1/config', methods=['GET', 'HEAD', 'OPTIONS'])
def get_config():
    return {
        'basic': SETTINGS_BASIC,
        'advanced': strip_basic_settings(SETTINGS),
    }

@app.route('/api/v1/config', methods=['POST'])
def update_config():
    # TODO: Hot apply settings
    err = {
        'success': False,
        'message': "Some error",
    }
    return {
        'success': True,
        'need_restart': False,
        'message': "Some Message, like, Please restart."
    }

async def wshandler(connection):
    client = DGConnection(connection, SETTINGS=SETTINGS)
    await client.serve()

async def async_main():
    for handler in handlers:
        handler.start_background_jobs()
    try: 
        server = AsyncIOOSCUDPServer((SETTINGS["osc"]["listen_host"], SETTINGS["osc"]["listen_port"]), dispatcher, asyncio.get_event_loop())
        transport, protocol = await server.create_serve_endpoint()
        # await wsserve(wshandler, "127.0.0.1", 8765)
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error("OSC UDP Recevier listen failed.")
        logger.error("OSC监听失败，可能存在端口冲突")
        return
    try: 
        async with wsserve(wshandler, SETTINGS['ws']["listen_host"], SETTINGS['ws']["listen_port"]):
            await asyncio.Future()  # run forever
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error("Websocket server listen failed.")
        logger.error("WS服务监听失败，可能存在端口冲突")
        return

    transport.close()

def async_main_wrapper():
    """Not async Wrapper around async_main to run it as target function of Thread"""
    asyncio.run(async_main())

def config_save():
    with open(CONFIG_FILENAME, 'w', encoding='utf-8') as fw:
        yaml.safe_dump(SETTINGS, fw, allow_unicode=True)
    with open(CONFIG_FILENAME_BASIC, 'w', encoding='utf-8') as fw:
        yaml.safe_dump(SETTINGS_BASIC, fw, allow_unicode=True)

class ConfigFileInited(Exception):
    pass

def config_init():
    logger.info(f'Init settings..., Config filename: {CONFIG_FILENAME_BASIC} {CONFIG_FILENAME}, Config version: {CONFIG_FILE_VERSION}.')
    global SETTINGS, SETTINGS_BASIC, SERVER_IP
    if not (os.path.exists(CONFIG_FILENAME) and os.path.exists(CONFIG_FILENAME_BASIC)):
        SETTINGS['ws']['master_uuid'] = str(uuid.uuid4())
        config_save()
        raise ConfigFileInited()

    with open(CONFIG_FILENAME, 'r', encoding='utf-8') as fr:
        SETTINGS = yaml.safe_load(fr)
    with open(CONFIG_FILENAME_BASIC, 'r', encoding='utf-8') as fr:
        SETTINGS_BASIC = yaml.safe_load(fr)

    if SETTINGS.get('version', None) != CONFIG_FILE_VERSION or SETTINGS_BASIC.get('version', None) != CONFIG_FILE_VERSION:
        logger.error(f"Configuration file version mismatch! Please delete the {CONFIG_FILENAME_BASIC} and {CONFIG_FILENAME} files and run the program again to generate the latest version of the configuration files.")
        raise Exception(f'配置文件版本不匹配！请删除 {CONFIG_FILENAME_BASIC} {CONFIG_FILENAME} 文件后再次运行程序，以生成最新版本的配置文件。')
    if SETTINGS['ws']['master_uuid'] is None:
        SETTINGS['ws']['master_uuid'] = str(uuid.uuid4())
        config_save()
    SERVER_IP = SETTINGS['SERVER_IP'] or get_current_ip()

    for chann in ['channel_a', 'channel_b']:
        SETTINGS['dglab3'][chann]['avatar_params'] = SETTINGS_BASIC['dglab3'][chann]['avatar_params']
        SETTINGS['dglab3'][chann]['mode'] = SETTINGS_BASIC['dglab3'][chann]['mode']
        SETTINGS['dglab3'][chann]['strength_limit'] = SETTINGS_BASIC['dglab3'][chann]['strength_limit']

    logger.remove()
    logger.add(sys.stderr, level=SETTINGS['log_level'])
    logger.success("The configuration file initialization is complete. The WebSocket service needs to listen for incoming connections. If a firewall prompt appears, please click Allow Access.")
    logger.success("配置文件初始化完成，Websocket服务需要监听外来连接，如弹出防火墙提示，请点击允许访问。")

def main():
    global dispatcher, handlers
    dispatcher = Dispatcher()
    handlers = []

    for chann in ['A', 'B']:
        config_chann_name = f'channel_{chann.lower()}'
        chann_mode = SETTINGS['dglab3'][config_chann_name]['mode']
        shock_handler = ShockHandler(SETTINGS=SETTINGS, DG_CONN = DGConnection, channel_name=chann)
        handlers.append(shock_handler)
        for param in SETTINGS['dglab3'][config_chann_name]['avatar_params']:
            logger.success(f"Channel {chann} Mode：{chann_mode} Listening：{param}")
            dispatcher.map(param, shock_handler.osc_handler)
    
    TuyaConn = TuYaConnection(
        access_id=SETTINGS['machine']['tuya']['access_id'],
        access_key=SETTINGS['machine']['tuya']['access_key'],
        device_ids=SETTINGS['machine']['tuya']['device_ids'],
    )
    machine_tuya_handler = TuyaHandler(SETTINGS=SETTINGS, DEV_CONN=TuyaConn)
    handlers.append(machine_tuya_handler)
    for param in SETTINGS['machine']['tuya']['avatar_params']:
        logger.success(f"Machine Listening：{param}")
        dispatcher.map(param, machine_tuya_handler.osc_handler)


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
        logger.success('The configuration file initialization is complete. Please modify it as needed and restart the program.')
        logger.success('配置文件初始化完成，请按需修改后重启程序。')
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error("Unexpected Error.")
    logger.info('Exiting in 60 seconds ... Press Ctrl-C to exit immediately')
    logger.info('退出等待60秒 ... 按Ctrl-C立即退出')
    time.sleep(60)