/* ghosthand.h -- Ghost Hand BeG0nE recorder for NATIVE mods (C / C++), the twin of the plugin's ghosthand.lua
 * (reader, 2026-10-17; written for Hard Reset VR, meant for begone/ghost-hand/ in the lanes plugin).
 *
 * Writes, while a headset session runs, where the real controllers are, where the game draws the hands, the
 * weapon's moving parts, what the mod measured, and when each hand gesture starts and ends. The lines are exactly
 * ghosthand.lua's, so the same filer (ghost_hand_check.py) reads them; Lanes' rider files the log when the session
 * ends. It writes ONLY between gh_vr_on() and gh_vr_off(): a flat run writes nothing, the game being in VR is the
 * switch (as jitterlog.h).
 *
 * Header-only, C89 and C++, Windows only. One buffered text file per VR session in
 *   %LOCALAPPDATA%\BeG0nE\ghost-hand\<game>_<yyyymmdd-hhmmss>.ghl
 * Thread-safe (one critical section): the controllers may be logged on the headset thread and the game's hands on
 * the game thread; a frame (gh_frame) holds whatever arrived since the last one, the last line of a kind winning.
 *
 * Usage, once per module:
 *     #define GHOSTHAND_IMPLEMENTATION
 *     #include "ghosthand.h"
 * and in every other file just #include "ghosthand.h".
 *     gh_init("hard-reset-vr", "openxr");      at load
 *     gh_vr_on();  ...  gh_vr_off();           with the VR session
 *   once per frame, all positions in the SAME space (metres):
 *     gh_real('L'|'R', tracked, x, y, z)       the controller as the headset tracks it
 *     gh_game('L'|'R', x, y, z)                the hand the game draws
 *     gh_part("slide", x, y, z)                a moving part of the weapon
 *     gh_value("rack", 0.82f)                  what the mod measured
 *     gh_button("LG", 1)                       a button that matters for the gesture
 *     gh_frame()                               end of the frame
 *   around every hand gesture:
 *     gh_event("rack", "start") ... gh_event("rack", "done" | "fail" | "cancel")
 *     gh_value("rack_need", 0.06f)             optional: metres the gesture needs, so misses can be judged
 */
#ifndef GHOSTHAND_H
#define GHOSTHAND_H

#ifdef __cplusplus
extern "C" {
#endif

void gh_init(const char* game, const char* runtime);   /* names only; no file yet */
void gh_vr_on(void);                                    /* opens the session's file; logging starts */
void gh_vr_off(void);                                   /* flushes and closes; logging stops */
int  gh_is_on(void);
void gh_real(char side, int tracked, float x, float y, float z);
void gh_game(char side, float x, float y, float z);
void gh_part(const char* name, float x, float y, float z);
void gh_value(const char* name, float v);
void gh_button(const char* name, int down);
void gh_event(const char* name, const char* what);
void gh_frame(void);

#ifdef __cplusplus
}
#endif

#ifdef GHOSTHAND_IMPLEMENTATION
#include <windows.h>
#include <stdio.h>
#include <string.h>

#define GH_VERSION          1
#define GH_BUFFER_BYTES     65536        /* written out when fuller than GH_FLUSH_AT or older than GH_FLUSH_US */
#define GH_FLUSH_AT         (GH_BUFFER_BYTES - 256)
#define GH_FLUSH_US         1000000LL
#define GH_NAME_CHARS       64
#define GH_WORD_CHARS       48           /* a name or outcome in a line; spaces become '_' (ghosthand.lua's word()) */
#define GH_PATH_CHARS       520
#define GH_FOLDER           "\\BeG0nE\\ghost-hand"

typedef struct {
    CRITICAL_SECTION cs;
    int cs_ready, on;
    FILE* f;
    char buf[GH_BUFFER_BYTES];
    int len;
    LONGLONG freq, t0, last_flush;
    char game[GH_NAME_CHARS], runtime[GH_NAME_CHARS];
} GhState;

static GhState gh_s;

static LONGLONG gh_now_us(void) {
    LARGE_INTEGER c;
    QueryPerformanceCounter(&c);
    return c.QuadPart * 1000000LL / gh_s.freq;
}

static void gh_flush_locked(void) {
    if (gh_s.f && gh_s.len > 0) {
        fwrite(gh_s.buf, 1, (size_t)gh_s.len, gh_s.f);
        fflush(gh_s.f);
        gh_s.len = 0;
    }
    gh_s.last_flush = gh_now_us();
}

static void gh_put(const char* line, int n) {
    if (n <= 0) return;
    EnterCriticalSection(&gh_s.cs);
    if (gh_s.on) {
        if (gh_s.len + n >= GH_BUFFER_BYTES) gh_flush_locked();
        memcpy(gh_s.buf + gh_s.len, line, (size_t)n);
        gh_s.len += n;
    }
    LeaveCriticalSection(&gh_s.cs);
}

static void gh_word(const char* s, char* out) {
    int i = 0;
    if (!s || !*s) s = "?";
    for (; s[i] && i < GH_WORD_CHARS - 1; ++i) out[i] = (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r') ? '_' : s[i];
    out[i] = 0;
}

static char gh_side(char side) { return side == 'L' || side == 'l' ? 'L' : 'R'; }

void gh_init(const char* game, const char* runtime) {
    LARGE_INTEGER f;
    if (!gh_s.cs_ready) { InitializeCriticalSection(&gh_s.cs); gh_s.cs_ready = 1; }
    QueryPerformanceFrequency(&f);
    gh_s.freq = f.QuadPart ? f.QuadPart : 1;
    strncpy(gh_s.game, game ? game : "game", GH_NAME_CHARS - 1);
    strncpy(gh_s.runtime, runtime ? runtime : "unknown", GH_NAME_CHARS - 1);
}

void gh_vr_on(void) {
    char path[GH_PATH_CHARS], base[GH_PATH_CHARS];
    SYSTEMTIME st;
    DWORD n;
    if (!gh_s.cs_ready) gh_init(gh_s.game[0] ? gh_s.game : "game", gh_s.runtime[0] ? gh_s.runtime : "unknown");
    EnterCriticalSection(&gh_s.cs);
    if (gh_s.on) { LeaveCriticalSection(&gh_s.cs); return; }
    n = GetEnvironmentVariableA("LOCALAPPDATA", base, sizeof base);
    if (n == 0 || n >= sizeof base) strcpy(base, ".");
    strncat(base, GH_FOLDER, sizeof base - strlen(base) - 1);
    {   /* make BeG0nE\ then BeG0nE\ghost-hand\ */
        char* slash = strrchr(base, '\\');
        if (slash) { *slash = 0; CreateDirectoryA(base, NULL); *slash = '\\'; }
        CreateDirectoryA(base, NULL);
    }
    GetLocalTime(&st);
    _snprintf(path, sizeof path, "%s\\%s_%04d%02d%02d-%02d%02d%02d.ghl", base, gh_s.game,
              st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
    gh_s.f = fopen(path, "wb");
    if (gh_s.f) {
        gh_s.t0 = gh_now_us();
        gh_s.len = _snprintf(gh_s.buf, GH_BUFFER_BYTES, "#ghosthand %d game=%s runtime=%s pid=%lu\n", GH_VERSION,
                             gh_s.game, gh_s.runtime, (unsigned long)GetCurrentProcessId());
        gh_s.on = 1;
        gh_flush_locked();
    }
    LeaveCriticalSection(&gh_s.cs);
}

void gh_vr_off(void) {
    if (!gh_s.cs_ready) return;
    EnterCriticalSection(&gh_s.cs);
    if (gh_s.on) {
        gh_s.on = 0;
        if (gh_s.len + 8 < GH_BUFFER_BYTES) { memcpy(gh_s.buf + gh_s.len, "#end\n", 5); gh_s.len += 5; }
        gh_flush_locked();
        fclose(gh_s.f);
        gh_s.f = NULL;
    }
    LeaveCriticalSection(&gh_s.cs);
}

int gh_is_on(void) { return gh_s.on; }

void gh_real(char side, int tracked, float x, float y, float z) {
    char line[128];
    if (!gh_s.on) return;
    gh_put(line, _snprintf(line, sizeof line, "%lld R %c %d %.4f %.4f %.4f\n", gh_now_us() - gh_s.t0, gh_side(side),
                           tracked ? 1 : 0, x, y, z));
}

void gh_game(char side, float x, float y, float z) {
    char line[128];
    if (!gh_s.on) return;
    gh_put(line, _snprintf(line, sizeof line, "%lld G %c %.4f %.4f %.4f\n", gh_now_us() - gh_s.t0, gh_side(side), x, y, z));
}

void gh_part(const char* name, float x, float y, float z) {
    char line[160], w[GH_WORD_CHARS];
    if (!gh_s.on) return;
    gh_word(name, w);
    gh_put(line, _snprintf(line, sizeof line, "%lld P %s %.4f %.4f %.4f\n", gh_now_us() - gh_s.t0, w, x, y, z));
}

void gh_value(const char* name, float v) {
    char line[128], w[GH_WORD_CHARS];
    if (!gh_s.on) return;
    gh_word(name, w);
    gh_put(line, _snprintf(line, sizeof line, "%lld V %s %.5f\n", gh_now_us() - gh_s.t0, w, v));
}

void gh_button(const char* name, int down) {
    char line[128], w[GH_WORD_CHARS];
    if (!gh_s.on) return;
    gh_word(name, w);
    gh_put(line, _snprintf(line, sizeof line, "%lld B %s %d\n", gh_now_us() - gh_s.t0, w, down ? 1 : 0));
}

void gh_event(const char* name, const char* what) {
    char line[160], w[GH_WORD_CHARS], o[GH_WORD_CHARS];
    if (!gh_s.on) return;
    gh_word(name, w);
    gh_word(what, o);
    gh_put(line, _snprintf(line, sizeof line, "%lld E %s %s\n", gh_now_us() - gh_s.t0, w, o));
}

void gh_frame(void) {
    char line[64];
    if (!gh_s.on) return;
    gh_put(line, _snprintf(line, sizeof line, "%lld F\n", gh_now_us() - gh_s.t0));
    if (gh_now_us() - gh_s.last_flush > GH_FLUSH_US || gh_s.len > GH_FLUSH_AT) {
        EnterCriticalSection(&gh_s.cs);
        gh_flush_locked();
        LeaveCriticalSection(&gh_s.cs);
    }
}

#endif /* GHOSTHAND_IMPLEMENTATION */
#endif /* GHOSTHAND_H */
