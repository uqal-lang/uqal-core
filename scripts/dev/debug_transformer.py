# tests/debug_transformer.py
from lark import Lark
from pathlib import Path
from uqal_core.ast.transformer import UQALTransformer

grammar = Path("src/uqal_core/parser/base_grammar.lark").read_text()
parser = Lark(grammar, parser="earley", import_paths=["src/uqal_core/parser"])
transformer = UQALTransformer()

script = "db1.orders.get_value(where id = 5, field amount)"

try:
    tree = parser.parse(script)
    print("Tree:")
    print(tree.pretty())
    result = transformer.transform(tree)
    print("Result:", result)
except Exception as e:
    import traceback
    traceback.print_exc()