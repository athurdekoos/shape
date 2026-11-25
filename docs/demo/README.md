# Recording the demo

`record.py` runs the real `bin/shape` in the `examples` folder, on a pseudo-terminal of 100 columns by 28 rows. It types
`shape`, presses the keys in its `STORYBOARD` with the pauses written there, and writes everything the terminal received
to `demo.cast`. It needs Python 3.9 or later, bash and Node.js, on Linux or macOS. To change the demo, edit `STORYBOARD`.

`render.py` turns `demo.cast` into `docs/img/demo.gif` and two stills, `docs/img/list.png` and `docs/img/outline.png`.
It needs [agg](https://github.com/asciinema/agg) on the PATH, in the `AGG` environment variable or given with `--agg`,
the font DejaVu Sans Mono, and a Python with pyte and Pillow. Its font, font size and colours are set at the top of the file.

Run these two commands from the top of the repository:
```bash
python3 docs/demo/record.py
uv run --no-project --with pyte --with pillow python3 docs/demo/render.py
```
