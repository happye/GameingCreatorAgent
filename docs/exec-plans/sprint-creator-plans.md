# P050：创作者套餐（本地授权模型）

2026-11-01，Claude Code单Agent。

## 合同

- application/entitlements.py：PLANS（founder/free/creator/pro）、require/require_render/require_package_platform/renders_this_month/summary；EntitlementError。
- CreationJobs.check_entitlement在新任务登记前执行（重复请求不计）：成片额度、同一publication多平台包；server在活动规则、时间线导出、沙箱发布入口检查功能。
- 选择存于.cache/workspace/creations/entitlement.json，billing=none-local-evaluation；GET/POST /api/entitlement。

## 结果

2026-11-01创作者套餐P050已交付（部分，本地授权模型，未接支付）：按总方案§40定义Free/Creator/Creator Pro与默认“创始人验证版”（§42创始人自用，不限）。限制在真实入口生效：Free每月10次成片、同一封面文案只能出1个平台包、不能用活动规则解析/时间线导出；Creator开放活动规则、多平台、100次成片；Pro再开放时间线导出、1000次成片。用量从真实任务记录计（本月提交/完成的成片），重复提交同一请求不重复计；超额或不含的功能返回中文说明。创作页“套餐与用量”可切换（标注本地评估、不涉及付费）。默认创始人版保持现有全部功能不变。3项新测试（规则/计量、真实提交被额度拦截、HTTP功能门禁与非法套餐）+5个浏览器测试补模拟路由，相关27项通过、Ruff/mypy通过；单Agent。仍未做：真实支付/订阅、签名授权文件防篡改、水印、分析分钟计量、具体价格。51项10/40/1≈59%，首产品0/22/0≈50%；人工0/未来9、债务20项11/2/7不变。剩余未开始仅P051企业版。
