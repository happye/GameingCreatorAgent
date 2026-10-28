# TD003：FFmpeg月末候选隔离验证（已获许可，2026-10-29）

用户已明确回复“允许下载并隔离验证”，绑定机器可读候选的精确URL/SHA。现允许下载、缓存隔离解压及执行指定检查；不允许替换当前工具、改变生产pin或分发。当前固定副本继续用于开发，TD003仍open。

候选来自[BtbN月末发布](https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2026-09-30-13-08)，所选资产为`ffmpeg-N-127021-ge0c94b2d1c-win64-gpl-shared.zip`，官方资产页显示约83.9 MB；SHA256见[官方资产元数据](https://github.com/BtbN/FFmpeg-Builds/releases/expanded_assets/autobuild-2026-09-30-13-08)与[机器可读候选](../references/ffmpeg-source-candidate-20261029.json)。精确身份以所选资产名和SHA为准，不能套用发布标题中另一个master构建号。

[维护者保留规则](https://github.com/BtbN/FFmpeg-Builds#release-retention-policy)为最近14个日构建、月末构建两年；因此选月末，仍不保证永久可取。只读网页元数据已由Luna/high及主控分别核对，没有请求zip文件。

已许可操作范围：仅下载此精确归档至项目`.cache`，先核SHA再在隔离目录解压，读取内部文件与许可证，运行`ffmpeg/ffprobe -version`、`-buildconf`、`-L`，在隔离worktree检查媒体/存储/源时钟行为。当前`.tools/ffmpeg`、生产清单和旧分析数据全部保持。用户已对这组指定操作明确许可，可以开始；不得扩大为生产替换。

尚待真实检查：候选DLL集合、版本/ABI、解码器/编码器/滤镜能力、第三方notices、源代码对应关系、项目fixture与真实素材兼容性。GPL-shared标签不能代替上述核对，也不构成分发许可审查完成。后续替换生产pin或分发另行审阅，当前方案不包含。

并行独立交付：已有固定副本的离线准备脚本及假文件/当前副本测试，见sprint-offline-media-setup.md。此流程不下载，不解决当前复制副本来源问题，不将TD003关单。

许可记录：.cache/ffmpeg-candidate-20260930/authorization.json；通过此隔离验证也不自动授权生产替换或分发。
