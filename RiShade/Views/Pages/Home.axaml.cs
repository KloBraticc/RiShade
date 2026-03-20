using Avalonia.Controls;
using Avalonia.Controls.Shapes;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Threading;
using Microsoft.Win32;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;

namespace Rishade.Views;

public partial class Home : UserControl
{
    private int _step = 1;
    private string? _resolvedPythonExe;
    private SolidColorBrush _accent = new SolidColorBrush(Color.Parse("#0078D4"));

    private const string RepoOwner = "KloBraticc";
    private const string RepoName = "RiShade";
    private string? _originalUserPath;

    private static readonly string AppVersion =
        System.Reflection.Assembly.GetExecutingAssembly()
            .GetName().Version?.ToString() ?? "1.0.0.0";

    private const string PythonVersion = "3.11.9";
    private const string PythonInstallerUrl =
        "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe";

    private static readonly string RiShadeDir =
        System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "RiShade");
    private static readonly string InstallerJsonPath =
        System.IO.Path.Combine(RiShadeDir, "installer.json");

    private readonly List<(string package, string display)> _packages = new List<(string package, string display)>()
    {
        ("setuptools",           "Setup Tools"),
        ("wheel",                "Wheel Optimizer"),
        ("imgui",                "ImGui"),
        ("glfw",                 "GLFW Framework"),
        ("numpy",                "NumPy"),
        ("PyOpenGL",             "PyOpenGL"),
        ("PyOpenGL-accelerate",  "PyOpenGL Accelerate"),
        ("psutil",               "Process Utility"),
        ("pywin32",              "Windows API (win32)"),
        ("requests",             "Requests HTTP"),
        ("dxcam",                "DXCam Screen Capture"),
        ("mss",                  "MSS Capture"),
        ("pyyaml",               "PyYAML"),
        ("opencv-python",        "OpenCV (cv2)"),
    };

    public Home()
    {
        InitializeComponent();
        _accent = new SolidColorBrush(GetWindowsAccentColor());
        ApplyAccent();

        Button nextBtn = this.FindControl<Button>("NextBtn")!;
        nextBtn.Click += OnNextClick;

        Dispatcher.UIThread.Post(async () =>
        {
            await CheckForUpdatesAsync();

            string? installedVersion = ReadInstalledVersion();
            if (installedVersion == AppVersion)
            {
                await Task.Delay(50);
                nextBtn.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            }
        });
    }

    private async Task CheckForUpdatesAsync()
    {
        try
        {
            using HttpClient client = new HttpClient();
            client.DefaultRequestHeaders.Add("User-Agent", "RiShade-Updater");

            string url = $"https://api.github.com/repos/{RepoOwner}/{RepoName}/releases/latest";
            string response = await client.GetStringAsync(url);

            using JsonDocument doc = JsonDocument.Parse(response);
            string latestTag = doc.RootElement.GetProperty("tag_name").GetString() ?? "1.0.0.0";
            string cleanTag = latestTag.TrimStart('v');

            Version current = new Version(AppVersion);
            Version latest = new Version(cleanTag);

            if (latest > current)
            {
                AppendLog($"New version found: {latestTag}");

                string downloadUrl = "";
                foreach (var asset in doc.RootElement.GetProperty("assets").EnumerateArray())
                {
                    if (asset.GetProperty("name").GetString() == "Rishade.exe")
                    {
                        downloadUrl = asset.GetProperty("browser_download_url").GetString()!;
                        break;
                    }
                }

                if (!string.IsNullOrEmpty(downloadUrl))
                {
                    await DownloadAndRunUpdate(downloadUrl);
                }
            }
        }
        catch (Exception ex)
        {
            AppendLog($"Update check failed: {ex.Message}");
        }
    }

    private async Task DownloadAndRunUpdate(string url)
    {
        SetTitle("Updating");
        string tempExe = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "Rishade_New.exe");

        using (HttpClient client = new HttpClient())
        {
            var data = await client.GetByteArrayAsync(url);
            await File.WriteAllBytesAsync(tempExe, data);
        }

        Process.Start(new ProcessStartInfo
        {
            FileName = tempExe,
            UseShellExecute = true
        });

        Environment.Exit(0);
    }

    private static Color GetWindowsAccentColor()
    {
        try
        {
            using (RegistryKey? key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\DWM"))
            {
                if (key?.GetValue("AccentColor") is int raw)
                {
                    byte b = (byte)((raw >> 16) & 0xFF);
                    byte g = (byte)((raw >> 8) & 0xFF);
                    byte r = (byte)((raw) & 0xFF);
                    return Color.FromArgb(255, r, g, b);
                }
            }
        }
        catch { }
        return Color.Parse("#0078D4");
    }

    private void ApplyAccent()
    {
        this.FindControl<Ellipse>("Dot1")!.Fill = _accent;
        this.FindControl<Button>("NextBtn")!.Background = _accent;
        this.FindControl<ProgressBar>("InstallProgress")!.Foreground = _accent;
    }

    private void OnNextClick(object? sender, RoutedEventArgs e)
    {
        if (_step == 1)
        {
            _step = 2;
            UpdateStep();
            _ = RunInstall();
        }
    }

    private void UpdateStep()
    {
        this.FindControl<StackPanel>("Page1")!.IsVisible = _step == 1;
        this.FindControl<StackPanel>("Page2")!.IsVisible = _step == 2;
        this.FindControl<Button>("NextBtn")!.IsVisible = _step == 1;

        Color winAccent = GetWindowsAccentColor();
        this.FindControl<Ellipse>("Dot1")!.Fill = new SolidColorBrush(
            _step == 1 ? winAccent : Color.Parse("#444444"));
        this.FindControl<Ellipse>("Dot2")!.Fill = new SolidColorBrush(
            _step == 2 ? winAccent : Color.Parse("#444444"));
    }

    private void AppendLog(string line) => Dispatcher.UIThread.Post(() =>
    {
        TextBox box = this.FindControl<TextBox>("LogBox")!;
        box.Text += line + "\n";
        box.CaretIndex = int.MaxValue;
    });

    private void SetProgress(double val) => Dispatcher.UIThread.Post(() =>
        this.FindControl<ProgressBar>("InstallProgress")!.Value = val);

    private void SetTitle(string t) => Dispatcher.UIThread.Post(() =>
        this.FindControl<TextBlock>("InstallTitle")!.Text = t);

    private void MarkFailed() => Dispatcher.UIThread.Post(() =>
        this.FindControl<ProgressBar>("InstallProgress")!.Foreground =
            new SolidColorBrush(Color.Parse("#EF4444")));

    private void ShowFinishButton(string label) => Dispatcher.UIThread.Post(() =>
    {
        Button btn = this.FindControl<Button>("NextBtn")!;
        btn.Content = label;
        btn.IsVisible = true;
        btn.Click -= null;

        btn.Click += (object? sender, RoutedEventArgs args) =>
        {
            string shaderPath = System.IO.Path.Combine(RiShadeDir, "ShaderPy", "ri_shade.py");
            string pythonPath = _resolvedPythonExe ?? GetPython311Path();

            AppendLog($"Running: {pythonPath} \"{shaderPath}\"");

            try
            {
                ProcessStartInfo psi = new ProcessStartInfo
                {
                    FileName = "cmd.exe",
                    Arguments = $"/k \"\"{pythonPath}\" \"{shaderPath}\"\"",
                    WorkingDirectory = System.IO.Path.GetDirectoryName(shaderPath),
                    UseShellExecute = true
                };
                Process.Start(psi);
            }
            catch (Exception ex)
            {
                AppendLog($"Failed to start ri_shade.py: {ex.Message}");
            }
        };
    });

    private void RemoveStorePythonFromPath()
    {
        try
        {
            using RegistryKey? key = Registry.CurrentUser.OpenSubKey(
                @"Environment", writable: true);
            if (key == null) return;

            _originalUserPath = key.GetValue("PATH") as string;
            if (string.IsNullOrEmpty(_originalUserPath)) return;

            string[] parts = _originalUserPath.Split(';');
            string newPath = string.Join(';', Array.FindAll(parts, p => !p.Contains("WindowsApps\\Python", StringComparison.OrdinalIgnoreCase)));

            key.SetValue("PATH", newPath, RegistryValueKind.String);
            AppendLog("Temporarily removed Microsoft Store Python from PATH.");
        }
        catch (Exception ex)
        {
            AppendLog($"Failed to remove Store Python from PATH: {ex.Message}");
        }
    }

    private void RestoreOriginalPath()
    {
        try
        {
            if (_originalUserPath == null) return;

            using RegistryKey? key = Registry.CurrentUser.OpenSubKey(
                @"Environment", writable: true);
            if (key == null) return;

            key.SetValue("PATH", _originalUserPath, RegistryValueKind.String);
            AppendLog("Restored original PATH.");
        }
        catch (Exception ex)
        {
            AppendLog($"Failed to restore PATH: {ex.Message}");
        }
    }

    private static string? ReadInstalledVersion()
    {
        try
        {
            if (!File.Exists(InstallerJsonPath)) return null;
            string json = File.ReadAllText(InstallerJsonPath);
            using (JsonDocument doc = JsonDocument.Parse(json))
            {
                return doc.RootElement.GetProperty("version").GetString();
            }
        }
        catch { return null; }
    }

    private void WriteInstalledVersion()
    {
        try
        {
            Directory.CreateDirectory(RiShadeDir);
            string json = $"{{\n  \"version\": \"{AppVersion}\"\n}}";
            File.WriteAllText(InstallerJsonPath, json);
            AppendLog($"Version {AppVersion} to {InstallerJsonPath}");
        }
        catch (Exception ex)
        {
            AppendLog($"WriteInstalledVersion failed: {ex.Message}");
        }
    }

    private async Task RunInstall()
    {
        RemoveStorePythonFromPath();
        try
        {
            SetTitle("Installing Python 3.11...");
            _resolvedPythonExe = await EnsurePython311Installed();
            AppendLog($"Using Python at: {_resolvedPythonExe}");
            SetTitle("Upgrading pip...");
            await RunCommandAsync(_resolvedPythonExe, "-m ensurepip --upgrade", AppendLog);
            await RunCommandAsync(_resolvedPythonExe, "-m pip install --upgrade pip", AppendLog);

            SetTitle("Installing packages...");
            bool anyFailed = false;

            for (int i = 0; i < _packages.Count; i++)
            {
                (string pkg, string display) = _packages[i];
                AppendLog($"[{i + 1}/{_packages.Count}] Installing {display}...");

                bool ok = await InstallPackageAsync(_resolvedPythonExe, pkg, AppendLog);
                if (!ok)
                {
                    AppendLog($"{display} may have failed, continuing.");
                    anyFailed = true;
                }
                else
                {
                    AppendLog($"{display} installed.");
                }

                SetProgress((i + 1.0) / _packages.Count * 100.0);
            }

            if (anyFailed)
            {
                SetTitle("Installed with warnings");
                AppendLog("Finished with warnings | check above.");
            }
            else
            {
                SetTitle("Complete");
                AppendLog("All packages installed");
            }

            WriteInstalledVersion();
            SetProgress(94);
            SetTitle("Downloading ri_shade.py...");
            await DownloadRiShadeScript();
            SetProgress(100);
            SetTitle("Ready to Play!");
            ShowFinishButton("Start");
        }
        finally
        {
            RestoreOriginalPath();
        }
    }

    private async Task<string> EnsurePython311Installed()
    {
        string targetDir = System.IO.Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Programs", "Python", "Python311");

        string pythonExe = System.IO.Path.Combine(targetDir, "python.exe");
        if (File.Exists(pythonExe))
        {
            return pythonExe;
        }

        string installerPath = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "python311_installer.exe");
        AppendLog("Downloading Python 3.11.9 installer...");
        using (HttpClient client = new HttpClient())
        {
            var data = await client.GetByteArrayAsync(PythonInstallerUrl);
            await File.WriteAllBytesAsync(installerPath, data);
        }

        AppendLog("Installing Python 3.11.9...");
        Process installer = Process.Start(new ProcessStartInfo
        {
            FileName = installerPath,
            Arguments = $"/quiet InstallAllUsers=0 TargetDir=\"{targetDir}\" PrependPath=0 Include_pip=1",
            UseShellExecute = true
        })!;
        installer.WaitForExit();

        if (!File.Exists(pythonExe))
            throw new Exception("Python 3.11 installation failed.");

        return pythonExe;
    }

    private async Task DownloadRiShadeScript()
    {
        try
        {
            string shaderDir = System.IO.Path.Combine(RiShadeDir, "ShaderPy");
            Directory.CreateDirectory(shaderDir);

            string filePath = System.IO.Path.Combine(shaderDir, "ri_shade.py");
            string url = "https://raw.githubusercontent.com/KloBraticc/RiShade/main/Files/ri_shade.py";

            AppendLog("Downloading ri_shade.py...");

            using (HttpClient client = new HttpClient())
            {
                byte[] data = await client.GetByteArrayAsync(url);
                await File.WriteAllBytesAsync(filePath, data);
            }
        }
        catch (Exception ex)
        {
            AppendLog($"Failed to download ri_shade.py: {ex.Message}");
        }
    }

    private static string GetPython311Path()
    {
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string path = System.IO.Path.Combine(local, "Programs", "Python", "Python311", "python.exe");
        return File.Exists(path) ? path : throw new Exception("Python 3.11 not found");
    }

    private static async Task RunCommandAsync(string exe, string args, Action<string> log)
    {
        try
        {
            ProcessStartInfo psi = new ProcessStartInfo(exe, args)
            {
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            using (Process? proc = Process.Start(psi))
            {
                if (proc == null) return;

                proc.OutputDataReceived += (s, e) => { if (e.Data != null) log($"  {e.Data}"); };
                proc.ErrorDataReceived += (s, e) => { if (e.Data != null) log($"  {e.Data}"); };
                proc.BeginOutputReadLine();
                proc.BeginErrorReadLine();
                await proc.WaitForExitAsync();
            }
        }
        catch (Exception ex) { log($"  Exception {ex.Message}"); }
    }

    private static async Task<bool> InstallPackageAsync(string python, string package, Action<string> log)
    {
        try
        {
            ProcessStartInfo psi = new ProcessStartInfo(python,
                $"-m pip install {package} --no-warn-script-location")
            {
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            using (Process? proc = Process.Start(psi))
            {
                if (proc == null) return false;

                proc.OutputDataReceived += (s, e) => { if (e.Data != null) log($"  {e.Data}"); };
                proc.ErrorDataReceived += (s, e) => { if (e.Data != null) log($"  {e.Data}"); };
                proc.BeginOutputReadLine();
                proc.BeginErrorReadLine();
                await proc.WaitForExitAsync();
                return proc.ExitCode == 0;
            }
        }
        catch (Exception ex)
        {
            log($"  Exception {ex.Message}");
            return false;
        }
    }
}