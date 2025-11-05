import time

from amongus_reader.service import AmongUsReader


def main() -> None:
    reader = AmongUsReader(process_name="Among Us.exe", debug=True)
    reader.attach()
    try:
        for _ in range(8):
            try:
                state, snapshot = reader.get_session_snapshot()
                print({
                    "state": state,
                    "signals": snapshot,
                })
            except Exception as exc:
                print({"error": str(exc)})
            time.sleep(1.0)
    finally:
        reader.detach()


if __name__ == "__main__":
    main()
