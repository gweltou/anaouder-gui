
import re

from ostilhou.asr.dataset import MetadataParser


def format_txt(utterances: list[tuple]) -> str:
    # Remove metadata
    rm_special_tokens = True

    metadata_parser = MetadataParser()

    lines = []
    for i, (text, _) in enumerate(utterances):
        data = metadata_parser.parse_sentence(text)
        if data is None:
            continue
        regions, _ = data
        text = "".join([region["text"] for region in regions if "text" in region])

        text = re.sub(r"\*", "", text)
        text = re.sub(r"<br>", "\n", text, count=0, flags=re.IGNORECASE)
        text = text.replace("\u2028", "\n")

        if rm_special_tokens:
            text = re.sub(r"<(/?)(\w+)[^>]*>", "", text)

        lines.append(text.strip())

    return "\n".join(lines)
