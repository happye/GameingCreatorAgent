# 固定媒体生成器与合成源时钟预期（2026-10-29）

阶段：Phase 0工程测试的输入身份，不是F006人评或生产FFmpeg升级。来源：已获许可候选隔离原组151通过/3失败，经新旧probe读取相同新旧文件四矩阵证明合成输入随编码器版本变化；3校准场景已完整验证保护动作。Astra/low只读决策认为值得限定三个真实重编码夹具绑定固定生成器，保持精确断言。

owner：Sol/medium唯一实现者，在.cache/worktrees/media-clock-expectations、codex/media-clock-expectations（base1825d2b）拥有tests中的新media_generator_clocks helper、新helper单测及test_browser_source_clock.py、test_benchmark_source_clock_browser.py。主控公共记录；Sol/high唯一源时钟/身份评估。不得改APP/生产media-toolchain/原编码命令/容差/人工判断。主树44e2537完整verify98084仍跑，不能写主树源代码。

合同：按实际ffmpeg.exe SHA选择两条写死记录，再核对该记录对应DLL/工具文件SHA，不能仅读可修改manifest就接受任意库。只接受主树旧固定副本和已核SHA的2026-09-30月末候选；未知EXE或库不符明确失败。静态数据来自原manifest、候选manifest及四矩阵原JSON/输入SHA，不能运行时把APP/probe结果当预期。

旧预期：origin2478000us、duration2022000us、绝对video start2500000us，提示0.022s；新预期2478667us、2026667us、2500000us、提示0.021s。绝对起点不等于归一化偏移，不把2500000写进relative字段。只改三个实际生成输入的用例，纯手写MediaAsset/JS转换/边界条件常量不改，不全局替换。

验证：各自绑定的新旧已确认工具运行三个完整场景和原保护断言；未知SHA、DLL mismatch明确失败。生产旧工具相关回归保持通过。原151/3及校准补测证据保持历史事实，新结果单列“固定生成器预期绑定后验证”。所有工作树内仅copy旧固定工具或复用已批准候选，不下载新包/工具；包/venv不得写共享主树，用只读主Python做测试时-B和PYTHONDONTWRITEBYTECODE=1，浏览器指已有资源。

状态：开始实现；不修改生产pin、不声称候选许可证完成或F006验收通过。

执行中断节点：Sol/medium worker因usage limit结束，实际留下helper、helper单测和test_benchmark_source_clock_browser.py三文件（3个目标用例都在此文件，另测试文件无需改）。无存活原pytest。主控明确披露后仅接管Ruff/定向执行，Ruff通过；旧固定工具7单测+3完整场景10passed，.cache/generator-clocks-old.xml。Sol不重试，独立评估显式fallback到Astra/low默认角色按quality-guard合同仅一次；未审前不并主树，实际结果待录。

交付节点：Sol额度中断后的既有三文件由主控完成格式/定向验证；旧工具10passed/18.50秒、新工具10passed/17.05秒，JUnit generator-clocks-old/new.xml；实际完整文件hash记录与旧/新两manifest逐项一致。已明确披露后唯一独立评估使用Astra/low默认角色（intended quality-guard）PASS，无阻断缺陷，未更改默认模型路由。已主树集成并10passed/17.54秒，generator-clocks-main.xml，Ruff格式/检查通过。APP、脚本、生产媒体pin均无diff，仅helper/单测/三个实际生成用例变更；未改其他纯手造或边界测试，不重复无关3700全量。最后完整生产基线44e2537为3732passed/5skipped/退出0。原候选151/3与校准补测保留，新结果另列“固定生成器预期绑定后验证”。


后续长录像隔离对比已完成，结果和接手顺序见[sprint](sprint-saved-long-media-comparison.md)；本合同交付已完，无存活检查/写者。
