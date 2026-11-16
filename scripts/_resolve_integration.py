"""Union-resolve additive merge conflicts (keep both sides).

Each V7 phase adds new route functions to web/app.py and new sections to
AGENTS.md at the same anchor, so the correct resolution keeps BOTH sides.
Git may split one such region into several hunks separated by shared lines;
those shared lines belong to both sides' new blocks, so the union is
``ours_full + theirs_full``, where each side's view keeps the shared lines.

Usage: python3 scripts/_resolve_integration.py <file> [<file> ...]
"""
import sys


def union_resolve(text: str) -> str:
    lines = text.split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        if not lines[i].startswith("<<<<<<< "):
            out.append(lines[i])
            i += 1
            continue
        ours_all, theirs_all = [], []
        while True:
            assert lines[i].startswith("<<<<<<< ")
            i += 1
            ours = []
            while not lines[i].startswith("======="):
                ours.append(lines[i])
                i += 1
            i += 1
            theirs = []
            while not lines[i].startswith(">>>>>>> "):
                theirs.append(lines[i])
                i += 1
            i += 1
            ours_all.extend(ours)
            theirs_all.extend(theirs)
            # Another hunk of the same region follows a run of shared lines
            # (no intervening blank line); merge those shared lines into both.
            if i < n and lines[i].strip() != "" and any(
                lines[k].startswith("<<<<<<< ") for k in range(i, min(i + 80, n))
            ):
                while i < n and not lines[i].startswith("<<<<<<< "):
                    ours_all.append(lines[i])
                    theirs_all.append(lines[i])
                    i += 1
                continue
            break
        out.extend(ours_all)
        out.extend(theirs_all)
    return "\n".join(out)


def main(paths):
    for path in paths:
        text = open(path).read()
        if "<<<<<<< " not in text:
            print(f"{path}: no conflicts")
            continue
        resolved = union_resolve(text)
        assert "<<<<<<< " not in resolved and ">>>>>>> " not in resolved, path
        open(path, "w").write(resolved)
        print(f"{path}: resolved -> {len(resolved.splitlines())} lines")


if __name__ == "__main__":
    main(sys.argv[1:])
