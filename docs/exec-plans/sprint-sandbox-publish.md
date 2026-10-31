# P038：自动发布（本机沙箱）

2026-11-01，Claude Code单Agent。

## 合同

- infrastructure/sandbox_publisher.py：target只接受sandbox；真实平台名抛PermissionError；localChecks≠pass或publicationEligibility=blocked拒绝；记录独占创建，状态逐次推进并原子替换。
- POST /api/creation/publish {packageJobId,target}先经CreationJobs.package完整核验；GET /api/creation/publish/<id>推进/读取状态；GET ?packageJobId=历史。
- 页面按钮明确“本机模拟，不上传”。

## 结果

2026-11-01自动发布P038已交付（部分，仅本机沙箱）：发布包结果区新增“沙箱发布（本机模拟，不上传）”，先重新核验发布包文件与收据，再检查本地限值必须通过且未被标记blocked（如test_only音乐），然后在.cache/workspace/publishing记录一条模拟发布并按“已提交→处理中→已发布（模拟）”推进，每步带时间，可按编号查状态、按发布包查历史。目标填抖音/快手/B站/小红书等真实平台会被明确拒绝：需要官方开放接口、账号授权和你的明确同意，现阶段不连接任何平台、不上传任何文件。真实guide模式发布包沙箱发布到“已发布（模拟）”，真实平台目标被拒绝。5项测试（生命周期持久化、真实平台/未知目标/本地检查失败/blocked均拒绝且不留记录、路径校验）及包相关回归共15项通过、Ruff/mypy通过；单Agent。51项10/39/2≈58%，首产品0/22/0≈50%；人工0/未来9、债务20项11/2/7不变。剩余未开始仅P050创作者套餐、P051企业版。
