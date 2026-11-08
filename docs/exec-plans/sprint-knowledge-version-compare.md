# P018 本机补丁说明版本对比

2026-11-08；基线 main 36d8325。对应R3和P018尚未实现的补丁版本对比；不替代真实模型质量验收。

## 合同

- Studio在搜索结果或历史中显式选择同游戏的旧/新条目，逐行显示新增、删除、未变内容；两侧带条目ID、标题、来源、日期，可查看原文。相同正文如实显示无差异，来源变更仍在两侧可核。
- 复用不可覆盖KnowledgeStore和现有GET `/api/knowledge`，增加精确查询形态`before=<entryId>&after=<entryId>`；缺失条目或跨游戏拒绝。Application用标准库difflib生成只读行对照，不加依赖、数据库或模型。
- 对比不修改文件、不自动写旁白/策划。选择、游戏或项目变化使旧请求失效，防止迟到结果贴错出处。不是联网补丁抓取或语义玩法变化判断。
- 主控为root唯一写者：application/knowledge.py、ui/server.py、studio/knowledge.js及相应既有测试；三棵已有脏子树保留，不并行覆盖。task_explorer（Luna/high）已核需求与未实现状态；提交前唯一边界审查复核数据出处/迟到隔离。

## 验收

1. 同游戏两版含中文/空行/emoji的文本，增删/未变行逐字对应；元数据来自各自原记录，正文相同及来源单独变化均可核。
2. 真实HTTP拒绝未知ID/跨游戏，旧搜索/历史协议不变；对比前后知识文件字节不变。
3. Studio保存并修改为新版本→选两侧→对照→查看各原文；改选和迟到结果隔离，1440/1280无横向溢出。无新增模型/语音或写知识请求。
4. 定向/受影响验证先行，批次结束完整verify；不提前改变P018 delivery/quality或journey的人评状态。

## 实施与定向验证

3源码已实现；唯一task_quality_guard（Sol/high）核同游戏/身份/原文与出处、只读和迟到隔离通过。跨项目/游戏的比较迟到为父组件key重挂载与mounted/panelEpoch的静态核验，未冒充本轮专项浏览器触发。后续仅将过挤的出处布局改为纵向并折叠ID/完整时间，回归核可展开的两个真实ID/时间与原文，数据逻辑未变。

`test-affected.ps1 -Browser -PytestArgs -k knowledge`：29过1跳439 deselected，53.45秒；跳过为Windows当前账户不能创建symlink（test_knowledge_import.py:46），未绕过。证据.cache/knowledge-compare-affected.log/XML。新增HTTP/浏览器完整目录字节快照及真实增删截图2项过4.96秒；最终布局/ID/日期定向1过4.16秒（.cache/knowledge-compare-final-focused.log/XML）。Ruff及mypy209源通过。截图.cache/scratch/knowledge-version-compare/comparison-1440.png与1280.png，人工视检已完成，无横向溢出。

源码检查点后冻结并运行本批完整门禁：.cache/knowledge-compare-full-verify.log；清单.cache/knowledge-compare-freeze.json。完整绿前不推进main，不提升P018整项交付/人评。
