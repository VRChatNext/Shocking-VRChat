from typing import List
import asyncio
import yaml, uuid, os, sys, traceback, time, socket, re, json
from threading import Thread
from loguru import logger
import traceback
import copy

from flask import Flask, render_template, redirect, request, jsonify
from websockets.server import serve as wsserve

import srv
from srv.connector.coyotev3ws import DGWSMessage, DGConnection
from srv.handler.shock_handler import ShockHandler
from srv.handler.machine_handler import TuyaHandler, TuYaConnection

from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.dispatcher import Dispatcher

# Flask 应用实例
app = Flask(__name__)

# 配置文件版本和文件名常量
CONFIG_FILE_VERSION  = 'v0.2'
CONFIG_FILENAME = f'settings-advanced-{CONFIG_FILE_VERSION}.yaml'
CONFIG_FILENAME_BASIC = f'settings-{CONFIG_FILE_VERSION}.yaml'

# 基础配置文件 (settings-vX.X.yaml) 的默认内容
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
                '/avatar/parameters/pcs/contact/enterPass',
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

# 进阶配置文件 (settings-advanced-vX.X.yaml) 的默认内容
SETTINGS = {
    'SERVER_IP': None, # 服务器IP, None 时自动检测
    'dglab3': {
        'channel_a': {
            'mode_config':{
                'shock': { # 电击模式配置
                    'duration': 2, # 持续时间（秒）
                    'wave': '["0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464"]', # 电击波形
                },
                'distance': { # 距离模式配置
                    'freq_ms': 10, # 波形频率（毫秒）
                },
                'trigger_range': { # 触发阈值配置 (所有模式)
                    'bottom': 0.0, # 下界 (低于视为0%)
                    'top': 1.0,    # 上界 (超过视为100%)
                },
                'touch': { # 触摸模式配置
                    'freq_ms': 10, # 波形频率（毫秒）
                    'n_derivative': 1, # 使用哪个导数: 0=距离, 1=速度, 2=加速度, 3=冲击力
                    'derivative_params': [ # 各导数的归一化参数
                        {"top": 1, "bottom": 0}, # 距离
                        {"top": 5, "bottom": 0}, # 速度
                        {"top": 50, "bottom": 0}, # 加速度
                        {"top": 500, "bottom": 0}, # 冲击力
                    ]
                },
            }
        },
        'channel_b': { # B 通道配置，与 A 通道类似
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
                'touch': {
                    'freq_ms': 10,
                    'n_derivative': 1,
                    'derivative_params': [
                        {"top": 1, "bottom": 0},
                        {"top": 5, "bottom": 0},
                        {"top": 50, "bottom": 0},
                        {"top": 500, "bottom": 0},
                    ]
                },
            }
        },
    },
    'ws':{ # Websocket 服务配置 (用于 DG-LAB APP 连接)
        'master_uuid': None, # 控制端 UUID, 首次启动自动生成
        'listen_host': '0.0.0.0', # 监听地址
        'listen_port': 28846  # 监听端口
    },
    'osc':{ # OSC 服务配置 (用于接收 VRChat 数据)
        'listen_host': '127.0.0.1', # 监听地址
        'listen_port': 9001, # 监听端口
    },
    'web_server':{ # Web 服务器配置 (用于显示二维码)
        'listen_host': '127.0.0.1', # 监听地址
        'listen_port': 8800 # 监听端口
    },
    'log_level': 'INFO', # 日志级别
    'version': CONFIG_FILE_VERSION, # 配置文件版本
    'general': { # 通用配置
        'auto_open_qr_web_page': True, # 启动时自动打开二维码网页
        'local_ip_detect': { # 本地 IP 检测配置
            'host': '223.5.5.5', # 用于检测的服务器地址
            'port': 80, # 用于检测的服务器端口
        }
    }
}
# 全局变量，存储检测到的或手动设置的服务器 IP
SERVER_IP = None

# Flask 路由: 获取本机 IP 地址
@app.route('/get_ip')
def get_current_ip():
    """
    尝试连接到一个公共服务器以获取本机在局域网中的 IP 地址。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((SETTINGS['general']['local_ip_detect']['host'], SETTINGS['general']['local_ip_detect']['port']))
    client_ip = s.getsockname()[0]
    s.close()
    return client_ip

# Flask 路由: 根路径重定向到二维码页面
@app.route("/")
def web_index():
    return redirect("/qr", code=302)

# Flask 路由: 显示用于 DG-LAB APP 扫码连接的二维码
@app.route("/qr")
def web_qr():
    """
    渲染二维码页面，二维码内容包含 WebSocket 连接地址和 Master UUID。
    """
    return render_template('tiny-qr.html', content=f'https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#ws://{SERVER_IP}:{SETTINGS["ws"]["listen_port"]}/{SETTINGS["ws"]["master_uuid"]}')

# Flask 路由: (调试用) 获取当前 WebSocket 连接列表
@app.route('/conns')
def get_conns():
    return str(srv.WS_CONNECTIONS)

# Flask 路由: (调试用) 发送测试波形
@app.route('/sendwav')
async def sendwav():
    # 注意: srv.waveData 可能未定义
    await DGConnection.broadcast_wave(channel='A', wavestr=srv.waveData[0])
    return 'OK'

# Flask 请求后钩子: 如果请求带有 ?ret=status 参数，将响应内容替换为状态信息
@app.after_request
async def after_request_hook(response):
    if request.args.get('ret') == 'status' and response.status_code == 200:
        response = jsonify(await api_v1_status())
    return response

# 自定义异常：客户端不允许（例如，非 VRChat 客户端）
class ClientNotAllowed(Exception):
    pass

# Flask 错误处理器: 处理 ClientNotAllowed 异常
@app.errorhandler(ClientNotAllowed)
def hendle_ClientNotAllowed(e):
    return {
        "error": "Client not allowed."
    }, 401

# Flask 错误处理器: 处理其他未捕获的异常
@app.errorhandler(Exception)
def handle_Exception(e):
    return {
        "error": str(e)
    } , 500

# --- API V1 路由 ---

# 装饰器: 检查 User-Agent，仅允许来自 VRChat (UnityPlayer) 的请求
def allow_vrchat_only(func):
    async def wrapper(*args, **kwargs):
        ua = request.headers.get('User-Agent')
        if 'UnityPlayer' not in ua:
            raise ClientNotAllowed
        if 'NSPlayer' in ua or 'WMFSDK' in ua:
            raise ClientNotAllowed
        return await func(*args, **kwargs)
    # 更新 wrapper 的元信息，以便 Flask 能正确识别
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper

# API 路由: 获取当前服务状态和连接的设备信息
@app.route('/api/v1/status')
async def api_v1_status():
    """
    返回服务的健康状态和已连接设备（Coyote, Tuya 等）的列表及属性。
    """
    return {
        'healthy': 'ok',
        'devices': [
            # 列出已连接的 Coyote 设备及其强度和 UUID
            *[{"type": 'shock', 'device':'coyotev3', 'attr': {'strength':conn.strength, 'uuid':conn.uuid}} for conn in srv.WS_CONNECTIONS],
            # TODO: 列出已连接的 Tuya 设备
            *[{"type": 'machine', 'device':'tuya', 'attr': {}} for conn in []],
        ]
    }

# API 路由: 触发指定通道的电击
@app.route('/api/v1/shock/<channel>/<second>', endpoint='api_v1_shock')
@allow_vrchat_only
async def api_v1_shock(channel, second):
    """
    通过 API 触发指定通道 (A, B 或 all) 的固定波形电击，持续指定秒数。
    """
    if channel == 'all':
        channels = ['A', 'B']
    else:
        channels = [channel]
    try:
        second = float(second)
    except Exception:
        logger.warning('[API][shock] Invalid second, set to 1.')
        second = 1.0
    second = min(second, 10.0)
    repeat = int(10 * second)
    for _ in range(repeat // 10):
        for chan in channels:
            await api_v1_sendwave(chan, 10, '0A0A0A0A64646464')
    if repeat % 10 > 0:
        for chan in channels:
            await api_v1_sendwave(chan, repeat % 10, '0A0A0A0A64646464')
    return {'result': 'OK'}

# API 路由: 发送自定义波形数据
@app.route('/api/v1/sendwave/<channel>/<repeat>/<wavedata>', endpoint='api_v1_sendwave')
@allow_vrchat_only
async def api_v1_sendwave(channel, repeat, wavedata):
    """
    通过 API 发送自定义的 Coyote V3 波形片段。

    参数:
    channel -- 通道 (A 或 B)
    repeat -- 波形片段重复次数 (1-100, 每次重复代表 100ms)
    wavedata -- 16 进制波形片段 (如 0A0A0A0A64646464)
    """
    try:
        channel = channel.upper()
        if channel not in ['A', 'B']:
            raise Exception
    except:
        logger.warning('[API][sendwave] Invalid Channel, set to A.')
        channel = 'A'
    try:
        repeat = int(repeat)
        if repeat > 100 or repeat < 1:
            raise Exception
    except:
        logger.warning('[API][sendwave] Invalid repeat times, set to 10.')
        repeat = 10
    try:
        if not re.match(r'^([0-9A-F]{16})$', wavedata):
            raise Exception
    except:
        logger.warning('[API][sendwave] Invalid wave, set to 0A0A0A0A64646464.')
        wavedata = '0A0A0A0A64646464'
    wavestr = [wavedata for _ in range(repeat)]
    wavestr = json.dumps(wavestr, separators=(',', ':'))
    logger.success(f'[API][sendwave] C:{channel} R:{repeat} W:{wavedata}')
    await DGConnection.broadcast_wave(channel=channel, wavestr=wavestr)
    return {'result': 'OK'}

# 辅助函数: 从完整的配置字典中剥离基础配置部分
def strip_basic_settings(settings: dict) -> dict:
    """
    创建一个配置字典的副本，并移除基础配置中包含的字段，
    以便在 API 中仅返回进阶配置。
    """
    ret = copy.deepcopy(settings)
    for chann in ['channel_a', 'channel_b']:
        del ret['dglab3'][chann]['avatar_params']
        del ret['dglab3'][chann]['mode']
        del ret['dglab3'][chann]['strength_limit']
    return ret

# API 路由: 获取当前配置信息
@app.route('/api/v1/config', methods=['GET', 'HEAD', 'OPTIONS'])
def get_config():
    """
    返回当前加载的基础配置和进阶配置。
    """
    return {
        'basic': SETTINGS_BASIC,
        'advanced': strip_basic_settings(SETTINGS),
    }

# API 路由: 更新配置信息 (TODO: 未实现)
@app.route('/api/v1/config', methods=['POST'])
def update_config():
    """
    (占位符) 用于通过 API 更新配置。需要实现热重载逻辑。
    """
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

# --- WebSocket 和 OSC 服务 ---

# WebSocket 连接处理器
async def wshandler(connection):
    """
    处理新的 WebSocket 连接 (来自 DG-LAB APP)。
    为每个连接创建一个 DGConnection 实例来管理通信。
    """
    client = DGConnection(connection, SETTINGS=SETTINGS)
    await client.serve()

# 主异步函数
async def async_main():
    """
    启动 OSC 服务器和 WebSocket 服务器。
    """
    # 启动所有 Handler 的后台任务
    for handler in handlers:
        handler.start_background_jobs()
    try:
        server = AsyncIOOSCUDPServer((SETTINGS["osc"]["listen_host"], SETTINGS["osc"]["listen_port"]), dispatcher, asyncio.get_event_loop())
        logger.success(f'OSC Listening: {SETTINGS["osc"]["listen_host"]}:{SETTINGS["osc"]["listen_port"]}')
        transport, protocol = await server.create_serve_endpoint()
        # await wsserve(wshandler, "127.0.0.1", 8765) # 调试用
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

# 异步主函数的同步包装器
def async_main_wrapper():
    """
    用于在单独的线程中运行 asyncio 事件循环。
    """
    asyncio.run(async_main())

# --- 配置文件的加载与初始化 ---

# 保存当前配置到文件
def config_save():
    """
    将当前的 SETTINGS 和 SETTINGS_BASIC 字典保存到对应的 YAML 文件中。
    """
    with open(CONFIG_FILENAME, 'w', encoding='utf-8') as fw:
        yaml.safe_dump(SETTINGS, fw, allow_unicode=True)
    with open(CONFIG_FILENAME_BASIC, 'w', encoding='utf-8') as fw:
        yaml.safe_dump(SETTINGS_BASIC, fw, allow_unicode=True)

# 自定义异常：表示配置文件是首次生成
class ConfigFileInited(Exception):
    """当配置文件首次被创建时抛出此异常。"""
    pass

# 初始化配置：加载或创建配置文件
def config_init():
    """
    检查配置文件是否存在：
    - 如果不存在，则使用默认值创建新的配置文件，并抛出 ConfigFileInited 异常。
    - 如果存在，则加载配置文件内容到 SETTINGS 和 SETTINGS_BASIC 字典。
    同时进行版本检查、UUID 生成和日志配置。
    """
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

    # 检查配置文件版本
    if SETTINGS.get('version', None) != CONFIG_FILE_VERSION or SETTINGS_BASIC.get('version', None) != CONFIG_FILE_VERSION:
        logger.error(f"Configuration file version mismatch! Please delete the {CONFIG_FILENAME_BASIC} and {CONFIG_FILENAME} files and run the program again to generate the latest version of the configuration files.")
        raise Exception(f'配置文件版本不匹配！请删除 {CONFIG_FILENAME_BASIC} {CONFIG_FILENAME} 文件后再次运行程序，以生成最新版本的配置文件。')
    # 检查并生成 master_uuid
    if SETTINGS['ws']['master_uuid'] is None:
        SETTINGS['ws']['master_uuid'] = str(uuid.uuid4())
        config_save()
    # 获取服务器 IP
    SERVER_IP = SETTINGS['SERVER_IP'] or get_current_ip()

    # 合并基础配置到主配置
    for chann in ['channel_a', 'channel_b']:
        SETTINGS['dglab3'][chann]['avatar_params'] = SETTINGS_BASIC['dglab3'][chann]['avatar_params']
        SETTINGS['dglab3'][chann]['mode'] = SETTINGS_BASIC['dglab3'][chann]['mode']
        SETTINGS['dglab3'][chann]['strength_limit'] = SETTINGS_BASIC['dglab3'][chann]['strength_limit']

    # 配置日志记录器
    logger.remove()
    logger.add(sys.stderr, level=SETTINGS['log_level'])
    logger.success("The configuration file initialization is complete. The WebSocket service needs to listen for incoming connections. If a firewall prompt appears, please click Allow Access.")
    logger.success("配置文件初始化完成，Websocket服务需要监听外来连接，如弹出防火墙提示，请点击允许访问。")

# --- 主程序入口 ---

def main():
    """
    程序主逻辑：
    1. 初始化 OSC 调度器 (Dispatcher)。
    2. 根据配置创建并注册 OSC 消息处理器 (ShockHandler, TuyaHandler)。
    3. 在单独的线程中启动异步服务 (OSC, WebSocket)。
    4. 启动 Flask Web 服务器 (用于显示二维码和提供 API)。
    """
    global dispatcher, handlers # 声明为全局变量，以便在 async_main 中访问
    dispatcher = Dispatcher()
    handlers = [] # 存储所有处理器实例

    # 初始化并注册 DG-LAB Coyote 的处理器
    for chann in ['A', 'B']:
        config_chann_name = f'channel_{chann.lower()}'
        chann_mode = SETTINGS['dglab3'][config_chann_name]['mode']
        shock_handler = ShockHandler(SETTINGS=SETTINGS, DG_CONN = DGConnection, channel_name=chann)
        handlers.append(shock_handler)
        # 映射 OSC 参数
        for param in SETTINGS['dglab3'][config_chann_name]['avatar_params']:
            logger.success(f"Channel {chann} Mode：{chann_mode} Listening：{param}")
            dispatcher.map(param, shock_handler.osc_handler)

    # 初始化并注册 Tuya 设备的处理器 (如果配置存在)
    if 'machine' in SETTINGS and 'tuya' in SETTINGS['machine']:
        TuyaConn = TuYaConnection(
            access_id=SETTINGS['machine']['tuya']['access_id'],
            access_key=SETTINGS['machine']['tuya']['access_key'],
            device_ids=SETTINGS['machine']['tuya']['device_ids'],
        )
        machine_tuya_handler = TuyaHandler(SETTINGS=SETTINGS, DEV_CONN=TuyaConn)
        handlers.append(machine_tuya_handler)
        # 映射 OSC 参数
        for param in SETTINGS['machine']['tuya']['avatar_params']:
            logger.success(f"Machine Listening：{param}")
            dispatcher.map(param, machine_tuya_handler.osc_handler)


    # 在后台线程中启动异步服务
    th = Thread(target=async_main_wrapper, daemon=True)
    th.start()

    # 根据配置决定是否自动打开二维码网页
    if SETTINGS['general']['auto_open_qr_web_page']:
        import webbrowser
        webbrowser.open_new_tab(f"http://127.0.0.1:{SETTINGS['web_server']['listen_port']}")
    else:
        # 手动提示用户访问
        info_ip = SETTINGS['web_server']['listen_host']
        if info_ip == '0.0.0.0':
            info_ip = get_current_ip()
        logger.success(f"请打开浏览器访问 http://{info_ip}:{SETTINGS['web_server']['listen_port']}")
    # 启动 Flask Web 服务器
    app.run(SETTINGS['web_server']['listen_host'], SETTINGS['web_server']['listen_port'], debug=False)

if __name__ == "__main__":
    try:
        config_init() # 初始化配置
        main() # 运行主程序
    except ConfigFileInited:
        # 配置文件是首次生成，提示用户并退出
        logger.success('The configuration file initialization is complete. Please modify it as needed and restart the program.')
        logger.success('配置文件初始化完成，请按需修改后重启程序。')
    except Exception as e:
        # 捕获其他未预料到的顶层错误
        logger.error(traceback.format_exc())
        logger.error("Unexpected Error.")
    # 程序退出前的最后提示
    logger.info('Exiting in 1 seconds ... Press Ctrl-C to exit immediately')
    logger.info('退出等待1秒 ... 按Ctrl-C立即退出')
    time.sleep(1)