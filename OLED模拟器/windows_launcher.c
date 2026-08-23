/*
 * MonoOLED Studio v8.3 - Windows x64 native runtime-locator launcher.
 *
 * Normal Win32 imports, no shebang parsing, no CRT dependency.
 * The launcher validates candidate Python runtimes by importing PySide6 + Pillow,
 * then launches OLED模拟器\\gui.py with the default project. All paths are UTF-16
 * and quoted, including installations below C:\\Program Files.
 */

typedef unsigned char U8;
typedef unsigned short U16;
typedef U16 wchar_t;
typedef unsigned int U32;
typedef unsigned long DWORD;
typedef unsigned long long SIZE_T;
typedef int BOOL;
typedef unsigned short WORD;
typedef void *PVOID;
typedef void *HANDLE;
typedef void *HMODULE;
typedef const wchar_t *LPCWSTR;
typedef wchar_t *LPWSTR;

#define TRUE 1
#define FALSE 0
#define NULL ((void*)0)
#define INVALID_FILE_ATTRIBUTES 0xFFFFFFFFUL
#define CREATE_UNICODE_ENVIRONMENT 0x00000400UL
#define CREATE_NO_WINDOW 0x08000000UL
#define INFINITE_WAIT 0xFFFFFFFFUL
#define WAIT_TIMEOUT 258UL
#define STARTUP_SMOKE_TIMEOUT_MS 15000UL
#define STARTF_USESHOWWINDOW 0x00000001UL
#define SW_SHOWNORMAL 1
#define MB_OK 0x00000000UL
#define MB_ICONERROR 0x00000010UL
#define MAX_PATH_LONG 32768
#define CMD_CAP 65536

typedef struct _STARTUPINFOW {
    DWORD cb; LPWSTR lpReserved; LPWSTR lpDesktop; LPWSTR lpTitle;
    DWORD dwX; DWORD dwY; DWORD dwXSize; DWORD dwYSize; DWORD dwXCountChars; DWORD dwYCountChars;
    DWORD dwFillAttribute; DWORD dwFlags; WORD wShowWindow; WORD cbReserved2; U8 *lpReserved2;
    HANDLE hStdInput; HANDLE hStdOutput; HANDLE hStdError;
} STARTUPINFOW;

typedef struct _PROCESS_INFORMATION {
    HANDLE hProcess; HANDLE hThread; DWORD dwProcessId; DWORD dwThreadId;
} PROCESS_INFORMATION;

__declspec(dllimport) DWORD __stdcall GetModuleFileNameW(HMODULE, LPWSTR, DWORD);
__declspec(dllimport) DWORD __stdcall GetFileAttributesW(LPCWSTR);
__declspec(dllimport) DWORD __stdcall GetEnvironmentVariableW(LPCWSTR, LPWSTR, DWORD);
__declspec(dllimport) DWORD __stdcall SearchPathW(LPCWSTR, LPCWSTR, LPCWSTR, DWORD, LPWSTR, LPWSTR*);
__declspec(dllimport) BOOL __stdcall CreateProcessW(LPCWSTR, LPWSTR, PVOID, PVOID, BOOL, DWORD, PVOID, LPCWSTR, STARTUPINFOW*, PROCESS_INFORMATION*);
__declspec(dllimport) BOOL __stdcall CloseHandle(HANDLE);
__declspec(dllimport) void __stdcall ExitProcess(U32);
__declspec(dllimport) DWORD __stdcall WaitForSingleObject(HANDLE, DWORD);
__declspec(dllimport) BOOL __stdcall GetExitCodeProcess(HANDLE, DWORD*);
__declspec(dllimport) BOOL __stdcall TerminateProcess(HANDLE, U32);
__declspec(dllimport) int __stdcall MessageBoxW(PVOID, LPCWSTR, LPCWSTR, U32);

static wchar_t g_exe[MAX_PATH_LONG];
static wchar_t g_root[MAX_PATH_LONG];
static wchar_t g_script[MAX_PATH_LONG];
static wchar_t g_project[MAX_PATH_LONG];
static wchar_t g_python[MAX_PATH_LONG];
static wchar_t g_tmp[MAX_PATH_LONG];
static wchar_t g_cmd[CMD_CAP];

static SIZE_T wlen(const wchar_t *s) { SIZE_T n=0; while(s && s[n]) ++n; return n; }
static BOOL wcopy(wchar_t *dst, SIZE_T cap, const wchar_t *src) { SIZE_T n=wlen(src); if(n+1>cap) return FALSE; for(SIZE_T i=0;i<=n;i++) dst[i]=src[i]; return TRUE; }
static BOOL wcat(wchar_t *dst, SIZE_T cap, const wchar_t *src) { SIZE_T a=wlen(dst), b=wlen(src); if(a+b+1>cap) return FALSE; for(SIZE_T i=0;i<=b;i++) dst[a+i]=src[i]; return TRUE; }
static void zero_bytes(void *p, SIZE_T n) { U8 *d=(U8*)p; while(n--) *d++=0; }
static BOOL exists(const wchar_t *path) { return GetFileAttributesW(path)!=INVALID_FILE_ATTRIBUTES; }
static BOOL dirname_inplace(wchar_t *p) { SIZE_T n=wlen(p); while(n>0) { wchar_t c=p[n-1]; if(c==L'\\' || c==L'/') { p[n-1]=0; return TRUE; } --n; } return FALSE; }
static BOOL join2(wchar_t *out, SIZE_T cap, const wchar_t *a, const wchar_t *b) { return wcopy(out,cap,a) && wcat(out,cap,b); }
static BOOL append_quoted(wchar_t *cmd, SIZE_T cap, const wchar_t *v) { return wcat(cmd,cap,L"\"") && wcat(cmd,cap,v) && wcat(cmd,cap,L"\""); }

static void show_error(const wchar_t *msg, U32 code) {
    MessageBoxW(NULL,msg,L"MonoOLED Studio",MB_OK|MB_ICONERROR);
    ExitProcess(code);
    for(;;){}
}

static BOOL env_candidate(wchar_t *out, SIZE_T cap, const wchar_t *env, const wchar_t *suffix) {
    DWORD n=GetEnvironmentVariableW(env,g_tmp,MAX_PATH_LONG);
    if(!n || n>=MAX_PATH_LONG) return FALSE;
    return wcopy(out,cap,g_tmp) && wcat(out,cap,suffix) && exists(out);
}

enum { PY_DIRECT_WINDOWED=0, PY_LAUNCHER=1, PY_CONSOLE=2 };

static BOOL runtime_ok(const wchar_t *python, int kind) {
    STARTUPINFOW si; PROCESS_INFORMATION pi; DWORD exit_code=0xFFFFFFFFUL;
    zero_bytes(&si,sizeof(si)); zero_bytes(&pi,sizeof(pi));
    si.cb=(DWORD)sizeof(si); si.dwFlags=STARTF_USESHOWWINDOW; si.wShowWindow=SW_SHOWNORMAL;
    g_cmd[0]=0;
    if(!append_quoted(g_cmd,CMD_CAP,python) || !wcat(g_cmd,CMD_CAP,L" ")) return FALSE;
    if(kind==PY_LAUNCHER && !wcat(g_cmd,CMD_CAP,L"-3 ")) return FALSE;
    if(!wcat(g_cmd,CMD_CAP,L"-c ") || !append_quoted(g_cmd,CMD_CAP,L"import PySide6; import PIL")) return FALSE;
    DWORD flags=CREATE_UNICODE_ENVIRONMENT | (kind==PY_CONSOLE ? CREATE_NO_WINDOW : 0);
    if(!CreateProcessW(python,g_cmd,NULL,NULL,FALSE,flags,NULL,g_root,&si,&pi)) return FALSE;
    WaitForSingleObject(pi.hProcess,INFINITE_WAIT);
    BOOL ok=GetExitCodeProcess(pi.hProcess,&exit_code) && exit_code==0;
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    return ok;
}

static BOOL startup_smoke_ok(const wchar_t *python, int kind) {
    STARTUPINFOW si; PROCESS_INFORMATION pi; DWORD exit_code=0xFFFFFFFFUL;
    zero_bytes(&si,sizeof(si)); zero_bytes(&pi,sizeof(pi));
    si.cb=(DWORD)sizeof(si); si.dwFlags=STARTF_USESHOWWINDOW; si.wShowWindow=SW_SHOWNORMAL;
    g_cmd[0]=0;
    if(!append_quoted(g_cmd,CMD_CAP,python) || !wcat(g_cmd,CMD_CAP,L" ")) return FALSE;
    if(kind==PY_LAUNCHER && !wcat(g_cmd,CMD_CAP,L"-3 ")) return FALSE;
    if(!append_quoted(g_cmd,CMD_CAP,g_script)) return FALSE;
    if(exists(g_project) && (!wcat(g_cmd,CMD_CAP,L" --project ") || !append_quoted(g_cmd,CMD_CAP,g_project))) return FALSE;
    if(!wcat(g_cmd,CMD_CAP,L" --startup-smoke")) return FALSE;
    DWORD flags=CREATE_UNICODE_ENVIRONMENT | (kind==PY_CONSOLE ? CREATE_NO_WINDOW : 0);
    if(!CreateProcessW(python,g_cmd,NULL,NULL,FALSE,flags,NULL,g_root,&si,&pi)) return FALSE;
    DWORD wait=WaitForSingleObject(pi.hProcess,STARTUP_SMOKE_TIMEOUT_MS);
    if(wait==WAIT_TIMEOUT) {
        TerminateProcess(pi.hProcess,6);
        WaitForSingleObject(pi.hProcess,INFINITE_WAIT);
    }
    BOOL ok=(wait!=WAIT_TIMEOUT) && GetExitCodeProcess(pi.hProcess,&exit_code) && exit_code==0;
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    return ok;
}

static BOOL accept_candidate(const wchar_t *path, int kind, wchar_t *out, SIZE_T cap, int *out_kind) {
    if(!exists(path) || !runtime_ok(path,kind)) return FALSE;
    if(!wcopy(out,cap,path)) return FALSE;
    *out_kind=kind;
    return TRUE;
}

static BOOL find_python(const wchar_t *root, wchar_t *out, SIZE_T cap, int *kind) {
    DWORD override_n=GetEnvironmentVariableW(L"MONOOLED_PYTHON",g_tmp,MAX_PATH_LONG);
    if(override_n && override_n<MAX_PATH_LONG && accept_candidate(g_tmp,PY_CONSOLE,out,cap,kind)) return TRUE;
    const wchar_t *local_paths[]={
        L"\\_runtime\\pythonw.exe", L"\\_runtime\\python.exe",
        L"\\.venv-runtime\\Scripts\\pythonw.exe", L"\\.venv-runtime\\Scripts\\python.exe"
    };
    const int local_kinds[]={PY_DIRECT_WINDOWED,PY_CONSOLE,PY_DIRECT_WINDOWED,PY_CONSOLE};
    for(int i=0;i<4;i++) if(join2(g_tmp,MAX_PATH_LONG,root,local_paths[i]) && accept_candidate(g_tmp,local_kinds[i],out,cap,kind)) return TRUE;

    const wchar_t *vers[]={L"313",L"312",L"311",L"310"};
    const wchar_t *envs[]={L"LOCALAPPDATA",L"ProgramFiles"};
    for(int e=0;e<2;e++) for(int i=0;i<4;i++) {
        g_cmd[0]=0;
        if(e==0) wcat(g_cmd,CMD_CAP,L"\\Programs\\Python\\Python"); else wcat(g_cmd,CMD_CAP,L"\\Python");
        wcat(g_cmd,CMD_CAP,vers[i]);
        wcat(g_cmd,CMD_CAP,L"\\pythonw.exe");
        if(env_candidate(g_tmp,MAX_PATH_LONG,envs[e],g_cmd) && accept_candidate(g_tmp,PY_DIRECT_WINDOWED,out,cap,kind)) return TRUE;

        g_cmd[0]=0;
        if(e==0) wcat(g_cmd,CMD_CAP,L"\\Programs\\Python\\Python"); else wcat(g_cmd,CMD_CAP,L"\\Python");
        wcat(g_cmd,CMD_CAP,vers[i]);
        wcat(g_cmd,CMD_CAP,L"\\python.exe");
        if(env_candidate(g_tmp,MAX_PATH_LONG,envs[e],g_cmd) && accept_candidate(g_tmp,PY_CONSOLE,out,cap,kind)) return TRUE;
    }

    DWORD n=SearchPathW(NULL,L"pythonw.exe",NULL,MAX_PATH_LONG,g_tmp,NULL);
    if(n && n<MAX_PATH_LONG && accept_candidate(g_tmp,PY_DIRECT_WINDOWED,out,cap,kind)) return TRUE;
    n=SearchPathW(NULL,L"python.exe",NULL,MAX_PATH_LONG,g_tmp,NULL);
    if(n && n<MAX_PATH_LONG && accept_candidate(g_tmp,PY_CONSOLE,out,cap,kind)) return TRUE;
    n=SearchPathW(NULL,L"pyw.exe",NULL,MAX_PATH_LONG,g_tmp,NULL);
    if(n && n<MAX_PATH_LONG && accept_candidate(g_tmp,PY_LAUNCHER,out,cap,kind)) return TRUE;
    return FALSE;
}

void entry(void) {
    DWORD n=GetModuleFileNameW(NULL,g_exe,MAX_PATH_LONG);
    if(!n || n>=MAX_PATH_LONG || !wcopy(g_root,MAX_PATH_LONG,g_exe) || !dirname_inplace(g_root))
        show_error(L"Cannot resolve the application directory.",2);

    if(!join2(g_script,MAX_PATH_LONG,g_root,L"\\OLED模拟器\\gui.py") || !exists(g_script))
        show_error(L"OLED模拟器\\gui.py is missing next to the application. Re-extract the complete delivery package.",2);

    join2(g_project,MAX_PATH_LONG,g_root,L"\\CuringLite.project.oled.json");
    int py_kind=PY_DIRECT_WINDOWED;
    if(!find_python(g_root,g_python,MAX_PATH_LONG,&py_kind))
        show_error(L"No compatible Python GUI runtime was found. The launcher checked MONOOLED_PYTHON, _runtime, .venv-runtime, standard ProgramFiles / LOCALAPPDATA Python 3.13-3.10 locations and PATH, and verified PySide6 + Pillow imports.",3);
    if(!startup_smoke_ok(g_python,py_kind))
        show_error(L"GUI startup validation failed. The selected Python imports PySide6 + Pillow, but MonoOLED Studio could not construct and close its real Qt main window. Run Developer_Tools\\CREATE_RUNTIME_ENV.bat or inspect the logs folder before retrying.",5);

    g_cmd[0]=0;
    if(!append_quoted(g_cmd,CMD_CAP,g_python) || !wcat(g_cmd,CMD_CAP,L" ")) show_error(L"Command line is too long.",4);
    if(py_kind==PY_LAUNCHER && !wcat(g_cmd,CMD_CAP,L"-3 ")) show_error(L"Command line is too long.",4);
    if(!append_quoted(g_cmd,CMD_CAP,g_script)) show_error(L"Command line is too long.",4);
    if(exists(g_project) && (!wcat(g_cmd,CMD_CAP,L" --project ") || !append_quoted(g_cmd,CMD_CAP,g_project))) show_error(L"Command line is too long.",4);

    STARTUPINFOW si; PROCESS_INFORMATION pi;
    zero_bytes(&si,sizeof(si)); zero_bytes(&pi,sizeof(pi));
    si.cb=(DWORD)sizeof(si); si.dwFlags=STARTF_USESHOWWINDOW; si.wShowWindow=SW_SHOWNORMAL;
    DWORD flags=CREATE_UNICODE_ENVIRONMENT | (py_kind==PY_CONSOLE ? CREATE_NO_WINDOW : 0);
    if(!CreateProcessW(g_python,g_cmd,NULL,NULL,FALSE,flags,NULL,g_root,&si,&pi))
        show_error(L"The verified Python runtime was found, but the MonoOLED Studio process could not be started.",4);
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess); ExitProcess(0);
    for(;;){}
}
