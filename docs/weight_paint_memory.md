# Weight Paint brush memory

While Gamify is enabled, Weight Paint brushes default to Accumulate on when
first used in a file. Each brush asset remembers its own on/off setting.
Entering Weight Paint or selecting another brush restores that brush's setting.

The Gamify menu has **Remember Weight-Brush Accumulate Setting**, enabled by
default, in its own section. It is also available for meshes in Object and
Weight Paint modes. Turning it off stops both recording and restoring settings,
leaving the brush's current Accumulate value alone. Turning it back on restores
the remembered value. The toggle is saved with the scene in the blend file.

Settings are stored as scene custom properties in the current blend file and
shared across its scenes. Save the blend file to retain changes across restarts.
No external brush asset or startup preferences are saved or modified.

The active brush is checked every quarter second. UI changes to Accumulate also
notify the memory immediately, and saving captures the current setting. Other
paint modes are unaffected. A local brush without an asset reference uses its
name and library path as its identity; renaming it starts a new remembered entry.

Gamify must be enabled when the file is reopened. The Blender integration test
uses a temporary file to check switching brushes, mode changes, saving, loading,
first-use defaults, and handler/timer cleanup.
