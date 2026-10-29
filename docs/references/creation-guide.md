# 创作方案和剪辑决策

当前首版支持结构化需求和离线模板，使用明确选中的Completed分析素材；不调用模型，不产生新分析费用。它保留原分析和素材，写入全新的创作目录。

## 1. 填需求

复制仓库根的creation-brief.example.json，填写游戏、内容类型、平台、目标秒数、目标、观众、语气、必须主题和排除项。targetDuration必须为1–86400的整数秒。当前不是任意自然语言理解；未识别的创作意图不应视为已理解。

## 2. 生成方案并选择一个

```powershell
./scripts/plan-creation.ps1 -Project <项目目录> -Run <Completed版本ID> -Brief ./creation-brief.example.json -OutputPath <新的创作目录> -Select hook-first
```

Run可显式选多个版本；Event可进一步指定事件。支持chronological（同源按原时间）、hook-first（末段作为开场，再回溯）、reverse（倒序）三种模板。没有Select时只保存方案；选中可用方案才写edit-decision.json。

plans.json保存三种方案、原片段、可编辑描述草稿和缺口；receipt.json绑定完成文件SHA。少于3个不同源区间或必含主题缺已保存文字支持时，方案不可选，不会复制素材凑数。同源同区间跨分析版本只算一份；不足一个输出帧的片段不进入模板。

脚本目前是已有描述草稿，不代表真人确认、完整解说或玩法事实保证。必含主题检查只查保存文字，不证明画面理解；更完整的脚本/知识/素材评分按产品路线后续实现。

## 3. 真实渲染（首版已交付）

render-creation / scripts/render-creation.ps1接收项目、已完成创作目录和新输出目录，按选择方案的创作顺序生成video.mp4。实现状态、验证和已知限制见[sprint](../exec-plans/sprint-creation-render.md)；未有完成回执的目录不算成片成功。首步已支持原片裁剪、拼接、缩放/留边及音轨，不把它当字幕/变速/转场等完整渲染功能。

现有输出目录不会覆盖，原素材/项目和已有创作目录不可用作输出。源文件变动、来源或回执不符会拒绝，不能仅改JSON路径指定任意原片。

完整路线：[全51项计划](../exec-plans/accelerated-product-roadmap.md)。你现在必须做的人工任务为0项；后续触发与数量标准见[人工清单](../exec-plans/user-actions.md)。

```powershell
./scripts/render-creation.ps1 -Project <同一项目目录> -Creation <上一步创作目录> -OutputPath <新的成片目录> -Width 1280 -Height 720
```

完成目录含video.mp4与最后完成回执；实际首闭环样例为865帧、30fps、28.83秒。GUI表单与下载接入是下一批，当前须从公开脚本操作。
