# These are actually maintained in python-shelltoolbox.  Precise does not have
# that package, so we need to bootstrap the process by copying the functions
# we need here.

import subprocess

try:
    import shelltoolbox
except ImportError:
    def run(*args, **kwargs):
        """Run the command with the given arguments.

        The first argument is the path to the command to run.
        Subsequent arguments are command-line arguments to be passed.

        This function accepts all optional keyword arguments accepted by
        `subprocess.Popen`.
        """
        args = [i for i in args if i is not None]
        pipe = subprocess.PIPE
        process = subprocess.Popen(
            args, stdout=kwargs.pop('stdout', pipe),
            stderr=kwargs.pop('stderr', pipe),
            close_fds=kwargs.pop('close_fds', True), **kwargs)
        stdout, stderr = process.communicate()
        if process.returncode:
            exception = subprocess.CalledProcessError(
                process.returncode, repr(args))
            # The output argument of `CalledProcessError` was introduced in Python
            # 2.7. Monkey patch the output here to avoid TypeErrors in older
            # versions of Python, still preserving the output in Python 2.7.
            exception.output = ''.join(filter(None, [stdout, stderr]))
            raise exception
        return stdout

    def install_extra_repositories(*repositories):
        """Install all of the extra repositories and update apt.

        Given repositories can contain a "{distribution}" placeholder, that will
        be replaced by current distribution codename.

        :raises: subprocess.CalledProcessError
        """
        distribution = run('lsb_release', '-cs').strip()
        # Starting from Oneiric, `apt-add-repository` is interactive by
        # default, and requires a "-y" flag to be set.
        assume_yes = None if distribution == 'lucid' else '-y'
        for repo in repositories:
            repository = repo.format(distribution=distribution)
            run('apt-add-repository', assume_yes, repository)
        run('apt-get', 'clean')
        run('apt-get', 'update')
else:
    install_extra_repositories = shelltoolbox.install_extra_repositories
