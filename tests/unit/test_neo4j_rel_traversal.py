"""Tests for Neo4j Relationship Traversal: grammar, handler, AST, and translator."""
import pytest
from lark import Token
from uqal_core.ast.nodes import (
    DbQueryBlock,
    PlainField,
    PrefixedField,
    QueryAlias,
    QueryReturn,
    RelationshipTraversal,
)
from uqal_core.ast.transformer import UQALTransformer
from uqal_core.modules.standard.neo4j.module import Neo4jModule
from uqal_core.modules.standard.neo4j.translator import Neo4jTranslator
from uqal_core.parser.grammar_builder import GrammarBuilder

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def parse_neo4j():
    neo4j_module = Neo4jModule()
    parser = GrammarBuilder().build([neo4j_module])
    transformer = UQALTransformer()

    def _parse(script: str):
        return transformer.transform(parser.parse(script))

    return _parse


# ---- Grammar: simple relationship traversal ----

def test_grammar_simple_rel_traversal_returns_program(parse_neo4j):
    p = parse_neo4j(
        "let result = graphdb.query: "
        "let u = table User "
        "let o = table Order where u PLACED o "
        "return u.name, o.id"
    )
    assert p is not None
    assert len(p.statements) == 1


def test_grammar_simple_rel_traversal_is_query_block(parse_neo4j):
    p = parse_neo4j(
        "let result = graphdb.query: "
        "let u = table User "
        "let o = table Order where u PLACED o "
        "return u.name, o.id"
    )
    query_block = p.statements[0].value
    assert isinstance(query_block, DbQueryBlock)


def test_grammar_simple_rel_traversal_creates_relationship_node(parse_neo4j):
    p = parse_neo4j(
        "let result = graphdb.query: "
        "let u = table User "
        "let o = table Order where u PLACED o "
        "return u.name, o.id"
    )
    order_alias = p.statements[0].value.aliases[1]
    assert isinstance(order_alias.condition, RelationshipTraversal)


def test_grammar_simple_rel_traversal_source(parse_neo4j):
    p = parse_neo4j(
        "let result = graphdb.query: "
        "let u = table User "
        "let o = table Order where u PLACED o "
        "return u.name, o.id"
    )
    rt = p.statements[0].value.aliases[1].condition
    assert rt.source_alias == "u"


def test_grammar_simple_rel_traversal_type(parse_neo4j):
    p = parse_neo4j(
        "let result = graphdb.query: "
        "let u = table User "
        "let o = table Order where u PLACED o "
        "return u.name, o.id"
    )
    rt = p.statements[0].value.aliases[1].condition
    assert rt.relationship_type == "PLACED"


def test_grammar_simple_rel_traversal_target(parse_neo4j):
    p = parse_neo4j(
        "let result = graphdb.query: "
        "let u = table User "
        "let o = table Order where u PLACED o "
        "return u.name, o.id"
    )
    rt = p.statements[0].value.aliases[1].condition
    assert rt.target_alias == "o"


def test_grammar_simple_rel_traversal_no_properties(parse_neo4j):
    p = parse_neo4j(
        "let result = graphdb.query: "
        "let u = table User "
        "let o = table Order where u PLACED o "
        "return u.name, o.id"
    )
    rt = p.statements[0].value.aliases[1].condition
    assert rt.properties == []


# ---- Grammar: relationship traversal with properties ----

def test_grammar_rel_traversal_with_props_creates_relationship(parse_neo4j):
    p = parse_neo4j(
        "let result = graphdb.query: "
        "let o = table Order "
        "let p = table Product where o CONTAINS[qty, price] p "
        "return o.id, p.name"
    )
    product_alias = p.statements[0].value.aliases[1]
    assert isinstance(product_alias.condition, RelationshipTraversal)


def test_grammar_rel_traversal_two_props_count(parse_neo4j):
    p = parse_neo4j(
        "let result = graphdb.query: "
        "let o = table Order "
        "let p = table Product where o CONTAINS[qty, price] p "
        "return o.id, p.name"
    )
    rt = p.statements[0].value.aliases[1].condition
    assert len(rt.properties) == 2


def test_grammar_rel_traversal_two_props_names(parse_neo4j):
    p = parse_neo4j(
        "let result = graphdb.query: "
        "let o = table Order "
        "let p = table Product where o CONTAINS[qty, price] p "
        "return o.id, p.name"
    )
    rt = p.statements[0].value.aliases[1].condition
    assert "qty" in rt.properties
    assert "price" in rt.properties


def test_grammar_rel_traversal_three_properties(parse_neo4j):
    p = parse_neo4j(
        "let result = graphdb.query: "
        "let o = table Order "
        "let p = table Product where o CONTAINS[qty, price, discount] p "
        "return o.id, p.name"
    )
    rt = p.statements[0].value.aliases[1].condition
    assert len(rt.properties) == 3
    assert "discount" in rt.properties


# ---- _handle_neo4j_rel_traversal: direct call ----

def test_handler_returns_relationship_traversal():
    handler = Neo4jModule._handle_neo4j_rel_traversal
    children = [Token("NAME", "u"), Token("NAME", "PLACED"), Token("NAME", "o")]
    result = handler(children)
    assert isinstance(result, RelationshipTraversal)


def test_handler_extracts_source_alias():
    handler = Neo4jModule._handle_neo4j_rel_traversal
    children = [Token("NAME", "u"), Token("NAME", "PLACED"), Token("NAME", "o")]
    result = handler(children)
    assert result.source_alias == "u"


def test_handler_extracts_relationship_type():
    handler = Neo4jModule._handle_neo4j_rel_traversal
    children = [Token("NAME", "u"), Token("NAME", "PLACED"), Token("NAME", "o")]
    result = handler(children)
    assert result.relationship_type == "PLACED"


def test_handler_extracts_target_alias():
    handler = Neo4jModule._handle_neo4j_rel_traversal
    children = [Token("NAME", "u"), Token("NAME", "PLACED"), Token("NAME", "o")]
    result = handler(children)
    assert result.target_alias == "o"


def test_handler_no_properties_for_simple_form():
    handler = Neo4jModule._handle_neo4j_rel_traversal
    children = [Token("NAME", "u"), Token("NAME", "PLACED"), Token("NAME", "o")]
    result = handler(children)
    assert result.properties == []


def test_handler_extracts_two_properties():
    handler = Neo4jModule._handle_neo4j_rel_traversal
    children = [
        Token("NAME", "o"),
        Token("NAME", "CONTAINS"),
        Token("NAME", "qty"),
        Token("NAME", "price"),
        Token("NAME", "p"),
    ]
    result = handler(children)
    assert result.properties == ["qty", "price"]


def test_handler_extracts_three_properties():
    handler = Neo4jModule._handle_neo4j_rel_traversal
    children = [
        Token("NAME", "o"),
        Token("NAME", "CONTAINS"),
        Token("NAME", "qty"),
        Token("NAME", "price"),
        Token("NAME", "discount"),
        Token("NAME", "p"),
    ]
    result = handler(children)
    assert result.properties == ["qty", "price", "discount"]


def test_handler_source_target_with_properties():
    handler = Neo4jModule._handle_neo4j_rel_traversal
    children = [
        Token("NAME", "a"),
        Token("NAME", "KNOWS"),
        Token("NAME", "since"),
        Token("NAME", "b"),
    ]
    result = handler(children)
    assert result.source_alias == "a"
    assert result.target_alias == "b"
    assert result.properties == ["since"]


# ---- RelationshipTraversal AST node ----

def test_relationship_traversal_all_fields():
    rt = RelationshipTraversal(
        source_alias="a",
        relationship_type="KNOWS",
        target_alias="b",
        properties=["since", "weight"],
    )
    assert rt.source_alias == "a"
    assert rt.relationship_type == "KNOWS"
    assert rt.target_alias == "b"
    assert rt.properties == ["since", "weight"]


def test_relationship_traversal_default_properties():
    rt = RelationshipTraversal(
        source_alias="x",
        relationship_type="FOLLOWS",
        target_alias="y",
    )
    assert rt.properties == []


def test_relationship_traversal_is_node():
    from uqal_core.ast.nodes import Node
    rt = RelationshipTraversal(
        source_alias="a", relationship_type="R", target_alias="b"
    )
    assert isinstance(rt, Node)


# ---- _detect_relationship ----

def test_detect_relationship_with_simple_traversal():
    translator = Neo4jTranslator()
    rt = RelationshipTraversal(
        source_alias="u", relationship_type="PLACED", target_alias="o"
    )
    alias = QueryAlias(alias="o", table="Order", condition=rt)
    rel_type, props = translator._detect_relationship(alias, ["u", "o"])
    assert rel_type == "PLACED"
    assert props == []


def test_detect_relationship_with_properties():
    translator = Neo4jTranslator()
    rt = RelationshipTraversal(
        source_alias="o",
        relationship_type="CONTAINS",
        target_alias="p",
        properties=["qty", "price"],
    )
    alias = QueryAlias(alias="p", table="Product", condition=rt)
    rel_type, props = translator._detect_relationship(alias, ["o", "p"])
    assert rel_type == "CONTAINS"
    assert props == ["qty", "price"]


def test_detect_relationship_none_when_no_condition():
    translator = Neo4jTranslator()
    alias = QueryAlias(alias="u", table="User", condition=None)
    rel_type, props = translator._detect_relationship(alias, ["u"])
    assert rel_type is None
    assert props == []


def test_detect_relationship_returns_type_string():
    translator = Neo4jTranslator()
    rt = RelationshipTraversal(source_alias="a", relationship_type="KNOWS", target_alias="b")
    alias = QueryAlias(alias="b", table="Person", condition=rt)
    rel_type, _ = translator._detect_relationship(alias, ["a", "b"])
    assert isinstance(rel_type, str)


# ---- _translate_query_block ----

def test_translate_query_block_simple_traversal_has_match():
    translator = Neo4jTranslator()
    rt = RelationshipTraversal(
        source_alias="u", relationship_type="PLACED", target_alias="o"
    )
    block = DbQueryBlock(
        connection="graphdb",
        aliases=[
            QueryAlias(alias="u", table="User", condition=None),
            QueryAlias(alias="o", table="Order", condition=rt),
        ],
        returns=QueryReturn(fields=[
            PrefixedField(prefix="u", name="name"),
            PrefixedField(prefix="o", name="id"),
        ]),
    )
    cypher, _ = translator.translate(block)
    assert "MATCH" in cypher


def test_translate_query_block_simple_traversal_includes_rel_type():
    translator = Neo4jTranslator()
    rt = RelationshipTraversal(
        source_alias="u", relationship_type="PLACED", target_alias="o"
    )
    block = DbQueryBlock(
        connection="graphdb",
        aliases=[
            QueryAlias(alias="u", table="User", condition=None),
            QueryAlias(alias="o", table="Order", condition=rt),
        ],
        returns=QueryReturn(fields=[PrefixedField(prefix="u", name="name")]),
    )
    cypher, _ = translator.translate(block)
    assert "PLACED" in cypher


def test_translate_query_block_simple_traversal_return_clause():
    translator = Neo4jTranslator()
    rt = RelationshipTraversal(
        source_alias="u", relationship_type="PLACED", target_alias="o"
    )
    block = DbQueryBlock(
        connection="graphdb",
        aliases=[
            QueryAlias(alias="u", table="User", condition=None),
            QueryAlias(alias="o", table="Order", condition=rt),
        ],
        returns=QueryReturn(fields=[
            PrefixedField(prefix="u", name="name"),
            PrefixedField(prefix="o", name="id"),
        ]),
    )
    cypher, _ = translator.translate(block)
    assert "u.name AS name" in cypher
    assert "o.id AS id" in cypher


def test_translate_query_block_simple_traversal_returns_tuple():
    translator = Neo4jTranslator()
    rt = RelationshipTraversal(
        source_alias="u", relationship_type="PLACED", target_alias="o"
    )
    block = DbQueryBlock(
        connection="graphdb",
        aliases=[
            QueryAlias(alias="u", table="User", condition=None),
            QueryAlias(alias="o", table="Order", condition=rt),
        ],
        returns=QueryReturn(fields=[PrefixedField(prefix="u", name="name")]),
    )
    result = translator.translate(block)
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_translate_query_block_with_property_mapping_qty():
    translator = Neo4jTranslator()
    rt = RelationshipTraversal(
        source_alias="o",
        relationship_type="CONTAINS",
        target_alias="p",
        properties=["quantity", "price"],
    )
    block = DbQueryBlock(
        connection="graphdb",
        aliases=[
            QueryAlias(alias="o", table="Order", condition=None),
            QueryAlias(alias="p", table="Product", condition=rt),
        ],
        returns=QueryReturn(fields=[
            PrefixedField(prefix="o", name="id"),
            PrefixedField(prefix="p", name="name"),
            PlainField(name="quantity"),
            PlainField(name="price"),
        ]),
    )
    cypher, _ = translator.translate(block)
    assert "r_p.quantity AS quantity" in cypher


def test_translate_query_block_with_property_mapping_price():
    translator = Neo4jTranslator()
    rt = RelationshipTraversal(
        source_alias="o",
        relationship_type="CONTAINS",
        target_alias="p",
        properties=["quantity", "price"],
    )
    block = DbQueryBlock(
        connection="graphdb",
        aliases=[
            QueryAlias(alias="o", table="Order", condition=None),
            QueryAlias(alias="p", table="Product", condition=rt),
        ],
        returns=QueryReturn(fields=[
            PrefixedField(prefix="o", name="id"),
            PlainField(name="quantity"),
            PlainField(name="price"),
        ]),
    )
    cypher, _ = translator.translate(block)
    assert "r_p.price AS price" in cypher


def test_translate_query_block_rel_var_in_path_segment():
    translator = Neo4jTranslator()
    rt = RelationshipTraversal(
        source_alias="o",
        relationship_type="CONTAINS",
        target_alias="p",
        properties=["qty"],
    )
    block = DbQueryBlock(
        connection="graphdb",
        aliases=[
            QueryAlias(alias="o", table="Order", condition=None),
            QueryAlias(alias="p", table="Product", condition=rt),
        ],
        returns=QueryReturn(fields=[PlainField(name="qty")]),
    )
    cypher, _ = translator.translate(block)
    assert "r_p" in cypher
    assert "CONTAINS" in cypher
