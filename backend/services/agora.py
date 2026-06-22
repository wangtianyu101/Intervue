"""
Agora RTC 实时语音预留接口

未来扩展用，当前使用 WebSocket + 阿里云 ASR/TTS

依赖 (未来):
    pip install agoraAccessToken

文档:
    https://doc.shengwang.cn/doc/rtc/python/python-sdk/prepare
"""

import os
import time
import logging
from typing import Optional

logger = logging.getLogger("codemock.agora")


class AgoraService:
    """Agora RTC 预留接口"""

    def __init__(self, app_id: Optional[str] = None, app_certificate: Optional[str] = None):
        self.app_id = app_id or os.environ.get("AGORA_APP_ID", "")
        self.app_certificate = app_certificate or os.environ.get("AGORA_APP_CERTIFICATE", "")
        self._available = bool(self.app_id and self.app_certificate)

    @property
    def available(self) -> bool:
        return self._available

    def generate_token(self, channel: str, uid: int = 0, ttl: int = 3600) -> str:
        """生成 Agora Token

        Args:
            channel: 频道名
            uid: 用户ID (0 表示自动分配)
            ttl: Token 有效期 (秒)

        Returns:
            JWT Token

        Raises:
            NotImplementedError: 当前未实现，请使用 WebSocket 方案
        """
        if not self.available:
            raise ValueError("Agora not configured (AGORA_APP_ID and AGORA_APP_CERTIFICATE required)")

        # 预留实现 - 未来接入 Agora Token 生成
        # from agora.access_token import AccessToken
        # expiry = int(time.time()) + ttl
        # token = AccessToken(self.app_id, self.app_certificate, channel, uid)
        # token.add_priviledge(AccessToken.Privilege.joinChannel, expiry)
        # return token.dump()

        raise NotImplementedError("TODO: 实现 Agora Token 生成")


# 全局单例
_agora_service: Optional[AgoraService] = None


def get_agora_service() -> AgoraService:
    """获取 Agora 服务单例"""
    global _agora_service
    if _agora_service is None:
        _agora_service = AgoraService()
    return _agora_service
