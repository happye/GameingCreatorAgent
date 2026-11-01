// Thin Windows desktop host for the local creation workspace.
//
// Starts the bundled workspace service on a free 127.0.0.1 port inside a kill-on-close Job
// Object, waits for it to answer, then opens one application window. Closing the window (or
// the host) stops the service. Until the WebView2 SDK is approved for download, the window is
// Edge in application mode with its own profile under .cache; the service code is unchanged.
//
// Build: scripts/build-desktop.ps1 (uses the C# compiler that ships with Windows).
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

internal static class GamingCreatorHost
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr CreateJobObject(IntPtr attributes, string name);

    [DllImport("kernel32.dll")]
    private static extern bool SetInformationJobObject(IntPtr job, int infoClass, ref ExtendedLimits info, int length);

    [DllImport("kernel32.dll")]
    private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

    [DllImport("kernel32.dll")]
    private static extern bool TerminateJobObject(IntPtr job, uint exitCode);

    private static bool quiet;
    private static IntPtr job = IntPtr.Zero;

    [StructLayout(LayoutKind.Sequential)]
    private struct BasicLimits
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct IoCounters
    {
        public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount;
        public ulong ReadTransferCount, WriteTransferCount, OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct ExtendedLimits
    {
        public BasicLimits Basic;
        public IoCounters Io;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }

    private const int ExtendedLimitInformation = 9;
    private const uint KillOnJobClose = 0x2000;

    [STAThread]
    private static int Main(string[] args)
    {
        bool smoke = Array.IndexOf(args, "--smoke") >= 0;
        quiet = smoke;
        string root = FindRepository(AppDomain.CurrentDomain.BaseDirectory);
        if (root == null)
        {
            return Fail("找不到工作台目录（缺少 toolchain.json）。请把程序放在项目的 desktop\\bin 目录里运行。");
        }
        string logDirectory = Path.Combine(root, ".cache", "desktop");
        Directory.CreateDirectory(logDirectory);
        string key = Hash(root.ToLowerInvariant());
        bool created;
        using (var mutex = new Mutex(true, "Local\\GamingCreator.Desktop." + key, out created))
        {
            if (!created)
            {
                return Fail("工作台已经在运行，请切换到已打开的窗口。");
            }
            RelocateRuntime(root);
            string python = Path.Combine(root, ".venv", "Scripts", "python.exe");
            if (!File.Exists(python))
            {
                return Fail("缺少项目运行环境（.venv）。请先运行 scripts\\setup-demo.ps1。");
            }
            int port = FreePort();
            string url = "http://127.0.0.1:" + port + "/creation";
            string log = Path.Combine(logDirectory, "host-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".log");
            job = KillOnCloseJob();
            var service = new ProcessStartInfo(python,
                "-B -u -m gamingcreator.ui --host 127.0.0.1 --port " + port + " --repository \"" + root + "\"")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                WorkingDirectory = root,
            };
            service.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
            // A developer shell PYTHONPATH must never redirect the app to another code copy.
            service.EnvironmentVariables.Remove("PYTHONPATH");
            using (var writer = new StreamWriter(log, false, new UTF8Encoding(false)) { AutoFlush = true })
            using (Process server = Process.Start(service))
            {
                AssignProcessToJobObject(job, server.Handle);
                server.OutputDataReceived += (s, e) => { if (e.Data != null) lock (writer) writer.WriteLine(e.Data); };
                server.ErrorDataReceived += (s, e) => { if (e.Data != null) lock (writer) writer.WriteLine(e.Data); };
                server.BeginOutputReadLine();
                server.BeginErrorReadLine();
                if (!WaitReady(url, server, TimeSpan.FromSeconds(60)))
                {
                    Stop(server);
                    return Fail("工作台服务没有启动成功，日志：" + log);
                }
                if (smoke)
                {
                    Console.WriteLine("READY " + url);
                    Stop(server);
                    return 0;
                }
                if (!EmbeddedWindow.Run(url, Path.Combine(logDirectory, "webview2-profile"), server, writer))
                {
                    // Without a usable WebView2 runtime, fall back to an Edge application window.
                    Process window = OpenWindow(url, Path.Combine(logDirectory, "window-profile"));
                    if (window == null)
                    {
                        Stop(server);
                        return Fail("无法打开工作台窗口（WebView2 与 Microsoft Edge 都不可用）。");
                    }
                    using (window)
                    {
                        WaitHandle.WaitAny(new WaitHandle[] { new ProcessWait(window), new ProcessWait(server) });
                    }
                }
                Stop(server);
            }
            return 0;
        }
    }

    private sealed class ProcessWait : WaitHandle
    {
        public ProcessWait(Process process)
        {
            SafeWaitHandle = new Microsoft.Win32.SafeHandles.SafeWaitHandle(process.Handle, false);
        }
    }

    // A copied or moved app folder keeps an absolute interpreter path in pyvenv.cfg; repair it
    // to the bundled runtime inside this folder when the recorded one no longer exists.
    private static void RelocateRuntime(string root)
    {
        string config = Path.Combine(root, ".venv", "pyvenv.cfg");
        string runtimes = Path.Combine(root, ".tools", "python");
        if (!File.Exists(config) || !Directory.Exists(runtimes))
        {
            return;
        }
        string[] lines = File.ReadAllLines(config);
        for (int i = 0; i < lines.Length; i++)
        {
            if (!lines[i].StartsWith("home", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }
            string current = lines[i].Substring(lines[i].IndexOf('=') + 1).Trim();
            if (File.Exists(Path.Combine(current, "python.exe")))
            {
                return;
            }
            foreach (string candidate in Directory.GetDirectories(runtimes))
            {
                if (File.Exists(Path.Combine(candidate, "python.exe")))
                {
                    lines[i] = "home = " + candidate;
                    File.WriteAllLines(config, lines, new UTF8Encoding(false));
                    return;
                }
            }
        }
    }

    private static string FindRepository(string start)
    {
        for (var directory = new DirectoryInfo(start); directory != null; directory = directory.Parent)
        {
            if (File.Exists(Path.Combine(directory.FullName, "toolchain.json")))
            {
                return directory.FullName;
            }
        }
        return null;
    }

    private static string Hash(string text)
    {
        using (var sha = SHA256.Create())
        {
            byte[] digest = sha.ComputeHash(Encoding.UTF8.GetBytes(text));
            return BitConverter.ToString(digest, 0, 8).Replace("-", "");
        }
    }

    private static int FreePort()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        int port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
    }

    private static IntPtr KillOnCloseJob()
    {
        IntPtr job = CreateJobObject(IntPtr.Zero, null);
        var info = new ExtendedLimits();
        info.Basic.LimitFlags = KillOnJobClose;
        SetInformationJobObject(job, ExtendedLimitInformation, ref info, Marshal.SizeOf(typeof(ExtendedLimits)));
        // The handle stays open for the host's lifetime; when the host exits, Windows closes it
        // and terminates the service tree even if the host is killed.
        return job;
    }

    private static bool WaitReady(string url, Process server, TimeSpan timeout)
    {
        DateTime deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            if (server.HasExited)
            {
                return false;
            }
            try
            {
                var request = (HttpWebRequest)WebRequest.Create(url);
                request.Timeout = 2000;
                request.Proxy = null;
                using (var response = (HttpWebResponse)request.GetResponse())
                {
                    if (response.StatusCode == HttpStatusCode.OK)
                    {
                        return true;
                    }
                }
            }
            catch (WebException)
            {
            }
            Thread.Sleep(300);
        }
        return false;
    }

    private static Process OpenWindow(string url, string profile)
    {
        string[] candidates =
        {
            Environment.ExpandEnvironmentVariables(@"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            Environment.ExpandEnvironmentVariables(@"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        };
        foreach (string edge in candidates)
        {
            if (File.Exists(edge))
            {
                // A dedicated profile keeps this window in its own process, so its exit is ours.
                return Process.Start(new ProcessStartInfo(edge,
                    "--app=" + url + " --user-data-dir=\"" + profile + "\" --no-first-run --no-default-browser-check")
                {
                    UseShellExecute = false,
                });
            }
        }
        return null;
    }

    private static void Stop(Process server)
    {
        // The venv python.exe is a launcher with a child interpreter: end the whole job tree.
        if (job != IntPtr.Zero)
        {
            TerminateJobObject(job, 0);
        }
        try
        {
            if (!server.HasExited)
            {
                server.Kill();
                server.WaitForExit(5000);
            }
        }
        catch (InvalidOperationException)
        {
        }
    }

    private static int Fail(string message)
    {
        Console.Error.WriteLine(message);
        if (quiet)
        {
            return 1;
        }
        try
        {
            System.Windows.Forms.MessageBox.Show(message, "游戏创作工作台");
        }
        catch (Exception)
        {
        }
        return 1;
    }
}

// Embedded WebView2 window (SDK pinned in docs/references/webview2-sdk.json).
internal static class EmbeddedWindow
{
    public static bool Run(string url, string profile, Process server, StreamWriter log)
    {
        System.Windows.Forms.Application.EnableVisualStyles();
        var form = new System.Windows.Forms.Form
        {
            Text = "游戏创作工作台",
            Width = 1400,
            Height = 900,
            StartPosition = System.Windows.Forms.FormStartPosition.CenterScreen,
        };
        var view = new Microsoft.Web.WebView2.WinForms.WebView2 { Dock = System.Windows.Forms.DockStyle.Fill };
        form.Controls.Add(view);
        bool started = false;
        Exception failure = null;
        form.Load += async (sender, args) =>
        {
            try
            {
                var environment = await Microsoft.Web.WebView2.Core.CoreWebView2Environment.CreateAsync(null, profile);
                await view.EnsureCoreWebView2Async(environment);
                // Links that leave the local workspace open in the system browser, not inside the app.
                view.CoreWebView2.NewWindowRequested += (s, e) =>
                {
                    e.Handled = true;
                    Process.Start(new ProcessStartInfo(e.Uri) { UseShellExecute = true });
                };
                view.CoreWebView2.Navigate(url);
                started = true;
            }
            catch (Exception error)
            {
                failure = error;
                form.Close();
            }
        };
        server.EnableRaisingEvents = true;
        server.Exited += (sender, args) =>
        {
            if (form.IsHandleCreated)
            {
                form.BeginInvoke(new Action(form.Close));
            }
        };
        System.Windows.Forms.Application.Run(form);
        if (failure != null)
        {
            lock (log)
            {
                log.WriteLine("WebView2 unavailable: " + failure.Message);
            }
        }
        return started;
    }
}
