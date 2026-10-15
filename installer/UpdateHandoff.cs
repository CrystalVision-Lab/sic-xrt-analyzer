// GPL-3.0-only. Runs outside the install directory and waits for all app processes.
using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Threading;
using System.Windows.Forms;
class UpdateHandoff {
    static string Quote(string value) { return "\"" + value.TrimEnd('\\') + "\""; }
    static bool AppRunning(string folder) {
        foreach(string name in new[]{"SiCXrtAnalyzer","SiCXrtApp","SiCXrtWorker"})
            foreach(var p in Process.GetProcessesByName(name))using(p) {
                try { if(String.Equals(Path.GetDirectoryName(p.MainModule.FileName),folder,StringComparison.OrdinalIgnoreCase))return true; }
                catch(System.ComponentModel.Win32Exception) { throw new IOException("Cannot inspect XRT process"); }
                catch(InvalidOperationException) { }
            }
        return false;
    }
    [STAThread] static int Main(string[] args) {
        if(args.Length!=3)return 40;
        string setup=Path.GetFullPath(args[1]),folder=Path.GetFullPath(args[2]).TrimEnd('\\');
        string log=Path.Combine(Path.GetDirectoryName(setup),"handoff.log");
        int result=44;
        Application.EnableVisualStyles();
        var form=new Form{Text="SiC XRT 업데이트",Width=440,Height=145,FormBorderStyle=FormBorderStyle.FixedDialog,ControlBox=false,StartPosition=FormStartPosition.CenterScreen};
        var label=new Label{Left=20,Top=18,Width=390,Height=30,Text="프로그램 종료를 기다리는 중…"};
        var progress=new ProgressBar{Left=20,Top=55,Width=390,Height=20,Style=ProgressBarStyle.Marquee};
        form.Controls.Add(label);form.Controls.Add(progress);
        Action<string> status=s=>form.BeginInvoke((Action)(()=>label.Text=s));
        form.Shown+=(s,e)=>ThreadPool.QueueUserWorkItem(_=>{
            try {
                int pid=int.Parse(args[0]);
                try { using(var parent=Process.GetProcessById(pid))if(!parent.WaitForExit(60000))throw new IOException("Setup did not exit"); }catch(ArgumentException){}
                string expected=Path.GetFileNameWithoutExtension(setup);
                if(expected.Length!=64||new DirectoryInfo(Path.GetDirectoryName(setup)).Name!="app-updates")throw new IOException("Invalid cache");
                var until=DateTime.UtcNow.AddSeconds(120);
                while(AppRunning(folder)&&DateTime.UtcNow<until)Thread.Sleep(250);
                if(AppRunning(folder))throw new IOException("XRT still running");
                status("설치 파일을 확인하는 중…");
                string actual;
                using(var sha=SHA256.Create())using(var input=File.OpenRead(setup))actual=BitConverter.ToString(sha.ComputeHash(input)).Replace("-","").ToLowerInvariant();
                if(actual!=expected||!File.Exists(Path.Combine(folder,"SiCXrtAnalyzer.exe")))throw new IOException("Integrity check failed");
                File.AppendAllText(log,"VERIFIED_AND_APP_EXITED\r\n");status("업데이트 적용 중 · 완료 후 자동으로 열립니다");
                var start=new ProcessStartInfo(setup,"/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /NORESTARTAPPLICATIONS /XRTUPDATE=1 /XRTHANDOFF=1 /DIR="+Quote(folder)+" /LOG="+Quote(Path.Combine(Path.GetDirectoryName(setup),"install.log"))){UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=Path.GetDirectoryName(setup)};
                using(var process=Process.Start(start)){process.WaitForExit();result=process.ExitCode;}
                File.AppendAllText(log,"SETUP_EXIT="+result+"\r\n");
                if(result==0)Process.Start(new ProcessStartInfo(Path.Combine(folder,"SiCXrtAnalyzer.exe")){UseShellExecute=false,WorkingDirectory=folder});
            } catch(Exception ex){File.AppendAllText(log,"FAILED="+ex.GetType().Name+"\r\n");}
            form.BeginInvoke((Action)(()=>form.Close()));
        });
        Application.Run(form);
        if(result!=0)MessageBox.Show("업데이트를 완료하지 못했습니다. 다른 XRT 창을 닫고 다시 설치해 주세요.\r\n기록: "+log,"SiC XRT 업데이트",MessageBoxButtons.OK,MessageBoxIcon.Warning);
        return result;
    }
}
