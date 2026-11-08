# P033：Studio专业时间线入口与Premiere独立旁白轨

2026-11-07，延续R2全制作；三格式原导出仅在旧创作页有入口，Studio缺入口，既有音轨仅原片声明。此切片补Studio可操作入口及XMEML真实旁白素材轨，不把P033全部格式/混音/真实导入视为已完成。

## 决策与归属

Astra/low选择已有Premiere XMEML的独立旁白轨，不引入OTIO依赖。parent持合同/文档/集成及本机编辑器验证，Sol/medium唯一实施树`.worktrees/j1-preview-corrections`；唯一Sol/high查资产身份、输出时钟及只读边界。Root当前组合完整门禁运行，禁止改root源码。

本机只读确认`C:\Program Files\Adobe\Adobe Premiere Pro 2023\Adobe Premiere Pro.exe`存在（23.0.0/23.0.0.63），没有发现Premiere进程；尚未启动或验证软件可运行。不得擅自安装全局CEP扩展、改调试注册表、覆盖用户项目或接受登录/许可。已具备具体XML后再由parent验证独立临时项目，失败只阻断对应导入验收。

## 后端与纯导出

- `ui/creation_jobs.py:timeline_export`核已保存父链及旁白来源，复用只读load_chain/asset验证，使用NarrationArtifact现有wav_path/sample_rate/channels/sample_width/sample_count及NarrationSelection.start_frame，不能客户端传任意路径。GET不生成TTS、媒体、修订或恢复写盘；非completed/错项目/回执/缺件明确拒绝。
- `application/timeline_export.py:to_xmeml`增加可选纯数据旁白输入，在原源音轨外增加独立audio/track/clipitem，独立file/clip ID。文件URI引用核验后的实际WAV，声明真实声道、采样率/位深；source in=0，输出start=start_frame，时长为ceil(sample_count*fps/sample_rate)，整段容纳约束沿validate_narration_fit。无旁白时保持原导出字节与默认行为。
- 原视频源URI、源时钟、总长、变速/转场/字幕路径保留。独立干声交接不声称已表达混音增益/闪避/淡入淡出；BGM独立轨及其他格式旁白属于后续，不用自定义metadata冒充编辑器效果。不增加持久产物或依赖，新增函数尽量≤80行。

## Studio入口

`static/studio/edit.js`导出检查器接现有fcpxml/otio/xmeml路由，沿已保存base.jobId/planId及尺寸。有未保存草稿、助手预览、忙碌或基线未就绪时禁用，明确先保存；不自动保存/生成版本。描述各格式实际能力与Premiere干声混音需复核，不能只把旧页面入口当Studio已接。

先检查HTTP状态；失败在页内显示，成功再下载明确`.fcpxml/.otio/-premiere.xml`文件名，不能将JSON错误下载成XML。项目/base/草稿变化或卸载取消请求，响应和blob保存前再次核身份，防迟到旧下载；释放对象URL。沿原套餐门禁，不自动切套餐。

## 验收

1. 带实际WAV的保存修订HTTP下载XML：解析独立轨、唯一ID、可打开URI、真实格式、起点/非整帧末端与整段fit。覆盖普通无旁白旧导出、保存替换/速度转场/非零源PTS方案；拒旁白错项目/回执/缺失/非completed，导出前后原资产和job/转录/账本不变。
2. 真实Studio三种下载、明确文件名、未保存/助手/任务忙禁用、403/409错误页内显示；跨project/base/draft迟到不下载、不污染新状态。局部真实媒体证明，不发云请求，不拿测试音频冒充音色质量。
3. parent在独立临时Premiere项目导入同一XML，记录版本/翻译提示/轨道/播放，验证旁白可移动和静音；未取得证据保持importVerified未验、P033 partial。无原生桌面控制工具时可先准备完整可检查文件，不伪造导入成功。

官方范围：[Adobe参考手册](https://helpx.adobe.com/pdf/premiere_pro_reference.pdf)、[Apple XMEML时钟](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/FinalCutPro_XML/Topics/Topics.html)、[Adobe XML音频转换限制](https://helpx.adobe.com/in_hi/premiere/desktop/render-and-export/export-files/export-a-project-as-a-final-cut-pro-xml-file.html)。文档支持格式语义，不能代替本机实测。

## 2026-11-08 定向交接证据

`.cache/premiere-contract-final.xml`：35通过/0跳过，112.552秒；Ruff/format及两生产源mypy通过。实际2206样本/22050Hz旁白起7终11帧，真实PCM/URI、坏依赖HTTP400/409及全库字节不变；实际FFmpeg源origin2.5秒，先保存1x替换再v4后代2x/3帧转场并携旁白，组合链通过。Studio三格式下载、6组跨project/base/unmount忽略abort的迟到成功/错误、400/403/409零URL/下载、assistant/busy禁用均验证。无旁白输出另与原HEAD实现比对，默认/含源音轨字节一致。

唯一Sol/high最终专项通过，无阻断问题；未独立运行测试。parent已准备合成MP4、免费本机David语音及117帧XML试件，旁白起7长67帧；Premiere仍未启动或实导，不能标importVerified/P033通过。root集成完整门禁待执行，原转录、账本、用户录像与全局Adobe设置未改。
