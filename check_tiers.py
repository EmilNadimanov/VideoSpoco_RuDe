import os
import re
from subprocess import DEVNULL, check_call
import sys
import datetime as dt
from xml.etree import ElementTree as et


LINGUISTIC_TYPE_REF = {"utterance"}


class ParseError(Exception):
    """    The Exception class to use in case user input is incorrect  """

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


def check(efile):
    root = et.parse(efile).getroot()

    time_slots = dict()
    for ts in root.findall('.//TIME_ORDER/TIME_SLOT'):
        if ts.get('TIME_VALUE') is not None:
            time_slots[ts.get('TIME_SLOT_ID')] = int(ts.get('TIME_VALUE'))

    tiers = [t for t in root.findall('TIER') if t.get("LINGUISTIC_TYPE_REF") in LINGUISTIC_TYPE_REF]
    tier_number = 0  # each (2n)th tier is the translation of (2n-1)th tier (note that index [1] points to tier 2)

    flawless = True
    while tier_number < len(tiers):
        tier1, tier2 = tiers[tier_number], tiers[tier_number + 1]   # parsing tiers in pairs

        aa1, aa2 = tier1.findall('.//ALIGNABLE_ANNOTATION'), tier2.findall('.//ALIGNABLE_ANNOTATION')

        for aa1, aa2 in zip(aa1, aa2):
            start1, end1 = time_slots[aa1.get('TIME_SLOT_REF1')], time_slots[aa1.get('TIME_SLOT_REF2')]
            start2, end2 = time_slots[aa1.get('TIME_SLOT_REF1')], time_slots[aa1.get('TIME_SLOT_REF2')]
            start1, end1 = dt.timedelta(milliseconds=start1), dt.timedelta(milliseconds=end1)
            start2, end2 = dt.timedelta(milliseconds=start2), dt.timedelta(milliseconds=end2)
            text1 = aa1.find("ANNOTATION_VALUE").text
            text2 = aa2.find("ANNOTATION_VALUE").text
            if text1 is None:  # no translation for one of the tiers
                flawless = False
                print("Speaker:", tier1.get("TIER_ID"),
                      "\t Empty field:", text1, " | ", text2,
                      "\t Located between", start1, "and", end1)
            elif text2 is None:
                flawless = False
                print("Speaker:", tier2.get("TIER_ID"),
                      "\t Empty field:", text1, " | ", text2,
                      "\t Located between", start2, "and", end2)
        tier_number += 2

    if flawless:
        print("File seems to have no errors in intervals.")


def main():
    if len(sys.argv) < 2:
        raise ParseError("Provide the path to separate ELAN files or a directory as command line arguments")
    efiles = list()
    for arg in sys.argv[1:]:
        if os.path.exists(arg) is False:
            print("Location does not exist:", arg)
            continue
        elif os.path.isdir(arg):
            efiles += [file.path for file in os.scandir(arg) if os.path.splitext(file.path)[1] == ".eaf"]
        elif os.path.splitext(os.path.split(arg)[1])[1] == ".eaf":
            efiles.append(arg)

    for efile in efiles:
        print("Checking ", efile)
        check(efile)
        print('*'*30)


if __name__ == '__main__':
    main()
