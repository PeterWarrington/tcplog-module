# "Images of a wire – TCPLog: Congestion Control logging in the Linux kernel" - Source code

<img src="tcplog-logo.png" width="100px"/>

TCPLog is a independent research project for fulfilment of the University of Glasgow Level 4 Honours Computing Science BSc course.

TCPLog is a project for the logging of Congestion Control state for live TCP connections in the Linux kernel. The source code consists of:

* `tcplog.c`, `tcplog.h` - A kernel module which writes TCPLog formatted log information to a character device file.
* `scripts/capture_utility.py` - A utility for capturing from the `/dev/tcplog` character device.
* `scripts/visualise_utility.py` - A GUI utility for displaying TCPLog JSON files in an interactive graph and list view.
* `scripts/mininet_tester.py` - A utility for capturing TCPLogs under a Mininet virtual environments, with environment properties set as command-line arguments.
* `scripts/test_runner.py` - A utility that runs mininet_tester.py using four different environments. Runs unit tests and collects TCPLog results for each of these.
* `scripts/to_qvis.py` - A utility that converts TCPLog files so that they can be viewed using the Qvis web-app.
* `Vagrantfile` - Specifies the Vagrant environment for running and testing TCPLog.
* `Makefile` - Provides scriptlets for building, running, and testing TCPLog.

## Build instructions

### Requirements

The kernel module source code must be built under a Linux environment.

The Vagrantfile is provided to build a virtual machine for this purpose. Instructions are only provided for this Vagrant environment

On your host machine you must:

* Install the latest Python 3 with tkinter (tkinter is built into the Windows distribution, and is available as `python3-tk` on most Debians, `python-tk` on Mac OS Homebrew (Install guide: <https://brew.sh/>))
* Install Vagrant (https://developer.hashicorp.com/vagrant/install)
* Install Make (Windows: <https://gnuwin32.sourceforge.net/packages/make.htm>, Debian: `sudo apt install make`, Mac OS: `xcode-select --install`)

### Test steps

To test TCPLog and collect results:

On the host run `make test-all`

- This automatically creates the VM, builds the source, installs the module, and runs the tests - no need for the other steps.

### Build/install steps

1. Run `vagrant up` in the source code root directory to start the Linux VM.
2. Next, run `vagrant ssh` to access the VM's terminal prompt.
3. Within the VM, `cd ~/tcplog-module` to access the shared source code root.

If you JUST want to build TCPLog:

4. Within the VM, run `make`.

To install TCPLog:

4. Within the VM, run `make install`.

### Visualisation steps

Run `python3 scripts/visualise_utility.py <path to TCPLog file>`.

For command-line options run `python3 scripts/visualise_utility.py --help`.