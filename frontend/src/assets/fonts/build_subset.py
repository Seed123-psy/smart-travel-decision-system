"""Build the locally served Chinese UI font without network access."""

import argparse
from pathlib import Path
from shutil import copyfile

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont


def characters(repository: Path) -> set[int]:
    codepoints = set(range(0x20, 0x7F))
    for lead in range(0xA1, 0xF8):
        for trail in range(0xA1, 0xFF):
            try:
                codepoints.update(map(ord, bytes((lead, trail)).decode("gb2312")))
            except UnicodeDecodeError:
                pass
    for start, end in ((0x2000, 0x2070), (0x20A0, 0x20D0), (0x3000, 0x3040), (0xFF00, 0xFFF0)):
        codepoints.update(range(start, end))
    for directory in (repository / "frontend/src", repository / "backend/app"):
        for source in directory.rglob("*"):
            if source.suffix in {".vue", ".ts", ".css", ".py"} and "fonts" not in source.parts:
                codepoints.update(map(ord, source.read_text(encoding="utf-8")))
    return codepoints


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Original NotoSansSC-VF.ttf")
    args = parser.parse_args()
    output = Path(__file__).resolve().parent / "noto-sans-sc-ui.woff2"
    repository = output.parents[4]
    font = TTFont(args.source)
    available = set(font.getBestCmap())
    requested = characters(repository)
    options = subset.Options()
    options.hinting = False
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 8, 9, 11, 13, 14, 16, 17, 25]
    options.name_languages = ["*"]
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=requested & available)
    subsetter.subset(font)
    instantiateVariableFont(font, {"wght": (400, 400, 700)}, inplace=True)
    font.flavor = "woff2"
    font.save(output)
    public_license = repository / "frontend/public/fonts/OFL.txt"
    public_license.parent.mkdir(parents=True, exist_ok=True)
    copyfile(output.with_name("OFL.txt"), public_license)
    print(f"Saved {output.name}: {output.stat().st_size:,} bytes")
    print(f"Unicode characters: {len(font.getBestCmap()):,}; wght: 400-700; hints removed")


if __name__ == "__main__":
    main()
