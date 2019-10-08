import argparse
import calendar
import logging
import os
import subprocess
import sys
import time

here = os.path.dirname(__file__)
wpt_root = os.path.abspath(os.path.join(here, os.pardir, os.pardir))

logger = logging.getLogger()

WEEKLY_EPOCH_SIZE = 604800
WEEKLY_EPOCH_OFFSET = -259200  # Monday, 29 December 1969 0:00:00

DEFAULT_EPOCH_UNTIL = calendar.timegm(time.gmtime())
DEFAULT_EPOCH_STEP = 86400
DEFAULT_NUM_REVISIONS = 1
DEFAULT_LOG_LEVEL = 30
DEFAULT_VERBOSE = False
DEFAULT_HEAD_REVISION = "origin/master"

REV_LIST_COUNT = 10000
TAGGED_REVISIONS = "merge_pr_"

MYPY = False
if MYPY:
    # MYPY is set to True when run under Mypy.
    from typing import Any
    from typing import Callable
    from typing import Dict
    from typing import List
    from typing import Text
    from typing import Union


def parser_debug_log_level(**kwargs):
    # type: (**Any) -> Any
    debug_level = kwargs.get("log_level", DEFAULT_LOG_LEVEL)

    if isinstance(debug_level, int):
        return debug_level

    try:
        return int(debug_level)
    except Exception:
        pass

    return debug_level


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


def parser_num_revisions(**kwargs):
    # type: (**Any) -> int
    num_revisions = kwargs.get("num_revisions", DEFAULT_NUM_REVISIONS)
    return int(num_revisions)


COMMAND_ARGS = {
    "epoch_until": {
        "name": "epoch-until",
        "default": DEFAULT_EPOCH_UNTIL,
        "help": "Show revisions older than a specific date in UNIX "
                "timestamp. NOW is the default value. For example: "
                "'1570345200'.",
        "parser": parser_epoch_until
    },
    "epoch_step": {
        "name": "epoch-step",
        "default": DEFAULT_EPOCH_STEP,
        "help": "Regular interval of seconds used to get the tagged revision. "
                "three-hourly, six-hourly, eight-hourly, twelve-hourly, "
                "daily, weekly or 3600, 7200, 10800 ...",
        "parser": parser_epoch_step
    },
    "head_revision": {
        "name": "head-revision",
        "default": DEFAULT_HEAD_REVISION,
        "help": "Head revision (Default: %s)" % DEFAULT_HEAD_REVISION,
        "parser": lambda **kwargs: kwargs.get("head_revision",
                                              DEFAULT_HEAD_REVISION),
    },
    "log_level": {
        "name": "log-level",
        "default": DEFAULT_LOG_LEVEL,
        "help": "Debug log level. For example: DEBUG, INFO, WARNING, ERROR, "
                "CRITICAL or an integer value like 10, 20 ",
        "parser": parser_debug_log_level
    },
    "num_revisions": {
        "name": "num-revisions",
        "default": DEFAULT_NUM_REVISIONS,
        "help": "Number of revisions to get.",
        "parser": parser_num_revisions
    },
    "verbose": {
        "name": "verbose",
        "default": DEFAULT_VERBOSE,
        "help": "Show more information in the output",
        "parser": lambda **kwargs: kwargs.get("verbose", DEFAULT_VERBOSE),
        "type": bool
    }
}


def get_git_cmd(repo_path):
    # type: (bytes) -> Callable[..., Text]
    """Create a function for invoking git commands as a subprocess."""
    def git(cmd, *args):
        # type: (Text, *Union[bytes, Text]) -> Text
        arg_list = list(item.decode("utf8") if isinstance(item, bytes) else item for item in args)  # noqa E501
        full_cmd = [u"git", cmd] + arg_list  # type: List[Text]
        try:
            logger.debug(" ".join(full_cmd))
            return subprocess.check_output(full_cmd, cwd=repo_path).decode("utf8").strip()  # noqa E501
        except subprocess.CalledProcessError as e:
            logger.critical("Git command exited with status %i" % e.returncode)
            logger.critical(e.output)
            sys.exit(1)
    return git


def get_tagged_revisions(commit, min_age, skip=0, max_count=10):
    # type: (bytes, int, int, int) -> Dict[..., Dict]
    '''
    Returns the tagged revisions indexed by the committer date.
    '''
    git = get_git_cmd(wpt_root)
    command = [
        "--no-walk",
        "--skip=%s" % skip,
        "--max-count=%s" % max_count,
        "--min-age=%s" % min_age,
        "--format=epoch:%ct:commit:%H:%D",
        commit
    ]
    result = {}
    for output_line in git("rev-list", *command).split("\n")[1::2]:
        # print output_line
        output = output_line.split(":")
        if len(output) > 5 and output[5].find(TAGGED_REVISIONS) > -1:
            revision = {}
            revision["epoch"] = int(output[1])
            revision["commit"] = output[3].strip()
            revision["tag"] = output[5].strip()
            result[int(output[1])] = revision
    return result


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
    head_revision = COMMAND_ARGS["head_revision"]["parser"](**kwargs)
    epoch_until = COMMAND_ARGS["epoch_until"]["parser"](**kwargs)
    num_revisions = COMMAND_ARGS["num_revisions"]["parser"](**kwargs)
    verbose = COMMAND_ARGS["verbose"]["parser"](**kwargs)

    iterator = 0
    result = []
    previous_revision = None

    # Iterates the rev-list command in bunchs of "rev_list_step"
    # items skipping the previous "rev_list_offset" and it is incremented in
    # "rev_list_step" each time no more valid tagged revisions are found in
    # the current set of revisions.
    # The loop ends once we reached the required number of revisions to return
    # or the are no more tagged revisions returned found by the rev-list
    # iterator.
    # Because it is posible to find the same revision as candidate for two
    # consecutives "epoch_step" (case I in the example) the loop checks if
    # previous revision added is equal to the current one and skip this on
    # positive case.
    #
    #   Fri   Sat   Sun   Mon   Tue   Wed   Thu   Fri   Sat
    #    |     |     |     |     |     |     |     |     |
    # -A---B-C---DEF---G---H--I-----------J-----K-L----M--N--
    #                                                       ^
    #                                                      now
    rev_list_offset = 0
    rev_list_step = REV_LIST_COUNT
    tagged_revisions = get_tagged_revisions(head_revision, epoch_until,
                                            rev_list_offset, rev_list_step)
    while iterator < num_revisions:
        if len(tagged_revisions) == 0:
            break
        # For epoch size equal to weekly we need to use a offset to start
        # the week on Monday 00:00:00.
        epoch_offset = 0
        if epoch_step == WEEKLY_EPOCH_SIZE:
            epoch_offset = WEEKLY_EPOCH_OFFSET
        min_age = ((((epoch_until - epoch_offset) / epoch_step) - iterator) * epoch_step) + epoch_offset  # noqa E501
        if min_age < 0:
            break
        try:
            tagged_revision = get_newer_tagged_revision(tagged_revisions,
                                                        min_age)
            if previous_revision != tagged_revision["commit"]:
                if verbose:
                    result.append("epoch: %(epoch)s commit: %(commit)s tag: %(tag)s" % tagged_revision)  # noqa E501
                else:
                    result.append("%(commit)s" % tagged_revision)
                previous_revision = tagged_revision["commit"]
            else:
                num_revisions += 1
            iterator += 1
        except ValueError:
            # Not revisions found in this set of tagged revision older
            # than epoch_until (skipping the first "rev_list_offset" values)
            rev_list_offset += rev_list_step
            tagged_revisions = get_tagged_revisions(head_revision,
                                                    epoch_until,
                                                    rev_list_offset,
                                                    rev_list_step)
    return result


def get_parser():
    # type: () -> argparse.ArgumentParser
    parser = argparse.ArgumentParser()
    for k in sorted(COMMAND_ARGS.iterkeys()):
        command_arg = COMMAND_ARGS[k]
        default_value = command_arg.get("default", None)
        command_arg_type = command_arg.get("type", None)
        if command_arg_type == bool:
            action = "store_false" if default_value else "store_true"
            parser.add_argument("--%s" % command_arg["name"],
                                action=action,
                                help=command_arg["help"])
        else:
            parser.add_argument("--%s" % command_arg["name"],
                                default=default_value,
                                help=command_arg["help"])

    return parser


def run_rev_list(**kwargs):
    # type: (**Any) -> None
    log_level = COMMAND_ARGS["log_level"]["parser"](**kwargs)
    logger.setLevel(log_level)
    logger.debug("Log level set to %s" % logger.getEffectiveLevel())
    for item in list_tagged_revisons(**kwargs):
        print(item)
    return
