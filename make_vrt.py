import os
import re
from nltk import word_tokenize
from xml.etree import ElementTree as et
import sys

# Any questions about this code can be sent to nadimaemi@gmail.com
# I may answer them. I may not.

ANNOT_REGEX = r"([ -]NVK|[ -]AA|[ -]Illok\.)$"
LINGUISTIC_TYPE_REF = {"utterance"}
OUT_PATH = "./VRT"


class ParseError(Exception):
    """    The Exception class to use in case something is incorrect  """

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


def extract_annotations(root):
    """
    Linguistic annotations are extracted based on the assumption that their names end with special symbolic sequences.
      For the files I initially have, those are "AA", "NVK", "Illok.". To add new ones alter the regular expression in
      the ANNOT_REGEX global variable.
    Linguistic annotations are have type 'list'. They are the  values in a dictionary and are accessed by the name of a
    tier without the '-AA'/' AA' or '-NVK'/' NVK' part. That means "Junge-NVK' is accessed by 'Junge'.
    """
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
    tier_number = 0

    while tier_number < len(tiers):  # a while-loop because we need to parse tiers in pairs
        tier1, tier2 = tiers[tier_number], tiers[tier_number + 1]

        # An attempt to find a tier in German based on its name; Tiers are supposed to be ordered Russian first,
        # German second. However, this variable assignment helps avoid mistakes
        ru_tier, de_tier = (tier1, tier2) if re.search(r'[a-zA-Z]', tier2.get("TIER_ID")) is not None else (tier2, tier1)
        speaker = re.sub("-Spch", '', de_tier.get("TIER_ID"))
        try:  # only few tiers have annotations
            annot_tiers = ling_annotations[speaker]
        except KeyError:
            annot_tiers = None

        aa_ru_all = ru_tier.findall('.//ALIGNABLE_ANNOTATION')
        aa_de_all = de_tier.findall('.//ALIGNABLE_ANNOTATION')
        idx = 0  # using index because we need to occasionally pop empty intervals from alignable annotations

        while idx < min(len(aa_ru_all), len(aa_de_all)):
            aa_ru, aa_de = aa_ru_all[idx], aa_de_all[idx]
            start_ru = time_slots[aa_ru.get('TIME_SLOT_REF1')]
            start_de = time_slots[aa_de.get('TIME_SLOT_REF1')]

            # we pop empty intervals that have no pairs because they were added by mistake
            if abs(int(start_ru) - int(start_de)) > 100:  # triggers if annotations are more than 100ms apart
                if start_de < start_ru:  # lonely empty intervals appear earlier than valid ones
                    aa_de_all.pop(idx)
                else:
                    aa_ru_all.pop(idx)
            else:
                text_ru = aa_ru.find("ANNOTATION_VALUE").text
                text_de = aa_de.find("ANNOTATION_VALUE").text
                annot = ''
                if annot_tiers is not None:
                    annot = []
                    for annot_tier in annot_tiers:  # Annotations start ≈ when the speech does
                        annot.extend(
                            [an.find("ANNOTATION_VALUE").text for an in annot_tier.findall('.//ALIGNABLE_ANNOTATION') if
                             abs(int(time_slots[an.get('TIME_SLOT_REF1')]) - int(start_de)) < 100 and
                             an.find("ANNOTATION_VALUE").text is not None])
                speech_slices.append([start_ru, str(text_ru), str(text_de), ' '.join(annot)])
                idx += 1

        # if len(aa_ru_all) != len(aa_de_all):
        #     msg = ' '.join(["\nWarning! Tiers", tier1.get("TIER_ID"), "and", tier2.get("TIER_ID"),
        #                     "have unequal lengths. Correct data before processing. "
        #                     "Check ELAN file for blank annotations or other errors."])
        #     raise ParseError(msg)

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
            efiles = [file.path for file in os.scandir(arg) if os.path.splitext(file.path)[1] == ".eaf"]
        elif os.path.splitext(arg)[1] == ".eaf":
            efiles.append(arg)
    if not efiles:
        raise ParseError("No .eaf files found")
    for efile in efiles:
        make_vrt_files(efile)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise ParseError("Provide the path(s) to separate ELAN file(s) or to a directory as command line arguments")
    print("Making .vrt for:")
    main()

