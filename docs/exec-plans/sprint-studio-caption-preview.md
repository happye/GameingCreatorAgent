# Studio 草稿字幕即时预览

2026-11-07，延续R2/P029：已保存的逐镜字幕可导出，但方案播放器仍不显示字幕。不能把旧版本输出cue直接套到重排、变速或替换后的草稿。

## 合同与归属

- Sol/medium唯一实施树`.worktrees/j1-preview-corrections`、分支`codex/studio-caption-preview-20261107`，已合运行时身份711734f与字幕e98e913；parent持文档和root集成。不得修改root受测源码，不复制其他工具角色。
- 只读草稿预览POST：核项目、方案、父摘要，复用prepare_revision/resolve_overrides及真实渲染相同的转录选择/build_subtitles。普通与v4替换链均支持。只返回内存cue，不登记job/修订、不写转录/账本、不调用模型。
- 返回半开输出微秒区间与文本/抬高层位。none清空；SRT复用毫秒向下取整/零长过滤；burn复用ASS百分秒取整、重叠分段、早镜头抬高和安全字符替换。不得改变现有SRT/ASS导出结果；浏览器文字排版仅预览内容和时机。
- 方案播放器按player.outUs显示实际shownClips草稿，含助手未应用预览；字幕覆盖过滤已删除镜头，替换沿既有身份规则。请求键绑定项目、父job/摘要、方案、模式与有效草稿；250ms防抖，换键立即隐旧cue，abort+序号拒迟到响应。播放、定位、选镜头不触发新POST。
- 无转录/none/错误/加载状态明确；不显示过期字幕。旧版本无覆盖保持继承。尽量复用严格读取，不另增逐字段hash，不削弱已有媒体/身份/预算门禁。

## 验收与边界

1. 对同一草稿的真实本地SRT/烧录导出核对文本、量化边界、转场双字幕层位；覆盖重复素材/变速/替换run/手写/隐藏/恢复自动/极短cue及ASS特殊字符。
2. HTTP错项目/父摘要/未知clip/过期replacement manifest拒绝；预览前后job、修订、转录、账本不变。相关后端回归串行跑。
3. 浏览器暂停定位、修改/模式切换立即失效、防抖及跨项目迟到响应不污染；已有保存/重开/替换与播放回归保留。
4. 子树env后显式PYTHONPATH为自身src并核import；只定向测试，root完整门禁由parent执行。唯一Sol/high评估身份/时钟/只读边界，不叠普通reviewer。人工观感/真实模型质量继续未验收。

## 独立树交接证据

后端111通过/0跳过、70.651秒（`.cache/caption-preview-backend-final.xml`）；浏览器12通过/0跳过、54.266秒（`.cache/caption-preview-browser-combined.xml`）。同一v4替换B run、2x速度和3帧转场草稿串接真实SRT/送FFmpeg的ASS事件/MP4双层像素；重复A/A/B重排转录、继承及删镜覆盖、sourcePath注入和旧v4身份拒绝均有证据。浏览器忽略abort的迟到成功/失败覆盖project/parent/none，防抖和暂停定位通过。字体像素排版不作同等承诺。

唯一Sol/high曾发现旁白依赖走jobs.get导致恢复写盘的P2；复现失败XML保留，现load_chain/resolve/asset只读模式贯穿，旁白pending/running/interrupted均拒绝且全库文件字节不变。默认正常调用仍保留恢复行为。专项复核通过，无未修复缺陷；Ruff/format/mypy5源/diff检查通过。根目录完整门禁与main集成仍待完成，不提升P029整体交付或人评状态。
