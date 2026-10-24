# 单注册帧自动静态观察：离线交付

2026-10-24，Phase 0／F010。本轮已完成工程验收；真实发图尚未授权，F006/F009/F010继续false。

## 现在能做什么

选已有Completed录像的一张登记画面，先完全本地冻结提案；在该提案另有明确授权后，生产入口最多发送一次，严格解析并独立保存静态草案，沿用现有collection发布和条件查询。恢复只补本地结算／发布，不重新发图。没有主体时保留真实单帧记录并报告no_observations，不造主体或动作事件。三个命令及字段说明见[使用指南](../references/static-observation-generation-guide.md)。

模型必须明确指出局部衣物／持有物属于哪个part。棕短裤＋白外套不会因程序拼接变成棕外套；左手物体形状不会与右手物体类别拼成同一个物品。这只保证保存声明之间的关系不被程序编造，仍不能证明模型看对了真实画面。

## 修复与独立评估

Luna/high只读定位接口；DSH唯一写六源码／三测试；Codex负责合同、正式检查、文档和Git；唯一Sol/high先评合同，后复核同一交付，无重复reviewer。实际型号已从turn_context核实。

首轮正式134通过／1权限skip，但独立评估仍找出五项反例，原证据保留，未以绿测试盖过问题：项目全体attempt误耗新授权额度；零字节／丢失账本被当新库；同proposal换授权时混用旧费用；异常测试未证明硬退出恢复；平面属性被程序硬合成同衣物／同持有物。

五项已在同task一次集中追修并经该评估者PASS：按authorizationId＋hash计额；持久初始化标记与空／缺库失败关闭；既有attempt授权冲突拒绝；真实os._exit四断点和新进程恢复；显式局部parts-v2及跨物负例／同物正例。原static store／codec／matcher／V6不改。main.py确为59行纯新增，原行无删除。

## 正式验证

最终合同v4 `a1881905d1290c68bd826e77d824f69006fd98d99332ee9f497455a82c465187`，635个实际输入、8495个显式运行依赖。合同R1–R9未删改；源码修复期间用紧凑v3保留要求，避免把完整依赖目录清单重复送进编码模型；最终完整测试计划仍由主控绑定并执行。

| 检查 | 结果／回执 |
| --- | --- |
| 真实SQLite、生产装配、fake transport、跨进程查询／并发／硬退出及邻接回归 | 159passed／1权限skip，49.08秒；run `c1281d7a-cc96-4e76-b480-f22f773191cc` |
| 九文件Ruff／格式、六源码mypy `--follow-imports=silent` | 通过；run `c21ec6f2-1843-4bcc-8ba1-44dbf2c1f37f`；不是整仓mypy或完整verify |
| 两次离线wheel、全部Python成员与源码字节比对、隔离wheel导入CLI | 通过；run `6d244f3f-4732-43c4-9e40-4bcd5f0a2d73` |
| 独立费用／持久化／并发／身份／部件边界评估 | 同一Sol/high复核五项PASS；未重复全套测试 |
| 既有资产保护 | 37个保护文件SHA不变；原标注及纠正、旧费用与V6规则保持 |

四个真实子进程硬退出点：planned落盘尚未发图、HTTP中、typed文件已落盘但尚未结算、collection已发布但尚未标记。新进程均可重新取得锁；前两者保留未知占用，后两者只恢复本地发布，总发送最多一次。唯一skip是Windows符号链接创建权限，不声明POSIX锁或断电级介质故障已实测。

三回执在最终文档／Git变化前均由receipt重读并经评估者独立核验，valid/evidenceComplete/passed=true；源前后指纹一致 `8f48551ca18900c1d8adec3adbf36a2cf28d2020e8de538c3d66c098ec18cf19`。后续文档／Git变化后它们是该受测版本的历史证据，九源码／测试SHA另存validated-source.json，不冒充新Git基线的当前回执。

两个wheel逐字节一致，SHA `351bac8501fe3d4f31ecc05a719a243af5771ac284ce45bbc06f93759cb09eea`，120成员／105个Python成员，无.cache或__pycache__路径。uv关于缓存位于源目录的原警告保留，实际包内已核无缓存。隔离子进程忽略PYTHONUTF8而以本机GB18030输出帮助；原始字节保留并另存正确UTF-8解码副本，源码字节及包内中文未改变。

## 续接核查、旧进度与下一步

旧task `gamingcreator-static-observations-20261023`实时无运行轮次／队列，三个请求均COMPLETED，但后台子树静止未证，原STOP_PENDING／阻断保留；未重投、重复cancel、杀Host或归档。工具fc47d97的新CLI直接导入当前磁盘模块；两次最新优化仅改Skill／手册／离线benchmark，没有Host升级需重启。个人与工具仓库Skill逐字节一致。环境85份漂移pyc已从SHA固定的本地原安装包恢复并留原字节，回执／系统配置不改，完整init通过。

新task `gamingcreator-static-generation-20261024`／session `codex-d988fa9d-3d21-4604-b2f2-26c5b46d9d90`，同workspace `f4395711-a8fb-49a3-ad95-7305ce9ea1e8`。两个distinct请求 `754ee660-07dc-4243-b173-2c4a7c887b2d`、`e75d4f30-871b-4e72-890a-90acf7ec63b4` 均COMPLETED，新终态答复各按hash全文读一次。使用60秒增量摘要、单watcher和最多三窗口的有限脚本观察，不读进行中全文、不常驻调度。

DSH用量投影为partial：208个usage事件因请求关联不明被排除，汇总token与费用保持未知，不补零、不算节省比例；两个逻辑send不等于提供方请求数，更不是双方总账。原始usage-final.json已保存，本轮不扩修外部工具。

进一步已用新生产prepare入口，完全本地冻结原28–29秒样例的28.5秒单帧，proposalHash `95880840d38ea2f6e6bda85427ecfab8806cab9ec02422b1bd3d4a449a5f2b59`。922个旧项目文件（排除SQLite共享内存文件）SHA不变，零发送、无授权文件、无预算占用；没有执行旧付费脚本。冻结价格快照计算预留¥0.416；官方现价核对仍为Flash高峰未缓存输入¥2／百万、输出¥8／百万，真实试验拟新增上限¥0.50、一次请求／一张图、禁止重试。[DeepSeek官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

这份本机提案保存在`artifacts/dsh-static-generation-20261024/real-single-frame-proposal.json`，不是新费用授权。真实执行前须用户明确同意把该单帧及静态提示词发送到`https://api.deepseek.com/chat/completions`。只验证新协议接受性和生成保存，不要求重新标注；真实画面对错与原人评继续留空。新初始化marker会拒绝无marker旧试验账本，不自动迁移；当前没有真实静态生成账本。

本机完整证据在ignored `artifacts/dsh-static-generation-20261024/`，包括四版合同、两次新答复、首轮及最终回执／JUnit、评估、保护及实际提案。Git提交与普通推送状态以Git和同目录publication.json为准，不强推。长钟馗269成功／3缺口、469观察与原费用，原12条标注及纠正、六份新增素材均保留。真实验收仍按Phase 0原门槛，不转入创作成片或商业阶段。
