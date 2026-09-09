# 高德 Web 服务接入

本适配器读取 POI、步行路线和天气预报，供后续真实 Agent 查询使用。它不生成行程，也不能证明票价或营业状态。协议依据于 2026-09-09 阅读的高德官方文档；测试数据为合成协议样例，不证明线上数据准确性。

## 申请与配置

1. 登录[高德开放平台控制台](https://console.amap.com/dev/key/app)，没有开发者账号时先注册。
2. 在「应用管理」选择「创建新应用」，名称可填「智能旅行规划（本地开发）」。
3. 选择该应用，点击「添加 Key」，服务平台选择 **Web 服务**。
4. 将密钥保存到忽略版本控制的 `backend/.env`：`AMAP_WEB_SERVICE_KEY=你的密钥`。不要写入前端 `VITE_*` 变量、截图、测试样例或提交记录。

申请流程依据[创建应用和 Key](https://lbs.amap.com/api/webservice/create-project-and-key)。如果控制台要求实名认证，按当前页面完成。权限、调用额度和是否需要开通服务，以该账号控制台显示为准；这里不承诺免费配额。JavaScript API Key 不能替代 Web 服务 Key；平台不匹配会返回 `10009`。

## 接口与归一化

| 方法 | 官方接口 | 请求与结果约定 |
| --- | --- | --- |
| `search_pois(city, keywords, *, types=None)` | [`/v3/place/text`](https://lbs.amap.com/api/webservice/guide/api/search) | `citylimit=true` 限定城市，`extensions=all` 获取行政区码，读取第一页最多 20 项。`types` 可传六位分类码（多个用 `|` 分隔），不传时维持无类别限制。返回 `pois`，每项包含 `id/name/location/adcode/typecode`。 |
| `poi_details(poi_id)` | [`/v3/place/detail`](https://lbs.amap.com/api/webservice/guide/api/search) | 按真实 POI ID 查询，结果仍为 `pois` 列表；有时需要另开高级权限。有返回的营业时间文本可保留，但不证明行程当天营业。 |
| `walking_route(origin, destination)` | [`/v3/direction/walking`](https://lbs.amap.com/api/webservice/guide/api/direction) | 起终点格式为「经度,纬度」，最多六位小数。返回首个方案的 `distance_meters/duration_seconds` 及所有方案的距离、时间。接口最长支持 100 km 范围内步行规划。 |
| `weather_forecast(city)` | [`/v3/weather/weatherInfo`](https://lbs.amap.com/api/webservice/guide/api/weatherinfo) | `city` 必须是六位行政区码，`extensions=all` 请求预报。返回 `forecasts[].casts[]`，日期范围完全保留上游数据，不补齐到七天。 |

返回结果附带 `source=amap`、不含查询凭证的 `source_url`、UTC `fetched_at/expires_at`、来源 `status`、中文 `summary` 和限制说明。来源 TTL 为 POI 24 小时、详情 6 小时、天气及路线 30 分钟；这是应用采用的有效期，不是供应商准确性保证。天气另保留上游 `report_time`；抓取时间不能代替数据发布时间。空列表保持为空；缺少的字符串字段或官方以 `[]` 表示的未知值归一化为 `null`。实时营业状态和门票价格始终未知；餐饮或景区的平均消费不能转换成门票报价。

步行结果的 `polyline` 只拼接上游 `steps[].polyline` 并去重相邻步骤端点；没有几何信息时为 `null`，不以直线冒充步行路线。

规划景点使用 `types="110000"`（风景名胜），住宿使用 `types="100000"`（住宿服务），并根据真实返回的 `typecode` 再筛选 `11`/`10` 前缀。缺失或空数组的类型码归一化为 `null`，不能根据名称猜成景点；交通设施 `15` 和地名地址 `19` 不能进入景点安排。天气查询的城市定位保留不限制类别的查询方式。分类依据于 2026-09-09 下载核验的[官方 POI 分类编码表](https://lbs.amap.com/api/webservice/download)（表内版本 V1.06，2023-02-08），没有新增付费重试或额外查询。

## 行程确定性校验

`app/services/plan_validation.py` 的 `validate_plan(request, collected, amap)` 消费真实 Agent 收集的数据，输出 `plan/validation/budget`。日期须完整有序，每日 1–6 项活动须位于确认的时间窗口内且不得重叠；虚构景点/酒店 ID、跨城或非大陆地点会返回 `PLAN_INVALID`。同城归属按真实行政区码校验，允许同城不同区，允许景点跨日重游。

相邻活动按真实步行时间加显式 10 分钟缓冲计算最早到达。全程路线查询最多 3 并发、8 秒总预算，保留调用方 10 秒校验阶段的收尾时间；相同起终点在本次校验内复用结果。无法查询、返回不完整或证据过期均标记 `unknown`，不能填成 0；来不及衔接则标记 `conflict`。

来源到达 `expires_at` 即为 `stale`；过期路线不能算已验证，过期、跨城、超日期范围或异常温度的天气返回 `null`。真实预报的暴雨等恶劣天气产生风险提示。原始营业时间文本不足以证明指定日期开放，因此活动仍明确标记 `opening_status=unknown`。游览时长是建议，所有票价、餐饮、市内交通及住宿报价均保持未知，预算 `pricing_status=not_calculated`；不会声称满足预算。

## 错误与验证

HTTP 200 仍需检查 `status/info/infocode`。2026-09-09 的真实步行接口返回 `info="ok"`，与文档中的大写 `OK` 不同，因此成功状态兼容这两种大小写，仍严格校验 `status="1"` 和成功错误码。依据[官方错误码](https://lbs.amap.com/api/webservice/guide/tools/info)，适配器区分未配置、权限失败、配额耗尽、限流、超时、无路线、参数错误和响应异常。配额耗尽不自动重试；暂时限流或服务失败标记可重试，适配器本身不会自动重发。

请求固定使用 `https://restapi.amap.com`，关闭重定向，超时由注入的 `httpx.AsyncClient` 控制。错误消息不含原始 URL、密钥或上游诊断正文；`httpx/httpcore` 请求日志对 `key` 查询参数脱敏。

在 `backend/` 激活虚拟环境后运行 `python -m pytest tests/test_amap_provider.py tests/test_plan_validation.py`。测试覆盖请求参数、成功与空数据、配额权限、超时、重定向、异常格式、凭证脱敏，以及行程日期/地点/时间约束、到达冲突、过期边界和未知费用。线上可用性必须使用用户配置的真实密钥另行验证。
