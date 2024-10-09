import time
from loguru import logger
from tuya_connector import (
	TuyaOpenAPI,
	TuyaOpenPulsar,
	TuyaCloudPulsarTopic,
)

class TuYaConnection():
    def __init__(
            self, 
            access_id: str, 
            access_key: str, 
            device_ids: list, 
            api_endpoint= "https://openapi.tuyacn.com", 
            mq_endpoint="wss://mqe.tuyacn.com:8285/", 
            cmd_gap=0.2,
        ) -> None:
        self.tyapi = TuyaOpenAPI(api_endpoint, access_id, access_key)
        self.tyapi.connect()
        self.last_cmd_time = 0
        self.cmd_gap = cmd_gap
        self.device_ids = device_ids
        self.mq_endpoint = mq_endpoint
        self.set_switch(True)
        self.current_level = 1
    
    def __del__(self):
        self.set_switch(False)

    async def sendcmd(self, code, value):
        curr_time = time.time()
        if curr_time - self.last_cmd_time < self.cmd_gap and code in ['level', 'mode']:
            logger.debug(f"Skip cmd: {code}:{value}")
        for device_id in self.device_ids:
            resp = self.tyapi.post(f"/v1.0/iot-03/devices/{device_id}/commands", {"commands":[{"code":code,"value":value}]})
            logger.success(f"{device_id}:{code}:{value}")
            if resp.get('success') != True:
                logger.error(f"{resp}")

    def sendcmd_sync(self, code, value):
        curr_time = time.time()
        if curr_time - self.last_cmd_time < self.cmd_gap and code in ['level', 'mode']:
            logger.debug(f"Skip cmd: {code}:{value}")
        for device_id in self.device_ids:
            resp = self.tyapi.post(f"/v1.0/iot-03/devices/{device_id}/commands", {"commands":[{"code":code,"value":value}]})
            logger.success(f"{device_id}:{code}:{value}")
            if resp.get('success') != True:
                logger.error(f"{resp}")
    
    def set_switch(self, switch:bool=True):
        self.sendcmd_sync('switch', switch)

    async def set_level(self, level:int=1):
        if level == 0:
            # await self.sendcmd('level', f"level_{level}")
            # self.current_level = 1
            # self.set_switch(False)
            # self.current_level = 0
            level = 1
        # else:
            # if self.current_level == 0 :
            #     self.set_switch(True)

        await self.sendcmd('level', f"level_{level}")
        self.current_level = level

    async def set_mode(self, mode:str='A'):
        await self.sendcmd('mode', f"level_{mode}")
    

        