// Green monitor with a faint, striped Claude starburst behind the text and a light that
// runs down the screen over it. Same letter glow, glass tint, dark corners and
// user-message colour as green-monitor/robco.hlsl, but the scanlines live on the picture.
// The picture comes from the profile's "experimental.pixelShaderImagePath"
// (starburst.png by default; any picture works, it is turned green here).
// Moving pictures: tools/gif-to-sheet.py lays a GIF's frames out in a grid on one picture,
// and the four SHEET/FRAME numbers below tell the shader how to flip through them.
// Left at 1 / 1 / 1 they mean "a normal still picture".
Texture2D shaderTexture;
Texture2D image;
SamplerState samplerState;
cbuffer PixelShaderSettings { float Time; float Scale; float2 Resolution; float4 Background; };

static const float  GLOW_RADIUS   = 2.5;    // pixels; how far the halo spreads
static const float  GLOW_STRENGTH = 0.45;   // halo added around letters (letters stay sharp)
static const float3 GLASS_TINT    = float3(0.020, 0.070, 0.035); // green of the empty screen
static const float  VIGNETTE      = 1.35;   // how dark the corners get

static const float3 PIC_GREEN     = float3(0.30, 1.00, 0.50); // colour the picture is drawn in
static const float  PIC_STRENGTH  = 0.30;   // how faint the picture is (0 = gone, 1 = full)
static const float  PIC_CONTRAST  = 1.4;    // pushes darks down so the picture reads as a shape
static const float  PIC_SIZE      = 0.80;   // picture height as a fraction of the window height
static const float  PIC_X         = 0.5;    // where it sits (0 = left edge, 1 = right edge)
static const float  PIC_Y         = 0.5;    // where it sits (0 = top, 1 = bottom)
static const float  PIC_EDGE_FADE = 0.12;   // soft fade at the picture's left/right edges
static const float  STRIPE_PERIOD = 4.0;    // pixels per stripe cycle on the picture
static const float  STRIPE_DARKEN = 0.55;   // how dark the dark stripe is
static const float  ROLL_SECONDS  = 9.0;    // time for the light bar to travel top to bottom
static const float  ROLL_HEIGHT   = 0.10;   // bar height (fraction of the screen)
static const float  ROLL_STRENGTH = 0.55;   // how much the bar lights the picture up

static const uint   SHEET_COLS    = 1;      // frames per row in a frame sheet (1 = still picture)
static const uint   SHEET_ROWS    = 1;      // rows of frames in a frame sheet (1 = still picture)
static const uint   FRAME_COUNT   = 1;      // frames used (the last row may be part-empty)
static const float  FRAME_SECONDS = 0.08;   // how long each frame shows

static const float3 MARKER        = float3(0.0, 0.0, 3.0 / 255.0); // user-message background
static const float3 USER_GREEN    = float3(0.80, 1.00, 0.45);      // colour of the user's text
static const int    ROW_SAMPLES   = 48;     // spots checked along a row to find the marker

bool isMarker(float3 c)
{
    return all(abs(c - MARKER) < 0.5 / 255.0);
}

float ink(float3 c)
{
    return saturate(max(c.r, max(c.g, c.b)));
}

float3 sampleScreen(float2 uv)
{
    float3 c = shaderTexture.Sample(samplerState, uv).rgb;
    if (isMarker(c)) return float3(0, 0, 0);
    return c;
}

float3 recolour(float2 uv)
{
    float3 c = sampleScreen(uv);
    bool userRow = false;
    for (int i = 0; i < ROW_SAMPLES; i++)
    {
        float x = (i + 0.5) / ROW_SAMPLES;
        if (isMarker(shaderTexture.Sample(samplerState, float2(x, uv.y)).rgb)) { userRow = true; break; }
    }
    if (userRow) c = USER_GREEN * ink(c);
    return c;
}

// The picture, fitted to the window height (so it grows and shrinks with the window),
// returned as a 0..1 brightness plus how much of it is "there" at this spot.
float2 picture(float4 pos)
{
    float w, h;
    image.GetDimensions(w, h);
    if (w < 1 || h < 1) return float2(0, 0);
    w /= SHEET_COLS;
    h /= SHEET_ROWS;

    float picH = Resolution.y * PIC_SIZE;
    float picW = picH * (w / h);
    float left = (Resolution.x - picW) * PIC_X;
    float top  = (Resolution.y - picH) * PIC_Y;
    float2 uv  = float2((pos.x - left) / picW, (pos.y - top) / picH);
    if (uv.x < 0 || uv.x > 1 || uv.y < 0 || uv.y > 1) return float2(0, 0);

    // pick this moment's frame, staying half a pixel inside it so neighbours never bleed in
    uint   frame = min((uint)(frac(Time / (FRAME_SECONDS * FRAME_COUNT)) * FRAME_COUNT), FRAME_COUNT - 1);
    float2 cell  = float2(frame % SHEET_COLS, frame / SHEET_COLS);
    float2 inner = clamp(uv, 0.5 / float2(w, h), 1.0 - 0.5 / float2(w, h));
    float3 p = image.Sample(samplerState, (cell + inner) / float2(SHEET_COLS, SHEET_ROWS)).rgb;
    float  l = dot(p, float3(0.299, 0.587, 0.114));
    l = saturate(pow(l, PIC_CONTRAST) * 1.25);
    float fade = smoothstep(0, PIC_EDGE_FADE, uv.x) * smoothstep(0, PIC_EDGE_FADE, 1 - uv.x)
               * smoothstep(0, PIC_EDGE_FADE, uv.y) * smoothstep(0, PIC_EDGE_FADE, 1 - uv.y);
    return float2(l, fade);
}

// the background fades to black in a thin strip at the left and right edges of the window, where the
// picture is cut off; the top and bottom are drawn right to the edge. The letters do not fade.
static const float  SIDE_FADE     = 0.04;   // share of the width over which each side fades to black
float screenFade(float2 tex)
{
    return smoothstep(0.0, 1.0, saturate(min(tex.x, 1.0 - tex.x) / SIDE_FADE));
}

float4 main(float4 pos : SV_POSITION, float2 tex : TEXCOORD) : SV_TARGET
{
    float3 text = recolour(tex);

    // halo: average of nearby pixels, added on top so the sharp letter stays underneath
    float2 px = GLOW_RADIUS * max(Scale, 1.0) / Resolution;
    float3 glow = 0;
    glow += sampleScreen(tex + float2( px.x, 0));
    glow += sampleScreen(tex + float2(-px.x, 0));
    glow += sampleScreen(tex + float2(0,  px.y));
    glow += sampleScreen(tex + float2(0, -px.y));
    glow += sampleScreen(tex + float2( px.x,  px.y) * 0.7);
    glow += sampleScreen(tex + float2(-px.x,  px.y) * 0.7);
    glow += sampleScreen(tex + float2( px.x, -px.y) * 0.7);
    glow += sampleScreen(tex + float2(-px.x, -px.y) * 0.7);
    text += glow / 8.0 * GLOW_STRENGTH;

    // the picture: faint green, striped, lit by the rolling bar
    float2 pic   = picture(pos);
    float  s     = max(Scale, 1.0);
    float  strip = (fmod(floor(pos.y), STRIPE_PERIOD * s) < STRIPE_PERIOD * s * 0.5) ? (1.0 - STRIPE_DARKEN) : 1.0;
    float  rollY = frac(Time / ROLL_SECONDS) * 1.4 - 0.2;
    float  roll  = exp(-pow((tex.y - rollY) / ROLL_HEIGHT, 2.0));
    float  bright = pic.x * pic.y * strip * (PIC_STRENGTH + roll * ROLL_STRENGTH);
    float3 back  = (GLASS_TINT + PIC_GREEN * bright) * screenFade(tex);

    // letters sit on top; the picture fades out underneath them so they stay readable
    float3 color = text + back * (1.0 - ink(text));

    // dark corners
    float2 d = tex - 0.5;
    color *= saturate(1.0 - dot(d, d) * VIGNETTE);

    return float4(color, 1.0);
}
