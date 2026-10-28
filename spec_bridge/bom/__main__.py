"""Link a BOM table to the registry (D-101). A preview unless --apply is given.

    uv run python -m spec_bridge.bom data/synth/boms/BOM-001.md
    uv run python -m spec_bridge.bom BOM-001.xlsx --registry var/registry/dev.sqlite --apply

Prints the plan as JSON: each row's status (new, existing, pending and why), the root's
relations the BOM does not list, and whether anything was written.
"""

import argparse
import json
import sys
from pathlib import Path

from spec_bridge.bom.linker import apply, plan, summary
from spec_bridge.bom.reader import BomError, read_bom
from spec_bridge.ontology.loader import load_ontology
from spec_bridge.registry.store import (
    ROOT,
    SCHEMA_VERSION,
    RegistryError,
    RegistryStore,
    stored_schema,
)

ONTOLOGY = ROOT / "ontology/ontology.yaml"
REGISTRY = ROOT / "var/registry/dev.sqlite"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m spec_bridge.bom")
    parser.add_argument("bom", type=Path)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--apply", action="store_true", help="write the new relations")
    args = parser.parse_args(argv)
    if not args.registry.is_file():
        sys.exit(f"{args.registry}: no registry (uv run python -m spec_bridge.registry.store dev)")
    version = stored_schema(args.registry)
    if not args.apply and version != SCHEMA_VERSION:  # opening it would migrate the file
        sys.exit(
            f"refused: {args.registry} has schema {version}, not {SCHEMA_VERSION}; a preview "
            "writes nothing, so it does not migrate the file (--apply or the app migrates it)"
        )
    onto = load_ontology(ONTOLOGY)
    try:
        store = RegistryStore(args.registry, onto)
    except RegistryError as error:
        sys.exit(f"refused: {error}")
    try:
        result = plan(store, onto, read_bom(args.bom))
        added = apply(store, result, "reviewer") if args.apply else 0
    except (BomError, RegistryError) as error:
        sys.exit(f"refused: {error}")
    finally:
        store.close()
    report = summary(result) | {"applied": args.apply, "added": added}
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
