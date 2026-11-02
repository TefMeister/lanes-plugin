// The still copy of lanes.hlsl: the same green monitor and Lanes banner, but nothing moves.
// The rolling light bar and the frame sheet are gone, so the shader never reads Time. Windows
// Terminal redraws a window over and over only while its shader reads Time; without it the
// window is drawn again only when the text changes, which takes most of the load off the PC.
// Use it with a still picture (lanes.png) in "experimental.pixelShaderImagePath".
Texture2D shaderTexture;
Texture2D image;
SamplerState samplerState;
cbuffer PixelShaderSettings { float Time; float Scale; float2 Resolution; float4 Background; };

static const float  GLOW_RADIUS   = 2.5;    // pixels; how far the halo spreads
static const float  GLOW_STRENGTH = 0.45;   // halo added around letters (letters stay sharp)
static const float3 GLASS_TINT    = float3(0.020, 0.070, 0.035); // green of the empty screen
static const float  VIGNETTE      = 1.35;   // how dark the corners get

static const float3 PIC_GREEN     = float3(0.30, 1.00, 0.50); // the one colour the banner is drawn in
static const float  PIC_STRENGTH  = 0.20;   // how faint the picture is (0 = gone, 1 = full)
static const float  PIC_CONTRAST  = 1.4;    // pushes darks down so the banner reads clearly
static const float  PIC_X         = 0.5;    // where the banner sits (0 = left edge, 1 = right edge)
static const float  PIC_EDGE_FADE = 0.06;   // soft fade at the picture's left/right edges
static const float  STRIPE_PERIOD = 4.0;    // pixels per stripe cycle on the picture
static const float  STRIPE_DARKEN = 0.55;   // how dark the dark stripe is

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
float4 picture(float4 pos)
{
    float w, h;
    image.GetDimensions(w, h);
    if (w < 1 || h < 1) return float4(0, 0, 0, 0);

    // whole banner fits inside the window (wide picture: fills the width, centred top to bottom)
    float fit  = min(Resolution.x / w, Resolution.y / h);
    float picW = w * fit;
    float picH = h * fit;
    float left = (Resolution.x - picW) * PIC_X;
    float top  = (Resolution.y - picH) * 0.5;
    float2 uv  = float2((pos.x - left) / picW, (pos.y - top) / picH);
    if (uv.x < 0 || uv.x > 1 || uv.y < 0 || uv.y > 1) return float4(0, 0, 0, 0);

    float3 p = image.Sample(samplerState, uv).rgb;
    float  l = dot(p, float3(0.299, 0.587, 0.114));
    l = saturate(pow(l, PIC_CONTRAST) * 1.25);
    float fade = smoothstep(0, PIC_EDGE_FADE, uv.x) * smoothstep(0, PIC_EDGE_FADE, 1 - uv.x)
               * smoothstep(0, PIC_EDGE_FADE, uv.y) * smoothstep(0, PIC_EDGE_FADE, 1 - uv.y);
    return float4(PIC_GREEN * l, fade);
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

    // the picture: faint green, striped, still
    float4 pic   = picture(pos);
    float  s     = max(Scale, 1.0);
    float  strip = (fmod(floor(pos.y), STRIPE_PERIOD * s) < STRIPE_PERIOD * s * 0.5) ? (1.0 - STRIPE_DARKEN) : 1.0;
    float  bright = pic.w * strip * PIC_STRENGTH;
    float3 back  = (GLASS_TINT + pic.rgb * bright) * screenFade(tex);

    // letters sit on top; the picture fades out underneath them so they stay readable
    float3 color = text + back * (1.0 - ink(text));

    // dark corners
    float2 d = tex - 0.5;
    color *= saturate(1.0 - dot(d, d) * VIGNETTE);

    return float4(color, 1.0);
}
