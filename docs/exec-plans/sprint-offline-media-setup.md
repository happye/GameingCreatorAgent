# Phase 0 固定媒体工具离线准备（2026-10-29）

主交付：新机器/独立worktree不再手工逐个复制固定FFmpeg文件；从已有本地bin目录恢复当前已固定副本。动机：TD003复制副本无可用上游归档，且本轮独立worktree曾因缺FFmpeg跳过17项回归。此交付只补可靠的离线准备流程，不解决来源/许可证，不改变当前pin、不下载新构建、不推进后续创作阶段。

设计：task_architect/gpt-6-astra/low只读最小方案。实现由task_developer/gpt-6.1-sol/medium在独立.cache/worktrees/offline-media-setup、分支codex/offline-media-setup（base3f7450a）拥有scripts/setup-media.ps1、scripts/toolchain.ps1和新tests/test_setup_media.py。主控公共记录；Sol/high唯一独立边界评估，不叠普通review。用户已授权本地开发，任何新构建下载/替换仍需之后具体许可。

合同：setup-media.ps1 -SourceBin <已有本地目录>只读现有media-toolchain.json，仅复制列出的固定EXE/DLL，拒绝来源/目标/暂存路径链接和重解析点。先复制到.tools下唯一staging，逐文件核验SHA，再整体原子发布到不存在的.tools/ffmpeg。已有目标验证通过则幂等返回；验证失败绝不覆盖、删除或自动修复。不增Force、不接setup-demo默认、不接任意manifest或下载参数，不运行源文件。

复用：toolchain.ps1可抽取接受明确目录的内部校验器，公开Assert-ProjectMediaTools仍固定项目路径及原清单。清单应拒绝空/重复/逃逸/无效SHA等明显结构错误，现有九文件与版本不变。

失败/并发：失败保留已有目标和来源字节，只清理本次创建、位于项目.tools且经复核的唯一staging；不得递归删除未验证目标或隐藏原错误。并发最多一次发布，另一方可验证既有匹配目标后返回或明确停止，不能覆盖任何工具。只改项目内文件，不改PATH/注册表/用户系统设置。

验证：离线fixture测试缺文件/hash错误/manifest路径逃逸或重复/来源与目标链接/已存在匹配与不匹配/并发发布/staging失败清理与保护他人目录；真实当前副本在缓存隔离小仓库恢复并通过原hash门禁、ffmpeg/ffprobe version；主树init及受影响媒体入口检查。Fixture通过不等于新官方构建兼容/许可证已核验。所有Python先加载主树env，再设worktree PYTHONPATH，python -B，缓存隔离；无新二进制下载或全局安装。

状态：合同已确定，开始实施。当前四项基线d13b0e7完整verify3706通过/3跳过/退出0；没有运行中的旧检查。

实施节点：Sol/medium独立三文件已完成，PS7/WindowsPS5.1 26passed/2文件符号链接权限skip；真实原副本在缓存恢复9SHA及ffmpeg/ffprobe版本通过，Sol/high独立边界审查中。另用户已许可月末候选下载并隔离验证，另Sol/medium worker另cache/worktree执行，不改变本脚本旧pin复制安装合同。

集成节点：Sol/high关键边界评估PASS（只读，无有证据缺陷），三文件已主树集成。主树首组3失败由候选UV误目标删除主venv部分依赖导致ModuleNotFoundError，不归为媒体安装缺陷；原锁+本地缓存恢复41包、init与应用/测试/浏览器导入恢复后，同组40passed/2文件symlink权限skip、47.77秒，JUnit .cache/offline-media-main-restored.xml。真实当前副本9SHA/版本恢复已通过。生产pin不变，TD003仍open。后续环境写操作必须用目标worktree自身env并断言UV_PROJECT_ENVIRONMENT，--project不够；已同步协作指南及错误记录。下一步提交并对最终整合版本完整verify。
