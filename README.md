# uqal-core

The core engine of [UQAL](https://uqal-lang.github.io/uqal-docs) — a unified query abstraction layer that lets you write one query syntax and run it against any supported database.

`uqal-core` contains the parser, grammar builder, AST, module loader, and CLI. It is the runtime that all UQAL modules plug into.

---

## What is UQAL?

UQAL is a database-agnostic query language. Instead of writing SQL for PostgreSQL, Cypher for Neo4j, and MQL for MongoDB separately, you write UQAL once and the appropriate module translates it into the native query for the connected database.

```
mydb.users.get_table(where active = true, fields id, name)
```

---

## Installation

```bash
uv add uqal-core
```

Requires Python 3.12+.

---

## Quick Start

```bash
# Start the interactive UQAL shell
uqal shell

# Run a query file
uqal run query.uqal

# List loaded modules
uqal list-modules
```

---

## Modules

Database support comes from modules. Standard modules ship with `uqal-core`. Community modules are installed separately:

```bash
uv add uqal-postgis
uqal add-module community.postgis
```

Browse available modules: [uqal-lang/uqal-modules](https://github.com/uqal-lang/uqal-modules)

---

## Development Setup

```bash
git clone https://github.com/uqal-lang/uqal-core
cd uqal-core
uv sync
uv run pytest
```

Dev scripts are in `scripts/dev/`:

```bash
# Parse and translate a query
uv run python scripts/dev/check_query.py "mydb.users.get_table()"

# Inspect the combined grammar
uv run python scripts/dev/inspect_grammar.py

# Validate a module implementation
uv run python scripts/dev/validate_module.py standard.postgresql
```

---

## Contributing

`uqal-core` is maintained by the core team. See [CONTRIBUTING](https://uqal-lang.github.io/uqal-docs/contributing) for the development workflow.

To contribute a new database module, head to [uqal-lang/uqal-modules](https://github.com/uqal-lang/uqal-modules).

---

## License

[MIT](LICENSE)
