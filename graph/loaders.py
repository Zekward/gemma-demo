"""
Thin per-DB loaders over the ONE canonical store (nodes.jsonl + edges.jsonl).

Principle (verified 2026-06): keep the graph DB-neutral. Every engine gets a ~20-line
adapter; swapping "try Kuzu vs Neo4j vs Memgraph" is a loader change, never a re-model.

Cypher family — LadybugDB (the maintained Kuzu fork; kuzudb/kuzu was archived after
Apple's Oct-2025 acquisition), Neo4j, Memgraph, FalkorDB — all speak (Open)Cypher, so
they SHARE one loader. ArangoDB (AQL) and DuckDB (SQL/PGQ) diverge and get their own.
"""
from __future__ import annotations
import json, pathlib

HERE = pathlib.Path(__file__).parent
def _read(name): return [json.loads(l) for l in (HERE / name).read_text().splitlines() if l.strip()]
def nodes(): return _read("nodes.jsonl")
def edges(): return _read("edges.jsonl")


# --- Cypher family: Neo4j / Memgraph / FalkorDB / LadybugDB --------------------
# Pass any OpenCypher session with a .run(query, **params) method (neo4j driver works
# for Neo4j + Memgraph over Bolt; falkordb/ladybug have near-identical clients).
def load_cypher(run):
    for n in nodes():
        run("MERGE (x {id:$id}) SET x += $props, x.label=$label",
            id=n["id"], props=n["props"], label=n["label"])
    for e in edges():
        run("MATCH (a {id:$s}),(b {id:$d}) "
            "MERGE (a)-[r:REL {type:$t}]->(b) SET r += $props",
            s=e["src"], d=e["dst"], t=e["type"],
            props={"relationship": e["props"]["relationship"],
                   "summary": e["props"]["summary"],
                   "materiality": e["props"]["materiality"],
                   "differences": json.dumps(e["props"]["differences"])})  # props must be primitive


# --- Neo4j bulk path: emit :ID/:LABEL/:START_ID/:END_ID CSVs for neo4j-admin import
def to_neo4j_csv(outdir="neo4j_import"):
    import csv
    d = HERE / outdir; d.mkdir(exist_ok=True)
    with open(d / "nodes.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow([":ID", ":LABEL", "props"])
        for n in nodes(): w.writerow([n["id"], n["label"], json.dumps(n["props"])])
    with open(d / "edges.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow([":START_ID", ":END_ID", ":TYPE", "props"])
        for e in edges(): w.writerow([e["src"], e["dst"], e["type"], json.dumps(e["props"])])
    return str(d)


# --- DuckDB + DuckPGQ (analytics companion; eats the parquet mirror) -----------
def load_duckdb(db=":memory:"):
    import duckdb
    con = duckdb.connect(db)
    con.execute("CREATE TABLE n(id VARCHAR, label VARCHAR, props JSON)")
    con.execute("CREATE TABLE e(src VARCHAR, dst VARCHAR, type VARCHAR, props JSON)")
    for n in nodes():
        con.execute("INSERT INTO n VALUES (?,?,?)", [n["id"], n["label"], json.dumps(n["props"])])
    for e in edges():
        con.execute("INSERT INTO e VALUES (?,?,?,?)", [e["src"], e["dst"], e["type"], json.dumps(e["props"])])
    # then optionally: INSTALL duckpgq; CREATE PROPERTY GRAPH g VERTEX TABLES (n) EDGE TABLES (e ...);
    return con


# --- NetworkX (in-memory scratch / algorithms / reference) --------------------
def load_networkx():
    import networkx as nx
    g = nx.MultiDiGraph()
    for n in nodes(): g.add_node(n["id"], label=n["label"], **n["props"])
    for e in edges(): g.add_edge(e["src"], e["dst"], key=e["type"], **e["props"])
    return g


if __name__ == "__main__":
    print(f"canonical store: {len(nodes())} nodes, {len(edges())} edges")
    try:
        g = load_networkx()
        print(f"networkx     : {g.number_of_nodes()} nodes / {g.number_of_edges()} edges OK")
    except ImportError:
        print("networkx     : (pip install networkx to test)")
    try:
        con = load_duckdb()
        r = con.execute("SELECT type, count(*) FROM e GROUP BY type ORDER BY 2 DESC").fetchall()
        print(f"duckdb       : loaded OK; edge types {dict(r)}")
    except ImportError:
        print("duckdb       : (pip install duckdb to test)")
    print(f"neo4j csv    : {to_neo4j_csv()}")
