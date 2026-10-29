# FFmpeg月末候选隔离验证（2026-10-29）

结论：下载及隔离评估已执行，仍不替换生产pin，不关闭TD003。当前原FFmpeg、生产清单及三份原片hash前后一致。用户许可只覆盖指定归档的下载/提取/运行验证，不含替换或分发。

候选：N-127021-ge0c94b2d1c-20260930，精确官方来源与SHA见ffmpeg-source-proposal-20261029.md和../references/ffmpeg-source-candidate-20261029.json。归档87,981,673字节，SHA完全符合许可；安全提取224文件，回执在.cache/ffmpeg-candidate-20260930/extraction-receipt.json。下载文件保留名ffmpeg.zip.partial但已完整校验，不表示有后台下载。

结果：154个独立检查原组最终151通过/3失败/0跳过。首次35项浏览器因环境缺包跳过，已从现有缓存离线补齐并实际运行33通过/2失败；没有隐藏skip。公开PS准备入口已实际通过。三段真实素材预处理成功，独立环境真实存储二进程往返成功；0模型调用。原测试断言未改。

三失败：旧合成样片时长2.022000秒、音频起点2.478000秒；新候选生成的样片为2.026667秒/2.478667秒，页面无画面间隔从0.022变为0.021秒。两个浏览器断言在其后保护动作之前停止，不能称目标动作已验证。四组交叉读取同一新/旧文件时，两版本ffprobe输出一致；证据支持合成编码/封装变化，并未发现同输入探测差异。矩阵命令、输入SHA、四份原JSON和matrix-summary.json均保留；追加校准三场景补测另记，不改报原151/3结果。

构建差异：libav DLL ABI各升一代，配置新增libcurl/librsvg，移除libshaderc、禁用FFmpeg whisper；真实本项目兼容性不得仅据这些标签推定。已保存-version/-buildconf/-L输出。GPLv3文本存在，完整对应源码及第三方notices证据未完成审阅，不宣称可分发。

环境事故：候选准备曾因UV_PROJECT_ENVIRONMENT继承主树，uv --project没有改变虚拟环境目标，导致主venv部分依赖被删除，主树三媒体入口报ModuleNotFoundError。原工具/生产pin/原片未变。主控按原uv.lock及本地缓存恢复41锁定包，init与导入恢复，主树相关组40通过/2权限skip。候选随后使用真正独立runtime/venv；candidate-environment.json记录其身份。错误/首次失败/恢复后结果均保留，协作指南已区分只读共享测试与独立环境写操作。

恢复注意：run-validation.ps1是首次实验原始记录，含已过期主venv路径且提取拒绝覆盖，不能直接重跑。后续只在候选worktree自身env、显式候选UV_PROJECT_ENVIRONMENT下运行指定检查；已有SHA与结果不覆盖。当前无需要重启的旧检查。

补充实验已完成：按两版本ffprobe独立一致证实的新样片源时钟，仅在候选cache复制测试模块，替换对应时刻预期和提示文本、保持所有容差与后续保护断言；3场景通过，完整执行快速切换防旧时钟串用、可见零轴矛盾拒绝。原测试文件前后SHA相同，原151/3结果不变。依据/原文件SHA/改动范围/日志见calibrated-smoke-basis.json、calibrated-smoke-result.json与calibrated-smoke.log。机器可读最终结果见../references/ffmpeg-source-evaluation-20261029.json；candidate.json为许可时点不可变快照，其当时downloaded=false不代表当前下载状态。授权doc SHA与完整归档SHA均由主控再次核对一致。无后台候选任务。

固定生成器预期绑定后验证：Astra/low设计、Sol/medium留下三测试文件后额度中断，主控完成新旧两套7单测+3完整场景各10passed；Astra/low显式替代独立边界评估PASS，主树旧工具10passed。只依据实际EXE及整套已确认工具/DLL SHA选择静态整数预期，未知或混库失败；APP/生产pin/编码命令/容差/保护动作未改，不把运行时app/probe输出当答案。该后续测试夹具维护结果不覆盖原151/3记录，也不构成生产替换或许可证审阅完成。


已保存真实长录像补充验证：按旧manifest完整采样参数重取，1903源时刻和44629音频原始映射均相同，音频PCM相同。JPEG文件SHA全部不同、WAV文件SHA不同；同一完整SHA核验的固定参考解码器归一RGB24后1903/1903像素SHA相同，1280×534、SAR801/800。原片及1907旧文件前后不变；Astra/low独立时钟/保护审计与增量像素审计PASS。结论仅限本片/参数/参考解码器；不覆盖旧证据、不更改生产pin、不声明模型质量或许可证完成。完整合同/缓存路径/下一主线门禁见[sprint](sprint-saved-long-media-comparison.md)，机器结果见evaluation新增savedLongReplay。
