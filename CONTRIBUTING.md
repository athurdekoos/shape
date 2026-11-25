# Contributing

Changes are welcome. These are the rules the code already follows.

- **Tests first.** Write the test that fails, then the code. Run `python3 -m pytest -q` before
  you open a pull request.
- **Standard library only.** `shape` and `python/shapetable.py` must run on Python 3.9 with
  nothing installed. The tests may use `pytest` and `jsonschema`.
- **No program is ever run for its work.** `shape` runs the commands listed in `shape.json` to
  read their JSON, and it parses Python files to read a docstring. It does nothing else to a
  program.
- **Every message is a sentence.** A problem or a note names the state and the event, and
  says what was expected.

## Changing the format

The format is in four places, and a change must reach all four in one pull request:
[lib/shapeformat.py](lib/shapeformat.py), [docs/FORMAT.md](docs/FORMAT.md),
[schema/shape.schema.json](schema/shape.schema.json) and the tests in
[tests/test_format.py](tests/test_format.py).

A description that is valid today should stay valid. Add a key or a shorthand; do not
change what an existing one means.

## Adding an example in another language

Put it in its own folder under [examples/](examples/). It should keep its moves in one table,
take every move from that table, print each move it takes as a line of the form
`state event -> target`, and print the table as JSON with `--shape`. Add it to
[examples/shape.json](examples/shape.json) and add a test like the ones in
[tests/test_examples.py](tests/test_examples.py), which is skipped when the language is not installed.
