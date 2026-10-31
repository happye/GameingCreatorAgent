# P018：游戏知识层（本机）

2026-11-01，Claude Code单Agent。

## 合同

- application/knowledge.py：条目字段校验与长度/控制字符限制，来源类型official/wiki/user，entryId=内容SHA256，replaces形成版本链；current/history/search/citation纯函数。
- infrastructure/knowledge_store.py：.cache/workspace/knowledge/<entryId>.json独占创建、永不覆盖；替换必须同游戏且原条目存在。
- GET /api/knowledge?game=&q= 与 ?entryId=；POST /api/knowledge 文本或文件（复用活动规则本机读取）。

## 结果

2026-11-01游戏知识层P018已交付（部分）：创作页新增“游戏知识（本机）”，按需求里的游戏名查找/新增条目（标题、内容、来源类型官方说明/Wiki攻略站/用户资料、来源说明），内容可手填或从本地txt/md/html/截图/PDF读取（复用活动规则的本机读取，不联网）；条目以内容SHA256命名、一条一个文件、永不覆盖，修改生成新版本并记录replaces，可查完整历史，查找只显示最新版本；查找按关键词在标题(×3)/正文中的出现次数排序，每条带“（来源：类型·说明，日期）”，可一键“插入到旁白”（截取前120字+出处）。存于.cache/workspace/knowledge。4项测试（校验、版本/历史、跨游戏隔离、HTTP文本/文件新增+查找+历史+错误）及相关回归共68项通过、Ruff/mypy通过；单Agent。仍未做：规划/解说自动引用知识、联网抓取Wiki、补丁版本对比。51项10/37/4≈56%，首产品0/22/0≈50%；人工0/未来9、债务20项11/2/7不变。下一专业时间线导出（P033）。
