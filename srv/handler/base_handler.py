from loguru import logger
import asyncio

class BaseHandler():
    
    @staticmethod
    def param_sanitizer(param):
        try:
            param = param[0]
        except:
            pass
        if isinstance(param, float):
            param = min(max(param, 0.0), 1.0)
        elif isinstance(param, int):
            param = min(max(param, 0), 1)
        elif isinstance(param, bool):
            param = 1 if param else 0
        else:
            raise ValueError('错误的输入参数类型，仅支持 1~0 之间的 float、int 或 bool。')
        return param

    def osc_handler(self, address, *args):
        # logger.debug(f"VRCOSC: CHANN {self.channel}: {address}: {args}")
        val = self.param_sanitizer(args)
        return asyncio.ensure_future(self._handler(val))