from __future__ import annotations


def main() -> None:
    from .server import build_server
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
