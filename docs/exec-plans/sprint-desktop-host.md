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
