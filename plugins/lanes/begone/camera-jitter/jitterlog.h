/* jitterlog.h -- BeG0nE Camera Jitter ride-along, the piece that lives INSIDE a VR mod (2026-10-08).
 *
 * The mod writes down three moments, every frame, and nothing else:
 *   jl_pose_*()    "I just READ the headset pose"      (headset thread or game thread, wherever the read is)
 *   jl_camera_*()  "I just WROTE the game's camera"    (game thread)
 *   jl_present()   "a picture just went out"           (the Present / xrEndFrame of the frame)
 * From those three streams the checker (jitter_log_check.py) can say whether the camera is renewed less often
 * than pictures are drawn, whether the runtime handed the same pose twice, whether the camera trails the pose by
 * a frame, and how old the pose was when it was used. A recording cannot say any of that.
 *
 * It writes ONLY between jl_vr_on() and jl_vr_off(): call them when the VR session really starts and stops
 * (OpenXR: session state READY/FOCUSED and STOPPING; SteamVR: VR_Init succeeded / VR_Shutdown). A flat run
 * writes nothing, so nothing has to be switched on or off from outside: the game being in VR is the switch.
 *
 * Header-only, C89 and C++, Windows only. One buffered text file per VR session in
 *   %LOCALAPPDATA%\BeG0nE\jitter\<game>_<yyyymmdd-hhmmss>.jl
 * about 10 KB a second at 90 Hz, flushed once a second from jl_present(). Thread-safe (one critical section).
 *
 * Rotations are logged as yaw / pitch / roll in degrees. jl_*_q() converts a quaternion in the OpenXR convention
 * (x right, y up, z back); if the mod already has angles, jl_*_ypr() takes them as they are. The checker only
 * compares a stream with itself, so the convention has to be consistent within one mod, not across mods.
 *
 * Usage, once per module:
 *     #define JITTERLOG_IMPLEMENTATION
 *     #include "jitterlog.h"
 * and in every other file just #include "jitterlog.h".
 *     jl_init("hard-reset-vr", "openxr");   at load
 *     jl_vr_on();  ...  jl_vr_off();         with the VR session
 */
#ifndef JITTERLOG_H
#define JITTERLOG_H

#ifdef __cplusplus
extern "C" {
#endif

void jl_init(const char* game, const char* runtime);  /* names only; no file yet */
void jl_vr_on(void);                                   /* opens the session's file; logging starts */
void jl_vr_off(void);                                  /* flushes and closes; logging stops */
int  jl_is_on(void);
void jl_pose_ypr(float yaw_deg, float pitch_deg, float roll_deg, float x, float y, float z);
void jl_pose_q(float qx, float qy, float qz, float qw, float x, float y, float z);
void jl_camera_ypr(float yaw_deg, float pitch_deg, float roll_deg, float x, float y, float z);
void jl_camera_q(float qx, float qy, float qz, float qw, float x, float y, float z);
void jl_present(void);
/* Occlusion Drift BeG0nE rides on the same log: one line per controller read. side 'L' or 'R'; tracked = the
 * runtime said the pose is valid/tracked (0 when the headset lost the controller, which is the fault that cure
 * removes). Angles and position as for the head. */
void jl_hand_ypr(char side, int tracked, float yaw_deg, float pitch_deg, float roll_deg, float x, float y, float z);
void jl_hand_q(char side, int tracked, float qx, float qy, float qz, float qw, float x, float y, float z);
void jl_mark(const char* text);                        /* a free-text line, e.g. "session FOCUSED" */

#ifdef __cplusplus
}
#endif

#ifdef JITTERLOG_IMPLEMENTATION
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <math.h>

#define JL_VERSION          1
#define JL_BUFFER_BYTES     65536        /* written out when fuller than JL_FLUSH_AT or older than JL_FLUSH_US */
#define JL_FLUSH_AT         (JL_BUFFER_BYTES - 256)
#define JL_FLUSH_US         1000000LL
#define JL_NAME_CHARS       64
#define JL_PATH_CHARS       520
#define JL_RAD2DEG          57.2957795f
#define JL_FOLDER           "\\BeG0nE\\jitter"

typedef struct {
    CRITICAL_SECTION cs;
    int cs_ready, on;
    FILE* f;
    char buf[JL_BUFFER_BYTES];
    int len;
    LONGLONG freq, t0, last_flush;
    char game[JL_NAME_CHARS], runtime[JL_NAME_CHARS];
} JlState;

static JlState jl_s;

static LONGLONG jl_now_us(void) {
    LARGE_INTEGER c;
    QueryPerformanceCounter(&c);
    return c.QuadPart * 1000000LL / jl_s.freq;
}

static void jl_flush_locked(void) {
    if (jl_s.f && jl_s.len > 0) {
        fwrite(jl_s.buf, 1, (size_t)jl_s.len, jl_s.f);
        fflush(jl_s.f);
        jl_s.len = 0;
    }
    jl_s.last_flush = jl_now_us();
}

static void jl_write_x(char kind, float yaw, float pitch, float roll, float x, float y, float z, int extra) {
    char line[160];
    int n;
    if (!jl_s.on) return;
    if (extra < 0)
        n = _snprintf(line, sizeof line, "%lld %c %.3f %.3f %.3f %.4f %.4f %.4f\n",
                      jl_now_us() - jl_s.t0, kind, yaw, pitch, roll, x, y, z);
    else
        n = _snprintf(line, sizeof line, "%lld %c %.3f %.3f %.3f %.4f %.4f %.4f %d\n",
                      jl_now_us() - jl_s.t0, kind, yaw, pitch, roll, x, y, z, extra);
    if (n <= 0) return;
    EnterCriticalSection(&jl_s.cs);
    if (jl_s.len + n >= JL_BUFFER_BYTES) jl_flush_locked();
    memcpy(jl_s.buf + jl_s.len, line, (size_t)n);
    jl_s.len += n;
    LeaveCriticalSection(&jl_s.cs);
}

static void jl_write(char kind, float yaw, float pitch, float roll, float x, float y, float z) {
    jl_write_x(kind, yaw, pitch, roll, x, y, z, -1);
}

static void jl_q_to_ypr(float qx, float qy, float qz, float qw, float* yaw, float* pitch, float* roll) {
    float sp = 2.0f * (qw * qx - qy * qz);
    if (sp > 1.0f) sp = 1.0f;
    if (sp < -1.0f) sp = -1.0f;
    *yaw   = (float)atan2(2.0f * (qw * qy + qx * qz), 1.0f - 2.0f * (qy * qy + qx * qx)) * JL_RAD2DEG;
    *pitch = (float)asin(sp) * JL_RAD2DEG;
    *roll  = (float)atan2(2.0f * (qw * qz + qx * qy), 1.0f - 2.0f * (qx * qx + qz * qz)) * JL_RAD2DEG;
}

void jl_init(const char* game, const char* runtime) {
    LARGE_INTEGER f;
    if (!jl_s.cs_ready) { InitializeCriticalSection(&jl_s.cs); jl_s.cs_ready = 1; }
    QueryPerformanceFrequency(&f);
    jl_s.freq = f.QuadPart ? f.QuadPart : 1;
    strncpy(jl_s.game, game ? game : "game", JL_NAME_CHARS - 1);
    strncpy(jl_s.runtime, runtime ? runtime : "unknown", JL_NAME_CHARS - 1);
}

void jl_vr_on(void) {
    char path[JL_PATH_CHARS], base[JL_PATH_CHARS];
    SYSTEMTIME st;
    DWORD n;
    if (!jl_s.cs_ready) jl_init(jl_s.game[0] ? jl_s.game : "game", jl_s.runtime[0] ? jl_s.runtime : "unknown");
    EnterCriticalSection(&jl_s.cs);
    if (jl_s.on) { LeaveCriticalSection(&jl_s.cs); return; }
    n = GetEnvironmentVariableA("LOCALAPPDATA", base, sizeof base);
    if (n == 0 || n >= sizeof base) strcpy(base, ".");
    strncat(base, JL_FOLDER, sizeof base - strlen(base) - 1);
    {   /* make BeG0nE\ then BeG0nE\jitter\ */
        char* slash = strrchr(base, '\\');
        if (slash) { *slash = 0; CreateDirectoryA(base, NULL); *slash = '\\'; }
        CreateDirectoryA(base, NULL);
    }
    GetLocalTime(&st);
    _snprintf(path, sizeof path, "%s\\%s_%04d%02d%02d-%02d%02d%02d.jl", base, jl_s.game,
              st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
    jl_s.f = fopen(path, "wb");
    if (jl_s.f) {
        jl_s.t0 = jl_now_us();
        jl_s.len = _snprintf(jl_s.buf, JL_BUFFER_BYTES, "#jitterlog %d game=%s runtime=%s pid=%lu\n",
                             JL_VERSION, jl_s.game, jl_s.runtime, (unsigned long)GetCurrentProcessId());
        jl_s.on = 1;
        jl_flush_locked();
    }
    LeaveCriticalSection(&jl_s.cs);
}

void jl_vr_off(void) {
    if (!jl_s.cs_ready) return;
    EnterCriticalSection(&jl_s.cs);
    if (jl_s.on) {
        jl_s.on = 0;
        if (jl_s.len + 8 < JL_BUFFER_BYTES) { memcpy(jl_s.buf + jl_s.len, "#end\n", 5); jl_s.len += 5; }
        jl_flush_locked();
        fclose(jl_s.f);
        jl_s.f = NULL;
    }
    LeaveCriticalSection(&jl_s.cs);
}

int jl_is_on(void) { return jl_s.on; }

void jl_pose_ypr(float yaw, float pitch, float roll, float x, float y, float z) { jl_write('P', yaw, pitch, roll, x, y, z); }
void jl_camera_ypr(float yaw, float pitch, float roll, float x, float y, float z) { jl_write('C', yaw, pitch, roll, x, y, z); }

void jl_pose_q(float qx, float qy, float qz, float qw, float x, float y, float z) {
    float yaw, pitch, roll;
    if (!jl_s.on) return;
    jl_q_to_ypr(qx, qy, qz, qw, &yaw, &pitch, &roll);
    jl_write('P', yaw, pitch, roll, x, y, z);
}

void jl_camera_q(float qx, float qy, float qz, float qw, float x, float y, float z) {
    float yaw, pitch, roll;
    if (!jl_s.on) return;
    jl_q_to_ypr(qx, qy, qz, qw, &yaw, &pitch, &roll);
    jl_write('C', yaw, pitch, roll, x, y, z);
}

void jl_hand_ypr(char side, int tracked, float yaw, float pitch, float roll, float x, float y, float z) {
    jl_write_x(side == 'L' ? 'L' : 'R', yaw, pitch, roll, x, y, z, tracked ? 1 : 0);
}

void jl_hand_q(char side, int tracked, float qx, float qy, float qz, float qw, float x, float y, float z) {
    float yaw, pitch, roll;
    if (!jl_s.on) return;
    jl_q_to_ypr(qx, qy, qz, qw, &yaw, &pitch, &roll);
    jl_write_x(side == 'L' ? 'L' : 'R', yaw, pitch, roll, x, y, z, tracked ? 1 : 0);
}

void jl_present(void) {
    if (!jl_s.on) return;
    jl_write('F', 0, 0, 0, 0, 0, 0);
    if (jl_now_us() - jl_s.last_flush > JL_FLUSH_US || jl_s.len > JL_FLUSH_AT) {
        EnterCriticalSection(&jl_s.cs);
        jl_flush_locked();
        LeaveCriticalSection(&jl_s.cs);
    }
}

void jl_mark(const char* text) {
    char line[200];
    int n;
    if (!jl_s.on || !text) return;
    n = _snprintf(line, sizeof line, "%lld M %s\n", jl_now_us() - jl_s.t0, text);
    if (n <= 0) return;
    EnterCriticalSection(&jl_s.cs);
    if (jl_s.len + n >= JL_BUFFER_BYTES) jl_flush_locked();
    memcpy(jl_s.buf + jl_s.len, line, (size_t)n);
    jl_s.len += n;
    LeaveCriticalSection(&jl_s.cs);
}

#endif /* JITTERLOG_IMPLEMENTATION */
#endif /* JITTERLOG_H */
