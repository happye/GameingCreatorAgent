# 持久平台包队列

范围：按用户选定的1–4个唯一平台顺序调用既有单包任务；不改套餐、费用、Hook/CTA或成片时长。

验收：固定requestId幂等；请求schema及whole-file SHA256绑定项目、发布回执和完整有序profile；OS owner证明运行，GET/启动不自动恢复；显式resume恢复同batch，完成包核验复用，中断子任务保留历史后新增attempt，failed不自动重试；cancel停止后续，当前FFmpeg完成并保留产物，返回后不提交下一项。同发布的查询复用与submit共用独立发布锁，避免跨batch重复提交。

接口：POST /api/creation/package-batches；GET同路径以projectId、publicationJobId列出；GET /<batchId>?projectId；POST /<batchId>/resume、/cancel仅接收projectId。submit/resume/cancel返回snapshot。

实现：独立batches目录，注册/owner/短状态锁与creation根锁分离；原子state（整体schema + SHA256封装，每次读取校验）；持久childRequestId先于submit，恢复注册窗口读取既有child；所有包沿用现有get/verify及权限。

验证：Ruff及mypy定向；不运行pytest、模型、安装、上传。真实pub598a72a7f4164c3fba2ff8e234081681、FFmpeg与进程重启由主控集成验收；未据此改人评或passes。工作树env缺venv时显式使用主树.venv并设置本树PYTHONPATH，避免系统Python缺ruff。
