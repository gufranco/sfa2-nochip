#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include <SDL.h>

#include "libretro.h"
#include "snes9x.h"
#include "memmap.h"

#include "windowed_lorom.h"

static const int SCREEN_WIDTH = 256;
static const int SCREEN_HEIGHT = 224;
static const int DEFAULT_SCALE = 3;
static const int AUDIO_CHANNELS = 2;
static const int AUDIO_LATENCY_FRAMES = 4;
static const int LOOKUP_TABLE_BANK = 0x60;
static const unsigned long SCAN_BUDGET = 64;
static const int CAPTURE_TAIL_FRAMES = 240;

unsigned long sf_bank_reads[256];

static unsigned frames_seen = 0;
static unsigned last_read_bank = 0xFFFF;
static unsigned long scan_run = 0;
static unsigned scan_start_addr = 0;
static unsigned long scan_misses = 0;
static unsigned long scan_total = 0;
static unsigned capture_until = 0;
static FILE *probe_log = NULL;

extern "C" void sf_note_read(uint32 address)
{
    const unsigned bank = (address >> 16) & 0xFF;
    if (bank == LOOKUP_TABLE_BANK) {
        if (last_read_bank != LOOKUP_TABLE_BANK) {
            scan_run = 1;
            scan_start_addr = address & 0xFFFF;
        } else {
            scan_run++;
        }
    } else if (last_read_bank == LOOKUP_TABLE_BANK && scan_run) {
        scan_total++;
        if (scan_run > SCAN_BUDGET) {
            scan_misses++;
            capture_until = frames_seen + CAPTURE_TAIL_FRAMES;
            if (probe_log) {
                fprintf(probe_log, "SCANLEN frame=%u addr=%04X steps=%lu\n",
                        frames_seen, scan_start_addr, scan_run);
                fflush(probe_log);
            }
        }
        scan_run = 0;
    }
    last_read_bank = bank;
}

extern "C" void sf_note_write(uint32 address) { (void)address; }

extern "C" void sf_note_write_word(uint32 address) { (void)address; }

static SDL_Window *window = NULL;
static SDL_Renderer *renderer = NULL;
static SDL_Texture *texture = NULL;
static SDL_AudioDeviceID audio_device = 0;
static unsigned texture_width = 0;
static unsigned texture_height = 0;
static bool running = true;

static bool cb_environment(unsigned cmd, void *data)
{
    switch (cmd) {
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
        *(const char **)data = ".";
        return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
    case RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL:
    case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
    case RETRO_ENVIRONMENT_SET_VARIABLES:
    case RETRO_ENVIRONMENT_SET_MEMORY_MAPS:
    case RETRO_ENVIRONMENT_SET_GEOMETRY:
    case RETRO_ENVIRONMENT_SET_SUPPORT_ACHIEVEMENTS:
        return true;
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
        *(bool *)data = false;
        return true;
    default:
        return false;
    }
}

static bool ensure_texture(unsigned width, unsigned height)
{
    if (texture && width == texture_width && height == texture_height) {
        return true;
    }
    if (texture) {
        SDL_DestroyTexture(texture);
    }
    texture = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGB565,
                                SDL_TEXTUREACCESS_STREAMING, (int)width, (int)height);
    if (!texture) {
        fprintf(stderr, "cannot create texture: %s\n", SDL_GetError());
        return false;
    }
    texture_width = width;
    texture_height = height;
    return true;
}

static const char *dump_directory(void)
{
    const char *set = getenv("SFPLAYDUMP");
    return set ? set : "build/shots/play";
}

static void write_ppm(const void *data, unsigned width, unsigned height, size_t pitch,
                      const char *tag)
{
    char path[512];
    snprintf(path, sizeof(path), "%s/%s-%06u.ppm", dump_directory(), tag, frames_seen);
    FILE *out = fopen(path, "wb");
    if (!out) {
        return;
    }
    fprintf(out, "P6\n%u %u\n255\n", width, height);
    const uint16_t *pixels = (const uint16_t *)data;
    const unsigned stride = (unsigned)(pitch / sizeof(uint16_t));
    for (unsigned y = 0; y < height; y++) {
        for (unsigned x = 0; x < width; x++) {
            const uint16_t value = pixels[y * stride + x];
            const unsigned char rgb[3] = {
                (unsigned char)(((value >> 11) & 0x1F) * 255 / 31),
                (unsigned char)(((value >> 5) & 0x3F) * 255 / 63),
                (unsigned char)((value & 0x1F) * 255 / 31),
            };
            fwrite(rgb, 1, 3, out);
        }
    }
    fclose(out);
}

static bool capture_requested = false;

static void cb_video(const void *data, unsigned width, unsigned height, size_t pitch)
{
    if (!data || !ensure_texture(width, height)) {
        return;
    }
    frames_seen++;
    if (capture_requested || frames_seen < capture_until) {
        write_ppm(data, width, height, pitch, capture_requested ? "asked" : "miss");
        capture_requested = false;
    }
    SDL_UpdateTexture(texture, NULL, data, (int)pitch);
    SDL_RenderClear(renderer);
    SDL_RenderCopy(renderer, texture, NULL, NULL);
    SDL_RenderPresent(renderer);
}

static void cb_audio(int16_t left, int16_t right)
{
    const int16_t pair[AUDIO_CHANNELS] = {left, right};
    if (audio_device) {
        SDL_QueueAudio(audio_device, pair, sizeof(pair));
    }
}

static size_t cb_audio_batch(const int16_t *data, size_t frames)
{
    if (audio_device) {
        SDL_QueueAudio(audio_device, data, (Uint32)(frames * AUDIO_CHANNELS * sizeof(int16_t)));
    }
    return frames;
}

static void cb_input_poll(void) {}

struct KeyBinding {
    SDL_Scancode key;
    unsigned button;
};

static const KeyBinding BINDINGS[] = {
    {SDL_SCANCODE_UP, RETRO_DEVICE_ID_JOYPAD_UP},
    {SDL_SCANCODE_DOWN, RETRO_DEVICE_ID_JOYPAD_DOWN},
    {SDL_SCANCODE_LEFT, RETRO_DEVICE_ID_JOYPAD_LEFT},
    {SDL_SCANCODE_RIGHT, RETRO_DEVICE_ID_JOYPAD_RIGHT},
    {SDL_SCANCODE_Z, RETRO_DEVICE_ID_JOYPAD_B},
    {SDL_SCANCODE_X, RETRO_DEVICE_ID_JOYPAD_A},
    {SDL_SCANCODE_A, RETRO_DEVICE_ID_JOYPAD_Y},
    {SDL_SCANCODE_S, RETRO_DEVICE_ID_JOYPAD_X},
    {SDL_SCANCODE_Q, RETRO_DEVICE_ID_JOYPAD_L},
    {SDL_SCANCODE_W, RETRO_DEVICE_ID_JOYPAD_R},
    {SDL_SCANCODE_RETURN, RETRO_DEVICE_ID_JOYPAD_START},
    {SDL_SCANCODE_RSHIFT, RETRO_DEVICE_ID_JOYPAD_SELECT},
    {SDL_SCANCODE_LSHIFT, RETRO_DEVICE_ID_JOYPAD_SELECT},
};

static int16_t cb_input_state(unsigned port, unsigned device, unsigned index, unsigned id)
{
    (void)device;
    (void)index;
    if (port != 0) {
        return 0;
    }
    const Uint8 *keys = SDL_GetKeyboardState(NULL);
    for (size_t i = 0; i < sizeof(BINDINGS) / sizeof(BINDINGS[0]); i++) {
        if (BINDINGS[i].button == id && keys[BINDINGS[i].key]) {
            return 1;
        }
    }
    return 0;
}

static bool read_file(const char *path, std::vector<unsigned char> &out)
{
    FILE *file = fopen(path, "rb");
    if (!file) {
        return false;
    }
    fseek(file, 0, SEEK_END);
    const long size = ftell(file);
    fseek(file, 0, SEEK_SET);
    out.resize((size_t)size);
    const size_t got = fread(out.data(), 1, out.size(), file);
    fclose(file);
    return got == out.size();
}

static void pump_events(void)
{
    SDL_Event event;
    while (SDL_PollEvent(&event)) {
        if (event.type == SDL_QUIT) {
            running = false;
        } else if (event.type == SDL_KEYDOWN) {
            if (event.key.keysym.scancode == SDL_SCANCODE_ESCAPE) {
                running = false;
            } else if (event.key.keysym.scancode == SDL_SCANCODE_F12
                       || event.key.keysym.scancode == SDL_SCANCODE_C
                       || event.key.keysym.scancode == SDL_SCANCODE_GRAVE) {
                capture_requested = true;
                capture_until = frames_seen + CAPTURE_TAIL_FRAMES;
                printf("capture at frame %u: lookups %lu, over-budget %lu\n",
                       frames_seen, scan_total, scan_misses);
                fflush(stdout);
                if (probe_log) {
                    fprintf(probe_log, "CAPTURE frame=%u lookups=%lu over_budget=%lu\n",
                            frames_seen, scan_total, scan_misses);
                    fflush(probe_log);
                }
            } else if (event.key.keysym.scancode == SDL_SCANCODE_R
                       && (event.key.keysym.mod & KMOD_GUI)) {
                retro_reset();
            }
        }
    }
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: sfplay <rom> [-1 stock | -2 windowed lorom]\n");
        return 2;
    }

    const int mirror_shift = argc > 2 ? atoi(argv[2]) : -2;

    std::vector<unsigned char> rom;
    if (!read_file(argv[1], rom)) {
        fprintf(stderr, "cannot read %s\n", argv[1]);
        return 1;
    }

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO) != 0) {
        fprintf(stderr, "SDL_Init failed: %s\n", SDL_GetError());
        return 1;
    }

    const char *slash = strrchr(argv[1], '/');
    const char *title = slash ? slash + 1 : argv[1];
    window = SDL_CreateWindow(title, SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                              SCREEN_WIDTH * DEFAULT_SCALE, SCREEN_HEIGHT * DEFAULT_SCALE,
                              SDL_WINDOW_SHOWN | SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI);
    if (!window) {
        fprintf(stderr, "cannot create window: %s\n", SDL_GetError());
        return 1;
    }

    renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!renderer) {
        renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
    }
    if (!renderer) {
        fprintf(stderr, "cannot create renderer: %s\n", SDL_GetError());
        return 1;
    }
    SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "nearest");
    SDL_RenderSetLogicalSize(renderer, SCREEN_WIDTH, SCREEN_HEIGHT);

    retro_set_environment(cb_environment);
    retro_set_video_refresh(cb_video);
    retro_set_audio_sample(cb_audio);
    retro_set_audio_sample_batch(cb_audio_batch);
    retro_set_input_poll(cb_input_poll);
    retro_set_input_state(cb_input_state);
    retro_init();

    retro_game_info info;
    memset(&info, 0, sizeof(info));
    info.path = argv[1];
    info.data = rom.data();
    info.size = rom.size();

    if (!retro_load_game(&info)) {
        fprintf(stderr, "the core refused this image\n");
        return 1;
    }

    if (mirror_shift != -1) {
        if (Memory.ROM && Memory.MAX_ROM_SIZE >= rom.size()) {
            memcpy(Memory.ROM, rom.data(), rom.size());
        }
        Memory.CalculatedSize = (uint32)rom.size();
        Settings.SDD1 = FALSE;
        install_windowed_lorom_map(mirror_shift);
        S9xReset();
        install_windowed_lorom_map(mirror_shift);
    }

    retro_system_av_info av;
    retro_get_system_av_info(&av);

    SDL_AudioSpec want, have;
    SDL_zero(want);
    want.freq = (int)av.timing.sample_rate;
    want.format = AUDIO_S16SYS;
    want.channels = AUDIO_CHANNELS;
    want.samples = 512;
    audio_device = SDL_OpenAudioDevice(NULL, 0, &want, &have, 0);
    if (audio_device) {
        SDL_PauseAudioDevice(audio_device, 0);
    }

    const Uint32 audio_cap = (Uint32)(have.freq * AUDIO_CHANNELS * sizeof(int16_t)
                                      * AUDIO_LATENCY_FRAMES / 60);

    printf("sfplay: %s, %u banks, map %d, %ux%u at %.2f Hz\n", argv[1],
           (unsigned)(rom.size() >> 16), mirror_shift,
           av.geometry.base_width, av.geometry.base_height, av.timing.fps);
    printf("keys: arrows, Z=B X=A A=Y S=X, Q=L W=R, Enter=Start Shift=Select, F12 capture, Cmd+R reset, Esc quit\n");
    printf("frames land in %s\n", dump_directory());
    fflush(stdout);

    const char *log_path = getenv("SFPLAYLOG") ? getenv("SFPLAYLOG") : "build/logs/play-probe.txt";
    probe_log = fopen(log_path, "w");

    while (running) {
        pump_events();
        retro_run();
        while (audio_device && SDL_GetQueuedAudioSize(audio_device) > audio_cap) {
            SDL_Delay(1);
        }
    }

    printf("exit: frames %u, lookups %lu, over-budget %lu\n",
           frames_seen, scan_total, scan_misses);
    if (probe_log) {
        fprintf(probe_log, "EXIT frames=%u lookups=%lu over_budget=%lu\n",
                frames_seen, scan_total, scan_misses);
        fclose(probe_log);
    }
    retro_unload_game();
    retro_deinit();
    if (audio_device) {
        SDL_CloseAudioDevice(audio_device);
    }
    if (texture) {
        SDL_DestroyTexture(texture);
    }
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
