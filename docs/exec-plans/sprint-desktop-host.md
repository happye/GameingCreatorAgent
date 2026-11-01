# P039（R4第一步）：桌面EXE薄宿主

2026-11-01，Claude Code主控实现，单Agent（边界：进程生命周期，已用真实窗口与冒烟测试核对）。

## 合同

- desktop/host/GamingCreatorHost.cs，scripts/build-desktop.ps1用%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe编译，产物desktop/bin已忽略不入库。
- 单实例（按仓库路径哈希的Local互斥体）；随机空闲端口、只绑127.0.0.1；服务进程放入kill-on-close Job Object，停止时TerminateJobObject结束launcher与解释器。
- 就绪探测/creation返回200后才开窗；窗口=系统Edge --app，独立--user-data-dir在.cache/desktop；窗口或服务任一退出即全部停止。
- --smoke：启动→就绪→打印READY地址→停止，不开窗、不弹框。
- 不下载组件；WebView2 SDK下载已登记human-inputs待批准。

## 结果

2026-11-01桌面EXE薄宿主（P039部分，首产品★）：新增desktop/bin/GamingCreator.exe，用Windows自带C#编译器（scripts/build-desktop.ps1，不下载任何组件）生成；双击后单实例运行，在随机空闲端口只绑127.0.0.1启动工作台服务（Windows Job Object关窗即连同解释器子进程一起结束），等服务就绪后打开独立应用窗口，日志进.cache/desktop。当前窗口暂用系统Edge应用模式（独立配置目录），内嵌WebView2需先下载WebView2 SDK——已按规则登记为待你批准的下载事项（未来人工8→9项，不紧急，只阻断内嵌窗口替换）。实测：--smoke启动→就绪→停止且无残留进程；真实双击打开Edge应用窗口→关窗后宿主退出、服务进程0残留；第二实例被拒绝。2项桌面测试通过。仍未做：打包Python核心与运行时的安装器、干净机器安装/升级/卸载、代码签名与组件许可证材料。51项10/30/11≈49%，首产品22项0/22/0≈50%（全部至少部分可用）；人工0/未来9、债务20项11/2/7。

## 追加：内嵌WebView2

2026-11-01 P039推进：用户批准下载WebView2 SDK后，从nuget.org下载固定版本Microsoft.Web.WebView2 1.0.4314.35（与本机WebView2运行时156.0.4314同代），SHA512与NuGet公布值及大小一致，只解出net462的Core/WinForms托管库、x64 WebView2Loader与许可证到.tools/webview2（项目本地、不入库），固定版本与逐文件SHA256记在docs/references/webview2-sdk.json，每次构建先核对。桌面EXE改为内嵌WebView2窗口（独立用户数据目录.cache/desktop/webview2-profile，站外链接交给系统浏览器）；WebView2不可用时才退回Edge应用窗口。实测：标题“游戏创作工作台”的宿主窗口内运行6个WebView2进程、无Edge应用窗口，页面200；关窗后宿主退出、服务与WebView2进程0残留；冒烟与单实例2项测试通过。人工待办WebView2许可已完成：未来人工9→8项。仍未做：安装包与干净机器、签名、WebView2运行时随包分发及许可证材料核对。计数不变：51项10/41/0≈60%。

## 追加：便携应用目录

2026-11-01 P039推进（R4便携应用目录）：新增scripts/build-app.ps1，组装自包含的dist/GamingCreator（git已忽略）：固定Python运行时、去掉pytest/mypy/ruff/hatchling等开发工具的运行依赖、程序以普通包装入（不再链接本仓库源码）、FFmpeg、桌面EXE与WebView2库；总大小上限1.5GB（实测660MB），目录已存在且不是本脚本生成则拒绝覆盖，失败即删除半成品。两处按源码目录推算脚本位置的代码改为统一查找（仓库scripts/或应用目录scripts/）；宿主启动服务时清除PYTHONPATH，并在应用目录被移动后自动把pyvenv.cfg指回目录内运行时。实测：打包后的Python从应用目录加载程序与依赖（numpy/httpx/onnxruntime等），-Smoke就绪；把目录改名移动后仍能启动（自动修正运行时路径）。仍未做：真正的安装程序/卸载/升级、另一台干净机器实测、代码签名、WebView2运行时与第三方许可证随包材料；ASR/嵌入模型（.cache/models）未打包，新录像分析仍需在开发环境准备。计数不变：51项10/41/0≈60%。
