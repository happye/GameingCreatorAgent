# HANDOFF（覆盖快照）

## 最近一次会话（2026-11-19）

分支 `codex/knowledge-version-compare-20261108`。先看 [STATUS](STATUS.md) 和 [看板](docs/progress/index.html)。本批完成三个切片：P041 同一草稿混合 AI 插入、裁剪、局部删除、手动替换；P035 按平台选短版时长、填写画面内开场与结尾文案，再试听或下载各平台成片。不要重做多平台持久队列、AI 单换／多换／插入、编号策划、本地补足 30 秒或 Grok A01–F16 修复。

## 实证与接手入口

- 项目 `artifacts/demo-phase0`，真实漫画群星 run `f76f5d6495314c04ae04083614d4afd6`，作品 `55f97422dabd6c5a3d87eb323018e45a`。新代码验证服务 `http://127.0.0.1:8767/studio`，所有权与日志见 `.cache/workspace/port-8767.json`；此前 8766 未动。验证队列已终态。
- [混合剪辑](docs/exec-plans/sprint-mixed-timeline.md)：父 `6f57066755a04d47b05bbd28b1eb2667` 使用原已付费插入建议；保留 `48–48.5s` 插入，删另一原段、手换一段，同一草稿撤销/重做、刷新和保存；新版本 `27e135f8feb54512a5666a1cf065481e` → 渲染 `d26767ce66bd425a99408c6d8c6bcc9f`（825 帧 / 27.5 秒），浏览器已解码并播放。发布 `5462eed2c820468eb4beb5c1c5ac94d1` → B 站 `616395e711434a39a3d383ded9057b1d` 七文件。`composed-v1` 保存可信插入锚点，允许删锚后保留插入；旧 v5 恢复保持，替换段两侧固定硬切，编辑后旧预览不可套用。
- [平台短版](docs/exec-plans/sprint-platform-short-pack.md)：同一发布批 `f62b4943015cfab48822711116c2e921` 恢复 2/2，B 站全长 ZIP 原 SHA 不变，抖音 `8d38b8a136c346fb861627e892fa0024` 720×1280、450 帧 / 15.000 秒，音画终点相同。`Fields.variant.durationFrames` 随队列冻结，单包和批量入口校验父收据与帧数；旧全长不变。
- [画面文案](docs/exec-plans/sprint-platform-video-copy.md)：同一发布批 `f1e517f6615987d13500c8f7874fb293` 重开 2/2，复用全长 B 站，抖音 `8d70a0e46326463ebd5696c114092a18` 首尾各两秒，画面、音轨各 15 秒。本机播放、下载结果卡包含冻结文案。`Fields.publicationText` 与时长独立。产物 `.cache/scratch/platform-video-copy-20261119/` 下有 `douyin-opening-closing.mp4`、七文件 ZIP、`frames.png` 和探测记录。
- 可用产物 `.cache/scratch/mixed-timeline-20261118/`：`mixed-timeline.mp4`、`bilibili-duration-variant.zip`、`douyin-duration-variant.zip`，以及 `playback.json`、`variants-final.json`。此前四平台与三平台中断恢复实证仍在 `.cache/scratch/package-batches-20261118/`，[原合同](docs/exec-plans/sprint-package-batches.md)。

## 下一优先级与约束

下一步 P035 按内容生成平台短版：从同一发布父成片及已有可信时间线选择最相关区间，显示选择和预览，复用冻结配置／队列；再接 P041 一句话发起混合修改，复用现有操作和试听。每个切片沿真实素材闭环并更新看板。原 `.codex/agents/` 用户更新、未跟踪设计文档、工作树及 stash 保留。

本批只有必要的小范围静态、浏览器和下载文件验证；无 pytest/全量/Release、无付费模型或上传、未合 main。旧完整 `verify-20261117-002506` 按用户要求中断，曾见失败，不标绿。J1 第五次人评未过，J2/J3 未人评，不因工程实证改 `passes` 或质量。更新和推送遵循 `AGENTS.md`；原录像、旧分析、收据和账本保留，已有失败/付费请求不重发。文字月 ¥30/单条 ¥1、指定视觉月 ¥50，继续走费用门禁；声音免费本机，真实平台发布或支付须另授权。
