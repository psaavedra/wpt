import argparse
import logging
import os
import subprocess

here = os.path.dirname(__file__)
wpt_root = os.path.abspath(os.path.join(here, os.pardir, os.pardir))

logger = logging.getLogger()

TAGGED_REVISIONS = "merge_pr_*"

COMMAND_ARGS = {
    "max_count": {
        "name": "max-count",
        "help": "Limit the number of commits to output"
    },
    "skip": {
        "name": "skip",
        "help": "Skip number commits before starting to show the commit output"
    },
    "since": {
        "name": "since",
        "help": "Show commits more recent than a specific date. "
                "For example: 10 week ago"
    },
    "until": {
        "name": "until",
        "help": "Show commits older than a specific date. "
                "For example: yesterday"
    },
    "max_age": {
        "name": "max-age",
        "help": "Limit the commits output to specified max time range"
    },
    "min_age": {
        "name": "min_age",
        "help": "Limit the commits output to specified min time range"
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

    def append_arg(arg_name):
        arg_value = kwargs.get(arg_name, None)
        if arg_value:
            command.append("--%s" % COMMAND_ARGS[arg_name]["name"])
            command.append(arg_value)

    git = get_git_cmd(wpt_root)
    command = ["--tags=%s" % TAGGED_REVISIONS, "--no-walk"]
    for commands_arg in COMMAND_ARGS.iterkeys():
        append_arg(commands_arg)
    return git("rev-list", *command).split("\n")


def get_parser():
    # type: () -> argparse.ArgumentParser
    parser = argparse.ArgumentParser()
    for command_arg in COMMAND_ARGS.itervalues():
        parser.add_argument("--%s" % command_arg["name"],
                            default=None, help=command_arg["help"])
    return parser


def run_rev_list(**kwargs):
    # type: (**Any) -> None
    for item in list_tagged_revisons(**kwargs):
        print(item)
    return
