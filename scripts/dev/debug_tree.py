# tests/debug_tree.py
from lark import Lark
from pathlib import Path
from uqal_core.ast.transformer import UQALTransformer

grammar = Path("src/uqal_core/parser/base_grammar.lark").read_text()
parser = Lark(grammar, parser="earley", import_paths=["src/uqal_core/parser"])

cases = [
    "db1.orders.get_value(where id = 5, field amount)",
    'db1.users.insert_table({"id": integer(primary_key: true), "name": string})',
    "if age > 18 : let a = 5",
]

for script in cases:
    print(f"\n{'='*60}")
    print(f"Script: {script}")
    print(f"{'='*60}")
    tree = parser.parse(script)
    print(tree.pretty())