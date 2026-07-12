# Sentinel stack startup splash — custom-painted UI matching brand splash design.

param(
    [switch]$Elevated
)

$ErrorActionPreference = "Continue"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$ScriptsDir = $PSScriptRoot
$MonitorRoot = Split-Path -Parent $ScriptsDir
$StartScript = Join-Path $ScriptsDir "start-gnbot-stack.ps1"
$LogDir = Join-Path $MonitorRoot "logs"
$script:StatusFile = Join-Path $LogDir "stack-splash.status"
$VersionFile = Join-Path $MonitorRoot "VERSION"

$script:AppVersion = "v1.0.0"
if (Test-Path $VersionFile) {
    $rawVer = (Get-Content $VersionFile -Raw).Trim()
    if ($rawVer) { $script:AppVersion = if ($rawVer.StartsWith("v")) { $rawVer } else { "v$rawVer" } }
}

$logoCandidates = @(
    (Join-Path $MonitorRoot "static\splash\sentinel-logo.png"),
    (Join-Path $ScriptsDir "..\static\splash\sentinel-logo.png")
)
$script:LogoPath = $logoCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not ([System.Management.Automation.PSTypeName]"Sentinel.SplashCanvas").Type) {
    try {
        Add-Type -ReferencedAssemblies System.Drawing, System.Windows.Forms -TypeDefinition @"
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.Windows.Forms;

namespace Sentinel {
    public class SplashCanvas : Control {
        private Image _logo;
        private int _progress = 5;
        private string _status = "INITIALIZING SYSTEM...";

        public int ProgressPercent {
            get { return _progress; }
            set { _progress = Math.Max(0, Math.Min(100, value)); Invalidate(); }
        }

        public string StatusText {
            get { return _status; }
            set { _status = string.IsNullOrWhiteSpace(value) ? "INITIALIZING SYSTEM..." : value.ToUpperInvariant(); Invalidate(); }
        }

        public string VersionText { get; set; }

        public SplashCanvas() {
            VersionText = "v1.0.0";
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            BackColor = Color.FromArgb(8, 12, 24);
            Font = new Font("Segoe UI", 9f);
        }

        public void SetLogo(Image img) {
            if (_logo != null) _logo.Dispose();
            _logo = ProcessLogoTransparency(img);
            Invalidate();
        }

        private static Image ProcessLogoTransparency(Image source) {
            var src = new Bitmap(source);
            var bitmap = new Bitmap(src.Width, src.Height, PixelFormat.Format32bppArgb);
            for (int y = 0; y < src.Height; y++) {
                for (int x = 0; x < src.Width; x++) {
                    Color c = src.GetPixel(x, y);
                    int avg = (c.R + c.G + c.B) / 3;
                    int spread = Math.Max(c.R, Math.Max(c.G, c.B)) - Math.Min(c.R, Math.Min(c.G, c.B));
                    bool isBackground = c.A < 16 || (avg > 170 && spread < 40);
                    bitmap.SetPixel(x, y, isBackground ? Color.FromArgb(0, 0, 0, 0) : c);
                }
            }
            src.Dispose();
            source.Dispose();
            return bitmap;
        }

        protected override void Dispose(bool disposing) {
            if (disposing && _logo != null) _logo.Dispose();
            base.Dispose(disposing);
        }

        private static void FillRoundedRect(Graphics g, Brush brush, RectangleF r, float radius) {
            using (var path = RoundedRect(r, radius))
                g.FillPath(brush, path);
        }

        private static GraphicsPath RoundedRect(RectangleF r, float radius) {
            var path = new GraphicsPath();
            float d = radius * 2f;
            path.AddArc(r.X, r.Y, d, d, 180, 90);
            path.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            path.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            path.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            path.CloseFigure();
            return path;
        }

        private void DrawBackground(Graphics g, Rectangle b) {
            using (var bg = new LinearGradientBrush(b, Color.FromArgb(10, 14, 28), Color.FromArgb(4, 6, 14), 90f))
                g.FillRectangle(bg, b);

            int cx = b.Width / 2;
            int cy = (int)(b.Height * 0.28);
            using (var pen = new Pen(Color.FromArgb(28, 99, 102, 241), 1f)) {
                for (int i = 1; i <= 4; i++) {
                    int r = 60 + i * 38;
                    g.DrawEllipse(pen, cx - r, cy - r, r * 2, r * 2);
                }
            }

            // HUD ticks
            using (var pen = new Pen(Color.FromArgb(35, 59, 130, 246), 1f)) {
                for (int a = 0; a < 360; a += 30) {
                    double rad = a * Math.PI / 180.0;
                    int r1 = 95, r2 = 105;
                    g.DrawLine(pen,
                        cx + (int)(r1 * Math.Cos(rad)), cy + (int)(r1 * Math.Sin(rad)),
                        cx + (int)(r2 * Math.Cos(rad)), cy + (int)(r2 * Math.Sin(rad)));
                }
            }

            DrawWaveMesh(g, b);
        }

        private void DrawWaveMesh(Graphics g, Rectangle b) {
            int baseY = (int)(b.Height * 0.72);
            int w = b.Width;
            using (var pen = new Pen(Color.FromArgb(40, 129, 140, 248), 1f))
            using (var brush = new SolidBrush(Color.FromArgb(90, 56, 189, 248))) {
                for (int x = 0; x < w; x += 14) {
                    for (int row = 0; row < 5; row++) {
                        double t = (x + row * 7) * 0.03;
                        int y = baseY + row * 16 + (int)(Math.Sin(t) * 10) + (int)(Math.Cos(t * 0.7) * 6);
                        float size = 2f + (row % 2);
                        float alpha = 40 + row * 12;
                        using (var dot = new SolidBrush(Color.FromArgb((int)alpha, 56 + row * 20, 120 + row * 15, 248)))
                            g.FillEllipse(dot, x, y, size, size);
                    }
                }
            }
        }

        private void DrawLogo(Graphics g, Rectangle b) {
            int size = 148;
            int x = (b.Width - size) / 2;
            int y = (int)(b.Height * 0.11);
            if (_logo != null) {
                g.DrawImage(_logo, x, y, size, size);
                return;
            }
            int cx = b.Width / 2;
            int cy = y + size / 2;
            using (var path = new GraphicsPath()) {
                for (int i = 0; i < 6; i++) {
                    double ang = (60 * i - 30) * Math.PI / 180.0;
                    float px = cx + (float)(58 * Math.Cos(ang));
                    float py = cy + (float)(58 * Math.Sin(ang));
                    if (i == 0) path.AddLine(px, py, px, py);
                    else path.AddLine(path.GetLastPoint(), new PointF(px, py));
                }
                path.CloseFigure();
                using (var pen = new Pen(Color.FromArgb(180, 129, 140, 248), 3f))
                    g.DrawPath(pen, path);
            }
            using (var brush = new SolidBrush(Color.FromArgb(34, 211, 238)))
                g.FillEllipse(brush, cx - 18, cy - 18, 36, 36);
        }

        private void DrawTitle(Graphics g, Rectangle b) {
            int y = (int)(b.Height * 0.36);
            using (var font = new Font("Segoe UI", 32f, FontStyle.Bold))
            using (var brush = new SolidBrush(Color.FromArgb(245, 248, 252))) {
                var title = "Sentinel";
                var sz = g.MeasureString(title, font);
                float x = (b.Width - sz.Width) / 2f;
                g.DrawString(title, font, brush, x, y);
                using (var accent = new Pen(Color.FromArgb(160, 129, 140, 248), 2f)) {
                    g.DrawLine(accent, x + sz.Width + 4, y + sz.Height - 6, x + sz.Width + 14, y + sz.Height - 6);
                    g.DrawLine(accent, x + sz.Width + 14, y + sz.Height - 6, x + sz.Width + 14, y + sz.Height + 4);
                }
            }

            y += 52;
            string[] words = { "OBSERVE.", "ANALYZE.", "CONTROL." };
            Color[] colors = {
                Color.FromArgb(59, 130, 246),
                Color.FromArgb(168, 85, 247),
                Color.FromArgb(34, 211, 238)
            };
            using (var font = new Font("Segoe UI", 8.5f, FontStyle.Bold)) {
                float totalW = 0;
                foreach (var w in words) totalW += g.MeasureString(w + " ", font).Width;
                float x = (b.Width - totalW) / 2f;
                for (int i = 0; i < words.Length; i++) {
                    using (var brush = new SolidBrush(colors[i]))
                        g.DrawString(words[i] + " ", font, brush, x, y);
                    x += g.MeasureString(words[i] + " ", font).Width;
                }
            }
        }

        private void DrawProgress(Graphics g, Rectangle b) {
            int barW = (int)(b.Width * 0.72);
            int barH = 5;
            int x = (b.Width - barW) / 2;
            int y = (int)(b.Height * 0.52);

            var track = new RectangleF(x, y, barW, barH);
            FillRoundedRect(g, new SolidBrush(Color.FromArgb(45, 55, 72)), track, 3f);

            int fillW = Math.Max(6, (int)(barW * (_progress / 100.0)));
            var fill = new RectangleF(x, y, fillW, barH);
            using (var brush = new LinearGradientBrush(fill,
                Color.FromArgb(168, 85, 247),
                Color.FromArgb(34, 211, 238),
                LinearGradientMode.Horizontal))
                FillRoundedRect(g, brush, fill, 3f);

            // Glow at leading edge
            if (fillW > 8) {
                using (var glow = new SolidBrush(Color.FromArgb(120, 34, 211, 238)))
                    g.FillEllipse(glow, x + fillW - 8, y - 3, 12, 11);
            }

            using (var font = new Font("Segoe UI", 8.5f, FontStyle.Bold))
            using (var brush = new SolidBrush(Color.FromArgb(148, 163, 184))) {
                var status = _status ?? "INITIALIZING SYSTEM...";
                var sz = g.MeasureString(status, font);
                g.DrawString(status, font, brush, (b.Width - sz.Width) / 2f, y + 16);
            }
        }

        private void DrawFeatureIcons(Graphics g, Rectangle b) {
            string[] labels = { "MONITOR", "INSIGHT", "RELIABILITY", "CONTROL" };
            int cols = 4;
            int cellW = b.Width / cols;
            int y = (int)(b.Height * 0.78);
            int iconSize = 28;

            for (int i = 0; i < cols; i++) {
                int cx = cellW * i + cellW / 2;
                var box = new RectangleF(cx - iconSize / 2f, y, iconSize, iconSize);
                using (var pen = new Pen(Color.FromArgb(80, 99, 102, 241), 1.2f))
                using (var path = RoundedRect(box, 5f))
                    g.DrawPath(pen, path);

                using (var pen = new Pen(Color.FromArgb(180, 129, 140, 248), 1.5f)) {
                    int ix = cx;
                    int iy = y + iconSize / 2;
                    switch (i) {
                        case 0: // pulse
                            g.DrawLines(pen, new Point[] {
                                new Point(ix - 9, iy), new Point(ix - 5, iy),
                                new Point(ix - 2, iy - 7), new Point(ix + 2, iy + 7),
                                new Point(ix + 5, iy), new Point(ix + 9, iy)
                            });
                            break;
                        case 1: // bars
                            g.DrawLine(pen, ix - 7, iy + 5, ix - 7, iy - 2);
                            g.DrawLine(pen, ix - 2, iy + 5, ix - 2, iy - 6);
                            g.DrawLine(pen, ix + 4, iy + 5, ix + 4, iy - 10);
                            break;
                        case 2: // shield
                            g.DrawEllipse(pen, ix - 7, iy - 8, 14, 14);
                            g.DrawLine(pen, ix - 3, iy, ix - 1, iy + 3);
                            g.DrawLine(pen, ix - 1, iy + 3, ix + 5, iy - 4);
                            break;
                        case 3: // target
                            g.DrawEllipse(pen, ix - 8, iy - 8, 16, 16);
                            g.DrawEllipse(pen, ix - 4, iy - 4, 8, 8);
                            g.DrawLine(pen, ix, iy - 9, ix, iy + 9);
                            g.DrawLine(pen, ix - 9, iy, ix + 9, iy);
                            break;
                    }
                }

                using (var font = new Font("Segoe UI", 7f, FontStyle.Bold))
                using (var brush = new SolidBrush(Color.FromArgb(100, 129, 140, 248))) {
                    var lbl = labels[i];
                    var sz = g.MeasureString(lbl, font);
                    g.DrawString(lbl, font, brush, cx - sz.Width / 2f, y + iconSize + 6);
                }
            }
        }

        private void DrawVersion(Graphics g, Rectangle b) {
            using (var font = new Font("Segoe UI", 8f))
            using (var brush = new SolidBrush(Color.FromArgb(80, 148, 163, 184))) {
                var text = VersionText ?? "v1.0.0";
                var sz = g.MeasureString(text, font);
                g.DrawString(text, font, brush, (b.Width - sz.Width) / 2f, b.Height - 28);
            }
        }

        protected override void OnPaint(PaintEventArgs e) {
            try {
                var g = e.Graphics;
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;
                var b = ClientRectangle;
                DrawBackground(g, b);
                DrawLogo(g, b);
                DrawTitle(g, b);
                DrawProgress(g, b);
                DrawFeatureIcons(g, b);
                DrawVersion(g, b);
            } catch (Exception ex) {
                e.Graphics.Clear(BackColor);
                using (var font = new Font("Segoe UI", 10f))
                using (var brush = new SolidBrush(Color.FromArgb(239, 68, 68)))
                    e.Graphics.DrawString("Splash render error: " + ex.Message, font, brush, 12, 12);
            }
        }
    }
}
"@ -ErrorAction Stop
    } catch {
        throw "Sentinel splash UI failed to compile: $($_.Exception.Message)"
    }
}

if (-not ([System.Management.Automation.PSTypeName]"Sentinel.SplashCanvas").Type) {
    throw "Sentinel splash UI failed to compile. Check PowerShell/.NET Framework installation."
}

$script:Steps = @(
    @{ Pattern = "Stack start|Preparing"; Percent = 12; Status = "INITIALIZING SYSTEM..." }
    @{ Pattern = "watcher"; Percent = 35; Status = "STARTING WATCHER..." }
    @{ Pattern = "monitor on port"; Percent = 58; Status = "STARTING DASHBOARD..." }
    @{ Pattern = "Launching GnBots"; Percent = 78; Status = "LAUNCHING GNBOTS..." }
    @{ Pattern = "Tray icon|Stack is up"; Percent = 95; Status = "FINALIZING..." }
)

$script:StartProc = $null
$script:StackLaunchAt = $null
$script:Finished = $false
$script:Success = $false
$script:CancelRequested = $false
$script:CurrentPercent = 5

function script:Get-DashboardPort {
    $port = 8787
    $cfgPath = Join-Path $MonitorRoot "config.json"
    if (Test-Path $cfgPath) {
        try {
            $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
            if ($cfg.dashboard_port) { $port = [int]$cfg.dashboard_port }
        } catch {}
    }
    if ($port -le 0) { $port = 8787 }
    return $port
}

function script:Splash_SetError {
    param([string]$Message)
    if ($null -ne $script:Canvas) {
        $script:Canvas.StatusText = "STARTUP FAILED"
        $script:Canvas.ProgressPercent = $script:CurrentPercent
    }
    if ($null -ne $script:CancelBtn) { $script:CancelBtn.Text = "Close" }
    $script:Finished = $true
}

function script:Splash_UpdateFromStatus {
    param([string]$Raw)
    if ($null -eq $script:Canvas) { return }
    $text = [string]$Raw
    foreach ($step in $script:Steps) {
        if ($text -match $step.Pattern) {
            if ($step.Percent -gt $script:CurrentPercent) {
                $script:CurrentPercent = [int]$step.Percent
                $script:Canvas.ProgressPercent = $script:CurrentPercent
            }
            $script:Canvas.StatusText = $step.Status
            return
        }
    }
    if ($text -match "did not become healthy|Missing config\.json") {
        $script:Canvas.StatusText = "STARTUP FAILED"
    }
}

function script:Splash_TestMonitorPing {
    try {
        $port = script:Get-DashboardPort
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/ping" -UseBasicParsing -TimeoutSec 4
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function script:Splash_OnCloseTimerTick {
    if ($null -ne $script:CloseTimer) {
        $script:CloseTimer.Stop()
        $script:CloseTimer.Dispose()
        $script:CloseTimer = $null
    }
    if ($null -ne $script:Form) {
        $script:Form.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $script:Form.Close()
    }
}

function script:Splash_StopStartProc {
    if ($null -eq $script:StartProc) { return }
    try {
        if (-not $script:StartProc.HasExited) {
            Stop-Process -Id $script:StartProc.Id -Force -ErrorAction SilentlyContinue
        }
    } catch {}
    $script:StartProc = $null
}

function script:Splash_OnTimerTick {
    if ($script:Finished) { return }
    try {
        $statusText = ""
        if (Test-Path $script:StatusFile) {
            $raw = Get-Content $script:StatusFile -Raw -ErrorAction SilentlyContinue
            if ($raw) {
                $statusText = $raw.Trim()
                script:Splash_UpdateFromStatus $statusText
            }
        }

        if (-not $script:StackLaunchAt) { return }

        $monitorUp = script:Splash_TestMonitorPing
        $elapsed = ((Get-Date) - $script:StackLaunchAt).TotalSeconds
        $stackReady = ($statusText -match "Stack is up") -or $monitorUp

        if (-not $stackReady -and $elapsed -lt 120) { return }

        $script:Finished = $true
        if ($null -ne $script:Timer) { $script:Timer.Stop() }

        if (-not $monitorUp) {
            script:Splash_SetError "dashboard unreachable"
            return
        }

        if ($null -ne $script:Canvas) {
            $script:Canvas.ProgressPercent = 100
            $script:Canvas.StatusText = "SYSTEM READY"
        }
        if ($null -ne $script:CancelBtn) { $script:CancelBtn.Text = "Close" }
        $script:Success = $true

        $port = script:Get-DashboardPort
        Start-Process "http://127.0.0.1:$port/"

        $script:CloseTimer = New-Object System.Windows.Forms.Timer
        $script:CloseTimer.Interval = 900
        $script:CloseTimer.Add_Tick({ script:Splash_OnCloseTimerTick })
        $script:CloseTimer.Start()
    } catch {
        if ($script:CancelRequested) {
            if ($null -ne $script:Form) {
                $script:Form.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
                $script:Form.Close()
            }
            return
        }
        script:Splash_SetError $_.Exception.Message
    }
}

function script:Splash_OnShown {
    try {
        if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
        if (Test-Path $script:StatusFile) { Remove-Item $script:StatusFile -Force -ErrorAction SilentlyContinue }

        . (Join-Path $ScriptsDir "hidden-powershell.ps1")
        $argList = @("-Quiet", "-StatusFile", $script:StatusFile)
        if ($Elevated) { $argList += "-Elevated" }
        Start-HiddenPowerShellFile -ScriptPath $StartScript -Arguments $argList -WorkingDirectory $MonitorRoot | Out-Null
        $script:StackLaunchAt = Get-Date
        if ($null -ne $script:Timer) { $script:Timer.Start() }
    } catch {
        script:Splash_SetError $_.Exception.Message
    }
}

function script:Splash_OnCancelClick {
    if ($script:Finished) {
        if ($null -ne $script:Form) {
            $script:Form.DialogResult = if ($script:Success) {
                [System.Windows.Forms.DialogResult]::OK
            } else {
                [System.Windows.Forms.DialogResult]::Cancel
            }
            $script:Form.Close()
        }
        return
    }
    $script:CancelRequested = $true
    if ($null -ne $script:Timer) { $script:Timer.Stop() }
    script:Splash_StopStartProc
    if ($null -ne $script:Form) {
        $script:Form.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
        $script:Form.Close()
    }
}

function script:Splash_OnCloseClick {
    $script:CancelRequested = $true
    if ($null -ne $script:Timer) { $script:Timer.Stop() }
    script:Splash_StopStartProc
    if ($null -ne $script:Form) {
        $script:Form.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
        $script:Form.Close()
    }
}

# --- Form (borderless branded window) ---
$script:Form = New-Object System.Windows.Forms.Form
$script:Form.Text = "Sentinel"
$script:Form.ClientSize = New-Object System.Drawing.Size 480, 720
$script:Form.StartPosition = "CenterScreen"
$script:Form.FormBorderStyle = "None"
$script:Form.BackColor = [System.Drawing.Color]::FromArgb(8, 12, 24)
$script:Form.ShowInTaskbar = $true
$script:Form.TopMost = $true

$script:Canvas = New-Object Sentinel.SplashCanvas
$script:Canvas.Dock = "Fill"
$script:Canvas.VersionText = $script:AppVersion
$script:Canvas.ProgressPercent = 5
$script:Form.Controls.Add($script:Canvas)

if ($script:LogoPath) {
    try {
        $script:Canvas.SetLogo([System.Drawing.Image]::FromFile($script:LogoPath))
    } catch {}
}

$script:Timer = New-Object System.Windows.Forms.Timer
$script:Timer.Interval = 120
$script:Timer.Add_Tick({ script:Splash_OnTimerTick })

$closeBtn = New-Object System.Windows.Forms.Button
$closeBtn.Text = "X"
$closeBtn.FlatStyle = "Flat"
$closeBtn.FlatAppearance.BorderSize = 0
$closeBtn.Size = New-Object System.Drawing.Size 36, 32
$closeBtn.Location = New-Object System.Drawing.Point 444, 4
$closeBtn.BackColor = [System.Drawing.Color]::FromArgb(8, 12, 24)
$closeBtn.ForeColor = [System.Drawing.Color]::FromArgb(148, 163, 184)
$closeBtn.Cursor = [System.Windows.Forms.Cursors]::Hand
$closeBtn.Add_Click({ script:Splash_OnCloseClick })
$script:Form.Controls.Add($closeBtn)
$closeBtn.BringToFront()

$script:CancelBtn = New-Object System.Windows.Forms.Label
$script:CancelBtn.Text = "Cancel"
$script:CancelBtn.AutoSize = $true
$script:CancelBtn.ForeColor = [System.Drawing.Color]::FromArgb(100, 148, 163, 184)
$script:CancelBtn.BackColor = [System.Drawing.Color]::Transparent
$script:CancelBtn.Font = New-Object System.Drawing.Font("Segoe UI", 8.5)
$script:CancelBtn.Cursor = [System.Windows.Forms.Cursors]::Hand
$script:CancelBtn.Location = New-Object System.Drawing.Point 420, 688
$script:Form.Controls.Add($script:CancelBtn)
$script:CancelBtn.BringToFront()

$script:CancelBtn.Add_Click({ script:Splash_OnCancelClick })

# Drag borderless window
$script:Form.Add_MouseDown({ if ($_.Button -eq "Left") { $script:Form.Capture = $true } })
$script:Form.Add_MouseMove({
    if ($script:Form.Capture -and ([System.Windows.Forms.Control]::MouseButtons -band "Left")) {
        $script:Form.Location = New-Object System.Drawing.Point(
            ($script:Form.Location.X + [System.Windows.Forms.Control]::MousePosition.X - $script:DragX),
            ($script:Form.Location.Y + [System.Windows.Forms.Control]::MousePosition.Y - $script:DragY)
        )
    }
})
$script:Form.Add_MouseDown({ $script:DragX = [System.Windows.Forms.Control]::MousePosition.X; $script:DragY = [System.Windows.Forms.Control]::MousePosition.Y })
$script:Canvas.Add_MouseDown({ $script:Form.Capture = $true; $script:DragX = [System.Windows.Forms.Control]::MousePosition.X; $script:DragY = [System.Windows.Forms.Control]::MousePosition.Y })
$script:Canvas.Add_MouseMove({
    if ($script:Form.Capture) {
        $script:Form.Location = New-Object System.Drawing.Point(
            ($script:Form.Location.X + [System.Windows.Forms.Control]::MousePosition.X - $script:DragX),
            ($script:Form.Location.Y + [System.Windows.Forms.Control]::MousePosition.Y - $script:DragY)
        )
        $script:DragX = [System.Windows.Forms.Control]::MousePosition.X
        $script:DragY = [System.Windows.Forms.Control]::MousePosition.Y
    }
})
$script:Canvas.Add_MouseUp({ $script:Form.Capture = $false })

$script:Form.Add_Shown({ script:Splash_OnShown })

$script:Form.Add_FormClosed({
    if ($null -ne $script:Timer) { $script:Timer.Stop(); $script:Timer.Dispose() }
    if ($null -ne $script:CloseTimer) { $script:CloseTimer.Stop(); $script:CloseTimer.Dispose() }
    if ($script:StartProc) { script:Splash_StopStartProc }
})

try {
    $result = $script:Form.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) { exit 0 }
    exit 1
} catch {
    $err = $_.Exception.Message
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
    $errLog = Join-Path $LogDir "splash-error.log"
    Add-Content -Path $errLog -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $err)
    [System.Windows.Forms.MessageBox]::Show(
        "Sentinel splash could not start:`n`n$err`n`nSee logs\splash-error.log",
        "Sentinel",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}
