# R2-F：逐镜头变速与字幕/原声同步

2026-10-31，Astra/low已给源/输出时钟方案，主控持久化。目标0.5x/1x/2x实际生效、保存/祖先撤销/重渲染，延续全部51项路线。P028/P032仍部分，不因内部子项虚增。

新修订EDL edit-decision-revision-v2；新clips每项exact `{clipId,startUs,endUs,speed:{numerator,denominator}}`。speed仅严格整数对1/2、1/1、2/1，禁止bool/float/别的比例。服务端outputFrames=floor((endUs-startUs)*fps*den/(1000000*num))，不足一帧拒绝，尾余量<1输出帧舍弃。累计输出起点只加整数帧。稳定clipId/parent唯一非空子集、父源区间裁短、root/run/media/event/SHA/evidence不改；v2放开的是输出帧不能变长限制，不能扩大源范围。显式手动慢放可超过原Brief目标，显示实际差异，不改原目标/事实。

旧v1请求/EDL/收据保持原字节且可读，缺速率按1x仅解释旧版本；v2必须显式speed。原根validate_render_plan等于已选规划的保护不放宽。RenderClip.speed新增Fraction(1,1)默认，类型/三个允许值校验；v2派生/严格重建比对，再交renderer。

画面先按原source origin/PTS裁切，再setpts除speed，再fps/缩放/固定帧数。原声按现有绝对秒裁切/原clock补齐，再atempo保音高、补尾/裁至outputFrames/fps；禁止改采样率伪变速。ASR求源交集后offset+(sourceUs-startUs)/1000000/speed，clip到实际输出终点；用户整镜头字幕覆盖全输出片段。BGM继续最终输出clock，不随速率变调；duck使用变速后的原声。

归属：Sol/medium clip-speed-core树：creation_editing/rendering/revision_jobs及核心测试；Sol/medium clip-speed-render树：creation_subtitles/ffmpeg_render及真实音视频/字幕测试，依赖冻结RenderClip.speed；Sol/medium clip-speed-frontend树：creation静态及browser/mock，新源入出点+速率请求，不把旧outputFrames当源长度。独立worktree、保留他人、不递归；主控集成/实际工作台，唯一Sol/high评估来源/时钟/身份。

验收：两个颜色镜头各0.5/2倍输出切换帧精确；源字幕位置按倍速、手写覆盖完整；已知音调频率保持而时长变化；非零origin/延迟音频/无声/原声+BGM实际验证；0.5→2→祖先恢复不改源/证据；旧v1回读/下载兼容，越父范围/错帧/伪速率拒绝。封面/平台包读新总frames保持输出fps。必要定向/实际产物验证，无新模型/下载/原库写，不重复旧全量。

## 已交付与证据

2026-10-31逐镜头变速已交，Goal active：0.5x/1x/2x保存v2源区间/速率，画面与保音高原声/字幕同步，配乐保持输出时钟。138主树联合、19最终渲染增量、5源码mypy/Ruff通过；Sol/high首次核查发现尾补P2后额度限制，已披露改由Astra/low最终增量限定PASS，不冒称Sol复核通过。真实UI40→17→祖先35帧、SRT1.000/.233/.500秒、BGM继承、旧文件/刷新/新实例通过；40帧新成片末帧封面与包亦通过。P028/P029/P032仍部分，51项10/19/22≈38%、首产品27%不虚增；人工0必做/未来8、技术债10/2/5不变，产品Provider新请求0。下一转场/候选替换。

两个阻断已解决且未放宽frame gate：2秒视频/2.75秒音轨，.5x由100改到计划110帧；真实30+10片段最终39帧，现manifest明确duration、有限输出帧及完整音频flush后40帧/1.333秒，两流0起点。19最终native包含14speed/5旧兼容、55/110帧、30fps40/18帧、29fps14帧颜色边界及AAC1024样本界限。原失败7014现场未改，另隔离复用验证。.5/2音调440Hz/BGM880Hz保持，非零origin/PCM/无音轨/已知起始静音/内部脉冲样例通过；不声称任意内部瞬态或每个独特源帧已sampleexact。

真实UI三渲染40/17/35帧，首字幕1.000/.233/.500秒，源区间/字幕文字/配乐/旧文件保持；刷新0POST/新实例0worker，手机截图已看。新40帧成片取末帧39并打包仍40帧，test_only资格blocked。临时服务关闭，无新Provider或外部动作。Sol/high最终usage_limit事实保留，不替其声明PASS；Astra/low静态最终增量限定PASS。
