# R1第二切片：EDL真实渲染MP4

2026-10-30，ADR-003及架构师R1合同的紧接交付，不依赖F006人评。输入上一切片完成目录和项目；输出全新目录中的真实MP4及回执。任务尚未实现，不计渲染功能完成。

公开入口render-creation及scripts/render-creation.ps1；Application校验/编排，Infrastructure固定FFmpeg执行，不能让模型运行任意命令。复用新creation模型和原只读Store完整性检查；先核creation receipt、selected方案与EDL绑定，再从Store重取每个run/event/media的真实时钟、SHA、有效区间及原文件。EDL sourcePath不是独立授权，不能按任意外来路径直接渲染。

按segments创作顺序剪接；归一化源微秒须结合原origin/流时钟，输出帧号/帧率独立。首步真实trim/concat/scale及有声/无声处理，后续按R2补crop/speed/subtitle/overlay/transition，不冒称首步已全覆盖。输出新目录独占，临时产物通过ffprobe与可解码检查后最后发布完成回执。失败/取消/磁盘错误不留下Completed，不改源视频或覆盖旧成片。

验收：至少两个不同区间真实拼接并核可见顺序；有声、无声、VFR与非零PTS样片覆盖；视频总时长误差≤1输出帧；音画偏移有明确可重复测量，不把AAC封装时长当源时钟。原文件不变；重启可回读，新输出冲突/源篡改/越界/无效EDL拒绝。用本地已固定工具和已缓存合成材料，无下载/模型/费用；测试只围绕此合同，唯一关键边界评估者增量审新增范围。

实施接续：上一切片独立评估PASS并集成后，同一实施者在已同步代码的独立工作树承担新rendering/ffmpeg_render/CLI入口及对应测试；具体文件所有权以派发记录为准。公共路线/看板由主控维护，不抢写者代码。
