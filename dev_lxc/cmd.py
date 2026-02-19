#!/usr/bin/env python3
# Copyright (c) 2024-2025 Mitch Burton
# SPDX-License-Identifier: MIT

import argparse
import os
import random
import string
import subprocess
import sys

try:
    import yaml
except ImportError:
    yaml = None

SERIES = ["bionic", "focal", "jammy", "noble", "questing"]
DAILY_SERIES = "resolute"

CONFIG_DOTDIR = ".dev-lxc"
DEFAULT_CONFIG = os.path.expanduser("~/" + CONFIG_DOTDIR)


# revert to original `create` pending helper function decisions
def create(series: str, config: str = "", profile: str = ""):
    instance_name = _create_instance_name(series)

    if config:
        print("Using config " + config)

    _create_container(instance_name, series, config, profile)
    _exec_config(series, config)

    print("All done! ✨ 🍰 ✨")
    print(
        f"""
Jump into your new instance with:
    dev_lxc shell {series}
"""
    )


def shell(series: str, stop_after: bool):
    proj_dir = os.path.basename(os.getcwd())
    lxc_repo_path = f"/home/ubuntu/{os.path.basename(proj_dir)}"
    instance_name = _fetch_instance_name(series)

    _start_if_stopped(instance_name)

    subprocess.run(
        [
            "lxc",
            "exec",
            "--cwd",
            lxc_repo_path,
            instance_name,
            "--",
            "sudo",
            "-u",
            "ubuntu",
            "bash",
        ],
    )

    if stop_after:
        print(f"Stopping {instance_name}")
        stop(instance_name)


def remove(series: str):
    instance_name = _fetch_instance_name(series)

    _remove(instance_name)


def exec_cmd(series: str, command: str, stop_after: bool, emphemeral: bool, *env_args):
    proj_dir = os.path.basename(os.getcwd())
    lxc_repo_path = f"/home/ubuntu/{os.path.basename(proj_dir)}"

    if emphemeral:
        ident = "".join(random.sample(string.ascii_lowercase, 12))
        instance_name = f"-{_fetch_instance_name(series)}-{ident}"
        _create_container(instance_name, series)
    else:
        instance_name = _fetch_instance_name(series)

    _start_if_stopped(instance_name)

    run_args = [
        "lxc",
        "exec",
        "--user",
        "1000",
        "--group",
        "1000",
        "--cwd",
        lxc_repo_path,
        "--env",
        "HOME=/home/ubuntu",
        "--env",
        "USER=ubuntu",
        instance_name,
    ]

    for env_arg in env_args:
        run_args.append("--env")
        run_args.append(env_arg)

    run_args += ["--", "bash", "-c", command]

    result = subprocess.run(run_args)

    if result.returncode:
        print(
            f"Error running command {command} on instance {instance_name}",
            file=sys.stderr,
        )
    else:
        print("Command execution completed successfully")

    if stop_after or emphemeral:
        print(f"Stopping {instance_name}")
        _stop(instance_name)

    if emphemeral:
        print(f"Removing {instance_name}")
        _remove(instance_name)


def start(series: str) -> None:
    instance_name = _fetch_instance_name(series)

    _start_if_stopped(instance_name)


def stop(series: str) -> None:
    instance_name = _fetch_instance_name(series)

    _stop(instance_name)


def _discover_config(series: str) -> str:
    """
    Produces the filepath of a default config, if one is found.

    Checks these locations in this order of priority:
      1. `.dev-lxc/{series}.yaml`
      2. `.dev-lxc/base.yaml`
      3. `~/.dev-lxc/{series}.yaml`
      4. `~/.dev-lxc/base.yaml`

    Returns the path or an empty string if none of the above exist.
    """
    series_yaml = series + ".yaml"
    home_dir = os.path.expanduser("~")

    paths_to_check = (
        os.path.join(*parts)
        for parts in (
            (CONFIG_DOTDIR, series_yaml),
            (CONFIG_DOTDIR, "base.yaml"),
            (home_dir, CONFIG_DOTDIR, series_yaml),
            (home_dir, CONFIG_DOTDIR, "base.yaml"),
        )
    )

    for path in paths_to_check:
        if os.path.isfile(path):
            return path

    return ""


def _exec_config(series: str, config: str = "") -> None:
    """Executes the `dev-lxc-exec` section of `config` in the container for `series`."""
    if not config:
        return

    if yaml is None:
        print("PyYAML is not installed, skipping post-creation dev-lxc-exec")
        return

    with open(config) as config_fp:
        try:
            config_dict = yaml.safe_load(config_fp)
        except yaml.YAMLError as e:
            print(f"ERROR: Could not parse YAML from {config}: {e}", file=sys.stderr)
            return

    if "dev-lxc-exec" not in config_dict:
        return

    dev_lxc_exec = config_dict["dev-lxc-exec"]

    if not isinstance(dev_lxc_exec, (str, list)):
        print(
            f"ERROR: dev-lxc-exec in {config} must be either a string or list of strings",
            file=sys.stderr,
        )
        return

    if isinstance(dev_lxc_exec, str):
        dev_lxc_exec = [dev_lxc_exec]

    for command in dev_lxc_exec:
        print(f"Executing: {command}")
        exec_cmd(series, str(command), False, False)


def _create_container(
    instance_name: str,
    series: str,
    config: str = "",
    profile: str = "",
) -> None:
    """Creates a new container with the given `instance_name`."""
    proj_dir = os.path.basename(os.getcwd())
    uid = os.getuid()

    if series == DAILY_SERIES:
        remote = "ubuntu-daily"
    else:
        remote = "ubuntu"

    # If we can check instance info, we know it already exists.
    info_call = subprocess.run(
        ["lxc", "info", instance_name],
        capture_output=True,
    )

    if info_call.returncode == 0:
        print(f"ERROR: Instance {instance_name} already exists", file=sys.stderr)
        sys.exit(4)

    if config:
        try:
            with open(config, "rb") as config_fp:
                config_input = config_fp.read()
        except OSError as e:
            print(
                f"ERROR: Could not read LXD config from {config}: {e}", file=sys.stderr
            )
            config_input = None
    else:
        config_input = None

    # Create the instance using the appropriate config.
    cmd = [
        "lxc",
        "launch",
        f"{remote}:{series}",
        instance_name,
        "--config",
        f"raw.idmap=both {uid} 1000",
    ]

    if profile:
        cmd.extend(["--profile", profile])

    subprocess.run(cmd, input=config_input, check=True)

    # Wait for cloud-init to finish.
    print(
        f"Waiting for {instance_name} to complete initialization and package installation"
        " (this might take a while)"
    )
    subprocess.run(
        ["lxc", "exec", instance_name, "--", "cloud-init", "status", "--wait"],
    )

    # Mount the filesystem.
    lxc_repo_path = f"/home/ubuntu/{os.path.basename(proj_dir)}"
    subprocess.run(
        [
            "lxc",
            "config",
            "device",
            "add",
            instance_name,
            f"{instance_name}-src",
            "disk",
            f"source={os.getcwd()}",
            f"path={lxc_repo_path}",
        ],
        check=True,
    )


def _get_status(instance_name: str) -> str:
    """Gets the current status of the dev container for `series`."""

    try:
        result = subprocess.run(
            ["lxc", "info", instance_name],
            capture_output=True,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        if "Instance not found" in e.stderr:
            return "NONEXISTENT"
        raise e

    # Poor-person's YAML decoder.
    for line in result.stdout.splitlines():
        line = line.strip()

        if not line:
            continue

        k, v = line.split(":", 1)
        v = v.strip()

        if k == "Status":
            return v

    return "UNKNOWN"


def _remove(instance_name: str) -> None:
    result = subprocess.run(
        [
            "lxc",
            "delete",
            "--force",
            instance_name,
        ],
    )

    if result.returncode:
        # Output from the above goes to stdout/err so it should be apparent
        # what the error was.
        print(f"Unable to remove instance {instance_name}", file=sys.stderr)
    else:
        print(f"Removed instance {instance_name}")


def _start_if_stopped(instance_name: str) -> None:
    """Starts the LXD instance with name `instance_name` if it is not running."""
    status = _get_status(instance_name)

    if status == "STOPPED":
        print(f"Starting {instance_name}")
        subprocess.run(["lxc", "start", instance_name])


def _stop(instance_name: str) -> None:
    subprocess.run(["lxc", "stop", instance_name])


def _fetch_instance_name(series: str) -> str:
    """
    Accepts a series name from calling function, searches for extant instance
    by the name "proj_dir + series", resolves case where instance name matches with
    multiple extant instances, and returns a single instance_name; may return
    "" if no match found or user declines input in _get_instance_name_input
    """
    instance_name = _create_default_instance_name(series)
    matches = _get_instance_name_matches(instance_name)
    if not matches:
        return ""
    elif len(matches) == 1 and str(matches[0]) == instance_name:
        return instance_name
    else:
        instance_name = _get_instance_name_input(instance_name, matches)
        return instance_name


def _create_instance_name(series: str) -> str:
    """
    Accept series string name from calling function, and return a new instance name that does
    not conflict with any existing instance names
    """
    instance_name = _create_default_instance_name(series)
    if _get_instance_name_matches(instance_name):
        return _create_variant_instance_name(instance_name)
    else:
        return instance_name


def _get_instance_name_matches(instance_name: str) -> list[str]:
    """Accepts an instance name and returns list of instances whose names include {instance_name}"""
    matches = subprocess.run(
        ["lxc", "ls", "--all-projects", "-c", "n", "-f", "csv", instance_name],
        # `lxc ls` command note:
        # "-c n" -> "instance data column: name"
        # "-f csv" -> "output format type: csv"
        capture_output=True,
        text=True,
    )
    formatted_matches = matches.stdout.strip().split()
    return formatted_matches


def _create_default_instance_name(series: str) -> str:
    """Returns instance_name string, constructed from project directory and instance series"""
    proj_dir = os.path.basename(os.getcwd())
    instance_name = f"{proj_dir}-{series}"
    return instance_name


def _create_variant_instance_name(instance_name: str) -> str:
    """Accepts instance name and returns a variant name to avoid naming collisions"""
    variant_name = (
        f"{instance_name}-{''.join(random.choices(string.hexdigits, k=3)).lower()}"
    )
    while _get_instance_name_matches(variant_name) != []:
        variant_name += "".join(random.choices(string.hexdigits, k=1)).lower()
    return variant_name


def _get_instance_name_input(instance_name: str, matches: list) -> str:
    """When multiple instances match {instance_name}, allows user to specify instance to act upon"""
    if len(matches) == 1:
        print(f"One partial match for {instance_name};\n")
        choice = _get_confirmation(f"Interact with instance {matches[0]}? [Y/n]: ")
        if choice:
            instance_name = str(matches[0])
        else:
            return ""
    else:
        print(f"Multiple existing instances match the name '{instance_name}':\n-----")
        for index, match in enumerate(matches):
            print(f"[{index}]\t{match}")

        while True:
            choice = input(
                "Enter the index of the instance you would like to act upon: "
            )
            try:
                instance_index = int(choice)
                if 0 <= instance_index < len(matches):
                    break
                else:
                    print(f"Error: Index must be between 0 and {len(matches) - 1}")
            except ValueError:
                print(f"Error: {choice} is not an integer")
        instance_name = matches[instance_index]

    return instance_name


def _get_confirmation(prompt: str) -> bool:
    """
    Accept a prompt from a function needing user confirmation and return a bool
    representing the user's choice to proceed (True) or not (False); default is True
    """
    while True:
        choice = input(prompt).strip().lower()
        if choice == "":
            return True
        if choice in ("y", "yes"):
            return True
        elif choice in ("n", "no"):
            return False
        else:
            print("Invalid entry - please enter 'y' or 'n'")


def main():
    parser = argparse.ArgumentParser(
        prog="dev_lxc",
        description="Create, shell into, and remove developer containers",
    )

    subparsers = parser.add_subparsers(required=True)

    create_parser = subparsers.add_parser(
        "create",
        help="creates a container using the given Ubuntu series as a base",
    )
    create_parser.set_defaults(func=create)

    shell_parser = subparsers.add_parser(
        "shell",
        help="create a bash session in the given series's container",
    )
    shell_parser.set_defaults(func=shell)
    shell_parser.add_argument(
        "--stop-after",
        action="store_true",
        help="stop the container after the exiting the shell",
    )

    remove_parser = subparsers.add_parser(
        "remove",
        help="removes a container identified by Ubuntu series",
    )
    remove_parser.set_defaults(func=remove)

    exec_parser = subparsers.add_parser(
        "exec",
        help="executes an arbitrary command in the given series's container",
    )
    exec_parser.set_defaults(func=exec_cmd)
    exec_parser.add_argument("--env", nargs="*", default=[])
    exec_parser.add_argument(
        "--stop-after",
        action="store_true",
        help="stop the container after execution completes",
    )
    exec_parser.add_argument(
        "--ephemeral",
        action="store_true",
        help="use a temporary container that is deleted afterwards",
    )

    start_parser = subparsers.add_parser(
        "start",
        help="starts the given series's container",
    )
    start_parser.set_defaults(func=start)

    stop_parser = subparsers.add_parser(
        "stop",
        help="stops the given series's container",
    )
    stop_parser.set_defaults(func=stop)

    for subparser in (
        create_parser,
        shell_parser,
        remove_parser,
        exec_parser,
        start_parser,
        stop_parser,
    ):
        subparser.add_argument(
            "series",
            type=str,
            help="The Ubuntu series used as the base for the container",
            choices=SERIES + [DAILY_SERIES],
        )

    create_parser.add_argument(
        "-c",
        "--config",
        type=str,
        help="The path to a LXD config to apply to the instance",
    )

    create_parser.add_argument(
        "-p",
        "--profile",
        type=str,
        help="The name of a LXD profile to apply to the instance",
    )

    exec_parser.add_argument("command", type=str, help="The command to execute")

    parsed = parser.parse_args(sys.argv[1:])

    if hasattr(parsed, "env"):
        parsed.func(
            parsed.series,
            parsed.command,
            parsed.stop_after,
            parsed.ephemeral,
            *parsed.env,
        )
    elif hasattr(parsed, "stop_after"):
        parsed.func(parsed.series, parsed.stop_after)
    elif hasattr(parsed, "config"):
        parsed.func(
            parsed.series,
            parsed.config or _discover_config(parsed.series),
            parsed.profile,
        )
    else:
        parsed.func(parsed.series)


if __name__ == "__main__":
    main()
