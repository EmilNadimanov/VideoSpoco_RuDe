import os
import re
from subprocess import DEVNULL, check_call
import sys
import datetime as dt
from xml.etree import ElementTree as et

# Any questions about this code can be sent to nadimaemi@gmail.com
# I may answer them. I may not.

# German and Russian versions of the same lines have identical time slots. Therefore only one file should be created
#  for both such lines. If n verses are exactly within one timeslot, only one of them will be used to create
#  a ffmpeg command
already_created = set()
LINGUISTIC_TYPE_REF = {"utterance"}  # we are interested in specific tiers for cutting videos


class ParseError(Exception):
    """    The Exception class to use in case something is incorrect  """

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


def mkdir(name):
    try:
        os.mkdir(name)
    except FileExistsError:
        pass


def make_subtitles(filename, slice_):
    """
    Makes an .srt files in Subtitles directory for each videofile.
    Then converts them to .ass files to hardcode them into the picture via ffmpeg.

    Having that many subtitles files is necessary to make ffmpeg faster:
      when the -ss option stands before the -i option ffmpeg does not read the whole video to reach lines which
      appear at the end of the file. Otherwise it can take about 20 seconds to make subtitles for a single fragment.
    As a tradeoff, subtitles should then start from 00:00:00 for each video fragment. Therefore, no single file for
      subtitles can be used.
    For details on the order of arguments check the manual for this command.
    """
    mkdir("./Subtitles/{}".format(filename))
    for start, end, textRu, textDe, tier_id in slice_:
        mkdir("./Subtitles/{}/SRT".format(filename))

        subtitle_name = "{}-{}-{}-{}".format(filename, start, end, tier_id)
        start, end = "00:00:00,000", str(dt.timedelta(milliseconds=end - start))
        end += ",000" if len(end) == 7 else "0" * (11 - len(end))  # to comply with the srt format of time values.
        subs = open("./Subtitles/{}/SRT/{}.srt".format(filename, subtitle_name), 'w')
        subs.write("1\n" +
                   re.sub(r'\.', ',', "{} --> {}\n".format(start, end)) +
                   "{}\n".format(textRu) +
                   "{}\n\n".format(textDe))
        subs.close()
        command = \
            "ffmpeg -i ./Subtitles/{}/SRT/{}.srt ./Subtitles/{}/{}.ass".format(filename, subtitle_name,
                                                                               filename, subtitle_name)
        check_call(['/bin/sh', '-c', command + " -y -loglevel 24"], stdout=DEVNULL)
    check_call(['rm', '-rd', "./Subtitles/{}/SRT".format(filename)])  # clear unnecessary .srt files


def cut_video(video_path, filename, slice_):
    """
     Write a ffmpeg command to VideoBatch.sh
     A prototypical ffmpeg command for this function looks like this:
        ffmpeg -ss <start Time> -i <input file> -t <duration Time> <output_file_with_extension>
     For details on options used here read "man ffmpeg", for Time format read 'man ffmpeg-utils'.
    """
    # GET TIME VALUES
    i = filename
    ss = slice_[0] / 1000
    t = (slice_[1] - slice_[0]) / 1000

    # GET PROPER FILENAME AND EXTENSION
    r = re.compile(r"{}\.[a-zA-Z0-9]*".format(filename))
    # Variable full_filename takes the first one from all matching videos, because filenames are supposed to be
    #  unique, as mentioned in the docsting to main()
    full_filename = list(filter(r.match, os.listdir(video_path)))[0]
    extension = full_filename[len(filename):]

    cut_result = "{}-{}-{}-{}{}".format(i, slice_[0], slice_[1], slice_[4], extension)
    if cut_result in already_created:
        return
    else:
        already_created.add(cut_result)

    subtitles = "./Subtitles/{}/{}-{}-{}-{}.ass".format(filename, filename, slice_[0], slice_[1], slice_[4])
    command = \
        "ffmpeg -ss {} -i {}/{}{} -t {} -vf ass={} ./OUT/{}".format(ss, video_path, filename,
                                                                    extension, t, subtitles, cut_result)
    check_call(['/bin/sh', '-c', command + " -y -loglevel 24"])


def extract_speech(efiles):
    """
    This function extracts speech from intervals and saves it, as well as its' translation, the time when the line is
    pronounces and the name of the tier (typically the speaker's name).
    Timeslots are encloded in ELAN files as tags:
        First, TIME_SLOT_ID's serve as keys to TIME_VALUES in milliseconds. Some id's have no values - they are ignored.
        Second, each fragment of speech has TIME_SLOT_REF1 and TIME_SLOT_REF1, timeslot id's that represent the
            beginning and the end of a fragment.
    """
    time_slots = dict()  # key and value are {time_slot_id: time_value}
    speech_slices = dict()  # ties intervals in an ELAN file to the name of this file

    print("Parsing ELAN files")
    for efile in efiles:
        filename, extension = os.path.splitext(os.path.split(efile)[1])
        if extension != ".eaf":
            continue
        print("\t", efile, sep='')
        speech_slices[filename] = list()

        # ELAN files are XML files and are parsed accordingly
        root = et.parse(efile).getroot()
        for ts in root.findall('.//TIME_ORDER/TIME_SLOT'):
            if ts.get('TIME_VALUE') is not None:
                time_slots[ts.get('TIME_SLOT_ID')] = int(ts.get('TIME_VALUE'))

        tiers = [t for t in root.findall('TIER') if t.get("LINGUISTIC_TYPE_REF") in LINGUISTIC_TYPE_REF]
        tier_number = 0  # each (2k)th tier is the translation of (2k-1)th tier (note that index [1] points to tier 2)

        while tier_number < len(tiers):  # a while-loop because we need to parse tiers in pairs
            tier1, tier2 = tiers[tier_number], tiers[tier_number + 1]

            # An attempt to find a tier in German based on its name; Tiers are supposed to be ordered Russian first,
            # German second. However, this variable assignment helps avoid mistakes
            ru_tier, de_tier = (tier2, tier1) if re.search(r'[a-zA-Z]', tier1.get("TIER_ID")) is not None\
                else (tier1, tier2)

            aa_ru_all = ru_tier.findall('.//ALIGNABLE_ANNOTATION')
            aa_de_all = de_tier.findall('.//ALIGNABLE_ANNOTATION')
            idx = 0

            while idx < min(len(aa_ru_all), len(aa_de_all)):
                aa_ru, aa_de = aa_ru_all[idx], aa_de_all[idx]
                start_ru = time_slots[aa_ru.get('TIME_SLOT_REF1')]
                end_ru = time_slots[aa_ru.get('TIME_SLOT_REF2')]  # almost equal or equal for valid pairs
                start_de = time_slots[aa_de.get('TIME_SLOT_REF1')]

                # we pop empty intervals that have no pairs because they were added by mistake
                if abs(int(start_ru) - int(start_de)) > 100:  # triggers if annotations are more than 10ms apart
                    if int(start_de) < int(start_ru):  # empty intervals appear earlier than
                        aa_de_all.pop(idx)
                    else:
                        aa_ru_all.pop(idx)
                else:
                    text_ru = aa_ru.find("ANNOTATION_VALUE").text
                    text_de = aa_de.find("ANNOTATION_VALUE").text
                    speech_slices[filename].append([start_ru, end_ru, str(text_ru), str(text_de)])
                    idx += 1
            tier_number += 2
            # if len(aa_ru_all) != len(aa_de_all):
            #     msg = ' '.join(["\nWarning! Tiers", tier1.get("TIER_ID"), "and", tier2.get("TIER_ID"), "in", efile,
            #                     "have unequal lengths. Correct data before processing. "
            #                     "Check ELAN file for blank intervals or other errors."])
            #     raise ParseError(msg)

        speech_slices[filename].sort(key=(lambda x: x[1]))  # orders speech for the whole efile chronologically;
        for id_, list_ in enumerate(speech_slices[filename], start=1):
            list_.append(id_)  # this adds a unique id to every list in ordered speech_slices
    return speech_slices


def main(efiles, videofiles, video_path):
    """
    The script takes two arguments:
        1. The path to the directory with ELAN files
        2. The path to the directory with Videofiles
    It creates .ass files used as subtitles for video fragments;
    It creates a shell script (without a '#!/bin/bash' for safety reasons) with commands that cut the videofiles in
      accordance with the data in ELAN files with corresponding names and hardcodes subtitiles into the picture;
    PLEASE Read documentation to this script in the Documentation directory.
    """
    speech_slices = extract_speech(efiles)

    videofile_names = [os.path.splitext(os.path.split(filename)[1])[0] for filename in videofiles]

    for filename, slices in speech_slices.items():
        if filename in videofile_names and slices != []:
            print("Making subtitles for", filename, end='', flush=True)
            make_subtitles(filename, slices)
            print("\tDone!", flush=True)
            print("Cutting down fragments for", filename, flush=True)
            for slice_ in slices:
                cut_video(video_path, filename, slice_)
            print("\tDone!", flush=True)
        else:
            print("Warning! An ELAN file with no corresponding videofile, no video will be cut: ", filename)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise ParseError("Provide arguments as follows:\n"
                         "$... process_video.py <Path to ELAN files directory> <Path to videos directory> \n OR \n"
                         "$... process_video.py <Path to an ELAN file> <Path to a videofile>")
    elif not os.path.exists(sys.argv[1]) or not os.path.exists(sys.argv[2]):
        raise ParseError("Provide correct paths.")

    if os.path.isdir(sys.argv[1]) and os.path.isdir(sys.argv[2]):
        efiles = [file.path for file in os.scandir(sys.argv[1]) if os.path.splitext(file.path)[1] == ".eaf"]
        videofiles = [file.path for file in os.scandir(sys.argv[2])]
        video_path = sys.argv[2]
    elif os.path.isfile(sys.argv[1]) and os.path.isfile(sys.argv[2]):
        efiles = [os.path.relpath(sys.argv[1])]
        videofiles = [os.path.relpath(sys.argv[2])]
        video_path = os.path.split(os.path.relpath(sys.argv[2]))[0]  # get relative path to the file for formatting
    else:
        raise ParseError("Provide either two files or two directories.")
    mkdir("OUT")
    mkdir("Subtitles")

    main(efiles, videofiles, video_path)
