"""第三方渠道统一配置。

所有历史遗留 API 服务商（非 RunningHub 托管画布）的渠道名白名单统一收纳于此。
新增渠道时只需在此处追加平台标识，common 后端补偿扫描与退款保护逻辑会自动覆盖，
禁止在任务查询、补偿扫描或退款判断处散落 `platform == "xxx"` 的枚举。
"""

# 第三方渠道白名单：这些平台的任务由 common 后端统一补偿收敛，且失败不可退款（no_refund）
THIRD_PARTY_PLATFORMS = ("bltcy", "tudou")


def is_third_party_platform(platform: str) -> bool:
    return platform is not None and platform.strip() in set(THIRD_PARTY_PLATFORMS)