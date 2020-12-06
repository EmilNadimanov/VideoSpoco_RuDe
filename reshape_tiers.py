import csv
import os
from subprocess import DEVNULL, check_call
from sys import argv
from xml.etree import ElementTree as et

class ParseError(Exception):
    """    The Exception class to use in case something is incorrect  """

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


def extract_non_tier_elements(root):
    before, after = [], []
    append_to_after = False
    for node in list(root):
        if node.tag == "TIER":
            append_to_after = True
            continue
        if append_to_after is True:
            after.append(node)
        else:
            before.append(node)
    return before, after


def extract_tier_elements(root):
    utter, non_utter = [], []
    meta = open(argv[2], 'r', newline='')
    reader = csv.reader(meta)
    for row in reader:
        russian = root.find(f".//TIER[@TIER_ID='{row[0]}']")
        german = root.find(f".//TIER[@TIER_ID='{row[1]}']")
        if russian is None:
            raise ParseError(f'Tier "{row[0]}" not found.')
        elif german is None:
            raise ParseError(f'Tier "{row[1]}" not found.')
        russian.set("LINGUISTIC_TYPE_REF", 'utterance')
        german.set("LINGUISTIC_TYPE_REF", 'utterance')
        utter.extend([russian, german])
    non_utter = list(set(root.findall('TIER')) - set(utter))
    return utter, non_utter


def main(filename):
    """
    We need to reorder tiers with utterances in ELAN files to assure that corresponding tiers go in pairs and that
     German translations follow Russian text.
    We have to separate four types of xml elements, which we then join together:
        1) The ones that go before tiers
        2) The ones that go after tiers
        3) The ones that are tiers with utterances(we reorder them). They come from the .csv metadata
        4) The ones that are tiers without utterances(we add them to the very end)
    """
    tree = et.parse(filename)
    root = tree.getroot()

    before_tiers, after_tiers = extract_non_tier_elements(root)
    utterance_tiers, non_utterance_tiers = extract_tier_elements(root)

    new_type = et.Element('LINGUISTIC_TYPE')
    new_type.set('GRAPHIC_REFERENCES', "false")
    new_type.set('LINGUISTIC_TYPE_ID', "utterance")
    new_type.set('TIME_ALIGNABLE', "true")
    new_type.tail = '\n '
    after_tiers = [new_type] + after_tiers

    for tier in root.findall('*'):
        root.remove(tier)
    root.extend(before_tiers + utterance_tiers + non_utterance_tiers + after_tiers)
    tree.write(argv[1], encoding='UTF-8', method='xml')

    with open(argv[1], mode='r+') as efile:
        content = efile.read()
        efile.seek(0, 0)
        efile.write('<?xml version="1.0" encoding="UTF-8"?>\n ' + content)


if __name__ == '__main__':
    if len(argv) < 2:
        print("Provide an ELAN file to reorder.")
        exit()
    elif os.path.exists(argv[1]) and os.path.splitext(argv[1])[1] == '.eaf'\
            and os.path.exists(argv[2]) and os.path.splitext(argv[2])[1] == '.csv':
        splitargv = os.path.splitext(argv[1])
        backup_file = splitargv[0] + "_backup" + splitargv[1]

        print(open(argv[1]).read(),
              file=open(backup_file, mode='w'))
        main(argv[1])
    elif os.path.exists(argv[1]) is False or os.path.splitext(argv[1])[1] == '.eaf' is False:
        print("ELAN file does not exist and/or is not .eaf-formatted. Provide a valid ELAN file.")
    else:
        print("Metadata file does not exist and/or is not .csv-formatted. Provide a valid .csv file with metadata.")

