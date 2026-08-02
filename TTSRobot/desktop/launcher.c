/*
 * TTSRobot.exe — Windows launcher for the Discord TTS robot voice app.
 * Finds python\python.exe next to this executable, runs app\tts_app.py,
 * and keeps a console so the user can see bot status / errors.
 */
#include <windows.h>
#include <stdio.h>
#include <string.h>

static void die(const char *msg) {
    MessageBoxA(NULL, msg, "TTS Robot", MB_OK | MB_ICONERROR);
    ExitProcess(1);
}

int main(void) {
    char exePath[MAX_PATH];
    char root[MAX_PATH];
    char python[MAX_PATH];
    char script[MAX_PATH];
    char ffmpegDir[MAX_PATH];
    char pathEnv[32768];
    char cmd[2048];
    char *slash;
    DWORD n;
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    DWORD code = 1;

    n = GetModuleFileNameA(NULL, exePath, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) die("Could not locate TTSRobot.exe");

    strncpy(root, exePath, MAX_PATH - 1);
    root[MAX_PATH - 1] = 0;
    slash = strrchr(root, '\\');
    if (!slash) die("Bad install path");
    *slash = 0;

    _snprintf(python, MAX_PATH, "%s\\python\\python.exe", root);
    _snprintf(script, MAX_PATH, "%s\\app\\tts_app.py", root);
    _snprintf(ffmpegDir, MAX_PATH, "%s\\ffmpeg", root);
    if (GetFileAttributesA(python) == INVALID_FILE_ATTRIBUTES)
        die("Missing python\\python.exe — re-unzip the TTSRobot-Windows pack.");
    if (GetFileAttributesA(script) == INVALID_FILE_ATTRIBUTES)
        die("Missing app\\tts_app.py — re-unzip the TTSRobot-Windows pack.");

    SetCurrentDirectoryA(root);
    SetEnvironmentVariableA("PYTHONPATH", "app");
    SetEnvironmentVariableA("PYTHONUTF8", "1");
    SetEnvironmentVariableA("TTS_ROBOT_ROOT", root);

    /* Put bundled ffmpeg first on PATH */
    n = GetEnvironmentVariableA("PATH", pathEnv, sizeof(pathEnv));
    if (n > 0 && n < sizeof(pathEnv) - MAX_PATH - 2) {
        char newPath[32768];
        _snprintf(newPath, sizeof(newPath), "%s;%s", ffmpegDir, pathEnv);
        SetEnvironmentVariableA("PATH", newPath);
    } else {
        SetEnvironmentVariableA("PATH", ffmpegDir);
    }

    _snprintf(cmd, sizeof(cmd),
              "\"%s\" -u \"%s\"", python, script);

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (!CreateProcessA(NULL, cmd, NULL, NULL, FALSE, 0, NULL, root, &si, &pi)) {
        die("Failed to start TTS Robot. Try: python\\python.exe app\\tts_app.py");
    }

    WaitForSingleObject(pi.hProcess, INFINITE);
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return (int)code;
}
