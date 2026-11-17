# 持久平台包队列

R2 · P035 / P036 · 2026-11-18 · 已完成真实四平台及恢复流程，内容/平台资格仍未人评。

范围：按用户选定的1–4个唯一平台顺序调用既有单包任务；不改套餐、费用、Hook/CTA或成片时长。

验收：固定requestId幂等；请求schema及whole-file SHA256绑定项目、发布回执和完整有序profile；OS owner证明运行，GET/启动不自动恢复；显式resume恢复同batch，完成包核验复用，中断子任务保留历史后新增attempt，failed不自动重试；cancel停止后续，当前FFmpeg完成并保留产物，返回后不提交下一项。同发布的查询复用与submit共用独立发布锁，避免跨batch重复提交。

接口：POST /api/creation/package-batches；GET同路径以projectId、publicationJobId列出；GET /<batchId>?projectId；POST /<batchId>/resume、/cancel仅接收projectId。submit/resume/cancel返回snapshot。

实现：独立batches目录，注册/owner/短状态锁与creation根锁分离；原子state（整体schema + SHA256封装，每次读取校验）；持久childRequestId先于submit，恢复注册窗口读取既有child；所有包沿用现有get/verify及权限。

验证：Ruff及mypy定向；不运行pytest、模型、安装、上传。真实pub598a72a7f4164c3fba2ff8e234081681、FFmpeg与进程重启由主控集成验收；未据此改人评或passes。工作树env缺venv时显式使用主树.venv并设置本树PYTHONPATH，避免系统Python缺ruff。

主控实证：发布598a72a7f4164c3fba2ff8e234081681，队列e6e0f97ddd5a36c292318459a9895f54，经真实页面一次选B站/抖音/快手/小红书后关闭浏览器，四项服务端completed。B站复用0080900c6a5a4af4b17c26d92d1d64be，ZIP SHA与前批保存值相同；其他子包347e0699c8e94467a67419dd344f1d7c、907c3c1441664667b8aa9ba466894cab、7bab141486ea4948832866a722841a46完成。重新从素材区打开原包，页面4/4并下载四份不同平台七文件ZIP，ffprobe逐包实际30秒H264/AAC、各profile尺寸。

恢复实证：另存同素材的“多平台版”标题发布后提交三平台队列75e124109c594dcc8c87c446339a0df6。前两项完成/处理中时cancel，当前项收尾，第三项jobId仍空；显式resume启动第三项时终止已核身份的本仓库服务。重启后batch显示interrupted，两秒观察无新attempt；真实页面“继续未完成队列”恢复同batch，前两项ID7286f92f29774d9794a9aa45a94c4cea、b1d0a60fc91d46428de5758bfaae43dd保持，原中断bb3558c6482c48da9c66cd4cadc02e30保存在history，新增attempt2/job28a574f29720482b8cbba0008e055d31完成。再次打开页面3/3，旧尝试不改不删。

唯一关键guard通过：状态whole-hash、初始化原子公开/坏记录隔离、锁序/取消提交边界/权限复用/中断history均核对。主树3Python Ruff/format/mypy、2JS语法及真实流程/文件检查通过，无pytest/全量。早期下载脚本未等四个详情就按索引取链接导致重复下载，已等全详情并冻结不同href后获取四份，未重建包。产物.cache/scratch/package-batches-20261118/：bilibili.zip、douyin.zip、kuaishou.zip、xiaohongshu.zip、delivery-evidence.json和响应/截图。全程无模型/支付/实际平台上传；Hook/CTA/智能时长变体不在本批，P035整体仍partial。
