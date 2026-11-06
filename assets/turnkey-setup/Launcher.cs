using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Drawing;

internal static class McgsStart
{
    static string Root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
    static string Quote(string value)
    {
        // CommandLineToArgvW quoting; no shell and no command interpolation.
        var b = new StringBuilder("\""); int slashes = 0;
        foreach (char c in value) {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { b.Append('\\', slashes * 2 + 1); b.Append(c); slashes = 0; continue; }
            b.Append('\\', slashes); slashes = 0; b.Append(c);
        }
        b.Append('\\', slashes * 2); b.Append('"'); return b.ToString();
    }

    static string Execute(params string[] args)
    {
        string python = Path.Combine(Root, "runtime", "python", "python.exe");
        string script = Path.Combine(Root, "skill", "scripts", "turnkey.py");
        var command = new StringBuilder("-B -X utf8 ");
        command.Append(Quote(script)); command.Append(" --bundle-root "); command.Append(Quote(Root));
        foreach (string arg in args) { command.Append(' '); command.Append(Quote(arg)); }
        var start = new ProcessStartInfo(python, command.ToString()) {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true,
            RedirectStandardError = true, StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8, WorkingDirectory = Root
        };
        using (var p = Process.Start(start)) {
            Task<string> stdout = p.StandardOutput.ReadToEndAsync();
            Task<string> stderr = p.StandardError.ReadToEndAsync();
            p.WaitForExit(); Task.WaitAll(stdout, stderr);
            string result = stdout.Result;
            if (!String.IsNullOrWhiteSpace(stderr.Result)) result += Environment.NewLine + stderr.Result;
            return result;
        }
    }

    [STAThread]
    public static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        if (args.Length > 0) {
            try { Console.Write(Execute(args)); return 0; }
            catch (Exception e) { MessageBox.Show(e.Message, "MCGS 配置未完成"); return 1; }
        }
        var form = new Form { Text = "MCGS 工程技能 · 开箱配置", Width = 850, Height = 640,
            StartPosition = FormStartPosition.CenterScreen, Font = new Font("Microsoft YaHei UI", 10) };
        var top = new FlowLayoutPanel { Dock = DockStyle.Top, Height = 90, Padding = new Padding(12) };
        var family = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Width = 140 };
        family.Items.AddRange(new object[] { "McgsPro", "McgsStu" }); family.SelectedIndex = 0;
        var setup = new Button { Text = "检查 / 配置环境", AutoSize = true };
        var install = new Button { Text = "安装 Codex 技能", AutoSize = true };
        var verify = new Button { Text = "校验完整包", AutoSize = true };
        var readme = new Button { Text = "使用说明", AutoSize = true };
        top.Controls.AddRange(new Control[] { family, setup, install, verify, readme });
        var note = new Label { Text = "版本不同可保留并适配，也可选原目录重装。Pro 支持离线/在线；Stu 当前仅离线。", AutoSize = true, Padding = new Padding(0, 6, 0, 0) };
        top.Controls.Add(note);
        var output = new TextBox { Dock = DockStyle.Fill, Multiline = true, ScrollBars = ScrollBars.Both,
            ReadOnly = true, WordWrap = false, Font = new Font("Consolas", 10),
            Text = "完整包已包含运行时、预编译在线引擎与两份完整安装介质。\r\n先检查环境，再让智能体读取结果并选择修改方式。\r\n安装需要 UAC 或许可确认时，按原厂提示处理。" };
        var bottom = new Label { Dock = DockStyle.Bottom, Height = 42, Padding = new Padding(12),
            Text = "不会因环境配置自动修改工程。重装后的原目录和版本必须核实后才算安装完成。" };
        form.Controls.Add(output); form.Controls.Add(top); form.Controls.Add(bottom);
        Func<string[], Task> run = async delegate(string[] command) {
            setup.Enabled = install.Enabled = verify.Enabled = false;
            output.Text = "正在处理，请保留原厂向导窗口；未知结果不会自动重试。";
            try {
                string result = await Task.Run(() => Execute(command));
                output.Text = result;
                string log = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "mcgs-engineering");
                Directory.CreateDirectory(log);
                File.WriteAllText(Path.Combine(log, "last-setup-result.txt"), result, new UTF8Encoding(false));
            } catch (Exception e) { output.Text = "配置未完成：" + e.Message; }
            finally { setup.Enabled = install.Enabled = verify.Enabled = true; }
        };
        setup.Click += async delegate { await run(new[] { "setup", "--family", family.SelectedIndex == 0 ? "pro" : "stu", "--interactive" }); };
        install.Click += async delegate { await run(new[] { "install-skill" }); };
        verify.Click += async delegate { await run(new[] { "verify", "--full" }); };
        readme.Click += delegate { Process.Start(new ProcessStartInfo(Path.Combine(Root, "使用说明.md")) { UseShellExecute = true }); };
        Application.Run(form); return 0;
    }
}
