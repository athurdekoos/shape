# Changelog

## 0.1.0, 25 November 2026

- This is the first release. `shape` shows a program as an outline of its states, routes, ways it goes wrong and conditions.
- `shape --check` reads each program's JSON strictly and says in sentences what is wrong and what is probably a mistake.
- The format is version 0.1. [docs/FORMAT.md](docs/FORMAT.md) describes it, and [schema/shape.schema.json](schema/shape.schema.json) is the same format for a tool.
- [python/shapetable.py](python/shapetable.py) lets a Python program keep its moves in one table, run through that table and print it.
