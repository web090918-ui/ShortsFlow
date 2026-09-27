from pathlib import Path
import shutil

import deno


def main() -> None:
    destination = Path(__file__).parents[1] / "app" / ".runtime" / "deno"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(deno.find_deno_bin(), destination)
    destination.chmod(0o755)
    print(f"Bundled Deno runtime at {destination}")


if __name__ == "__main__":
    main()
