from loguru import logger
import asyncio

# 基础处理器类，提供通用的 OSC 参数处理方法
class BaseHandler():
    
    @staticmethod
    def param_sanitizer(param):
        """
        静态方法，用于清理和规范化接收到的 OSC 参数。
        确保参数值在 0 到 1 的范围内。

        Args:
            param: 从 OSC 接收到的原始参数 (通常是包含单个元素的元组或列表)。

        Returns:
            float 或 int: 规范化后的参数值 (0 到 1)。

        Raises:
            ValueError: 如果参数类型不是 float, int 或 bool。
        """
        try:
            # OSC 参数通常包装在一个元组或列表中，尝试提取第一个元素
            param = param[0]
        except (IndexError, TypeError):
            # 如果提取失败（例如参数为空或不是序列），则忽略
            pass

        if isinstance(param, float):
            # 如果是浮点数，限制在 [0.0, 1.0] 范围内
            param = min(max(param, 0.0), 1.0)
        elif isinstance(param, int):
            # 如果是整数，也限制在 [0, 1] 范围内 (通常用于 bool 转换后的值)
            param = min(max(param, 0), 1)
        elif isinstance(param, bool):
            # 如果是布尔值，True 转换为 1, False 转换为 0
            param = 1 if param else 0
        else:
            # 其他类型视为无效输入
            raise ValueError('错误的输入参数类型，仅支持 1~0 之间的 float、int 或 bool。')
        return param

    def osc_handler(self, address, *args):
        """
        OSC 消息处理入口点。
        由 python-osc 的 Dispatcher 调用。

        Args:
            address (str): 接收到的 OSC 地址。
            *args: 接收到的 OSC 参数列表。
        """
        # logger.debug(f"VRCOSC: CHANN {self.channel}: {address}: {args}") # 可选的调试日志
        # 清理参数
        val = self.param_sanitizer(args)
        # 将具体的处理逻辑 (_handler 方法，由子类实现) 包装成 asyncio Task
        # 确保处理逻辑在事件循环中异步执行，不阻塞 OSC 服务器
        return asyncio.ensure_future(self._handler(val))