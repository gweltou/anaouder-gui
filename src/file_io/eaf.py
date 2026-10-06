import datetime
from pathlib import Path

# For eaf (Elan) file conversion
from xml.dom import minidom

import pytz

from src.version import __version__


def read_eaf_file(eaf_filename: Path) -> dict:
    """Write a split file and a text file from an eaf file"""
    abs_path = eaf_filename.absolute()
    rep = abs_path.parent
    # eaf_filename = abs_path.name

    doc = minidom.parse(str(abs_path))
    root = doc.firstChild

    def getText(nodelist):
        rc = []
        for node in nodelist:
            if node.nodeType == node.TEXT_NODE:
                rc.append(node.data)
        return "".join(rc)

    header = root.getElementsByTagName("HEADER")[0]
    md = header.getElementsByTagName("MEDIA_DESCRIPTOR")[0]
    wav_rel_path = md.getAttribute("RELATIVE_MEDIA_URL")

    time_resolution_str = header.getAttribute("TIME_UNITS")
    match time_resolution_str:
        case "milliseconds":
            time_resolution = 1 / 1000
        case _:
            time_resolution = 1

    wav_filename = (rep / wav_rel_path).resolve()

    time_order = root.getElementsByTagName("TIME_ORDER")[0]
    time_slots = time_order.getElementsByTagName("TIME_SLOT")
    time_slot_dict = {}
    for ts in time_slots:
        time_slot_dict[ts.getAttribute("TIME_SLOT_ID")] = int(
            ts.getAttribute("TIME_VALUE")
        ) * time_resolution

    tiers = root.getElementsByTagName("TIER")
    parsed_tiers = {}

    for tier in tiers:
        tier_id = tier.getAttribute("TIER_ID")
        tier_data = []

        annotations = tier.getElementsByTagName("ANNOTATION")
        for annotation in annotations:
            aa = annotation.getElementsByTagName("ALIGNABLE_ANNOTATION")[0]
            ts1 = aa.getAttribute("TIME_SLOT_REF1")
            ts2 = aa.getAttribute("TIME_SLOT_REF2")
            segment = [time_slot_dict[ts1], time_slot_dict[ts2]]
            text = getText(
                aa.getElementsByTagName("ANNOTATION_VALUE")[0].childNodes
            )
            tier_data.append((text, segment))

        parsed_tiers[tier_id] = tier_data

    return {
        "tiers": parsed_tiers,
        "media-path": wav_filename
    }




def format_eaf(utterances: list[tuple], media_path: Path, type="wav") -> str:
    """Export to eaf (Elan) file"""

    sentences = []
    segments = []
    for text, segment in utterances:
        if segment is None:
            continue
        sentences.append(text)
        segments.append(segment)

    if type == "mp3":
        mp3_file = media_path.with_suffix(".mp3")
        if not mp3_file.exists():
            # convert_to_mp3(audiofile, mp3_file)
            pass
        media_path = mp3_file

    doc = minidom.Document()

    root = doc.createElement("ANNOTATION_DOCUMENT")
    root.setAttribute("AUTHOR", f"Anaouder-gui {__version__}")
    root.setAttribute(
        "DATE",
        datetime.datetime.now(pytz.timezone("Europe/Paris")).isoformat(
            timespec="seconds"
        ),
    )
    root.setAttribute("FORMAT", "3.0")
    root.setAttribute("VERSION", "3.0")
    root.setAttribute("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.setAttribute(
        "xsi:noNamespaceSchemaLocation", "http://www.mpi.nl/tools/elan/EAFv3.0.xsd"
    )
    doc.appendChild(root)

    header = doc.createElement("HEADER")
    header.setAttribute("MEDIA_FILE", "")
    header.setAttribute("TIME_UNITS", "milliseconds")
    root.appendChild(header)

    media_descriptor = doc.createElement("MEDIA_DESCRIPTOR")
    media_descriptor.setAttribute("MEDIA_URL", "file://" + str(media_path.absolute()))
    if type == "mp3":
        media_descriptor.setAttribute("MIME_TYPE", "audio/mpeg")
    else:
        media_descriptor.setAttribute("MIME_TYPE", "audio/x-wav")
    media_descriptor.setAttribute(
        "RELATIVE_MEDIA_URL", "./" + media_path.name
    )
    header.appendChild(media_descriptor)

    time_order = doc.createElement("TIME_ORDER")
    last_t = 0
    for i, (s, e) in enumerate(segments):
        s, e = int(s * 1000), int(e * 1000)
        s = max(s, last_t)
        last_t = s
        time_slot = doc.createElement("TIME_SLOT")
        time_slot.setAttribute("TIME_SLOT_ID", f"ts{2 * i + 1}")
        time_slot.setAttribute("TIME_VALUE", str(s))
        time_order.appendChild(time_slot)
        time_slot = doc.createElement("TIME_SLOT")
        time_slot.setAttribute("TIME_SLOT_ID", f"ts{2 * i + 2}")
        time_slot.setAttribute("TIME_VALUE", str(e))
        time_order.appendChild(time_slot)
    root.appendChild(time_order)

    tier_trans = doc.createElement("TIER")
    tier_trans.setAttribute("LINGUISTIC_TYPE_REF", "transcript")
    tier_trans.setAttribute("TIER_ID", "Transcription")

    for i, sentence in enumerate(sentences):
        annotation = doc.createElement("ANNOTATION")
        alignable_annotation = doc.createElement("ALIGNABLE_ANNOTATION")
        alignable_annotation.setAttribute("ANNOTATION_ID", f"a{i + 1}")
        alignable_annotation.setAttribute("TIME_SLOT_REF1", f"ts{2 * i + 1}")
        alignable_annotation.setAttribute("TIME_SLOT_REF2", f"ts{2 * i + 2}")
        annotation_value = doc.createElement("ANNOTATION_VALUE")
        # text = doc.createTextNode(get_cleaned_sentence(sentence, rm_bl=True, keep_dash=True, keep_punct=True)[0])
        text = doc.createTextNode(sentence.replace("*", ""))
        annotation_value.appendChild(text)
        alignable_annotation.appendChild(annotation_value)
        annotation.appendChild(alignable_annotation)
        tier_trans.appendChild(annotation)
    root.appendChild(tier_trans)

    linguistic_type = doc.createElement("LINGUISTIC_TYPE")
    linguistic_type.setAttribute("GRAPHIC_REFERENCES", "false")
    linguistic_type.setAttribute("LINGUISTIC_TYPE_ID", "transcript")
    linguistic_type.setAttribute("TIME_ALIGNABLE", "true")
    root.appendChild(linguistic_type)

    language = doc.createElement("LANGUAGE")
    language.setAttribute("LANG_ID", "bre")
    language.setAttribute("LANG_LABEL", "Breton (bre)")
    root.appendChild(language)

    constraint_list = [
        (
            "Time_Subdivision",
            "Time subdivision of parent annotation's time interval, no time gaps allowed within this interval",
        ),
        (
            "Symbolic_Subdivision",
            "Symbolic subdivision of a parent annotation. Annotations refering to the same parent are ordered",
        ),
        ("Symbolic_Association", "1-1 association with a parent annotation"),
        (
            "Included_In",
            "Time alignable annotations within the parent annotation's time interval, gaps are allowed",
        ),
    ]
    for stereotype, description in constraint_list:
        constraint = doc.createElement("CONSTRAINT")
        constraint.setAttribute("DESCRIPTION", description)
        constraint.setAttribute("STEREOTYPE", stereotype)
        root.appendChild(constraint)

    xml_str = doc.toprettyxml(indent="\t", encoding="UTF-8")

    return xml_str.decode("utf-8")
