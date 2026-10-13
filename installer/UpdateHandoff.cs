// GPL-3.0-only. Wait for the old setup to exit, verify its cached bytes,
// then run a per-user in-place update without a wizard. No elevation/shell.
using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
class UpdateHandoff {
    static string Quote(string value) { return "\"" + value.TrimEnd('\\') + "\""; }
    [STAThread]
    static int Main(string[] args) {
        if(args.Length!=3) return 40;
        string setup=Path.GetFullPath(args[1]);
        string folder=Path.GetFullPath(args[2]).TrimEnd('\\');
        string log=Path.Combine(Path.GetDirectoryName(setup),"handoff.log");
        try {
            int pid=int.Parse(args[0]);
            try { using(var parent=Process.GetProcessById(pid)) { if(!parent.WaitForExit(60000))return 41; } }
            catch(ArgumentException) { }
            string expected=Path.GetFileNameWithoutExtension(setup);
            if(expected.Length!=64 || new DirectoryInfo(Path.GetDirectoryName(setup)).Name!="app-updates")return 42;
            string actual;
            using(var sha=SHA256.Create())using(var input=File.OpenRead(setup))actual=BitConverter.ToString(sha.ComputeHash(input)).Replace("-","").ToLowerInvariant();
            if(actual!=expected || !File.Exists(Path.Combine(folder,"SiCXrtAnalyzer.exe")))return 43;
            File.AppendAllText(log,"VERIFIED\r\n");
            var start=new ProcessStartInfo(setup,"/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /NORESTARTAPPLICATIONS /XRTUPDATE=1 /DIR="+Quote(folder)+" /LOG="+Quote(Path.Combine(Path.GetDirectoryName(setup),"install.log")));
            start.UseShellExecute=false;start.CreateNoWindow=true;start.WorkingDirectory=Path.GetDirectoryName(setup);
            using(var process=Process.Start(start)) { process.WaitForExit();File.AppendAllText(log,"SETUP_EXIT="+process.ExitCode+"\r\n");return process.ExitCode; }
        } catch(Exception e) { try{File.AppendAllText(log,"FAILED="+e.GetType().Name+"\r\n");}catch{} return 44; }
    }
}
