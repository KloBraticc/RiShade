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
    ("imgui[glfw]",          "ImGui + GLFW Bindings"),
    ("glfw",                 "GLFW Framework"),
    ("PyOpenGL",             "PyOpenGL"),
    ("PyOpenGL-accelerate",  "PyOpenGL Accelerate"),
    ("numpy",                "NumPy"),
    ("psutil",               "Process Utility"),
    ("pywin32",              "Windows API (win32)"),
    ("pywin32-ctypes",       "Win32 C-Types"),
    ("opencv-python",        "OpenCV (Image Processing)"),
    ("dxcam",                "DXCam Screen Capture"),
    ("mss",                  "MSS Capture"),
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
			else
			{
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
            bool robloxRunning = Process.GetProcessesByName("RobloxPlayerBeta").Length > 0;

            if (!robloxRunning)
            {
                AppendLog("Roblox is not running.");
                return;
            }

            string shaderPath = System.IO.Path.Combine(RiShadeDir, "ShaderPy", "ri_shade.py");
            string pythonPath = _resolvedPythonExe ?? "python";

            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = "cmd.exe",
                Arguments = $"/k \"\"{pythonPath}\" \"{shaderPath}\"\"",
                WorkingDirectory = System.IO.Path.GetDirectoryName(shaderPath),
                UseShellExecute = true
            };
            Process.Start(psi);
        };
    });

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
		string? installedVersion = ReadInstalledVersion();

		if (installedVersion == AppVersion)
		{
			SetTitle("Ready to Play!");
			AppendLog("No Updates or Updated packages to install");
			SetProgress(100);
			ShowFinishButton("Start");
			return;
		}

		if (installedVersion != null)
			AppendLog($"Updated: {installedVersion} - {AppVersion}\n");

		AppendLog("Python...");
		string? pythonExe = await FindPython();

		if (pythonExe == null)
		{
			AppendLog("Python not found.");
			AppendLog($"Python {PythonVersion}..\n");
			SetTitle("Python...");

			bool downloaded = await DownloadAndInstallPython();
			if (!downloaded)
			{
				SetTitle("Installation Failed");
				MarkFailed();
				AppendLog("\nCould not install Python automatically.");
				AppendLog("Please install Python 3.11+ manually:");
				AppendLog("https://www.python.org/downloads/");
				ShowFinishButton("Close");
				return;
			}

			AppendLog("\nRe-scanning PATH...");
			pythonExe = await FindPython();

			if (pythonExe == null)
			{
				pythonExe = GetDefaultPythonInstallPath();
				AppendLog($"Using Python at: {pythonExe}");
			}
		}
		else
		{
			AppendLog($"Found Python at: {pythonExe}");
		}

		AppendLog("");
		SetTitle("Upgrading pip...");
		AppendLog("Upgrading pip...");
		await RunCommandAsync(pythonExe, "-m pip install --upgrade pip --quiet", AppendLog);
		AppendLog("pip up to date\n");

		SetTitle("Installing packages...");
		bool anyFailed = false;

		for (int i = 0; i < _packages.Count; i++)
		{
			(string pkg, string display) = _packages[i];
			AppendLog($"[{i + 1}/{_packages.Count}] Installing {display}...");

			bool ok = await InstallPackageAsync(pythonExe, pkg, AppendLog);

			if (!ok)
			{
				AppendLog($"{display} may have failed, continuing.");
				anyFailed = true;
			}
			else
			{
				AppendLog($"{display} installed.");
			}

			AppendLog("");
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
		SetTitle("Downloading ri_shader.py...");
		await DownloadRiShadeScript();
		SetProgress(100);
        SetTitle("Ready to Play!");
        ShowFinishButton("Start");
	}

	private async Task DownloadRiShadeScript()
	{
		try
		{
			string shaderDir = System.IO.Path.Combine(
				Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
				"Rishade",
				"ShaderPy");

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

	private async Task<bool> DownloadAndInstallPython()
	{
		string tempPath = System.IO.Path.Combine(System.IO.Path.GetTempPath(), $"python-{PythonVersion}-amd64.exe");

		try
		{
			using (HttpClient client = new HttpClient())
			{
				client.Timeout = TimeSpan.FromMinutes(10);
				AppendLog($"Saving to: {tempPath}");

				using (HttpResponseMessage response = await client.GetAsync(
					PythonInstallerUrl, HttpCompletionOption.ResponseHeadersRead))
				{
					response.EnsureSuccessStatusCode();
					long? total = response.Content.Headers.ContentLength;

					using (Stream stream = await response.Content.ReadAsStreamAsync())
					using (FileStream file = File.Create(tempPath))
					{
						byte[] buffer = new byte[81920];
						long downloaded = 0;
						int read;

						while ((read = await stream.ReadAsync(buffer)) > 0)
						{
							await file.WriteAsync(buffer.AsMemory(0, read));
							downloaded += read;

							if (total.HasValue)
							{
								double pct = downloaded / (double)total.Value * 100.0;
								SetProgress(pct);
								Dispatcher.UIThread.Post(() =>
									this.FindControl<TextBlock>("InstallTitle")!.Text =
										$"Python... {pct:0}%");
							}
						}
					}
				}
			}

			AppendLog("complete");
			AppendLog("Python installer (this may take a minute)...");
			SetTitle("Python...");
			SetProgress(0);

			ProcessStartInfo psi = new ProcessStartInfo(tempPath,
				"/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_doc=0")
			{
				UseShellExecute = true,
				Verb = "runas",
				CreateNoWindow = false,
			};

			using (Process? proc = Process.Start(psi))
			{
				if (proc == null) { AppendLog("Could not start installer."); return false; }
				await proc.WaitForExitAsync();

				if (proc.ExitCode != 0)
				{
					AppendLog($"Python exited with code {proc.ExitCode}.");
					return false;
				}
			}

			AppendLog($"Python {PythonVersion} installed");
			return true;
		}
		catch (Exception ex)
		{
			AppendLog($"Download/install failed: {ex.Message}");
			return false;
		}
		finally
		{
			try { if (File.Exists(tempPath)) File.Delete(tempPath); } catch { }
		}
	}

	private static string GetDefaultPythonInstallPath()
	{
		string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
		string guess = System.IO.Path.Combine(local, "Programs", "Python", "Python311", "python.exe");
		return File.Exists(guess) ? guess : "python";
	}

	private static async Task<string?> FindPython()
	{
		string[] candidates = new string[] { "python", "python3", "py" };
		foreach (string candidate in candidates)
		{
			try
			{
				ProcessStartInfo psi = new ProcessStartInfo(candidate, "--version")
				{
					RedirectStandardOutput = true,
					RedirectStandardError = true,
					UseShellExecute = false,
					CreateNoWindow = true,
				};
				using (Process? proc = Process.Start(psi))
				{
					if (proc == null) continue;
					await proc.WaitForExitAsync();
					if (proc.ExitCode == 0) return candidate;
				}
			}
			catch { }
		}
		return null;
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

				proc.OutputDataReceived += (object sender, DataReceivedEventArgs e) => { if (e.Data != null) log($"  {e.Data}"); };
				proc.ErrorDataReceived += (object sender, DataReceivedEventArgs e) => { if (e.Data != null) log($"  {e.Data}"); };
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

				proc.OutputDataReceived += (object sender, DataReceivedEventArgs e) => { if (e.Data != null) log($"  {e.Data}"); };
				proc.ErrorDataReceived += (object sender, DataReceivedEventArgs e) => { if (e.Data != null) log($"  {e.Data}"); };
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