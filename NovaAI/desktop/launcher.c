/*
 * NovaAI.exe — Windows launcher for the Nova desktop chat app.
 * Finds python\python.exe next to this executable, runs app\nova_app.py,
 * and keeps a small console so the user can see download / unlock status.
 */
#include <windows.h>
#include <stdio.h>
#include <string.h>

#define MUTEX_NAME "Local\\NovaAI-Desktop-SingleInstance"

static void die(const char *msg) {
    MessageBoxA(NULL, msg, "Nova AI", MB_OK | MB_ICONERROR);
    ExitProcess(1);
}

int main(void) {
    char exePath[MAX_PATH];
    char root[MAX_PATH];
    char python[MAX_PATH];
    char script[MAX_PATH];
    char dllPath[MAX_PATH];
    char modelPath[MAX_PATH];
    char cmd[2048];
    char *slash;
    DWORD n;
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    DWORD code = 1;
    HANDLE mutex;

    /* Only one Nova window at a time — a second double-click focuses the idea
       of "already running" instead of spawning another server. */
    mutex = CreateMutexA(NULL, TRUE, MUTEX_NAME);
    if (mutex && GetLastError() == ERROR_ALREADY_EXISTS) {
        MessageBoxA(NULL,
                    "Nova AI is already running.\n"
                    "Check your browser or the Nova console window.",
                    "Nova AI", MB_OK | MB_ICONINFORMATION);
        if (mutex) CloseHandle(mutex);
        return 0;
    }

    n = GetModuleFileNameA(NULL, exePath, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) die("Could not locate NovaAI.exe");

    strncpy(root, exePath, MAX_PATH - 1);
    root[MAX_PATH - 1] = 0;
    slash = strrchr(root, '\\');
    if (!slash) die("Bad install path");
    *slash = 0;

    _snprintf(python, MAX_PATH, "%s\\python\\python.exe", root);
    _snprintf(script, MAX_PATH, "%s\\app\\nova_app.py", root);
    _snprintf(dllPath, MAX_PATH, "%s\\app\\nova_fastmath.dll", root);
    _snprintf(modelPath, MAX_PATH, "%s\\app\\nova_model.sc", root);

    if (GetFileAttributesA(python) == INVALID_FILE_ATTRIBUTES)
        die("Missing python\\python.exe — re-unzip the NovaAI-Windows pack.");
    if (GetFileAttributesA(script) == INVALID_FILE_ATTRIBUTES)
        die("Missing app\\nova_app.py — re-unzip the NovaAI-Windows pack.");

    SetCurrentDirectoryA(root);
    SetConsoleTitleA("Nova AI — leave this window open while you chat");
    SetEnvironmentVariableA("PYTHONPATH", "app");
    SetEnvironmentVariableA("PYTHONUTF8", "1");
    SetEnvironmentVariableA("PYTHONIOENCODING", "utf-8");
    /* Prefer the bundled brain (no download on first unlock). */
    if (GetFileAttributesA(modelPath) != INVALID_FILE_ATTRIBUTES)
        SetEnvironmentVariableA("NOVA_MODEL_PATH", modelPath);
    if (GetFileAttributesA(dllPath) != INVALID_FILE_ATTRIBUTES)
        SetEnvironmentVariableA("NOVA_FASTMATH", dllPath);

    _snprintf(cmd, sizeof(cmd),
              "\"%s\" -B -u \"%s\"", python, script);

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (!CreateProcessA(NULL, cmd, NULL, NULL, FALSE, 0, NULL, root, &si, &pi)) {
        die("Failed to start Nova. Try running python\\python.exe app\\nova_app.py");
    }

    WaitForSingleObject(pi.hProcess, INFINITE);
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    if (mutex) {
        ReleaseMutex(mutex);
        CloseHandle(mutex);
    }
    return (int)code;
}
