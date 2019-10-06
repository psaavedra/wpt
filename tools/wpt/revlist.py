import argparse
import logging
import os
import subprocess
import calendar
import time

here = os.path.dirname(__file__)
wpt_root = os.path.abspath(os.path.join(here, os.pardir, os.pardir))

logger = logging.getLogger()

WEEKLY_EPOCH_SIZE = 604800
WEEKLY_EPOCH_OFFSET = -259200  # Monday, 29 December 1969 0:00:00

DEFAULT_EPOCH_UNTIL = calendar.timegm(time.gmtime())
DEFAULT_EPOCH_STEP = 3600
DEFAULT_NUM_REVISIONS = 1
DEFAULT_LOG_LEVEL = 30
DEFAULT_VERBOSE = False
HEAD_REVISION = "master"
TAGGED_REVISIONS = "merge_pr_*"


def parser_debug_log_level(**kwargs):
    # type: (**Any) -> [Text|Number]
    debug_level = kwargs.get("log_level", DEFAULT_LOG_LEVEL)

    if isinstance (debug_level, int):
        return debug_level

    try:
        return int(debug_level)
    except Exception:
        pass

    return debug_level


def parser_epoch_step(**kwargs):
    # type: (**Any) -> Number]
    epoch_step = kwargs.get("epoch_step", DEFAULT_EPOCH_STEP)
    if isinstance (epoch_step, int):
        return epoch_step
    if epoch_step.lower() == "hourly":
        return 3600
    if epoch_step.lower() == "two-hourly":
        return 7200
    if epoch_step.lower() == "four-hourly":
        return 14400
    if epoch_step.lower() == "six-hourly":
        return 21600
    if epoch_step.lower() == "eight-hourly":
        return 28800
    if epoch_step.lower() == "twelve-hourly":
        return 43200
    if epoch_step.lower() == "daily":
        return 86400
    if epoch_step.lower() == "weekly":
        return 604800
    return int(epoch_step)


def parser_epoch_until(**kwargs):
    # type: (**Any) -> Number]
    epoch_until = kwargs.get("epoch_until", DEFAULT_EPOCH_UNTIL)
    if isinstance (epoch_until, int):
        return epoch_until
    if epoch_until.lower() == "now":
        return DEFAULT_EPOCH_UNTIL
    return int(epoch_until)


def parser_num_revisions(**kwargs):
    # type: (**Any) -> Number]
    num_revisions = kwargs.get("num_revisions", DEFAULT_NUM_REVISIONS)
    return int(num_revisions)


def parser_verbose(**kwargs):
    # type: (**Any) -> Boolean]
    return kwargs.get("verbose", DEFAULT_VERBOSE)


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
                "hourly, two-hourly, four-hourly, six-hourly, eight-hourly, "
                "twelve-hourly, daily, weekly or 3600, 7200, 86000 ...",
        "parser": parser_epoch_step
    },
    "num_revisions": {
        "name": "num-revisions",
        "default": DEFAULT_NUM_REVISIONS,
        "help": "Number of revisions to get.",
        "parser": parser_num_revisions
    },
    "log_level": {
        "name": "log-level",
        "default": DEFAULT_LOG_LEVEL,
        "help": "Debug log level. For example: DEBUG, INFO, WARNING, ERROR, "
                "CRITICAL or an integer value like 10, 20 ",
        "parser": parser_debug_log_level
    },
    "verbose": {
        "name": "verbose",
        "default": DEFAULT_VERBOSE,
        "help": "Show more information in the output",
        "parser": parser_verbose,
        "type": bool
    }
}


def get_git_cmd(repo_path):
    # type: (bytes) -> Callable[..., Text]
    """Create a function for invoking git commands as a subprocess."""
    def git(cmd, *args):
        # type: (Text, *Union[bytes, Text]) -> Text
        full_cmd = [u"git", cmd] + list(item.decode("utf8") if isinstance(item, bytes) else item for item in args)  # type: List[Text]
        try:
            logger.debug(" ".join(full_cmd))
            return subprocess.check_output(full_cmd, cwd=repo_path).decode("utf8").strip()
        except subprocess.CalledProcessError as e:
            logger.critical("Git command exited with status %i" % e.returncode)
            logger.critical(e.output)
            sys.exit(1)
    return git


def list_tagged_revisons(**kwargs):
    # type: (**Any) -> List[Text]
    logger.debug("list_tagged_revisons: %s" % kwargs)
    git = get_git_cmd(wpt_root)
    epoch_step = COMMAND_ARGS["epoch_step"]["parser"](**kwargs)
    epoch_until = COMMAND_ARGS["epoch_until"]["parser"](**kwargs)
    num_revisions = COMMAND_ARGS["num_revisions"]["parser"](**kwargs)
    verbose = COMMAND_ARGS["verbose"]["parser"](**kwargs)

    iterator = 0
    result = []
    previous_command_output = ""
    while iterator < num_revisions:
        min_age = (( epoch_until / epoch_step ) - iterator) * epoch_step
        # For epoch size equal to weekly we need to use a offset to start
        # the week on Monday 00:00:00.
        if epoch_step == WEEKLY_EPOCH_SIZE:
            min_age += WEEKLY_EPOCH_OFFSET
        if min_age < 0:
            break
        command = ["--max-count=1", "--tags=%s" % TAGGED_REVISIONS,
                   "--min-age=%s" % min_age]
        if verbose:
            command.append("--format=date: %cI epoch: %ct commit: %H %D")
        command.append("--no-walk")
        command.append(HEAD_REVISION)
        command_output = git("rev-list", *command)
        if command_output != previous_command_output:
            result.append(command_output.split("\n")[-1])  # we are only
            # intereted in the last line of the output
            previous_command_output = command_output
        else:
            num_revisions += 1
        iterator += 1
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
