import argparse
import calendar
import logging
import os
import time
from tools.wpt.testfiles import get_git_cmd

here = os.path.dirname(__file__)
wpt_root = os.path.abspath(os.path.join(here, os.pardir, os.pardir))

logger = logging.getLogger()

DEFAULT_EPOCH_STEP = 86400
DEFAULT_EPOCH_THESHOLD = 600
DEFAULT_EPOCH_UNTIL = calendar.timegm(time.gmtime())
DEFAULT_MAX_COUNT = 1

FOR_EACH_REF_MAX_COUNT = 100000

TAGGED_REVISIONS = "refs/tags/merge_pr_*"

WEEKLY_EPOCH_SIZE = 604800
WEEKLY_EPOCH_OFFSET = -259200  # Monday, 29 December 1969 0:00:00


MYPY = False
if MYPY:
    # MYPY is set to True when run under Mypy.
    from typing import Any
    from typing import Dict
    from typing import List
    from typing import Text


def parser_epoch_step(**kwargs):
    # type: (**Any) -> int
    epoch_step = kwargs.get("epoch_step", DEFAULT_EPOCH_STEP)
    if isinstance(epoch_step, int):
        return epoch_step
    if epoch_step.lower() == "three-hourly":
        return 10800
    if epoch_step.lower() == "six-hourly":
        return 21600
    if epoch_step.lower() == "twelve-hourly":
        return 43200
    if epoch_step.lower() == "daily":
        return 86400
    if epoch_step.lower() == "weekly":
        return 604800
    return int(epoch_step)


def parser_epoch_until(**kwargs):
    # type: (**Any) -> int
    epoch_until = kwargs.get("epoch_until", DEFAULT_EPOCH_UNTIL)
    if isinstance(epoch_until, int):
        return epoch_until
    if epoch_until.lower() == "now":
        return DEFAULT_EPOCH_UNTIL
    return int(epoch_until)


def parser_max_count(**kwargs):
    # type: (**Any) -> int
    max_count = kwargs.get("max_count", DEFAULT_MAX_COUNT)
    return int(max_count)


COMMAND_ARGS = {
    "epoch_until": {
        "name": "epoch-until",
        "default": DEFAULT_EPOCH_UNTIL,
        "help": "Show revisions older than a specific date in UNIX "
                "timestamp. NOW is the default value. For example: "
                "'1570345200'.",
        "parser": parser_epoch_until
    },
    "epoch_threshold": {
        "name": "epoch-threshold",
        "default": DEFAULT_EPOCH_THESHOLD,
        "help": "Safety threshold respect now "
                "(default: %s seconds)." % DEFAULT_EPOCH_THESHOLD,
        "parser": lambda **kwargs: int(kwargs.get("epoch_threshold",
                                                  DEFAULT_EPOCH_THESHOLD)),
        "type": int
    },

    "epoch_step": {
        "name": "epoch-step",
        "default": DEFAULT_EPOCH_STEP,
        "help": "Regular interval of seconds used to get the tagged revision. "
                "three-hourly, six-hourly, eight-hourly, twelve-hourly, "
                "daily, weekly or 3600, 7200, 10800 ...",
        "parser": parser_epoch_step
    },
    "max_count": {
        "name": "max-count",
        "default": DEFAULT_MAX_COUNT,
        "help": "Maximum number of revisions to be returned by the command "
                "(default: %s)." % DEFAULT_MAX_COUNT,
        "parser": parser_max_count
    }
}


def get_tagged_revisions(pattern):
    # type: (bytes) -> List[..., Dict]
    '''
    Returns the tagged revisions indexed by the committer date.
    '''
    git = get_git_cmd(wpt_root)
    command = [
        pattern,
        '--sort=-committerdate',
        '--format=%(refname:lstrip=2) %(objectname) %(committerdate:raw)',
        '--count=%s' % FOR_EACH_REF_MAX_COUNT
    ]
    return git("for-each-ref", *command)


def get_newer_tagged_revision(tagged_revisions, min_age):
    # type: (Dict, int) -> Dict
    epoch = max(i for i in tagged_revisions.keys() if i < min_age)
    c = tagged_revisions.keys()
    c.sort(reverse=True)
    return tagged_revisions[epoch]


def list_tagged_revisons(**kwargs):
    # type: (**Any) -> List[Text]
    logger.debug("list_tagged_revisons: %s" % kwargs)
    epoch_step = COMMAND_ARGS["epoch_step"]["parser"](**kwargs)
    epoch_threshold = COMMAND_ARGS["epoch_threshold"]["parser"](**kwargs)
    epoch_until = COMMAND_ARGS["epoch_until"]["parser"](**kwargs)
    max_count = COMMAND_ARGS["max_count"]["parser"](**kwargs)

    if epoch_until > DEFAULT_EPOCH_UNTIL - epoch_threshold:
        epoch_until = DEFAULT_EPOCH_UNTIL - epoch_threshold
        logger.debug("epoch-until adjusted to %s using the safety epoch-threshold value (%s)" % (epoch_until, epoch_threshold))  # noqa E501

    iterator = 0

    # Iterates the tagged revisions in descending order finding the more
    # recent commit still older than a "min_age" value.
    # When a commit is found "min_age" is set to a new value multiplier of
    # "epoch_step" but still below of the date of the current commit found.
    # This needed to deal with intervals where no candidates were found
    # for the current "epoch_step" and the next candidate found is yet below
    # the lower values of the interval (it is the case of J and I for the
    # interval between Wed and Tue, in the example). The algorithm fix
    # the next "min_age" value based on the date value of the current one
    # skipping the intermediate values.
    # The loop ends once we reached the required number of revisions to return
    # or the are no more tagged revisions or the min_age reach zero.
    #
    #   Fri   Sat   Sun   Mon   Tue   Wed   Thu   Fri   Sat
    #    |     |     |     |     |     |     |     |     |
    # -A---B-C---DEF---G---H--IJ----------K-----L-M----N--O--
    #                                                       ^
    #                                                      now
    # Expected result: N,M,K,J,H,G,F,C,A

    # For epoch size equal to weekly we need to use a offset to start
    # the week on Monday 00:00:00.
    epoch_offset = 0
    if epoch_step == WEEKLY_EPOCH_SIZE:
        epoch_offset = WEEKLY_EPOCH_OFFSET
    min_age = ((((epoch_until - epoch_offset) / epoch_step) - iterator) * epoch_step) + epoch_offset  # noqa E501
    for tagged_revision in get_tagged_revisions(TAGGED_REVISIONS).split("\n"):
        revision_tag, revision_commit, revision_date, _ = tagged_revision.split(" ")  # noqa E501
        revision_date = int(revision_date)
        if min_age < 0:
            return
        if iterator >= max_count:
            return
        if revision_date <= min_age:
            print(revision_commit)
            iterator += 1
            min_age = ((((revision_date - epoch_offset) / epoch_step)) * epoch_step) + epoch_offset  # noqa E501


def get_parser():
    # type: () -> argparse.ArgumentParser
    parser = argparse.ArgumentParser()
    for k in sorted(COMMAND_ARGS.iterkeys()):
        command_arg = COMMAND_ARGS[k]
        default_value = command_arg.get("default", None)
        command_arg_type = command_arg.get("type", None)
        parser.add_argument("--%s" % command_arg["name"],
                            default=default_value,
                            type=command_arg_type,
                            help=command_arg["help"])
    return parser


def run_rev_list(**kwargs):
    # type: (**Any) -> None
    list_tagged_revisons(**kwargs)
    return
