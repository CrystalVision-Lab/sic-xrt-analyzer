// GPL-3.0-only. Native entry point never loads application Python DLLs during setup.
using System;
using System.IO;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Threading;
using System.Windows.Forms;
class NativeLauncher {
    const string SetupMutex="CrystalVisionLab_SicXrt_81CAB3F6-F3BE-4B05-ACB8-E9F47113CC32";
    static string Quote(string x) { return "\""+x.Replace("\"","\\\"").TrimEnd('\\')+"\""; }
    static string Digest(string p) { using(var h=SHA256.Create())using(var f=File.OpenRead(p))return BitConverter.ToString(h.ComputeHash(f)).Replace("-","").ToLowerInvariant(); }
    static bool Installing() { try { using(var m=Mutex.OpenExisting(SetupMutex))return true; }catch(WaitHandleCannotBeOpenedException){return false;} }
    static bool Verify(string root) {
        string manifest=Path.Combine(root,"runtime-files.sha256");
        if(!File.Exists(manifest)||new FileInfo(manifest).Length>1024*1024)return false;
        var lines=File.ReadAllLines(manifest);if(lines.Length<5||lines.Length>4096)return false;
        foreach(string line in lines) {
            if(line.Length<67)return false;
            string relative=line.Substring(66),path=Path.GetFullPath(Path.Combine(root,relative));
            if(!path.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)||!File.Exists(path)||Digest(path)!=line.Substring(0,64))return false;
        }
        return true;
    }
    static void Failure() { MessageBox.Show("프로그램 설치가 완료되지 않았습니다. 다운로드 사이트에서 설치 파일을 다시 실행해 주세요.\r\nhttps://pc1.tail23f008.ts.net", "SiC XRT 설치 복구",MessageBoxButtons.OK,MessageBoxIcon.Warning); }
    [STAThread] static int Main(string[] args) {
        string root=Path.GetFullPath(AppDomain.CurrentDomain.BaseDirectory).TrimEnd('\\');
        try {
            if(args.Length==1&&args[0]=="--verify-runtime")return Verify(root)?0:65;
            if(args.Length==2&&args[0]=="--wait-install") {
                root=Path.GetFullPath(args[1]).TrimEnd('\\');
                var until=DateTime.UtcNow.AddMinutes(15);
                while(Installing()&&DateTime.UtcNow<until)Thread.Sleep(250);
                if(Installing()||File.Exists(Path.Combine(root,".xrt-install-incomplete"))){Failure();return 66;}
                Process.Start(new ProcessStartInfo(Path.Combine(root,"SiCXrtAnalyzer.exe")){UseShellExecute=false,WorkingDirectory=root});return 0;
            }
            if(Installing()) {
                string temp=Path.Combine(Path.GetTempPath(),"XrtLaunchWait-"+Process.GetCurrentProcess().Id+".exe");
                File.Copy(Process.GetCurrentProcess().MainModule.FileName,temp,false);
                Process.Start(new ProcessStartInfo(temp,"--wait-install "+Quote(root)){UseShellExecute=false,CreateNoWindow=true});return 0;
            }
            if(File.Exists(Path.Combine(root,".xrt-install-incomplete"))||!Verify(root)){Failure();return 65;}
            string ident;
            using(var h=SHA256.Create())ident=BitConverter.ToString(h.ComputeHash(System.Text.Encoding.UTF8.GetBytes(root.ToLowerInvariant()))).Replace("-","");
            bool created;
            using(var instance=new Mutex(true,"CrystalVisionLab_XrtRun_"+ident,out created)) {
                if(!created)return 0;
                string joined=String.Join(" ",Array.ConvertAll(args,Quote));
                var start=new ProcessStartInfo(Path.Combine(root,"SiCXrtApp.exe"),joined){UseShellExecute=false,WorkingDirectory=root};
                using(var child=Process.Start(start)){child.WaitForExit();return child.ExitCode;}
            }
        } catch { if(Array.IndexOf(args,"--verify-runtime")<0)Failure();return 67; }
    }
}
