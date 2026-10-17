"""Entry point: ``python3 -m rp_wolfboot`` serves the wolfBoot runner on $RUNNER_PORT (8080)."""

from rp_runner.server import serve

from rp_wolfboot.family import WolfbootFamily


def main() -> None:
    serve(WolfbootFamily())


if __name__ == "__main__":
    main()
