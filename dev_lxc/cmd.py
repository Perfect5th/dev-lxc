#!/usr/bin/env python3
import argparse
import os
import random
import string
import subprocess
import sys

try:
    import yaml
    PY_YAML = True
except ImportError:
    PY_YAML = False

SERIES = ["bionic", "focal", "jammy", "noble", "oracular", "plucky"]
DAILY_SERIES = "plucky"


def create(series: str, config: str = ""):
    proj_dir = os.path.basename(os.getcwd())
    instance_name = os.path.basename(proj_dir) + f"-{series}"

    _create_container(instance_name, series, config)
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
    instance_name = os.path.basename(proj_dir) + f"-{series}"

    _start_if_stopped(instance_name)

    subprocess.run(
        [
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
            "bash",
        ],
    )

    if stop_after:
        print(f"Stopping {instance_name}")
        stop(series)


def remove(series: str):
    proj_dir = os.path.basename(os.getcwd())
    instance_name = os.path.basename(proj_dir) + f"-{series}"

    _remove(instance_name)


def exec_cmd(series: str, command: str, stop_after: bool, emphemeral: bool, *env_args):
    proj_dir = os.path.basename(os.getcwd())
    lxc_repo_path = f"/home/ubuntu/{os.path.basename(proj_dir)}"

    if emphemeral:
        ident = "".join(random.sample(string.ascii_lowercase, 12))
        instance_name = os.path.basename(proj_dir) + f"-{series}-{ident}"
        _create_container(instance_name, series)
    else:
        instance_name = os.path.basename(proj_dir) + f"-{series}"

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
        print(f"Error running command {command} on instance {instance_name}")
    else:
        print("Command execution completed successfully")

    if stop_after or emphemeral:
        print(f"Stopping {instance_name}")
        _stop(instance_name)

    if emphemeral:
        print(f"Removing {instance_name}")
        _remove(instance_name)


def start(series: str) -> None:
    proj_dir = os.path.basename(os.getcwd())
    instance_name = os.path.basename(proj_dir) + f"-{series}"

    _start_if_stopped(instance_name)


def stop(series: str) -> None:
    proj_dir = os.path.basename(os.getcwd())
    instance_name = os.path.basename(proj_dir) + f"-{series}"

    _stop(instance_name)


def _exec_config(series: str, config: str = "") -> None:
    """Executes the `dev-lxc-exec` section of `config` in the container for `series`."""
    if not config:
        return

    if not PY_YAML:
        print("PyYAML is not installed, skipping post-creation dev-lxc-exec")
        return

    with open(config) as config_fp:
        try:
            config_dict = yaml.safe_load(config_fp)
        except yaml.YAMLError as e:
            print(f"ERROR: Could not parse YAML from {config}: {e}")
            return

    if "dev-lxc-exec" not in config_dict:
        return

    dev_lxc_exec = config_dict["dev-lxc-exec"]

    if not isinstance(dev_lxc_exec, (str, list)):
        print(f"ERROR: dev-lxc-exec in {config} must be either a string or list of strings")
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
        print(f"ERROR: Instance {instance_name} already exists")
        sys.exit(4)

    if config:
        try:
            with open(config, "rb") as config_fp:
                config_input = config_fp.read()
        except OSError as e:
            print(f"ERROR: Could not read LXD config from {config}: {e}")
    else:
        config_input = None

    # Create the instance using the appropriate config.
    subprocess.run(
        [
            "lxc",
            "launch",
            f"{remote}:{series}",
            instance_name,
            "--config",
            f"raw.idmap=both {uid} 1000",
        ],
        input=config_input,
        check=True,
    )

    # Wait for cloud-init to finish.
    print(
        f"Waiting for {instance_name} to complete initialization and package installation"
        " (this might take awhile)"
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
            text=True
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
        print(f"Unable to remove instance {instance_name}")
    else:
        print(f"Removed instance {instance_name}")


def _start_if_stopped(instance_name: str) -> None:
    """Starts the LXD instance with name `instance_name` if it is not running.
    """
    status = _get_status(instance_name)

    if status == "STOPPED":
        print(f"Starting {instance_name}")
        subprocess.run(["lxc", "start", instance_name])


def _stop(instance_name: str) -> None:
    subprocess.run(["lxc", "stop", instance_name])


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
        help="stop the container after the exiting the shell"
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
            choices=SERIES,
        )

    create_parser.add_argument(
        "-c",
        "--config",
        type=str,
        help="An LXD config to configure the instance",
    )
    exec_parser.add_argument("command", type=str, help="The command to execute")

    parsed = parser.parse_args(sys.argv[1:])

    if hasattr(parsed, "env"):
        parsed.func(
            parsed.series,
            parsed.command,
            parsed.stop_after,
            parsed.ephemeral,
            *parsed.env
        )
    elif hasattr(parsed, "stop_after"):
        parsed.func(parsed.series, parsed.stop_after)
    elif hasattr(parsed, "config"):
        parsed.func(parsed.series, parsed.config)
    else:
        parsed.func(parsed.series)


if __name__ == "__main__":
    main()
