from __future__ import annotations

import argparse

from .upstream import InMemoryUpstreamStore, create_upstream_http_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Pilot Agent upstream HTTP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    store = InMemoryUpstreamStore()
    server = create_upstream_http_server(args.host, args.port, store)
    server.serve_forever()


if __name__ == "__main__":
    main()

