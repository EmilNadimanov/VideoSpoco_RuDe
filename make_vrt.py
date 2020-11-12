import os
import re
from nltk import word_tokenize
from xml.etree import ElementTree as et
import sys

# Any questions about this code can be sent to nadimaemi@gmail.com
# I may answer them. I may not.

ANNOT_REGEX = r"[ -]NVK|[ -]AA$"
LINGUISTIC_TYPE_REF = {"utterance"}
OUT_PATH = "./VRT"


class ParseError(Exception):
    """    The Exception class to use in case something is incorrect  """

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


def extract_annotations(root):
    result = dict()  # annotations
    for tier in [t for t in root.findall('TIER') if re.search(ANNOT_REGEX, t.get("TIER_ID")) is not None]:
        speaker = re.sub(ANNOT_REGEX, "", tier.get("TIER_ID"))
        result[speaker] = result.get(speaker, list())
        result[speaker].append(tier)
    return result


def extract_data(efile):
    """

    """
    time_slots = dict()  # key and value are {time_slot_id: time_value}
    speech_slices = list()

    # ELAN files are represented as XML files and are parsed as such
    root = et.parse(efile).getroot()
    for ts in root.findall('.//TIME_ORDER/TIME_SLOT'):
        if ts.get('TIME_VALUE') is not None:
            time_slots[ts.get('TIME_SLOT_ID')] = int(ts.get('TIME_VALUE'))

    tiers = [t for t in root.findall('TIER') if t.get("LINGUISTIC_TYPE_REF") in LINGUISTIC_TYPE_REF]
    ling_annotations = extract_annotations(root)
    tier_number = 0  # each (2n)th tier is the translation of (2n-1)th tier (note that index [1] points to tier 2)
    while tier_number < len(tiers):  # a while-loop because we need to parse tiers in pairs
        tier1, tier2 = tiers[tier_number], tiers[tier_number + 1]
        speaker = re.sub("-Spch", '', tier2.get("TIER_ID"))
        try:
            annot_tiers = ling_annotations[speaker]
        except KeyError:
            annot_tiers = None

        aa1, aa2 = tier1.findall('.//ALIGNABLE_ANNOTATION'), tier2.findall('.//ALIGNABLE_ANNOTATION')
        if len(aa1) != len(aa2):
            msg = ' '.join(["\nWarning! Tiers", tier1.get("TIER_ID"), "and", tier2.get("TIER_ID"),
                            "have unequal lengths. Correct data before processing. "
                            "Check ELAN file for blank annotations or other errors."])
            raise ParseError(msg)

        for aa1, aa2 in zip(aa1, aa2):
            start = time_slots[aa1.get('TIME_SLOT_REF1')]
            text_ru = aa1.find("ANNOTATION_VALUE").text
            text_de = aa2.find("ANNOTATION_VALUE").text
            annot = ''
            if annot_tiers is not None:  # only few tiers have annotations
                annot = []
                for annot_tier in annot_tiers:  # non-empty annotation fields that start ≈ when the speech interval does
                    annot.extend([an.find("ANNOTATION_VALUE").text for an in annot_tier.findall('.//ALIGNABLE_ANNOTATION') if
                             abs(int(time_slots[an.get('TIME_SLOT_REF1')]) - int(start)) < 100 and
                             an.find("ANNOTATION_VALUE").text is not None])
            speech_slices.append([start, str(text_ru), str(text_de), 'own    '.join(annot)])
        tier_number += 2

    speech_slices.sort(key=(lambda x: x[0]))  # orders speech in the whole efile chronologically;
    utterRu, utterDe, ling_annot = list(), list(), list()
    for id_, list_ in enumerate(speech_slices, start=1):
        utterRu.append([id_, list_[1]])
        utterDe.append([id_, list_[2]])
        ling_annot.append([id_, list_[3]])
    return utterRu, utterDe, ling_annot


def make_vrt(utterances, filename, language):
    vrt = ["<meta filename={}, language={}>".format(filename, language)]
    for id_, utterance in utterances:
        vrt.append('<Align_RU_DE id={}>'.format(id_))
        for word in word_tokenize(utterance):
            vrt.append(word)
        vrt.append('</Align_RU_DE>'.format(id_))
    vrt.append('</meta>')
    return '\n'.join(vrt)


def make_vrt_files(efile):
    utterRU, utterDE, linguistic_annotation = extract_data(efile)
    filename = os.path.splitext(os.path.split(efile)[1])[0]
    print("\t", filename)
    vrtRU = make_vrt(utterRU, filename, "RU")
    vrtDE = make_vrt(utterDE, filename, "DE")
    vrtLA = make_vrt(linguistic_annotation, filename, "annotation")
    if not os.path.exists(OUT_PATH):
        os.makedirs(OUT_PATH)
    with open(os.path.join(OUT_PATH, "{}-RU.vrt".format(filename)), 'w') as output:
        output.write(vrtRU)
    with open(os.path.join(OUT_PATH, "{}-DE.vrt".format(filename)), 'w') as output:
        output.write(vrtDE)
    with open(os.path.join(OUT_PATH, "{}-annot.vrt".format(filename)), 'w') as output:
        output.write(vrtLA)


def main():
    efiles = list()
    for arg in sys.argv[1:]:
        if os.path.exists(arg) is False:
            print("Location does not exist:", arg)
            continue
        elif os.path.isdir(arg):
            efiles += [file.path for file in os.scandir(arg) if os.path.splitext(file.path)[1] == ".eaf"]
        elif os.path.splitext(arg)[1] == ".eaf":
            efiles.append(arg)
    if not efiles:
        raise ParseError("No .eaf files found")
    for efile in efiles:
        make_vrt_files(efile)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise ParseError("Provide the path to separate ELAN files or a directory as command line arguments")
    print("Making .vrt for:")
    main()

