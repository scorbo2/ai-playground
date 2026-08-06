# Objective

Produce a skeletal (but runnable) single-file Python codebase that can be used as a template for creating
simple vector-graphics games, similar to classic arcade games. The only dependencies are
`pygame-ce` and the Python standard library. The codebase should be clean, well-organized,
and well-commented, such that it is possible to use it as an easy starting point when
creating a new game.

## Window and setup

The program starts in a resizable 800x600 window. The window has a minimum size of 640x480, but no maximum size.
There is no forced aspect ratio (that is, user can resize the window into a portrait shape or a landscape shape
or a square shape, as long as the width is >= 640 and the height is >= 480).

The `F11` key should act as a full-screen mode toggle. Entering full-screen mode should use the current display's
native resolution to show the game on the entire display. Hitting `F11` again should return to a window with
the same position and dimensions that were in effect before full-screen mode was activated.

### Command-line arguments

- `--width` should accept any positive integer greater than or equal to 640. This is the starting window width,
  and any value given here overrides the default value of 800.
- `--height` should accept any positive integer greater than or equal to 480. This is the starting window height,
  and any value given here overrides the default value of 600.
- `--fullscreen` - if present, the program immediately switches to fullscreen mode when launching.

## Game modes

The program should implement a state machine with the following modes:

- **Title Screen Mode** (default mode). Shown when the program is first launched. Player can enter game mode or exit.
- **Game Mode**. This template program simply displays the text "GAME MODE" in large centered white text on
  a simple black background. This is a placeholder for the actual game code. The user can press ESC to
  toggle Pause Mode.
- **Pause Mode**. Can only be entered from game mode. Simple white text centered on a simple black background
  reads "PAUSE" on line 1, "PRESS ESC TO RESUME" on line 2, and "PRESS X TO EXIT" on line 3. Pressing ESC exits
  Pause Mode and resumes Game Mode. Pressing `x` from within Pause Mode returns to Title Screen Mode.
- **Game Over Mode**. Simple red centered text on a black background reads "GAME OVER". Pressing ESC returns
  to Title Screen Mode. There is no way to enter Game Over Mode within this template program. The logic for
  entering Game Over Mode will be filled in when an actual game is created from this template.
- **Test Mode**. Activate via the `--test` command-line argument. For testing purposes only.

### Title Screen Mode

The text "Arcade Template" (a placeholder game title) should be displayed in very large green text centered
in the upper half of the screen. Smaller white text underneath the title should read "Press Enter to start"
on one line, and "Press ESC to exit" on the next line. The background is a simple solid black color.

Pressing `Enter` from Title Screen Mode enters Game Mode. Pressing `ESC` from Title Screen Mode exits the
program with exit code 0 (normal termination).

### Window resize handler

The placeholder text displayed in each game mode must respond to window resize events and fullscreen mode toggle.
That is, centered text should remain centered even as the window grows or shrinks. Font sizes remain fixed.

### Test Mode

This mode can only be accessed by passing the `--test` argument on the command line. Start Title Screen Mode
and then exit the application with exit code 0 (normal termination) after 250ms. This mode simply confirms that
the game starts up correctly. 

## Sound

If a file named `audio.json` exists in the same directory as the Python source file, it should be loaded.
It is **not** an error condition if this file does not exist or is not readable.

If present, the file is expected to have this structure:

```
{
  "audioMapping": [
    {
      "gameEvent": "UNIQUE_EVENT_CODE",
      "audio": "/path/to/audio.wav"
    },
    ...
  ]
}
```

This is a simple array of mappings, each containing a unique game event descriptor and a path to an audio file corresponding
to that game event. If the given path is relative, it is assumed to be relative to the directory containing the Python source file.

It is not an error if a named audio file does not exist or is not readable, but a log warning should be emitted in that case.

All named audio files should be eagerly loaded on startup and cached in-memory.

### No audio in test mode

If `--test` is given on the command line to enter Test Mode, `audio.json` can be ignored entirely (no parsing, no eager
loading, no audio caching, no audio output). Skip pygame.mixer.init().

### Supported game events

This template project supports the following game events. Implementations can add to this list.

- `startup`: palyed when program starts up (except in Test Mode as noted above).
- `newGame`: played on transition from Title Screen Mode to Game Mode
- `pause`: played on transition from Game Mode to Pause Mode
- `unpause`: played on transition from Pause Mode to Game Mode

If an unrecognized game event descriptor is found, just ignore it.

### Command-line arguments

- `--nosound` - if given, all audio is disabled. Do not parse `audio.json`. Skip pygame.mixer.init().

## Miscellaneous

- Use Python's logging module for warnings (INFO level for startup, WARNING for missing audio files).
- Use `argparse` for command-line argument parsing.
- Use type hints and docstrings for functions and classes.
- **Framerate**: Locked at 60 FPS via `clock.tick(60)`
- **Good use of constants, no magic numbers**: use constants as needed, and keep them grouped together
  near the top of the file. Examples: `DEFAULT_WINDOW_WIDTH`, `DEFAULT_WINDOW_HEIGHT`, etc.
- Use `TODO` markers in comments to describe where actual game logic and code should go.
- Do not add external dependencies beyond `pygame-ce` and the Python standard library. Keep the code
  minimal but production-ready. Prioritize readability and clear extension points.

