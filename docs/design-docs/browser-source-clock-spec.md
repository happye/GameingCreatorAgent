# 验收页面浏览器源时间映射

该能力属于Phase 0本地验收工具。application/browser_source_clock.py保存纯数学和边界，ui/static/source-clock.js提供对应浏览器运算与实际加载／定位观测；两页面复用。domain源时间、FFmpeg probe、存储与Provider不变。

播放器轴不是天然的规范源时间。已实测Chromium／MP4在非零PTS时可暴露绝对展示轴，先核真实源元数据和浏览器观测，再减去量化origin。源微秒用half-up量化；安全整数、有限值、流覆盖、2ms轴容差及50ms时长容差共同约束。只有视频有效覆盖范围可自动取时或回看。

每次媒体加载以新代次重建映射，捕获token／generation／currentSrc；每个定位await返回后、恢复位置写入前都核身份。定位须真正完成并有可呈现数据，超时返回失败。未知或不一致状态禁自动按钮，保留手填规范源时间及本机原片链接。零起点异常增长／非有限时长均撤销；非零定位的实证增长仍须有限且不超过origin加规范跨度的已知端点。

原片参考页在播放器移动或忙碌时保持pending，最多两次空闲重验；正常重验恢复原位置，媒体重载或查询切换则取消旧恢复。候选页把规范区间转换为播放器区间，验证后真正播放，在区间末暂停；不把自然片尾当区间终止证据。

原参考context的媒体字段与automaticTimeCapture旧语义保留。新顶层runtimeClocks为由实际源派生的运行投影，不参与contextSha256；验证时剔除此字段核原身份，并对存在的投影严格重建比较。旧包无此字段仍可验证和使用原行为。原plan、记录schema、参考事件、Top10身份及评分不改。

实证和当前限制见[交付报告](../exec-plans/report-2026-10-24-source-clock-mapping.md)。支持范围只对应已测本地Chromium／合成MP4，不泛化为全部编码或浏览器通过；视频晚起的无画面头部、矛盾媒体和不支持情况继续手工核对。合成条码画面与ffprobe帧PTS独立oracle是验证的一部分，不以赋值currentTime自证映射。
