# 本地媒体处理合同（F002）

## 使用与结果

先准备项目隔离工具并运行 `scripts/init.ps1`。`scripts/test-media.ps1 -SourcePath <video>` 处理单段；`-AllLocal` 顺序处理当前授权 `GameVideos/**/*.mp4`，不联网、不调用模型。应用接口是 `MediaProcessor.probe/preprocess`，采样参数为 Fraction 间隔、最大宽度、最大帧数；处理结果只证明媒体 bundle 完成，`gamingcreator analyze` 仍未集成模型/存储。

新目录内输出 JPEG、16kHz/16bit/单声道 WAV、`media-manifest.json`。文件与时间映射核验、源文件重新 hash 及取消检查成功后，才 `fsync` 临时 manifest 并原子替换。失败目录无完成 manifest，留给 F004 恢复；不自动删除用户路径。证据 ID 使用 run/media 命名空间。

## 源时钟与音频映射

- 选择首个非封面视频和首个音轨。必须有有效 `start_pts`、`duration_ts`、正 timebase；缺失则明确输入错误，暂不猜测 format.duration。
- origin 是选中流最早 presentation start；总时长由最大流 end 减 origin。保留原始整数 PTS 与 Fraction 时基，点/起点向下取微秒、终点/时长向上取微秒。
- 图片采用 `-copyts`、时间驱动 select、showinfo 和 passthrough。按整数 PTS 映射，核对文件/日志数量并检查选中帧递增；不按 FPS 推时间，也不声称校验了所有未选中源帧。
- WAV 样本轴与源时轴通过逐输出音频帧映射。`map_interval(start_sample,end_sample,asset)` 返回源范围、跨越的 gap/overlap 和精确边界裁切量。跨越不连续点的范围包含不确定性，F003 不得改用单一 offset。
- 重采样后按声明音轨结束 PTS 做 atrim，保留观察到的裁前/裁后样本数；这不是所有未请求尾部样本的完整统计。起终点容许≤1输出样本的量化误差，裁切量留在 manifest，不能放宽掩盖实质越界。

## 进程与限制

只调用 `.tools/ffmpeg/bin`，`media-toolchain.json` 固定二进制/DLL hash；manifest 记录 FFmpeg/ffprobe 版本。参数列表、无 shell、file/pipe 协议限制、隐藏启动。Windows 先挂起创建、加入非继承 Job，再恢复；关闭 Job 后排空管道并回收进程树，不能只杀 venv 启动器。

当前每次 stdout≤4MiB、stderr≤16MiB，超限停止且不发布完成结果。双音频日志使小时级素材需要流式解析（TD001）；当前只验证约 8 分钟合计素材，不宣称小时级性能。开发工具顺序执行；分析任务并发/单写调度在 Application/F004。正式分发前解决复制的 FFmpeg 来源及 GPL 义务。
