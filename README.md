# dev-lxc

This is a tidy little Python script I use when I want to quickly create an [LXD system container][1] for development purposes. It mounts the current directory in the home directory of the instance.

## Installation

It's a single script file. Make sure you have [LXD installed][2] and Python 3.10 or higher. Get the file, make it executable, and put it on your `PATH` somewhere.

## Basic Usage

### Create an instance

Create an instance using a specific Ubuntu series, by codename:

    dev_lxc create jammy

Instance names are generated from the current directory + the series of the container; for example: `myProject-noble`. If you create another container of the same series in the same directory (or one with the same directory name elsewhere in your filesystem), a hex-character suffix will be added to the instance name to ensure uniqueness; for example: `myProject-noble-e8d`.

If you have a valid YAML file for configuring the instance (nice for if you want it to start with certain packages installed):

    dev_lxc create jammy --config ./my-config.yaml

### Interacting with existing instances

Use the commands below to interact with your existing instances. If there is only a partial match or if there are multiple matches for your current directory + series, you will be prompted to specify which instance to act upon. At this time, running these commands while specifying an instance name instead of its series is not supported.

### Open a shell in an instance

Once you've created an instance, you can spin up a shell in it:

    dev_lxc shell jammy

The default user (`ubuntu`) should be uid-mapped to your user, so file permissions should be okay.

### Exec a command in an instance

    dev_lxc exec jammy 'echo "hello"'

This executes using `bash`, so try not to get too fancy. You can also provide environment variables:

    dev_lxc exec jammy 'echo "hello $MITCH"' --env MITCH="mitchell"

### Stop or Start an instance

    dev_lxc stop jammy

Stops the instance from running. Most other commands (`shell`, `exec`) should start the instance if it's stopped before running.

    dev_lxc start jammy

Starts it up again.

### Remove Instance

    dev_lxc remove jammy

This deletes the instance. It is gone for good.

   [1]: https://canonical.com/lxd
   [2]: https://canonical.com/lxd/install
