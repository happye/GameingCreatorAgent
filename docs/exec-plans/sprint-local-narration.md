# R2-I：本地单段旁白

2026-10-31，Astra/low基于现有混音/版本/发布包架构提出，主控冻结。R2-H真实验证期间可并行开发独立本地合成模块；未接入试听/挂接/渲染前不计配音功能交付。

用户输入文字并选已安装声音，先得到可试听WAV，再挂接剪辑，以输出startFrame定位，原声/配乐/旁白各自音量，保存/移除/祖先恢复与真实MP4可用。不新增EDL schema，不调用付费TTS、不下载声音、不修改系统设置。当前已只读证实SAPI可枚举Huihui中文、Zira/David英文，尚未证明合成与取消。

## 数据与时间

AudioMix原三字段/旧source-v1语义不变，旁白作为并列revision字段narration。省略继承、null移除、对象{assetJobId,receiptSha256,startFrame,gainDb,ducking}替换；gainDb沿-60..0，ducking off|narration-v1，起点为非负严格整数输出帧。一个版本最多一条。

WAV不循环/变速/静默截断。完整样本时长必须满足sample_count/sample_rate <= (output_frames-startFrame)/fps，用有理数/整数比较。超长可试听，但挂接/后续裁短或变速造成超长时明确拒绝，旧版仍可用。混音起点按输出采样率量化，误差不超过一音频样本，收据记录舍入。原source-v1先对BGM压低；narration-v1以未调音量旁白驱动原声+BGM压低，再混入调音量旁白，旁白结束后恢复。无原声/无BGM也能输出。

## 合成资产与I/O

新job kind narration，请求requestId/projectId/text/voiceId。声音来自实际枚举，消失则拒绝、不回退；文字纯文本，不拼PowerShell源码，不开放SSML/XML/rate或任意引擎路径。COM运行于可取消/超时的隔离子进程，文本经UTF8 JSON文件传入，调用明确纯文本模式；仅本任务暂存清理。

creation-narration-receipt-v1绑定job/request/project、text SHA、完整voice token/描述/语言、engine windows-sapi、实际WAV格式/样本数/时长、narration.wav与narration.txt SHA。licenseStatus=unknown，不能据系统存在声音声称商用已授权。WAV是后续唯一音频依据，重启只读回、不能重新合成；同文字的不同输出不冒充同资产。生成不自动挂接剪辑。

纯Application协议拟为LocalVoice、NarrationRequest、NarrationArtifact及validate_narration_fit；Infrastructure提供async list_local_voices与synthesize_local_narration(request,output_directory,context)，固定本地工具/共享可取消进程原语，不写主venv。声音消失/WAV或收据篡改/取消不登记completed，不影响现有成片。

## 集成与验收

独立合成owner：新application/narration.py、infrastructure/sapi_narration.py、项目内SAPI helper脚本和定向测试。任务/版本owner：domain/creation_narration.py、ui/narration_jobs.py、creation_jobs/revision_jobs/server；renderer owner：独立旁白输入/三路混音/收据/文字产物；frontend owner：声音/文字生成、试听/时长、起点/音量/duck/挂接/移除。具体接口实施前协调，不覆盖其他owner。

真实中文声音→非空可解码WAV/文本/样本/SHA；已有成片起点0及非零两例，三路独立音量/duck真实生效；超长拒绝并保存旧SHA；挂接→重启→渲染→祖先→移除通过；失败/取消/声音消失/篡改有行为验证；MP4帧布局不变，文本下载和下游包能消费，声音许可未知保留。旧七文件包严格集合不放宽，若增加narration.txt须显式新包版本/可选文件合同并保留无旁白七文件兼容。刷新0POST、新实例0worker、Provider0。

唯一Sol/high关键评估，主控真实UI验证；P026只能按实际部分交付计数，质量/商用资格仍独立。当前人工0项必做、未来8项、债务10/2/5不变，不要求新素材或费用许可。
