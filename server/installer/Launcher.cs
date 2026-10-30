using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

internal static class Launcher
{
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern int SetCurrentProcessExplicitAppUserModelID(string appId);

    [STAThread]
    private static void Main()
    {
        SetCurrentProcessExplicitAppUserModelID("davuses.PageVoice.Server");
        string directory = AppDomain.CurrentDomain.BaseDirectory;
        string script = Path.Combine(directory, "start-tray.vbs");
        try
        {
            if (!File.Exists(script))
                throw new FileNotFoundException("Reinstall PageVoice to restore its launcher script.", script);
            Process.Start(new ProcessStartInfo
            {
                FileName = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "wscript.exe"),
                Arguments = "\"" + script + "\"",
                WorkingDirectory = directory,
                UseShellExecute = false,
                CreateNoWindow = true
            });
        }
        catch (Exception error)
        {
            MessageBox.Show("PageVoice could not start.\n\n" + error.Message,
                "PageVoice Server", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
